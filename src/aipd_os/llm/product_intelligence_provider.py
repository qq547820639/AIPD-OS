"""配置驱动的 LLM ProductIntelligenceProvider（v5.9.2 N-1）。

继承 :class:`aipd_os.product_intelligence.provider.ProductIntelligenceProvider`，
用通用 :class:`aipd_os.llm.client.LlmClient` 把 Evidence（ClaimAssessment 等）
转译为 product intelligence **candidate** 输出（typed input / typed candidate /
schema validation 由上游 adapter + :meth:`validate_candidates` 完成）。

诚实原则（§4/32/36 对齐）：
- 输出永远是 Candidate（lifecycle=candidate），绝不直接创建 approved 对象；
- LLM 调用失败或响应无法解析 → 抛 :class:`ProductProviderError` 上抛，
  **绝不返回空列表假装成功**；
- 未配置真实 Provider 时本类不会被生产 bootstrap 装配（见 runtime）。
"""
from __future__ import annotations

import json
from typing import Any

from aipd_os.llm.client import LlmClient
from aipd_os.product_intelligence.provider import (
    CandidateFeature,
    CandidateInsight,
    CandidateOpportunity,
    CandidatePrinciple,
    CandidateRequirement,
    ProductIntelligenceProvider,
    ProductProviderError,
)

_SYSTEM_BASE = (
    "你是 AIPD-OS 产品开发分析助手。你只输出 JSON，不要输出任何解释、"
    "注释或 JSON 以外的文字。"
)


def _strip_markdown_fence(text: str) -> str:
    """剥离 markdown 代码围栏（```json / ```）与前后空白（共享实现）。"""
    from aipd_os.llm.json_helpers import strip_markdown_fence
    return strip_markdown_fence(text)


def _parse_json_list(raw: str) -> list[dict[str, Any]]:
    """把 LLM 响应解析为对象列表；失败抛 ProductProviderError（不假装成功）。"""
    from aipd_os.llm.json_helpers import parse_json_text
    try:
        data = parse_json_text(raw)
    except ValueError as exc:
        raise ProductProviderError(f"{exc}") from exc
    if not isinstance(data, list):
        raise ProductProviderError("LLM 响应必须是 JSON 数组（对象列表）")
    return data


def _str(value: Any, default: str = "") -> str:
    return str(value) if value is not None else default


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v) for v in value]


def _optional_str(value: Any) -> str | None:
    return str(value) if value is not None else None


