"""OutboxDispatcher — 异步消费 outbox 事件。

P2-M5: Outbox Runtime Activation

提供 run_once() / drain() 用于 CLI/test/manual 调用。
不要求后台 daemon。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any, Callable

from aipd_os.state.outbox import (
    ExternalOperationRepository,
    OutboxRepository,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class OutboxDispatcher:
    """异步 outbox 事件消费者。

    支持：
    - claim: 原子 claim + lease
    - dispatch: 通过 handler 执行外部操作
    - complete/retry/terminal/unknown: 操作结果记录
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        worker_id: str = "dispatcher-1",
    ) -> None:
        self._conn = conn
        self._worker_id = worker_id
        self._outbox = OutboxRepository(conn)
        self._operations = ExternalOperationRepository(conn)
        self._handlers: dict[str, Callable[..., Any]] = {}

    def register_handler(self, event_type: str,
                         handler: Callable[..., Any]) -> None:
        """注册事件处理器。"""
        self._handlers[event_type] = handler

    def run_once(self, limit: int = 10) -> list[dict[str, Any]]:
        """消费一批事件。"""
        claimed = self._outbox.claim_available(self._worker_id, limit)
        results = []
        for event in claimed:
            result = self._dispatch_one(event)
            results.append(result)
        self._conn.commit()
        return results

    def drain(self, max_iterations: int = 100) -> list[dict[str, Any]]:
        """持续消费直到无事件或达到 max_iterations。"""
        all_results = []
        for _ in range(max_iterations):
            batch = self.run_once()
            if not batch:
                break
            all_results.extend(batch)
        return all_results

    def _dispatch_one(self, event: dict[str, Any]) -> dict[str, Any]:
        """处理单个事件。"""
        event_type = event.get("event_type", "")
        handler = self._handlers.get(event_type)
        if handler is None:
            # 无处理器 → 标记 terminal
            self._outbox.mark_terminal(
                event["event_id"], event["tenant_id"],
                event["project_id"],
                f"no handler for event_type={event_type}")
            return {"event_id": event["event_id"], "status": "TERMINAL_NO_HANDLER"}

        try:
            handler(event)
            self._outbox.mark_completed(
                event["event_id"], event["tenant_id"],
                event["project_id"])
            return {"event_id": event["event_id"], "status": "COMPLETED"}
        except TimeoutError as exc:
            # 超时 → UNKNOWN_OUTCOME（不是 FAILED）
            self._outbox.mark_retry(
                event["event_id"], event["tenant_id"],
                event["project_id"], str(exc))
            return {"event_id": event["event_id"],
                    "status": "UNKNOWN_OUTCOME", "error": str(exc)}
        except ConnectionError as exc:
            # 网络错误 → retryable
            self._outbox.mark_retry(
                event["event_id"], event["tenant_id"],
                event["project_id"], str(exc))
            return {"event_id": event["event_id"],
                    "status": "RETRYABLE", "error": str(exc)}
        except Exception as exc:
            # 其他错误 → terminal
            self._outbox.mark_terminal(
                event["event_id"], event["tenant_id"],
                event["project_id"], str(exc))
            return {"event_id": event["event_id"],
                    "status": "TERMINAL", "error": str(exc)}
