"""统一事务上下文管理。

提供 TransactionContext 用于在同一 SQLite 连接上执行多个 repository 操作，
保证 commit/rollback 语义一致。

P2-M1: State Infrastructure Foundation
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Generator


@contextmanager
def transaction(conn: sqlite3.Connection) -> Generator[sqlite3.Connection, None, None]:
    """事务上下文管理器。

    用法::

        with transaction(conn) as tx:
            repo_a.save(tx, ...)
            repo_b.save(tx, ...)
        # 自动 commit；异常自动 rollback

    注意：如果 conn 已经在一个事务中（例如通过 BEGIN IMMEDIATE），
    本 context manager 不会嵌套 BEGIN，只在退出时 commit/rollback。
    """
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


@contextmanager
def transaction_from_path(db_path: str) -> Generator[sqlite3.Connection, None, None]:
    """从事务上下文管理器创建连接并管理事务。

    用法::

        with transaction_from_path("/path/to/db") as conn:
            repo.save(conn, ...)
    """
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
