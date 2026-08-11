"""Idea 字段序列化器（v5.8.1 Commit 2）。

``constraints_json`` 的统一序列化/反序列化契约：

- :func:`serialize_constraints`  —— 新写入**永远用真 JSON**
  （``json.dumps(..., ensure_ascii=False, sort_keys=True)``），
  不再使用 Python repr（``str({...})``）；
- :func:`parse_constraints`  —— 读取时用 ``json.loads`` 解析并验证可解析；
  兼容旧 DB 中遗留的 Python repr 字符串（如 ``"{'constraints': [...]}"``，
  由 v5.8 的 ``decomposer._persist`` 写入），失败时尝试 ``ast.literal_eval``。

decomposer 写、IdeaService 读均经由此模块，保证格式统一。
"""
from __future__ import annotations

import ast
import json
from typing import Any

# constraints_json 的顶层结构：{"constraints": [str, ...]}
_CONSTRAINTS_KEY = "constraints"


def serialize_constraints(constraints: list[str]) -> str:
    """把约束列表序列化为真 JSON 字符串。

    ``{"constraints": [...]}``，``ensure_ascii=False`` + ``sort_keys=True``，
    保证跨平台/跨语言可解析且确定性。
    """
    return json.dumps(
        {_CONSTRAINTS_KEY: [str(c) for c in constraints]},
        ensure_ascii=False,
        sort_keys=True,
    )


def parse_constraints(constraints_json: str) -> list[str]:
    """解析 ``constraints_json`` 为约束字符串列表。

    优先 ``json.loads``；若失败（旧 DB 中遗留 Python repr，如
    ``"{'constraints': ['a']}"``），尝试 ``ast.literal_eval`` 后同样按
    ``{"constraints": [...]}`` / 纯列表 两种结构归一化。
    两种格式都无法解析时抛 :class:`ValueError`（显式失败，不静默）。
    """
    if constraints_json is None:
        return []
    text = str(constraints_json).strip()
    if not text:
        return []
    data: Any
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        try:
            data = ast.literal_eval(text)
        except (ValueError, SyntaxError, TypeError) as exc:
            raise ValueError(
                f"constraints_json 无法解析（既非 JSON 也非旧 repr）: "
                f"{text[:80]!r}") from exc
    return _normalize_constraints(data)


def _normalize_constraints(data: Any) -> list[str]:
    """把解析后的结构归一化为字符串列表。"""
    if isinstance(data, dict):
        items = data.get(_CONSTRAINTS_KEY)
        if items is None:
            # 空对象 {}（默认 EMPTY_CONSTRAINTS_JSON）视为空约束列表
            if not data:
                return []
            raise ValueError(
                f"constraints_json 缺少 {_CONSTRAINTS_KEY!r} 键: {str(data)[:80]!r}")
        data = items
    if isinstance(data, list):
        out: list[str] = []
        for item in data:
            if isinstance(item, str):
                out.append(item)
            else:
                out.append(str(item))
        return out
    raise ValueError(
        f"constraints_json 顶层必须是 dict/列表，实际为 {type(data).__name__}: "
        f"{str(data)[:80]!r}")


__all__ = [
    "serialize_constraints",
    "parse_constraints",
]
