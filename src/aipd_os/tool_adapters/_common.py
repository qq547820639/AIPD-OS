"""工具适配器共享工具。"""

from __future__ import annotations

import os
from typing import Any


def env(name: str, default: str | None = None) -> str | None:
    """读取环境变量，空串视为未设置。"""
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    return v


def meta(
    capability_id: str,
    name: str,
    provider: str,
    version: str,
    available: bool = True,
    maturity_ceiling: str | None = None,
) -> dict[str, Any]:
    """构造 discover() 返回的能力元信息。"""
    return {
        "id": capability_id,
        "name": name,
        "provider": provider,
        "version": version,
        "maturity_ceiling": maturity_ceiling,
        "available": available,
    }


def token_meta(text: str, cost_per_1k: float = 0.0) -> dict[str, Any]:
    """根据文本长度估算 token 用量与成本，返回 _meta 字段。"""
    tokens = max(1, len(text) // 4)
    return {
        "cost": round(tokens / 1000 * cost_per_1k, 6),
        "tokens_in": 0,
        "tokens_out": tokens,
    }


__all__ = ["env", "meta", "token_meta"]
