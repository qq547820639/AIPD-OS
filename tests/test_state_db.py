"""多租户多项目状态库：乐观锁、租户隔离、事实/决策 CRUD。"""
from __future__ import annotations

from pathlib import Path

import pytest

from aipd_os.state.db import AIPDStateDB, OptimisticLockError, ProjectNotFoundError


@pytest.fixture
def db(tmp_path):
    return AIPDStateDB(str(tmp_path / "state.db"), encryption_key="test-key")


def test_optimistic_lock_conflict_second_update_fails(db):
    db.ensure_default_tenant()
    db.init_project("default", "p1", "P1", "goal")
    p = db.get_project("default", "p1")
    assert p["version_no"] == 1

    db.update_project("default", "p1", expected_version=1, name="P1 v2")
    assert db.get_project("default", "p1")["version_no"] == 2

    # 第二次用旧版本号更新 → 冲突
    with pytest.raises(OptimisticLockError):
        db.update_project("default", "p1", expected_version=1, name="boom")


def test_multi_tenant_isolation(db):
    db.ensure_default_tenant()
    db.create_tenant("tenantA")
    db.create_tenant("tenantB")
    db.init_project("tenantA", "projA", "A", "goal-a")
    db.init_project("tenantB", "projB", "B", "goal-b")

    # B 读不到 A 的项目
    with pytest.raises(ProjectNotFoundError):
        db.get_project("tenantB", "projA")

    assert db.get_project("tenantA", "projA")["name"] == "A"
    assert [p["project_id"] for p in db.list_projects("tenantB")] == ["projB"]


def test_fact_crud(db):
    db.ensure_default_tenant()
    db.init_project("default", "p1", "P1", "goal")
    fid = db.add_fact("default", "p1", "latency", 42, "V", unit="ms", source="bench")
    facts = db.list_facts("default", "p1")
    assert facts[0]["key"] == "latency"
    assert facts[0]["value"] == 42
    assert db.get_fact("default", "p1", fid)["value"] == 42

    db.update_fact("default", "p1", fid, expected_version=1, value=43)
    assert db.get_fact("default", "p1", fid)["value"] == 43

    db.delete_fact("default", "p1", fid)
    assert db.list_facts("default", "p1") == []


def test_decision_crud_and_project_status(db):
    db.ensure_default_tenant()
    db.init_project("default", "p1", "P1", "goal")
    did = db.propose_decision("default", "p1", "pick model", "use A", ["A", "B"])
    assert db.get_project("default", "p1")["status"] == "awaiting_owner_decision"

    db.resolve_decision("default", "p1", did, "A", "chosen")
    resolved = db.list_resolved_decisions("default", "p1")
    assert [d["decision_id"] for d in resolved] == [did]
    assert db.get_project("default", "p1")["status"] == "active"


def test_sensitive_field_encrypted_at_rest(db):
    db.ensure_default_tenant()
    db.init_project("default", "p1", "P1", "goal")
    db.add_fact("default", "p1", "supplier_quote", 1234.5, "V")
    import sqlite3
    conn = sqlite3.connect(str(db.path))
    raw = conn.execute("SELECT value_json FROM facts").fetchone()[0]
    conn.close()
    assert "__encrypted__" in raw
    assert db.list_facts("default", "p1")[0]["value"] == 1234.5


def test_object_store_safe_neutralizes_dot_dot(tmp_path):
    """回归：project_id '..' 不得经 ObjectStore 路径穿越 base_dir。"""
    from aipd_os.state.objects import ObjectStore, _safe

    assert _safe("..") == "_"
    assert _safe(".") == "_"
    assert _safe("../etc") == "_etc"  # "/" 已替换为 "_"，无穿越
    base = tmp_path / "objects"
    store = ObjectStore(str(base))
    p = store.put("..", "k", b"v")
    # 产物必须落在 base 之内（".." 被中和为 "_"，不逃逸）
    assert Path(p).resolve().is_relative_to(base.resolve())
