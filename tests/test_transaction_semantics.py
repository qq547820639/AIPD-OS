"""P2-M1: Transaction semantics tests.

验证 state/transaction.py 的 commit/rollback 行为。
"""
from __future__ import annotations

import sqlite3

import pytest

from aipd_os.state.transaction import transaction


@pytest.fixture
def conn(tmp_path):
    """创建临时 SQLite 连接。"""
    db_path = str(tmp_path / "test.db")
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    c.execute("""
        CREATE TABLE test_entities (
            id TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    c.commit()
    yield c
    c.close()


class TestTransactionCommit:
    """事务成功时数据应存在。"""

    def test_commit_persists_data(self, conn):
        with transaction(conn):
            conn.execute(
                "INSERT INTO test_entities(id, value) VALUES (?, ?)",
                ("A", "alpha"))
        # 验证数据存在
        row = conn.execute(
            "SELECT value FROM test_entities WHERE id=?", ("A",)).fetchone()
        assert row is not None
        assert row["value"] == "alpha"

    def test_commit_multiple_rows(self, conn):
        with transaction(conn):
            conn.execute(
                "INSERT INTO test_entities(id, value) VALUES (?, ?)",
                ("A", "alpha"))
            conn.execute(
                "INSERT INTO test_entities(id, value) VALUES (?, ?)",
                ("B", "beta"))
        rows = conn.execute("SELECT * FROM test_entities").fetchall()
        assert len(rows) == 2


class TestTransactionRollback:
    """异常时数据应不存在。"""

    def test_rollback_on_exception(self, conn):
        try:
            with transaction(conn):
                conn.execute(
                    "INSERT INTO test_entities(id, value) VALUES (?, ?)",
                    ("A", "alpha"))
                raise ValueError("simulated failure")
        except ValueError:
            pass
        # 验证数据不存在（已 rollback）
        row = conn.execute(
            "SELECT value FROM test_entities WHERE id=?", ("A",)).fetchone()
        assert row is None

    def test_rollback_on_sql_error(self, conn):
        try:
            with transaction(conn):
                conn.execute(
                    "INSERT INTO test_entities(id, value) VALUES (?, ?)",
                    ("A", "alpha"))
                # 插入重复主键 → IntegrityError
                conn.execute(
                    "INSERT INTO test_entities(id, value) VALUES (?, ?)",
                    ("A", "duplicate"))
        except sqlite3.IntegrityError:
            pass
        # 验证第一条也不存在（整个事务 rollback）
        row = conn.execute(
            "SELECT value FROM test_entities WHERE id=?", ("A",)).fetchone()
        assert row is None


class TestTransactionAtomicity:
    """事务原子性。"""

    def test_all_or_nothing(self, conn):
        """部分成功不应留下半状态。"""
        try:
            with transaction(conn):
                conn.execute(
                    "INSERT INTO test_entities(id, value) VALUES (?, ?)",
                    ("A", "alpha"))
                conn.execute(
                    "INSERT INTO test_entities(id, value) VALUES (?, ?)",
                    ("A", "duplicate"))  # 失败
        except sqlite3.IntegrityError:
            pass
        # A 也不存在
        rows = conn.execute("SELECT * FROM test_entities").fetchall()
        assert len(rows) == 0

    def test_sequential_transactions_independent(self, conn):
        """独立事务不应互相影响。"""
        with transaction(conn):
            conn.execute(
                "INSERT INTO test_entities(id, value) VALUES (?, ?)",
                ("A", "alpha"))
        try:
            with transaction(conn):
                conn.execute(
                    "INSERT INTO test_entities(id, value) VALUES (?, ?)",
                    ("A", "duplicate"))
        except sqlite3.IntegrityError:
            pass
        # A 仍然存在（第一个事务已 commit）
        row = conn.execute(
            "SELECT value FROM test_entities WHERE id=?", ("A",)).fetchone()
        assert row is not None
        assert row["value"] == "alpha"
