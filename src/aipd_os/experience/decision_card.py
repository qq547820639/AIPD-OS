"""决策卡片：始终只呈现单一最高优先级的待审决策。

避免把一堆决策一股脑丢给产品所有者。每次只突出一个最高优先级
（系统最早提出、仍在等待的所有者）决策，并给出 AI 建议、2-4 个选项、
每个选项的成本/性能/时间/安全影响，以及批准后系统会自动执行什么。
若无待审决策则返回 None。
"""
from __future__ import annotations

import re
from typing import Any

from ..execution.decision_policy import build_decision_package
from ..state.db import AIPDStateDB

_IMPACT_DIMS = ("cost", "performance", "time", "safety")

# 默认按选项顺序给出的影响档位（首个=AI 推荐，风险相对受控）
_DEFAULT_IMPACT_LEVELS = (
    {"cost": "medium", "performance": "medium", "time": "medium", "safety": "none"},
    {"cost": "high", "performance": "low", "time": "high", "safety": "low"},
    {"cost": "low", "performance": "high", "time": "low", "safety": "none"},
    {"cost": "medium", "performance": "medium", "time": "high", "safety": "low"},
)


def _normalize_options(raw: Any) -> list[str]:
    """把 options（可能是 list 或 str）规整为 2-4 个字符串选项。"""
    if raw is None:
        return ["按 AI 推荐路径继续并冻结该决策点",
                "暂停并补充研究/数据后再决策",
                "改为人工介入执行该步骤"]
    if isinstance(raw, str):
        # 兼容 "A/B/C" 或 "A、B、C" 分隔
        candidates = [o.strip() for o in re.split(r"[/、,，|]", raw) if o.strip()]
        return candidates
    candidates = [str(o) for o in raw if str(o).strip()]
    if not candidates:
        return ["按 AI 推荐路径继续并冻结该决策点", "暂停并补充研究后再决策"]
    return candidates


def _clip_options(opts: list[str]) -> list[str]:
    if len(opts) >= 2 and len(opts) <= 4:
        return opts
    if len(opts) < 2:
        while len(opts) < 2:
            opts.append("补充研究后由所有者在更多选项中选择")
    if len(opts) > 4:
        opts = opts[:4]
    return opts


def _per_option_impacts(options: list[str]) -> dict[str, dict[str, str]]:
    """为每个选项生成成本/性能/时间/安全影响。"""
    impacts: dict[str, dict[str, str]] = {}
    for i, option in enumerate(options):
        level = _DEFAULT_IMPACT_LEVELS[i % len(_DEFAULT_IMPACT_LEVELS)]
        impacts[option] = dict(level)
    return impacts


def _after_approval(decision: dict[str, Any]) -> str:
    meta = decision.get("options_meta") or {}
    override = meta.get("after_approval")
    if override:
        return str(override)
    return f"批准后，系统将按推荐方案自动推进「{decision.get('topic')}」并同步更新相关产物与检查点。"  # noqa: E501


def build_decision_card(db: AIPDStateDB, project_id: str,
                        decision_id: str | None = None,
                        tenant_id: str = "default") -> dict[str, Any] | None:
    """返回单一最高优先级待审决策卡片；若无待审决策返回 None。"""
    open_decisions = db.list_open_decisions(tenant_id, project_id)
    if not open_decisions:
        return None

    if decision_id is not None:
        chosen = next((d for d in open_decisions if d["decision_id"] == decision_id), None)
        if chosen is None:
            return None
    else:
        # 最早提出仍在等待的决策视为最高优先级
        chosen = open_decisions[0]

    options = _clip_options(_normalize_options(chosen.get("options")))

    # 复用执行层的决策包逻辑生成默认建议（若可用）
    try:
        pkg = build_decision_package(
            {"work_id": chosen.get("decision_id"),
             "title": chosen.get("topic"),
             "category": chosen.get("trigger") or "decision"},
            recommendation=chosen.get("recommendation"),
            options=options,
            impact={},
        )
        recommendation = pkg["recommendation"]
    except Exception:
        recommendation = (chosen.get("recommendation")
                          or "按 AI 推荐路径继续，同时保留回退与复核点")

    return {
        "decision_id": chosen["decision_id"],
        "topic": chosen.get("topic"),
        "ai_recommendation": recommendation,
        "options": options,
        "impacts": _per_option_impacts(options),
        "after_approval": _after_approval(chosen),
        "details": {
            "status": chosen.get("status"),
            "trigger": chosen.get("trigger"),
            "created_at": chosen.get("created_at"),
        },
    }


__all__ = ["build_decision_card"]
