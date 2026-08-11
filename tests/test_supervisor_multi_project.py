"""v5.7 Commit 5：Supervisor Multi-project / Tenant Scope 测试。

覆盖（用 AIPDStateDB 建两个项目 + Supervisor）：
- two projects coexist（构造不抛 "expected exactly one"）；
- run p1 does not mutate p2（work item 只进 p1 队列）；
- decision p1 not visible to p2（p1 proposed decision 不阻塞 p2 owner_required 项）；
- work queue p1 not claimed by p2（next_work(project=p1) 不返回 p2 的 work）；
- capability record correctly scoped；
- 无 project_id + 多项目 → 明确报 project context required；
- 单项目无 project_id → 兼容工作。
"""
from __future__ import annotations

import pytest

from aipd_os.state.db import AIPDStateDB
from aipd_os.supervisor import Supervisor


def _make_env(tmp_path, projects=("P1", "P2")):
    db = AIPDStateDB(str(tmp_path / "state.db"))
    db.ensure_default_tenant("default")
    for pid in projects:
        db.init_project("default", pid, pid, f"goal-{pid}")
    return db


def _make_sup(db, project_id):
    sup = Supervisor(str(db.path), tenant_id="default",
                     project_id=project_id, state_db=db)
    sup.init_lifecycle()
    return sup


# ---------------------------------------------------------------------------
# 1) 两项目共存：构造不抛 "expected exactly one"
# ---------------------------------------------------------------------------
def test_two_projects_coexist(tmp_path):
    db = _make_env(tmp_path)
    sup1 = _make_sup(db, "P1")
    sup2 = _make_sup(db, "P2")
    assert sup1.project_id() == "P1"
    assert sup2.project_id() == "P2"
    assert sup1.tenant_id() == "default"


# ---------------------------------------------------------------------------
# 2) run p1 does not mutate p2（work item 只进 p1 队列）
# ---------------------------------------------------------------------------
def test_run_p1_does_not_mutate_p2(tmp_path):
    db = _make_env(tmp_path)
    sup1 = _make_sup(db, "P1")
    sup2 = _make_sup(db, "P2")
    wid = sup1.add_work("S1_theory", "research", "t", "o")
    assert wid.startswith("W-")

    # p2 队列没有该 work item；p1 队列有
    with sup2.connect() as c:
        p2_rows = c.execute(
            "SELECT work_id FROM supervisor_work_items "
            "WHERE project_id='P2'").fetchall()
        p1_rows = c.execute(
            "SELECT work_id FROM supervisor_work_items "
            "WHERE project_id='P1'").fetchall()
    assert [r["work_id"] for r in p2_rows] == []
    assert [r["work_id"] for r in p1_rows] == [wid]

    # next_work(p2) 不领取 p1 的 work
    assert sup2.next_work(project_id="P2") is None


# ---------------------------------------------------------------------------
# 3) decision p1 not visible to p2
# ---------------------------------------------------------------------------
def test_decision_p1_does_not_block_p2(tmp_path):
    db = _make_env(tmp_path)
    sup1 = _make_sup(db, "P1")
    sup2 = _make_sup(db, "P2")
    sup1.add_work("S5_cad", "release_gate", "r1", "o", owner_required=True)
    sup2.add_work("S5_cad", "release_gate", "r2", "o", owner_required=True)

    # p1 触发决策
    r1 = sup1.run_supervisor(steps=1, project_id="P1")
    assert r1 and r1[0]["action"] == "decision"
    # p2 的 owner_required 项不被 p1 的 proposed decision 阻塞 → 触发自己的决策
    r2 = sup2.run_supervisor(steps=1, project_id="P2")
    assert r2 and r2[0]["action"] == "decision"
    assert r1[0]["decision"]["decision_id"] != r2[0]["decision"]["decision_id"]

    # 决策各自落在正确项目
    decs_p1 = db.list_decisions("default", "P1")
    decs_p2 = db.list_decisions("default", "P2")
    assert len(decs_p1) == 1 and len(decs_p2) == 1
    assert db.get_project("default", "P1")["status"] == "awaiting_owner_decision"
    assert db.get_project("default", "P2")["status"] == "awaiting_owner_decision"


