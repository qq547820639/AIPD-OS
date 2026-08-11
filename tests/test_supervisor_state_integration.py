"""v5.7 Commit 4：Supervisor canonical Decision 集成测试。

覆盖（真实使用 AIPDStateDB + Supervisor 同一个 DB 文件）：
- owner_required work → run_supervisor → canonical Decision 创建成功
  （decisions 表有行，tenant_id/project_id 正确）→ project status ==
  awaiting_owner_decision → work item blocked_decision（decision_id 为
  canonical id）→ state_db.resolve_decision 解决 → Supervisor next_work
  恢复该工作项；
- Supervisor-only 旧 DB（无 canonical decisions）：_persist_decision legacy
  compatibility adapter 仍工作（现有 test_supervisor_execution.py 的决策
  测试继续通过）；
- canonical decisions 表存在但未传 state_db → fail-closed 明确报错。
"""
from __future__ import annotations

import sqlite3

import pytest

from aipd_os.state.db import AIPDStateDB
from aipd_os.supervisor import Supervisor


def _make_canonical_env(tmp_path):
    """AIPDStateDB（canonical SCHEMA 先执行）+ Supervisor 共享同一 DB。"""
    db_path = str(tmp_path / "state.db")
    db = AIPDStateDB(db_path)
    db.ensure_default_tenant("default")
    db.init_project("default", "P1", "P1", "goal")
    sup = Supervisor(db_path, tenant_id="default", project_id="P1", state_db=db)
    sup.init_lifecycle()
    return db, sup


def _make_legacy_env(tmp_path):
    """Supervisor-only 旧 DB：projects 表 + 一行，无 canonical decisions。"""
    db_path = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS projects("
        "project_id TEXT PRIMARY KEY, name TEXT, goal TEXT, gate TEXT DEFAULT 'G0',"
        " status TEXT DEFAULT 'active', version TEXT, owner_policy TEXT,"
        " created_at TEXT, updated_at TEXT)"
    )
    conn.execute(
        "INSERT INTO projects VALUES('P1','t','g','G0','active','0.1.0','{}','t','t')"
    )
    conn.commit()
    conn.close()
    sup = Supervisor(db_path)  # 未传 state_db → legacy path
    sup.init_lifecycle()
    return sup


# ---------------------------------------------------------------------------
# 1) canonical 决策全生命周期
# ---------------------------------------------------------------------------
def test_canonical_decision_created_and_resolved_recovers(tmp_path):
    db, sup = _make_canonical_env(tmp_path)
    wid = sup.add_work(
        "S5_cad", "release_gate", "release", "o",
        owner_required=True, capability_floor="doc.generate",
        inputs={"title": "T"},
    )

    # run_supervisor → 决策暂停
    results = sup.run_supervisor(steps=1, project_id="P1")
    assert results and results[0]["action"] == "decision"
    did = results[0]["decision"]["decision_id"]

    # canonical decisions 表有行（tenant_id/project_id 正确）
    decs = db.list_decisions("default", "P1")
    assert any(d["decision_id"] == did for d in decs), decs
    d = next(d for d in decs if d["decision_id"] == did)
    assert d["tenant_id"] == "default"
    assert d["project_id"] == "P1"
    assert d["topic"] == "release"
    assert d["status"] == "proposed"

    # 项目状态自动置 awaiting_owner_decision（db.propose_decision 行为）
    assert db.get_project("default", "P1")["status"] == "awaiting_owner_decision"

    # work item 阻塞且引用 canonical decision_id
    with sup.connect() as c:
        row = c.execute(
            "SELECT status, decision_id FROM supervisor_work_items WHERE work_id=?",
            (wid,)).fetchone()
    assert row["status"] == "blocked_decision"
    assert row["decision_id"] == did

    # canonical 决策解决 → 项目恢复 active → Supervisor 恢复该工作项
    db.resolve_decision("default", "P1", did, "A")
    assert db.get_project("default", "P1")["status"] == "active"
    item = sup.next_work(project_id="P1")
    assert item is not None and item["work_id"] == wid
    assert item["status"] == "running"


