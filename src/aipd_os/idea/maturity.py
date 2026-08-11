"""Idea Maturity（v5.8 Commit 14）。

生命周期映射（确定性规则）：
  - I0_RAW_IDEA             —— raw idea 存在（无 claims）；
  - I1_STRUCTURED_IDEA      —— Idea structured + 核心 Claims 创建 + schema valid；
  - I2_EVIDENCE_BACKED_IDEA —— 关键 Claims 经 evidence retrieval
    （support/contradiction/unknown 显式存在，无 fake evidence —— relation 的
    evidence_id 必须真实存在于 canonical evidence 表，由 EvidenceRelationService
    强制校验）；
  - I3_PRODUCT_OPPORTUNITY  —— 只定义 contract，本轮不实现。

与 Supervisor 正交：S0 Intake 承载 I0→I1；S1 Theory/Research 承载 I1→I2
（只做文档映射，不改 Supervisor 代码）。
"""
from __future__ import annotations

from enum import Enum

from .evidence_graph import EvidenceGraph
from .models import Idea


class IdeaMaturity(str, Enum):
    I0_RAW_IDEA = "I0"
    I1_STRUCTURED_IDEA = "I1"
    I2_EVIDENCE_BACKED_IDEA = "I2"
    # I3 只定义 contract：产品机会判定需要真实市场/工程证据，不在 Idea 域内实现。
    I3_PRODUCT_OPPORTUNITY = "I3"

    @classmethod
    def from_lifecycle(cls, lifecycle_status: str) -> IdeaMaturity:
        """把 idea.lifecycle_status 映射到成熟度枚举（I3 不由此映射）。"""
        mapping = {
            "raw": cls.I0_RAW_IDEA,
            "structured": cls.I1_STRUCTURED_IDEA,
            "evidence_backed": cls.I2_EVIDENCE_BACKED_IDEA,
        }
        if lifecycle_status not in mapping:
            raise ValueError(
                f"cannot map lifecycle_status {lifecycle_status!r} to IdeaMaturity")
        return mapping[lifecycle_status]

    @classmethod
    def evaluate(cls, idea: Idea, graph: EvidenceGraph) -> IdeaMaturity:
        """确定性 maturity 判定（基于 graph 实际 evidence，非 fake）。"""
        claims = graph.list_claims(idea.tenant_id, idea.project_id, idea.idea_id)
        if not claims:
            return cls.I0_RAW_IDEA
        has_real_evidence = any(
            graph.get_claim_evidence(idea.tenant_id, idea.project_id, c.claim_id)
            for c in claims
        )
        if has_real_evidence:
            return cls.I2_EVIDENCE_BACKED_IDEA
        return cls.I1_STRUCTURED_IDEA


__all__ = ["IdeaMaturity"]
