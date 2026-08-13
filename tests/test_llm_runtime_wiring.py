"""runtime 配置驱动 LLM Provider 装配测试（v5.9.2 N-1）。

验证 ``build_runtime`` 在 ``AIPD_MODEL_API_KEY`` + ``AIPD_MODEL_BASE_URL``
配置时装配真实 LLM Provider（product.* / idea.decompose）；未配置时保持
与基线一致的诚实降级（EXTERNAL_DEPENDENCY / 不注册 idea.decompose）。
所有断言均**不发起真实网络调用**（仅检查注册/装配结果）。
"""
from __future__ import annotations

import pytest

from aipd_os.config import reload_settings
from aipd_os.runtime import (
    PROBE_AVAILABLE,
    PROBE_EXTERNAL,
    PROBE_UNAVAILABLE,
    build_runtime,
    reset_runtime,
)

_MODEL_ENV_VARS = ("AIPD_MODEL_API_KEY", "AIPD_MODEL_BASE_URL", "AIPD_MODEL_NAME")


@pytest.fixture(autouse=True)
def _clean_model_env_and_runtime(monkeypatch):
    """清空 LLM 配置 env + 重置 runtime/settings，隔离测试。"""
    for var in _MODEL_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    reset_runtime()
    reload_settings()
    yield
    reset_runtime()
    reload_settings()


def test_llm_wiring_when_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPD_MODEL_API_KEY", "k")
    monkeypatch.setenv("AIPD_MODEL_BASE_URL", "http://fake/v1/chat/completions")
    monkeypatch.setenv("AIPD_MODEL_NAME", "gpt-test")
    reload_settings()
    ctx = build_runtime(db_path=str(tmp_path / "state.db"))

    probe = ctx.probe()
    # product.* adapter discover available=True → probe AVAILABLE
    assert probe["product"]["product.derive_insights"] == PROBE_AVAILABLE

    # idea.decompose 经 ProviderRegistry 注册，probe().available 为 True
    adapter = ctx.providers.get_by_capability("idea.decompose")
    assert adapter is not None
    assert adapter.probe().available is True
    assert ctx.external_providers["llm-idea-decomposer"].available() is True
    assert ctx.external_providers["llm-product-intelligence"].configured is True


def test_llm_wiring_unconfigured_matches_baseline(tmp_path):
    ctx = build_runtime(db_path=str(tmp_path / "state.db"))
    probe = ctx.probe()

    # product.* 以 provider=None 注册 → discover available=False → EXTERNAL_DEPENDENCY
    assert probe["product"]["product.derive_insights"] == PROBE_EXTERNAL

    # idea.decompose 未注册（providers 中无该 capability）
    assert ctx.providers.get_by_capability("idea.decompose") is None
    # probe 的 research 字典只看 adapters → idea.decompose 仍 UNAVAILABLE（现状保持）
    assert probe["research"]["idea.decompose"] == PROBE_UNAVAILABLE

    # 未配置时 external_providers 不含 LLM provider
    assert "llm-product-intelligence" not in ctx.external_providers
    assert "llm-idea-decomposer" not in ctx.external_providers
    assert ctx.external_providers["researchstudio"] is not None
