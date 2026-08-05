"""自然语言指令解析与应用。

面向产品所有者的指令解析器：识别
  - "批准"（批准下一个待审决策）
  - "成本/价钱再降低 X%"（成本削减目标）
  - "外观更工业化"（更工业化的设计意图）
  - "不要医疗风"（避免某种风格）
  - "@artifact"（引用具体制品）

返回结构化 :class:`Instruction`；``apply_instruction`` 负责把影响传播到状态库
（记录约束 / 标记相关产物过期）。**不会真正重新生成制品**。
仅做关键词（中文）+ 简单正则匹配，不依赖任何 LLM。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..state.db import AIPDStateDB


_APPROVE_RE = re.compile(r"批准|同意|approve|确认执行", re.IGNORECASE)
_COST_RE = re.compile(r"(?:成本|价钱|价格|价位|售价)[^0-9]*(\d+(?:\.\d+)?)\s*%")
_INDUSTRIAL_RE = re.compile(r"工业化|更工业|工业风")
_MEDICAL_RE = re.compile(r"不要医疗|避免医疗|不要医疗风|医疗风|医疗器械风")
_ARTIFACT_RE = re.compile(r"@([\w\-\./\\]+)")


@dataclass
class Instruction:
    """结构化指令。``propagated_impact`` 为采纳后预计影响的中文描述。"""
    kind: str
    target: Optional[str] = None
    params: Dict[str, Any] = field(default_factory=dict)
    propagated_impact: List[str] = field(default_factory=list)


def _prev_approved(decision: Dict[str, Any]) -> str:
    return decision.get("recommendation") or "推荐方案"


def _next_open_decision(db: AIPDStateDB, project_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
    open_ds = db.list_open_decisions(tenant_id, project_id)
    return open_ds[0] if open_ds else None


def parse_instruction(text: str, db: AIPDStateDB, project_id: str,
                      tenant_id: str = "default") -> Instruction:
    """把一句自然语言解析成结构化指令。"""
    artifact_match = _ARTIFACT_RE.search(text)
    artifact = artifact_match.group(1) if artifact_match else None

    open_dec = _next_open_decision(db, project_id, tenant_id)

    # 1) 批准下一个待审决策
    if _APPROVE_RE.search(text):
        target = artifact or (open_dec["decision_id"] if open_dec else None)
        impact = []
        if open_dec:
            impact.append(f"执行决策「{open_dec['topic']}」的推荐方案（{_prev_approved(open_dec)}）")
        if artifact:
            impact.append(f"对制品 @{artifact} 应用批准动作")
        return Instruction(kind="approve", target=target,
                            params={"decision_id": target}, propagated_impact=impact)

    # 2) 成本 / 价钱削减
    cm = _COST_RE.search(text)
    if cm:
        pct = float(cm.group(1))
        target = artifact
        impact = [f"将成本目标降低 {pct:.0f}%，并据此更新预算/报价约束"]
        if artifact:
            impact.append(f"受影响的 @{artifact} 及其依赖产物需按新成本约束重做")
        return Instruction(kind="cost_reduction", target=target,
                            params={"metric": "cost", "percentage": pct},
                            propagated_impact=impact)

    # 3) 更工业化的外观风格
    if _INDUSTRIAL_RE.search(text):
        target = artifact
        impact = [f"记录设计意图：外观更工业化"]
        if artifact:
            impact.append(f"@{artifact} 相关外观/手册类页面标记为过期")
        return Instruction(kind="style_constraint", target=target,
                            params={"style": "industrial", "avoid": None},
                            propagated_impact=impact)

    # 4) 避免医疗风格
    if _MEDICAL_RE.search(text):
        target = artifact
        impact = [f"记录设计意图：避免医疗风外观"]
        if artifact:
            impact.append(f"@{artifact} 相关外观/手册类页面标记为过期")
        return Instruction(kind="style_constraint", target=target,
                            params={"style": None, "avoid": "medical"},
                            propagated_impact=impact)

    # 未识别 → 通用指令
    impact = []
    if artifact:
        impact.append(f"更新制品 @{artifact}")
    return Instruction(kind="unknown", target=artifact,
                        params={"raw": text}, propagated_impact=impact)


def _deliverable_version(db: AIPDStateDB, tenant_id: str, project_id: str,
                         deliverable_id: str) -> Optional[Dict[str, Any]]:
    for d in db.list_deliverables(tenant_id, project_id):
        if d["deliverable_id"] == deliverable_id:
            return d
    return None


def _mark_stale(db: AIPDStateDB, tenant_id: str, project_id: str,
                predicate=None) -> List[str]:
    """把符合条件的交付物标记为过期（stale），返回被标记的 deliverable_id 列表。"""
    marked: List[str] = []
    for d in db.list_deliverables(tenant_id, project_id):
        if d.get("status") in ("released", "archived"):
            continue
        if predicate is not None and not predicate(d):
            continue
        cur = _deliverable_version(db, tenant_id, project_id, d["deliverable_id"])
        if cur is None:
            continue
        db.update_deliverable(tenant_id, project_id, d["deliverable_id"],
                              expected_version=cur["version_no"], status="stale")
        marked.append(d["deliverable_id"])
    return marked


def apply_instruction(instruction: Instruction, db: AIPDStateDB, project_id: str,
                      tenant_id: str = "default") -> Dict[str, Any]:
    """把指令传播到状态库：记录约束/决策，并标记依赖产物过期。不真正重生成制品。"""
    kind = instruction.kind
    result: Dict[str, Any] = {
        "kind": kind,
        "target": instruction.target,
        "params": instruction.params,
        "applied": True,
        "recorded_fact_id": None,
        "resolved_decision_id": None,
        "stale_deliverables": [],
        "propagated_impact": list(instruction.propagated_impact),
    }

    if kind == "approve":
        decision_id = instruction.target or instruction.params.get("decision_id")
        open_ds = db.list_open_decisions(tenant_id, project_id)
        target_dec = next((d for d in open_ds if d["decision_id"] == decision_id), None)
        if target_dec is not None:
            choice = _prev_approved(target_dec)
            db.resolve_decision(tenant_id, project_id, target_dec["decision_id"],
                                choice=choice, comment="已由产品所有者批准")
            result["resolved_decision_id"] = target_dec["decision_id"]
            result["propagated_impact"].append(
                f"决策「{target_dec['topic']}」已批准，采用推荐方案：{choice}")
        else:
            result["propagated_impact"].append("当前没有待批准的决策")
        return result

    if kind == "cost_reduction":
        pct = instruction.params.get("percentage", 0)
        fid = db.add_fact(tenant_id, project_id,
                          key="cost_target", value=f"降低成本 {pct:.0f}%",
                          status="C", source="owner-instruction",
                          conditions="产品所有者指定的成本约束")
        result["recorded_fact_id"] = fid
        marked = _mark_stale(db, tenant_id, project_id)
        result["stale_deliverables"] = marked
        result["propagated_impact"].append(
            f"已记录成本约束（降低 {pct:.0f}%），{len(marked)} 项未发布产物标记为过期待重做")
        return result

    if kind == "style_constraint":
        style = instruction.params.get("style")
        avoid = instruction.params.get("avoid")
        desc = style or ("避免" + (avoid or ""))
        fid = db.add_fact(tenant_id, project_id,
                          key="design_intent", value=f"外观风格：{desc}",
                          status="C", source="owner-instruction",
                          conditions="产品所有者指定的设计意图约束")
        result["recorded_fact_id"] = fid
        marked = _mark_stale(
            db, tenant_id, project_id,
            predicate=lambda d: "manual" in (d.get("type") or "").lower()
            or "page" in (d.get("type") or "").lower()
            or "外观" in (d.get("type") or ""))
        result["stale_deliverables"] = marked
        result["propagated_impact"].append(
            f"已记录设计意图约束（{desc}），{len(marked)} 项外观/手册类产物标记为过期")
        return result

    # unknown
    if instruction.target:
        marked = _mark_stale(db, tenant_id, project_id,
                             predicate=lambda d: d.get("deliverable_id") == instruction.target)
        result["stale_deliverables"] = marked
    return result


__all__ = ["Instruction", "parse_instruction", "apply_instruction"]
