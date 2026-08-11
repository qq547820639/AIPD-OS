"""Idea Domain：Raw Idea → Structured Idea 的 canonical 对象模型。

Idea 是「尚未验证的产品构想」，经 AIPDStateDB 持久化（v5.8 Commit 9）。
最小字段集：idea_id / tenant_id / project_id / title / raw_input / goal /
problem / target_user / desired_outcome / constraints_json / source /
lifecycle_status / version_no / created_at / updated_at。

v5.8.1 Commit 3：**lifecycle_status 与成熟度（IdeaMaturity）分离**。
lifecycle_status 只表达**对象生命状态** ∈ {active, archived, superseded}；
I0/I1/I2/I3 成熟度是 derived projection（IdeaMaturity.evaluate 只读 graph），
不再从 lifecycle 推导。旧值 raw/structured/evidence_backed（v5.8）读取时
compatibility mapping → active；写入永远用新枚举。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .serializers import parse_constraints

# Idea 对象生命状态（v5.8.1 Commit 3；不再与成熟度 I0-I3 混用）
IDEA_LIFECYCLE_ACTIVE = "active"
IDEA_LIFECYCLE_ARCHIVED = "archived"
IDEA_LIFECYCLE_SUPERSEDED = "superseded"
IDEA_LIFECYCLE_STATUSES = frozenset({
    IDEA_LIFECYCLE_ACTIVE,
    IDEA_LIFECYCLE_ARCHIVED,
    IDEA_LIFECYCLE_SUPERSEDED,
})

# 旧值 compatibility mapping（v5.8 的 lifecycle 语义 → 新对象生命状态）。
# 成熟度不再由 lifecycle 携带（raw/structured/evidence_backed 全部 → active，
# 具体成熟度由 IdeaMaturity.evaluate 按 graph 判定）。
_LEGACY_LIFECYCLE_TO_ACTIVE = frozenset({
    "raw", "structured", "evidence_backed",
})

# 默认约束 JSON（空对象序列化）
EMPTY_CONSTRAINTS_JSON = "{}"


@dataclass
class Idea:
    """一条 canonical Idea（tenant+project scoped，version_no 乐观锁）。

    lifecycle_status ∈ {active, archived, superseded}（对象生命状态）；
    成熟度 I0/I1/I2/I3 由 IdeaMaturity.evaluate 派生，不存于此字段。
    """

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
    lifecycle_status: str = IDEA_LIFECYCLE_ACTIVE
    version_no: int = 1
    created_at: str | None = None
    updated_at: str | None = None

    def __post_init__(self) -> None:
        # 旧值（raw/structured/evidence_backed）compatibility → active
        if self.lifecycle_status in _LEGACY_LIFECYCLE_TO_ACTIVE:
            self.lifecycle_status = IDEA_LIFECYCLE_ACTIVE
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
            lifecycle_status=data.get("lifecycle_status", IDEA_LIFECYCLE_ACTIVE),
            version_no=data.get("version_no", 1),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )

    @property
    def constraints(self) -> list[str]:
        """解析后的约束列表（经 serializer；兼容旧 repr 遗留数据）。"""
        return parse_constraints(self.constraints_json)


__all__ = [
    "Idea",
    "IDEA_LIFECYCLE_ACTIVE",
    "IDEA_LIFECYCLE_ARCHIVED",
    "IDEA_LIFECYCLE_SUPERSEDED",
    "IDEA_LIFECYCLE_STATUSES",
    "EMPTY_CONSTRAINTS_JSON",
]
