"""Outbox + External Operation Repository。

激活 migration v14 创建的 outbox_events 和 external_operations 表。
提供事务内追加 + 异步消费的完整运行时。

P2-M5: Outbox + External Operation Runtime Activation
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── External Operation Status Machine ──────────────────────────────
OP_PENDING = "PENDING"
OP_DISPATCHED = "DISPATCHED"
OP_ACKNOWLEDGED = "ACKNOWLEDGED"
OP_SUCCEEDED = "SUCCEEDED"
OP_FAILED_RETRYABLE = "FAILED_RETRYABLE"
OP_FAILED_TERMINAL = "FAILED_TERMINAL"
OP_UNKNOWN_OUTCOME = "UNKNOWN_OUTCOME"
OP_COMPENSATING = "COMPENSATING"
OP_COMPENSATED = "COMPENSATED"

VALID_OP_STATUSES = frozenset({
    OP_PENDING, OP_DISPATCHED, OP_ACKNOWLEDGED, OP_SUCCEEDED,
    OP_FAILED_RETRYABLE, OP_FAILED_TERMINAL, OP_UNKNOWN_OUTCOME,
    OP_COMPENSATING, OP_COMPENSATED,
})

# 合法状态转换
_VALID_TRANSITIONS: dict[str, set[str]] = {
    OP_PENDING: {OP_DISPATCHED, OP_FAILED_TERMINAL},
    OP_DISPATCHED: {OP_ACKNOWLEDGED, OP_SUCCEEDED, OP_FAILED_RETRYABLE,
                    OP_FAILED_TERMINAL, OP_UNKNOWN_OUTCOME},
    OP_ACKNOWLEDGED: {OP_SUCCEEDED, OP_FAILED_RETRYABLE, OP_FAILED_TERMINAL, OP_UNKNOWN_OUTCOME},
    OP_SUCCEEDED: set(),
    OP_FAILED_RETRYABLE: {OP_DISPATCHED, OP_FAILED_TERMINAL},
    OP_FAILED_TERMINAL: {OP_COMPENSATING},
    OP_UNKNOWN_OUTCOME: {OP_SUCCEEDED, OP_FAILED_TERMINAL, OP_COMPENSATING},
    OP_COMPENSATING: {OP_COMPENSATED},
    OP_COMPENSATED: set(),
}


class OutboxRepository:
    """outbox_events 表的 Repository。

    与 domain mutation 同事务追加事件，dispatcher 异步消费。
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def append_event(
        self,
        event_id: str,
        tenant_id: str,
        project_id: str,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: dict[str, Any],
        idempotency_key: str = "",
        schema_version: int = 1,
    ) -> None:
        """在当前事务中追加 outbox 事件。"""
        now = _now()
        self._conn.execute(
            "INSERT INTO outbox_events"
            "(event_id,tenant_id,project_id,aggregate_type,aggregate_id,"
            "event_type,payload_json,schema_version,created_at,available_at,"
            "attempt_count,max_attempts,last_error,idempotency_key)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (event_id, tenant_id, project_id, aggregate_type, aggregate_id,
             event_type, json.dumps(payload), schema_version, now, now,
             0, 5, "", idempotency_key))

    def claim_available(
        self,
        worker_id: str,
        limit: int = 10,
        lease_seconds: int = 300,
    ) -> list[dict[str, Any]]:
        """Claim 可用事件（**单条语句**，返回已写入租约后的行）。

        必须是「一条」而不是「先 SELECT 再逐行 UPDATE」：后者在两次语句之间留有
        窗口，第二个 worker 的无条件 `UPDATE ... WHERE event_id=?` 会把别人的租约
        覆盖掉 ⇒ 同一事件被两份处理（对外就是两封邮件）。写入侧再带一次可领谓词，
        使这条语句即使被将来的人拆成两段也不会静默退化。

        lease_seconds: 默认 5 分钟。
        """
        now = _now()
        expires = (datetime.now(timezone.utc) +
                   timedelta(seconds=lease_seconds)).isoformat()
        claimable = ("(claimed_at IS NULL OR claim_expires_at IS NULL "
                     "OR claim_expires_at < ?)")
        rows = self._conn.execute(
            "WITH due AS ("
            "  SELECT rowid AS rid FROM outbox_events"
            "  WHERE completed_at IS NULL AND " + claimable +
            "  ORDER BY available_at LIMIT ?)"
            " UPDATE outbox_events"
            " SET claimed_at=?, claimed_by=?, claim_expires_at=?"
            " WHERE rowid IN (SELECT rid FROM due)"
            "   AND completed_at IS NULL AND " + claimable +
            " RETURNING *",
            (now, limit, now, worker_id, expires, now)).fetchall()
        return [dict(row) for row in rows]

    def mark_completed(self, event_id: str, tenant_id: str, project_id: str,
                       note: str = "") -> None:
        """完成事件。``note`` 用于留下「为什么这条没有真的对外做」的读得懂的痕迹
        （典型是幂等去重）；不传时保持 ``last_error`` 原样。"""
        if note:
            self._conn.execute(
                "UPDATE outbox_events SET completed_at=?, last_error=?, "
                "attempt_count=attempt_count+1 "
                "WHERE event_id=? AND tenant_id=? AND project_id=?",
                (_now(), note, event_id, tenant_id, project_id))
            return
        self._conn.execute(
            "UPDATE outbox_events SET completed_at=?, last_error='', "
            "attempt_count=attempt_count+1 "
            "WHERE event_id=? AND tenant_id=? AND project_id=?",
            (_now(), event_id, tenant_id, project_id))

    def mark_retry(self, event_id: str, tenant_id: str, project_id: str, error: str) -> None:
        """可重试失败：立即释放租约，让事件重新可领。

        调用方**必须**先看 `attempt_count` 是否已到 `max_attempts`——这里不做预算
        判断，否则毒事件会在一次 `drain()` 里无限循环（曾经如此）。
        """
        self._conn.execute(
            "UPDATE outbox_events SET claimed_at=NULL, last_error=?, "
            "attempt_count=attempt_count+1 WHERE event_id=? AND tenant_id=? AND project_id=?",
            (error, event_id, tenant_id, project_id))

    def mark_unknown(self, event_id: str, tenant_id: str, project_id: str,
                     error: str) -> None:
        """对外调用**结果未知**（典型是超时）：离开可领集合，等人工核对。

        与 `mark_retry` 的区别是本条存在的全部理由：超时不证明没送达，自动重投
        就是第二次对外发送。与 `mark_terminal` 一样置 `completed_at`，但
        `last_error` 以 `UNKNOWN_OUTCOME:` 开头，供核对侧区分「失败终止」与
        「结果未知」。
        """
        self._conn.execute(
            "UPDATE outbox_events SET completed_at=?, claimed_at=NULL, "
            "last_error=?, attempt_count=attempt_count+1 "
            "WHERE event_id=? AND tenant_id=? AND project_id=?",
            (_now(), f"UNKNOWN_OUTCOME: {error}", event_id, tenant_id, project_id))

    def mark_terminal(self, event_id: str, tenant_id: str, project_id: str, error: str) -> None:
        self._conn.execute(
            "UPDATE outbox_events SET completed_at=?, last_error=?, "
            "attempt_count=attempt_count+1 WHERE event_id=? AND tenant_id=? AND project_id=?",
            (_now(), error, event_id, tenant_id, project_id))


