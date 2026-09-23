"""P2-M1 可重入事务契约（ConnectionFactory.transaction）。

回归背景：``transaction()`` 早先每次都新开连接并 ``BEGIN IMMEDIATE``。
由于 SQLite 写锁按连接持有，同一进程内「外层事务未提交 → 内层又开一个事务」
的写法会与自己的写锁互等，busy_timeout(5s) 后抛 ``database is locked``。
Supervisor 的 ``add_lineage → project_id → connect`` 与
``_mark_stale → add_lineage`` 正好命中该形状，导致 run_supervisor 全部
变成 internal_rework。
"""
from __future__ import annotations

import threading
import time

import pytest

from aipd_os.state.connection import ConnectionFactory


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "reentrancy.db"
    factory = ConnectionFactory(path)
    with factory.transaction() as c:
        c.execute("CREATE TABLE t (id TEXT PRIMARY KEY, value TEXT)")
    return path, factory


def _rows(factory):
    with factory.connection() as c:
        return {r["id"]: r["value"] for r in c.execute("SELECT id, value FROM t")}


class TestNestedReuse:
    def test_nested_transaction_does_not_self_deadlock(self, db):
        path, factory = db
        # 内层用另一个工厂实例（Supervisor.connect 每次新建），必须按路径识别外层事务
        start = time.monotonic()
        with factory.transaction() as outer:
            with ConnectionFactory(path).transaction() as inner:
                inner.execute("INSERT INTO t VALUES ('inner', 1)")
            outer.execute("INSERT INTO t VALUES ('outer', 1)")
        elapsed = time.monotonic() - start
        assert elapsed < 2.0, f"疑似等待写锁（busy_timeout=5s）：{elapsed:.2f}s"
        assert _rows(factory) == {"inner": "1", "outer": "1"}

    def test_inner_receives_same_connection(self, db):
        _, factory = db
        with factory.transaction() as outer, factory.transaction() as inner:
            assert inner is outer

    def test_third_level_nesting_is_fine(self, db):
        _, factory = db
        with factory.transaction() as a, \
                factory.transaction() as b, \
                factory.transaction() as c:
            assert a is b and b is c
            c.execute("INSERT INTO t VALUES ('deep', 1)")
        assert _rows(factory) == {"deep": "1"}


class TestSavepointSemantics:
    def test_caught_inner_failure_keeps_outer_work(self, db):
        _, factory = db
        with factory.transaction() as outer:
            outer.execute("INSERT INTO t VALUES ('keep', 1)")
            try:
                with factory.transaction():
                    raise RuntimeError("inner boom")
            except RuntimeError:
                pass
            outer.execute("INSERT INTO t VALUES ('after', 1)")
        assert _rows(factory) == {"keep": "1", "after": "1"}

    def test_inner_partial_writes_rolled_back_but_outer_rows_survive(self, db):
        _, factory = db
        with factory.transaction() as outer:
            outer.execute("INSERT INTO t VALUES ('keep', 1)")
            with pytest.raises(RuntimeError), factory.transaction() as inner:
                inner.execute("INSERT INTO t VALUES ('doomed', 1)")
                raise RuntimeError("inner boom")
        assert _rows(factory) == {"keep": "1"}

    def test_outer_failure_rolls_back_everything(self, db):
        _, factory = db
        with pytest.raises(RuntimeError), factory.transaction() as outer:
            outer.execute("INSERT INTO t VALUES ('a', 1)")
            with factory.transaction() as inner:
                inner.execute("INSERT INTO t VALUES ('b', 1)")
            raise RuntimeError("outer boom")
        assert _rows(factory) == {}


class TestRegistryHygiene:
    def test_registry_released_after_exception(self, db):
        _, factory = db
        with pytest.raises(RuntimeError), factory.transaction() as c:
            c.execute("INSERT INTO t VALUES ('x', 1)")
            raise RuntimeError("boom")
        # 若登记表未清理，下一次外层调用会走保存点分支并静默失去原子性
        with factory.transaction() as c:
            c.execute("INSERT INTO t VALUES ('y', 1)")
        assert _rows(factory) == {"y": "1"}

    def test_transactions_are_per_thread(self, db):
        """登记表按线程隔离：别的线程不得复用本线程的活动连接。

        注：外层事务持有 RESERVED 写锁，另一线程的写事务合法地必须等待
        （这是 SQLite 的串行化，不是缺陷），所以这里用只读连接验证隔离性。
        """
        _, factory = db
        box: dict = {}

        def worker() -> None:
            with factory.connection() as c:
                box["same"] = c is outer
                box["visible"] = c.execute("SELECT count(*) AS n FROM t").fetchone()["n"]

        with factory.transaction() as outer:
            outer.execute("INSERT INTO t VALUES ('pending', 1)")
            t = threading.Thread(target=worker)
            t.start()
            t.join(timeout=10)
            assert not t.is_alive()

        assert box["same"] is False
        assert box["visible"] == 0, "外层未提交的写不得被另一线程的连接看到（非同一连接）"
