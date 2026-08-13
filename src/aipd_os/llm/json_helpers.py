"""LLM Provider 共享的响应解析助手（全仓唯一实现）。

此前 ``llm/idea_decomposer_provider.py`` 与 ``llm/product_intelligence_provider.py``
各自复制一份 ``_strip_markdown_fence`` 与 JSON 解析逻辑；围栏剥离规则/容错策略
改一处容易漏改另一处。本模块提供与错误类型无关的纯函数，provider 层只负责把
失败包装成各自的异常类型（IdeaDecompositionUnavailable / ProductProviderError）。
"""

from __future__ import annotations

import json
from typing import Any


def strip_markdown_fence(text: str) -> str:
    """剥离 markdown 代码围栏（```json / ```）与前后空白。"""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def parse_json_text(raw: str) -> Any:
    """把 LLM 响应解析为 JSON 值；失败抛 ValueError（调用方包装为领域异常）。"""
    text = strip_markdown_fence(raw)
    try:
        return json.loads(text)
    except ValueError as exc:
        raise ValueError(f"LLM 响应不是合法 JSON（{exc}）") from exc


__all__ = ["strip_markdown_fence", "parse_json_text"]
