"""F-EXEC-03 / F-EXEC-04：outbox claim 与重试预算的行为契约。

这些用例先把「接线之前必须成立」的语义钉住：
- claim 必须在**写入时**重判可领条件（否则两个 worker 会双份领取 ⇒ 双份对外发送）；
- 领到的事件必须让 handler 看见自己的租约（旧实现返回的是 UPDATE 之前的快照）；
- 重试必须有预算上限（`max_attempts` 以前从未被读，毒事件会在一次 drain 里无限循环）；
- 外部调用的**超时**是「结果未知」，不是「可以重发」——与 UNKNOWN ≠ FAILED 的既有
  doctrine、以及 F-EXEC-01「结果未知的重驱动挂起等人工核对」一致；
- dispatcher 不得提交别人的事务（F-STATE-05 同一形状：静默 COMMIT 使回滚失效）。
"""
from __future__ import annotations

import inspect
import sqlite3

import pytest

from aipd_os.state import migrations as mig
from aipd_os.state.connection import ConnectionFactory
from aipd_os.state.dispatcher import OutboxDispatcher
from aipd_os.state.outbox import OutboxRepository


class _Raiser:
    """按预设异常序列抛错，并记录被调用次数。"""

    def __init__(self, errors: list[BaseException]):
        self.errors = errors
        self.calls = 0

    def __call__(self, event: dict) -> None:
        idx = min(self.calls, len(self.errors) - 1)
        self.calls += 1
        err = self.errors[idx]
        if err is not None:
            raise err


def _conn(tmp_path, name: str = "state.db") -> sqlite3.Connection:
    path = str(tmp_path / name)
    mig.migrate(path)
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c


def _append(repo: OutboxRepository, event_id: str = "evt-1", **kw) -> None:
    repo.append_event(event_id, "T-A", "P-1", "WorkItem", "W-1",
                      kw.pop("event_type", "test_event"), kw.pop("payload", {}),
                      **kw)


@pytest.fixture
def conn(tmp_path):
    c = _conn(tmp_path)
    yield c
    c.close()


class TestClaimAtomicity:
    def test_claim_is_a_single_statement_not_read_then_write(self, conn):
        """领活的 SELECT 与 UPDATE 之间没有窗口 ⇒ 必须是**一条**语句。

        行为面（下面的租约可见性 / 不被第二个人抢走）无法在单连接里观测这个窗口，
        所以这里直接钉形状：claim_available 里只能有 1 次游标执行。
        """
        src = inspect.getsource(OutboxRepository.claim_available)
        assert src.count("_conn.execute(") == 1, (
            "claim 退化成 SELECT 再逐行 UPDATE：两个 worker 会同时领到同一事件")

    def test_claimed_row_reports_its_own_lease(self, conn):
        _append(OutboxRepository(conn), event_type="e")
        conn.commit()
        claimed = OutboxRepository(conn).claim_available("w-1", limit=5)
        assert [e["event_id"] for e in claimed] == ["evt-1"]
        row = claimed[0]
        assert row["claimed_by"] == "w-1"
        assert row["claimed_at"] and row["claim_expires_at"]

    def test_live_lease_is_not_taken_by_a_second_worker(self, tmp_path):
        path = str(tmp_path / "state.db")
        mig.migrate(path)
        a = sqlite3.connect(path)
        a.row_factory = sqlite3.Row
        b = sqlite3.connect(path)
        b.row_factory = sqlite3.Row
        try:
            _append(OutboxRepository(a), event_type="e")
            a.commit()
            assert len(OutboxRepository(b).claim_available("B", limit=1)) == 1
            b.commit()
            # B 已领且租约未过期 ⇒ A 不能再拿（反向对照见下一条）
            assert OutboxRepository(a).claim_available("A", limit=1) == []
        finally:
            a.close()
            b.close()

    def test_expired_lease_is_claimable_again(self, tmp_path):
        """与上一条成对：判据必须是「租约过期」而不是「被领过」。"""
        path = str(tmp_path / "state.db")
        mig.migrate(path)
        c = sqlite3.connect(path)
        c.row_factory = sqlite3.Row
        try:
            _append(OutboxRepository(c), event_type="e")
            c.execute("UPDATE outbox_events SET claimed_at=?, claimed_by='dead',"
                      " claim_expires_at=? WHERE event_id='evt-1'",
                      ("2000-01-01T00:00:00+00:00", "2000-01-02T00:00:00+00:00"))
            c.commit()
            claimed = OutboxRepository(c).claim_available("new", limit=1)
            assert [e["event_id"] for e in claimed] == ["evt-1"]
            assert claimed[0]["claimed_by"] == "new"
        finally:
            c.close()


