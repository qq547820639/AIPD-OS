"""F-EXEC-02：outbox 接线到真实产品路径（RFQ 询价邮件）。

接线前的事实（本轮实测）：`OutboxDispatcher` / `OutboxRepository` 在 `src/`、
`scripts/` 里**没有任何产品调用点**——只有测试与性能量具消费它们；
`external_operations` 台账同样无人写入（dispatcher 只 `import` 了仓储却从不调用）。
也就是说「对外副作用有没有真的做过」这个问题，产品侧一直无人记录。

本文件把这条链钉成一条可跑的闭环，并固定三处安全边界：
1. 适配器**不再内联发送**，改为在同一状态库里落事件（先事件后执行）；
2. handler 先查 `external_operations` 台账，同一幂等键只做一次对外调用；
3. 密码只从环境变量在发送瞬间取，**不写进事件载荷**（事件表是明文落盘的）。
"""
from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace

import pytest

from aipd_os.execution.side_effects import (
    EVENT_RFQ_SEND,
    OutboxQueue,
    build_rfq_dispatcher,
    rfq_idempotency_key,
    rfq_send_handler,
)
from aipd_os.state import migrations as mig
from aipd_os.state.connection import ConnectionFactory
from aipd_os.state.dispatcher import OutboxDispatcher
from aipd_os.state.outbox import (
    OP_DISPATCHED,
    OP_SUCCEEDED,
    OP_UNKNOWN_OUTCOME,
    ExternalOperationRepository,
    OutboxRepository,
)


class _Transport:
    """假 SMTP 投递：记录每一次真实调用，可按需抛错。"""

    def __init__(self, error: BaseException | None = None, message_id: str = "<m-1@x>"):
        self.calls: list[dict] = []
        self.error = error
        self.message_id = message_id

    def __call__(self, host, port, user, password, from_addr, to_addrs,
                 subject, body, **kw) -> str:
        self.calls.append({"host": host, "port": port, "user": user,
                           "password": password, "from": from_addr,
                           "to": list(to_addrs), "subject": subject, "body": body})
        if self.error is not None:
            raise self.error
        return self.message_id


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "state.db")
    mig.migrate(path)
    return path


@pytest.fixture
def conn(db):
    c = ConnectionFactory(db).connect()
    yield c
    c.close()


def _enqueue(queue: OutboxQueue, *, project_id="P-1", supplier="acme@x.com",
             part="支架", qty=10, work_id="W-1") -> str:
    key = rfq_idempotency_key(project_id=project_id, supplier=supplier,
                              part=part, quantity=qty)
    return queue.enqueue_rfq_send(
        tenant_id="T-A", project_id=project_id,
        work_id=work_id, idempotency_key=key,
        message={"host": "smtp.test", "port": 587, "from_addr": "aipd@x",
                 "to_addrs": [supplier], "subject": f"RFQ: {part}",
                 "body": f"请报价 {part} x{qty}", "username": "svc"})


def _events(conn) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT event_id, event_type, idempotency_key, payload_json, completed_at,"
        " last_error FROM outbox_events ORDER BY event_id").fetchall()]


class TestEnqueueIsTheProductCallSite:
    def test_enqueue_writes_one_event_with_the_rfq_type(self, db, conn):
        event_id = _enqueue(OutboxQueue(db))
        rows = _events(conn)
        assert len(rows) == 1
        assert rows[0]["event_type"] == EVENT_RFQ_SEND
        assert rows[0]["event_id"] == event_id
        assert rows[0]["idempotency_key"]
        assert rows[0]["completed_at"] is None

    def test_payload_never_carries_the_smtp_password(self, db, conn):
        """事件表是明文落盘的：载荷里只能有「在哪发」，不能有口令。"""
        _enqueue(OutboxQueue(db))
        payload = _events(conn)[0]["payload_json"]
        assert "password" not in payload.lower()
        assert "smtp.test" in payload

    def test_enqueue_participates_in_the_callers_transaction(self, tmp_path):
        """与领域写同事务：外层回滚 ⇒ 事件必须一起消失（否则会被凭空发出）。"""
        path = str(tmp_path / "state.db")
        mig.migrate(path)
        factory = ConnectionFactory(path)
        with pytest.raises(RuntimeError), factory.transaction() as c:
            c.execute("CREATE TABLE caller_marker(x INTEGER)")
            OutboxQueue(path).enqueue_rfq_send(
                tenant_id="T", project_id="P", work_id="W",
                idempotency_key="k-1",
                message={"host": "h", "port": 25, "from_addr": "f",
                         "to_addrs": ["t@x"], "subject": "s", "body": "b",
                         "username": "u"})
            assert c.execute(
                "SELECT COUNT(*) FROM outbox_events").fetchone()[0] == 1
            raise RuntimeError("rollback")
        with ConnectionFactory(path).connection() as after:
            assert after.execute(
                "SELECT COUNT(*) FROM outbox_events").fetchone()[0] == 0


