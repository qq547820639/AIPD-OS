"""会话恢复摘要：上次进行到哪、新增/变更了什么、还缺什么、下一步做什么。

复用执行层/状态层的 :class:`CheckpointManager`，它已经跟踪了
``resolved_decision_ids``，因此已解决的决策不会被再次追问。
这里把它转成面向所有者的中文自然语言结构。
"""
from __future__ import annotations

from typing import Any, Dict

from ..state.checkpoint import CheckpointManager
from ..state.db import AIPDStateDB


def build_resume_summary(db: AIPDStateDB, project_id: str,
                         tenant_id: str = "default") -> Dict[str, Any]:
    """返回会话恢复摘要（中文自然语言 + 结构化数据）。"""
    rs = CheckpointManager(db).resume_summary(project_id, tenant_id)
    resolved_ids = set(rs.get("resolved_decision_ids", []))

    # 只列出尚未解决的待审决策，绝不重提已解决的
    decisions_to_ask = [
        {"decision_id": d["decision_id"], "topic": d["topic"]}
        for d in rs.get("pending_decisions", [])
        if d["decision_id"] not in resolved_ids
    ]

    new_facts = [
        {"key": f["key"], "status": f["status"]}
        for f in rs.get("new_or_changed_facts", [])
    ]
    stale = [
        {"deliverable_id": a["deliverable_id"], "type": a["type"]}
        for a in rs.get("stale_artifacts", [])
    ]
    external = [
        {"source": f"{a['source_type']}:{a['source_id']}",
         "needs": f"{a['target_type']}:{a['target_id']}"}
        for a in rs.get("external_waiting", [])
    ]

    return {
        "where_left_off": rs.get("last_off") or "没有历史检查点，从当前阶段开始",
        "current_phase": rs.get("phase"),
        "project_status": rs.get("project_status"),
        "new_or_changed_facts": new_facts,
        "new_fact_keys": [f["key"] for f in new_facts],
        "stale_artifacts": stale,
        "external_waiting": external,
        "blockers": rs.get("blockers", []),
        "next_action": rs.get("next_action"),
        "decisions_to_ask": decisions_to_ask,
        "resolved_decision_ids": sorted(resolved_ids),
        "resume_at": rs.get("resume_at"),
    }


__all__ = ["build_resume_summary"]
