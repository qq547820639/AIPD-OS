"""决策策略：何时需要征询人类/所有者决策。

规则：**仅当**存在以下情形时才应征询决策：
1. 方向存在歧义（产品架构分叉等）；
2. 价值/风险偏好未知（需要所有者价值判断）；
3. 不可逆投入（开模/采购/正式发布等）；
4. 安全或监管影响；
5. 硬约束冲突。

普通的重做、检索、批量处理等不应触发决策。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

# 触发决策的类别
ASK_CATEGORIES = {
    "product_architecture_fork",  # 方向/架构分叉
    "value_preference_unknown",   # 价值/风险偏好未知
    "value_judgment",
    "irreversible_investment",    # 不可逆投入
    "tooling_or_purchase",
    "key_interface_freeze",
    "formal_drawing_release",
    "production_release",
    "safety_or_regulatory",
    "hard_constraint_conflict",
    "human_trial",
    "ip_or_claim_risk",
}

# 明确不需要征询的类别（普通工作）
NO_ASK_CATEGORIES = {"rework", "search", "batching", "ordinary", "iteration"}


def _flag(work_item: dict[str, Any], key: str, default: Any = None) -> Any:
    if work_item is None:
        return default
    return work_item.get(key, default)


def should_ask_decision(
    work_item: dict[str, Any] | None,
    context: dict[str, Any] | None = None,
) -> bool:
    """判断当前工作项是否需要征询决策。

    仅当方向歧义 / 价值偏好未知 / 不可逆投入 / 安全或监管 / 硬约束冲突时返回 True。
    普通重做、检索、批量处理等一律返回 False。
    """
    if work_item is None:
        return False
    ctx = context or {}
    cat = _flag(work_item, "category") or _flag(ctx, "category")

    if cat in ASK_CATEGORIES:
        return True

    # 标志位 / 档位判断（优先级高于 NO_ASK 类别：重做但不可逆/需所有者确认也须征询）
    if _flag(work_item, "irreversible") or _flag(ctx, "irreversible"):
        return True
    if _flag(work_item, "owner_required"):
        return True
    if _flag(work_item, "hard_constraint_conflict") or _flag(ctx, "hard_constraint_conflict"):
        return True
    if _flag(work_item, "value_judgment") or _flag(ctx, "value_judgment"):
        return True
    safety = _flag(work_item, "safety_impact") or _flag(ctx, "safety_impact") or "none"
    if safety in {"high", "critical"}:
        return True
    regulatory = _flag(work_item, "regulatory_impact") or _flag(ctx, "regulatory_impact") or "none"
    if regulatory in {"high", "critical"}:
        return True
    # 普通类别（重做/检索/批量等）不触发决策
    if cat in NO_ASK_CATEGORIES:
        return False
    return False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_decision_package(
    work_item: dict[str, Any],
    recommendation: str | None = None,
    options: list[str] | None = None,
    impact: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构建单一最高优先级决策包。

    包含：一个最高优先级决策、AI 建议、2-4 个选项、成本/性能/时间/安全影响，
    以及“批准后将执行什么”。
    """
    opts = options or [
        "按 AI 推荐路径继续并冻结该决策点",
        "暂停并补充研究/数据后再决策",
        "改为人工介入执行该步骤",
    ]
    if len(opts) < 2 or len(opts) > 4:
        raise ValueError("options 数量必须为 2-4 个")

    rec = recommendation or (
        "由 AI 按最稳妥的默认路径继续，同时保留回退与复核点"
        if not _flag(work_item, "irreversible")
        else "暂停不可逆投入，等待所有者确认后再执行"
    )

    imp = dict(impact or {})
    imp.setdefault("cost", _flag(work_item, "cost_impact", "medium"))
    imp.setdefault("performance", _flag(work_item, "performance_impact", "medium"))
    imp.setdefault("time", _flag(work_item, "time_impact", "medium"))
    imp.setdefault("safety", _flag(work_item, "safety_impact", "none"))

    category = _flag(work_item, "category", "decision")
    decision = {
        "topic": _flag(work_item, "title", "未命名决策"),
        "category": category,
        "reason": _flag(work_item, "decision_reason", f"触发类别: {category}"),
    }

    return {
        "decision_id": f"D-{uuid.uuid4().hex[:8]}",
        "work_id": _flag(work_item, "work_id"),
        "decision": decision,
        "recommendation": rec,
        "options": opts,
        "impact": imp,
        "execute_after_approval": (
            f"批准后将对工作项 {_flag(work_item, 'work_id')} 执行能力 "
            f"{_flag(work_item, 'capability_floor', 'N/A')} 并更新其状态与产物"
        ),
        "created_at": _now(),
        "status": "proposed",
    }


__all__ = [
    "ASK_CATEGORIES",
    "NO_ASK_CATEGORIES",
    "should_ask_decision",
    "build_decision_package",
]
