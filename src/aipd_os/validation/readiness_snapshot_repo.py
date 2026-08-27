"""ReadinessSnapshotRepository — readiness_snapshots 表 Repository。

P2-M7: Readiness Snapshot + Ruleset Completion

每次正式 readiness evaluation 自动持久化快照。
快照是 projection，不是 domain truth。
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# Ruleset version — bump when readiness rules materially change
READINESS_RULESET_VERSION = "2.0.0"


def compute_input_fingerprint(inputs: dict[str, Any]) -> str:
    """计算 readiness 输入的确定性 fingerprint。

    排除 volatile 字段（timestamp, random id）。
    """
    canonical = json.dumps(inputs, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


class ReadinessSnapshotRepository:
    """readiness_snapshots 表的 Repository。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(
        self,
        snapshot_id: str,
        tenant_id: str,
        project_id: str,
        overall_status: str,
        dimension_results: list[dict[str, Any]],
        blockers: list[str],
        warnings: list[str],
        missing_evidence: list[str],
        stale_dependencies: list[str],
        remediation_actions: list[str],
        input_fingerprint: str,
    ) -> None:
        """创建不可变 readiness 快照。"""
        now = _now()
        self._conn.execute(
            "INSERT INTO readiness_snapshots"
            "(snapshot_id, tenant_id, project_id, evaluated_at, "
            "overall_status, ruleset_version, input_fingerprint, "
            "dimension_results_json, blockers_json, warnings_json, "
            "missing_evidence_json, stale_dependencies_json, "
            "remediation_actions_json, superseded, created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,0,?)",
            (snapshot_id, tenant_id, project_id, now,
             overall_status, READINESS_RULESET_VERSION, input_fingerprint,
             json.dumps(dimension_results), json.dumps(blockers),
             json.dumps(warnings), json.dumps(missing_evidence),
             json.dumps(stale_dependencies), json.dumps(remediation_actions),
             now))

    def get(self, snapshot_id: str, tenant_id: str,
            project_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM readiness_snapshots "
            "WHERE snapshot_id=? AND tenant_id=? AND project_id=?",
            (snapshot_id, tenant_id, project_id)).fetchone()
        if row is None:
            return None
        return dict(row)

    def latest(self, tenant_id: str,
               project_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM readiness_snapshots "
            "WHERE tenant_id=? AND project_id=? AND superseded=0 "
            "ORDER BY evaluated_at DESC LIMIT 1",
            (tenant_id, project_id)).fetchone()
        if row is None:
            return None
        return dict(row)

    def list_snapshots(
        self, tenant_id: str, project_id: str, limit: int = 20,
    ) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM readiness_snapshots "
            "WHERE tenant_id=? AND project_id=? "
            "ORDER BY evaluated_at DESC LIMIT ?",
            (tenant_id, project_id, limit)).fetchall()
        return [dict(r) for r in rows]

    def mark_superseded(self, tenant_id: str, project_id: str) -> int:
        """标记所有当前快照为 superseded（为新快照腾位置）。"""
        cursor = self._conn.execute(
            "UPDATE readiness_snapshots SET superseded=1 "
            "WHERE tenant_id=? AND project_id=? AND superseded=0",
            (tenant_id, project_id))
        return cursor.rowcount