# ---------------------------------------------------------------------------
# 4) work queue p1 not claimed by p2
# ---------------------------------------------------------------------------
def test_work_queue_not_claimed_by_other_project(tmp_path):
    db = _make_env(tmp_path)
    sup1 = _make_sup(db, "P1")
    sup2 = _make_sup(db, "P2")
    wid = sup1.add_work("S1_theory", "research", "t", "o",
                        capability_floor="doc.generate")
    item = sup2.next_work(project_id="P2")
    assert item is None
    # 且 p1 的 work 未被 p2 改状态
    with sup1.connect() as c:
        row = c.execute(
            "SELECT status FROM supervisor_work_items WHERE work_id=?", (wid,)).fetchone()
    assert row["status"] == "queued"


# ---------------------------------------------------------------------------
# 5) capability record correctly scoped
# ---------------------------------------------------------------------------
def test_capability_record_scoped(tmp_path):
    db = _make_env(tmp_path)
    sup1 = _make_sup(db, "P1")
    sup2 = _make_sup(db, "P2")
    cid = sup1.register_capability("doc.generate", "available", provider="local")
    with sup1.connect() as c:
        row = c.execute(
            "SELECT project_id, tenant_id, name FROM supervisor_capabilities "
            "WHERE capability_id=?", (cid,)).fetchone()
    assert row["project_id"] == "P1"
    assert row["tenant_id"] == "default"
    assert row["name"] == "doc.generate"
    # p2 的能力列表不含 p1 的能力
    caps2 = sup2.status()["capabilities"]
    assert caps2 == []


# ---------------------------------------------------------------------------
# 6) 无 project_id + 多项目 → 明确报错
# ---------------------------------------------------------------------------
def test_multi_project_without_project_id_raises(tmp_path):
    db = _make_env(tmp_path)
    sup = Supervisor(str(db.path), tenant_id="default")  # 无 project_id
    with pytest.raises(ValueError, match="project context required"):
        sup.project_id()
    with pytest.raises(ValueError, match="project context required"):
        sup.next_work()


# ---------------------------------------------------------------------------
# 7) 单项目无 project_id → 兼容工作
# ---------------------------------------------------------------------------
def test_single_project_without_project_id_compat(tmp_path):
    db = _make_env(tmp_path, projects=("P1",))
    sup = Supervisor(str(db.path), tenant_id="default")  # 无 project_id
    assert sup.project_id() == "P1"
    wid = sup.add_work("S1_theory", "research", "t", "o")
    assert wid.startswith("W-")
    item = sup.next_work()
    assert item is not None and item["work_id"] == wid


# ---------------------------------------------------------------------------
# 8) tenant 作用域：不同租户项目互不可见
# ---------------------------------------------------------------------------
def test_tenant_scope_isolation(tmp_path):
    db = AIPDStateDB(str(tmp_path / "state.db"))
    db.ensure_default_tenant("default")
    db.init_project("default", "P1", "P1", "g1")
    db.ensure_default_tenant("tenantB")  # 租户必须已存在（系统路径创建）
    db.init_project("tenantB", "PB", "PB", "g2")
    sup_a = _make_sup(db, "P1")  # tenant default
    sup_b = Supervisor(str(db.path), tenant_id="tenantB", project_id="PB",
                       state_db=db)
    sup_b.init_lifecycle()

    wid = sup_a.add_work("S1_theory", "research", "t", "o")
    # tenantB supervisor 看不到 default 租户的 work item
    with sup_b.connect() as c:
        rows = c.execute(
            "SELECT work_id FROM supervisor_work_items WHERE project_id='PB'").fetchall()
    assert rows == []
    assert sup_b.next_work(project_id="PB") is None
    # default 租户内可见
    assert sup_a.next_work(project_id="P1")["work_id"] == wid
