"""Execution Router 与 Supervisor 真实闭环控制器（P1-1）。

在 :class:`~aipd_os.execution.execution_router.ExecutionRouter` 之上提供
「真实闭环」治理：进度/心跳、超时/取消、检查点续跑、时长/token/成本/工具调用
记录、产物校验、写回 Product Truth 与 Evidence Register、stale 传播、有界自动
返工、成熟度门槛、面向非技术用户的失败消息。

诚实性约束：不伪造成功。无真实模型时 cost=0、real_model=False；外部能力缺失
保持 external_blocked（external_dependency）。
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

from aipd_os.execution.adapter import AdapterError
from aipd_os.execution.execution_router import ExecutionRouter
from aipd_os.execution.registry import AdapterRegistry
from aipd_os.execution.runs import canonical_hash
from aipd_os.execution.closure_core import (
    EVENT_CANCELLED,
    EVENT_COMPLETE,
    EVENT_ESCALATED,
    EVENT_FAIL,
    EVENT_HEARTBEAT,
    EVENT_PROGRESS,
    EVENT_START,
    EVENT_STEP_COMPLETE,
    EVENT_STEP_START,
    EVENT_TIMED_OUT,
    ArtifactVerifier,
    ClosureStep,
    ClosureStore,
    CostLedger,
    RunControl,
    ReworkMachine,
    build_failure_message,
    check_maturity_floor,
)


def _now_monotonic() -> float:
    return time.monotonic()


def _monotonic_ms() -> int:
    return int(time.monotonic() * 1000)


class ClosureRun:
    """一次完整的闭环运行（进度、心跳、检查点、超时、取消、写回、返工）。"""

    def __init__(
        self,
        control: Optional[RunControl] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.control = control or RunControl()
        self.logger = logger or logging.getLogger("aipd.closure")
        # 每次 execute/resume 时由 _bind 注入
        self.store: Optional[ClosureStore] = None
        self.router: Optional[ExecutionRouter] = None
        self.registry: Optional[AdapterRegistry] = None
        self.state_db: Any = None
        self.tenant_id = "default"
        self.max_duration_s = 300.0
        self.max_step_duration_s = 120.0
        self.max_rework = 3
        self.heartbeat_interval_s = 0.1

        self.run_id = ""
        self.work_id = ""
        self.project_id = ""
        self.ledger = CostLedger()
        self._start_mono = 0.0
        self._last_heartbeat = 0.0
        self._generated: Dict[str, str] = {}
        self._completed_steps: List[str] = []

    # ---- 绑定运行环境 ----
    def bind(
        self,
        store: ClosureStore,
        router: ExecutionRouter,
        registry: AdapterRegistry,
        state_db: Any = None,
        tenant_id: str = "default",
        max_duration_s: float = 300.0,
        max_step_duration_s: float = 120.0,
        max_rework: int = 3,
        heartbeat_interval_s: float = 0.1,
    ) -> "ClosureRun":
        self.store = store
        self.router = router
        self.registry = registry
        self.state_db = state_db
        self.tenant_id = tenant_id
        self.max_duration_s = max_duration_s
        self.max_step_duration_s = max_step_duration_s
        self.max_rework = max_rework
        self.heartbeat_interval_s = heartbeat_interval_s
        return self

    # ---- 生命周期 ----
    def start(self, work_id: str, project_id: str = "") -> str:
        assert self.store is not None
        self.work_id = work_id
        self.project_id = project_id
        self.run_id = self.store.create_run(work_id, project_id)
        self._start_mono = _now_monotonic()
        self._last_heartbeat = 0.0
        self.store.emit_event(self.run_id, EVENT_START, message="run started")
        self.store.update_run(self.run_id, status="running")
        return self.run_id

    def heartbeat(self) -> None:
        assert self.store is not None
        run = self.store.get_run(self.run_id)
        self.store.emit_event(self.run_id, EVENT_HEARTBEAT,
                              step=run.get("current_step") or "", message="heartbeat")
        self._last_heartbeat = _now_monotonic()
        self.store.update_run(self.run_id, heartbeat_at=time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def _maybe_heartbeat(self) -> None:
        if _now_monotonic() - self._last_heartbeat >= self.heartbeat_interval_s:
            self.heartbeat()

    def emit_progress(self, progress: float, message: str = "", step: str = "") -> None:
        assert self.store is not None
        self.store.emit_event(self.run_id, EVENT_PROGRESS, step=step,
                              message=message, progress=max(0.0, min(1.0, progress)))

    def checkpoint(self, step_id: str, extra: Optional[Dict[str, Any]] = None) -> int:
        assert self.store is not None
        data = {
            "work_id": self.work_id,
            "project_id": self.project_id,
            "current_step": step_id,
            "completed_steps": list(self._completed_steps),
            "generated": dict(self._generated),
            "ledger": self.ledger.snapshot(),
            "extra": extra or {},
        }
        cid = self.store.save_checkpoint(self.run_id, step_id, data)
        self.store.update_run(self.run_id, current_step=step_id)
        return cid

    # ---- 主循环 ----
    def execute(self, work_id: str, steps: List[ClosureStep], project_id: str = "",
                required_floors: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        self.start(work_id, project_id)
        try:
            return self._run_steps(steps, required_floors or {}, base_steps=steps)
        except BaseException as exc:  # noqa: BLE001
            self.logger.exception("closure run aborted")
            self._emit_fail(str(exc))
            return self._finalize("failed", str(exc))

    def resume(self, run_id: str, steps: List[ClosureStep],
               required_floors: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """从上次检查点续跑（崩溃-重启-续跑）。"""
        assert self.store is not None
        run = self.store.get_run(run_id)
        self.run_id = run_id
        self.work_id = run["work_id"]
        self.project_id = run.get("project_id") or ""
        self._start_mono = _now_monotonic()
        self._last_heartbeat = 0.0
        cp = self.store.latest_checkpoint(run_id)
        if cp:
            data = cp["data"]
            self._completed_steps = list(data.get("completed_steps", []))
            self._generated = dict(data.get("generated", {}))
            ledger = data.get("ledger", {}) or {}
            self.ledger = CostLedger()
            self.ledger.tokens_in = ledger.get("tokens_in", 0)
            self.ledger.tokens_out = ledger.get("tokens_out", 0)
            self.ledger.cost = ledger.get("cost", 0.0)
            self.ledger.real_model = ledger.get("real_model", False)
            self.ledger.duration_ms = ledger.get("duration_ms", 0)
        todo = [s for s in steps if s.step_id not in self._completed_steps]
        self.store.update_run(run_id, status="running")
        self.store.emit_event(run_id, "resume",
                              message=f"resuming after {len(self._completed_steps)} steps")
        try:
            return self._run_steps(todo, required_floors or {}, base_steps=steps)
        except BaseException as exc:  # noqa: BLE001
            self.logger.exception("closure resume aborted")
            self._emit_fail(str(exc))
            return self._finalize("failed", str(exc))

    # ---- 内部：步骤循环 ----
    def _run_steps(self, steps: List[ClosureStep], required_floors: Dict[str, str],
                   base_steps: List[ClosureStep]) -> Dict[str, Any]:
        total = len(base_steps)
        for idx, step in enumerate(steps):
            if self.control.is_cancelled():
                return self._finalize("cancelled", "cancelled by user", step.step_id)
            if _now_monotonic() - self._start_mono > self.max_duration_s:
                return self._finalize("timed_out", "wall-clock timeout exceeded", step.step_id)
            floor = required_floors.get(step.capability_id)
            if floor:
                check = check_maturity_floor(self.registry, step.capability_id, floor)
                if not check["ok"]:
                    self._emit_escalated(step.step_id, check["reason"])
                    return self._finalize("escalated_user", check["reason"], step.step_id)
            input_hash = canonical_hash(step.inputs)
            if self._generated.get(step.step_id) == input_hash:
                self.emit_progress((idx + 1) / total,
                                   message="already generated, skipped duplicate",
                                   step=step.step_id)
                continue
            action = self._execute_step(step, input_hash, total, idx)
            if action == "done":
                continue
            if action == "escalate":
                return self._finalize("escalated_user",
                                      f"rework attempts exceeded for step {step.step_id}",
                                      step.step_id)
            if action == "cancelled":
                return self._finalize("cancelled", "cancelled by user", step.step_id)
            if action == "timed_out":
                return self._finalize("timed_out", "step/wall-clock timeout", step.step_id)
            if action == "failed":
                return self._finalize("failed", "step failed", step.step_id)
        return self._finalize("complete")

    def _execute_step(self, step: ClosureStep, input_hash: str, total: int,
                      offset: int) -> str:
        assert self.store is not None and self.router is not None
        self.store.update_run(self.run_id, current_step=step.step_id)
        self.store.emit_event(self.run_id, EVENT_STEP_START, step=step.step_id,
                              message=f"executing {step.step_id} via {step.capability_id}",
                              progress=(offset + 0.1) / total)
        rework = ReworkMachine(max_attempts=self.max_rework)
        context = dict(step.context or {})
        context.setdefault("work_id", self.work_id)
        context.setdefault("project_id", self.project_id)

        while True:
            self._maybe_heartbeat()
            if self.control.is_cancelled():
                return "cancelled"
            if _now_monotonic() - self._start_mono > self.max_duration_s:
                return "timed_out"

            out = self._invoke_router(step, context)
            if out is None:
                self._emit_escalated(step.step_id, "external dependency required")
                return "escalate"
            if out.get("interrupted") == "cancelled":
                return "cancelled"
            if out.get("interrupted") == "timed_out":
                return "timed_out"

            record = out["record"]
            result = out.get("result") or {}
            status = record.status

            if status in ("succeeded", "fallback"):
                produced = list(record.artifacts)
                checks = ArtifactVerifier().verify(step, produced, result)
                if not ArtifactVerifier.all_ok(checks):
                    self._log_tool_call(step, record, status="artifact_failed")
                    action = rework.record_failure("artifact_invalid",
                                                   "artifact verification failed")
                    self._emit_rework(step, rework)
                    if action == "escalate":
                        return "escalate"
                    continue
                self._write_back(step, record, result)
                self._log_tool_call(step, record, status=status)
                self._generated[step.step_id] = input_hash
                self._completed_steps.append(step.step_id)
                self.checkpoint(step.step_id)
                self.emit_progress((offset + 1) / total,
                                   message=f"step {step.step_id} complete", step=step.step_id)
                self.store.emit_event(self.run_id, EVENT_STEP_COMPLETE, step=step.step_id,
                                      message=f"{step.step_id} complete",
                                      progress=(offset + 1) / total)
                return "done"

            classification = record.error_classification or "tool_error"
            self._log_tool_call(step, record, status="failed")
            action = rework.record_failure(classification, record.error_message)
            self._emit_rework(step, rework)
            if action == "escalate":
                self._emit_escalated(step.step_id,
                                     f"rework exhausted: {record.error_message}")
                return "escalate"
            self.emit_progress((offset + 0.2) / total,
                               message=f"auto rework attempt {rework.attempts}",
                               step=step.step_id)

    def _emit_rework(self, step: ClosureStep, rework: ReworkMachine) -> None:
        assert self.store is not None
        self.store.emit_event(self.run_id, "rework", step=step.step_id,
                              message=f"rework attempt {rework.attempts} "
                                      f"({rework.last_classification})")

    def _emit_escalated(self, step: str, message: str) -> None:
        assert self.store is not None
        self.store.emit_event(self.run_id, EVENT_ESCALATED, step=step, message=message)

    def _emit_fail(self, message: str) -> None:
        assert self.store is not None
        self.store.emit_event(self.run_id, EVENT_FAIL, message=message)

    def _invoke_router(self, step: ClosureStep, context: Dict[str, Any]
                       ) -> Optional[Dict[str, Any]]:
        """在独立线程中调用 router.run，支持超时/取消中断在途工作。"""
        assert self.store is not None and self.router is not None
        holder: Dict[str, Any] = {}
        step_start = _now_monotonic()

        def _worker() -> None:
            try:
                holder["out"] = self.router.run(
                    self.work_id, step.capability_id, step.inputs,
                    context=context, project_id=self.project_id)
            except Exception as exc:  # noqa: BLE001
                holder["error"] = exc

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        while t.is_alive():
            if self.control.is_cancelled():
                return {"interrupted": "cancelled"}
            if _now_monotonic() - self._start_mono > self.max_duration_s:
                return {"interrupted": "timed_out"}
            if _now_monotonic() - step_start > self.max_step_duration_s:
                return {"interrupted": "timed_out"}
            self._maybe_heartbeat()
            time.sleep(0.01)
        t.join()
        if "error" in holder:
            self.store.emit_event(self.run_id, EVENT_FAIL, step=step.step_id,
                                  message=str(holder["error"]))
            return None
        return holder.get("out")

    def _log_tool_call(self, step: ClosureStep, record: Any, status: str) -> None:
        assert self.store is not None
        duration_ms = int(getattr(record, "duration_ms", 0) or 0)
        tokens_in = int(getattr(record, "tokens_in", 0) or 0)
        tokens_out = int(getattr(record, "tokens_out", 0) or 0)
        cost = float(getattr(record, "cost", 0.0) or 0.0)
        provider = str(getattr(record, "provider", "") or "")
        real_model = bool(cost > 0) or bool(provider and not provider.startswith("local"))
        self.store.log_tool_call(self.run_id, step.step_id, record.tool, status,
                                 duration_ms=duration_ms, tokens_in=tokens_in,
                                 tokens_out=tokens_out, cost=cost, real_model=real_model)
        self.ledger.record_call(tokens_in, tokens_out, cost, real_model, duration_ms)

    def _write_back(self, step: ClosureStep, record: Any, result: Dict[str, Any]) -> None:
        """成功步骤后写回 Product Truth（事实）与 Evidence Register（证据）。"""
        if self.state_db is None or not self.project_id:
            return
        spec = step.write_back or {}
        pid = self.project_id
        evidence_id = None
        if spec.get("evidence_title"):
            try:
                evidence_id = self.state_db.add_evidence(
                    self.tenant_id, pid, spec.get("evidence_kind", "execution"),
                    spec["evidence_title"], url=spec.get("evidence_url"),
                    summary=spec.get("evidence_summary"),
                    metadata={"run_id": self.run_id, "step_id": step.step_id,
                              "tool": record.tool})
            except Exception as exc:  # noqa: BLE001
                self.logger.warning("evidence write-back failed: %s", exc)
        if spec.get("fact_key") is not None:
            try:
                self.state_db.add_fact(
                    self.tenant_id, pid, spec["fact_key"],
                    spec.get("fact_value", result), status=spec.get("fact_status", "V"),
                    source=spec.get("fact_source", f"closure:{step.step_id}"),
                    version=spec.get("fact_version"),
                    confidence=spec.get("fact_confidence", 0.8))
                if evidence_id:
                    self.state_db.link_evidence(self.tenant_id, pid, evidence_id,
                                                evidence_id, relation="supports")
            except Exception as exc:  # noqa: BLE001
                self.logger.warning("fact write-back failed: %s", exc)

    # ---- stale 影响传播 ----
    def propagate_stale(self, changed_step_id: str, run_id: str = "",
                        reason: str = "upstream input changed") -> List[Dict[str, Any]]:
        assert self.store is not None
        rid = run_id or self.run_id
        stale: List[Dict[str, Any]] = []
        for dep in self.store.list_dependencies(rid):
            if dep["upstream_step"] == changed_step_id:
                self.store.add_stale(rid, dep["downstream_step"],
                                     artifact_path="", reason=reason)
                stale.append({"step_id": dep["downstream_step"], "reason": reason})
        return stale

    def _finalize(self, status: str, reason: str = "", step: str = ""
                  ) -> Dict[str, Any]:
        assert self.store is not None
        self.store.update_run(self.run_id, status=status, reason=reason or None)
        elapsed_ms = _monotonic_ms() - int(self._start_mono * 1000)
        self.ledger.duration_ms += max(0, elapsed_ms)
        if status == "complete":
            self.store.emit_event(self.run_id, EVENT_COMPLETE, step=step,
                                  message="run complete", progress=1.0)
        elif status == "cancelled":
            self.store.emit_event(self.run_id, EVENT_CANCELLED, step=step,
                                  message="run cancelled by user")
        elif status == "timed_out":
            self.store.emit_event(self.run_id, EVENT_TIMED_OUT, step=step,
                                  message="run timed out")
        elif status in ("failed", "escalated_user"):
            self.store.emit_event(self.run_id, EVENT_FAIL, step=step,
                                  message=reason or "run failed")
        events = self.store.list_events(self.run_id)
        tool_calls = self.store.list_tool_calls(self.run_id)
        failure_message = None
        if status in ("failed", "escalated_user", "timed_out", "cancelled"):
            failure_message = build_failure_message({
                "run_id": self.run_id, "work_id": self.work_id, "step": step,
                "reason": reason or "unknown",
                "kind": {"cancelled": "已取消", "timed_out": "已超时",
                         "escalated_user": "已升级待人工处理"}.get(status, "失败"),
                "saved": self._describe_saved(), "next_step": self._next_step_hint(status)})
        return {
            "run_id": self.run_id, "work_id": self.work_id,
            "project_id": self.project_id, "status": status,
            "reason": reason or None,
            "steps_completed": list(self._completed_steps),
            "events": [e.to_dict() for e in events],
            "tool_calls": tool_calls,
            "ledger": self.ledger.snapshot(),
            "stale": self.store.list_stale(self.run_id),
            "failure_message": failure_message,
        }

    def _describe_saved(self) -> str:
        if not self._completed_steps:
            return "尚未写入新的有效产物；执行进度与检查点已保存，可安全续跑"
        return (f"已完成步骤 {len(self._completed_steps)} 个"
                f"（{'、'.join(self._completed_steps)}）的产物与检查点均已持久化")

    @staticmethod
    def _next_step_hint(status: str) -> str:
        if status == "cancelled":
            return "您已取消本次执行；随时可重新运行或从断点恢复"
        if status == "timed_out":
            return "执行超时；可延长超时时间后从断点恢复，或减少单次工作量"
        if status == "escalated_user":
            return "自动重做已达上限；请由人工介入决策后继续，或调整输入后重试"
        return "请查看失败原因，修正输入后重试；断点进度已保存，可续跑"


# 兼容别名
RunClosure = ClosureRun


__all__ = ["ClosureRun", "RunClosure"]