def test_canonical_decision_project_scoped(tmp_path):
    """canonical 决策写入正确的 tenant/project（不串项目）。"""
    db, sup = _make_canonical_env(tmp_path)
    db.init_project("default", "P2", "P2", "goal2")
    wid = sup.add_work("S3_manual", "m", "t", "o", owner_required=True)
    results = sup.run_supervisor(steps=1, project_id="P1")
    did = results[0]["decision"]["decision_id"]

    decs_p1 = db.list_decisions("default", "P1")
    decs_p2 = db.list_decisions("default", "P2")
    assert any(d["decision_id"] == did for d in decs_p1)
    assert not any(d["decision_id"] == did for d in decs_p2)
    assert db.get_project("default", "P1")["status"] == "awaiting_owner_decision"
    assert db.get_project("default", "P2")["status"] == "active"


# ---------------------------------------------------------------------------
# 2) legacy compatibility adapter（Supervisor-only 旧 DB）
# ---------------------------------------------------------------------------
def test_legacy_decision_persist_without_state_db(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPD_OUTPUT_DIR", str(tmp_path))
    sup = _make_legacy_env(tmp_path)
    wid = sup.add_work("S5_cad", "release_gate", "release", "o",
                       owner_required=True)
    results = sup.run_supervisor(steps=1)
    assert results and results[0]["action"] == "decision"
    did = results[0]["decision"]["decision_id"]

    with sup.connect() as c:
        row = c.execute(
            "SELECT decision_id, project_id, status FROM decisions "
            "WHERE decision_id=?", (did,)).fetchone()
        assert row is not None
        assert row["project_id"] == "P1"
        assert row["status"] == "proposed"
        w = c.execute(
            "SELECT status, decision_id FROM supervisor_work_items WHERE work_id=?",
            (wid,)).fetchone()
        assert w["status"] == "blocked_decision"
        assert w["decision_id"] == did


def test_legacy_db_keeps_old_decisions_table_data(tmp_path, monkeypatch):
    """legacy 兼容路径绝不破坏旧 decisions 表数据。"""
    monkeypatch.setenv("AIPD_OUTPUT_DIR", str(tmp_path))
    sup = _make_legacy_env(tmp_path)
    # 预置一条历史决策（旧数据）
    with sup.connect() as c:
        c.execute(
            "INSERT INTO decisions(decision_id,project_id,topic,status,"
            "options_json,created_at) VALUES('D-OLD','P1','old','resolved','[]',"
            "'2024-01-01T00:00:00Z')")
    wid = sup.add_work("S5_cad", "release_gate", "release", "o",
                       owner_required=True)
    results = sup.run_supervisor(steps=1)
    did = results[0]["decision"]["decision_id"]
    with sup.connect() as c:
        old = c.execute(
            "SELECT status FROM decisions WHERE decision_id='D-OLD'").fetchone()
    assert old is not None and old["status"] == "resolved"  # 旧数据未动
    assert did != "D-OLD"


# ---------------------------------------------------------------------------
# 3) canonical 表存在但未传 state_db → fail-closed
# ---------------------------------------------------------------------------
def test_legacy_persist_fails_closed_on_canonical_db(tmp_path):
    db_path = str(tmp_path / "state.db")
    db = AIPDStateDB(db_path)
    db.ensure_default_tenant("default")
    db.init_project("default", "P1", "P1", "goal")
    sup = Supervisor(db_path, tenant_id="default", project_id="P1")  # 未传 state_db
    sup.init_lifecycle()
    sup.add_work("S5_cad", "release_gate", "release", "o", owner_required=True)
    with pytest.raises(RuntimeError, match="canonical decisions table detected"):
        sup.run_supervisor(steps=1)
