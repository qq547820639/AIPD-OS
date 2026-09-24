"""``aipd outbox drain`` —— 消费 outbox 里的对外副作用事件。

显式驱动、不做后台守护：外部副作用什么时候真的发生，必须是一个可指认的入口
（CLI / 监督器 / 运维脚本），而不是「某个线程大概在跑」。缺 SMTP 配置时
handler 会抛 ``ConnectionError`` ⇒ 事件按预算重试后终止，绝不伪造已发送。
"""
from __future__ import annotations

from aipd_os.cli._helpers import _emit


def cmd_outbox(args):
    from aipd_os.execution.side_effects import build_rfq_dispatcher
    from aipd_os.state.connection import ConnectionFactory

    limit = max(1, int(getattr(args, "limit", 10) or 10))
    factory = ConnectionFactory(str(args.db))
    with factory.connection() as conn:
        dispatcher = build_rfq_dispatcher(conn, worker_id=getattr(
            args, "worker_id", "cli-outbox"))
        results = dispatcher.run_once(limit=limit)
        statuses = {r["event_id"]: r.get("status", "") for r in results}
        rows = conn.execute(
            "SELECT event_id, last_error FROM outbox_events"
            " WHERE completed_at IS NOT NULL").fetchall()
        notes = {row["event_id"]: (row["last_error"] or "") for row in rows}
        sent = sum(1 for eid, status in statuses.items()
                   if status == "COMPLETED" and not notes.get(eid))
        deduped = sum(1 for eid, status in statuses.items()
                      if status == "COMPLETED" and notes.get(eid))
        pending = conn.execute(
            "SELECT COUNT(*) FROM outbox_events WHERE completed_at IS NULL"
        ).fetchone()[0]

    payload = {
        "command": "outbox drain",
        "ok": all(r.get("status") != "TERMINAL" for r in results),
        "db": str(args.db),
        "results": results,
        "sent": sent,
        "deduped": deduped,
        "pending": pending,
    }

    def prose():
        if not results:
            print(f"没有可消费的 outbox 事件（待办 {pending} 条）")
            return
        print(f"本次消费 {len(results)} 件："
              f"真发 {sent}、幂等去重 {deduped}、待办 {pending}")
        for r in results:
            print(f"  {r['event_id']}  {r['status']}"
                  + (f"  {r['error']}" if r.get("error") else ""))

    _emit(args, payload, prose)
    return 0 if payload["ok"] else 4


__all__ = ["cmd_outbox"]
