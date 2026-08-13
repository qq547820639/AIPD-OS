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
