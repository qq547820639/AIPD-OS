"""风险健康视图：把风险与外部等待事项汇总成一个确定性的红/黄/绿健康灯。

纯函数、无随机、无外部调用：给定相同的输入必定得到相同的输出。
供产品所有者一眼看懂项目当前的健康状态，不暴露任何内部代号。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# 影响级别优先级（数值越小越优先）
_IMPACT_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

# 项目处于这些状态视为存在阻塞（blocked_external 已在红灯分支单独处理）
_BLOCKER_STATUSES = {"blocked_external", "internal_rework", "awaiting_owner_decision"}

_LABELS = {"green": "良好", "yellow": "需关注", "red": "高风险"}


def _open_risks(risks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [r for r in risks if r.get("status") == "open"]


def _top_open_risk(risks: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    opens = _open_risks(risks)
    if not opens:
        return None
    return sorted(opens, key=lambda r: _IMPACT_ORDER.get(str(r.get("impact")).lower(), 4))[0]


def traffic_light_status(risks: List[Dict[str, Any]],
                         external_waiting: List[Dict[str, Any]],
                         project_status: Optional[str] = None) -> str:
    """返回 "red" / "yellow" / "green" 三态健康灯。"""
    opens = _open_risks(risks)
    if project_status == "blocked_external" or any(
            str(r.get("impact")).lower() in ("critical", "high") for r in opens):
        return "red"
    if any(str(r.get("impact")).lower() == "medium" for r in opens) \
            or external_waiting \
            or (project_status in _BLOCKER_STATUSES):
        return "yellow"
    return "green"


def compute_risk_health(risks: List[Dict[str, Any]],
                        external_waiting: List[Dict[str, Any]],
                        project_status: Optional[str] = None) -> Dict[str, Any]:
    """返回确定性的风险健康视图。

    规则：
      - 存在 impact 为 critical/high 的未闭环风险，或项目处于 blocked_external
        => 红灯；
      - 存在 impact 为 medium 的未闭环风险，或还有外部等待事项，或项目存在阻塞
        => 黄灯；
      - 否则 => 绿灯。
    """
    light = traffic_light_status(risks, external_waiting, project_status)
    top = _top_open_risk(risks)
    top_title = top["title"] if top else None

    if light == "red":
        summary = "项目当前处于高风险状态，需要立即关注。"
        reason = "存在高风险未闭环风险，或项目正被外部阻塞。" \
                 + (f"首要风险：{top_title}。" if top_title else "")
    elif light == "yellow":
        summary = "项目需要您关注，存在待处理的待办事项。"
        reason = "存在中等风险、尚未闭环的外部等待事项，或项目处于阻塞状态。"
    else:
        summary = "项目整体健康，暂无显著风险。"
        reason = "无重大未闭环风险，也无外部阻塞。"

    return {
        "traffic_light": light,
        "summary": summary,
        "reason": reason,
        "top_risk_title": top_title,
    }


__all__ = ["compute_risk_health", "traffic_light_status"]