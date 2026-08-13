"""统一执行路由。

:class:`ExecutionRouter` 负责：
1. 按能力标识选择适配器并进行能力可用性与输入校验；
2. 以带退避的重试循环执行，记录每次重试到 retry_lineage；
3. 主适配器失败后按 fallback_chain 降级切换（记录为 status='fallback'）；
4. 持久化执行记录与证据，返回规范化结果。
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from aipd_os.execution.adapter import AdapterError, ToolAdapter
from aipd_os.execution.models import (
    RETRYABLE_CLASSIFICATIONS,
    ExecutionRecord,
)
from aipd_os.execution.registry import AdapterRegistry
from aipd_os.execution.runs import RunStore, canonical_hash

DEFAULT_MAX_RETRIES = 3
BACKOFF_BASE_S = 0.05


class InputValidationError(Exception):
    """输入校验失败。"""

    def __init__(self, capability_id: str, errors: list[str]) -> None:
        self.capability_id = capability_id
        self.errors = errors
        super().__init__(
            f"input invalid for {capability_id}: {', '.join(errors)}"
        )


class ExecutionRouter:
    """统一执行路由。"""

    def __init__(
        self,
        store: RunStore,
        registry: AdapterRegistry,
        logger: logging.Logger | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        self.store = store
        self.registry = registry
        self.logger = logger or logging.getLogger("aipd.router")
        self.max_retries = max_retries

    # ---- 哈希 ----
    @staticmethod
    def _hash(data: Any) -> str:
        return canonical_hash(data)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    # ---- 主入口 ----
    def run(
        self,
        work_id: str,
        capability_id: str,
        input: dict[str, Any],
        context: dict[str, Any] | None = None,
        project_id: str = "",
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        """执行一次路由，返回 ``{'record': ExecutionRecord, 'result': dict|None}``。

        输入非法时抛出 :class:`InputValidationError`。
        提供 ``idempotency_key`` 时执行幂等去重：已有成功/进行中记录则不重复
        调用 adapter。重试仅对 ``PURE`` / ``IDEMPOTENT`` 副作用的适配器开放，
        外部副作用（发邮件/登记报价等）首次失败即停止，避免重复执行。
        """
        adapter = self.registry.get(capability_id)
        if adapter is None:
            raise KeyError(f"no adapter for capability: {capability_id}")

        context = context or {}
        project_id = project_id or context.get("project_id", "")
        context["project_id"] = project_id
        # 幂等 scope 需要 tenant_id：从 context 传播（缺省 'default'）。
        tenant_id = context.get("tenant_id") or "default"
        context["tenant_id"] = tenant_id
        idempotency_key = idempotency_key or context.get("idempotency_key", "")

        # 1) 能力可用性
        meta = adapter.discover()
        if not meta.get("available", True):
            record = self._mark_external_blocked(
                work_id, adapter, input, context, idempotency_key=idempotency_key)
            return {"record": record, "result": None}

        # 2) 输入校验
        errors = adapter.validate_input(input)
        if errors:
            raise InputValidationError(capability_id, errors)

        # 3) 幂等去重：仅在相同 (tenant_id, project_id, capability, key) scope
        #    内命中；跨项目/跨租户/跨能力绝不误去重。
        if idempotency_key:
            existing = self.store.find_by_idempotency_key(
                idempotency_key,
                tenant_id=tenant_id,
                project_id=project_id,
                capability=capability_id)
            if existing is not None:
                if existing.status in ("succeeded", "fallback"):
                    return {"record": existing,
                            "result": self.store.get_result(existing.run_id),
                            "deduped": True}
                if existing.status in ("running", "retried"):
                    return {"record": existing, "result": None,
                            "deduped": True, "in_progress": True}

        input_hash = self._hash(input)
        run_id = self.store.create_run(
            work_id, adapter.capability_id(), meta.get("provider", ""),
            meta.get("version", "1.0"), input_hash,
            project_id=project_id,
            tenant_id=tenant_id,
            adapter_id=adapter.capability_id(),
            capability=adapter.capability_id(),
            idempotency_key=idempotency_key,
            side_effect_mode=adapter.side_effect_mode(),
        )
        lineage: list[str] = []

        side_effect_mode = adapter.side_effect_mode()
        retry_allowed = side_effect_mode in ("PURE", "IDEMPOTENT")

        max_attempts = max(1, min(adapter.retry_limits(), self.max_retries))
        attempt = 0
        last_class = "tool_error"
        last_msg = ""
        while attempt < max_attempts:
            attempt += 1
            try:
                return self._finalize_success(
                    run_id, lineage, work_id, adapter, input, status="succeeded",
                    idempotency_key=idempotency_key,
                )
            except AdapterError as exc:
                last_msg = exc.message
                last_class = adapter.classify_failure(exc)
                self.logger.warning(
                    "adapter attempt failed",
                    extra={"aipd_fields": {
                        "run_id": run_id, "capability": capability_id,
                        "attempt": attempt, "classification": last_class,
                        "error": last_msg,
                        "side_effect_mode": side_effect_mode,
                    }},
                )
                if (self._retryable(last_class) and retry_allowed
                        and attempt < max_attempts):
                    prev = run_id
                    run_id = self.store.record_retry(prev)
                    lineage = list(self.store.get_run(run_id).retry_lineage)
                    time.sleep(BACKOFF_BASE_S * (2 ** (attempt - 1)))
                    continue
                # 不可重试 / 外部副作用 / 已用尽尝试次数 -> 进入降级
                break

        # 4) 降级链
        fallback_result = self._try_fallback(
            run_id, lineage, work_id, input, adapter, context,
            idempotency_key=idempotency_key,
        )
        if fallback_result is not None:
            return fallback_result

        # 5) 最终失败：外部阻塞错误保持 blocked_external 语义
        final_status = "blocked_external" if last_class == "external_blocked" else "failed"
        record = self.store.update_run(
            run_id,
            status=final_status,
            end_time=self._now(),
            duration_ms=0,
            error_classification=last_class,
            error_message=last_msg or "execution failed",
            result={},
        )
        return {"record": record, "result": None}

    # ---- 内部 ----
    def _retryable(self, classification: str) -> bool:
        return classification in RETRYABLE_CLASSIFICATIONS

    @staticmethod
    def _has_simulated_marker(result: Any) -> bool:
        """检测结果是否带 simulated 占位标记（顶层或常见包装键内）。

        imggen 在顶层返回 ``{"status": "simulated", ...}``；cad 把
        ``{"status": "simulated"}`` 放在 ``cad_contract`` 包装键内。
        """
        if not isinstance(result, dict):
            return False
        if result.get("simulated") is True or result.get("status") == "simulated":
            return True
        for wrapper in ("cad_contract", "contract"):
            inner = result.get(wrapper)
            if isinstance(inner, dict) and (
                inner.get("simulated") is True or inner.get("status") == "simulated"
            ):
                return True
        return False

    def _finalize_success(
        self,
        run_id: str,
        lineage: list[str],
        work_id: str,
        adapter: ToolAdapter,
        input: dict[str, Any],
        status: str,
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        raw = adapter.execute(input)
        result = adapter.normalize(raw)
        meta = result.pop("_meta", {}) if isinstance(result, dict) else {}
        artifacts = adapter.collect_artifacts(raw)
        evidence = adapter.persist_evidence(raw, run_id)
        output_hash = self._hash(result)
        end = self._now()
        side_effect_mode = adapter.side_effect_mode()

        # 防御纵深：adapter 返回 simulated 占位 → 绝不标记 succeeded。
        if self._has_simulated_marker(result):
            record = self.store.update_run(
                run_id,
                work_id=work_id,
                status="blocked_external",
                end_time=end,
                duration_ms=0,
                output_hash=output_hash,
                error_classification="external_blocked",
                error_message="adapter returned simulated placeholder; refusing to mark succeeded",
                result=result,
                side_effect_mode=side_effect_mode,
                idempotency_key=idempotency_key,
                remote_operation_id="",
            )
            return {"record": record, "result": None}

        remote_op = ""
        if isinstance(result, dict):
            raw_op = result.get("remote_operation_id") or meta.get("remote_operation_id")
            if isinstance(raw_op, str) and raw_op:
                remote_op = raw_op

        record = self.store.update_run(
            run_id,
            work_id=work_id,
            status=status,
            end_time=end,
            duration_ms=0,
            output_hash=output_hash,
            error_classification="",
            error_message="",
            artifacts=artifacts,
            evidence_references=evidence,
            result=result,
            cost=float(meta.get("cost", 0.0)),
            tokens_in=int(meta.get("tokens_in", 0)),
            tokens_out=int(meta.get("tokens_out", 0)),
            side_effect_mode=side_effect_mode,
            idempotency_key=idempotency_key,
            remote_operation_id=remote_op,
        )
        return {"record": record, "result": result}

    def _try_fallback(
        self,
        run_id: str,
        lineage: list[str],
        work_id: str,
        input: dict[str, Any],
        adapter: ToolAdapter,
        context: dict[str, Any] | None = None,
        idempotency_key: str = "",
    ) -> dict[str, Any] | None:
        context = context or {}
        for cid in adapter.fallback_chain():
            fb = self.registry.get(cid)
            if fb is None:
                continue
            meta = fb.discover()
            if not meta.get("available", True):
                continue
            errors = fb.validate_input(input)
            if errors:
                continue
            fallback_run_id = self.store.create_run(
                work_id, fb.capability_id(), meta.get("provider", ""),
                meta.get("version", "1.0"), self._hash(input),
                retry_lineage=list(lineage) + [run_id],
                project_id=context.get("project_id", ""),
                tenant_id=context.get("tenant_id") or "default",
                adapter_id=fb.capability_id(),
                capability=fb.capability_id(),
                retry_parent=run_id,
                fallback_from=adapter.capability_id(),
                idempotency_key=idempotency_key,
                side_effect_mode=fb.side_effect_mode(),
            )
            try:
                return self._finalize_success(
                    fallback_run_id, list(lineage) + [run_id],
                    work_id, fb, input, status="fallback",
                    idempotency_key=idempotency_key,
                )
            except AdapterError as exc:
                self.logger.warning(
                    "fallback adapter failed",
                    extra={"aipd_fields": {
                        "run_id": fallback_run_id, "capability": cid,
                        "classification": fb.classify_failure(exc),
                        "error": exc.message,
                    }},
                )
                continue
        return None

    def _mark_external_blocked(
        self,
        work_id: str,
        adapter: ToolAdapter,
        input: dict[str, Any],
        context: dict[str, Any],
        idempotency_key: str = "",
    ) -> ExecutionRecord:
        meta = adapter.discover()
        input_hash = self._hash(input)
        run_id = self.store.create_run(
            work_id, adapter.capability_id(), meta.get("provider", ""),
            meta.get("version", "1.0"), input_hash,
            project_id=context.get("project_id", ""),
            tenant_id=context.get("tenant_id") or "default",
            adapter_id=adapter.capability_id(),
            capability=adapter.capability_id(),
            idempotency_key=idempotency_key,
            side_effect_mode=adapter.side_effect_mode(),
        )
        # 写入外部任务包（诚实性）
        try:
            task_pkg = adapter.execute(input)
            pkg = task_pkg.get("external_task_package", "") if isinstance(task_pkg, dict) else ""
        except AdapterError as exc:
            pkg = exc.task_package or ""
        record = self.store.update_run(
            run_id,
            status="blocked_external",
            end_time=self._now(),
            duration_ms=0,
            error_classification="external_blocked",
            error_message=f"capability {adapter.capability_id()} unavailable; external task package: {pkg}",
            artifacts=[pkg] if pkg else [],
            result={"external_task_package": pkg},
        )
        return record

    # ---- 批量处理 ----
    def run_work_items(
        self,
        work_items: list[dict[str, Any]],
        capability_selector=None,
    ) -> list[dict[str, Any]]:
        """批量处理工作项。

        :param capability_selector: 从 work_item 中解析能力标识的可调用对象，
            默认读取 ``capability_floor``。
        """
        selector = capability_selector or (lambda w: w.get("capability_floor"))
        results = []
        for item in work_items:
            work_id = item.get("work_id")
            cid = selector(item)
            if not cid:
                results.append(
                    {"work_id": work_id, "ok": False, "error": "no capability_floor"}
                )
                continue
            try:
                out = self.run(work_id, cid, item.get("inputs", {}), context={"work_id": work_id})
                out["work_id"] = work_id
                out["ok"] = out["record"].status in {"succeeded", "fallback"}
                results.append(out)
            except Exception as exc:  # noqa: BLE001 - 批量处理：单条失败不影响其余，但必须记录
                self.logger.warning(
                    "work item failed",
                    extra={"aipd_fields": {
                        "work_id": work_id, "capability": cid, "error": str(exc),
                    }},
                )
                results.append({"work_id": work_id, "ok": False, "error": str(exc)})
        return results


__all__ = ["ExecutionRouter", "InputValidationError", "DEFAULT_MAX_RETRIES"]
