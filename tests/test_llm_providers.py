"""LLM Provider 契约与装配单元测试（v5.9.2 N-1）。

覆盖：
- :class:`LlmClient`：HTTP 200 / 非 200 / 网络异常 / 坏 JSON / 未配置
  （全部 monkeypatch urllib，**绝不发起真实网络调用**）；
- :class:`LlmProductIntelligenceProvider`：5 个方法产出正确 typed candidates、
  坏 JSON → ProductProviderError、围栏 JSON 可剥离；
- :class:`LlmIdeaDecompositionProvider`：StructuredCandidate 字段映射 +
  source、坏 JSON → IdeaDecompositionUnavailable。
"""
from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from email.message import Message
from typing import Any

import pytest

from aipd_os.idea.decomposer import (
    IdeaDecompositionUnavailable,
    StructuredCandidate,
)
from aipd_os.llm.client import LlmClient, LlmNotConfiguredError
from aipd_os.llm.idea_decomposer_provider import LlmIdeaDecompositionProvider
from aipd_os.llm.product_intelligence_provider import (
    LlmProductIntelligenceProvider,
)
from aipd_os.product_intelligence.provider import (
    CandidateFeature,
    CandidateInsight,
    CandidateOpportunity,
    CandidatePrinciple,
    CandidateRequirement,
    ProductProviderError,
)

# ---------------------------------------------------------------------------
# LlmClient HTTP 契约（monkeypatch urllib.request.urlopen）
# ---------------------------------------------------------------------------


class _FakeResponse:
    """模拟 urlopen 返回的响应对象（上下文管理器 + getcode + read）。"""

    def __init__(self, status: int = 200, body: bytes = b"") -> None:
        self._status = status
        self._body = body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        return None

    def getcode(self) -> int:
        return self._status

    def read(self) -> bytes:
        return self._body


def _client(**kwargs: Any) -> LlmClient:
    defaults: dict[str, Any] = {
        "endpoint": "http://fake/v1/chat/completions",
        "api_key": "secret",
        "model": "gpt-test",
    }
    defaults.update(kwargs)
    return LlmClient(
        endpoint=str(defaults["endpoint"]),
        api_key=str(defaults["api_key"]),
        model=str(defaults["model"]),
    )


def test_client_complete_returns_content(monkeypatch):
    payload = {"choices": [{"message": {"content": "hello world"}}]}
    monkeypatch.setattr(
        urllib.request, "urlopen",
        lambda req, timeout=None: _FakeResponse(
            200, json.dumps(payload).encode("utf-8")))
    assert _client().complete([{"role": "user", "content": "hi"}]) == "hello world"


