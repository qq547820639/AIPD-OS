"""外部副作用的事件化：outbox 事件 → dispatcher → handler → ``external_operations`` 台账。

放在 ``execution/``（编排层）而不是 ``state/``：这里决定「谁在什么时候真的对外
发东西」，``state/outbox.py`` 只负责事件表与状态机的持久化。

三处安全边界（都是接线时才会踩到的）：

1. **先事件后执行**。执行记录（``execution_runs.db``）与状态库（``state.db``）是
   两个 SQLite 文件，跨文件没有事务能把它们绑在一起。所以选「事件可能存在而执行
   记录没有」而不是「执行记录说发过而事件没有」：前者最多多发一次且有台账可查，
   后者是供应商什么都没收到、系统却以为已发出。
2. **台账先行**。每次对外调用先在 ``external_operations`` 里占住幂等键，
   已 ``SUCCEEDED`` 就直接判定为做过；v16 的部分唯一索引
   ``(tenant, project, provider, operation_kind, idempotency_key)`` 兜住并发重放。
3. **口令不入库**。``outbox_events.payload_json`` 是明文落盘的，载荷里只放
   「在哪发、发给谁、发什么」；SMTP 口令在真正投递的那一刻从环境取。
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from typing import Any, Callable

from aipd_os.execution.runs import canonical_hash
from aipd_os.state.connection import ConnectionFactory
from aipd_os.state.dispatcher import OutboxDispatcher, attempt_budget
from aipd_os.state.errors import ExternalOperationUnknownError
from aipd_os.state.outbox import (
    OP_DISPATCHED,
    OP_FAILED_RETRYABLE,
    OP_FAILED_TERMINAL,
    OP_PENDING,
    OP_SUCCEEDED,
    OP_UNKNOWN_OUTCOME,
    ExternalOperationRepository,
    OutboxRepository,
)

EVENT_RFQ_SEND = "supply.rfq.send"
OPERATION_KIND_EMAIL = "rfq_email"
PROVIDER_SMTP = "smtp"


def rfq_idempotency_key(*, project_id: str, supplier: str, part: str,
                        quantity: Any = 1) -> str:
    """按**内容**派生幂等键：换供应商 / 换零件 / 换数量算新的一次询价。

    与 F-EXEC-01 的 ``auto:`` 键同一 doctrine——同一内容重驱动必须落到同一个键上，
    否则「重跑一次监督器」就等于给同一家供应商发两封信。
    """
    return "rfq:" + canonical_hash([project_id, supplier, part, str(quantity)])


class OutboxQueue:
    """把「要对外做的事」写成事件，交给 dispatcher 执行。"""

    def __init__(self, db_path: str | os.PathLike[str]) -> None:
        self._factory = ConnectionFactory(str(db_path))

    def enqueue(self, *, event_type: str, payload: dict[str, Any],
                tenant_id: str = "default", project_id: str = "",
                aggregate_type: str = "", aggregate_id: str = "",
                idempotency_key: str = "") -> str:
        """追加事件；外层已有事务时并入该事务（由 ``ConnectionFactory`` 保证）。"""
        event_id = f"EVT-{uuid.uuid4().hex[:16]}"
        with self._factory.transaction() as conn:
            OutboxRepository(conn).append_event(
                event_id, tenant_id, project_id, aggregate_type, aggregate_id,
                event_type, payload, idempotency_key=idempotency_key)
        return event_id

    def enqueue_rfq_send(self, *, tenant_id: str, project_id: str, work_id: str,
                         idempotency_key: str, message: dict[str, Any]) -> str:
        """排队一封 RFQ 邮件。``message`` 不含口令。"""
        return self.enqueue(
            event_type=EVENT_RFQ_SEND,
            payload={**message, "work_id": work_id},
            tenant_id=tenant_id, project_id=project_id,
            aggregate_type="WorkItem", aggregate_id=work_id,
            idempotency_key=idempotency_key)


def rfq_send_handler(conn: sqlite3.Connection,
                     send: Callable[..., str] | None = None
                     ) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """返回 outbox handler：查台账 → 没做过才真发 → 把结果写回台账。

    抛出的异常种类就是 dispatcher 的分类依据：
    ``TimeoutError`` → 事件结果未知（不重发）；``ConnectionError`` → 可重试。
    """
    sender = send
    ops = ExternalOperationRepository(conn)

    def handle(event: dict[str, Any]) -> dict[str, Any]:
        tenant = event["tenant_id"]
        project = event["project_id"]
        key = event.get("idempotency_key") or ""
        payload = json.loads(event.get("payload_json") or "{}")

        existing = ops.find_by_idempotency_key(
            tenant, project, PROVIDER_SMTP, key,
            operation_kind=OPERATION_KIND_EMAIL) if key else None
        if existing is not None and existing["status"] == OP_UNKNOWN_OUTCOME:
            # 结果未知 ≠ 可以重发：重新入队同一条也必须拒发，等人工核对
            raise ExternalOperationUnknownError(
                f"幂等键 {key} 的外部调用结果未知"
                f"（operation {existing['operation_id']}），需人工核对后才能重发")
        if existing is not None and existing["status"] == OP_SUCCEEDED:
            # 完成状态由 dispatcher 统一写（note 从返回值派生），这里不自己 mark
            return {"deduped": True,
                    "external_reference": existing.get("external_reference", "")}

        operation_id = existing["operation_id"] if existing is not None \
            else f"OP-{uuid.uuid4().hex[:16]}"
        if existing is None:
            try:
                ops.create(operation_id, tenant, project, provider=PROVIDER_SMTP,
                           operation_kind=OPERATION_KIND_EMAIL,
                           idempotency_key=key,
                           request_hash=canonical_hash(payload))
            except sqlite3.IntegrityError as exc:
                # 另一个 worker 已占住这个键：本次不发，交给预算内的下一次再看
                raise ConnectionError(
                    f"idempotency key {key!r} already claimed by another worker") from exc
        current = ops.get(operation_id, tenant, project) or {"status": OP_PENDING}
        if current["status"] != OP_DISPATCHED:
            # PENDING → DISPATCHED 与 FAILED_RETRYABLE → DISPATCHED 都是合法边，
            # 不必在此分叉；状态机本身会拒绝其它来源态。
            ops.transition_status(operation_id, tenant, project, OP_DISPATCHED)

        attempts, budget, exhausted = attempt_budget(event)
        try:
            message_id = (sender or _smtp_send)(
                payload.get("host", ""), int(payload.get("port") or 25),
                payload.get("username", ""), _smtp_password(),
                payload.get("from_addr", ""), list(payload.get("to_addrs") or []),
                payload.get("subject", ""), payload.get("body", ""))
        except TimeoutError as exc:
            ops.transition_status(operation_id, tenant, project,
                                  OP_UNKNOWN_OUTCOME, error=str(exc))
            raise
        except Exception as exc:  # noqa: BLE001 - 分类由异常类型决定，不吞
            if exhausted:
                ops.transition_status(operation_id, tenant, project,
                                      OP_FAILED_TERMINAL, error=str(exc))
            else:
                ops.transition_status(operation_id, tenant, project,
                                      OP_FAILED_RETRYABLE, error=str(exc))
            raise
        ops.transition_status(operation_id, tenant, project, OP_SUCCEEDED,
                              external_reference=message_id or "")
        return {"sent": True, "external_reference": message_id}

    return handle


def build_rfq_dispatcher(conn: sqlite3.Connection,
                         send: Callable[..., str] | None = None,
                         worker_id: str = "dispatcher-1") -> OutboxDispatcher:
    """装配好 RFQ 处理器的 dispatcher。"""
    dispatcher = OutboxDispatcher(conn, worker_id)
    dispatcher.register_handler(EVENT_RFQ_SEND, rfq_send_handler(conn, send=send))
    return dispatcher


def _smtp_send(*args: Any, **kwargs: Any) -> str:
    """默认投递：延迟导入，保持本模块可在无邮件依赖时被引用。"""
    from aipd_os.mail.client import send_email  # noqa: PLC0415

    return send_email(*args, **kwargs)


def _smtp_password() -> str:
    return os.environ.get("AIPD_SMTP_PASSWORD") or ""


__all__ = [
    "EVENT_RFQ_SEND",
    "OPERATION_KIND_EMAIL",
    "PROVIDER_SMTP",
    "OutboxQueue",
    "build_rfq_dispatcher",
    "rfq_idempotency_key",
    "rfq_send_handler",
]
