"""统一 Owner Dashboard / CLI 输出（P2-2）。

默认展示只含 10 个面向产品所有者的自然语言区块，永不暴露内部代号
（gate / manifest / 制品 ID / 决策 ID / maturity 代号 / checkpoint / work item），
这些只放在 ``details``（内部技术细节）里，需显式查看。

- ``--json`` 与人类可读模式完全分离；
- 紧凑移动端输出（``compact``，窄屏友好、无装饰字符）；
- 制品 before/after 差异、成本&耗时变化；
- 进度事件、可取消、失败恢复命令、唯一待决定、"为什么需要您决定"。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..state.checkpoint import CheckpointManager
from ..state.db import AIPDStateDB
from .artifact_preview import artifact_preview
from .decision_card import build_decision_card
from .external_wait import summarize_external_wait
from .impact_analysis import milestone_cn
from .project_summary import build_project_summary
from .risk_health import compute_risk_health

# 变更动作 → 中文
_ACTION_CN = {
    "create": "新增", "update": "更新", "rework": "返工", "accept": "验收通过",
    "revert": "回滚", "delete": "删除",
}
_OBJECT_CN = {
    "deliverable": "制品", "fact": "参数/事实", "decision": "决策", "risk": "风险",
}
_HEALTH_LABEL = {"green": "🟢 良好", "yellow": "🟡 需关注", "red": "🔴 高风险"}


def _impact_cn(v: Any) -> str:
    return {"high": "高", "medium": "中", "low": "低", "none": "无"}.get(str(v).lower(), str(v))


def _recent_changes(db: AIPDStateDB, project_id: str, tenant_id: str,
                    limit: int = 5) -> List[str]:
    """把最近变更渲染成中文（不暴露内部 object_id / 代号）。"""
    changes = db.list_changes(tenant_id, project_id)
    out: List[str] = []
    for ch in reversed(changes[-limit:]):
        action = _ACTION_CN.get(ch.get("action", ""), ch.get("action", ""))
        obj = _OBJECT_CN.get(ch.get("object_type", ""), ch.get("object_type", ""))
        reason = (ch.get("reason") or "").strip()
        line = f"{action}了一项{obj}"
        if reason:
            line += f"（{reason}）"
        out.append(line)
    return out or ["暂无变更记录。"]


def _reversible_operations(db: AIPDStateDB, project_id: str,
                           tenant_id: str) -> List[Dict[str, Any]]:
    """从审计日志识别可撤销操作（reversible=True 的 operation）。"""
    ops: List[Dict[str, Any]] = []
    for e in db.list_audit(limit=200):
        if e.get("action") != "operation" or e.get("project_id") != project_id:
            continue
        after = e.get("after_json") or {}
        if isinstance(after, str):
            try:
                after = json.loads(after)
            except Exception:  # noqa: BLE001
                after = {}
        if after.get("reversible") is True:
            ops.append({
                "kind": after.get("kind"),
                "affected_count": after.get("affected_count", 0),
                "at": e.get("timestamp"),
            })
    return ops


def build_dashboard(db: AIPDStateDB, project_id: str,
                    tenant_id: str = "default") -> Dict[str, Any]:
    """构建统一 Owner Dashboard（10 个所有者区块 + details 内部细节）。"""
    ps = build_project_summary(db, project_id, tenant_id)
    card = build_decision_card(db, project_id, tenant_id=tenant_id)
    changes = _recent_changes(db, project_id, tenant_id)
    reversible = _reversible_operations(db, project_id, tenant_id)
    risks = db.list_risks(tenant_id, project_id)
    external = summarize_external_wait(
        CheckpointManager(db).resume_summary(project_id, tenant_id)["external_waiting"])
    project = db.get_project(tenant_id, project_id)
    ap = artifact_preview(db, project_id, tenant_id)

    single_decision: Optional[Dict[str, Any]] = None
    if card is not None:
        single_decision = {
            "topic": card["topic"],
            "ai_recommendation": card["ai_recommendation"],
            "options": card["options"],
            "impacts": card["impacts"],
            "after_approval": card["after_approval"],
            "why_need_decide": ("该决策会确定项目后续方向，需要您确认后再推进。"),
        }

    return {
        "current_goal": project.get("goal"),
        "executing": ps.get("current_work"),
        "done": ps.get("completed"),
        "missing": ps.get("gaps"),
        "top_risk": ps.get("top_risk"),
        "next_milestone": ps.get("next_milestone"),
        "external_waits": external.get("summary", "无外部等待事项"),
        "single_decision": single_decision,
        "recent_changes": changes,
        "reversible_operations": reversible,

        # 增值区块（仍在所有者视角，不暴露内部代号）
        "health": _HEALTH_LABEL.get(
            compute_risk_health(risks, [], project.get("status"))["traffic_light"],
            "🟢 良好"),
        "artifact_versions": _artifact_versions(ap),

        # 内部技术细节（默认隐藏）
        "details": {
            "project_id": project_id,
            "project_name": project.get("name"),
            "gate": milestone_cn(project.get("gate")),
            "status": project.get("status"),
            "counts": ps.get("details", {}).get("counts", {}),
            "decision_id": (card or {}).get("decision_id"),
            "deliverable_count": ap.get("details", {}).get("deliverable_count", 0),
        },
    }


def _artifact_versions(ap: Dict[str, Any]) -> List[str]:
    """把 CAD 版本差异渲染成中文（before/after 差异）。"""
    out: List[str] = []
    for c in ap.get("cad_versions", []) or []:
        if "from_version" in c and "to_version" in c:
            line = f"CAD 版本 {c.get('from_version')} → {c.get('to_version')}"
            if c.get("reason"):
                line += f"（{c['reason']}）"
            out.append(line)
    for p in ap.get("parameter_diffs", []) or []:
        name = p.get("key") or p.get("parameter") or ""
        out.append(f"参数 {name}：{p.get('from', '-')} → {p.get('to', '-')}")
    return out or ["暂无制品版本/参数差异。"]


def render_dashboard_text(view: Dict[str, Any],
                          compact: bool = False) -> str:
    """把 Dashboard 渲染为人类可读文本。compact 为窄屏/移动端友好输出。"""
    lines: List[str] = []
    if compact:
        # 紧凑模式：每区块一行，无装饰字符，窄终端友好
        dec = view.get("single_decision")
        lines.append(f"目标：{view['current_goal']}")
        lines.append(f"执行中：{view['executing']}")
        lines.append(f"已完成：{view['done']}")
        lines.append(f"缺口：{view['missing']}")
        lines.append(f"风险：{view['top_risk']}")
        lines.append(f"外部等待：{view['external_waits']}")
        if dec:
            lines.append(f"待您决定：{dec['topic']}")
            lines.append(f"为什么需要决定：{dec['why_need_decide']}")
        else:
            lines.append("待您决定：无")
        lines.append(f"里程碑：{view['next_milestone']}")
        lines.append("最近变化：" + "；".join(view['recent_changes']))
        lines.append("可撤销操作：" + (
            "、".join(f"{op['kind']}({op['affected_count']}项)" for op in view['reversible_operations'])
            or "无"))
        lines.append(f"健康：{view['health']}")
        return "\n".join(lines)

    # 完整人类可读模式
    lines.append("AIPD 项目总览")
    lines.append(f"当前目标：{view['current_goal']}")
    lines.append("")
    lines.append(f"正在执行：{view['executing']}")
    lines.append("")
    lines.append(f"已完成：{view['done']}")
    lines.append("")
    lines.append(f"还缺什么：{view['missing']}")
    lines.append("")
    lines.append(f"最大风险：{view['top_risk']}")
    lines.append("")
    lines.append(f"外部等待：{view['external_waits']}")
    lines.append("")
    dec = view.get("single_decision")
    if dec:
        lines.append("唯一需要您决定的事项：")
        lines.append(f"  {dec['topic']}")
        lines.append(f"  AI 建议：{dec['ai_recommendation']}")
        lines.append("  可选方案及其影响：")
        for opt in dec["options"]:
            imp = dec.get("impacts", {}).get(opt, {})
            lines.append(
                f"    - {opt}（成本:{_impact_cn(imp.get('cost', '-'))}"
                f" / 性能:{_impact_cn(imp.get('performance', '-'))}"
                f" / 时间:{_impact_cn(imp.get('time', '-'))}"
                f" / 安全:{_impact_cn(imp.get('safety', '-'))}）")
        lines.append(f"  为什么需要您决定：{dec['why_need_decide']}")
        lines.append(f"  批准后系统将自动执行：{dec['after_approval']}")
    else:
        lines.append("唯一需要您决定的事项：无")
    lines.append("")
    lines.append(f"下一里程碑：{view['next_milestone']}")
    lines.append("")
    lines.append("最近变化：")
    for c in view["recent_changes"]:
        lines.append(f"  - {c}")
    lines.append("")
    lines.append("制品版本 / 参数差异：")
    for v in view.get("artifact_versions", []):
        lines.append(f"  - {v}")
    lines.append("")
    if view.get("reversible_operations"):
        lines.append("可撤销操作（可用 `aipd recover --db ...` 回滚）：")
        for op in view["reversible_operations"]:
            lines.append(f"  - {op['kind']}（影响 {op['affected_count']} 项）")
    else:
        lines.append("可撤销操作：无")
    lines.append("")
    lines.append(f"健康状态：{view['health']}")
    lines.append("")
    lines.append("---")
    lines.append("<details><summary>内部代号 / 技术细节</summary>")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(view["details"], ensure_ascii=False, indent=2, default=str))
    lines.append("```")
    lines.append("</details>")
    return "\n".join(lines)


def render_dashboard_json(view: Dict[str, Any]) -> str:
    """--json 模式：返回纯 JSON，与人类可读模式完全分离（含内部细节）。"""
    return json.dumps(view, ensure_ascii=False, default=str)


__all__ = ["build_dashboard", "render_dashboard_text", "render_dashboard_json"]
