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


# 可重试的错误分类：仅当错误被归为可重试时才进行退避重试
@dataclass
class ExecutionRecord:
    """一次工具执行的规范化记录。

    字段集合为固定契约，禁止随意增删；新增持久化数据请放入
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

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_db_row(cls, row: Dict[str, Any]) -> "ExecutionRecord":
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
    "ExecutionRecord",
    "ToolResult",
]