class TestHandlerSendsOnceAndLedgers:
    def test_happy_path_sends_and_records_succeeded(self, db, conn):
        transport = _Transport(message_id="<rfq-42@smtp.test>")
        _enqueue(OutboxQueue(db))
        results = build_rfq_dispatcher(conn, send=transport).run_once()
        assert [r["status"] for r in results] == ["COMPLETED"]
        assert len(transport.calls) == 1
        call = transport.calls[0]
        assert call["host"] == "smtp.test" and call["port"] == 587
        assert call["to"] == ["acme@x.com"] and call["subject"] == "RFQ: 支架"
        assert call["password"] == "" or call["password"] is None   # 未配置口令
        ops = conn.execute("SELECT operation_id,status,external_reference,attempt"
                           " FROM external_operations").fetchall()
        assert len(ops) == 1
        assert ops[0]["status"] == OP_SUCCEEDED
        assert ops[0]["external_reference"] == "<rfq-42@smtp.test>"

    def test_same_idempotency_key_is_not_sent_twice(self, db, conn):
        """重复事件（同一内容重驱动）只对外发送一次——这是接线的全部目的。"""
        queue = OutboxQueue(db)
        _enqueue(queue)
        _enqueue(queue)                       # 同 key、不同 event_id
        transport = _Transport()
        results = build_rfq_dispatcher(conn, send=transport).drain()
        assert [r["status"] for r in results] == ["COMPLETED", "COMPLETED"]
        assert len(transport.calls) == 1, "重复事件必须被台账幂等挡住"
        assert conn.execute("SELECT COUNT(*) FROM external_operations").fetchone()[0] == 1
        deduped = conn.execute(
            "SELECT COUNT(*) FROM outbox_events"
            " WHERE completed_at IS NOT NULL AND last_error LIKE 'dedup%'").fetchone()[0]
        assert deduped == 1, "去重那条必须留下可读痕迹，且只有它被去重"

    def test_different_supplier_is_a_different_send(self, db, conn):
        """幂等键按内容派生：换供应商/换零件必须算新的一次，不能被去重吞掉。"""
        queue = OutboxQueue(db)
        _enqueue(queue, supplier="acme@x.com")
        _enqueue(queue, supplier="beta@x.com")
        transport = _Transport()
        build_rfq_dispatcher(conn, send=transport).drain()
        assert len(transport.calls) == 2
        assert conn.execute("SELECT COUNT(*) FROM external_operations").fetchone()[0] == 2

    def test_send_failure_retries_then_stops_within_budget(self, db, conn):
        transport = _Transport(error=ConnectionError("smtp refused"))
        _enqueue(OutboxQueue(db))
        results = build_rfq_dispatcher(conn, send=transport).drain(max_iterations=20)
        assert len(transport.calls) <= 5
        assert results[-1]["status"] == "TERMINAL_ATTEMPTS_EXHAUSTED"
        row = conn.execute("SELECT status, last_error FROM external_operations").fetchone()
        assert row["status"] == "FAILED_TERMINAL"

    def test_timeout_records_unknown_outcome_and_does_not_reshed(self, db, conn):
        """超时 = 结果未知：台账记 UNKNOWN_OUTCOME，事件离开可领集合，不自动重发。"""
        transport = _Transport(error=TimeoutError("read timed out"))
        _enqueue(OutboxQueue(db))
        results = build_rfq_dispatcher(conn, send=transport).run_once()
        assert results[0]["status"] == "UNKNOWN_OUTCOME"
        assert len(transport.calls) == 1
        row = conn.execute("SELECT status FROM external_operations").fetchone()
        assert row["status"] == OP_UNKNOWN_OUTCOME
        # 再跑一次不得重发（只有人工核对/重新入队才能再来）
        again = build_rfq_dispatcher(conn, send=_Transport()).run_once()
        assert again == []
        assert len(transport.calls) == 1


