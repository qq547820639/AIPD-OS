"""成功经验回灌测试：渲染/指纹/Provider 注入（v5.10 定位修正）。"""
from __future__ import annotations

from aipd_os.llm.experience import (
    DEFAULT_EXPERIENCE,
    ExperienceFeedback,
    render_experience,
)


def test_render_experience_contains_practices_and_principles():
    out = render_experience(DEFAULT_EXPERIENCE)
    assert "既有成功经验" in out
    assert "检索到 ≠ 证实" in out  # 恒附加的行为原则
    assert DEFAULT_EXPERIENCE[0]["practice"][:12] in out
    # 空经验 → 空串（基线行为不变）
    assert render_experience([]) == ""


def test_render_respects_max_chars():
    out = render_experience(DEFAULT_EXPERIENCE, max_chars=200)
    assert len(out) <= 200


def test_fingerprint_stable_and_source_sensitive():
    a = ExperienceFeedback()
    b = ExperienceFeedback()
    assert a.fingerprint() == b.fingerprint()
    c = ExperienceFeedback(examples=[], source="other")
    assert c.fingerprint() != a.fingerprint()
    assert len(a.fingerprint()) == 16


def test_product_provider_injects_experience_into_system():
    """经验回灌：Provider 构造时传入 ExperienceFeedback，系统消息必须包含
    经验段落；不传时基线行为不变。"""
    from aipd_os.llm.product_intelligence_provider import (
        LlmProductIntelligenceProvider,
    )

    class _Client:
        model = "test-model"

        def __init__(self):
            self.messages = []

        def complete(self, messages):
            self.messages = messages
            return "[]"

    exp = ExperienceFeedback()
    client = _Client()
    provider = LlmProductIntelligenceProvider(client, experience=exp)
    provider.derive_insights({"idea_id": "i1", "claims": [], "assessments": []})
    system = client.messages[0]["content"]
    assert "既有成功经验" in system
    assert "检索到 ≠ 证实" in system

    # 不回灌：无经验段落
    client2 = _Client()
    provider2 = LlmProductIntelligenceProvider(client2)
    provider2.derive_insights({"idea_id": "i1", "claims": [], "assessments": []})
    assert "既有成功经验" not in client2.messages[0]["content"]


def test_idea_provider_injects_experience_into_system():
    from aipd_os.llm.idea_decomposer_provider import (
        LlmIdeaDecompositionProvider,
    )

    class _Client:
        model = "test-model"

        def __init__(self):
            self.messages = []
            self.configured = True

        def complete(self, messages):
            self.messages = messages
            return ('{"title": "t", "goal": "g", "problem": "p", '
                    '"target_user": "u", "desired_outcome": "o", '
                    '"constraints": [], "claims": [{"claim_type": "problem", '
                    '"statement": "s"}]}')

    exp = ExperienceFeedback()
    client = _Client()
    provider = LlmIdeaDecompositionProvider(client, experience=exp)
    provider.decompose("做个产品")
    system = client.messages[0]["content"]
    assert "既有成功经验" in system
