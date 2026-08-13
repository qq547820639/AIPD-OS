"""顶层所有者视图：把各 experience 模块组合成一个统一的自然语言更新。

``OwnerView.owner_update`` 返回项目摘要 + 单一决策卡片 + 会话恢复摘要 + 制品预览；
``to_markdown`` 渲染成面向产品所有者的可读 Markdown，内部代号只放在可折叠的
``<details>`` 区块里。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..state.checkpoint import CheckpointManager
from ..state.db import AIPDStateDB
from .artifact_preview import artifact_preview
from .decision_card import build_decision_card
from .external_wait import summarize_external_wait
from .project_summary import build_project_summary
from .resume_summary import build_resume_summary
from .risk_health import compute_risk_health

# 健康灯 → 带图标的彩色标签
_HEALTH_LABEL = {"green": "🟢 良好", "yellow": "🟡 需关注", "red": "🔴 高风险"}
_WAIT_BUCKET_CN = {"supplier": "供应商", "lab": "测试实验室", "other": "其他"}

# 影响档位代号 → 中文（不在正文暴露 medium/high 等英文）
_IMPACT_CN = {"high": "高", "medium": "中", "low": "低", "none": "无"}


def _impact_cn(v: Any) -> str:
    return _IMPACT_CN.get(str(v).lower(), str(v))


def _where_left_off_cn(rs: Dict[str, Any]) -> str:
    """把“上次进行到哪”渲染成干净中文，避免泄漏 Python dict 的 repr。"""
    wlo = rs.get("where_left_off", "")
    if isinstance(wlo, dict):
        note = wlo.get("note") or wlo.get("summary") or ""
        at = wlo.get("at") or wlo.get("created_at")
        if note and at:
            return f"{note}（记录于 {at}）"
        if note:
            return str(note)
        if at:
            return f"上次记录于 {at}"
        return "没有历史检查点，从当前阶段开始"
    return str(wlo) if wlo else "没有历史检查点，从当前阶段开始"


def _next_action_cn(rs: Dict[str, Any]) -> str:
    """把英文内部动作描述（如 resolve proposed decisions）翻成中文。"""
    na = rs.get("next_action", "") or ""
    if isinstance(na, str):
        if na.startswith("resolve proposed decisions: "):
            return "处理待审决策：" + na[len("resolve proposed decisions: "):]
        if na.startswith("continue phase "):
            return "继续推进当前阶段：" + na[len("continue phase "):]
    return str(na)


def _artifact_diff_section(ap: Dict[str, Any]) -> str:
    """把制品版本/参数差异渲染成中文正文（数据存在才展示）。"""
    lines: List[str] = []
    cad = ap.get("cad_versions") or []
    if cad:
        lines.append("CAD 版本差异：")
        for c in cad:
            if "from_version" in c and "to_version" in c:
                line = f"- CAD 版本：{c.get('from_version') or '?'} → {c.get('to_version') or '?'}"
                if c.get("reason"):
                    line += f"（原因：{c['reason']}）"
                lines.append(line)
            else:
                lines.append(f"- CAD 当前版本：{c.get('version') or '-'}")
    params = ap.get("parameter_diffs") or []
    if params:
        lines.append("关键参数变化：")
        for p in params:
            name = p.get("key") or p.get("parameter") or ""
            lines.append(f"- {name}：{p.get('from', '-')} → {p.get('to', '-')}")
    if not lines:
        return "当前没有已记录的制品版本/参数差异。"
    return "\n".join(lines)


def _build_risk_and_wait(db, tenant: str, project_id: str) -> Dict[str, Any]:
    """读取风险、外部等待项与项目状态，构建风险健康 + 外部等待视图。"""
    risks = db.list_risks(tenant, project_id)
    external_waiting = CheckpointManager(db).resume_summary(project_id, tenant)["external_waiting"]
    project_status = db.get_project(tenant, project_id).get("status")
    return {
        "risk_health": compute_risk_health(risks, external_waiting, project_status),
        "external_wait": summarize_external_wait(external_waiting),
    }


def _health_section(rh: Dict[str, Any]) -> str:
    """渲染风险健康状态的 Markdown 段落（不暴露内部代号）。"""
    light = rh.get("traffic_light", "green")
    label = _HEALTH_LABEL.get(light, "🟢 良好")
    reason = rh.get("reason", "")
    return f"{label}" + (f" — {reason}" if reason else "")


def _wait_section(ew: Dict[str, Any]) -> str:
    """渲染外部等待事项的 Markdown 段落（不暴露内部代号）。"""
    if not ew.get("count", 0):
        return "项目当前无外部等待事项。"
    lines = [ew.get("summary", "")]
    for bucket in ("supplier", "lab", "other"):
        items = ew.get(bucket, [])
        if not items:
            continue
        lines.append(f"- {_WAIT_BUCKET_CN[bucket]}：")
        for line in items:
            lines.append(f"  - {line}")
    return "\n".join(lines)


def render_markdown(view: Dict[str, Any]) -> str:
    """把一个 owner_update 视图渲染成人类友好的 Markdown。"""
    ps = view.get("project_summary", {})
    name = (ps.get("details") or {}).get("name") or "项目"
    rs = view.get("resume_summary", {})

    lines = [
        f"# {name} — 产品所有者视图",
        "",
        "## 正在做什么",
        ps.get("current_work", ""),
        "",
        "## 已完成",
        ps.get("completed", ""),
        "",
        "## 还缺什么",
        ps.get("gaps", ""),
        "",
        "## 最大风险",
        ps.get("top_risk", ""),
        "",
        "## 下一个里程碑",
        ps.get("next_milestone", ""),
        "",
        "## 风险健康状态",
        _health_section(view.get("risk_health", {})),
        "",
        "## 外部等待事项",
        _wait_section(view.get("external_wait", {})),
        "",
        "## 需要您做决策",
    ]
    card = view.get("decision_card")
    if card is None:
        lines.append("当前没有待您决策的事项。")
    else:
        lines.append(f"**{card['topic']}**")
        lines.append(f"- AI 建议：{card['ai_recommendation']}")
        lines.append("- 可选方案及其影响：")
        for opt in card["options"]:
            imp = card.get("impacts", {}).get(opt, {})
            lines.append(
                f"  - {opt}（成本:{_impact_cn(imp.get('cost', '-'))}"
                f" / 性能:{_impact_cn(imp.get('performance', '-'))}"
                f" / 时间:{_impact_cn(imp.get('time', '-'))}"
                f" / 安全:{_impact_cn(imp.get('safety', '-'))}）")
        lines.append(f"- 批准后系统将自动执行：{card['after_approval']}")

    lines += [
        "",
        "## 上次进行到哪",
        _where_left_off_cn(rs),
        "",
        "## 新增/变更的关键参数",
        "、".join(rs.get("new_fact_keys", [])) if rs.get("new_fact_keys") else "无",
        "",
        "## 制品版本 / 参数差异",
        _artifact_diff_section(view.get("artifact_preview", {})),
        "",
        "## 下一步",
        _next_action_cn(rs),
        "",
        "---",
        "<details><summary>内部代号 / 技术细节</summary>",
        "",
        "```json",
        json.dumps(view, ensure_ascii=False, indent=2, default=str),
        "```",
        "</details>",
    ]
    return "\n".join(lines)


class OwnerView:
    """组合各面向所有者的视图模块。"""

    def __init__(self, db: AIPDStateDB, tenant_id: str = "default"):
        self._db = db
        self._tenant = tenant_id

    @property
    def tenant_id(self) -> str:
        return self._tenant

    def owner_update(self, project_id: str) -> Dict[str, Any]:
        """返回所有者的完整更新视图（自然语言优先）。"""
        view = {
            "project_summary": build_project_summary(self._db, project_id, self._tenant),
            "decision_card": build_decision_card(self._db, project_id, tenant_id=self._tenant),
            "resume_summary": build_resume_summary(self._db, project_id, self._tenant),
            "artifact_preview": artifact_preview(self._db, project_id, self._tenant),
        }
        view.update(_build_risk_and_wait(self._db, self._tenant, project_id))
        return view

    def to_markdown(self, view: Optional[Dict[str, Any]] = None,
                    project_id: Optional[str] = None) -> str:
        """把 owner_update 的结果渲染成 Markdown。未传 view 时自动构建。"""
        if view is None:
            pid = project_id or self._latest_project_id()
            view = self.owner_update(pid)
        return render_markdown(view)

    def _latest_project_id(self) -> str:
        projects = self._db.list_projects(self._tenant)
        if not projects:
            raise ValueError("当前租户下没有项目")
        return projects[0]["project_id"]


def to_markdown(view: Dict[str, Any]) -> str:
    """纯函数：渲染一个已构建好的 owner_update 视图为 Markdown。"""
    return render_markdown(view)


__all__ = ["OwnerView", "to_markdown", "render_markdown"]