class TestAdapterDefersToTheQueue:
    def test_adapter_with_queue_does_not_send_inline(self, db, conn, monkeypatch):
        from aipd_os.mail import client as mail_client
        from aipd_os.tool_adapters.mail_rfq_adapter import MailRfqAdapter

        def boom(*a, **kw):
            raise AssertionError("配置了队列后适配器不得内联发送")

        monkeypatch.setattr(mail_client, "send_email", boom)
        monkeypatch.setenv("AIPD_SMTP_HOST", "smtp.test")
        out = MailRfqAdapter(queue=OutboxQueue(db)).execute(
            {"supplier": "acme@x.com", "part": "支架", "quantity": 10,
             "work_id": "W-1", "project_id": "P-1"})
        assert out["sent"] is False and out["queued"] is True
        assert out["provider"] == "outbox"
        assert _events(conn)[0]["event_type"] == EVENT_RFQ_SEND
        assert out["rfq_draft"]["to"] == "acme@x.com"

    def test_adapter_without_queue_keeps_the_inline_path(self, monkeypatch):
        """反向对照：没接队列时今天的内联发送行为不变（不擅自改变旧装配）。"""
        from aipd_os.mail import client as mail_client
        from aipd_os.tool_adapters.mail_rfq_adapter import MailRfqAdapter

        seen = {}

        def fake_send(host, port, user, password, from_addr, to_addrs,
                      subject, body, **kw):
            seen["to"] = list(to_addrs)
            return "<inline-1@x>"

        monkeypatch.setattr(mail_client, "send_email", fake_send)
        monkeypatch.setenv("AIPD_SMTP_HOST", "smtp.test")
        out = MailRfqAdapter().execute({"supplier": "acme@x.com", "part": "P"})
        assert out["sent"] is True and out["message_id"] == "<inline-1@x>"
        assert seen["to"] == ["acme@x.com"]

    def test_registry_wires_the_queue_when_a_state_db_is_given(self, db, monkeypatch):
        """装配点：给 build_registry 传状态库 ⇒ RFQ 适配器带队列。"""
        from aipd_os.mail import client as mail_client
        from aipd_os.tool_adapters.builtin import build_registry

        monkeypatch.setattr(mail_client, "send_email",
                            lambda *a, **kw: (_ for _ in ()).throw(
                                AssertionError("不该内联")))
        monkeypatch.setenv("AIPD_SMTP_HOST", "smtp.test")
        registry = build_registry(state_db=db)
        out = registry.get("supply.rfq").execute(
            {"supplier": "s@x.com", "part": "P", "project_id": "P-1"})
        assert out["queued"] is True
        # 不带 state_db 时仍是旧行为（不发送、不建事件）
        plain = build_registry()
        assert plain.get("supply.rfq")._queue is None


class TestCliDrain:
    def test_drain_command_reports_send(self, db, monkeypatch, capsys):
        from aipd_os.cli.commands_outbox import cmd_outbox

        transport = _Transport(message_id="<cli-1@x>")
        monkeypatch.setattr("aipd_os.mail.client.send_email", transport)
        monkeypatch.setenv("AIPD_SMTP_HOST", "smtp.test")
        _enqueue(OutboxQueue(db))

        # 用 SimpleNamespace 而不是 class 体：class 体里的 `db = db` 走 LOAD_NAME，
        # 会绑到模块级同名 fixture 函数上（表现为「no such table」而不是 NameError）。
        args = SimpleNamespace(db=db, limit=5, json=True, worker_id="test-outbox")

        assert cmd_outbox(args) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["results"][0]["status"] == "COMPLETED"
        assert payload["sent"] == 1
        assert len(transport.calls) == 1


class TestLedgerIsReachableOnlyThroughTheHandler:
    def test_find_by_idempotency_key_honours_operation_kind(self, conn):
        """台账唯一约束含 operation_kind，查询也必须带上——否则跨种类串键。"""
        ops = ExternalOperationRepository(conn)
        ops.create("op-1", "T", "P", provider="smtp", operation_kind="rfq_email",
                   idempotency_key="k-9")
        conn.commit()
        assert ops.find_by_idempotency_key("T", "P", "smtp", "k-9",
                                           operation_kind="rfq_email") is not None
        assert ops.find_by_idempotency_key("T", "P", "smtp", "k-9",
                                           operation_kind="other") is None

    def test_v16_unique_index_actually_rejects_a_duplicate(self, conn):
        """这条索引在接线之前从未被任何用例跑过（实测）。"""
        ops = ExternalOperationRepository(conn)
        ops.create("op-a", "T", "P", provider="smtp", operation_kind="rfq_email",
                   idempotency_key="dup-1")
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            ops.create("op-b", "T", "P", provider="smtp",
                       operation_kind="rfq_email", idempotency_key="dup-1")

    def test_handler_uses_the_ledger_before_calling_the_transport(self, db, conn):
        """已有 SUCCEEDED 台账时 handler 直接判定为已做过（重放安全）。"""
        repo = OutboxRepository(conn)
        repo.append_event("evt-replay", "T", "P", "WorkItem", "W", EVENT_RFQ_SEND,
                          {"host": "h", "port": 25, "from_addr": "f",
                           "to_addrs": ["t@x"], "subject": "s", "body": "b",
                           "username": "u"}, idempotency_key="replay-1")
        conn.commit()
        ops = ExternalOperationRepository(conn)
        ops.create("op-pre", "T", "P", provider="smtp",
                   operation_kind="rfq_email", idempotency_key="replay-1")
        ops.transition_status("op-pre", "T", "P", OP_DISPATCHED)
        ops.transition_status("op-pre", "T", "P", OP_SUCCEEDED,
                              external_reference="<pre@x>")
        conn.commit()
        transport = _Transport()
        d = OutboxDispatcher(conn, "w")
        d.register_handler(EVENT_RFQ_SEND, rfq_send_handler(conn, send=transport))
        assert d.run_once()[0]["status"] == "COMPLETED"
        assert transport.calls == []
