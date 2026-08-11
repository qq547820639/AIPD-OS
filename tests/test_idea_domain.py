"""v5.8 Commit 9：Idea Domain + migration 测试。

覆盖：
- create/get/update/archive/list 全 CRUD + tenant scope + project scope；
- version_no 乐观锁冲突；
- audit 记录存在（ideas 写操作进 audit_log）；
- migration v1→v2 后 ideas 表可用 + rollback 正常（v2/v3/v4 表一并验证）；
- tenantA 不能读 tenantB 的 idea（service 层拒绝）。
"""
from __future__ import annotations

import sqlite3

import pytest

from aipd_os.idea import (
    Idea,
    IdeaNotFoundError,
    IdeaOptimisticLockError,
    IdeaService,
)
from aipd_os.state import migrations
from aipd_os.state.db import AIPDStateDB

NEW_TABLES = {"ideas", "claims", "claim_evidence_relations"}


@pytest.fixture
def env(tmp_path):
    db = AIPDStateDB(str(tmp_path / "state.db"))
    db.ensure_default_tenant("default")
    db.init_project("default", "P1", "P1", "goal")
    return db, IdeaService(db)


def _idea(**kw):
    defaults = dict(
        idea_id="", title="外骨骼助力", raw_input="帮助老年人行走",
        goal="提升行动能力", problem="肌肉力量下降", target_user="老年人",
        desired_outcome="独立行走 30 分钟", source="user-interview",
    )
    defaults.update(kw)
    return Idea(tenant_id="default", project_id="P1", **defaults)


# ---------------------------------------------------------------------------
# 1) CRUD
# ---------------------------------------------------------------------------
def test_idea_crud(env):
    db, svc = env
    idea = svc.create(_idea())
    assert idea.idea_id.startswith("IDEA-")
    # v5.8.1 Commit 3：lifecycle_status 只表达对象生命状态（默认 active）
    assert idea.lifecycle_status == "active"

    got = svc.get("default", "P1", idea.idea_id)
    assert got.title == "外骨骼助力"
    assert got.tenant_id == "default" and got.project_id == "P1"

    updated = svc.update("default", "P1", idea.idea_id, expected_version=1,
                         title="外骨骼升级版", goal="提升耐力")
    assert updated.version_no == 2
    assert updated.title == "外骨骼升级版"
    assert svc.get("default", "P1", idea.idea_id).version_no == 2

    archived = svc.archive("default", "P1", idea.idea_id, expected_version=2)
    assert archived.lifecycle_status == "archived"
    assert archived.version_no == 3

    ids = svc.list_ids("default", "P1")
    assert ids == [idea.idea_id]
    assert len(svc.list("default", "P1")) == 1


# ---------------------------------------------------------------------------
# 2) scope：tenant / project 隔离
# ---------------------------------------------------------------------------
def test_idea_tenant_scope_isolation(env):
    db, svc = env
    db.ensure_default_tenant("tenantB")
    db.init_project("tenantB", "PB", "PB", "g")
    idea = svc.create(_idea())  # tenant default / P1
    with pytest.raises((IdeaNotFoundError, KeyError)):
        svc.get("tenantB", "PB", idea.idea_id)
    assert svc.list("tenantB", "PB") == []


def test_idea_project_scope_isolation(env):
    db, svc = env
    db.init_project("default", "P2", "P2", "g")
    idea = svc.create(_idea())  # project P1
    with pytest.raises((IdeaNotFoundError, KeyError)):
        svc.get("default", "P2", idea.idea_id)
    assert svc.list("default", "P2") == []


# ---------------------------------------------------------------------------
# 3) 乐观锁 + 非法 lifecycle
# ---------------------------------------------------------------------------
def test_idea_optimistic_lock_conflict(env):
    _, svc = env
    idea = svc.create(_idea())
    svc.update("default", "P1", idea.idea_id, expected_version=1, title="v2")
    with pytest.raises(IdeaOptimisticLockError):
        svc.update("default", "P1", idea.idea_id, expected_version=1, title="stale")


def test_idea_invalid_lifecycle_rejected(env):
    _, svc = env
    with pytest.raises(ValueError):
        Idea(idea_id="", tenant_id="default", project_id="P1",
             title="x", lifecycle_status="bogus")


# ---------------------------------------------------------------------------
# 4) audit
# ---------------------------------------------------------------------------
def test_idea_writes_are_audited(env):
    db, svc = env
    idea = svc.create(_idea(), actor="alice")
    svc.update("default", "P1", idea.idea_id, expected_version=1,
               title="audited", actor="bob")
    records = db.list_audit(limit=100)
    actions = [r["action"] for r in records]
    assert "idea.create" in actions
    assert "idea.update" in actions
    create_rec = next(r for r in records if r["action"] == "idea.create")
    assert create_rec["actor"] == "alice"
    assert create_rec["tenant_id"] == "default"
    assert create_rec["project_id"] == "P1"


# ---------------------------------------------------------------------------
# 5) migration v1→v5（idea/claim/relation/id_sequences） + rollback
# ---------------------------------------------------------------------------
def test_migration_applies_idea_claim_relation_tables(tmp_path):
    db_path = str(tmp_path / "m.db")
    applied = migrations.migrate(db_path)
    # v5.8.1 Commit 7/9：v5=id_sequences，v6=generic lineage 列
    assert applied == [1, 2, 3, 4, 5, 6, 7]
    assert migrations.current_version(db_path) == 7
    conn = sqlite3.connect(db_path)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert tables >= NEW_TABLES
    assert {"id_sequences"} <= tables


def test_migration_v2_creates_ideas_on_v1_era_db(tmp_path):
    """模拟 v1-era 库（无 ideas/claims/relations 表）→ migrate 后 v2/v3/v4/v5 补齐。"""
    db_path = str(tmp_path / "m.db")
    migrations.migrate(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("DROP TABLE id_sequences")
    conn.execute("DROP TABLE claim_evidence_relations")
    conn.execute("DROP TABLE claims")
    conn.execute("DROP TABLE ideas")
    conn.execute("DELETE FROM schema_migrations WHERE version IN (2,3,4,5,6,7)")
    conn.commit()
    conn.close()
    assert migrations.current_version(db_path) == 1
    applied = migrations.migrate(db_path)
    assert applied == [2, 3, 4, 5, 6, 7]
    conn = sqlite3.connect(db_path)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert tables >= NEW_TABLES
    assert {"id_sequences"} <= tables


def test_migration_rollback_drops_idea_tables(tmp_path):
    db_path = str(tmp_path / "m.db")
    migrations.migrate(db_path)
    rolled = migrations.rollback(db_path, target=1)
    assert rolled == [7, 6, 5, 4, 3, 2]
    assert migrations.current_version(db_path) == 1
    conn = sqlite3.connect(db_path)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert not (NEW_TABLES & tables)
    assert "id_sequences" not in tables
    # 再迁移 → 表恢复
    migrations.migrate(db_path)
    conn = sqlite3.connect(db_path)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert tables >= NEW_TABLES
    assert {"id_sequences"} <= tables


def test_migration_ups_idempotent_on_existing_db(tmp_path):
    """AIPDStateDB 已建表（migration runner）时 migrate 幂等（CREATE IF NOT EXISTS 不报错）。"""
    db_path = str(tmp_path / "s.db")
    AIPDStateDB(db_path)  # __init__ 走 migrate() 建全部表
    applied = migrations.migrate(db_path)
    assert applied == []  # 已全部应用
    assert migrations.current_version(db_path) == 7
    conn = sqlite3.connect(db_path)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert tables >= NEW_TABLES
    assert {"id_sequences"} <= tables
