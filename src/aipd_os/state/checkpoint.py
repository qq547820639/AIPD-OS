"""会话检查点：保存 / 恢复 / 恢复摘要。

``resume_summary`` 返回会话上次中断的位置、上次检查点之后新增/变更的事实、
过期制品、外部等待项、当前阶段、阻塞项与下一步动作；
并且不会重新追问已解决的决策（跟踪 ``resolved_decision_ids``）。
"""
from __future__ import annotations

from typing import Any

from .db import AIPDStateDB, now_iso


class CheckpointManager:
    def __init__(self, db: AIPDStateDB):
        self._db = db

    def save_checkpoint(self, project_id: str, data: Any, tenant_id: str = "default",
                        summary: Any = None) -> int:
        return self._db.save_checkpoint(tenant_id, project_id, data, summary)

    def restore_latest(self, project_id: str, tenant_id: str = "default") -> dict[str, Any] | None:
        cp = self._db.latest_checkpoint(tenant_id, project_id)
        if cp is None:
            return None
        return {"checkpoint_id": cp["checkpoint_id"], "data": cp["data"],
                "summary": cp["summary"], "created_at": cp["created_at"]}

    def resume_summary(self, project_id: str, tenant_id: str = "default") -> dict[str, Any]:
        db = self._db
        cp = db.latest_checkpoint(tenant_id, project_id)
        project = db.get_project(tenant_id, project_id)

        open_decisions = db.list_open_decisions(tenant_id, project_id)
        resolved = db.list_resolved_decisions(tenant_id, project_id)
        resolved_ids = [d["decision_id"] for d in resolved]

        last_off = None
        if cp:
            last_off = cp.get("summary") or {"at": cp["created_at"], "note": "no summary recorded"}

        new_facts = []
        stale_artifacts = []
        if cp:
            cp_ts = cp["created_at"]
            for f in db.list_facts(tenant_id, project_id):
                if str(f["updated_at"]) > cp_ts:
                    new_facts.append({"fact_id": f["fact_id"], "key": f["key"],
                                      "status": f["status"], "updated_at": f["updated_at"]})
            for d in db.list_deliverables(tenant_id, project_id):
                if d["status"] in ("planned", "in_progress") and str(d["updated_at"]) < cp_ts:
                    stale_artifacts.append({"deliverable_id": d["deliverable_id"],
                                            "type": d["type"], "status": d["status"]})
        else:
            new_facts = [{"fact_id": f["fact_id"], "key": f["key"], "status": f["status"]}
                         for f in db.list_facts(tenant_id, project_id)]

        external_waiting = []
        blockers = []
        for dep in db.list_dependencies(tenant_id, project_id):
            if dep["relation"] in ("needs_external", "blocked_by_external"):
                external_waiting.append({"source_type": dep["source_type"], "source_id": dep["source_id"],  # noqa: E501
                                         "target_type": dep["target_type"], "target_id": dep["target_id"]})  # noqa: E501
        if project["status"] == "blocked_external":
            external_waiting.append({"note": "project status is blocked_external"})
        for risk in db.list_risks(tenant_id, project_id):
            if risk["status"] == "open" and risk["impact"] in ("high", "critical"):
                blockers.append({"risk_id": risk["risk_id"], "title": risk["title"], "impact": risk["impact"]})  # noqa: E501
        if project["status"] in ("awaiting_owner_decision", "blocked_external", "internal_rework"):
            blockers.append(project["status"])

        if open_decisions:
            next_action = "resolve proposed decisions: " + ", ".join(
                d["topic"] for d in open_decisions[:3])
        else:
            next_action = f"continue phase {project['gate']}"

        return {
            "project_id": project_id,
            "tenant_id": tenant_id,
            "phase": project["gate"],
            "project_status": project["status"],
            "last_off": last_off or "no prior checkpoint",
            "new_or_changed_facts": new_facts,
            "stale_artifacts": stale_artifacts,
            "external_waiting": external_waiting,
            "blockers": blockers,
            "next_action": next_action,
            "pending_decisions": [{"decision_id": d["decision_id"], "topic": d["topic"],
                                   "status": d["status"]} for d in open_decisions],
            "resolved_decision_ids": resolved_ids,
            "resume_at": now_iso(),
        }


__all__ = ["CheckpointManager"]