def test_client_complete_sends_openai_compatible_payload(monkeypatch):
    captured = {}

    def fake_urlopen(req: urllib.request.Request, timeout: float | None = None) -> _FakeResponse:
        captured["request"] = req
        return _FakeResponse(
            200, json.dumps({"choices": [{"message": {"content": "x"}}]}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    _client().complete([{"role": "user", "content": "hi"}])
    req = captured["request"]
    assert req.headers["Authorization"] == "Bearer secret"
    assert req.headers["Content-type"] == "application/json"
    body = json.loads(req.data.decode("utf-8"))
    assert body["model"] == "gpt-test"
    assert body["temperature"] == 0.2
    assert body["messages"] == [{"role": "user", "content": "hi"}]


def test_client_complete_non_200_raises(monkeypatch):
    def fake_urlopen(req: urllib.request.Request, timeout: float | None = None) -> None:
        raise urllib.error.HTTPError(
            "http://fake", 500, "Internal Server Error", Message(), io.BytesIO(b"boom"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(RuntimeError, match="500"):
        _client().complete([{"role": "user", "content": "hi"}])


def test_client_complete_network_error_raises(monkeypatch):
    def fake_urlopen(req: urllib.request.Request, timeout: float | None = None) -> None:
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(RuntimeError, match="connection refused"):
        _client().complete([{"role": "user", "content": "hi"}])


def test_client_complete_bad_json_raises(monkeypatch):
    monkeypatch.setattr(
        urllib.request, "urlopen",
        lambda req, timeout=None: _FakeResponse(200, b"not json"))
    with pytest.raises(RuntimeError):
        _client().complete([{"role": "user", "content": "hi"}])


def test_client_complete_missing_choices_raises(monkeypatch):
    monkeypatch.setattr(
        urllib.request, "urlopen",
        lambda req, timeout=None: _FakeResponse(
            200, json.dumps({"choices": []}).encode()))
    with pytest.raises(RuntimeError):
        _client().complete([{"role": "user", "content": "hi"}])


def test_client_not_configured_raises():
    with pytest.raises(LlmNotConfiguredError):
        LlmClient("", "k", "m").complete([{"role": "user", "content": "hi"}])
    with pytest.raises(LlmNotConfiguredError):
        LlmClient("http://fake", "", "m").complete([{"role": "user", "content": "hi"}])


def test_client_configured_property():
    assert LlmClient("http://fake", "k", "m").configured is True
    assert LlmClient("", "k", "m").configured is False
    assert LlmClient("http://fake", "", "m").configured is False


# ---------------------------------------------------------------------------
# 脚本化 LlmClient（供 Provider 测试使用，绝不发起真实网络调用）
# ---------------------------------------------------------------------------


class _FakeLlmClient(LlmClient):
    """返回预设 JSON 文本的脚本化客户端，并记录每次调用消息。"""

    def __init__(
        self,
        responses: list[str] | None = None,
        configured: bool = True,
        model: str = "fake-model",
    ) -> None:
        super().__init__(endpoint="http://fake", api_key="fake-key", model=model)
        self._responses = list(responses or [])
        self._configured = configured
        self.calls: list[list[dict[str, Any]]] = []

    @property
    def configured(self) -> bool:
        return self._configured

    def complete(self, messages: list[dict[str, Any]]) -> str:
        self.calls.append(messages)
        if not self._responses:
            return "[]"
        return self._responses.pop(0)


def _pi(responses: list[str]) -> LlmProductIntelligenceProvider:
    return LlmProductIntelligenceProvider(_FakeLlmClient(responses))


def _dec(
    responses: list[str], configured: bool = True
) -> LlmIdeaDecompositionProvider:
    return LlmIdeaDecompositionProvider(
        _FakeLlmClient(responses, configured=configured))


# ---------------------------------------------------------------------------
# LlmProductIntelligenceProvider
# ---------------------------------------------------------------------------


def test_derive_insights_maps_candidates():
    resp = json.dumps([{
        "statement": "用户需要更快的导出", "insight_type": "user_problem",
        "source_claim_ids": ["c1"], "rationale": "r", "limitations": "l",
    }])
    out = _pi([resp]).derive_insights({"idea_id": "i1"})
    assert len(out) == 1
    c = out[0]
    assert isinstance(c, CandidateInsight)
    assert c.statement == "用户需要更快的导出"
    assert c.insight_type == "user_problem"
    assert c.source_claim_ids == ["c1"]
    assert c.rationale == "r"
    assert c.limitations == "l"


def test_identify_opportunities_maps_candidates():
    resp = json.dumps([{
        "title": "一键导出", "statement": "提供一键导出", "source_insight_ids": ["i1"],
        "target_user": "分析师", "problem": "手动太慢", "desired_outcome": "秒级导出",
        "differentiation": "全格式", "known_alternatives": ["x"], "evidence_gaps": ["g"],
    }])
    out = _pi([resp]).identify_opportunities({"idea_id": "i1"})
    assert len(out) == 1
    c = out[0]
    assert isinstance(c, CandidateOpportunity)
    assert c.title == "一键导出"
    assert c.statement == "提供一键导出"
    assert c.source_insight_ids == ["i1"]
    assert c.known_alternatives == ["x"]
    assert c.evidence_gaps == ["g"]


def test_derive_principles_maps_candidates():
    resp = json.dumps([{
        "statement": "数据可导是底线", "source_insight_ids": ["i1"],
        "rationale": "r", "criticality": "high",
    }])
    out = _pi([resp]).derive_principles({"idea_id": "i1"})
    assert len(out) == 1
    c = out[0]
    assert isinstance(c, CandidatePrinciple)
    assert c.statement == "数据可导是底线"
    assert c.criticality == "high"


def test_derive_requirements_maps_candidates():
    resp = json.dumps([{
        "title": "导出耗时", "statement": "导出耗时 < 1s", "source_principle_ids": ["p1"],
        "requirement_type": "non_functional", "criticality": "normal",
        "verification_method": "benchmark", "nominal_value": "1",
        "unit": "s", "upper_limit": "1",
    }])
    out = _pi([resp]).derive_requirements({"idea_id": "i1"})
    assert len(out) == 1
    c = out[0]
    assert isinstance(c, CandidateRequirement)
    assert c.title == "导出耗时"
    assert c.statement == "导出耗时 < 1s"
    assert c.source_principle_ids == ["p1"]
    assert c.nominal_value == "1"
    assert c.unit == "s"


def test_derive_features_maps_candidates():
    resp = json.dumps([{
        "title": "导出中心", "description": "统一导出入口", "source_requirement_ids": ["r1"],
        "feature_type": "capability", "assumptions": ["a"], "constraints": ["c"],
    }])
    out = _pi([resp]).derive_features({"idea_id": "i1"})
    assert len(out) == 1
    c = out[0]
    assert isinstance(c, CandidateFeature)
    assert c.title == "导出中心"
    assert c.description == "统一导出入口"
    assert c.source_requirement_ids == ["r1"]
    assert c.assumptions == ["a"]
    assert c.constraints == ["c"]


def test_pi_fenced_json_stripped():
    resp = "```json\n[{\"statement\": \"ok\"}]\n```"
    out = _pi([resp]).derive_insights({"idea_id": "i1"})
    assert len(out) == 1
    assert out[0].statement == "ok"


def test_pi_bad_json_raises_product_provider_error():
    with pytest.raises(ProductProviderError):
        _pi(["not json"]).derive_insights({"idea_id": "i1"})


def test_pi_non_list_json_raises_product_provider_error():
    with pytest.raises(ProductProviderError):
        _pi([json.dumps({"insights": []})]).derive_insights({"idea_id": "i1"})


def test_pi_produced_candidates_pass_validation():
    provider = _pi([
        json.dumps([{"statement": "s1"}]),
        json.dumps([{"title": "t1", "statement": "s1"}]),
        json.dumps([{"statement": "s1"}]),
        json.dumps([{"title": "t1", "statement": "s1"}]),
        json.dumps([{"title": "t1", "description": "d1"}]),
    ])
    assert provider.validate_candidates(
        provider.derive_insights({}), "insight") == []
    assert provider.validate_candidates(
        provider.identify_opportunities({}), "opportunity") == []
    assert provider.validate_candidates(
        provider.derive_principles({}), "principle") == []
    assert provider.validate_candidates(
        provider.derive_requirements({}), "requirement") == []
    assert provider.validate_candidates(
        provider.derive_features({}), "feature") == []


# ---------------------------------------------------------------------------
# LlmIdeaDecompositionProvider
# ---------------------------------------------------------------------------


def test_dec_available_reflects_client_configured():
    assert _dec([], configured=True).available() is True
    assert _dec([], configured=False).available() is False


def test_dec_unconfigured_decompose_raises():
    with pytest.raises(IdeaDecompositionUnavailable):
        _dec([], configured=False).decompose("raw idea")


def test_dec_decompose_maps_structured_candidate():
    resp = json.dumps({
        "title": "T", "goal": "G", "problem": "P", "target_user": "U",
        "desired_outcome": "O", "constraints": ["c1"],
        "claims": [{"claim_type": "problem", "statement": "s1"}],
    })
    c = _dec([resp]).decompose("raw idea")
    assert isinstance(c, StructuredCandidate)
    assert c.title == "T"
    assert c.goal == "G"
    assert c.constraints == ["c1"]
    assert c.claims == [{"claim_type": "problem", "statement": "s1"}]
    assert c.source == "llm_idea_decomposer"


def test_dec_decompose_fenced_json():
    inner = json.dumps({
        "title": "T", "goal": "G", "problem": "P", "target_user": "U",
        "desired_outcome": "O", "constraints": [],
        "claims": [{"claim_type": "user", "statement": "s"}],
    })
    c = _dec(["```json\n" + inner + "\n```"]).decompose("raw idea")
    assert c.title == "T"
    assert c.source == "llm_idea_decomposer"


def test_dec_bad_json_raises():
    with pytest.raises(IdeaDecompositionUnavailable):
        _dec(["not json"]).decompose("raw idea")


def test_dec_missing_title_raises():
    with pytest.raises(IdeaDecompositionUnavailable):
        _dec([json.dumps({"goal": "G"})]).decompose("raw idea")
