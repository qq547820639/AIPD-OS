"""IdeaDecomposer 确定性夹具（v5.8 Commit 12）。

仅测试路径使用：生产 ``IdeaDecomposer`` 默认无 provider（CAPABILITY_UNAVAILABLE），
测试通过 :class:`FakeIdeaDecompositionProvider` 显式注入。

候选 Claims 是「待验证命题」，默认 epistemic_status=A/U，绝不产出 V 事实。
"""
from __future__ import annotations

from typing import Any

from aipd_os.idea import (
    IdeaDecompositionProvider,
    StructuredCandidate,
)

ELDERLY_REHAB_PROMPT = "我想做一个利用 AI 帮助独居老人居家康复的产品"

# 示例候选输出（fixture 非真实医学事实）
# EPISTEMIC_NOTE: fixture 数据仅用于测试系统行为，不代表真实医学结论。
FIXTURE_ELDERLY_REHAB_CANDIDATE = {
    "title": "AI 独居老人居家康复助手",
    "goal": "利用 AI 视觉与运动指导帮助独居老人安全完成居家康复训练",
    "problem": "独居老人缺乏康复训练陪伴，动作依从性与正确性难以保证",
    "target_user": "60 岁以上独居、患慢性运动功能障碍的老年人",
    "desired_outcome": "老人能独立完成每日 20 分钟康复训练，动作正确率提升",
    "constraints": ["单摄像头即可", "离线可运行", "不依赖护工在场"],
    "claims": [
        {"claim_type": "problem", "statement": "独居老人居家康复存在依从性不足的问题"},
        {"claim_type": "user", "statement": "60 岁以上独居老人是主要目标用户"},
        {"claim_type": "behavior", "statement": "视觉反馈可能改善康复动作完成度"},
        {"claim_type": "mechanism", "statement": "AI 姿态估计可识别康复动作正确性"},
        {"claim_type": "technology", "statement": "单目摄像头可支撑居家动作识别"},
        {"claim_type": "product", "statement": "离线本地推理满足隐私与可靠性要求"},
        {"claim_type": "safety", "statement": "动作纠正提示不应鼓励超出安全范围的动作"},
        {"claim_type": "engineering", "statement": "需要低算力设备上的实时推理方案"},
    ],
    "source": "test_fixture",
    "EPISTEMIC_NOTE": "FIXTURE ONLY: 非真实医学事实；仅用于测试系统行为。",
}


class FakeIdeaDecompositionProvider(IdeaDecompositionProvider):
    """确定性分解 provider（仅测试路径）。"""

    name = "fake-idea-decomposer"

    def __init__(self, candidate: dict[str, Any | None] | None = None) -> None:
        self._candidate = candidate or FIXTURE_ELDERLY_REHAB_CANDIDATE
        self.decompose_count = 0

    def available(self) -> bool:
        return True

    def decompose(self, raw_input: str,
                  idea_context: dict[str, Any | None] | None = None) -> StructuredCandidate:
        self.decompose_count += 1
        data = dict(self._candidate)
        data.pop("EPISTEMIC_NOTE", None)
        return StructuredCandidate.from_dict(data)


class BrokenFakeIdeaDecompositionProvider(IdeaDecompositionProvider):
    """返回非法结构（缺字段）的 provider（用于 FAILED_VALIDATION 测试）。"""

    name = "broken-idea-decomposer"

    def available(self) -> bool:
        return True

    def decompose(self, raw_input: str,
                  idea_context: dict[str, Any | None] | None = None) -> StructuredCandidate:
        # 缺 title / claims（schema required）
        return StructuredCandidate(title="", goal="g", problem="p",
                                   target_user="u", desired_outcome="o",
                                   constraints=[], claims=[])


__all__ = [
    "ELDERLY_REHAB_PROMPT",
    "FIXTURE_ELDERLY_REHAB_CANDIDATE",
    "FakeIdeaDecompositionProvider",
    "BrokenFakeIdeaDecompositionProvider",
]
