"""健康检查：数据库连通性、schema 版本、备份新鲜度、磁盘剩余。"""
from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import migrations


def health_check(db_path: str) -> dict[str, Any]:
    """返回健康状态字典，``ok`` 表示整体健康。"""
    path = Path(db_path)
    result: dict[str, Any] = {"db_path": str(path), "ok": True, "checks": {}}

    # 1) 数据库连通性
    try:
        conn = sqlite3.connect(str(path))
        conn.execute("SELECT 1").fetchone()
        conn.close()
        result["checks"]["db_connectivity"] = "ok"
    except sqlite3.Error as exc:  # pragma: no cover
        result["checks"]["db_connectivity"] = f"error: {exc}"
        result["ok"] = False

    # 2) schema 版本（先回填 schema_migrations 记录，保证 version>=1）
    try:
        migrations.migrate(str(path))
        version = migrations.current_version(str(path))
        result["checks"]["schema_version"] = version
    except Exception as exc:  # pragma: no cover
        result["checks"]["schema_version"] = f"error: {exc}"

    # 3) 备份新鲜度（最近一次备份距今小时数）
    try:
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT created_at FROM backups ORDER BY created_at DESC LIMIT 1").fetchone()
        conn.close()
        if row:
            dt = datetime.fromisoformat(row["created_at"])
            hours = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
            result["checks"]["backup_age_hours"] = round(hours, 2)
        else:
            result["checks"]["backup_age_hours"] = None
    except Exception as exc:  # pragma: no cover
        result["checks"]["backup_age_hours"] = f"error: {exc}"

    # 4) 磁盘剩余
    try:
        usage = shutil.disk_usage(path.parent if path.exists() else ".")
        result["checks"]["disk_free_bytes"] = usage.free
        result["checks"]["disk_total_bytes"] = usage.total
    except Exception as exc:  # pragma: no cover
        result["checks"]["disk_free_bytes"] = f"error: {exc}"

    return result


__all__ = ["health_check"]
