"""追加式审计日志（append-only JSONL）。

每条记录：actor / action / project_id / tenant_id / timestamp / before / after。
默认写入 ``<db_dir>/audit.log``（JSON Lines）；也同步写入数据库 audit_log 表。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .db import AIPDStateDB


class AuditLogger:
    def __init__(self, db: AIPDStateDB, log_path: Optional[str] = None):
        self._db = db
        if log_path is None:
            log_path = str(Path(db.path).parent / "audit.log")
        self._path = Path(log_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, actor: str, action: str, project_id: Optional[str] = None,
            tenant_id: Optional[str] = None, before: Any = None, after: Any = None) -> None:
        record = {
            "actor": actor,
            "action": action,
            "project_id": project_id,
            "tenant_id": tenant_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "before": before,
            "after": after,
        }
        with open(self._path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        self._db.add_audit(actor, action, project_id, tenant_id, before, after)

    def read(self, limit: int = 100) -> list:
        """读取 JSONL 审计日志（文件末尾最新在前）。"""
        if not self._path.exists():
            return []
        lines = self._path.read_text(encoding="utf-8").strip().splitlines()
        records = []
        for line in lines[-limit:]:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return records


__all__ = ["AuditLogger"]
