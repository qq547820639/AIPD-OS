"""StalePropagationService — 统一的 stale 传播引擎。

P2-M6: Unified Dependency + Stale Propagation

核心规则：
- BOM material change → CostSnapshot stale → Readiness HOLD
- Requirement/CTQ change → linked Validation stale → Readiness HOLD
- CAD material revision change → Validation stale → Readiness HOLD
- Supplier qualification change → Supply stale
- Blocking Issue opens → Readiness no longer PASS
- Validation PASS becomes stale → Readiness HOLD

所有传播 deterministic + auditable + idempotent。
历史 evidence immutable (PASS + stale=true, 不是 PASS→FAIL)。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# Material field definitions per domain
BOM_MATERIAL_FIELDS = frozenset({
    "quantity", "unit", "part_number", "supplier", "unit_cost",
    "revision", "material", "specification",
})

REQUIREMENT_MATERIAL_FIELDS = frozenset({
    "title", "description", "acceptance_criteria", "priority",
    "ctq_target", "ctq_tolerance", "verification_method",
})

CAD_MATERIAL_FIELDS = frozenset({
    "content_hash", "revision", "maturity", "generator_version",
})


class StalePropagationService:
    """统一的 stale 传播服务。

    输入：upstream node changed
    输出：affected targets marked stale + propagation trace
    """

    def __init__(self, db: Any) -> None:
        """db: AIPDStateDB 实例（提供 dependencies/audit/changes 表访问）。"""
        self._db = db

    def propagate_bom_change(
        self,
        tenant_id: str,
        project_id: str,
        bom_id: str,
        old_fields: dict[str, Any],
        new_fields: dict[str, Any],
    ) -> dict[str, Any]:
        """BOM material change → Cost stale → Readiness HOLD。"""
        changed_material = self._material_changed(
            BOM_MATERIAL_FIELDS, old_fields, new_fields)
        if not changed_material:
            return {"propagated": False, "reason": "no material fields changed"}

        # Mark dependent Cost snapshots stale via dependency graph
        affected = self._mark_downstream_stale(
            tenant_id, project_id, "bom", bom_id,
            reason=f"BOM material change: {', '.join(sorted(changed_material))}",
            target_types=("cost_snapshot",),
        )
        # Append propagation event to outbox
        self._append_propagation_event(
            tenant_id, project_id, "bom", bom_id,
            "bom_material_change", changed_material, affected,
        )
        return {"propagated": True, "material_fields": sorted(changed_material),
                "affected": affected}

    def propagate_requirement_change(
        self,
        tenant_id: str,
        project_id: str,
        requirement_id: str,
        old_fields: dict[str, Any],
        new_fields: dict[str, Any],
    ) -> dict[str, Any]:
        """Requirement/CTQ change → linked Validation stale → Readiness HOLD。"""
        changed_material = self._material_changed(
            REQUIREMENT_MATERIAL_FIELDS, old_fields, new_fields)
        if not changed_material:
            return {"propagated": False, "reason": "no material fields changed"}

        affected = self._mark_downstream_stale(
            tenant_id, project_id, "requirement", requirement_id,
            reason=f"Requirement material change: {', '.join(sorted(changed_material))}",
            target_types=("validation_result",),
        )
        self._append_propagation_event(
            tenant_id, project_id, "requirement", requirement_id,
            "requirement_material_change", changed_material, affected,
        )
        return {"propagated": True, "material_fields": sorted(changed_material),
                "affected": affected}

    def propagate_cad_change(
        self,
        tenant_id: str,
        project_id: str,
        artifact_id: str,
        old_fields: dict[str, Any],
        new_fields: dict[str, Any],
    ) -> dict[str, Any]:
        """CAD material revision change → Validation stale → Readiness HOLD。"""
        changed_material = self._material_changed(
            CAD_MATERIAL_FIELDS, old_fields, new_fields)
        if not changed_material:
            return {"propagated": False, "reason": "no material fields changed"}

        affected = self._mark_downstream_stale(
            tenant_id, project_id, "cad_artifact", artifact_id,
            reason=f"CAD material change: {', '.join(sorted(changed_material))}",
            target_types=("validation_result",),
        )
        self._append_propagation_event(
            tenant_id, project_id, "cad_artifact", artifact_id,
            "cad_material_change", changed_material, affected,
        )
        return {"propagated": True, "material_fields": sorted(changed_material),
                "affected": affected}

    def propagate_issue_opened(
        self,
        tenant_id: str,
        project_id: str,
        issue_id: str,
    ) -> dict[str, Any]:
        """Blocking Issue opens → Readiness no longer PASS。"""
        self._append_propagation_event(
            tenant_id, project_id, "issue", issue_id,
            "issue_opened", set(), [],
        )
        return {"propagated": True, "reason": "blocking issue opened",
                "readiness_impact": "HOLD"}

    def _material_changed(
        self,
        material_fields: frozenset[str],
        old_fields: dict[str, Any],
        new_fields: dict[str, Any],
    ) -> set[str]:
        """检查 material fields 是否有实际变化。"""
        changed = set()
        for field in material_fields:
            old_val = old_fields.get(field)
            new_val = new_fields.get(field)
            if old_val != new_val:
                changed.add(field)
        return changed

    def _mark_downstream_stale(
        self,
        tenant_id: str,
        project_id: str,
        source_type: str,
        source_id: str,
        reason: str,
        target_types: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        """通过 dependency graph 标记 downstream targets 为 stale。"""
        now = _now()
        affected = []
        with self._db.connect() as conn:
            for target_type in target_types:
                deps = conn.execute(
                    "SELECT target_type, target_id FROM dependencies "
                    "WHERE tenant_id=? AND project_id=? "
                    "AND source_type=? AND source_id=? "
                    "AND target_type=?",
                    (tenant_id, project_id, source_type, source_id,
                     target_type)).fetchall()
                for dep in deps:
                    # Mark validation_results stale
                    if target_type == "validation_result":
                        cursor = conn.execute(
                            "UPDATE validation_results "
                            "SET stale=1, stale_reason=?, updated_at=? "
                            "WHERE result_id=? AND tenant_id=? AND project_id=? "
                            "AND stale=0",
                            (reason, now, dep["target_id"],
                             tenant_id, project_id))
                        if cursor.rowcount > 0:
                            affected.append({
                                "target_type": target_type,
                                "target_id": dep["target_id"],
                                "action": "marked_stale",
                            })
                    # Mark cost snapshots stale (via changes table)
                    elif target_type == "cost_snapshot":
                        conn.execute(
                            "INSERT OR IGNORE INTO changes"
                            "(tenant_id, project_id, entity_type, entity_id, "
                            "change_type, change_data, created_at) "
                            "VALUES(?,?,?,?,?,?,?)",
                            (tenant_id, project_id, target_type,
                             dep["target_id"], "stale",
                             json.dumps({"reason": reason}), now))
                        affected.append({
                            "target_type": target_type,
                            "target_id": dep["target_id"],
                            "action": "marked_stale",
                        })
        return affected

    def _append_propagation_event(
        self,
        tenant_id: str,
        project_id: str,
        source_type: str,
        source_id: str,
        event_type: str,
        material_fields: set[str],
        affected: list[dict[str, Any]],
    ) -> None:
        """记录传播事件到 changes 表。"""
        now = _now()
        with self._db.connect() as conn:
            conn.execute(
                "INSERT INTO changes"
                "(project_id, tenant_id, object_type, object_id, "
                "action, after_json, reason, created_at) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (project_id, tenant_id, source_type, source_id,
                 event_type,
                 json.dumps({
                     "material_fields": sorted(material_fields),
                     "affected_count": len(affected),
                 }),
                 f"stale propagation: {event_type}",
                 now))
