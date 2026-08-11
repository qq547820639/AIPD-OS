"""EvidenceGraph：Claim ↔ Evidence 可查询图（v5.8 Commit 11，SQLite 实现）。

project scoped 查询 API（全部 tenant+project 过滤）：
  - get_claim / get_claim_evidence（返回**全部** relation，含 pending/rejected）
  - get_supporting_evidence / get_contradicting_evidence / get_inconclusive_evidence
    （v5.8.1 Commit 4：只统计 ``review_status == "reviewed"`` 的 relation）
  - get_unknown_claims（epistemic_status ∈ {U, A}）
  - get_evidence_gaps（无 **reviewed** relation 的 claim —— pending 不算完成）
  - get_idea_evidence_summary（review-aware 汇总 + per-claim assessment）

不引入 Neo4j：relations 已落在 SQLite 的 claim_evidence_relations 表。
"""
from __future__ import annotations

from typing import Any

from aipd_os.state.db import AIPDStateDB

from .claim_assessment import assess
from .claim_service import ClaimNotFoundError
from .claims import Claim
from .evidence_relations import RELATION_TYPES, EvidenceRelation

# 「unknown」认知状态：无证据/未验证（Commit 7 定义的 U=Unknown；A=Assumption
# 视为初始 Candidate Claim 未验证）。
UNKNOWN_EPISTEMIC_STATUSES = frozenset({"U", "A"})

# 语义查询只统计已评审（reviewed）的关系；pending/rejected 不参与。
_REVIEWED = "reviewed"

