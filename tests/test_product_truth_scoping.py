"""Change Set 6 ProductTruth 作用域 + metadata 持久化 + 返工诚实测试（P0-8/9/10）。

覆盖：
- 同一 content 在两个 project 下各自 add → find_id_by_type_and_content 按
  project 正确区分、不串；
- query 按 tenant/project 过滤；get 跨租户/项目 → KeyError；
- metadata round-trip：add 带 metadata → get 回来完全一致（dict 相等）；
- 旧 schema 库（手工建无新列的表）→ 实例化后自动补列、旧数据可读；
- run_rework(无 rework_fn) → status blocked、truth status blocked、
  version 不变（绝不假成功）；
- run_rework(rework_fn=_ok) → succeeded + version bump（回归）；
- lineage 边按 project 隔离。
"""
from __future__ import annotations

import sqlite3

import pytest

from aipd_os.product_truth.lineage import LineageGraph
from aipd_os.product_truth.models import TruthRecord
from aipd_os.product_truth.propagation import PropagationEngine
from aipd_os.product_truth.store import ProductTruthStore


# ---------------------------------------------------------------------------
# a) 同一 content 两个 project → find_id 按 project 区分
# ---------------------------------------------------------------------------
def test_find_id_respects_project_scope(tmp_path):
    db = str(tmp_path / "a.db")
    s1 = ProductTruthStore(db, tenant_id="t1", project_id="p1")
    s2 = ProductTruthStore(db, tenant_id="t1", project_id="p2")
    rid1 = s1.add(TruthRecord("fact", "peak torque 120Nm"))
    rid2 = s2.add(TruthRecord("fact", "peak torque 120Nm"))
    assert rid1 != rid2

    # 各自 scope 查到自己的记录
    assert s1.find_id_by_type_and_content("fact", "peak torque 120Nm") == rid1
    assert s2.find_id_by_type_and_content("fact", "peak torque 120Nm") == rid2

    # 同一库、显式 scope：跨 project 不去重
    s_plain = ProductTruthStore(db)
    assert s_plain.find_id_by_type_and_content("fact", "peak torque 120Nm",
                                               tenant_id="t1", project_id="p1") == rid1
    assert s_plain.find_id_by_type_and_content("fact", "peak torque 120Nm",
                                               tenant_id="t1", project_id="p2") == rid2
    # 默认 scope（'default'）查不到
    assert s_plain.find_id_by_type_and_content("fact", "peak torque 120Nm") is None


# ---------------------------------------------------------------------------
# b) query 按 tenant/project 过滤；get 跨 scope → KeyError
# ---------------------------------------------------------------------------
def test_query_and_get_scope_filtered(tmp_path):
    s = ProductTruthStore(str(tmp_path / "b.db"))
    rid_p1 = s.add(TruthRecord("fact", "in p1"), project_id="p1")
    rid_p2 = s.add(TruthRecord("fact", "in p2"), project_id="p2")

    # 默认 scope=default 查不到
    assert s.query(record_type="fact") == []
    assert [r.record_id for r in s.query(record_type="fact", project_id="p1")] == [rid_p1]
    assert [r.record_id for r in s.query(record_type="fact", project_id="p2")] == [rid_p2]
    assert s.list_all(project_id="p1")[0].record_id == rid_p1

    # 跨 scope get → KeyError
    with pytest.raises(KeyError):
        s.get(rid_p1, project_id="p2")
    assert s.get(rid_p1, project_id="p1").record_id == rid_p1


# ---------------------------------------------------------------------------
# c) metadata round-trip
# ---------------------------------------------------------------------------
def test_metadata_roundtrip(tmp_path):
    s = ProductTruthStore(str(tmp_path / "c.db"))
    meta = {"source_file": "bom.csv", "tags": ["x", "y"], "nested": {"k": 1}}
    rid = s.add(TruthRecord("fact", "meta fact", metadata=meta))
    rec = s.get(rid)
    assert rec.metadata == meta
    assert rec.to_dict()["metadata"] == meta

    # update 支持 metadata 整体替换
    new_meta = {"tags": ["z"]}
    s.update(rid, metadata=new_meta)
    assert s.get(rid).metadata == new_meta


