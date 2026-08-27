"""P2-M5: OutboxDispatcher tests。

验证 dispatcher 的 claim → dispatch → complete/retry/terminal 流程。
"""
from __future__ import annotations

import sqlite3

import pytest

from aipd_os.state.dispatcher import OutboxDispatcher
from aipd_os.state.outbox import OutboxRepository


@pytest.fixture
def conn(tmp_path):
    from aipd_os.state import migrations as mig
    path = str(tmp_path / "test.db")
    mig.migrate(path)
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    yield c
    c.close()


class TestDispatcher:
    """OutboxDispatcher 基本流程。"""

    def test_run_once_completes_event(self, conn):
        repo = OutboxRepository(conn)
        repo.append_event("evt-1", "T-A", "P-1", "Issue", "ISS-1",
                          "test_event", {"key": "value"})
        conn.commit()
        dispatcher = OutboxDispatcher(conn, "worker-1")
        dispatcher.register_handler("test_event", lambda e: None)
        results = dispatcher.run_once()
        assert len(results) == 1
        assert results[0]["status"] == "COMPLETED"

    def test_no_handler_marks_terminal(self, conn):
        repo = OutboxRepository(conn)
        repo.append_event("evt-1", "T-A", "P-1", "Issue", "ISS-1",
                          "unknown_event", {})
        conn.commit()
        dispatcher = OutboxDispatcher(conn, "worker-1")
        results = dispatcher.run_once()
        assert len(results) == 1
        assert results[0]["status"] == "TERMINAL_NO_HANDLER"

    def test_timeout_marks_unknown_outcome(self, conn):
        repo = OutboxRepository(conn)
        repo.append_event("evt-1", "T-A", "P-1", "Issue", "ISS-1",
                          "timeout_event", {})
        conn.commit()

        def timeout_handler(e):
            raise TimeoutError("connection timed out")

        dispatcher = OutboxDispatcher(conn, "worker-1")
        dispatcher.register_handler("timeout_event", timeout_handler)
        results = dispatcher.run_once()
        assert len(results) == 1
        assert results[0]["status"] == "UNKNOWN_OUTCOME"

    def test_connection_error_marks_retryable(self, conn):
        repo = OutboxRepository(conn)
        repo.append_event("evt-1", "T-A", "P-1", "Issue", "ISS-1",
                          "network_event", {})
        conn.commit()

        def network_handler(e):
            raise ConnectionError("refused")

        dispatcher = OutboxDispatcher(conn, "worker-1")
        dispatcher.register_handler("network_event", network_handler)
        results = dispatcher.run_once()
        assert len(results) == 1
        assert results[0]["status"] == "RETRYABLE"

    def test_generic_error_marks_terminal(self, conn):
        repo = OutboxRepository(conn)
        repo.append_event("evt-1", "T-A", "P-1", "Issue", "ISS-1",
                          "fail_event", {})
        conn.commit()

        def fail_handler(e):
            raise ValueError("bad data")

        dispatcher = OutboxDispatcher(conn, "worker-1")
        dispatcher.register_handler("fail_event", fail_handler)
        results = dispatcher.run_once()
        assert len(results) == 1
        assert results[0]["status"] == "TERMINAL"

    def test_drain_processes_all(self, conn):
        repo = OutboxRepository(conn)
        for i in range(5):
            repo.append_event(f"evt-{i}", "T-A", "P-1", "Issue", f"ISS-{i}",
                              "test_event", {})
        conn.commit()
        dispatcher = OutboxDispatcher(conn, "worker-1")
        dispatcher.register_handler("test_event", lambda e: None)
        results = dispatcher.drain()
        assert len(results) == 5

    def test_two_workers_no_double_process(self, conn):
        """两个 dispatcher 同时运行 → 不重复处理。"""
        repo = OutboxRepository(conn)
        repo.append_event("evt-1", "T-A", "P-1", "Issue", "ISS-1",
                          "test_event", {})
        conn.commit()
        d1 = OutboxDispatcher(conn, "worker-1")
        d1.register_handler("test_event", lambda e: None)
        d2 = OutboxDispatcher(conn, "worker-2")
        d2.register_handler("test_event", lambda e: None)
        r1 = d1.run_once()
        r2 = d2.run_once()
        total = len(r1) + len(r2)
        assert total == 1  # 只有一个 worker 消费了事件