class ExternalOperationRepository:
    """external_operations 表的 Repository。

    管理外部副作用操作的完整生命周期。
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(
        self,
        operation_id: str,
        tenant_id: str,
        project_id: str,
        provider: str,
        operation_kind: str,
        idempotency_key: str = "",
        request_hash: str = "",
    ) -> dict[str, Any]:
        """创建新操作记录。"""
        now = _now()
        self._conn.execute(
            "INSERT INTO external_operations"
            "(operation_id,tenant_id,project_id,idempotency_key,provider,"
            "operation_kind,request_hash,status,attempt,started_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (operation_id, tenant_id, project_id, idempotency_key, provider,
             operation_kind, request_hash, OP_PENDING, 0, now))
        return {"operation_id": operation_id, "status": OP_PENDING}

    def get(self, operation_id: str, tenant_id: str, project_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM external_operations "
            "WHERE operation_id=? AND tenant_id=? AND project_id=?",
            (operation_id, tenant_id, project_id)).fetchone()
        return dict(row) if row else None

    def find_by_idempotency_key(self, tenant_id: str, project_id: str,
                                 provider: str, idempotency_key: str,
                                 operation_kind: str = "") -> dict[str, Any] | None:
        """按幂等键查操作台账。

        ``operation_kind`` 必须能参与过滤：v16 的部分唯一索引键是
        ``(tenant, project, provider, operation_kind, idempotency_key)``，查询少了
        这一列就会在不同种类之间串键，命中哪一条取决于 SQLite 的返回顺序。
        """
        sql = ("SELECT * FROM external_operations "
               "WHERE tenant_id=? AND project_id=? AND provider=?"
               " AND idempotency_key=?")
        params: list[Any] = [tenant_id, project_id, provider, idempotency_key]
        if operation_kind:
            sql += " AND operation_kind=?"
            params.append(operation_kind)
        row = self._conn.execute(sql, params).fetchone()
        return dict(row) if row else None

    def transition_status(self, operation_id: str, tenant_id: str, project_id: str,
                          new_status: str, error: str = "",
                          external_reference: str = "") -> None:
        """状态转换（带合法性检查）。"""
        if new_status not in VALID_OP_STATUSES:
            raise ValueError(f"invalid status {new_status!r}")
        row = self._conn.execute(
            "SELECT status FROM external_operations "
            "WHERE operation_id=? AND tenant_id=? AND project_id=?",
            (operation_id, tenant_id, project_id)).fetchone()
        if row is None:
            raise ValueError(f"operation {operation_id} not found")
        current = row["status"]
        if new_status not in _VALID_TRANSITIONS.get(current, set()):
            raise ValueError(f"invalid transition {current} → {new_status}")
        now = _now()
        sets = ["status=?", "attempt=attempt+1"]
        params: list[Any] = [new_status]
        if error:
            sets.append("last_error=?")
            params.append(error)
        if external_reference:
            sets.append("external_reference=?")
            params.append(external_reference)
        if new_status in (OP_SUCCEEDED, OP_FAILED_TERMINAL, OP_COMPENSATED):
            sets.append("completed_at=?")
            params.append(now)
        params.extend([operation_id, tenant_id, project_id])
        self._conn.execute(
            f"UPDATE external_operations SET {', '.join(sets)} "
            "WHERE operation_id=? AND tenant_id=? AND project_id=?", params)

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn
