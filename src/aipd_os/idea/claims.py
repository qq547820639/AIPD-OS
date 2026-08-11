"""Claim Domain：需要证据支持、反驳或验证的命题（v5.8 Commit 10）。

Claim 字段：claim_id / tenant_id / project_id / idea_id / claim_type /
statement / epistemic_status / lifecycle_status / confidence / source /
version_no / created_at / updated_at。

- claim_type ∈ {problem, user, behavior, mechanism, technology, product,
  market, business, safety, regulatory, engineering}；
- epistemic_status ∈ FACT_STATUSES（含 U）；**初始 Candidate Claim 通常 A
  （Assumption）或 U（Unknown），绝不默认 V（verified）**；
- idea_id 为软引用（不强外键，避免迁移复杂度）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aipd_os.state.db import FACT_STATUSES

# Claim 类型
CLAIM_TYPES = frozenset({
    "problem", "user", "behavior", "mechanism", "technology", "product",
    "market", "business", "safety", "regulatory", "engineering",
})

# 默认认知状态：Candidate Claim = Assumption（尚未验证的命题）。
# 绝不默认 V（verified）——verified 需要显式证据/工程确认。
DEFAULT_EPISTEMIC_STATUS = "A"

# Claim 生命周期
CLAIM_LIFECYCLE_ACTIVE = "active"
CLAIM_LIFECYCLE_SUPERSEDED = "superseded"
CLAIM_LIFECYCLE_ARCHIVED = "archived"
CLAIM_LIFECYCLE_STATUSES = frozenset({
    CLAIM_LIFECYCLE_ACTIVE, CLAIM_LIFECYCLE_SUPERSEDED, CLAIM_LIFECYCLE_ARCHIVED,
})


@dataclass
class Claim:
    """一条 Candidate Claim（tenant+project+idea scoped，version_no 乐观锁）。"""

    claim_id: str
    tenant_id: str = "default"
    project_id: str = "default"
    idea_id: str = ""
    claim_type: str = "problem"
    statement: str = ""
    epistemic_status: str = DEFAULT_EPISTEMIC_STATUS
    lifecycle_status: str = CLAIM_LIFECYCLE_ACTIVE
    confidence: float = 0.5
    source: str = ""
    version_no: int = 1
    created_at: str | None = None
    updated_at: str | None = None

    def __post_init__(self) -> None:
        if self.claim_type not in CLAIM_TYPES:
            raise ValueError(
                f"invalid claim_type {self.claim_type!r}; "
                f"expected one of {sorted(CLAIM_TYPES)}")
        if self.epistemic_status not in FACT_STATUSES:
            raise ValueError(
                f"invalid epistemic_status {self.epistemic_status!r}; "
                f"expected one of {sorted(FACT_STATUSES)}")
        if self.lifecycle_status not in CLAIM_LIFECYCLE_STATUSES:
            raise ValueError(
                f"invalid lifecycle_status {self.lifecycle_status!r}; "
                f"expected one of {sorted(CLAIM_LIFECYCLE_STATUSES)}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0,1]")
        if self.version_no < 1:
            raise ValueError("version_no must be >= 1")

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "idea_id": self.idea_id,
            "claim_type": self.claim_type,
            "statement": self.statement,
            "epistemic_status": self.epistemic_status,
            "lifecycle_status": self.lifecycle_status,
            "confidence": self.confidence,
            "source": self.source,
            "version_no": self.version_no,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Claim:
        return cls(
            claim_id=data["claim_id"],
            tenant_id=data.get("tenant_id", "default"),
            project_id=data.get("project_id", "default"),
            idea_id=data.get("idea_id", ""),
            claim_type=data.get("claim_type", "problem"),
            statement=data.get("statement", ""),
            epistemic_status=data.get("epistemic_status", DEFAULT_EPISTEMIC_STATUS),
            lifecycle_status=data.get("lifecycle_status", CLAIM_LIFECYCLE_ACTIVE),
            confidence=data.get("confidence", 0.5),
            source=data.get("source", ""),
            version_no=data.get("version_no", 1),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


__all__ = [
    "Claim",
    "CLAIM_TYPES",
    "DEFAULT_EPISTEMIC_STATUS",
    "CLAIM_LIFECYCLE_ACTIVE",
    "CLAIM_LIFECYCLE_SUPERSEDED",
    "CLAIM_LIFECYCLE_ARCHIVED",
    "CLAIM_LIFECYCLE_STATUSES",
]
