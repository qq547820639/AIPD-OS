"""EvidenceGraph：Claim ↔ Evidence 可查询图（v5.8 Commit 11，SQLite 实现）。

project scoped 查询 API（全部 tenant+project 过滤）：
  - get_claim / get_claim_evidence
  - get_supporting_evidence / get_contradicting_evidence / get_inconclusive_evidence
  - get_unknown_claims（epistemic_status ∈ {U, A}）
  - get_evidence_gaps（无任何 relation 的 claim）
  - get_idea_evidence_summary（{total_claims, supporting, contradicting,
    inconclusive, unknown, gaps}）

不引入 Neo4j：relations 已落在 SQLite 的 claim_evidence_relations 表。
"""
from __future__ import annotations

from typing import Any

from aipd_os.state.db import AIPDStateDB

from .claim_service import ClaimNotFoundError
from .claims import Claim
from .evidence_relations import RELATION_TYPES, EvidenceRelation

# 「unknown」认知状态：无证据/未验证（Commit 7 定义的 U=Unknown；A=Assumption
# 视为初始 Candidate Claim 未验证）。
UNKNOWN_EPISTEMIC_STATUSES = frozenset({"U", "A"})


class EvidenceGraph:
    def __init__(self, db: AIPDStateDB) -> None:
        self._db = db

    @staticmethod
    def _row_to_relation(row: Any) -> EvidenceRelation:
        return EvidenceRelation.from_dict(dict(row))

    # ------------------------------------------------------------ claims
    def get_claim(self, tenant_id: str, project_id: str, claim_id: str) -> Claim:
        with self._db.connect() as c:
            row = c.execute(
                "SELECT * FROM claims WHERE claim_id=? AND project_id=? AND tenant_id=?",
                (claim_id, project_id, tenant_id)).fetchone()
        if row is None:
            raise ClaimNotFoundError(claim_id)
        return Claim.from_dict(dict(row))

    def list_claims(self, tenant_id: str, project_id: str,
                    idea_id: str | None = None) -> list[Claim]:
        sql = "SELECT * FROM claims WHERE project_id=? AND tenant_id=?"
        params: list[Any] = [project_id, tenant_id]
        if idea_id is not None:
            sql += " AND idea_id=?"
            params.append(idea_id)
        sql += " ORDER BY created_at"
        with self._db.connect() as c:
            rows = c.execute(sql, params).fetchall()
        return [Claim.from_dict(dict(r)) for r in rows]

    # ---------------------------------------------------------- relations
    def get_claim_evidence(self, tenant_id: str, project_id: str,
                           claim_id: str) -> list[EvidenceRelation]:
        with self._db.connect() as c:
            rows = c.execute(
                "SELECT * FROM claim_evidence_relations "
                "WHERE claim_id=? AND project_id=? AND tenant_id=? ORDER BY created_at",
                (claim_id, project_id, tenant_id)).fetchall()
        return [self._row_to_relation(r) for r in rows]

    def get_relations_by_type(self, tenant_id: str, project_id: str,
                              claim_id: str, relation_type: str) -> list[EvidenceRelation]:
        if relation_type not in RELATION_TYPES:
            raise ValueError(f"invalid relation_type {relation_type!r}")
        with self._db.connect() as c:
            rows = c.execute(
                "SELECT * FROM claim_evidence_relations "
                "WHERE claim_id=? AND project_id=? AND tenant_id=? AND relation_type=? "
                "ORDER BY created_at",
                (claim_id, project_id, tenant_id, relation_type)).fetchall()
        return [self._row_to_relation(r) for r in rows]

    def get_supporting_evidence(self, tenant_id: str, project_id: str,
                                claim_id: str) -> list[EvidenceRelation]:
        return (self.get_relations_by_type(tenant_id, project_id, claim_id, "supports")
                + self.get_relations_by_type(tenant_id, project_id, claim_id,
                                             "partially_supports"))

    def get_contradicting_evidence(self, tenant_id: str, project_id: str,
                                   claim_id: str) -> list[EvidenceRelation]:
        return self.get_relations_by_type(tenant_id, project_id, claim_id, "contradicts")

    def get_inconclusive_evidence(self, tenant_id: str, project_id: str,
                                  claim_id: str) -> list[EvidenceRelation]:
        return self.get_relations_by_type(tenant_id, project_id, claim_id, "inconclusive")

    # ------------------------------------------------------ aggregate views
    def get_unknown_claims(self, tenant_id: str, project_id: str) -> list[Claim]:
        """epistemic_status ∈ {U, A} 的 claims（未验证）。"""
        return [
            cl for cl in self.list_claims(tenant_id, project_id)
            if cl.epistemic_status in UNKNOWN_EPISTEMIC_STATUSES
        ]

    def get_evidence_gaps(self, tenant_id: str, project_id: str) -> list[Claim]:
        """无任何 relation 的 claims（证据空白）。"""
        gaps = []
        for cl in self.list_claims(tenant_id, project_id):
            if not self.get_claim_evidence(tenant_id, project_id, cl.claim_id):
                gaps.append(cl)
        return gaps

    def get_idea_evidence_summary(self, tenant_id: str, project_id: str,
                                  idea_id: str) -> dict[str, Any]:
        """按 idea 汇总 evidence 状态。"""
        claims = self.list_claims(tenant_id, project_id, idea_id=idea_id)
        supporting = contradicting = inconclusive = unknown = gaps = 0
        for cl in claims:
            rels = self.get_claim_evidence(tenant_id, project_id, cl.claim_id)
            if cl.epistemic_status in UNKNOWN_EPISTEMIC_STATUSES:
                unknown += 1
            if not rels:
                gaps += 1
            for rel in rels:
                if rel.relation_type in ("supports", "partially_supports"):
                    supporting += 1
                elif rel.relation_type == "contradicts":
                    contradicting += 1
                elif rel.relation_type == "inconclusive":
                    inconclusive += 1
        return {
            "total_claims": len(claims),
            "supporting": supporting,
            "contradicting": contradicting,
            "inconclusive": inconclusive,
            "unknown": unknown,
            "gaps": gaps,
        }


__all__ = ["EvidenceGraph", "UNKNOWN_EPISTEMIC_STATUSES"]