# supports/partially_supports 视为支持（review-aware）。
_SUPPORTING_TYPES = frozenset({"supports", "partially_supports"})


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
        """返回 claim 的**全部** relations（含 pending/rejected；raw 视图）。"""
        with self._db.connect() as c:
            rows = c.execute(
                "SELECT * FROM claim_evidence_relations "
                "WHERE claim_id=? AND project_id=? AND tenant_id=? ORDER BY created_at",
                (claim_id, project_id, tenant_id)).fetchall()
        return [self._row_to_relation(r) for r in rows]

    def get_relations_by_type(self, tenant_id: str, project_id: str,
                              claim_id: str, relation_type: str,
                              review_status: str | None = None) -> list[EvidenceRelation]:
        """按关系类型（可选 review_status 过滤）查询 relations。"""
        if relation_type not in RELATION_TYPES:
            raise ValueError(f"invalid relation_type {relation_type!r}")
        sql = ("SELECT * FROM claim_evidence_relations "
               "WHERE claim_id=? AND project_id=? AND tenant_id=? AND relation_type=?")
        params: list[Any] = [claim_id, project_id, tenant_id, relation_type]
        if review_status is not None:
            sql += " AND review_status=?"
            params.append(review_status)
        sql += " ORDER BY created_at"
        with self._db.connect() as c:
            rows = c.execute(sql, params).fetchall()
        return [self._row_to_relation(r) for r in rows]

    def get_supporting_evidence(self, tenant_id: str, project_id: str,
                                claim_id: str) -> list[EvidenceRelation]:
        """只统计 reviewed 的 supports/partially_supports（Commit 4）。"""
        return (self.get_relations_by_type(tenant_id, project_id, claim_id,
                                           "supports", _REVIEWED)
                + self.get_relations_by_type(tenant_id, project_id, claim_id,
                                             "partially_supports", _REVIEWED))

    def get_contradicting_evidence(self, tenant_id: str, project_id: str,
                                   claim_id: str) -> list[EvidenceRelation]:
        """只统计 reviewed 的 contradicts（Commit 4）。"""
        return self.get_relations_by_type(tenant_id, project_id, claim_id,
                                          "contradicts", _REVIEWED)

    def get_inconclusive_evidence(self, tenant_id: str, project_id: str,
                                  claim_id: str) -> list[EvidenceRelation]:
        """只统计 reviewed 的 inconclusive（Commit 4）。"""
        return self.get_relations_by_type(tenant_id, project_id, claim_id,
                                          "inconclusive", _REVIEWED)

    # ------------------------------------------------------ aggregate views
    def get_unknown_claims(self, tenant_id: str, project_id: str) -> list[Claim]:
        """epistemic_status ∈ {U, A} 的 claims（未验证）。"""
        return [
            cl for cl in self.list_claims(tenant_id, project_id)
            if cl.epistemic_status in UNKNOWN_EPISTEMIC_STATUSES
        ]

    def get_evidence_gaps(self, tenant_id: str, project_id: str) -> list[Claim]:
        """无 **reviewed** relation 的 claims（证据空白；pending 不算完成）。"""
        gaps = []
        for cl in self.list_claims(tenant_id, project_id):
            rels = self.get_claim_evidence(tenant_id, project_id, cl.claim_id)
            if not any(r.review_status == _REVIEWED for r in rels):
                gaps.append(cl)
        return gaps

    def compute_idea_evidence(self, tenant_id: str, project_id: str,
                              idea_id: str) -> dict[str, Any]:
        """单一口径的 review-aware 计算（v5.8.1 Commit 12）。

        :class:`IdeaTruthProjection` 与 :meth:`get_idea_evidence_summary` 共用
        同一实现，避免两处语义漂移。返回 entries + counts + assessments。
        """
        claims = self.list_claims(tenant_id, project_id, idea_id=idea_id)
        supported_claims: list[dict[str, Any]] = []
        assumption: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = []
        contradicted: list[dict[str, Any]] = []
        unknown: list[dict[str, Any]] = []
        gaps: list[dict[str, Any]] = []
        pending_relations: list[dict[str, Any]] = []
        rejected_relations: list[dict[str, Any]] = []
        assessments: dict[str, dict[str, Any]] = {}
        reviewed_supporting = reviewed_contradicting = reviewed_inconclusive = 0

        for cl in claims:
            entry = {"claim_id": cl.claim_id, "claim_type": cl.claim_type,
                     "statement": cl.statement,
                     "epistemic_status": cl.epistemic_status}
            rels = self.get_claim_evidence(tenant_id, project_id, cl.claim_id)
            assessment = assess(cl, rels)
            assessments[cl.claim_id] = assessment
            reviewed = [r for r in rels if r.review_status == _REVIEWED]
            if reviewed:
                evidence.append(entry)
                if any(r.relation_type in _SUPPORTING_TYPES for r in reviewed):
                    supported_claims.append(entry)
                if any(r.relation_type == "contradicts" for r in reviewed):
                    contradicted.append(entry)
                reviewed_supporting += sum(
                    1 for r in reviewed if r.relation_type in _SUPPORTING_TYPES)
                reviewed_contradicting += sum(
                    1 for r in reviewed if r.relation_type == "contradicts")
                reviewed_inconclusive += sum(
                    1 for r in reviewed if r.relation_type == "inconclusive")
            else:
                gaps.append(entry)
            for r in rels:
                if r.review_status == "pending":
                    pending_relations.append({
                        "relation_id": r.relation_id,
                        "claim_id": cl.claim_id,
                        "evidence_id": r.evidence_id,
                        "relation_type": r.relation_type,
                    })
                elif r.review_status == "rejected":
                    rejected_relations.append({
                        "relation_id": r.relation_id,
                        "claim_id": cl.claim_id,
                        "evidence_id": r.evidence_id,
                        "relation_type": r.relation_type,
                    })
            if cl.epistemic_status == "A":
                assumption.append(entry)
            if cl.epistemic_status == "U":
                unknown.append(entry)

        not_searched = sum(
            1 for a in assessments.values()
            if a["status"] == "NOT_SEARCHED")
        return {
            "claims": claims,
            "supported_claims": supported_claims,
            "assumption": assumption,
            "evidence": evidence,
            "contradicted": contradicted,
            "unknown": unknown,
            "gaps": gaps,
            "pending_relations": pending_relations,
            "rejected_relations": rejected_relations,
            "assessments": assessments,
            "counts": {
                "total_claims": len(claims),
                "supported_claims": len(supported_claims),
                # DEPRECATED 兼容计数：只含 reviewed supports
                "known": len(supported_claims),
                "assumption": len(assumption),
                "evidence": len(evidence),
                "contradicted": len(contradicted),
                "unknown": len(unknown),
                "gaps": len(gaps),
                "evidence_gaps": len(gaps),
                "not_searched_claims": not_searched,
                "reviewed_supporting": reviewed_supporting,
                "reviewed_contradicting": reviewed_contradicting,
                "reviewed_inconclusive": reviewed_inconclusive,
                "pending_relations": len(pending_relations),
                "rejected_relations": len(rejected_relations),
            },
        }

    def get_idea_evidence_summary(self, tenant_id: str, project_id: str,
                                  idea_id: str) -> dict[str, Any]:
        """按 idea 汇总 evidence 状态（review-aware；单一口径 Commit 12）。

        v5.8.1 Commit 12：**复用 :meth:`compute_idea_evidence` 同一计数实现**
        （与 IdeaTruthProjection counts 完全一致，避免两处语义漂移）。
        """
        data = self.compute_idea_evidence(tenant_id, project_id, idea_id)
        c = data["counts"]
        return {
            "total_claims": c["total_claims"],
            # 兼容字段：supporting/contradicting = 有 reviewed relation 的 claim 数
            "supporting": c["known"],
            "contradicting": c["contradicted"],
            "inconclusive": c["reviewed_inconclusive"],
            # 兼容字段：unknown = U（未知）+ A（假设，未验证）→ 与 graph
            # UNKNOWN_EPISTEMIC_STATUSES({"U","A"}) 口径一致
            "unknown": c["unknown"] + c["assumption"],
            "gaps": c["evidence_gaps"],
            # review-aware counts（与 projection 同口径）
            "reviewed_supporting": c["reviewed_supporting"],
            "reviewed_contradicting": c["reviewed_contradicting"],
            "reviewed_inconclusive": c["reviewed_inconclusive"],
            "pending_relations": c["pending_relations"],
            "rejected_relations": c["rejected_relations"],
            "not_searched_claims": c["not_searched_claims"],
            "evidence_gaps": c["evidence_gaps"],
            "assessments": {k: v["status"]
                            for k, v in data["assessments"].items()},
        }


__all__ = ["EvidenceGraph", "UNKNOWN_EPISTEMIC_STATUSES"]
