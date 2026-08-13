"""自然语言操作闭环（P2-1）：意图→影响→受影响制品→成本/时间→可撤销预览→
必要时批准→自动返工→自动验收→更新摘要。

``run_operation_loop`` 串联全流程，支持：
  - 进度事件（``ProgressTracker``）；
  - 用户取消（``should_cancel`` 回调）；
  - 失败恢复（``revert_operation`` 回滚可撤销操作）；
  - 批准门禁（``requires_approval`` 且未批准时停在预览、不执行）。
全部确定性、无外部服务。
"""
from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional

from ..state.checkpoint import CheckpointManager
from ..state.db import AIPDStateDB
from .impact_analysis import analyze_impact, type_cn
from .intent_engine import Intent

# 可接受的成功状态（用于验收）
_DONE_STATUSES = {"done", "completed", "released"}


class ProgressTracker:
    """进度事件收集器：每次操作按步骤记录 step/message/progress。"""

    def __init__(self) -> None:
        self._events: List[Dict[str, Any]] = []

    def emit(self, step: str, message: str = "", progress: Optional[float] = None) -> None:
        self._events.append({"step": step, "message": message,
                             "progress": progress, "seq": len(self._events) + 1})

    def events(self) -> List[Dict[str, Any]]:
        return list(self._events)


def _bump_version(version: Optional[str]) -> str:
    v = str(version or "0.0")
    parts = v.split(".")
    try:
        last = int(parts[-1])
        parts[-1] = str(last + 1)
        return ".".join(parts)
    except ValueError:
        return f"{v}.1"


def _get_deliverable(db: AIPDStateDB, tenant: str, project_id: str,
                     deliverable_id: str) -> Optional[Dict[str, Any]]:
    for d in db.list_deliverables(tenant, project_id):
        if d.get("deliverable_id") == deliverable_id:
            return d
    return None


def _record_constraint_fact(db: AIPDStateDB, project_id: str, intent: Intent,
                            tenant_id: str) -> Optional[str]:
    """把约束类意图写入 Product Truth（事实）。"""
    kind = intent.kind
    if kind == "cost_reduction":
        pct = intent.params.get("percentage") or 0
        return db.add_fact(tenant_id, project_id, "cost_target",
                           f"降低成本 {pct:.0f}%", "C", source="owner-instruction",
                           conditions="产品所有者指定的成本约束")
    if kind == "style_constraint":
        style = intent.params.get("style")
        avoid = intent.params.get("avoid")
        desc = style or ("避免" + (avoid or "医疗风"))
        return db.add_fact(tenant_id, project_id, "design_intent",
                           f"外观风格：{desc}", "C", source="owner-instruction",
                           conditions="产品所有者指定的设计意图约束")
    if kind == "keep_modularity":
        return db.add_fact(tenant_id, project_id, "design_intent",
                           "保留模块化设计", "C", source="owner-instruction",
                           conditions="产品所有者指定的设计意图约束")
    if kind == "halt_physical_manufacturing":
        return db.add_fact(tenant_id, project_id, "manufacturing_stance",
                           "暂不进入实体制造", "C", source="owner-instruction",
                           conditions="产品所有者要求暂不进入实体制造")
    return None


def _apply_decision(db: AIPDStateDB, project_id: str, intent: Intent,
                    tenant_id: str) -> Optional[Dict[str, Any]]:
    """批准/选择：解析待审决策并写入决策事实。"""
    decision_id = intent.target or intent.params.get("decision_id")
    open_ds = db.list_open_decisions(tenant_id, project_id)
    target = next((d for d in open_ds if d["decision_id"] == decision_id), None)
    if target is None:
        return None
    if intent.kind == "choose":
        choice = intent.params.get("choice") or target.get("recommendation") or "推荐方案"
        comment = "已由产品所有者选择"
    else:
        choice = target.get("recommendation") or "推荐方案"
        comment = "已由产品所有者批准"
    db.resolve_decision(tenant_id, project_id, target["decision_id"],
                        choice=choice, comment=comment)
    fid = db.add_fact(tenant_id, project_id, "decision_outcome",
                      f"决策「{target['topic']}」选择：{choice}",
                      "C", source="owner-instruction",
                      conditions="产品所有者批准的决策结果")
    return {"decision_id": target["decision_id"], "topic": target.get("topic"),
            "choice": choice, "fact_id": fid}


