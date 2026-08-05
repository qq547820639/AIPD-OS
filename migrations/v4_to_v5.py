#!/usr/bin/env python3
"""把旧版单项目 sqlite（aipd_store schema）迁移到 v5 多租户多项目 schema。

用法：
  python migrations/v4_to_v5.py --legacy legacy.db --new state.db \
      [--tenant default] [--project-id <id>] [--encryption-key KEY]

提供 :func:`migrate_legacy` 供测试/程序化调用。
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

SRC = str(Path(__file__).resolve().parents[1] / "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from aipd_os.state.db import AIPDStateDB, now_iso  # noqa: E402
from aipd_os.state import migrations as mig  # noqa: E402

# 旧版单项目 schema（与 scripts/aipd_store.py 一致）
LEGACY_SCHEMA = r"""
CREATE TABLE IF NOT EXISTS projects (
  project_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  goal TEXT NOT NULL,
  gate TEXT NOT NULL DEFAULT 'G0',
  status TEXT NOT NULL DEFAULT 'active',
  version TEXT NOT NULL DEFAULT '0.1.0',
  owner_policy TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS facts (
  fact_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  key TEXT NOT NULL,
  value_json TEXT NOT NULL,
  unit TEXT, tolerance TEXT, conditions TEXT,
  status TEXT NOT NULL, confidence REAL NOT NULL DEFAULT 0.5, source TEXT, version TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(project_id, key, version)
);
CREATE TABLE IF NOT EXISTS evidence (
  evidence_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
  kind TEXT NOT NULL, title TEXT NOT NULL, url TEXT, identifier TEXT,
  accessed_at TEXT, quality TEXT, summary TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fact_evidence (
  fact_id TEXT NOT NULL, evidence_id TEXT NOT NULL,
  relation TEXT NOT NULL DEFAULT 'supports',
  PRIMARY KEY(fact_id, evidence_id, relation)
);
CREATE TABLE IF NOT EXISTS decisions (
  decision_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
  topic TEXT NOT NULL, trigger TEXT, recommendation TEXT,
  options_json TEXT NOT NULL DEFAULT '[]', status TEXT NOT NULL DEFAULT 'proposed',
  choice TEXT, comment TEXT, created_at TEXT NOT NULL, resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS deliverables (
  deliverable_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, type TEXT NOT NULL,
  path TEXT, status TEXT NOT NULL DEFAULT 'planned', version TEXT, gate TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}', updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dependencies (
  dependency_id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL,
  source_type TEXT NOT NULL, source_id TEXT NOT NULL,
  target_type TEXT NOT NULL, target_id TEXT NOT NULL, relation TEXT NOT NULL DEFAULT 'affects',
  UNIQUE(project_id, source_type, source_id, target_type, target_id, relation)
);
CREATE TABLE IF NOT EXISTS risks (
  risk_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, title TEXT NOT NULL,
  probability TEXT, impact TEXT, mitigation TEXT, status TEXT NOT NULL DEFAULT 'open',
  owner TEXT NOT NULL DEFAULT 'AI', trigger TEXT, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS changes (
  change_id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL,
  object_type TEXT NOT NULL, object_id TEXT NOT NULL, action TEXT NOT NULL,
  before_json TEXT, after_json TEXT, reason TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS gates (
  gate_record_id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL,
  gate TEXT NOT NULL, result TEXT NOT NULL, checks_json TEXT NOT NULL DEFAULT '{}',
  approved_by TEXT NOT NULL DEFAULT 'AI-internal', created_at TEXT NOT NULL
);
"""


def _connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _read_all(conn: sqlite3.Connection) -> Dict[str, List[Dict[str, Any]]]:
    tables = ["projects", "facts", "evidence", "fact_evidence", "decisions",
              "deliverables", "dependencies", "risks", "changes", "gates"]
    out: Dict[str, List[Dict[str, Any]]] = {}
    for t in tables:
        try:
            rows = conn.execute(f"SELECT * FROM {t}").fetchall()
            out[t] = [dict(r) for r in rows]
        except sqlite3.OperationalError:
            out[t] = []
    return out


def migrate_legacy(legacy_path: str, new_path: str, project_id: Optional[str] = None,
                   tenant_id: str = "default", encryption_key: str = "") -> Dict[str, Any]:
    """把旧版单项目库迁移进新的多租户库。返回统计信息。"""
    conn = _connect(legacy_path)
    data = _read_all(conn)
    conn.close()

    if not data["projects"]:
        raise ValueError("legacy db has no project row")

    src_project = data["projects"][0]
    pid = project_id or src_project["project_id"]

    # 建立新库（多租户 schema + 迁移记录）
    db = AIPDStateDB(new_path, encryption_key=encryption_key)
    mig.migrate(new_path)
    db.ensure_default_tenant(tenant_id)

    ts = now_iso()
    with db.connect() as c:
        c.execute("INSERT OR REPLACE INTO tenants(tenant_id,name,created_at) VALUES(?,?,?)",
                  (tenant_id, "Migrated Tenant", ts))
        c.execute(
            "INSERT INTO projects(project_id,tenant_id,name,goal,gate,status,version,owner_policy,"
            "created_at,updated_at,version_no) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (pid, tenant_id, src_project["name"], src_project["goal"], src_project["gate"],
             src_project["status"], src_project["version"], src_project["owner_policy"],
             src_project["created_at"], src_project["updated_at"], 1))

        for f in data["facts"]:
            c.execute(
                "INSERT INTO facts(fact_id,project_id,tenant_id,key,value_json,unit,tolerance,"
                "conditions,status,confidence,source,version,created_at,updated_at,version_no) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (f["fact_id"], pid, tenant_id, f["key"], f["value_json"], f.get("unit"),
                 f.get("tolerance"), f.get("conditions"), f["status"], f["confidence"],
                 f.get("source"), f.get("version"), f["created_at"], f["updated_at"], 1))

        for e in data["evidence"]:
            c.execute(
                "INSERT INTO evidence(evidence_id,project_id,tenant_id,kind,title,url,identifier,"
                "accessed_at,quality,summary,metadata_json,created_at,version_no) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (e["evidence_id"], pid, tenant_id, e["kind"], e["title"], e.get("url"),
                 e.get("identifier"), e.get("accessed_at"), e.get("quality"), e.get("summary"),
                 e.get("metadata_json", "{}"), e["created_at"], 1))

        for fe in data["fact_evidence"]:
            c.execute("INSERT OR IGNORE INTO fact_evidence(fact_id,project_id,tenant_id,evidence_id,relation) "
                      "VALUES(?,?,?,?,?)", (fe["fact_id"], pid, tenant_id, fe["evidence_id"], fe["relation"]))

        for d in data["decisions"]:
            c.execute(
                "INSERT INTO decisions(decision_id,project_id,tenant_id,topic,trigger,recommendation,"
                "options_json,status,choice,comment,created_at,resolved_at,version_no) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (d["decision_id"], pid, tenant_id, d["topic"], d.get("trigger"),
                 d.get("recommendation"), d.get("options_json", "[]"), d["status"], d.get("choice"),
                 d.get("comment"), d["created_at"], d.get("resolved_at"), 1))

        for dl in data["deliverables"]:
            c.execute(
                "INSERT INTO deliverables(deliverable_id,project_id,tenant_id,type,path,status,version,"
                "gate,metadata_json,updated_at,version_no) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (dl["deliverable_id"], pid, tenant_id, dl["type"], dl.get("path"), dl["status"],
                 dl.get("version"), dl.get("gate"), dl.get("metadata_json", "{}"), dl["updated_at"], 1))

        for dep in data["dependencies"]:
            c.execute("INSERT OR IGNORE INTO dependencies(project_id,tenant_id,source_type,source_id,"
                      "target_type,target_id,relation) VALUES(?,?,?,?,?,?,?)",
                      (pid, tenant_id, dep["source_type"], dep["source_id"], dep["target_type"],
                       dep["target_id"], dep["relation"]))

        for r in data["risks"]:
            c.execute(
                "INSERT INTO risks(risk_id,project_id,tenant_id,title,probability,impact,mitigation,"
                "status,owner,trigger,updated_at,version_no) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (r["risk_id"], pid, tenant_id, r["title"], r.get("probability"), r.get("impact"),
                 r.get("mitigation"), r["status"], r.get("owner", "AI"), r.get("trigger"),
                 r.get("updated_at") or ts, 1))

        for ch in data["changes"]:
            c.execute("INSERT INTO changes(project_id,tenant_id,object_type,object_id,action,before_json,"
                      "after_json,reason,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                      (pid, tenant_id, ch["object_type"], ch["object_id"], ch["action"],
                       ch.get("before_json"), ch.get("after_json"), ch.get("reason"), ch["created_at"]))

        for g in data["gates"]:
            c.execute("INSERT INTO gates(project_id,tenant_id,gate,result,checks_json,approved_by,created_at) "
                      "VALUES(?,?,?,?,?,?,?)",
                      (pid, tenant_id, g["gate"], g["result"], g.get("checks_json", "{}"),
                       g["approved_by"], g["created_at"]))

    return {
        "project_id": pid, "tenant_id": tenant_id,
        "counts": {t: len(data[t]) for t in data},
    }


def main(argv: Optional[List[str]] = None) -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Migrate legacy single-project DB to multi-tenant")
    parser.add_argument("--legacy", required=True)
    parser.add_argument("--new", required=True)
    parser.add_argument("--tenant", default="default")
    parser.add_argument("--project-id")
    parser.add_argument("--encryption-key", default="")
    args = parser.parse_args(argv)
    stats = migrate_legacy(args.legacy, args.new, args.project_id, args.tenant, args.encryption_key)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
