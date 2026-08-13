"""配置驱动的 LLM Provider 装配包（v5.9.2 N-1）。

包含通用 OpenAI 兼容 LLM 客户端（:mod:`aipd_os.llm.client`）以及
product intelligence / idea decompose 的 LLM Provider 实现：
- :class:`aipd_os.llm.client.LlmClient`：通用 ``/chat/completions`` 客户端；
- :class:`aipd_os.llm.product_intelligence_provider.LlmProductIntelligenceProvider`；
- :class:`aipd_os.llm.idea_decomposer_provider.LlmIdeaDecompositionProvider`。

仅在运行时显式配置（``AIPD_MODEL_API_KEY`` + ``AIPD_MODEL_BASE_URL``）时
由 ``runtime._register_external_providers`` 装配；未配置时行为与基线一致，
绝不注册 fake provider。
"""
from __future__ import annotations

from aipd_os.llm.client import DEFAULT_MODEL, LlmClient, LlmNotConfiguredError

__all__ = [
    "DEFAULT_MODEL",
    "LlmClient",
    "LlmNotConfiguredError",
]
