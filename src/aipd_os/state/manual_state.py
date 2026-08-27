"""Manual State Repository — canonicalize legacy JSON state.

P2-M4: Manual State Canonicalization

将 manual_chain 的 JSON 直接读写收敛到 Repository 模式。
Phase A/B: canonical DB storage + legacy JSON import.

manual_workflows 表存储 canonical state（migration v16）。
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _file_hash(path: Path) -> str:
    """计算文件内容 SHA-256。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ManualStateRepository:
    """Manual workflow state 的 Repository。

    存储在 manual_workflows 表（migration v16）。
    支持：
    - canonical DB 读写（primary）
    - legacy JSON 文件导入（one-time migration）
    - 幂等导入（相同内容不重复）
    - tenant/project scope
    - 乐观并发控制
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def read(self, tenant_id: str, project_id: str,
             workflow_id: str) -> dict[str, Any] | None:
        """读取 canonical state。"""
        row = self._conn.execute(
            "SELECT state_json, version_no, legacy_source_hash, "
            "legacy_imported_at, created_at, updated_at "
            "FROM manual_workflows "
            "WHERE workflow_id=? AND tenant_id=? AND project_id=?",
            (workflow_id, tenant_id, project_id)).fetchone()
        if row is None:
            return None
        state: dict[str, Any] = json.loads(row["state_json"])
        state["_tenant_id"] = tenant_id
        state["_project_id"] = project_id
        state["_workflow_id"] = workflow_id
        state["_version_no"] = row["version_no"]
        state["_updated_at"] = row["updated_at"]
        return state

    def write(self, tenant_id: str, project_id: str,
              workflow_id: str, state: dict[str, Any],
              expected_version: int = 0) -> int:
        """写入 canonical state，返回新 version_no。

        并发写入使用乐观锁：
        - 新建时 expected_version=0
        - 更新时 expected_version=当前 version_no
        0 rows → ConcurrentModificationError
        """
        now = _now()
        state_json = json.dumps(state, ensure_ascii=False)
        # Check if exists
        existing = self._conn.execute(
            "SELECT version_no FROM manual_workflows "
            "WHERE workflow_id=? AND tenant_id=? AND project_id=?",
            (workflow_id, tenant_id, project_id)).fetchone()
        if existing is None:
            if expected_version != 0:
                raise ValueError(
                    f"expected_version={expected_version} but row does not exist")
            self._conn.execute(
                "INSERT INTO manual_workflows"
                "(workflow_id, tenant_id, project_id, state_json, "
                "version_no, created_at, updated_at) "
                "VALUES(?,?,?,?,1,?,?)",
                (workflow_id, tenant_id, project_id, state_json, now, now))
            return 1
        # Update with optimistic concurrency
        cursor = self._conn.execute(
            "UPDATE manual_workflows SET state_json=?, "
            "version_no=version_no+1, updated_at=? "
            "WHERE workflow_id=? AND tenant_id=? AND project_id=? "
            "AND version_no=?",
            (state_json, now, workflow_id, tenant_id, project_id,
             expected_version))
        if cursor.rowcount == 0:
            raise ValueError(
                f"ConcurrentModification: expected version {expected_version} "
                f"but current version is {existing['version_no']}")
        return expected_version + 1

    def import_from_legacy(
        self,
        tenant_id: str,
        project_id: str,
        workflow_id: str,
        legacy_path: str | Path,
        force: bool = False,
    ) -> dict[str, Any]:
        """从 legacy JSON 导入到 canonical。

        幂等：相同内容不重复导入。
        如果 canonical 已存在且内容不同，需要 force=True。
        """
        legacy = Path(legacy_path)
        if not legacy.exists():
            raise FileNotFoundError(f"legacy file not found: {legacy}")

        legacy_hash = _file_hash(legacy)

        # 幂等检查
        existing = self._conn.execute(
            "SELECT version_no, legacy_source_hash FROM manual_workflows "
            "WHERE workflow_id=? AND tenant_id=? AND project_id=?",
            (workflow_id, tenant_id, project_id)).fetchone()
        if existing is not None:
            if existing["legacy_source_hash"] == legacy_hash:
                return {"status": "NO_OP", "reason": "already imported"}
            if not force:
                return {"status": "CONFLICT",
                        "reason": "canonical exists with different content"}

        # 执行导入
        legacy_data = json.loads(legacy.read_text(encoding="utf-8"))
        now = _now()
        state_json = json.dumps(legacy_data, ensure_ascii=False)
        if existing is not None:
            # Force overwrite
            self._conn.execute(
                "UPDATE manual_workflows SET state_json=?, "
                "legacy_source_hash=?, legacy_imported_at=?, "
                "version_no=version_no+1, updated_at=? "
                "WHERE workflow_id=? AND tenant_id=? AND project_id=?",
                (state_json, legacy_hash, now, now,
                 workflow_id, tenant_id, project_id))
        else:
            self._conn.execute(
                "INSERT INTO manual_workflows"
                "(workflow_id, tenant_id, project_id, state_json, "
                "version_no, legacy_source_hash, legacy_imported_at, "
                "created_at, updated_at) "
                "VALUES(?,?,?,?,1,?,?,?,?)",
                (workflow_id, tenant_id, project_id, state_json,
                 legacy_hash, now, now, now))
        return {"status": "IMPORTED", "legacy_hash": legacy_hash}

    def export_to_json(self, tenant_id: str, project_id: str,
                       workflow_id: str, export_path: str | Path) -> None:
        """导出 canonical state 到 JSON（projection, not truth）。"""
        state = self.read(tenant_id, project_id, workflow_id)
        if state is None:
            raise FileNotFoundError(
                f"workflow {workflow_id} not found")
        state["_export_type"] = "projection"
        state["_exported_at"] = _now()
        Path(export_path).write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8")
