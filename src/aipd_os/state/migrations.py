"""schema 迁移运行器。

使用 ``schema_migrations`` 表记录已应用的迁移版本，按顺序执行 ``up``，
并支持按目标版本回滚到任意历史版本（执行 ``down``）。

迁移列表中的每个条目：``{"version": int, "name": str, "up": [sql|callable], "down": [sql|callable]}``。
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List

from .db import SCHEMA as V1_INITIAL_SCHEMA

# v1 初始 schema（多租户多项目）
MIGRATIONS: List[Dict[str, Any]] = [
    {
        "version": 1,
        "name": "multi_tenant_initial_schema",
        "up": [V1_INITIAL_SCHEMA],
        "down": [
            "DROP TABLE IF EXISTS backups;",
            "DROP TABLE IF EXISTS checkpoints;",
            "DROP TABLE IF EXISTS audit_log;",
            "DROP TABLE IF EXISTS gates;",
            "DROP TABLE IF EXISTS changes;",
            "DROP TABLE IF EXISTS dependencies;",
            "DROP TABLE IF EXISTS risks;",
            "DROP TABLE IF EXISTS deliverables;",
            "DROP TABLE IF EXISTS decisions;",
            "DROP TABLE IF EXISTS fact_evidence;",
            "DROP TABLE IF EXISTS evidence;",
            "DROP TABLE IF EXISTS facts;",
            "DROP TABLE IF EXISTS projects;",
            "DROP TABLE IF EXISTS sessions;",
            "DROP TABLE IF EXISTS user_access;",
            "DROP TABLE IF EXISTS users;",
            "DROP TABLE IF EXISTS tenants;",
        ],
    },
    # v5.8 Commit 9：Idea Domain（canonical idea 表；对已存在 v1 库就地 CREATE）。
    {
        "version": 2,
        "name": "idea_domain",
        "up": [
            "CREATE TABLE IF NOT EXISTS ideas ("
            " idea_id TEXT NOT NULL, project_id TEXT NOT NULL,"
            " tenant_id TEXT NOT NULL DEFAULT 'default',"
            " title TEXT NOT NULL DEFAULT '', raw_input TEXT NOT NULL DEFAULT '',"
            " goal TEXT NOT NULL DEFAULT '', problem TEXT NOT NULL DEFAULT '',"
            " target_user TEXT NOT NULL DEFAULT '', desired_outcome TEXT NOT NULL DEFAULT '',"
            " constraints_json TEXT NOT NULL DEFAULT '{}',"
            " source TEXT NOT NULL DEFAULT '', lifecycle_status TEXT NOT NULL DEFAULT 'raw',"
            " version_no INTEGER NOT NULL DEFAULT 1,"
            " created_at TEXT NOT NULL, updated_at TEXT NOT NULL,"
            " PRIMARY KEY (idea_id, project_id, tenant_id));",
        ],
        "down": ["DROP TABLE IF EXISTS ideas;"],
    },
    # v5.8 Commit 10：Claim Domain（命题表；idea_id 为软引用，不强外键）。
    {
        "version": 3,
        "name": "claim_domain",
        "up": [
            "CREATE TABLE IF NOT EXISTS claims ("
            " claim_id TEXT NOT NULL, project_id TEXT NOT NULL,"
            " tenant_id TEXT NOT NULL DEFAULT 'default',"
            " idea_id TEXT NOT NULL DEFAULT '', claim_type TEXT NOT NULL,"
            " statement TEXT NOT NULL, epistemic_status TEXT NOT NULL DEFAULT 'A',"
            " lifecycle_status TEXT NOT NULL DEFAULT 'active',"
            " confidence REAL NOT NULL DEFAULT 0.5,"
            " source TEXT NOT NULL DEFAULT '', version_no INTEGER NOT NULL DEFAULT 1,"
            " created_at TEXT NOT NULL, updated_at TEXT NOT NULL,"
            " PRIMARY KEY (claim_id, project_id, tenant_id));",
        ],
        "down": ["DROP TABLE IF EXISTS claims;"],
    },
    # v5.8 Commit 11：EvidenceRelation（claim ↔ evidence 关系表）。
    {
        "version": 4,
        "name": "claim_evidence_relations",
        "up": [
            "CREATE TABLE IF NOT EXISTS claim_evidence_relations ("
            " relation_id TEXT NOT NULL, project_id TEXT NOT NULL,"
            " tenant_id TEXT NOT NULL DEFAULT 'default',"
            " claim_id TEXT NOT NULL, evidence_id TEXT NOT NULL,"
            " relation_type TEXT NOT NULL, strength REAL NOT NULL DEFAULT 0.5,"
            " applicability TEXT NOT NULL DEFAULT '',"
            " reasoning_summary TEXT NOT NULL DEFAULT '',"
            " limitations TEXT NOT NULL DEFAULT '',"
            " review_status TEXT NOT NULL DEFAULT 'pending',"
            " created_by TEXT NOT NULL DEFAULT 'system',"
            " version_no INTEGER NOT NULL DEFAULT 1,"
            " created_at TEXT NOT NULL, updated_at TEXT NOT NULL,"
            " PRIMARY KEY (relation_id, project_id, tenant_id),"
            " UNIQUE (claim_id, evidence_id, relation_type, project_id, tenant_id));",
        ],
        "down": ["DROP TABLE IF EXISTS claim_evidence_relations;"],
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _conn(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.executescript("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _ensure_schema_migrations(conn: sqlite3.Connection) -> None:
    conn.executescript(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL);"
    )


def applied_versions(db_path: str) -> List[int]:
    with _conn(db_path) as c:
        _ensure_schema_migrations(c)
        rows = c.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
    return [r[0] for r in rows]


def _run_steps(conn: sqlite3.Connection, steps: List[Any]) -> None:
    for step in steps:
        if callable(step):
            step(conn)
        else:
            conn.executescript(step)


def migrate(db_path: str) -> List[int]:
    """应用所有未执行的迁移，返回本次应用到的版本列表。"""
    applied = []
    with _conn(db_path) as c:
        _ensure_schema_migrations(c)
        done = {r[0] for r in c.execute("SELECT version FROM schema_migrations").fetchall()}
        for mig in sorted(MIGRATIONS, key=lambda m: m["version"]):
            if mig["version"] in done:
                continue
            _run_steps(c, mig["up"])
            c.execute("INSERT INTO schema_migrations(version,name,applied_at) VALUES(?,?,?)",
                      (mig["version"], mig["name"], _now()))
            applied.append(mig["version"])
    return applied


def rollback(db_path: str, target: int) -> List[int]:
    """回滚到指定目标版本（不含 target），返回被回滚的版本列表。"""
    rolled_back = []
    with _conn(db_path) as c:
        _ensure_schema_migrations(c)
        done = sorted(r[0] for r in c.execute("SELECT version FROM schema_migrations").fetchall())
        for version in reversed(done):
            if version <= target:
                break
            mig = next(m for m in MIGRATIONS if m["version"] == version)
            _run_steps(c, mig["down"])
            c.execute("DELETE FROM schema_migrations WHERE version=?", (version,))
            rolled_back.append(version)
    return rolled_back


def current_version(db_path: str) -> int:
    try:
        versions = applied_versions(db_path)
    except sqlite3.DatabaseError:
        return 0
    return max(versions) if versions else 0


__all__ = ["MIGRATIONS", "migrate", "rollback", "applied_versions", "current_version"]
