"""项目摘要：面向产品所有者的纯自然语言视图。

把状态库里的 facts / decisions / deliverables / risks / checkpoints 汇总成
产品所有者无需理解任何内部代号（gate / manifest / 数据库表）就能读懂的表述。
内部代号只出现在 ``details`` 子字典里。
"""
from __future__ import annotations

from typing import Any

from ..state.checkpoint import CheckpointManager
from ..state.db import AIPDStateDB

# gate 代号 → 人类可读里程碑名称（仅用于 details 之后的展示，不暴露给顶层字段）
GATE_NAMES: dict[str, str] = {
    "G0": "项目启动与概念验证",
    "G1": "需求与规格冻结",
    "G2": "方案选型与架构定稿",
    "G3": "详细设计与关键接口冻结",
    "G4": "样机与早期试制",
    "G5": "工程验证",
    "G6": "设计验证",
    "G7": "生产验证",
    "G8": "量产准备",
    "G9": "正式发布",
}

_DONE_STATUSES = {"done", "completed", "released"}
_WORK_STATUSES = {"planned", "in_progress", "in_progressing"}

# 交付物类型代号 → 中文（不把 manual/cad/bom 等内部代号泄露给所有者）
_TYPE_CN = {
    "manual": "使用手册", "cad": "CAD 图纸", "bom": "物料清单",
    "drawing": "工程图纸", "page": "页面", "marketing": "营销物料",
    "spec": "规格书", "test_report": "测试报告",
}

# 影响级别代号 → 中文
_SEVERITY_CN = {"critical": "严重", "high": "高", "medium": "中", "low": "低"}


def _type_cn(t: str | None) -> str:
    return _TYPE_CN.get((t or "").lower(), t or "")


def _severity_cn(s: str | None) -> str:
    return _SEVERITY_CN.get(str(s or "").lower(), s or "")


def _milestone(gate: str | None) -> str:
    return GATE_NAMES.get(gate or "", "后续阶段")


def _current_work(project: dict[str, Any], deliverables: list[dict[str, Any]],
                  open_decisions: list[dict[str, Any]], resume: dict[str, Any]) -> str:
    if open_decisions:
        topic = open_decisions[0]["topic"]
        return f"正在等待您的决策：{topic}。批准后系统会自动继续推进。"
    working = [d for d in deliverables if d.get("status") in _WORK_STATUSES]
    if working:
        names = "、".join(_type_cn(d["type"]) for d in working[:5])
        return f"正在推进：{names}（{_milestone(project.get('gate'))}）。"
    return f"按当前计划推进下一阶段：{_milestone(project.get('gate'))}。"


def _completed(decisions: list[dict[str, Any]], deliverables: list[dict[str, Any]],
               facts: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    done = [d for d in deliverables if d.get("status") in _DONE_STATUSES]
    if done:
        parts.append("已完成交付：" + "、".join(_type_cn(d["type"]) for d in done[:5]))
    if decisions:
        parts.append("已做决策：" + "；".join(
            f"{d['topic']}（选择{d.get('choice') or '推荐方案'}）" for d in decisions[:5]))
    verified = [f for f in facts if f.get("status") == "V"]
    if verified:
        parts.append("已验证关键参数：" + "、".join(f["key"] for f in verified[:5]))
    return "；".join(parts) if parts else "暂无已完成的里程碑。"


def _gaps(deliverables: list[dict[str, Any]], resume: dict[str, Any]) -> str:
    parts: list[str] = []
    pending = [d for d in deliverables if d.get("status") in _WORK_STATUSES]
    if pending:
        parts.append("待完成：" + "、".join(_type_cn(d["type"]) for d in pending[:5]))
    stale = [a for a in resume.get("stale_artifacts", [])]
    if stale:
        parts.append(f"有 {len(stale)} 项产物已过期需重做："
                     + "、".join(_type_cn(a["type"]) for a in stale[:5]))
    ext = resume.get("external_waiting", [])
    if ext:
        parts.append("仍有外部等待事项未闭环")
    return "；".join(parts) if parts else "没有明显的缺口，可继续推进。"


def _top_risk(risks: list[dict[str, Any]]) -> str:
    if not risks:
        return "暂无显著风险。"
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    ranked = sorted(risks, key=lambda r: order.get(str(r.get("impact")).lower(), 4))
    r = ranked[0]
    base = f"最大风险：{r['title']}"
    if r.get("impact"):
        base += f"（影响级别：{_severity_cn(r['impact'])}）"
    if r.get("mitigation"):
        base += f"；缓解措施：{r['mitigation']}"
    return base


def _next_milestone(project: dict[str, Any]) -> str:
    if project.get("status") == "released":
        return "已正式发布，进入量产与运维阶段。"
    gate = project.get("gate")
    return f"下一个里程碑：{_milestone(gate)}（当前所处阶段）。"


def build_project_summary(db: AIPDStateDB, project_id: str,
                          tenant_id: str = "default") -> dict[str, Any]:
    """返回纯自然语言的项目摘要。

    - current_work / completed / gaps / top_risk / next_milestone 均为中文自然语言；
    - 内部代号（gate / status / id）只放在 ``details`` 子字典。
    """
    project = db.get_project(tenant_id, project_id)
    facts = db.list_facts(tenant_id, project_id)
    deliverables = db.list_deliverables(tenant_id, project_id)
    decisions = db.list_resolved_decisions(tenant_id, project_id)
    open_decisions = db.list_open_decisions(tenant_id, project_id)
    risks = db.list_risks(tenant_id, project_id)
    resume = CheckpointManager(db).resume_summary(project_id, tenant_id)

    return {
        "current_work": _current_work(project, deliverables, open_decisions, resume),
        "completed": _completed(decisions, deliverables, facts),
        "gaps": _gaps(deliverables, resume),
        "top_risk": _top_risk(risks),
        "next_milestone": _next_milestone(project),
        "details": {
            "project_id": project_id,
            "tenant_id": tenant_id,
            "name": project.get("name"),
            "goal": project.get("goal"),
            "gate": project.get("gate"),
            "status": project.get("status"),
            "version": project.get("version"),
            "counts": {
                "facts": len(facts),
                "deliverables": len(deliverables),
                "open_decisions": len(open_decisions),
                "resolved_decisions": len(decisions),
                "open_risks": len([r for r in risks if r.get("status") == "open"]),
            },
        },
    }


__all__ = ["GATE_NAMES", "build_project_summary"]
