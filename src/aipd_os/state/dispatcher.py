"""OutboxDispatcher — 异步消费 outbox 事件。

P2-M5: Outbox Runtime Activation

提供 run_once() / drain() 用于 CLI/test/manual 调用。
不要求后台 daemon。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any, Callable

from aipd_os.state.outbox import OutboxRepository


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def attempt_budget(event: dict[str, Any]) -> tuple[int, int, bool]:
    """唯一一份重试预算判定：(本次之后的已试次数, 上限, 是否已用尽)。

    `claim_available` 返回的是**领取时**的行，`attempt_count` 还是本次之前的次数，
    所以这里 +1。上限缺失或为 0 一律按「只许一次」处理——预算的失败方向必须是
    早收口，不能退化成无限重试。事件表与台账都必须用它，否则两边结论会各说各话。
    """
    attempts = int(event.get("attempt_count", 0) or 0) + 1
    budget = int(event.get("max_attempts", 0) or 0) or 1
    return attempts, budget, attempts >= budget


class OutboxDispatcher:
    """异步 outbox 事件消费者。

    支持：
    - claim: 单语句原子 claim + lease
    - dispatch: 通过 handler 执行外部操作
    - complete/retry/terminal/unknown: 操作结果记录

    「这次对外调用到底成没成」记在 `external_operations` 上，由**各事件自己的
    handler** 写（只有它知道 provider / operation_kind / idempotency_key），
    dispatcher 只管事件表的可领集合与重试预算。
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        worker_id: str = "dispatcher-1",
    ) -> None:
        self._conn = conn
        self._worker_id = worker_id
        self._outbox = OutboxRepository(conn)
        self._handlers: dict[str, Callable[..., Any]] = {}

    def register_handler(self, event_type: str,
                         handler: Callable[..., Any]) -> None:
        """注册事件处理器。"""
        self._handlers[event_type] = handler

    def run_once(self, limit: int = 10) -> list[dict[str, Any]]:
        """消费一批事件。

        事务归属：只有当这条连接没有被上层的 `ConnectionFactory.transaction()`
        持有时才由本方法提交。否则一次 `run_once()` 会把调用方**尚未提交**的领域
        写一起提交掉、回滚失效——与 F-STATE-05 的 `executescript()` 同一形状。
        """
        claimed = self._outbox.claim_available(self._worker_id, limit)
        results = []
        for event in claimed:
            result = self._dispatch_one(event)
            results.append(result)
        if self._owns_transaction():
            self._conn.commit()
        return results

    def _owns_transaction(self) -> bool:
        """本连接是否由 dispatcher 负责提交（外层没有别人在管事务）。"""
        from aipd_os.state.connection import ConnectionFactory

        row = self._conn.execute("PRAGMA database_list").fetchone()
        path = row[2] if row and len(row) > 2 else ""
        if not path:
            return True                     # :memory: 没有登记可查，按自持处理
        return ConnectionFactory(path).active_transaction() is not self._conn

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
        """处理单个事件：结果分类与重试预算。"""
        event_type = event.get("event_type", "")
        handler = self._handlers.get(event_type)
        key = (event["event_id"], event["tenant_id"], event["project_id"])
        if handler is None:
            # 无处理器 → 标记 terminal
            self._outbox.mark_terminal(
                *key, f"no handler for event_type={event_type}")
            return {"event_id": event["event_id"], "status": "TERMINAL_NO_HANDLER"}

        try:
            returned = handler(event)
            # 幂等去重等「没真的对外做」的原因由 handler 说出来，完成状态由这里统一写；
            # 否则 handler 自己写完 note 会被这里的无条件完成覆盖成空。
            note = ""
            if isinstance(returned, dict) and returned.get("deduped"):
                ref = str(returned.get("external_reference") or "")
                note = f"deduped: operation already done{f' ({ref})' if ref else ''}"
            self._outbox.mark_completed(*key, note=note)
            out = {"event_id": event["event_id"], "status": "COMPLETED"}
            if note:
                out["deduped"] = True
            return out
        except TimeoutError as exc:
            # 超时 = 结果未知：可能已经送达，自动重投就是第二次对外发送
            self._outbox.mark_unknown(*key, str(exc))
            return {"event_id": event["event_id"],
                    "status": "UNKNOWN_OUTCOME", "error": str(exc)}
        except ConnectionError as exc:
            return self._retry_or_exhaust(event, "RETRYABLE", exc)
        except Exception as exc:
            # 其他错误 → terminal
            self._outbox.mark_terminal(*key, str(exc))
            return {"event_id": event["event_id"],
                    "status": "TERMINAL", "error": str(exc)}

    def _retry_or_exhaust(self, event: dict[str, Any], status: str,
                          exc: BaseException) -> dict[str, Any]:
        """可重试失败：`max_attempts` 是预算，不是装饰。

        claim 返回的 `attempt_count` 是**本次之前**的次数，所以本次之后是 +1。
        """
        attempts, budget, exhausted = attempt_budget(event)
        key = (event["event_id"], event["tenant_id"], event["project_id"])
        if exhausted:
            self._outbox.mark_terminal(
                *key, f"retry attempts exhausted ({attempts}/{budget}): {exc}")
            return {"event_id": event["event_id"],
                    "status": "TERMINAL_ATTEMPTS_EXHAUSTED",
                    "error": str(exc), "attempts": attempts}
        self._outbox.mark_retry(*key, str(exc))
        return {"event_id": event["event_id"], "status": status,
                "error": str(exc), "attempts": attempts}