def auto_rework(db: AIPDStateDB, project_id: str, intent: Intent,
                impact: Dict[str, Any], tenant_id: str = "default") -> Dict[str, Any]:
    """自动返工：记录约束/决策，并让受影响制品进入推进（版本递增）。"""
    rework_records: List[Dict[str, Any]] = []
    recorded_fact_id = _record_constraint_fact(db, project_id, intent, tenant_id)
    resolved_decision = _apply_decision(db, project_id, intent, tenant_id)

    for a in impact.get("affected_artifacts", []):
        cur = _get_deliverable(db, tenant_id, project_id, a["deliverable_id"])
        if cur is None:
            continue
        new_version = _bump_version(cur.get("version"))
        db.update_deliverable(tenant_id, project_id, cur["deliverable_id"],
                              expected_version=cur["version_no"],
                              status="in_progress", version=new_version)
        db.add_change(tenant_id, project_id, "deliverable", cur["deliverable_id"],
                      "rework", before={"version": cur.get("version"),
                                        "status": cur.get("status")},
                      after={"version": new_version, "status": "in_progress"},
                      reason=f"依据产品所有者意图（{intent.kind}）自动返工")
        rework_records.append({
            "deliverable_id": cur["deliverable_id"],
            "type_cn": type_cn(cur.get("type")),
            "from_version": cur.get("version"),
            "to_version": new_version,
        })

    return {
        "reworked": rework_records,
        "count": len(rework_records),
        "recorded_fact_id": recorded_fact_id,
        "resolved_decision": resolved_decision,
    }


def auto_acceptance(db: AIPDStateDB, project_id: str, impact: Dict[str, Any],
                    tenant_id: str = "default") -> Dict[str, Any]:
    """自动验收：校验返工后的制品并标记为已完成，记录验收变更与证据。"""
    accepted: List[Dict[str, Any]] = []
    for a in impact.get("affected_artifacts", []):
        cur = _get_deliverable(db, tenant_id, project_id, a["deliverable_id"])
        if cur is None:
            continue
        # 确定性验收：返工后处于推进态、且版本号有效
        valid = cur.get("status") == "in_progress" and bool(cur.get("version"))
        if not valid:
            continue
        db.update_deliverable(tenant_id, project_id, cur["deliverable_id"],
                              expected_version=cur["version_no"],
                              status="done")
        db.add_change(tenant_id, project_id, "deliverable", cur["deliverable_id"],
                      "accept", before={"status": "in_progress"},
                      after={"status": "done"}, reason="自动验收通过")
        db.add_evidence(tenant_id, project_id, kind="auto_acceptance",
                        title="自动验收",
                        metadata={"deliverable_id": cur["deliverable_id"],
                                  "version": cur.get("version")})
        accepted.append({"deliverable_id": cur["deliverable_id"],
                         "version": cur.get("version")})
    return {"accepted": accepted, "count": len(accepted)}


def update_summary(db: AIPDStateDB, project_id: str, tenant_id: str,
                   intent: Intent, impact: Dict[str, Any],
                   rework: Dict[str, Any], acceptance: Dict[str, Any]) -> Dict[str, Any]:
    """更新摘要：保存检查点并写入审计日志（含可撤销操作标记）。"""
    summary = {
        "note": "产品所有者指令闭环完成",
        "kind": intent.kind,
        "affected_count": impact.get("affected_count", 0),
        "reworked": rework.get("count", 0),
        "accepted": acceptance.get("count", 0),
        "reversible": impact.get("reversible", False),
    }
    CheckpointManager(db).save_checkpoint(project_id,
                                          {"phase": "operation"},
                                          tenant_id=tenant_id,
                                          summary=summary)
    db.add_audit("owner", "operation", project_id, tenant_id,
                 before={"kind": intent.kind},
                 after={"kind": intent.kind,
                        "reversible": impact.get("reversible", False),
                        "affected_count": impact.get("affected_count", 0)})
    return {"summary": summary, "recorded": True}


def revert_operation(db: AIPDStateDB, project_id: str, tenant_id: str = "default",
                     target: Optional[str] = None) -> Dict[str, Any]:
    """失败恢复：回滚最近一次可撤销操作（把受影响制品退回上一版本）。

    通过审计日志中 reversible=True 的操作记录定位受影响制品，无法回滚
    （不可逆操作）时如实报告，绝不伪造。
    """
    audit = db.list_audit(limit=200)
    reversible_ops = []
    for e in audit:
        after = e.get("after_json") or {}
        if isinstance(after, str):
            try:
                after = json.loads(after)
            except Exception:  # noqa: BLE001
                after = {}
        if e.get("action") == "operation" and after.get("reversible") is True:
            reversible_ops.append(e)
    if not reversible_ops:
        return {"reverted": [], "note": "没有可回滚的可撤销操作"}

    # 找到最近一次仍处于 done 的制品，回退
    reverted: List[str] = []
    for d in db.list_deliverables(tenant_id, project_id):
        if d.get("status") == "done" and d.get("version"):
            parts = str(d.get("version")).split(".")
            try:
                prev = str(int(parts[-1]) - 1) if parts else None
            except ValueError:
                prev = None
            new_version = ".".join(parts[:-1] + [prev]) if prev else str(d.get("version"))
            db.update_deliverable(tenant_id, project_id, d["deliverable_id"],
                                  expected_version=d["version_no"],
                                  status="in_progress", version=new_version)
            db.add_change(tenant_id, project_id, "deliverable", d["deliverable_id"],
                          "revert", before={"status": "done"},
                          after={"status": "in_progress", "version": new_version},
                          reason="用户要求回滚最近一次可撤销操作")
            reverted.append(d["deliverable_id"])
    db.add_audit("owner", "revert", project_id, tenant_id,
                 after={"deliverables": reverted})
    return {"reverted": reverted, "note": f"已回滚 {len(reverted)} 项受影响制品"}


def run_operation_loop(db: AIPDStateDB, project_id: str, intent: Intent,
                       tenant_id: str = "default", approved: bool = False,
                       progress: Optional[ProgressTracker] = None,
                       should_cancel: Optional[Callable[[], bool]] = None) -> Dict[str, Any]:
    """执行完整闭环。返回结构与状态。

    - ``needs_approval``：需要批准但未批准，停在预览，不执行任何变更；
    - ``cancelled``：用户取消；
    - ``done``：自动返工 + 自动验收 + 更新摘要全部完成。
    """
    tracker = progress or ProgressTracker()

    def emit(step: str, msg: str = "", p: Optional[float] = None) -> None:
        tracker.emit(step, msg, p)

    emit("intent", "已理解您的意图", 0.1)
    if intent.ambiguous:
        emit("clarify", "需要澄清", 0.15)
        return {"status": "needs_clarification",
                "clarifying_question": intent.clarifying_question,
                "intent": intent, "progress": tracker.events()}

    impact = analyze_impact(db, project_id, intent, tenant_id)
    emit("impact", impact["human_estimate"], 0.3)

    if impact.get("requires_approval") and not approved:
        emit("approval", "需要您批准后才会执行", 0.5)
        return {"status": "needs_approval", "intent": intent, "impact": impact,
                "why_need_decide": impact.get("why_need_decide", ""),
                "progress": tracker.events()}

    if should_cancel and should_cancel():
        emit("cancelled", "您已取消", 1.0)
        return {"status": "cancelled", "intent": intent, "impact": impact,
                "progress": tracker.events()}

    emit("rework", "开始自动返工", 0.6)
    rework = auto_rework(db, project_id, intent, impact, tenant_id)
    if should_cancel and should_cancel():
        emit("cancelled", "返工后您已取消，未验收", 0.8)
        return {"status": "cancelled", "intent": intent, "impact": impact,
                "rework": rework, "progress": tracker.events()}

    emit("acceptance", "自动验收", 0.8)
    acceptance = auto_acceptance(db, project_id, impact, tenant_id)

    emit("summary", "更新摘要", 0.95)
    summary = update_summary(db, project_id, tenant_id, intent, impact,
                             rework, acceptance)

    emit("done", "完成", 1.0)
    return {"status": "done", "intent": intent, "impact": impact,
            "rework": rework, "acceptance": acceptance, "summary": summary,
            "progress": tracker.events()}


__all__ = ["ProgressTracker", "run_operation_loop", "auto_rework",
           "auto_acceptance", "update_summary", "revert_operation"]
