"""Idea Domain：Raw Idea → Structured Idea 的 canonical 对象模型。

Idea 是「尚未验证的产品构想」，经 AIPDStateDB 持久化（v5.8 Commit 9）。
最小字段集：idea_id / tenant_id / project_id / title / raw_input / goal /
problem / target_user / desired_outcome / constraints_json / source /
lifecycle_status / version_no / created_at / updated_at。

lifecycle_status ∈ {raw, structured, evidence_backed, archived}
（I0/I1/I2 映射见 idea/maturity.py；I3 只定义 contract 不实现）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Idea 生命周期状态（Commit 14 将把 lifecycle_status 映射到 IdeaMaturity）
IDEA_LIFECYCLE_RAW = "raw"
IDEA_LIFECYCLE_STRUCTURED = "structured"
IDEA_LIFECYCLE_EVIDENCE_BACKED = "evidence_backed"
IDEA_LIFECYCLE_ARCHIVED = "archived"
IDEA_LIFECYCLE_STATUSES = frozenset({
    IDEA_LIFECYCLE_RAW,
    IDEA_LIFECYCLE_STRUCTURED,
    IDEA_LIFECYCLE_EVIDENCE_BACKED,
    IDEA_LIFECYCLE_ARCHIVED,
})

# 默认约束 JSON（空对象序列化）
EMPTY_CONSTRAINTS_JSON = "{}"


@dataclass
class Idea:
    """一条 canonical Idea（tenant+project scoped，version_no 乐观锁）。"""

    idea_id: str
    tenant_id: str = "default"
    project_id: str = "default"
    title: str = ""
    raw_input: str = ""
    goal: str = ""
    problem: str = ""
    target_user: str = ""
    desired_outcome: str = ""
    constraints_json: str = EMPTY_CONSTRAINTS_JSON
    source: str = ""
    lifecycle_status: str = IDEA_LIFECYCLE_RAW
    version_no: int = 1
    created_at: str | None = None
    updated_at: str | None = None

    def __post_init__(self) -> None:
        if self.lifecycle_status not in IDEA_LIFECYCLE_STATUSES:
            raise ValueError(
                f"invalid idea lifecycle_status {self.lifecycle_status!r}; "
                f"expected one of {sorted(IDEA_LIFECYCLE_STATUSES)}")
        if self.version_no < 1:
            raise ValueError("version_no must be >= 1")

    def to_dict(self) -> dict[str, Any]:
        return {
            "idea_id": self.idea_id,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "title": self.title,
            "raw_input": self.raw_input,
            "goal": self.goal,
            "problem": self.problem,
            "target_user": self.target_user,
            "desired_outcome": self.desired_outcome,
            "constraints_json": self.constraints_json,
            "source": self.source,
            "lifecycle_status": self.lifecycle_status,
            "version_no": self.version_no,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Idea:
        return cls(
            idea_id=data["idea_id"],
            tenant_id=data.get("tenant_id", "default"),
            project_id=data.get("project_id", "default"),
            title=data.get("title", ""),
            raw_input=data.get("raw_input", ""),
            goal=data.get("goal", ""),
            problem=data.get("problem", ""),
            target_user=data.get("target_user", ""),
            desired_outcome=data.get("desired_outcome", ""),
            constraints_json=data.get("constraints_json", EMPTY_CONSTRAINTS_JSON),
            source=data.get("source", ""),
            lifecycle_status=data.get("lifecycle_status", IDEA_LIFECYCLE_RAW),
            version_no=data.get("version_no", 1),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


__all__ = [
    "Idea",
    "IDEA_LIFECYCLE_RAW",
    "IDEA_LIFECYCLE_STRUCTURED",
    "IDEA_LIFECYCLE_EVIDENCE_BACKED",
    "IDEA_LIFECYCLE_ARCHIVED",
    "IDEA_LIFECYCLE_STATUSES",
    "EMPTY_CONSTRAINTS_JSON",
]
