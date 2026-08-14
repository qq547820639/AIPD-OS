"""健康检查。"""
from __future__ import annotations

from aipd_os.state.db import AIPDStateDB
from aipd_os.state.health import health_check


def test_health_ok(tmp_path):
    db = AIPDStateDB(str(tmp_path / "state.db"))
    db.ensure_default_tenant()
    result = health_check(str(tmp_path / "state.db"))
    assert result["ok"] is True
    assert result["checks"]["db_connectivity"] == "ok"
    assert isinstance(result["checks"]["schema_version"], int)
    assert result["checks"]["schema_version"] >= 1
    assert result["checks"]["backup_age_hours"] is None
    assert result["checks"]["disk_free_bytes"] > 0


def test_health_check_is_read_only_and_does_not_migrate(tmp_path):
    """回归：GET /health 健康检查不得触发 migrate 写副作用。"""
    import sqlite3

    from aipd_os.state.health import health_check
    from aipd_os.state.migrations import current_version

    db_path = str(tmp_path / "fresh.db")
    # 空文件：连通性探测会创建 0 字节文件？health_check 用 sqlite3.connect
    # 打开（会创建文件），但不得建表/迁移
    out = health_check(db_path)
    assert out["checks"]["schema_version"] == 0  # 未迁移
    assert current_version(db_path) == 0
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        ).fetchone()
        assert row is None, "health check 不得创建 schema_migrations 表"
    finally:
        conn.close()
