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
from typing import Any, Dict, List, Optional

from aipd_os.execution.adapter import AdapterError, ToolAdapter
from aipd_os.execution.models import (
    ERROR_CLASSIFICATIONS,
    RETRYABLE_CLASSIFICATIONS,
    ExecutionRecord,
    ToolResult,
)
from aipd_os.execution.registry import AdapterRegistry
from aipd_os.execution.runs import RunStore, canonical_hash

DEFAULT_MAX_RETRIES = 3
BACKOFF_BASE_S = 0.05


class InputValidationError(Exception):
    """输入校验失败。"""

    def __init__(self, capability_id: str, errors: List[str]) -> None:
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
        logger: Optional[logging.Logger] = None,
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
        input: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
        project_id: str = "",
    ) -> Dict[str, Any]:
        """执行一次路由，返回 ``{'record': ExecutionRecord, 'result': dict|None}``。

        输入非法时抛出 :class:`InputValidationError`。
        """
        adapter = self.registry.get(capability_id)
        if adapter is None:
            raise KeyError(f"no adapter for capability: {capability_id}")

        context = context or {}
        project_id = project_id or context.get("project_id", "")
        context["project_id"] = project_id

        # 1) 能力可用性
        meta = adapter.discover()
        if not meta.get("available", True):
            record = self._mark_external_blocked(work_id, adapter, input, context)
            return {"record": record, "result": None}

        # 2) 输入校验
        errors = adapter.validate_input(input)
        if errors:
            raise InputValidationError(capability_id, errors)

        input_hash = self._hash(input)
        run_id = self.store.create_run(
            work_id, adapter.capability_id(), meta.get("provider", ""),
            meta.get("version", "1.0"), input_hash,
            project_id=project_id,
            adapter_id=adapter.capability_id(),
            capability=adapter.capability_id(),
        )
        lineage: List[str] = []

        max_attempts = max(1, min(adapter.retry_limits(), self.max_retries))
        attempt = 0
        last_class = "tool_error"
        last_msg = ""
        while attempt < max_attempts:
            attempt += 1
            try:
                return self._finalize_success(
                    run_id, lineage, work_id, adapter, input, status="succeeded"
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
                    }},
                )
                if self._retryable(last_class) and attempt < max_attempts:
                    prev = run_id
                    run_id = self.store.record_retry(prev)
                    lineage = list(self.store.get_run(run_id).retry_lineage)
                    time.sleep(BACKOFF_BASE_S * (2 ** (attempt - 1)))
                    continue
                # 不可重试或已用尽尝试次数 -> 进入降级
                break

        # 3) 降级链
        fallback_result = self._try_fallback(
            run_id, lineage, work_id, input, adapter, context
        )
        if fallback_result is not None:
            return fallback_result

        # 4) 最终失败
        record = self.store.update_run(
            run_id,
            status="failed",
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

    def _finalize_success(
        self,
        run_id: str,
        lineage: List[str],
        work_id: str,
        adapter: ToolAdapter,
        input: Dict[str, Any],
        status: str,
    ) -> Dict[str, Any]:
        raw = adapter.execute(input)
        result = adapter.normalize(raw)
        meta = result.pop("_meta", {}) if isinstance(result, dict) else {}
        artifacts = adapter.collect_artifacts(raw)
        evidence = adapter.persist_evidence(raw, run_id)
        output_hash = self._hash(result)
        end = self._now()
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
        )
        return {"record": record, "result": result}

    def _try_fallback(
        self,
        run_id: str,
        lineage: List[str],
        work_id: str,
        input: Dict[str, Any],
        adapter: ToolAdapter,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
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
                adapter_id=fb.capability_id(),
                capability=fb.capability_id(),
                retry_parent=run_id,
                fallback_from=adapter.capability_id(),
            )
            try:
                return self._finalize_success(
                    fallback_run_id, list(lineage) + [run_id],
                    work_id, fb, input, status="fallback",
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
        input: Dict[str, Any],
        context: Dict[str, Any],
    ) -> ExecutionRecord:
        meta = adapter.discover()
        input_hash = self._hash(input)
        run_id = self.store.create_run(
            work_id, adapter.capability_id(), meta.get("provider", ""),
            meta.get("version", "1.0"), input_hash,
            project_id=context.get("project_id", ""),
            adapter_id=adapter.capability_id(),
            capability=adapter.capability_id(),
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
        work_items: List[Dict[str, Any]],
        capability_selector=None,
    ) -> List[Dict[str, Any]]:
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
            except Exception as exc:  # noqa: BLE001
                results.append({"work_id": work_id, "ok": False, "error": str(exc)})
        return results


__all__ = ["ExecutionRouter", "InputValidationError", "DEFAULT_MAX_RETRIES"]
