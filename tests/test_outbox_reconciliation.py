"""F-EXEC-05：外部副作用的「结果未知」必须可见、可核对，且只有一份重试预算。

接线（F-EXEC-02）之后留下的洞，本轮实测：
- `mark_unknown` 置了 `completed_at` ⇒ 这些行从 `completed_at IS NULL` 的**每一个**
  查询里消失，包括 CLI 自己唯一的 `pending` 计数——「供应商到底收没收到」这件事在
  无人核对时等于凭空蒸发；
- `external_operations` 有状态机、有 `idx_ext_ops_status` 索引，`state/errors.py:54`
  还有专门的 `ExternalOperationUnknownError`，但**全仓没有任何查询用到它、也没有任何
  地方 raise 那个异常**（实测 grep：只有契约测试断言它是 StateError 子类）；
- 「第几次 / 预算多少」在 `dispatcher._retry_or_exhaust` 与 handler 里各写一遍 ⇒
  事件说终止而台账说还能重试（或反过来）没有任何东西会发现。
"""
from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace

import pytest

from aipd_os.cli.commands_outbox import cmd_outbox
from aipd_os.execution.side_effects import (
    OutboxQueue,
    build_rfq_dispatcher,
    rfq_idempotency_key,
)
from aipd_os.state import migrations as mig
from aipd_os.state.connection import ConnectionFactory
from aipd_os.state.dispatcher import attempt_budget
from aipd_os.state.errors import ExternalOperationUnknownError
from aipd_os.state.outbox import (
    OP_FAILED_RETRYABLE,
    OP_SUCCEEDED,
    OP_UNKNOWN_OUTCOME,
    ExternalOperationRepository,
)


class _Transport:
    """假 SMTP：按次序抛出预设异常，并记录每次真实调用。"""

    def __init__(self, errors=None):
        self.calls = []
        self.errors = list(errors or [])

    def __call__(self, host, port, user, password, from_addr, to_addrs,
                 subject, body, **kw):
        idx = len(self.calls)
        self.calls.append(subject)
        err = self.errors[idx] if idx < len(self.errors) else None
        if err is not None:
            raise err
        return f"<m{idx}@x>"


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "state.db")
    mig.migrate(path)
    return path


@pytest.fixture
def conn(db):
    c = ConnectionFactory(db).connect()
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def _dispatcher(db, transport):
    c = ConnectionFactory(db).connect()
    c.row_factory = sqlite3.Row
    return build_rfq_dispatcher(c, send=transport)


def _message(supplier="acme@x.com", part="支架"):
    return {"host": "smtp.test", "port": 587, "from_addr": "aipd@x",
            "to_addrs": [supplier], "subject": f"RFQ: {part}",
            "body": f"请报价 {part}", "username": "svc"}


def _enqueue(db, *, project_id="P-1", supplier="acme@x.com", key=None):
    k = key or rfq_idempotency_key(project_id=project_id, supplier=supplier,
                                   part="支架", quantity=1)
    return OutboxQueue(db).enqueue_rfq_send(
        tenant_id="T-A", project_id=project_id, work_id="W-1",
        idempotency_key=k, message=_message(supplier))


def _ledger(conn):
    return [dict(r) for r in conn.execute(
        "SELECT operation_id, idempotency_key, status, last_error"
        " FROM external_operations ORDER BY started_at")]


def _run(args):
    """走真实输出通道取结果：cmd 的读数只经 `_emit` 打印到 stdout。"""
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cmd_outbox(args)
    return rc, json.loads(buf.getvalue())


class TestOneBudget:
    def test_attempt_budget_is_a_single_pure_decision(self):
        """预算只有一处定义：(本次之后的已试次数, 上限, 是否用尽)。"""
        assert attempt_budget({"attempt_count": 0, "max_attempts": 3}) == (1, 3, False)
        assert attempt_budget({"attempt_count": 2, "max_attempts": 3}) == (3, 3, True)
        # 缺字段或上限为 0 都不允许退化成「无限重试」
        assert attempt_budget({}) == (1, 1, True)
        assert attempt_budget({"attempt_count": 0, "max_attempts": 0}) == (1, 1, True)

    def test_event_and_ledger_agree_on_exhaustion(self, db, conn):
        """两条腿必须同时终止：事件说用尽而台账说还能重试就是两个真相。"""
        _enqueue(db)
        transport = _Transport([ConnectionError("boom")] * 6)
        results = _dispatcher(db, transport).drain(max_iterations=20)
        assert results[-1]["status"] == "TERMINAL_ATTEMPTS_EXHAUSTED"
        assert len(transport.calls) == 5, "预算不是装饰：5 次就该收口"
        rows = _ledger(conn)
        assert len(rows) == 1
        assert rows[0]["status"] == "FAILED_TERMINAL", (
            f"台账状态与事件结论不一致：{rows[0]['status']}")
        assert "exhausted" in conn.execute(
            "SELECT last_error FROM outbox_events").fetchone()[0]


