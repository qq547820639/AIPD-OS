"""迁移运行器核心逻辑。

包含 migrate / rollback / current_version / applied_versions 等公开 API，
以及事务管理、语句拆分等内部工具。
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

from .definitions import MIGRATIONS


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
    # 单条 execute（不用 executescript——后者会隐式 COMMIT，破坏外层事务）
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)"
    )


def _split_statements(script: str) -> list[str]:
    """把多语句脚本拆成单语句列表（引号/注释感知，支持同一行多条语句）。

    用于替代 executescript 执行迁移脚本：executescript 会先隐式 COMMIT，
    使迁移无法纳入事务（非原子）；拆分后逐条 conn.execute，保持外层事务。
    """
    statements: list[str] = []
    buf = ""
    in_single = False
    in_double = False
    in_comment = False
    i = 0
    n = len(script)
    while i < n:
        ch = script[i]
        nxt = script[i + 1] if i + 1 < n else ""
        if in_comment:
            buf += ch
            if ch == "\n":
                in_comment = False
            i += 1
            continue
        if ch == "-" and nxt == "-":
            buf += "--"
            in_comment = True
            i += 2
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        buf += ch
        if ch == ";" and not in_single and not in_double:
            stmt = buf.strip()
            if stmt:
                statements.append(stmt)
            buf = ""
        i += 1
    if buf.strip():
        statements.append(buf.strip())
    return statements


def _exec_script(conn: sqlite3.Connection, script: str) -> None:
    """事务内执行多语句脚本（不触发隐式 COMMIT）。"""
    for stmt in _split_statements(script):
        if stmt:
            conn.execute(stmt)


def applied_versions(db_path: str) -> list[int]:
    with _conn(db_path) as c:
        _ensure_schema_migrations(c)
        rows = c.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
    return [r[0] for r in rows]


def _run_steps(conn: sqlite3.Connection, steps: list[Any]) -> None:
    for step in steps:
        if callable(step):
            step(conn)
        else:
            _exec_script(conn, step)


def migrate(db_path: str) -> list[int]:
    """应用所有未执行的迁移，返回本次应用到的版本列表。

    整个迁移循环包在 ``BEGIN IMMEDIATE`` 事务内：
    - 并发迁移串行化（第二个进程阻塞等待，拿到锁后看到已应用版本即跳过）；
    - 迁移步骤与 schema_migrations 记录同事务提交（中途失败整体回滚，
      不再出现「DDL 已变但版本未记录」的半迁移状态）。
    """
    applied: list[int] = []
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        conn.executescript("PRAGMA foreign_keys = ON;")
        conn.execute("BEGIN IMMEDIATE")
        _ensure_schema_migrations(conn)
        done = {r[0] for r in conn.execute(
            "SELECT version FROM schema_migrations").fetchall()}
        for mig in sorted(MIGRATIONS, key=lambda m: m["version"]):
            if mig["version"] in done:
                continue
            _run_steps(conn, mig["up"])
            conn.execute("INSERT INTO schema_migrations(version,name,applied_at) VALUES(?,?,?)",  # noqa: E501
                         (mig["version"], mig["name"], _now()))
            applied.append(mig["version"])
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return applied


def rollback(db_path: str, target: int) -> list[int]:
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
    """只读探测当前 schema 版本（不建表、不迁移——供 health_check 等
    无副作用探测使用；未初始化的库返回 0）。"""
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        try:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name='schema_migrations'").fetchone()
            if row is None:
                return 0
            rows = conn.execute(
                "SELECT version FROM schema_migrations ORDER BY version").fetchall()
        finally:
            conn.close()
    except sqlite3.DatabaseError:
        return 0
    return max([r[0] for r in rows]) if rows else 0
