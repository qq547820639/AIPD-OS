"""Idea Maturity（v5.8 Commit 14 / v5.8.1 Commit 3-4 / v5.8.2 Commit 6）。

生命周期与成熟度分离（Commit 3）：``Idea.lifecycle_status`` 只表达对象生命
状态（active/archived/superseded）；**成熟度是 derived projection**——
:meth:`IdeaMaturity.evaluate` 只读 graph，不再从 lifecycle 推导。

保守 I2（Commit 4 + v5.8.2 Commit 6 Key Claim Coverage）——确定性规则：
  - I0_RAW_IDEA             —— 无 claims；
  - I1_STRUCTURED_IDEA      —— 有 claims，但未满足 I2 全部条件；
  - I2_EVIDENCE_BACKED_IDEA —— 全部满足：
    (a) 有 claims（Idea 已结构化）；
    (b) **所有 required key claim types 都存在**（IdeaMaturityPolicy；
        默认 problem/user/mechanism/technology —— 只有部分 key claims
        被调查 ≠ 必要类别齐全，例如缺 mechanism/technology 不能 I2）；
    (c) 每个 required key claim 都执行过 Evidence Search
        （有 reviewed relation —— pending/rejected 不算完成）；
    (d) 每个 required key claim 都有明确评估（ClaimAssessment 非
        NOT_SEARCHED）；
    (e) 无 fake/simulated evidence（relation.evidence_id 必须真实存在于
        canonical evidence 表 —— EvidenceRelationService 已强制校验）。
  - I3_PRODUCT_OPPORTUNITY  —— 只定义 contract，本轮不实现。

:class:`IdeaMaturityPolicy`：显式、可测、版本化的 key claim policy
（提示词 §15：不要把 key claims 永久硬编码死）。默认 required types：
problem / user / mechanism / technology；未来可按 project type / domain /
risk 升级（policy_version 驱动），本轮不复杂化。
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from .claim_assessment import ASSESSMENT_NOT_SEARCHED, assess
from .evidence_graph import EvidenceGraph
from .models import Idea

# 判定 I2 必须完成检索/评审的 key claim 类型（确定性规则）
KEY_CLAIM_TYPES = frozenset({"problem", "user", "mechanism", "technology"})


class IdeaMaturityPolicy:
    """Key Claim Coverage policy（v5.8.2 Commit 6；显式/可测/版本化）。

    - :attr:`policy_id`：策略版本标识（写入 gap/audit 输出）；
    - :attr:`required_claim_types`：I2 必须存在的 key claim 类别。
      默认 problem/user/mechanism/technology（提示词 §14-15）；
    - future：按 project_type / domain / risk 升级 required 集合，
      保留本类为唯一 policy 载体（禁止在 maturity 逻辑中再硬编码）。
    """

    policy_id = "idea_maturity_policy_v1"
    required_claim_types = frozenset({"problem", "user", "mechanism", "technology"})

    def required_missing(self, idea: Idea, graph: EvidenceGraph) -> list[str]:
        """缺失的 required claim type 列表（空 = 类别齐全）。"""
        present = {c.claim_type for c in graph.list_claims(
            idea.tenant_id, idea.project_id, idea.idea_id)}
        return sorted(self.required_claim_types - present)

    def not_searched_key_claims(self, idea: Idea,
                                graph: EvidenceGraph) -> list[str]:
        """required key claims 中未完成检索/评审的 claim_id 列表。"""
        out = []
        for c in graph.list_claims(idea.tenant_id, idea.project_id, idea.idea_id):
            if c.claim_type not in self.required_claim_types:
                continue
            rels = graph.get_claim_evidence(idea.tenant_id, idea.project_id,
                                            c.claim_id)
            if assess(c, rels)["status"] == ASSESSMENT_NOT_SEARCHED:
                out.append(c.claim_id)
        return out

    def gap_reasons(self, idea: Idea, graph: EvidenceGraph) -> list[str]:
        """面向 owner/audit 的证据缺口原因（空 = 满足 I2 前置）。"""
        reasons: list[str] = []
        missing = self.required_missing(idea, graph)
        if missing:
            reasons.append(
                f"missing required key claim types: {', '.join(missing)}")
        for cid in self.not_searched_key_claims(idea, graph):
            reasons.append(f"key claim {cid} not searched/assessed")
        return reasons

    def requirements_met(self, idea: Idea, graph: EvidenceGraph) -> bool:
        """required key claim coverage 是否全部满足（I2 前置条件）。"""
        return not self.gap_reasons(idea, graph)


# 默认 policy 实例（模块级单例；evaluate 使用）
_DEFAULT_POLICY = IdeaMaturityPolicy()


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
        """返回 idea 的 key claims（policy.required_claim_types 内的 claims）。"""
        return [
            c for c in graph.list_claims(idea.tenant_id, idea.project_id,
                                         idea.idea_id)
            if c.claim_type in _DEFAULT_POLICY.required_claim_types
        ]

    @classmethod
    def evaluate(cls, idea: Idea, graph: EvidenceGraph,
                 policy: IdeaMaturityPolicy | None = None) -> IdeaMaturity:
        """保守成熟度判定（只读 graph，不依赖 lifecycle_status）。

        v5.8.2 Commit 6：I2 必须满足 **required key claim coverage**
        （policy.required_claim_types 全覆盖 + 全部已检索/评审）；
        只有部分 key claims 被调查（如缺 mechanism/technology）→ I1 +
        Evidence Gap（:meth:`gap_reasons` 给出原因）。
        """
        p = policy or _DEFAULT_POLICY
        claims = graph.list_claims(idea.tenant_id, idea.project_id, idea.idea_id)
        if not claims:
            return cls.I0_RAW_IDEA

        # I2 前置：所有 required key claim types 存在 + 全部完成检索/评审
        if not p.requirements_met(idea, graph):
            return cls.I1_STRUCTURED_IDEA

        return cls.I2_EVIDENCE_BACKED_IDEA

    @classmethod
    def gap_reasons(cls, idea: Idea, graph: EvidenceGraph,
                    policy: IdeaMaturityPolicy | None = None) -> list[str]:
        """Idea 的 Evidence Gap 原因（供 owner UX / audit 展示）。"""
        p = policy or _DEFAULT_POLICY
        if not graph.list_claims(idea.tenant_id, idea.project_id, idea.idea_id):
            return ["no claims (I0: idea not structured)"]
        return p.gap_reasons(idea, graph)


__all__ = ["IdeaMaturity", "IdeaMaturityPolicy", "KEY_CLAIM_TYPES"]