# ---------------------------------------------------------------------------
# d) 旧 schema 库自动补列、旧数据可读
# ---------------------------------------------------------------------------
def test_old_schema_auto_migrates(tmp_path):
    db_path = str(tmp_path / "old.db")
    conn = sqlite3.connect(db_path)
    conn.executescript("""
    CREATE TABLE product_truth (
      id TEXT PRIMARY KEY, record_type TEXT NOT NULL, content TEXT NOT NULL,
      source TEXT NOT NULL DEFAULT '{}', trust_level TEXT NOT NULL,
      effective_at TEXT, expires_at TEXT, version INTEGER NOT NULL DEFAULT 1,
      status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );
    CREATE TABLE truth_lineage (
      edge_id INTEGER PRIMARY KEY AUTOINCREMENT, upstream_id TEXT NOT NULL,
      downstream_id TEXT NOT NULL, relation TEXT NOT NULL DEFAULT 'affects',
      created_at TEXT NOT NULL, UNIQUE(upstream_id, downstream_id, relation)
    );
    CREATE TABLE rework_tasks (
      task_id TEXT PRIMARY KEY, truth_id TEXT NOT NULL, reason TEXT NOT NULL,
      attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL,
      status TEXT NOT NULL DEFAULT 'pending', backoff_until TEXT,
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    """)
    conn.execute(
        "INSERT INTO product_truth(id,record_type,content,source,trust_level,version,"
        "status,created_at,updated_at) VALUES('T-001','fact','legacy truth','{}',"
        "'unverified',1,'active','2024-01-01T00:00:00+00:00','2024-01-01T00:00:00+00:00')")
    conn.commit()
    conn.close()

    s = ProductTruthStore(db_path)  # 实例化自动补列
    rec = s.get("T-001")
    assert rec.content == "legacy truth"
    assert rec.metadata == {}
    # 旧行落在默认 scope
    assert [r.record_id for r in s.query(record_type="fact")] == ["T-001"]
    # 新列可写
    rid2 = s.add(TruthRecord("fact", "new truth", metadata={"k": "v"}))
    assert s.get(rid2).metadata == {"k": "v"}


# ---------------------------------------------------------------------------
# e) run_rework 无 executor → blocked，绝不假成功
# ---------------------------------------------------------------------------
def test_run_rework_without_executor_refuses_fake_success(tmp_path):
    s = ProductTruthStore(str(tmp_path / "d.db"))
    lineage = LineageGraph(s)
    eng = PropagationEngine(s, lineage)
    up = s.add(TruthRecord("fact", "up"))
    down = s.add(TruthRecord("requirement", "down"))
    lineage.add_edge(up, down)
    res = eng.on_upstream_changed(up)
    task_id = res["tasks"][0]["task_id"]
    v_before = s.get(down).version

    r = eng.run_rework(task_id)  # 无 rework_fn
    assert r["reworked"] is False
    assert r["status"] == "blocked"
    assert "refusing fake success" in r["reason"]
    assert s.get(down).status == "blocked"
    assert s.get(down).version == v_before
    assert eng.get_task(task_id).status == "blocked"


# ---------------------------------------------------------------------------
# f) run_rework 有 executor → succeeded + version bump（回归）
# ---------------------------------------------------------------------------
def test_run_rework_with_executor_succeeds(tmp_path):
    s = ProductTruthStore(str(tmp_path / "e.db"))
    lineage = LineageGraph(s)
    eng = PropagationEngine(s, lineage)
    up = s.add(TruthRecord("fact", "up"))
    down = s.add(TruthRecord("requirement", "down"))
    lineage.add_edge(up, down)
    res = eng.on_upstream_changed(up)
    task_id = res["tasks"][0]["task_id"]

    r = eng.run_rework(task_id, rework_fn=lambda tid: True)
    assert r["reworked"] is True
    assert r["status"] == "succeeded"
    assert r["new_version"] == 2
    assert s.get(down).status == "active"
    assert s.get(down).version == 2


# ---------------------------------------------------------------------------
# g) lineage 边按 project 隔离
# ---------------------------------------------------------------------------
def test_lineage_scope_isolated(tmp_path):
    db = str(tmp_path / "f.db")
    s1 = ProductTruthStore(db, tenant_id="t", project_id="p1")
    s2 = ProductTruthStore(db, tenant_id="t", project_id="p2")
    a1 = s1.add(TruthRecord("fact", "a1"))
    b1 = s1.add(TruthRecord("requirement", "b1"))
    a2 = s2.add(TruthRecord("fact", "a2"))
    b2 = s2.add(TruthRecord("requirement", "b2"))

    g1 = LineageGraph(s1)
    g2 = LineageGraph(s2)
    g1.add_edge(a1, b1)
    g2.add_edge(a2, b2)

    assert g1.downstream_of(a1) == [b1]
    assert g2.downstream_of(a2) == [b2]
    # 默认 scope（'default'）看不到任何边
    g0 = LineageGraph(ProductTruthStore(db))
    assert g0.edges() == []
    # 显式 scope 可见
    assert len(g0.edges(tenant_id="t", project_id="p1")) == 1
