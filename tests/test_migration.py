"""v4 → v5 迁移与回滚（旧单项目库 → 多租户库 → 恢复旧格式）。"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in [ROOT / "scripts", ROOT / "migrations"]:
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from aipd_store import SCHEMA as LEGACY_SCHEMA  # noqa: E402
from rollback_v5 import rollback_v5  # noqa: E402
from v4_to_v5 import migrate_legacy  # noqa: E402

from aipd_os.state.db import AIPDStateDB  # noqa: E402


def _build_legacy(path: str) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(LEGACY_SCHEMA)
    conn.execute(
        "INSERT INTO projects(project_id,name,goal,gate,status,version,owner_policy,created_at,updated_at) "
        "VALUES('legacy-1','Legacy Project','migrate me','G1','active','0.2.0','AI','2024-01-01T00:00:00Z',"
        "'2024-01-02T00:00:00Z')")
    conn.execute(
        "INSERT INTO facts(fact_id,project_id,key,value_json,status,confidence,created_at,updated_at) "
        "VALUES('F-001','legacy-1','latency','42','V',0.9,'2024-01-01T00:00:00Z','2024-01-01T00:00:00Z')")
    conn.execute(
        "INSERT INTO evidence(evidence_id,project_id,kind,title,created_at) "
        "VALUES('E-001','legacy-1','paper','Some paper','2024-01-01T00:00:00Z')")
    conn.execute(
        "INSERT INTO fact_evidence(fact_id,evidence_id,relation) VALUES('F-001','E-001','supports')")
    conn.execute(
        "INSERT INTO decisions(decision_id,project_id,topic,recommendation,options_json,status,created_at) "
        "VALUES('D-001','legacy-1','pick model','use A','[\"A\",\"B\"]','resolved','2024-01-01T00:00:00Z')")
    conn.execute(
        "INSERT INTO deliverables(deliverable_id,project_id,type,status,updated_at) "
        "VALUES('DEL-001','legacy-1','spec','planned','2024-01-01T00:00:00Z')")
    conn.execute(
        "INSERT INTO risks(risk_id,project_id,title,status,updated_at) "
        "VALUES('RISK-001','legacy-1','schedule risk','open','2024-01-01T00:00:00Z')")
    conn.execute(
        "INSERT INTO dependencies(project_id,source_type,source_id,target_type,target_id,relation) "
        "VALUES('legacy-1','fact','F-001','deliverable','DEL-001','affects')")
    conn.execute(
        "INSERT INTO changes(project_id,object_type,object_id,action,created_at) "
        "VALUES('legacy-1','fact','F-001','create','2024-01-01T00:00:00Z')")
    conn.execute(
        "INSERT INTO gates(project_id,gate,result,created_at) "
        "VALUES('legacy-1','G1','pass','2024-01-01T00:00:00Z')")
    conn.commit()
    conn.close()


def test_migrate_then_rollback(tmp_path):
    legacy = str(tmp_path / "legacy.db")
    new = str(tmp_path / "state.db")
    restored = str(tmp_path / "restored.db")

    _build_legacy(legacy)

    # 迁移到多租户
    stats = migrate_legacy(legacy, new, tenant_id="default")
    assert stats["project_id"] == "legacy-1"
    assert stats["counts"]["facts"] == 1

    db = AIPDStateDB(new)
    assert db.get_project("default", "legacy-1")["name"] == "Legacy Project"
    assert db.get_project("default", "legacy-1")["gate"] == "G1"
    assert db.list_facts("default", "legacy-1")[0]["value"] == 42
    assert db.list_decisions("default", "legacy-1")[0]["status"] == "resolved"
    assert len(db.list_deliverables("default", "legacy-1")) == 1
    assert len(db.list_risks("default", "legacy-1")) == 1
    assert len(db.list_dependencies("default", "legacy-1")) == 1
    assert len(db.list_changes("default", "legacy-1")) == 1
    assert len(db.list_gates("default", "legacy-1")) == 1

    # 回滚为旧单项目格式
    rb = rollback_v5(new, restored, tenant_id="default", project_id="legacy-1")
    assert rb["counts"]["facts"] == 1

    conn = sqlite3.connect(restored)
    conn.row_factory = sqlite3.Row
    proj = conn.execute("SELECT * FROM projects").fetchone()
    facts = conn.execute("SELECT * FROM facts").fetchall()
    decisions = conn.execute("SELECT * FROM decisions").fetchall()
    carries = conn.execute(
        "SELECT COUNT(*) n FROM fact_evidence").fetchone()
    gates = conn.execute("SELECT * FROM gates").fetchall()
    conn.close()

    assert proj["project_id"] == "legacy-1"
    assert proj["name"] == "Legacy Project"
    assert facts[0]["key"] == "latency"
    assert json.loads(facts[0]["value_json"]) == 42
    assert decisions[0]["topic"] == "pick model"
    assert carries["n"] == 1
    assert gates[0]["result"] == "pass"
