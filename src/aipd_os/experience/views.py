"""顶层所有者视图：把各 experience 模块组合成一个统一的自然语言更新。

``OwnerView.owner_update`` 返回项目摘要 + 单一决策卡片 + 会话恢复摘要 + 制品预览；
``to_markdown`` 渲染成面向产品所有者的可读 Markdown，内部代号只放在可折叠的
``<details>`` 区块里。
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from ..state.db import AIPDStateDB
from .project_summary import build_project_summary
from .decision_card import build_decision_card
from .resume_summary import build_resume_summary
from .artifact_preview import artifact_preview


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
        "## 需要您做决策",
    ]
    card = view.get("decision_card")
    if card is None:
        lines.append("当前没有待您决策的事项。")
    else:
        lines.append(f"**{card['topic']}**（{card['decision_id']}）")
        lines.append(f"- AI 建议：{card['ai_recommendation']}")
        lines.append("- 可选方案及其影响：")
        for opt in card["options"]:
            imp = card.get("impacts", {}).get(opt, {})
            lines.append(
                f"  - {opt}（成本:{imp.get('cost', '-')} / 性能:{imp.get('performance', '-')}"
                f" / 时间:{imp.get('time', '-')} / 安全:{imp.get('safety', '-')}）")
        lines.append(f"- 批准后系统将自动执行：{card['after_approval']}")

    lines += [
        "",
        "## 上次进行到哪",
        str(rs.get("where_left_off", "")),
        "",
        "## 新增/变更的关键参数",
        "、".join(rs.get("new_fact_keys", [])) if rs.get("new_fact_keys") else "无",
        "",
        "## 下一步",
        str(rs.get("next_action", "")),
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
        return {
            "project_summary": build_project_summary(self._db, project_id, self._tenant),
            "decision_card": build_decision_card(self._db, project_id, tenant_id=self._tenant),
            "resume_summary": build_resume_summary(self._db, project_id, self._tenant),
            "artifact_preview": artifact_preview(self._db, project_id, self._tenant),
        }

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
