"""Product Truth 数据模型：记录类型、信任分级、记录与返工任务。

仅依赖标准库。记录类型与字段覆盖 fact / assumption / requirement / ctq /
evidence / decision / risk / artifact_version，以及 source / trust_level /
effective_at / expires_at 等确定性字段。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# 记录类型（truth 分类）
# v5.9：feature —— Product Definition Gate 批准后的 Feature 写入 Product Truth
# （record_type="feature"，metadata.gate_approved=True）。
TRUTH_TYPES = frozenset({
    "fact", "assumption", "requirement", "ctq", "evidence", "decision",
    "risk", "artifact_version", "feature",
})

# 确定性分级（trust_level）：越高越可信
TRUST_LEVELS = frozenset({"verified", "high", "medium", "low", "unverified"})

# truth 记录状态
TRUTH_STATUS = frozenset({"active", "stale", "expired", "blocked", "superseded"})

# 返工任务状态
REWORK_STATUS = frozenset({"pending", "running", "succeeded", "blocked"})


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_type(record_type: str) -> None:
    if record_type not in TRUTH_TYPES:
        raise ValueError(
            f"invalid truth type {record_type!r}; expected one of {sorted(TRUTH_TYPES)}")


def ensure_trust(trust_level: str) -> None:
    if trust_level not in TRUST_LEVELS:
        raise ValueError(
            f"invalid trust level {trust_level!r}; expected one of {sorted(TRUST_LEVELS)}")


@dataclass
class SourceRef:
    """来源：文件 + 段落 + 获取时间。"""
    file: Optional[str] = None
    section: Optional[str] = None
    fetched_at: Optional[str] = None
    note: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {}
        if self.file is not None:
            d["file"] = self.file
        if self.section is not None:
            d["section"] = self.section
        if self.fetched_at is not None:
            d["fetched_at"] = self.fetched_at
        if self.note is not None:
            d["note"] = self.note
        return d

    @classmethod
    def from_dict(cls, data: Any) -> SourceRef:
        if data is None:
            return cls()
        if isinstance(data, str):
            return cls(note=data)
        if isinstance(data, dict):
            return cls(
                file=data.get("file"),
                section=data.get("section"),
                fetched_at=data.get("fetched_at"),
                note=data.get("note"),
            )
        return cls()


@dataclass
class TruthRecord:
    """一条结构化 Product Truth 记录。"""
    record_type: str
    content: str
    source: Optional[SourceRef] = None
    trust_level: str = "unverified"
    effective_at: Optional[str] = None
    expires_at: Optional[str] = None
    record_id: Optional[str] = None
    version: int = 1
    status: str = "active"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        ensure_type(self.record_type)
        ensure_trust(self.trust_level)
        if self.status not in TRUTH_STATUS:
            raise ValueError(
                f"invalid truth status {self.status!r}; expected one of {sorted(TRUTH_STATUS)}")

    def is_expired(self, at: Optional[str] = None) -> bool:
        """按绝对时间判定是否过期。无 expires_at 视为永不过期。"""
        if not self.expires_at:
            return False
        ref = at or now_iso()
        try:
            e = datetime.fromisoformat(self.expires_at)
            r = datetime.fromisoformat(ref)
        except ValueError:
            return False
        return r >= e

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.record_id,
            "type": self.record_type,
            "content": self.content,
            "source": self.source.to_dict() if self.source else {},
            "trust_level": self.trust_level,
            "effective_at": self.effective_at,
            "expires_at": self.expires_at,
            "version": self.version,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }


@dataclass
class TrustAssessment:
    """可信度评估结果：缺失证据/过期时给出确定性分级并说明原因。"""
    trust_level: str
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"trust_level": self.trust_level, "reasons": list(self.reasons)}


@dataclass
class ReworkTask:
    """针对单个受影响 truth 的、有次数上限的返工任务。"""
    truth_id: str
    reason: str
    task_id: Optional[str] = None
    attempts: int = 0
    max_attempts: int = 3
    status: str = "pending"
    backoff_until: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.status not in REWORK_STATUS:
            raise ValueError(
                f"invalid rework status {self.status!r}; expected one of {sorted(REWORK_STATUS)}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "truth_id": self.truth_id,
            "reason": self.reason,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "status": self.status,
            "backoff_until": self.backoff_until,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


__all__ = [
    "TRUTH_TYPES", "TRUST_LEVELS", "TRUTH_STATUS", "REWORK_STATUS",
    "now_iso", "ensure_type", "ensure_trust", "SourceRef", "TruthRecord",
    "TrustAssessment", "ReworkTask",
]
