"""FakeProductIntelligenceProvider（**仅测试用**，§35/60）。

生产 bootstrap 绝不注册 fake —— 未配置真实 Provider 时 runtime probe
诚实报 EXTERNAL_DEPENDENCY；fake 只出现在测试 Runtime Golden E2E 中打通
Supervisor → Router → Adapter → Provider → Service 全链。
"""
from __future__ import annotations

from typing import Any

from aipd_os.product_intelligence.provider import (
    CandidateFeature,
    CandidateInsight,
    CandidateOpportunity,
    CandidatePrinciple,
    CandidateRequirement,
    ProductIntelligenceProvider,
)


class FakeProductIntelligenceProvider(ProductIntelligenceProvider):
    """测试专用：基于真实上下文（claims/insights 等）产出预置 candidates。"""

    provider_name = "fake-product-provider"
    model_name = "test-fixture"
    prompt_version = "fake_v1"

    def __init__(self) -> None:
        super().__init__()
        self.configured = True
        self.derive_calls: list[str] = []

    # ---- 预置候选（可覆盖）----
    insight_statements = [
        ("高龄用户需要短路径完成训练任务", "user_problem"),
        ("连续选择导致任务中断与放弃", "behavior"),
    ]
    opportunity_title = "AI 康复训练数字伴侣"
    principle_statements = ["关键康复任务减少层级与选择数量",
                            "训练任务一次一目标"]
    requirement_defs = [
        ("核心训练流程交互深度 ≤ 1 层菜单", "interaction", "critical",
         "usability test with 65+ users"),
        ("单任务全屏模式", "interaction", "critical", "usability test"),
    ]
    feature_defs = [
        ("单任务全屏训练模式", "mode"),
        ("语音+画面自动反馈", "automation"),
    ]

    def derive_insights(self, context: dict[str, Any]) -> list[CandidateInsight]:
        self.derive_calls.append("insights")
        claims = context.get("claims") or []
        claim_ids = [c["claim_id"] for c in claims]
        return [
            CandidateInsight(statement=s, insight_type=t,
                             source_claim_ids=claim_ids[:2],
                             rationale="fixture")
            for s, t in self.insight_statements
        ]

    def identify_opportunities(
            self, context: dict[str, Any]) -> list[CandidateOpportunity]:
        self.derive_calls.append("opportunity")
        insights = context.get("insights") or []
        return [CandidateOpportunity(
            title=self.opportunity_title, statement="基于证据的机会",
            source_insight_ids=[i["insight_id"] for i in insights[:1]],
            target_user="65+ 独居老人", problem="康复训练难以坚持",
            desired_outcome="训练完成率提升")]

    def derive_principles(self, context: dict[str, Any]) -> list[CandidatePrinciple]:
        self.derive_calls.append("principles")
        insights = context.get("insights") or []
        return [CandidatePrinciple(
            statement=s,
            source_insight_ids=[i["insight_id"] for i in insights[:1]],
            rationale="evidence-backed fixture") for s in self.principle_statements]

    def derive_requirements(
            self, context: dict[str, Any]) -> list[CandidateRequirement]:
        self.derive_calls.append("requirements")
        principles = context.get("principles") or []
        return [CandidateRequirement(
            title=t, statement=t, requirement_type=rt, criticality=cr,
            verification_method=vm,
            source_principle_ids=[p["principle_id"] for p in principles[:1]])
            for t, rt, cr, vm in self.requirement_defs]

    def derive_features(self, context: dict[str, Any]) -> list[CandidateFeature]:
        self.derive_calls.append("features")
        requirements = context.get("requirements") or []
        return [CandidateFeature(
            title=t, description=t, feature_type=ft,
            source_requirement_ids=[r["requirement_id"]
                                    for r in requirements[:1]])
            for t, ft in self.feature_defs]


__all__ = ["FakeProductIntelligenceProvider"]