class TestRetryBudget:
    def test_retryable_failures_stop_at_max_attempts(self, conn):
        """毒事件不能在一次 drain 里被无限重领（旧实现：max_attempts 从未被读）。"""
        repo = OutboxRepository(conn)
        _append(repo, event_type="e")
        conn.commit()
        raiser = _Raiser([ConnectionError("smtp down")])
        d = OutboxDispatcher(conn, "w")
        d.register_handler("e", raiser)
        results = d.drain(max_iterations=20)
        assert raiser.calls <= 5, f"重试无预算上限：handler 被调 {raiser.calls} 次"
        assert results[-1]["status"] == "TERMINAL_ATTEMPTS_EXHAUSTED"
        row = conn.execute("SELECT completed_at, last_error FROM outbox_events"
                           " WHERE event_id='evt-1'").fetchone()
        assert row["completed_at"] is not None, "预算耗尽必须离开可领集合"
        assert "attempt" in (row["last_error"] or "").lower()

    def test_fewer_failures_than_budget_stay_claimable(self, conn):
        """反向对照：未达预算的失败仍然可重投，否则上一条只是「一律终止」。"""
        _append(OutboxRepository(conn), event_type="e")
        conn.commit()
        d = OutboxDispatcher(conn, "w")
        d.register_handler("e", _Raiser([ConnectionError("flaky")]))
        out = d.run_once()
        assert out[0]["status"] == "RETRYABLE"
        row = conn.execute("SELECT completed_at FROM outbox_events"
                           " WHERE event_id='evt-1'").fetchone()
        assert row["completed_at"] is None
        # 释放租约后下一次 run_once 能再领到
        d2 = OutboxDispatcher(conn, "w")
        d2.register_handler("e", lambda e: None)
        assert [r["status"] for r in d2.run_once()] == ["COMPLETED"]


class TestUnknownOutcomeIsNotResent:
    def test_timeout_does_not_release_the_event_for_reshed(self, conn):
        """对外发送超时 = 结果未知：可能已经送达，自动重发 = 供应商收到两封。"""
        _append(OutboxRepository(conn), event_type="e")
        conn.commit()
        d = OutboxDispatcher(conn, "w")
        d.register_handler("e", _Raiser([TimeoutError("read timed out")]))
        out = d.run_once()
        assert out[0]["status"] == "UNKNOWN_OUTCOME"
        row = conn.execute("SELECT completed_at, claimed_at, last_error"
                           " FROM outbox_events WHERE event_id='evt-1'").fetchone()
        assert row["completed_at"] is not None, "UNKNOWN 仍留在可领集合 ⇒ 会被自动重发"
        assert row["claimed_at"] is None
        assert "UNKNOWN" in (row["last_error"] or "").upper()
        # 再领一次必须是空：只有人工核对（重新入队/裁决）才能再来一次
        assert OutboxRepository(conn).claim_available("w2", limit=5) == []

    def test_connection_error_is_still_retryable(self, conn):
        """配对极性：连接层失败（未建立会话）可以重投，超时不行。"""
        _append(OutboxRepository(conn), event_type="e")
        conn.commit()
        d = OutboxDispatcher(conn, "w")
        d.register_handler("e", _Raiser([ConnectionError("conn refused")]))
        assert d.run_once()[0]["status"] == "RETRYABLE"


class TestDispatcherTransactionOwnership:
    def test_run_once_does_not_commit_the_callers_transaction(self, tmp_path):
        """在调用方事务里跑 dispatcher，不得把外层未提交的写一起提交。

        F-STATE-05 的同一形状（`executescript` 隐式 COMMIT）：这里的凶手是
        `run_once()` 末尾无条件的 `self._conn.commit()`。
        """
        path = str(tmp_path / "state.db")
        mig.migrate(path)
        factory = ConnectionFactory(path)
        with pytest.raises(RuntimeError), factory.transaction() as c:
            c.execute("CREATE TABLE caller_marker(x INTEGER)")
            _append(OutboxRepository(c), event_type="e")
            d = OutboxDispatcher(c, "w")
            d.register_handler("e", lambda e: None)
            assert d.run_once()[0]["status"] == "COMPLETED"
            # dispatcher 跑完之后事务仍归调用方：还能继续写，并最终整体回滚
            c.execute("INSERT INTO caller_marker VALUES(1)")
            assert c.execute(
                "SELECT COUNT(*) FROM outbox_events").fetchone()[0] == 1
            raise RuntimeError("caller rolls the whole thing back")
        probe = sqlite3.connect(path)
        try:
            tables = {r[0] for r in probe.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            assert "caller_marker" not in tables, "外层事务被 dispatcher 提前提交"
            assert probe.execute(
                "SELECT COUNT(*) FROM outbox_events").fetchone()[0] == 0, (
                "dispatcher 提交了调用方的事务：outbox 行与其状态一起落盘")
        finally:
            probe.close()

    def test_run_once_persists_when_it_owns_the_connection(self, conn):
        """反向对照：独立连接（无人持有事务）时 dispatcher 仍要把结果写盘。"""
        _append(OutboxRepository(conn), event_type="e")
        conn.commit()
        d = OutboxDispatcher(conn, "w")
        d.register_handler("e", lambda e: None)
        d.run_once()
        second = _conn_with_reopen(conn)
        assert second.execute("SELECT completed_at FROM outbox_events"
                             " WHERE event_id='evt-1'").fetchone()[0] is not None


def _conn_with_reopen(conn: sqlite3.Connection) -> sqlite3.Connection:
    """另开一条连接读盘，确认结果真的提交了而不是只在内存事务里。"""
    path = conn.execute("PRAGMA database_list").fetchone()[2]
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    return c