class TestUnknownOutcomeIsReconcilable:
    def test_unknown_row_survives_in_the_review_view(self, db, conn):
        """它已离开 pending 集合（`completed_at` 置位），核对视图是唯一入口。"""
        _enqueue(db)
        _dispatcher(db, _Transport([TimeoutError("read timed out")])).run_once()
        assert conn.execute("SELECT completed_at FROM outbox_events").fetchone()[0]
        unresolved = ExternalOperationRepository(conn).list_unresolved("T-A", "P-1")
        assert [r["status"] for r in unresolved] == [OP_UNKNOWN_OUTCOME]
        assert unresolved[0]["idempotency_key"]

    def test_in_flight_and_retryable_also_need_review(self, db, conn):
        """「还挂着」与「还能重试」同样未收口；已收口的三种状态不得混进来。"""
        ops = ExternalOperationRepository(conn)
        ops.create("op-stuck", "T-A", "P-1", provider="smtp",
                   operation_kind="rfq_email", idempotency_key="k-stuck")
        ops.transition_status("op-stuck", "T-A", "P-1", "DISPATCHED")
        ops.create("op-retry", "T-A", "P-1", provider="smtp",
                   operation_kind="rfq_email", idempotency_key="k-retry")
        ops.transition_status("op-retry", "T-A", "P-1", "DISPATCHED")
        ops.transition_status("op-retry", "T-A", "P-1", OP_FAILED_RETRYABLE,
                              error="smtp refused")
        ops.create("op-done", "T-A", "P-1", provider="smtp",
                   operation_kind="rfq_email", idempotency_key="k-done")
        ops.transition_status("op-done", "T-A", "P-1", "DISPATCHED")
        ops.transition_status("op-done", "T-A", "P-1", OP_SUCCEEDED,
                              external_reference="<ok@x>")
        conn.commit()
        got = sorted(r["status"] for r in
                     ExternalOperationRepository(conn).list_unresolved("T-A", "P-1"))
        assert got == sorted(["DISPATCHED", OP_FAILED_RETRYABLE])

    def test_scope_isolates_tenants_and_projects(self, db, conn):
        ops = ExternalOperationRepository(conn)
        ops.create("op-a", "T-A", "P-1", provider="smtp",
                   operation_kind="rfq_email", idempotency_key="ka")
        ops.create("op-b", "T-B", "P-2", provider="smtp",
                   operation_kind="rfq_email", idempotency_key="kb")
        conn.commit()
        mine = ExternalOperationRepository(conn).list_unresolved("T-A", "P-1")
        assert [r["operation_id"] for r in mine] == ["op-a"]
        # 不给作用域 = 全量核对视图（运维入口需要它）
        assert len(ExternalOperationRepository(conn).list_unresolved()) == 2

    def test_replaying_a_key_stuck_in_unknown_fails_closed(self, db, conn):
        """结果未知时重新入队同一条必须**拒发**，而不是「再试一次」。"""
        key = rfq_idempotency_key(project_id="P-1", supplier="acme@x.com",
                                  part="支架", quantity=1)
        _enqueue(db, key=key)
        transport = _Transport([TimeoutError("read timed out")])
        _dispatcher(db, transport).run_once()
        assert _ledger(conn)[0]["status"] == OP_UNKNOWN_OUTCOME

        _enqueue(db, key=key)                        # 人工重新入队
        second = _dispatcher(db, transport).run_once()
        assert second[0]["status"] == "TERMINAL", second
        assert "结果未知" in second[0]["error"], second[0]["error"]
        assert len(transport.calls) == 1, "未知态被当成可重发 ⇒ 供应商收到两封"
        with pytest.raises(ExternalOperationUnknownError):
            _dispatcher(db, transport)._handlers["supply.rfq.send"](
                {"event_id": "e", "tenant_id": "T-A", "project_id": "P-1",
                 "idempotency_key": key, "attempt_count": 0, "max_attempts": 5,
                 "payload_json": json.dumps(_message())})


class TestCliSurfaces:
    def test_drain_reports_needs_review_count(self, db):
        _enqueue(db)
        _dispatcher(db, _Transport([TimeoutError("t")])).run_once()
        rc, payload = _run(SimpleNamespace(db=db, limit=5, json=True,
                                           worker_id="t", outbox_cmd="drain"))
        assert rc == 0
        assert payload["needs_review"] == 1
        assert payload["pending"] == 0, "未知行已 completed_at，pending 不再等于健康度"

    def test_review_lists_rows_and_signals_nonzero(self, db):
        _enqueue(db)
        _dispatcher(db, _Transport([TimeoutError("boom")])).run_once()
        rc, payload = _run(SimpleNamespace(db=db, json=True, limit=20,
                                           outbox_cmd="review"))
        assert rc == 4, "有未收口的外部操作时必须给非零，运维/CI 才接得住"
        assert payload["unresolved"][0]["status"] == OP_UNKNOWN_OUTCOME

    def test_review_is_zero_when_everything_settled(self, db):
        _enqueue(db)
        _dispatcher(db, _Transport()).run_once()
        rc, payload = _run(SimpleNamespace(db=db, json=True, limit=20,
                                           outbox_cmd="review"))
        assert rc == 0
        assert payload["unresolved"] == []

    def test_missing_db_is_a_clear_error_not_a_new_file(self, db, tmp_path,
                                                        monkeypatch):
        """路径写错必须就地报错——本轮真的发生过「把函数当路径」在仓库根建文件。"""
        cwd = tmp_path / "cwd"
        cwd.mkdir()
        monkeypatch.chdir(str(cwd))
        rc, payload = _run(SimpleNamespace(db=str(cwd / "nope.db"), json=True,
                                           limit=5, outbox_cmd="review"))
        assert rc == 2
        assert "不存在" in payload["reason"]
        assert list(cwd.glob("*.db")) == [], "不得替用户创建状态库"
