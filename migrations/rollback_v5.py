#!/usr/bin/env python3
"""把 v5 多租户库回滚/导出为旧版单项目 sqlite（aipd_store schema）。

用法：
  python migrations/rollback_v5.py --new state.db --legacy legacy_restored.db \
      [--tenant default] [--project-id <id>]

提供 :func:`rollback_v5` 供测试/程序化调用。
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



def _ensure_legacy_schema(conn: sqlite3.Connection) -> None:
    # 复用 v4_to_v5 的旧 schema 定义
    from v4_to_v5 import LEGACY_SCHEMA
    conn.executescript(LEGACY_SCHEMA)


def rollback_v5(new_path: str, legacy_path: str, tenant_id: str = "default",
                project_id: Optional[str] = None) -> Dict[str, Any]:
    """把新库指定 tenant/project 的数据写回旧版单项目库。返回统计。"""
    new_conn = sqlite3.connect(new_path)
    new_conn.row_factory = sqlite3.Row
    new_conn.execute("PRAGMA foreign_keys = ON")

    if project_id is None:
        rows = new_conn.execute("SELECT project_id FROM projects WHERE tenant_id=?",
                                (tenant_id,)).fetchall()
        if not rows:
            new_conn.close()
            raise ValueError(f"no project found in tenant {tenant_id!r}")
        project_id = rows[0]["project_id"]

    def rows(table: str, cols: str) -> List[Dict[str, Any]]:
        # 数据完整性：必须同时按 tenant_id + project_id 过滤。此前只过滤
        # tenant_id，会把同租户下其他项目的数据并入目标项目（多项目回滚
        # 数据污染，且可能触发 UNIQUE(project_id,key,version) 冲突崩溃）。
        return [dict(r) for r in new_conn.execute(
            f"SELECT {cols} FROM {table} WHERE tenant_id=? AND project_id=?",
            (tenant_id, project_id)).fetchall()]

    project_row = new_conn.execute(
        "SELECT * FROM projects WHERE tenant_id=? AND project_id=?",
        (tenant_id, project_id)).fetchone()
    if project_row is None:
        new_conn.close()
        raise ValueError(f"project {project_id!r} not found in tenant {tenant_id!r}")
    project = dict(project_row)

    facts = rows("facts", "*")
    evidence = rows("evidence", "*")
    fact_evidence = rows("fact_evidence", "*")
    decisions = rows("decisions", "*")
    deliverables = rows("deliverables", "*")
    dependencies = rows("dependencies", "*")
    risks = rows("risks", "*")
    changes = rows("changes", "*")
    gates = rows("gates", "*")
    new_conn.close()

    # 写旧库（先建旧 schema）
    Path(legacy_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(legacy_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _ensure_legacy_schema(conn)
    try:
        conn.execute(
            "INSERT INTO projects(project_id,name,goal,gate,status,version,owner_policy,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (project["project_id"], project["name"], project["goal"], project["gate"], project["status"],
             project["version"], project["owner_policy"], project["created_at"], project["updated_at"]))
        for f in facts:
            conn.execute(
                "INSERT INTO facts(fact_id,project_id,key,value_json,unit,tolerance,conditions,status,"
                "confidence,source,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (f["fact_id"], project_id, f["key"], f["value_json"], f.get("unit"), f.get("tolerance"),
                 f.get("conditions"), f["status"], f["confidence"], f.get("source"), f.get("version"),
                 f["created_at"], f["updated_at"]))
        for e in evidence:
            conn.execute(
                "INSERT INTO evidence(evidence_id,project_id,kind,title,url,identifier,accessed_at,quality,"
                "summary,metadata_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (e["evidence_id"], project_id, e["kind"], e["title"], e.get("url"), e.get("identifier"),
                 e.get("accessed_at"), e.get("quality"), e.get("summary"), e.get("metadata_json", "{}"),
                 e["created_at"]))
        for fe in fact_evidence:
            conn.execute("INSERT OR IGNORE INTO fact_evidence(fact_id,evidence_id,relation) VALUES(?,?,?)",
                         (fe["fact_id"], fe["evidence_id"], fe["relation"]))
        for d in decisions:
            conn.execute(
                "INSERT INTO decisions(decision_id,project_id,topic,trigger,recommendation,options_json,"
                "status,choice,comment,created_at,resolved_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (d["decision_id"], project_id, d["topic"], d.get("trigger"), d.get("recommendation"),
                 d.get("options_json", "[]"), d["status"], d.get("choice"), d.get("comment"),
                 d["created_at"], d.get("resolved_at")))
        for dl in deliverables:
            conn.execute(
                "INSERT INTO deliverables(deliverable_id,project_id,type,path,status,version,gate,"
                "metadata_json,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (dl["deliverable_id"], project_id, dl["type"], dl.get("path"), dl["status"],
                 dl.get("version"), dl.get("gate"), dl.get("metadata_json", "{}"), dl["updated_at"]))
        for dep in dependencies:
            conn.execute("INSERT OR IGNORE INTO dependencies(project_id,source_type,source_id,target_type,"
                         "target_id,relation) VALUES(?,?,?,?,?,?)",
                         (project_id, dep["source_type"], dep["source_id"], dep["target_type"],
                          dep["target_id"], dep["relation"]))
        for r in risks:
            conn.execute(
                "INSERT INTO risks(risk_id,project_id,title,probability,impact,mitigation,status,owner,"
                "trigger,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (r["risk_id"], project_id, r["title"], r.get("probability"), r.get("impact"),
                 r.get("mitigation"), r["status"], r.get("owner", "AI"), r.get("trigger"),
                 r.get("updated_at")))
        for ch in changes:
            conn.execute("INSERT INTO changes(project_id,object_type,object_id,action,before_json,after_json,"
                         "reason,created_at) VALUES(?,?,?,?,?,?,?,?)",
                         (project_id, ch["object_type"], ch["object_id"], ch["action"], ch.get("before_json"),
                          ch.get("after_json"), ch.get("reason"), ch["created_at"]))
        for g in gates:
            conn.execute("INSERT INTO gates(project_id,gate,result,checks_json,approved_by,created_at) "
                         "VALUES(?,?,?,?,?,?)",
                         (project_id, g["gate"], g["result"], g.get("checks_json", "{}"),
                          g["approved_by"], g["created_at"]))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {"project_id": project_id, "tenant_id": tenant_id,
            "counts": {"facts": len(facts), "evidence": len(evidence), "decisions": len(decisions),
                       "deliverables": len(deliverables), "risks": len(risks),
                       "dependencies": len(dependencies), "changes": len(changes), "gates": len(gates)}}


def main(argv: Optional[List[str]] = None) -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Rollback v5 multi-tenant DB to legacy single-project")
    parser.add_argument("--new", required=True)
    parser.add_argument("--legacy", required=True)
    parser.add_argument("--tenant", default="default")
    parser.add_argument("--project-id")
    args = parser.parse_args(argv)
    stats = rollback_v5(args.new, args.legacy, args.tenant, args.project_id)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
