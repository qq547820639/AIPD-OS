"""EvidenceRelation：Claim ↔ 现有 evidence 表 的关系（v5.8 Commit 11）。

复用 canonical evidence 表（不建第二 truth source）。relation_type ∈
{supports, contradicts, partially_supports, inconclusive, not_applicable}。

**来源可信度 ≠ 关系强度**：高可信论文（source credibility 高）可能对该 claim
not_applicable；relation.strength 描述「这条证据对 claim 的支持强度」，与
evidence 的来源可信度是不同概念。

证据引用必须校验属于同 tenant+project（跨项目/跨租户 link 拒绝）。
"""
from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from aipd_os.state.db import AIPDStateDB, now_iso

# 关系类型
RELATION_TYPES = frozenset({
    "supports", "contradicts", "partially_supports", "inconclusive",
    "not_applicable",
})

# review_status
REVIEW_STATUSES = frozenset({"pending", "reviewed", "rejected"})


@dataclass
class EvidenceRelation:
    """一条 Claim↔Evidence 关系（tenant+project scoped，version_no 乐观锁）。"""

    relation_id: str
    tenant_id: str = "default"
    project_id: str = "default"
    claim_id: str = ""
    evidence_id: str = ""
    relation_type: str = "supports"
    strength: float = 0.5
    applicability: str = ""
    reasoning_summary: str = ""
    limitations: str = ""
    review_status: str = "pending"
    created_by: str = "system"
    version_no: int = 1
    created_at: str | None = None
    updated_at: str | None = None

    def __post_init__(self) -> None:
        if self.relation_type not in RELATION_TYPES:
            raise ValueError(
                f"invalid relation_type {self.relation_type!r}; "
                f"expected one of {sorted(RELATION_TYPES)}")
        if self.review_status not in REVIEW_STATUSES:
            raise ValueError(
                f"invalid review_status {self.review_status!r}; "
                f"expected one of {sorted(REVIEW_STATUSES)}")
        if not 0.0 <= self.strength <= 1.0:
            raise ValueError("strength must be in [0,1]")
        if self.version_no < 1:
            raise ValueError("version_no must be >= 1")

    def to_dict(self) -> dict[str, Any]:
        return {
            "relation_id": self.relation_id,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "claim_id": self.claim_id,
            "evidence_id": self.evidence_id,
            "relation_type": self.relation_type,
            "strength": self.strength,
            "applicability": self.applicability,
            "reasoning_summary": self.reasoning_summary,
            "limitations": self.limitations,
            "review_status": self.review_status,
            "created_by": self.created_by,
            "version_no": self.version_no,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvidenceRelation:
        return cls(
            relation_id=data["relation_id"],
            tenant_id=data.get("tenant_id", "default"),
            project_id=data.get("project_id", "default"),
            claim_id=data.get("claim_id", ""),
            evidence_id=data.get("evidence_id", ""),
            relation_type=data.get("relation_type", "supports"),
            strength=data.get("strength", 0.5),
            applicability=data.get("applicability", ""),
            reasoning_summary=data.get("reasoning_summary", ""),
            limitations=data.get("limitations", ""),
            review_status=data.get("review_status", "pending"),
            created_by=data.get("created_by", "system"),
            version_no=data.get("version_no", 1),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


class EvidenceRelationNotFoundError(KeyError):
    """在指定 scope 下找不到 relation。"""


class EvidenceRelationOptimisticLockError(Exception):
    """relation version_no 乐观锁冲突。"""


class EvidenceRelationScopeError(ValueError):
    """跨 scope 引用拒绝（claim/evidence 不属于同 tenant+project）。"""


class EvidenceRelationService:
    def __init__(self, db: AIPDStateDB) -> None:
        self._db = db

    # ------------------------------------------------------------- helpers
    def _next_id(self, prefix: str = "REL") -> str:
        with self._db.connect() as c:
            rows = c.execute("SELECT relation_id FROM claim_evidence_relations").fetchall()
        nums = []
        for r in rows:
            if isinstance(r["relation_id"], str) and r["relation_id"].startswith(prefix + "-"):
                with suppress(ValueError):
                    nums.append(int(r["relation_id"].rsplit("-", 1)[1]))
        return f"{prefix}-{max(nums, default=0) + 1:03d}"

    @staticmethod
    def _row_to_relation(row: Any) -> EvidenceRelation:
        return EvidenceRelation.from_dict(dict(row))

    def _audit(self, actor: str, action: str, rel: EvidenceRelation,
               before: Any = None) -> None:
        self._db.add_audit(actor, action, rel.project_id, rel.tenant_id,
                           before=before, after=rel.to_dict())

    def _ensure_claim_in_scope(self, tenant_id: str, project_id: str, claim_id: str) -> None:
        with self._db.connect() as c:
            row = c.execute(
                "SELECT 1 FROM claims WHERE claim_id=? AND project_id=? AND tenant_id=?",
                (claim_id, project_id, tenant_id)).fetchone()
        if row is None:
            raise EvidenceRelationScopeError(
                f"claim {claim_id!r} does not exist in tenant {tenant_id!r}/"
                f"project {project_id!r}")

    def _ensure_evidence_in_scope(self, tenant_id: str, project_id: str,
                                  evidence_id: str) -> None:
        """证据必须属于同 tenant+project（跨项目/跨租户 link 拒绝）。"""
        with self._db.connect() as c:
            row = c.execute(
                "SELECT 1 FROM evidence WHERE evidence_id=? AND project_id=? AND tenant_id=?",
                (evidence_id, project_id, tenant_id)).fetchone()
        if row is None:
            raise EvidenceRelationScopeError(
                f"evidence {evidence_id!r} does not exist in tenant {tenant_id!r}/"
                f"project {project_id!r} (cross-scope evidence link rejected)")

    # --------------------------------------------------------------- CRUD
    def add(self, rel: EvidenceRelation, actor: str = "system") -> EvidenceRelation:
        """创建 Claim↔Evidence 关系（校验 claim/evidence 同 scope）。"""
        self._ensure_claim_in_scope(rel.tenant_id, rel.project_id, rel.claim_id)
        self._ensure_evidence_in_scope(rel.tenant_id, rel.project_id, rel.evidence_id)
        if rel.relation_id in ("", None):
            rel = EvidenceRelation(
                relation_id=self._next_id(), tenant_id=rel.tenant_id,
                project_id=rel.project_id, claim_id=rel.claim_id,
                evidence_id=rel.evidence_id, relation_type=rel.relation_type,
                strength=rel.strength, applicability=rel.applicability,
                reasoning_summary=rel.reasoning_summary,
                limitations=rel.limitations, review_status=rel.review_status,
                created_by=actor, version_no=rel.version_no,
                created_at=rel.created_at, updated_at=rel.updated_at)
        ts = now_iso()
        with self._db.connect() as c:
            c.execute(
                "INSERT OR REPLACE INTO claim_evidence_relations("
                "relation_id,project_id,tenant_id,claim_id,evidence_id,relation_type,"
                "strength,applicability,reasoning_summary,limitations,review_status,"
                "created_by,version_no,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (rel.relation_id, rel.project_id, rel.tenant_id, rel.claim_id,
                 rel.evidence_id, rel.relation_type, rel.strength, rel.applicability,
                 rel.reasoning_summary, rel.limitations, rel.review_status,
                 actor, rel.version_no, ts, ts))
        created = EvidenceRelation(
            relation_id=rel.relation_id, tenant_id=rel.tenant_id,
            project_id=rel.project_id, claim_id=rel.claim_id,
            evidence_id=rel.evidence_id, relation_type=rel.relation_type,
            strength=rel.strength, applicability=rel.applicability,
            reasoning_summary=rel.reasoning_summary, limitations=rel.limitations,
            review_status=rel.review_status, created_by=actor,
            version_no=rel.version_no, created_at=ts, updated_at=ts)
        self._audit(actor, "evidence_relation.add", created)
        return created

    def get(self, tenant_id: str, project_id: str, relation_id: str) -> EvidenceRelation:
        with self._db.connect() as c:
            row = c.execute(
                "SELECT * FROM claim_evidence_relations "
                "WHERE relation_id=? AND project_id=? AND tenant_id=?",
                (relation_id, project_id, tenant_id)).fetchone()
        if row is None:
            raise EvidenceRelationNotFoundError(relation_id)
        return self._row_to_relation(row)

    def list_for_claim(self, tenant_id: str, project_id: str,
                       claim_id: str) -> list[EvidenceRelation]:
        with self._db.connect() as c:
            rows = c.execute(
                "SELECT * FROM claim_evidence_relations "
                "WHERE claim_id=? AND project_id=? AND tenant_id=? ORDER BY created_at",
                (claim_id, project_id, tenant_id)).fetchall()
        return [self._row_to_relation(r) for r in rows]

    def update(self, tenant_id: str, project_id: str, relation_id: str,
               expected_version: int, actor: str = "system",
               **fields: Any) -> EvidenceRelation:
        allow = {"relation_type", "strength", "applicability", "reasoning_summary",
                 "limitations", "review_status"}
        if not fields:
            raise ValueError("no editable fields provided")
        bad = set(fields) - allow
        if bad:
            raise ValueError(f"not editable fields: {sorted(bad)}")
        if "relation_type" in fields and fields["relation_type"] not in RELATION_TYPES:
            raise ValueError(f"invalid relation_type {fields['relation_type']!r}")
        if "review_status" in fields and fields["review_status"] not in REVIEW_STATUSES:
            raise ValueError(f"invalid review_status {fields['review_status']!r}")
        if "strength" in fields and not 0.0 <= fields["strength"] <= 1.0:
            raise ValueError("strength must be in [0,1]")
        before = self.get(tenant_id, project_id, relation_id)
        set_cols = sorted(fields)
        set_sql = ", ".join([f"{col}=?" for col in set_cols]
                              + ["updated_at=?", "version_no=version_no+1"])
        params = [fields[k] for k in set_cols] + [now_iso()]
        with self._db.connect() as c:
            cur = c.execute(
                f"UPDATE claim_evidence_relations SET {set_sql} "
                "WHERE relation_id=? AND project_id=? AND tenant_id=? AND version_no=?",
                params + [relation_id, project_id, tenant_id, expected_version])
            if cur.rowcount != 1:
                raise EvidenceRelationOptimisticLockError(
                    f"relation {relation_id} optimistic-lock conflict (version mismatch)")
        after = self.get(tenant_id, project_id, relation_id)
        self._audit(actor, "evidence_relation.update", after, before=before.to_dict())
        return after


__all__ = [
    "EvidenceRelation",
    "RELATION_TYPES",
    "REVIEW_STATUSES",
    "EvidenceRelationService",
    "EvidenceRelationNotFoundError",
    "EvidenceRelationOptimisticLockError",
    "EvidenceRelationScopeError",
]
