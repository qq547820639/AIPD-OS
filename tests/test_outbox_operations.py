"""P2-M5: Outbox + External Operation tests。

验证 outbox_events 和 external_operations 的运行时行为。
"""
from __future__ import annotations

import sqlite3

import pytest

from aipd_os.state.outbox import (
    OP_DISPATCHED,
    OP_FAILED_RETRYABLE,
    OP_PENDING,
    OP_SUCCEEDED,
    OP_UNKNOWN_OUTCOME,
    ExternalOperationRepository,
    OutboxRepository,
)


@pytest.fixture
def conn(tmp_path):
    """创建带 v14 schema 的临时数据库。"""
    from aipd_os.state import migrations as mig
    path = str(tmp_path / "test.db")
    mig.migrate(path)
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    yield c
    c.close()


class TestOutboxRepository:
    """Outbox 事件追加与消费。"""

    def test_append_event_in_transaction(self, conn):
        repo = OutboxRepository(conn)
        repo.append_event("evt-1", "T-A", "P-1", "Issue", "ISS-1",
                          "resolved", {"key": "value"})
        conn.commit()
        row = conn.execute("SELECT * FROM outbox_events WHERE event_id=?", ("evt-1",)).fetchone()
        assert row is not None
        assert row["tenant_id"] == "T-A"
        assert row["project_id"] == "P-1"

    def test_rollback_does_not_leave_outbox(self, conn):
        repo = OutboxRepository(conn)
        try:
            conn.execute("BEGIN IMMEDIATE")
            repo.append_event("evt-1", "T-A", "P-1", "Issue", "ISS-1",
                              "resolved", {"key": "value"})
            conn.rollback()
        except Exception:
            pass
        row = conn.execute("SELECT * FROM outbox_events WHERE event_id=?", ("evt-1",)).fetchone()
        assert row is None

    def test_claim_available(self, conn):
        repo = OutboxRepository(conn)
        repo.append_event("evt-1", "T-A", "P-1", "Issue", "ISS-1",
                          "resolved", {"key": "value"})
        repo.append_event("evt-2", "T-A", "P-1", "Issue", "ISS-2",
                          "resolved", {"key": "value2"})
        conn.commit()
        claimed = repo.claim_available("worker-1", limit=5)
        assert len(claimed) == 2

    def test_mark_completed(self, conn):
        repo = OutboxRepository(conn)
        repo.append_event("evt-1", "T-A", "P-1", "Issue", "ISS-1",
                          "resolved", {"key": "value"})
        conn.commit()
        claimed = repo.claim_available("worker-1")
        repo.mark_completed(claimed[0]["event_id"], "T-A", "P-1")
        conn.commit()
        row = conn.execute(
            "SELECT completed_at FROM outbox_events WHERE event_id=?",
            ("evt-1",)).fetchone()
        assert row["completed_at"] is not None

    def test_cross_tenant_isolation(self, conn):
        repo = OutboxRepository(conn)
        repo.append_event("evt-1", "T-A", "P-1", "Issue", "ISS-1",
                          "resolved", {})
        repo.append_event("evt-2", "T-B", "P-1", "Issue", "ISS-2",
                          "resolved", {})
        conn.commit()
        # Tenant A's events
        rows = conn.execute("SELECT * FROM outbox_events WHERE tenant_id=?", ("T-A",)).fetchall()
        assert len(rows) == 1
        assert rows[0]["event_id"] == "evt-1"


