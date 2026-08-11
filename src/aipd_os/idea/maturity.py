"""Idea Maturity（v5.8 Commit 14 / v5.8.1 Commit 3-4）。

生命周期与成熟度分离（Commit 3）：``Idea.lifecycle_status`` 只表达对象生命
状态（active/archived/superseded）；**成熟度是 derived projection**——
:meth:`IdeaMaturity.evaluate` 只读 graph，不再从 lifecycle 推导。

保守 I2（Commit 4）——确定性规则：
  - I0_RAW_IDEA             —— 无 claims；
  - I1_STRUCTURED_IDEA      —— 有 claims，但 key claims 未完成 Evidence
    Search / 评审（或该 Idea 无任何 reviewed evidence）；
  - I2_EVIDENCE_BACKED_IDEA —— 全部满足：
    (a) 有 claims；
    (b) 所有 KEY_CLAIM_TYPES 的 key claims 都执行过 Evidence Search
        （有 reviewed relation —— pending/rejected 不算完成）；
    (c) 每个 key claim 都有明确评估（ClaimAssessment 非 NOT_SEARCHED）；
    (d) 无 fake/simulated evidence（relation.evidence_id 必须真实存在于
        canonical evidence 表 —— EvidenceRelationService 已强制校验）。
  - I3_PRODUCT_OPPORTUNITY  —— 只定义 contract，本轮不实现。

``KEY_CLAIM_TYPES``：{problem, user, mechanism, technology}（确定性规则；
business/regulatory/safety 由 policy 决定，本轮按非 key 处理）。
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from .claim_assessment import ASSESSMENT_NOT_SEARCHED, assess
from .evidence_graph import EvidenceGraph
from .models import Idea

# 判定 I2 必须完成检索/评审的 key claim 类型（确定性规则）
KEY_CLAIM_TYPES = frozenset({"problem", "user", "mechanism", "technology"})


class IdeaMaturity(str, Enum):
    I0_RAW_IDEA = "I0"
    I1_STRUCTURED_IDEA = "I1"
    I2_EVIDENCE_BACKED_IDEA = "I2"
    # I3 只定义 contract：产品机会判定需要真实市场/工程证据，不在 Idea 域内实现。
    I3_PRODUCT_OPPORTUNITY = "I3"

    @classmethod
    def from_lifecycle(cls, lifecycle_status: str) -> IdeaMaturity:
        """【DEPRECATED】lifecycle_status 已不再携带成熟度（Commit 3）。

        旧值 raw/structured/evidence_backed 保留映射以兼容历史调用；
        新值 active/archived/superseded 无法推导成熟度 → 抛 ValueError。
        请改用 :meth:`IdeaMaturity.evaluate`（只读 graph）。
        """
        legacy = {
            "raw": cls.I0_RAW_IDEA,
            "structured": cls.I1_STRUCTURED_IDEA,
            "evidence_backed": cls.I2_EVIDENCE_BACKED_IDEA,
        }
        if lifecycle_status in legacy:
            return legacy[lifecycle_status]
        raise ValueError(
            f"lifecycle_status {lifecycle_status!r} no longer encodes maturity; "
            "use IdeaMaturity.evaluate()")

    @classmethod
    def key_claims(cls, graph: EvidenceGraph, idea: Idea) -> list[Any]:
        """返回 idea 的 key claims（KEY_CLAIM_TYPES 内的 claims）。"""
        return [
            c for c in graph.list_claims(idea.tenant_id, idea.project_id,
                                         idea.idea_id)
            if c.claim_type in KEY_CLAIM_TYPES
        ]

    @classmethod
    def evaluate(cls, idea: Idea, graph: EvidenceGraph) -> IdeaMaturity:
        """保守成熟度判定（只读 graph，不依赖 lifecycle_status）。"""
        claims = graph.list_claims(idea.tenant_id, idea.project_id, idea.idea_id)
        if not claims:
            return cls.I0_RAW_IDEA

        key = [c for c in claims if c.claim_type in KEY_CLAIM_TYPES]
        if key:
            # I2 要求所有 key claims 都完成 Evidence Search + 明确评估
            for c in key:
                rels = graph.get_claim_evidence(
                    idea.tenant_id, idea.project_id, c.claim_id)
                if assess(c, rels)["status"] == ASSESSMENT_NOT_SEARCHED:
                    return cls.I1_STRUCTURED_IDEA
            return cls.I2_EVIDENCE_BACKED_IDEA

        # 无 key claims：保守起见仍需至少一条 reviewed evidence 才 I2
        has_reviewed = any(
            any(r.review_status == "reviewed"
                for r in graph.get_claim_evidence(
                    idea.tenant_id, idea.project_id, c.claim_id))
            for c in claims
        )
        return cls.I2_EVIDENCE_BACKED_IDEA if has_reviewed else cls.I1_STRUCTURED_IDEA


__all__ = ["IdeaMaturity", "KEY_CLAIM_TYPES"]
