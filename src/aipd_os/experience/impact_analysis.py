"""影响分析与成本/时间估算（P2-1 闭环）。

把一条 :class:`Intent` 展开为：受影响制品列表、预计成本/时间、可撤销预览、
必要时的批准门禁与"为什么需要您决定"的说明，以及 before/after 差异。
全部确定性、可测试，不依赖任何外部服务。
"""
from __future__ import annotations

from typing import Any, Dict, List

from ..state.db import AIPDStateDB
from .intent_engine import Intent

# 交付物类型代号 → 中文
_TYPE_CN = {
    "manual": "使用手册", "cad": "CAD 图纸", "bom": "物料清单",
    "drawing": "工程图纸", "page": "页面", "marketing": "营销物料",
    "spec": "规格书", "test_report": "测试报告",
}

# 里程碑/阶段代号 → 中文
_MILESTONE_CN = {
    "G0": "概念验证", "G1": "需求冻结", "G2": "方案定稿", "G3": "详细设计",
    "G4": "样机试制", "G5": "工程验证", "G6": "设计验证", "G7": "生产验证",
    "G8": "量产准备", "G9": "正式发布",
}

# 每项受影响制品的估算耗时（分钟）与成本（元）
_MINUTES_PER_ARTIFACT = 15
_BASE_MINUTES = 5
_COST_PER_ARTIFACT = 6.0


def type_cn(t: Any) -> str:
    return _TYPE_CN.get(str(t or "").lower(), str(t or ""))


def milestone_cn(gate: Any) -> str:
    return _MILESTONE_CN.get(str(gate or ""), "后续阶段")


def _in_scope(d: Dict[str, Any]) -> bool:
    return d.get("status") not in ("released", "archived")


def _affected_for_kind(db: AIPDStateDB, project_id: str, intent: Intent,
                       tenant_id: str) -> List[Dict[str, Any]]:
    """根据意图类型确定受影响制品（未发布未归档的交付物）。"""
    deliverables = db.list_deliverables(tenant_id, project_id)
    kind = intent.kind
    if kind in ("cost_reduction", "approve", "choose"):
        return [d for d in deliverables if _in_scope(d)]
    if kind == "style_constraint":
        return [d for d in deliverables if _in_scope(d) and (
            "manual" in (d.get("type") or "").lower()
            or "page" in (d.get("type") or "").lower()
            or "外观" in (d.get("type") or ""))]
    if kind == "update_artifact" and intent.target:
        return [d for d in deliverables if d.get("deliverable_id") == intent.target]
    if kind in ("keep_modularity", "halt_physical_manufacturing"):
        return []
    return [d for d in deliverables if _in_scope(d)]


def _is_reversible(intent: Intent) -> bool:
    """可撤销操作：返回 True；不可逆的方向性/制造决定返回 False。"""
    if intent.kind in ("approve", "choose", "halt_physical_manufacturing"):
        return False
    return True


def _requires_approval(intent: Intent) -> bool:
    """必要时批准：批准/选择方案、暂不进入实体制造等方向性操作需显式批准。"""
    if intent.kind in ("approve", "choose", "halt_physical_manufacturing"):
        return True
    return False


def _why_need_decide(intent: Intent) -> str:
    if intent.kind == "halt_physical_manufacturing":
        return ("是否进入实体制造会直接影响供应链排产与验证投入，"
                "属于不可逆的外部投入决定，需要您明确确认。")
    if intent.kind in ("approve", "choose"):
        return ("该操作会采纳一个具体方案并据此推进，属于项目方向性决定，"
                "需要您确认后再执行。")
    return ""


def estimate_cost_time(intent: Intent,
                       affected: List[Dict[str, Any]]) -> Dict[str, Any]:
    """确定性估算影响范围、耗时与成本。"""
    n = len(affected)
    if intent.kind in ("approve", "choose"):
        minutes = _BASE_MINUTES
    elif intent.kind in ("keep_modularity", "halt_physical_manufacturing"):
        minutes = 2
    else:
        minutes = _BASE_MINUTES + n * _MINUTES_PER_ARTIFACT
    cost = n * _COST_PER_ARTIFACT
    return {
        "affected_count": n,
        "estimated_minutes": minutes,
        "estimated_cost": round(cost, 2),
        "human_estimate": (
            f"预计影响 {n} 项产物，耗时约 {minutes} 分钟；"
            f"估算成本约 {cost:.0f} 元（AI 估算，非真实计费）。"),
    }


def build_preview(db: AIPDStateDB, project_id: str,
                  affected: List[Dict[str, Any]],
                  tenant_id: str) -> Dict[str, Any]:
    """生成受影响制品的 before/after 可撤销预览。"""
    before: List[Dict[str, Any]] = []
    for d in affected:
        before.append({
            "deliverable_id": d.get("deliverable_id"),
            "type_cn": type_cn(d.get("type")),
            "status": d.get("status"),
            "version": d.get("version"),
        })
    after = []
    for b in before:
        entry = dict(b)
        entry["status"] = "in_progress"  # 返工后进入推进
        after.append(entry)
    return {"before": before, "after": after}


def analyze_impact(db: AIPDStateDB, project_id: str, intent: Intent,
                   tenant_id: str = "default") -> Dict[str, Any]:
    """返回完整的确定性影响分析报告。"""
    affected = _affected_for_kind(db, project_id, intent, tenant_id)
    estimate = estimate_cost_time(intent, affected)
    reversible = _is_reversible(intent)
    requires_approval = _requires_approval(intent)

    result: Dict[str, Any] = {
        "kind": intent.kind,
        "affected_artifacts": affected,
        "affected_count": estimate["affected_count"],
        "estimated_minutes": estimate["estimated_minutes"],
        "estimated_cost": estimate["estimated_cost"],
        "human_estimate": estimate["human_estimate"],
        "reversible": reversible,
        "requires_approval": requires_approval,
        "why_need_decide": _why_need_decide(intent),
        "preview": build_preview(db, project_id, affected, tenant_id),
        "propagated_impact": list(intent.propagated_impact),
    }
    if intent.ambiguous:
        result["ambiguous"] = True
        result["clarifying_question"] = intent.clarifying_question
    return result


__all__ = ["analyze_impact", "estimate_cost_time", "type_cn", "milestone_cn"]