class TestExternalOperationRepository:
    """外部操作生命周期。"""

    def test_create_operation(self, conn):
        repo = ExternalOperationRepository(conn)
        result = repo.create("op-1", "T-A", "P-1", "supplier-api", "place_order",
                             idempotency_key="key-1")
        conn.commit()
        assert result["status"] == OP_PENDING
        op = repo.get("op-1", "T-A", "P-1")
        assert op is not None
        assert op["status"] == OP_PENDING

    def test_transition_pending_to_dispatched(self, conn):
        repo = ExternalOperationRepository(conn)
        repo.create("op-1", "T-A", "P-1", "supplier-api", "place_order")
        conn.commit()
        repo.transition_status("op-1", "T-A", "P-1", OP_DISPATCHED)
        conn.commit()
        op = repo.get("op-1", "T-A", "P-1")
        assert op["status"] == OP_DISPATCHED

    def test_invalid_transition_raises(self, conn):
        repo = ExternalOperationRepository(conn)
        repo.create("op-1", "T-A", "P-1", "supplier-api", "place_order")
        conn.commit()
        with pytest.raises(ValueError, match="invalid transition"):
            repo.transition_status("op-1", "T-A", "P-1", OP_SUCCEEDED)

    def test_unknown_outcome_is_valid(self, conn):
        repo = ExternalOperationRepository(conn)
        repo.create("op-1", "T-A", "P-1", "supplier-api", "place_order")
        conn.commit()
        repo.transition_status("op-1", "T-A", "P-1", OP_DISPATCHED)
        repo.transition_status("op-1", "T-A", "P-1", OP_UNKNOWN_OUTCOME, error="timeout")
        conn.commit()
        op = repo.get("op-1", "T-A", "P-1")
        assert op["status"] == OP_UNKNOWN_OUTCOME
        assert op["last_error"] == "timeout"

    def test_find_by_idempotency_key(self, conn):
        repo = ExternalOperationRepository(conn)
        repo.create("op-1", "T-A", "P-1", "supplier-api", "place_order",
                     idempotency_key="key-1")
        repo.create("op-2", "T-A", "P-1", "supplier-api", "place_order",
                     idempotency_key="key-2")
        conn.commit()
        op = repo.find_by_idempotency_key("T-A", "P-1", "supplier-api", "key-1")
        assert op is not None
        assert op["operation_id"] == "op-1"

    def test_cross_tenant_isolation(self, conn):
        repo = ExternalOperationRepository(conn)
        repo.create("op-1", "T-A", "P-1", "supplier-api", "place_order")
        repo.create("op-2", "T-B", "P-1", "supplier-api", "place_order")
        conn.commit()
        op_a = repo.get("op-1", "T-B", "P-1")
        assert op_a is None  # Tenant B cannot see Tenant A's operation

    def test_full_lifecycle_succeeded(self, conn):
        repo = ExternalOperationRepository(conn)
        repo.create("op-1", "T-A", "P-1", "supplier-api", "place_order",
                     idempotency_key="key-1")
        conn.commit()
        repo.transition_status("op-1", "T-A", "P-1", OP_DISPATCHED)
        repo.transition_status("op-1", "T-A", "P-1", OP_SUCCEEDED,
                               external_reference="ext-ref-123")
        conn.commit()
        op = repo.get("op-1", "T-A", "P-1")
        assert op["status"] == OP_SUCCEEDED
        assert op["external_reference"] == "ext-ref-123"
        assert op["completed_at"] is not None

    def test_retryable_failure_then_success(self, conn):
        repo = ExternalOperationRepository(conn)
        repo.create("op-1", "T-A", "P-1", "supplier-api", "place_order")
        conn.commit()
        repo.transition_status("op-1", "T-A", "P-1", OP_DISPATCHED)
        repo.transition_status("op-1", "T-A", "P-1", OP_FAILED_RETRYABLE, error="network")
        conn.commit()
        op = repo.get("op-1", "T-A", "P-1")
        assert op["status"] == OP_FAILED_RETRYABLE
        # Can retry
        repo.transition_status("op-1", "T-A", "P-1", OP_DISPATCHED)
        repo.transition_status("op-1", "T-A", "P-1", OP_SUCCEEDED)
        conn.commit()
        op = repo.get("op-1", "T-A", "P-1")
        assert op["status"] == OP_SUCCEEDED
