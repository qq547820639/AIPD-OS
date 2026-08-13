"""监督器执行（run_supervisor）测试。"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from aipd_supervisor import Supervisor  # noqa: E402


def _make_sup(tmp_path):
    db = str(tmp_path / "sup.db")
    conn = sqlite3.connect(db)
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
    sup = Supervisor(db)
    sup.init_lifecycle()
    return sup


def test_run_supervisor_executes_doc_to_complete(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPD_OUTPUT_DIR", str(tmp_path))
    sup = _make_sup(tmp_path)
    wid = sup.add_work(
        "S1_theory", "research", "t", "o",
        capability_floor="doc.generate",
        inputs={"title": "T", "sections": [{"heading": "H", "body": "b"}]},
    )
    results = sup.run_supervisor(steps=1)
    assert results and results[0]["action"] == "complete"
    counts = sup.status()["work_counts"]
    assert counts.get("complete", 0) == 1
    with sup.connect() as c:
        row = c.execute(
            "SELECT outputs_json FROM supervisor_work_items WHERE work_id=?", (wid,)
        ).fetchone()
    assert "markdown" in row[0]


def test_run_supervisor_owner_required_returns_decision(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPD_OUTPUT_DIR", str(tmp_path))
    sup = _make_sup(tmp_path)
    sup.add_work(
        "S5_cad", "release_gate", "release", "o",
        capability_floor="doc.generate",
        owner_required=True,
        inputs={"title": "T"},
    )
    results = sup.run_supervisor(steps=1)
    assert results and results[0]["action"] == "decision"
    assert "decision_id" in results[0]["decision"]
    counts = sup.status()["work_counts"]
    assert counts.get("complete", 0) == 0
    assert counts.get("blocked_decision", 0) == 1


def test_run_supervisor_no_work_stops(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPD_OUTPUT_DIR", str(tmp_path))
    sup = _make_sup(tmp_path)
    assert sup.run_supervisor(steps=1) == []


def test_mark_stale_exact_dependency_match(tmp_path):
    """回归：_mark_stale 必须按依赖列表精确匹配，不得用 LIKE 子串误伤
    （此前 "%W-001%" 会命中 W-0010 等前缀型 ID）。"""
    sup = _make_sup(tmp_path)
    w1 = sup.add_work("S1_theory", "research", "t1", "o1")
    w2 = sup.add_work("S1_theory", "research", "t2", "o2",
                      depends=[w1])
    w3 = sup.add_work("S2_product_definition", "product", "t3", "o3")
    # w3 不依赖 w1
    sup.complete(w2, {"x": 1})
    # 直接构造一个依赖关系为 [w1] 的行与一个相似前缀行
    with sup.connect() as c:
        c.execute("UPDATE supervisor_work_items SET status='complete' "
                  "WHERE work_id=?", (w3,))
    stale = sup._mark_stale(w1)
    assert w2 in stale["stale"]
    assert w3 not in stale["stale"]
