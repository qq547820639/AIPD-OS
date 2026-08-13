"""所有者体验层共享纯函数（全仓唯一实现）。

此前三组助手在多处复制粘贴、语义漂移：
- 选项规整：``instructions._options_of`` vs ``intent_engine._options_of``；
- 版本递增：``operations._bump_version`` vs ``web.views.WebConsole._bump_version``；
- metadata 解码：``artifact_preview._metadata`` vs ``web.views._metadata``。
统一收敛到本模块，各处 import 复用。
"""

from __future__ import annotations

import json
import re
from typing import Any

# 选项字符串的常见分隔符（"A/B/C"、"A、B、C"、"A,B,C"）
_OPTION_SPLIT_RE = re.compile(r"[/、,，|]")


def options_of(decision: dict[str, Any] | None) -> list[str]:
    """把 decision 的 options（list / 'A/B/C' 字符串 / options_json）规整为
    字符串列表（与决策卡片同口径）。"""
    if not decision:
        return []
    raw = decision.get("options")
    if raw is None:
        raw = decision.get("options_json")
    # DB 把 options 存为 options_json 字符串，先尝试 JSON 解码
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return [str(o) for o in parsed if str(o).strip()]
        if isinstance(parsed, str):
            raw = parsed
        elif parsed is not None:
            return []
        return [o.strip() for o in _OPTION_SPLIT_RE.split(raw) if o.strip()]
    if isinstance(raw, list):
        return [str(o) for o in raw if str(o).strip()]
    return []


def bump_version(version: str | None) -> str:
    """把版本号最后一段 +1（无法解析时追加 .1），用于返工/回滚的版本递增。"""
    v = str(version or "0.0")
    parts = v.split(".")
    try:
        last = int(parts[-1])
        parts[-1] = str(last + 1)
        return ".".join(parts)
    except ValueError:
        return f"{v}.1"


def metadata_of(d: dict[str, Any]) -> dict[str, Any]:
    """deliverables 表把 metadata 存为 metadata_json，统一解码为 dict。"""
    raw = d.get("metadata_json") or d.get("metadata")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


__all__ = ["options_of", "bump_version", "metadata_of"]
