"""统一 SQLite 连接策略。

提供 ConnectionFactory 统一所有 SQLite 连接的 pragma 配置、
事务语义和错误映射。所有 store 应通过本模块获取连接，
而非各自调用 sqlite3.connect()。

P2-M1: Common DB Infrastructure
"""
from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

# ── 统一 pragma 配置 ──────────────────────────────────────────
# 所有 AIPD-OS SQLite 连接必须应用这些 pragma。
# WAL 模式暂不全局开启——需要在 Windows/macOS/Linux/共享文件系统
# 和 test isolation 场景验证后再决定。当前使用默认 DELETE journal。
_PRAGMAS: list[str] = [
    "PRAGMA foreign_keys = ON",
    "PRAGMA busy_timeout = 5000",       # 5s 等待锁
    "PRAGMA timeout = 10000",            # 10s 连接超时
    "PRAGMA synchronous = NORMAL",       # 性能/安全平衡
]


class ConnectionFactory:
    """统一 SQLite 连接工厂。

    所有 store 通过 ``ConnectionFactory(path)`` 获取连接，
    保证 pragma 一致、row_factory 统一、事务边界清晰。
    """

    def __init__(self, db_path: str | Path) -> None:
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        """创建新连接并应用统一 pragma。"""
        conn = sqlite3.connect(str(self.path), timeout=10)
        conn.row_factory = sqlite3.Row
        for pragma in _PRAGMAS:
            conn.execute(pragma)
        return conn

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """事务上下文管理器。

        用法::

            with factory.transaction() as conn:
                conn.execute("INSERT ...")
                conn.execute("UPDATE ...")
            # 自动 commit；异常自动 rollback
        """
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        """非事务连接上下文（自动 commit 每条语句）。

        用于只读查询或不需要原子性的单条写操作。
        """
        conn = self.connect()
        try:
            yield conn
        finally:
            conn.close()


def apply_pragmas(conn: sqlite3.Connection) -> None:
    """对已有连接应用统一 pragma（兼容层）。"""
    for pragma in _PRAGMAS:
        conn.execute(pragma)
