"""P2-M10：状态层性能门禁（确定性、机器无关）。

与 ``scripts/state_perf_gate.py`` 的分工：
- 量具负责「测出毫秒数 + 与基线比相对劣化」（本机/CI 波动大，只做趋势棘轮）；
- 本文件只放**不依赖墙钟阈值**的硬门禁：查询计划是否走索引、重入事务是否
  只开一条连接、claim 是否互斥、语句数是否随依赖线性增长。
  比值型断言（批处理 vs 逐条）用极宽松的下界，只抓「量级反转」不误报抖动。
"""
from __future__ import annotations

import sqlite3
import time

import pytest

from aipd_os.state import migrations as mig
from aipd_os.state.connection import ConnectionFactory
from aipd_os.state.db import FACT_STATUSES, AIPDStateDB
from aipd_os.state.outbox import OutboxRepository
from aipd_os.state.stale_propagation import StalePropagationService

TENANT = "default"
PROJECT = "P-PERF"
CLAIM_SQL = (
    "SELECT * FROM outbox_events "
    "WHERE completed_at IS NULL "
    "AND (claimed_at IS NULL OR claim_expires_at IS NULL OR claim_expires_at < ?) "
    "ORDER BY available_at LIMIT ?")


@pytest.fixture
def db(tmp_path):
    store = AIPDStateDB(str(tmp_path / "state.db"))
    store.ensure_default_tenant(TENANT)
    store.init_project(TENANT, PROJECT, "perf gate", "goal")
    return store


def _plan(conn: sqlite3.Connection, sql: str, args: tuple) -> list[str]:
    return [r[3] for r in conn.execute("EXPLAIN QUERY PLAN " + sql, args)]


def _fact_status() -> str:
    return sorted(FACT_STATUSES)[0]


