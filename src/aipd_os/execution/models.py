"""执行记录与结果数据模型。

:class:`ExecutionRecord` 是每一次工具执行的持久化记录；
:class:`ToolResult` 是对执行结果的规范化封装。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List

# 状态取值
STATUS_CHOICES = {
    "succeeded",
    "failed",
    "blocked_external",
    "retried",
    "fallback",
    "cancelled",
}

# 错误分类取值
ERROR_CLASSIFICATIONS = {
    "tool_error",
    "capability_missing",
    "input_invalid",
    "external_blocked",
    "decision_required",
    "policy_violation",
    "transient",
}

RETRYABLE_CLASSIFICATIONS = {"transient", "tool_error"}

# 副作用模式：决定失败后是否允许自动退避重试。
#   - PURE：无副作用，失败可安全重试（默认）；
#   - IDEMPOTENT：有副作用但自带幂等（重复执行不产生重复效果），可重试；
#   - EXTERNAL_SIDE_EFFECT：对外部系统产生副作用（发邮件/登记外部报价等），
#     重试可能重复执行 → 禁止自动重试；
#   - NON_RETRYABLE：不可重试。
SIDE_EFFECT_MODES = {"PURE", "IDEMPOTENT", "EXTERNAL_SIDE_EFFECT", "NON_RETRYABLE"}


# 可重试的错误分类：仅当错误被归为可重试时才进行退避重试
@dataclass
class ExecutionRecord:
    """一次工具执行的规范化记录。

    字段集合为固定契约，禁止随意删改；新增持久化数据请放入
    ``result`` / ``artifact`` 等扩展字段或 store 的附加列。
    """

    run_id: str
    work_id: str
    tool: str
    provider: str
    version: str
    input_hash: str
    output_hash: str
    start_time: str
    end_time: str
    duration_ms: int
    cost: float
    tokens_in: int
    tokens_out: int
    status: str
    error_classification: str
    retry_lineage: List[str] = field(default_factory=list)
    evidence_references: List[str] = field(default_factory=list)
    error_message: str = ""
    artifacts: List[str] = field(default_factory=list)
    project_id: str = ""
    tenant_id: str = "default"
    capability: str = ""
    retry_parent: str = ""
    fallback_from: str = ""
    idempotency_key: str = ""
    side_effect_mode: str = "PURE"
    remote_operation_id: str = ""

    @property
    def started_at(self) -> str:
        """与 start_time 等价的时间戳（两种命名风格兼容）。"""
        return self.start_time

    @property
    def completed_at(self) -> str:
        """与 end_time 等价的时间戳（两种命名风格兼容）。"""
        return self.end_time

    @property
    def execution_id(self) -> str:
        """执行标识（run_id 的兼容别名）。"""
        return self.run_id

    @property
    def attempt_number(self) -> int:
        """当前尝试序号：重试 lineage 长度 + 1（首次尝试为 1）。"""
        return len(self.retry_lineage) + 1

    @property
    def adapter_id(self) -> str:
        """适配器标识：优先 capability，缺省回退到 tool。"""
        return self.capability or self.tool

    @property
    def provider_version(self) -> str:
        """提供方版本（version 的别名）。"""
        return self.version

    @property
    def token_usage(self) -> Dict[str, int]:
        """token 用量（{input, output}）。"""
        return {"input": self.tokens_in, "output": self.tokens_out}

    @property
    def error_type(self) -> str:
        """错误分类（error_classification 的别名）。"""
        return self.error_classification

    @property
    def evidence_ids(self) -> List[str]:
        """证据引用（evidence_references 的别名）。"""
        return self.evidence_references

    @property
    def artifact_ids(self) -> List[str]:
        """产物路径列表（artifacts 的别名）。"""
        return self.artifacts

    def unified_record(self) -> Dict[str, Any]:
        """返回包含全部统一运行记录字段的 dict（向后追加，不删旧字段）。"""
        return {
            "run_id": self.run_id,
            "project_id": self.project_id,
            "tenant_id": self.tenant_id,
            "work_id": self.work_id,
            "adapter_id": self.adapter_id,
            "provider": self.provider,
            "provider_version": self.provider_version,
            "capability": self.capability,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "cost": self.cost,
            "token_usage": self.token_usage,
            "retry_parent": self.retry_parent,
            "fallback_from": self.fallback_from,
            "error_type": self.error_type,
            "evidence_ids": self.evidence_ids,
            "artifact_ids": self.artifact_ids,
            "idempotency_key": self.idempotency_key,
            "side_effect_mode": self.side_effect_mode,
            "remote_operation_id": self.remote_operation_id,
        }

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_db_row(cls, row: Dict[str, Any]) -> ExecutionRecord:
        import json

        def _loads(raw: Any, default: Any) -> Any:
            if raw is None:
                return default
            if isinstance(raw, list):
                return raw
            try:
                return json.loads(raw)
            except Exception:
                return default

        return cls(
            run_id=row["run_id"],
            work_id=row["work_id"],
            tool=row["tool"],
            provider=row["provider"],
            version=row["version"],
            input_hash=row["input_hash"],
            output_hash=row["output_hash"] or "",
            start_time=row["start_time"],
            end_time=row["end_time"] or "",
            duration_ms=row["duration_ms"] or 0,
            cost=float(row["cost"] or 0),
            tokens_in=int(row["tokens_in"] or 0),
            tokens_out=int(row["tokens_out"] or 0),
            status=row["status"],
            error_classification=row["error_classification"] or "",
            retry_lineage=_loads(row["retry_lineage_json"], []),
            evidence_references=_loads(row["evidence_refs_json"], []),
            error_message=row["error_message"] or "",
            artifacts=_loads(row["artifacts_json"], []),
            project_id=row.get("project_id", "") or "",
            tenant_id=row.get("tenant_id", "") or "default",
            capability=row.get("capability", "") or "",
            retry_parent=row.get("retry_parent", "") or "",
            fallback_from=row.get("fallback_from", "") or "",
            idempotency_key=row.get("idempotency_key", "") or "",
            side_effect_mode=row.get("side_effect_mode", "") or "PURE",
            remote_operation_id=row.get("remote_operation_id", "") or "",
        )


@dataclass
class ToolResult:
    """规范化后的执行结果封装。"""

    ok: bool
    data: Dict[str, Any] = field(default_factory=dict)  # 规范化输出
    artifacts: List[str] = field(default_factory=list)
    evidence_references: List[str] = field(default_factory=list)
    cost: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    error_message: str = ""
    error_classification: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


__all__ = [
    "STATUS_CHOICES",
    "ERROR_CLASSIFICATIONS",
    "RETRYABLE_CLASSIFICATIONS",
    "SIDE_EFFECT_MODES",
    "ExecutionRecord",
    "ToolResult",
]