class LlmProductIntelligenceProvider(ProductIntelligenceProvider):
    """OpenAI 兼容 LLM 驱动的 Product Intelligence 生成 Provider。"""

    provider_name = "llm-openai-compatible"
    prompt_version = "pi-v1"

    def __init__(self, client: LlmClient) -> None:
        super().__init__()
        self._client = client
        self.configured = True
        self.model_name = client.model

    # ------------------------------------------------------------------ helper
    def _complete_json(self, stage_prompt: str,
                       context: dict[str, Any]) -> list[dict[str, Any]]:
        """构造 system/user 消息并解析为对象列表（失败上抛，不吞错）。"""
        system = _SYSTEM_BASE + "\n\n" + stage_prompt
        user = json.dumps(context, ensure_ascii=False)
        raw = self._client.complete([
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ])
        return _parse_json_list(raw)

    # ------------------------------------------------------------- generation
    def derive_insights(self, context: dict[str, Any]) -> list[CandidateInsight]:
        prompt = (
            "当前阶段：从 ClaimAssessment/Claims 提炼 Insight 候选。\n"
            "输入 context 各键含义：idea_id（想法 id）、claims（候选命题列表，"
            "每项含 claim_id/claim_type/statement/epistemic_status）、"
            "assessments（命题评价）、tenant_id/project_id（作用域）。\n"
            "输出一个 JSON 数组，每项一个对象，字段：statement（必填，洞察陈述）、"
            "insight_type（默认 user_problem）、source_claim_ids（字符串数组，"
            "来源命题 id）、rationale（依据）、limitations（局限）。"
        )
        items = self._complete_json(prompt, context)
        return [
            CandidateInsight(
                statement=_str(d.get("statement")),
                insight_type=_str(d.get("insight_type"), "user_problem"),
                source_claim_ids=_str_list(d.get("source_claim_ids")),
                rationale=_str(d.get("rationale")),
                limitations=_str(d.get("limitations")),
            )
            for d in items
        ]

    def identify_opportunities(
            self, context: dict[str, Any]) -> list[CandidateOpportunity]:
        prompt = (
            "当前阶段：从 Insights 提炼 Opportunity 候选（不自动 select —— "
            "selection 是 Owner/Gate 层决策）。\n"
            "输入 context 各键含义：idea_id、insights（洞察列表，每项含 "
            "insight_id/title/statement）、tenant_id/project_id。\n"
            "输出一个 JSON 数组，每项一个对象，字段：title（必填，机会标题）、"
            "statement（必填，机会陈述）、source_insight_ids（字符串数组）、"
            "target_user（目标用户）、problem（问题）、desired_outcome（期望结果）、"
            "differentiation（差异化）、known_alternatives（字符串数组）、"
            "evidence_gaps（字符串数组）。"
        )
        items = self._complete_json(prompt, context)
        return [
            CandidateOpportunity(
                title=_str(d.get("title")),
                statement=_str(d.get("statement")),
                source_insight_ids=_str_list(d.get("source_insight_ids")),
                target_user=_str(d.get("target_user")),
                problem=_str(d.get("problem")),
                desired_outcome=_str(d.get("desired_outcome")),
                differentiation=_str(d.get("differentiation")),
                known_alternatives=_str_list(d.get("known_alternatives")),
                evidence_gaps=_str_list(d.get("evidence_gaps")),
            )
            for d in items
        ]

    def derive_principles(self,
                          context: dict[str, Any]) -> list[CandidatePrinciple]:
        prompt = (
            "当前阶段：从 Insights + 已选 Opportunity 提炼 ProductPrinciple 候选。\n"
            "输入 context 各键含义：idea_id、insights（洞察列表）、opportunity"
            "（已选机会对象，含 opportunity_id/title/statement）、"
            "tenant_id/project_id。\n"
            "输出一个 JSON 数组，每项一个对象，字段：statement（必填，原则陈述）、"
            "source_insight_ids（字符串数组）、rationale（依据）、"
            "criticality（默认 normal）。"
        )
        items = self._complete_json(prompt, context)
        return [
            CandidatePrinciple(
                statement=_str(d.get("statement")),
                source_insight_ids=_str_list(d.get("source_insight_ids")),
                rationale=_str(d.get("rationale")),
                criticality=_str(d.get("criticality"), "normal"),
            )
            for d in items
        ]

    def derive_requirements(
            self, context: dict[str, Any]) -> list[CandidateRequirement]:
        prompt = (
            "当前阶段：从 Principles 提炼 Requirement 候选（candidate，非 approved）。\n"
            "输入 context 各键含义：idea_id、principles（原则列表，每项含 "
            "principle_id/title/statement）、tenant_id/project_id。\n"
            "输出一个 JSON 数组，每项一个对象，字段：title（必填，需求标题）、"
            "statement（必填，需求陈述）、source_principle_ids（字符串数组）、"
            "requirement_type（默认 functional）、criticality（默认 normal）、"
            "verification_method（验证方法）、nominal_value（标称值）、unit（单位）、"
            "lower_limit（下限）、upper_limit（上限）、tolerance（公差）、"
            "test_condition（测试条件）。"
        )
        items = self._complete_json(prompt, context)
        return [
            CandidateRequirement(
                title=_str(d.get("title")),
                statement=_str(d.get("statement")),
                source_principle_ids=_str_list(d.get("source_principle_ids")),
                requirement_type=_str(d.get("requirement_type"), "functional"),
                criticality=_str(d.get("criticality"), "normal"),
                verification_method=_str(d.get("verification_method")),
                nominal_value=_optional_str(d.get("nominal_value")),
                unit=_optional_str(d.get("unit")),
                lower_limit=_optional_str(d.get("lower_limit")),
                upper_limit=_optional_str(d.get("upper_limit")),
                tolerance=_optional_str(d.get("tolerance")),
                test_condition=_optional_str(d.get("test_condition")),
            )
            for d in items
        ]

    def derive_features(self, context: dict[str, Any]) -> list[CandidateFeature]:
        prompt = (
            "当前阶段：从 Requirements 提炼 Feature 候选（candidate，非 approved）。\n"
            "输入 context 各键含义：idea_id、requirements（需求列表，每项含 "
            "requirement_id/title/statement）、tenant_id/project_id。\n"
            "输出一个 JSON 数组，每项一个对象，字段：title（必填，功能标题）、"
            "description（必填，功能描述）、source_requirement_ids（字符串数组）、"
            "feature_type（默认 capability）、assumptions（字符串数组）、"
            "constraints（字符串数组）。"
        )
        items = self._complete_json(prompt, context)
        return [
            CandidateFeature(
                title=_str(d.get("title")),
                description=_str(d.get("description")),
                source_requirement_ids=_str_list(d.get("source_requirement_ids")),
                feature_type=_str(d.get("feature_type"), "capability"),
                assumptions=_str_list(d.get("assumptions")),
                constraints=_str_list(d.get("constraints")),
            )
            for d in items
        ]


__all__ = [
    "LlmProductIntelligenceProvider",
]