class TestQueryPlanGates:
    """热读路径必须由索引给出「定位 + 顺序」，不允许全表扫描或临时排序。"""

    def test_outbox_claim_is_index_ordered_without_temp_btree(self, db):
        with db.connect() as c:
            steps = _plan(c, CLAIM_SQL, ("2999-01-01", 10))
        text = " | ".join(steps)
        assert "TEMP B-TREE" not in text, (
            f"claim 每批都在排序全量候选，积压越大越慢：{text}")
        assert "SEARCH" in text or "USING INDEX" in text, text

    def test_changes_by_scope_uses_index_not_full_scan(self, db):
        with db.connect() as c:
            steps = _plan(
                c,
                "SELECT * FROM changes WHERE tenant_id=? AND project_id=? "
                "ORDER BY created_at",
                (TENANT, PROJECT))
        text = " | ".join(steps)
        assert "SCAN changes" not in text, f"审计读路径全表扫描：{text}"
        assert "TEMP B-TREE" not in text, f"审计读路径临时排序：{text}"

    def test_dependency_lookup_is_index_search(self, db):
        with db.connect() as c:
            steps = _plan(
                c,
                "SELECT target_type, target_id FROM dependencies "
                "WHERE tenant_id=? AND project_id=? AND source_type=? "
                "AND source_id=? AND target_type=?",
                (TENANT, PROJECT, "bom", "BOM-1", "cost_snapshot"))
        assert any("SEARCH" in s for s in steps), steps

    def test_v17_perf_indexes_exist_and_rollback_removes_them(self, db):
        def indexes(conn):
            return {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'")}
        with db.connect() as c:
            created = {"idx_changes_scope_time", "idx_outbox_due"}
            assert created <= indexes(c), created - indexes(c)
        rolled = mig.rollback(str(db.path), 16)
        # 本用例只管 v17 的两条索引；回滚链会把 v17 之上后来新增的版本一起退掉，
        # 所以断言「v17 在回滚清单里」而不是「v17 恰好是链尾」。
        assert 17 in rolled, rolled
        with db.connect() as c:
            assert not (created & indexes(c))
            mig.migrate(str(db.path))  # 复位，fixture 仍可继续使用
            assert created <= indexes(c)


class TestConnectionAndTransactionGates:
    def test_nesting_does_not_open_extra_connections(self, db, monkeypatch):
        """重入必须复用外层连接：20 层嵌套只允许 1 次物理 connect。

        回归背景：每次 transaction() 都新开连接并 BEGIN IMMEDIATE，
        会与自己的写锁互等到 busy_timeout（database is locked）。
        """
        calls: list[int] = []
        original = ConnectionFactory.connect

        def counting_connect(self):
            calls.append(1)
            return original(self)

        monkeypatch.setattr(ConnectionFactory, "connect", counting_connect)
        factory = ConnectionFactory(db.path)
        with factory.transaction():
            for _ in range(20):
                with ConnectionFactory(db.path).transaction():
                    pass
        assert len(calls) == 1

    def test_batched_transaction_outranks_per_statement_writes(self, db):
        """事务边界策略的量级门禁：批处理至少快 5x。

        只断言数量级，不断言毫秒数——跨机器差异太大；若策略失效（例如
        Repository 又自行 commit）会直接掉到逐条路径，比值会崩到 1 附近。
        """
        factory = ConnectionFactory(db.path)
        status = _fact_status()
        n = 120

        def purge() -> None:
            with factory.transaction() as c:
                c.execute("DELETE FROM facts")
                c.execute("DELETE FROM changes")

        purge()
        start = time.perf_counter()
        with db.transaction():
            for i in range(n):
                db.add_fact(TENANT, PROJECT, f"b{i}", {"v": i}, status)
        batched = time.perf_counter() - start

        purge()
        start = time.perf_counter()
        for i in range(n):
            db.add_fact(TENANT, PROJECT, f"a{i}", {"v": i}, status)
        one_by_one = time.perf_counter() - start

        assert batched < one_by_one / 5.0, (
            f"批处理 {batched*1000:.1f}ms vs 逐条 {one_by_one*1000:.1f}ms — "
            "P2-M4 事务边界策略未生效")
        assert batched > 0 and one_by_one > 0

    def test_migrate_on_current_db_is_a_noop(self, db):
        assert mig.migrate(str(db.path)) == []
        assert mig.current_version(str(db.path)) == max(
            m["version"] for m in mig.MIGRATIONS)


class TestOutboxClaimExclusion:
    def test_two_workers_never_claim_the_same_event(self, db):
        """lease 生效后，第二个 worker 不得再取走同一批事件。

        两次 claim 各自提交：SQLite 只允许一个写者，真实的两个 worker 就是
        两个进程上的两个连接，claim 的互斥性正体现在「已带 lease 的行不再返回」。
        """
        factory = ConnectionFactory(db.path)
        with factory.transaction() as c:
            repo = OutboxRepository(c)
            for i in range(30):
                repo.append_event(f"e{i}", TENANT, PROJECT, "Issue",
                                  f"ISS-{i}", "test.event", {"i": i})

        with factory.transaction() as c:
            first = OutboxRepository(c).claim_available(
                "w-1", limit=10, lease_seconds=600)
        with factory.transaction() as c:
            second = OutboxRepository(c).claim_available(
                "w-2", limit=10, lease_seconds=600)
        ids_1 = {e["event_id"] for e in first}
        ids_2 = {e["event_id"] for e in second}
        assert len(ids_1) == 10
        assert ids_1 & ids_2 == set(), f"同一事件被两个 worker 取走：{ids_1 & ids_2}"
        with factory.connection() as c:
            rows = c.execute(
                "SELECT claimed_by, COUNT(*) AS n FROM outbox_events "
                "WHERE claimed_by <> '' GROUP BY claimed_by").fetchall()
        assert {r["claimed_by"]: r["n"] for r in rows} == {"w-1": 10, "w-2": 10}

    def test_expired_lease_becomes_claimable_again(self, db):
        factory = ConnectionFactory(db.path)
        with factory.transaction() as c:
            OutboxRepository(c).append_event(
                "e-lease", TENANT, PROJECT, "Issue", "ISS-1", "test.event", {})
        with factory.transaction() as c:
            assert len(OutboxRepository(c).claim_available(
                "w-1", limit=5, lease_seconds=600)) == 1
        with factory.transaction() as c:
            c.execute("UPDATE outbox_events SET claim_expires_at=? "
                      "WHERE event_id='e-lease'", ("2000-01-01T00:00:00+00:00",))
        with factory.connection() as c:
            reclaimed = OutboxRepository(c).claim_available(
                "w-2", limit=5, lease_seconds=600)
            c.commit()
        assert [e["event_id"] for e in reclaimed] == ["e-lease"]


class TestStalePropagationScaling:
    """传播的语句数必须随依赖数线性增长（抓 N+1 查询）。"""

    def _count_statements(self, db, dep_count: int) -> tuple[int, int]:
        project = f"P-{dep_count}"
        db.init_project(TENANT, project, "scale", "goal")
        for i in range(dep_count):
            db.add_dependency(TENANT, project, "bom", "BOM-1",
                              "cost_snapshot", f"COST-{i}")
        svc = StalePropagationService(db)
        counted: list[str] = []
        with db.transaction() as conn:
            conn.set_trace_callback(counted.append)
            result = svc.propagate_bom_change(
                TENANT, project, "BOM-1", {"quantity": 1}, {"quantity": 2})
            conn.set_trace_callback(None)
        assert len(result["affected"]) == dep_count
        return dep_count, len([s for s in counted if s.strip()])

    def test_statement_count_grows_linearly_in_dependencies(self, db):
        small, n_small = self._count_statements(db, 40)
        large, n_large = self._count_statements(db, 200)
        marginal = (n_large - n_small) / (large - small)
        assert marginal <= 1.5, (
            f"每个依赖新增 {marginal:.2f} 条语句（{n_small}→{n_large}），"
            "疑似 N+1：应一条 SELECT 取依赖 + 每条依赖一次写")
