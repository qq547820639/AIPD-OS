"""EvidenceRelation：Claim ↔ 现有 evidence 表 的关系（v5.8 Commit 11）。

复用 canonical evidence 表（不建第二 truth source）。relation_type ∈
{supports, contradicts, partially_supports, inconclusive, not_applicable}。

**来源可信度 ≠ 关系强度**：高可信论文（source credibility 高）可能对该 claim
not_applicable；relation.strength 描述「这条证据对 claim 的支持强度」，与
evidence 的来源可信度是不同概念。

证据引用必须校验属于同 tenant+project（跨项目/跨租户 link 拒绝）。
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from aipd_os.state.db import AIPDStateDB, now_iso
from aipd_os.state.lineage import LineageNodeRef, LineageService

# 关系类型
RELATION_TYPES = frozenset({
    "supports", "contradicts", "partially_supports", "inconclusive",
    "not_applicable",
})

# review_status
REVIEW_STATUSES = frozenset({"pending", "reviewed", "rejected"})

# 旧 DB 中「无评价」的 legacy 哨兵值（v5.8 默认 0.5 = 伪精确，Commit 3 起
# 模型默认 None；读取时 0.5 视为 legacy_unscored 而非真实测量）。
LEGACY_UNSCORED_SENTINEL = 0.5

# Claim↔Evidence lineage 关系映射（v5.8.2 Commit 5 修正）：
# **只有 review_status=reviewed 才建立语义边**：
#   supports/partially_supports → supported_by；contradicts → contradicted_by；
#   inconclusive/not_applicable 不建边（无法表达支持/反驳语义）；
#   pending/rejected 一律不建语义边（pending=未确认，rejected=已否决）。
# 语义边集合（用于 retire 旧边时精确匹配）。
_SEMANTIC_LINEAGE_TYPES = frozenset({"supported_by", "contradicted_by"})

# relation_type → 对应语义 lineage 类型（仅 reviewed 生效）
_RELATION_TO_LINEAGE = {
    "supports": "supported_by",
    "partially_supports": "supported_by",
    "contradicts": "contradicted_by",
}


def _legacy_unscored(value: Any) -> bool:
    """判断 DB 读取值是否为 legacy 未评分哨兵（0.5）。"""
    return isinstance(value, (int, float)) and float(value) == LEGACY_UNSCORED_SENTINEL


@dataclass
class EvidenceRelation:
    """一条 Claim↔Evidence 关系（tenant+project scoped，version_no 乐观锁）。

    strength: Optional[float] —— **只有显式评分才填**（None=未评分）。
    不把不知道的装成知道：无评价时不默认 50%。旧 DB 的 0.5 读取时按
    legacy_unscored 处理为 None（不假设旧 0.5 是真实测量）。
    """

    relation_id: str
    tenant_id: str = "default"
    project_id: str = "default"
    claim_id: str = ""
    evidence_id: str = ""
    relation_type: str = "supports"
    strength: float | None = None
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
        if self.strength is not None and not 0.0 <= self.strength <= 1.0:
            raise ValueError("strength must be in [0,1] or None (unscored)")
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
        strength = data.get("strength")
        if _legacy_unscored(strength):
            # 旧 DB 的 0.5 = legacy_unscored 哨兵 → None（不假设是真实测量）
            strength = None
        return cls(
            relation_id=data["relation_id"],
            tenant_id=data.get("tenant_id", "default"),
            project_id=data.get("project_id", "default"),
            claim_id=data.get("claim_id", ""),
            evidence_id=data.get("evidence_id", ""),
            relation_type=data.get("relation_type", "supports"),
            strength=strength,
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


class EvidenceRelationConflictError(Exception):
    """同 (claim_id, evidence_id, relation_type, scope) 关系已存在（Commit 7）。

    由 :meth:`EvidenceRelationService.add` 在唯一键冲突时抛出；幂等语义请用
    :meth:`EvidenceRelationService.get_or_create`。
    """


class EvidenceRelationService:
    def __init__(self, db: AIPDStateDB) -> None:
        self._db = db

    # ------------------------------------------------------------- helpers
    def _next_id(self, prefix: str = "REL") -> str:
        """并发安全 ID：基于 id_sequences 表原子分配（v5.8.1 Commit 7）。"""
        return self._db.next_sequence("relation", prefix)

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
        """创建 Claim↔Evidence 关系（校验 claim/evidence 同 scope）。

        v5.8.1 Commit 7：不再 ``INSERT OR REPLACE`` —— 重复 (claim_id,
        evidence_id, relation_type) 唯一键冲突时抛
        :class:`EvidenceRelationConflictError`（不删除旧行、不重置
        created_at/version_no）。幂等语义请用 :meth:`get_or_create`。
        """
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
        try:
            with self._db.connect() as c:
                c.execute(
                    "INSERT INTO claim_evidence_relations("
                    "relation_id,project_id,tenant_id,claim_id,evidence_id,relation_type,"
                    "strength,applicability,reasoning_summary,limitations,review_status,"
                    "created_by,version_no,created_at,updated_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (rel.relation_id, rel.project_id, rel.tenant_id, rel.claim_id,
                     rel.evidence_id, rel.relation_type,
                     # strength=None（未评分）→ DB 存 legacy 哨兵 0.5（NOT NULL）；
                     # 模型层读取时再映射回 None（legacy_unscored）。
                     rel.strength if rel.strength is not None
                     else LEGACY_UNSCORED_SENTINEL,
                     rel.applicability, rel.reasoning_summary, rel.limitations,
                     rel.review_status, actor, rel.version_no, ts, ts))
        except sqlite3.IntegrityError as exc:
            raise EvidenceRelationConflictError(
                f"relation already exists for claim {rel.claim_id!r} / "
                f"evidence {rel.evidence_id!r} / type {rel.relation_type!r} "
                f"in tenant {rel.tenant_id!r}/project {rel.project_id!r} "
                "(use get_or_create for idempotent semantics)") from exc
        created = EvidenceRelation(
            relation_id=rel.relation_id, tenant_id=rel.tenant_id,
            project_id=rel.project_id, claim_id=rel.claim_id,
            evidence_id=rel.evidence_id, relation_type=rel.relation_type,
            strength=rel.strength, applicability=rel.applicability,
            reasoning_summary=rel.reasoning_summary, limitations=rel.limitations,
            review_status=rel.review_status, created_by=actor,
            version_no=rel.version_no, created_at=ts, updated_at=ts)
        self._audit(actor, "evidence_relation.add", created)
        # v5.8.2 Commit 5：只有 reviewed relation 才建语义 lineage 边；
        # pending/rejected 不写 supported_by/contradicted_by（不把未确认当已确认）。
        self._sync_lineage(rel, actor)
        return created

    def _sync_lineage(self, rel: EvidenceRelation, actor: str) -> None:
        """按 relation 的 (review_status, relation_type) 同步语义 lineage 边。

        规则（v5.8.2 Commit 5，R-08/R-09）：
        - ``reviewed`` + supports/partially_supports → ``supported_by`` 边；
        - ``reviewed`` + contradicts → ``contradicted_by`` 边；
        - ``reviewed`` + inconclusive/not_applicable → 不建语义边
          （现有语义边 retire）；
        - ``pending`` / ``rejected`` → 不建语义边（现有语义边 retire）。

        失效走 :meth:`LineageService.retire_edge`（soft-retire，不物理删除，
        历史保留在 dependencies 行 + audit_log）；语义变化（如
        supports→contradicts）先 retire 旧边再建新边。
        """
        expected_type = _RELATION_TO_LINEAGE.get(rel.relation_type) \
            if rel.review_status == "reviewed" else None
        lineage = LineageService(self._db)
        claim_node = LineageNodeRef(
            node_type="claim", node_id=rel.claim_id,
            tenant_id=rel.tenant_id, project_id=rel.project_id)
        ev_node = LineageNodeRef(
            node_type="evidence", node_id=rel.evidence_id,
            tenant_id=rel.tenant_id, project_id=rel.project_id)
        # 现有语义边：精确归属本 relation（provenance.relation_id 匹配）。
        # 同一 (claim, evidence) 可并存 supports+contradicts（MIXED 合法），
        # 因此不能按 (claim, evidence) 笼统匹配，否则会误 retire 另一条
        # relation 的边。v5.8.1 老边无 relation_id（无法归属）→ 不 retire、
        # 不重建（add_edge 幂等兜底）。
        existing = [
            e for e in lineage.outgoing(claim_node, include_retired=True)
            if e.target.node_type == "evidence"
            and e.target.node_id == rel.evidence_id
            and e.relation_type in _SEMANTIC_LINEAGE_TYPES
            and e.provenance.get("relation_id") == rel.relation_id
        ]
        for edge in existing:
            if edge.retired:
                continue  # 已失效，无需再处理
            if edge.relation_type != expected_type:
                lineage.retire_edge(
                    edge.edge_id, actor=actor,
                    reason=f"evidence_relation {rel.relation_id} review changed "
                           f"({rel.review_status}/{rel.relation_type})")
        if expected_type is None:
            return
        if not any((not e.retired) and e.relation_type == expected_type
                   for e in existing):
            lineage.add_edge(
                claim_node, ev_node, expected_type,
                provenance={"source": "evidence_relation",
                            "relation_type": rel.relation_type,
                            "relation_id": rel.relation_id},
                actor=actor)

    def get_or_create(self, rel: EvidenceRelation,
                      actor: str = "system") -> tuple[EvidenceRelation, bool]:
        """幂等创建：同 (claim_id, evidence_id, relation_type, scope) 已存在 →
        返回 (现有 relation, False)；否则创建 → (新 relation, True)。

        v5.8.1 Commit 7：供可能重复的调用方（如 research link）使用，避免误抛
        :class:`EvidenceRelationConflictError`。
        """
        self._ensure_claim_in_scope(rel.tenant_id, rel.project_id, rel.claim_id)
        self._ensure_evidence_in_scope(rel.tenant_id, rel.project_id, rel.evidence_id)
        with self._db.connect() as c:
            row = c.execute(
                "SELECT * FROM claim_evidence_relations "
                "WHERE claim_id=? AND evidence_id=? AND relation_type=? "
                "AND project_id=? AND tenant_id=?",
                (rel.claim_id, rel.evidence_id, rel.relation_type,
                 rel.project_id, rel.tenant_id)).fetchone()
        if row is not None:
            return self._row_to_relation(row), False
        return self.add(rel, actor=actor), True

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
        if "strength" in fields and fields["strength"] is not None \
                and not 0.0 <= fields["strength"] <= 1.0:
            raise ValueError("strength must be in [0,1] or None (unscored)")
        before = self.get(tenant_id, project_id, relation_id)
        set_cols = sorted(fields)
        # strength=None（未评分）→ DB 存 legacy 哨兵 0.5（NOT NULL）
        params: list[Any] = []
        for k in set_cols:
            v = fields[k]
            if k == "strength" and v is None:
                v = LEGACY_UNSCORED_SENTINEL
            params.append(v)
        set_sql = ", ".join([f"{col}=?" for col in set_cols]
                              + ["updated_at=?", "version_no=version_no+1"])
        params = params + [now_iso()]
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
        # v5.8.2 Commit 5：relation_type / review_status 变化时同步语义 lineage
        # （reviewed→建边；pending/rejected→retire 旧边；类型变化→retire+重建）。
        if "relation_type" in fields or "review_status" in fields:
            self._sync_lineage(after, actor)
        return after

    def review(self, tenant_id: str, project_id: str, relation_id: str,
               review_status: str, actor: str = "system",
               expected_version: int | None = None) -> EvidenceRelation:
        """显式评审 relation（reviewed / rejected），Commit 4 review semantics。

        - 只允许 ``reviewed`` / ``rejected``（把 pending 置回 pending 无意义，
          用 :meth:`update` 即可）；
        - ``expected_version`` 缺省时自动读取当前版本（便捷路径；并发敏感场景
          应显式传版本号以利用乐观锁）；
        - audit（action=evidence_relation.review）。
        """
        if review_status not in REVIEW_STATUSES:
            raise ValueError(
                f"invalid review_status {review_status!r}; "
                f"expected one of {sorted(REVIEW_STATUSES)}")
        if review_status == "pending":
            raise ValueError(
                "review() 只接受 reviewed/rejected；重置为 pending 请用 update()")
        if expected_version is None:
            expected_version = self.get(tenant_id, project_id, relation_id).version_no
        before = self.get(tenant_id, project_id, relation_id)
        updated = self.update(tenant_id, project_id, relation_id,
                              expected_version=expected_version, actor=actor,
                              review_status=review_status)
        self._db.add_audit(actor, "evidence_relation.review", project_id, tenant_id,
                           before=before.to_dict(), after=updated.to_dict())
        return updated


__all__ = [
    "EvidenceRelation",
    "RELATION_TYPES",
    "REVIEW_STATUSES",
    "LEGACY_UNSCORED_SENTINEL",
    "EvidenceRelationService",
    "EvidenceRelationNotFoundError",
    "EvidenceRelationOptimisticLockError",
    "EvidenceRelationScopeError",
    "EvidenceRelationConflictError",
]
