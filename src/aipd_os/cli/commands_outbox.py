"""``aipd outbox`` —— 对外副作用事件的显式驱动与核对。

drain：领一批事件并真执行（幂等台账保证同一内容只对外做一次）。
review：列出**未收口**的外部操作（还挂着 / 还能重试 / 结果未知 / 正在补偿），
        有未收口项时返回非零，便于运维与 CI 接得住。

为什么需要 review 这个读出口（F-EXEC-05）：`mark_unknown` 会给事件置
`completed_at`——事件必须离开可领集合，否则「超时」会被当成「可以重投」，
供应商就可能收到两封信。代价是这些行从此不在任何 `completed_at IS NULL`
的查询里，包括本命令自己的 `pending`。也就是说：**一次超时不会显示为失败、
不会显示为待发、也不会显示为待办**，除非有人来查台账。
"""
from __future__ import annotations

from pathlib import Path

from aipd_os.cli._helpers import _emit


def _limit(args, default: int) -> int:
    return max(1, int(getattr(args, "limit", default) or default))


def cmd_outbox(args):
    sub = getattr(args, "outbox_cmd", "drain") or "drain"
    db = Path(str(getattr(args, "db", "") or ""))
    if not db.is_file():
        # 绝不替用户创建状态库：路径写错必须就地报错（本轮真发生过把别的对象
        # 当路径传进来，在仓库根建了 4 个文件，测试全绿没人看见）。
        payload = {"command": f"outbox {sub}", "ok": False, "status": "HOLD",
                   "reason": f"状态库不存在：{db}", "db": str(db)}
        _emit(args, payload,
              lambda: print(payload["reason"]))
        return 2

    from aipd_os.state.connection import ConnectionFactory
    from aipd_os.state.outbox import ExternalOperationRepository

    worker_id = getattr(args, "worker_id", "cli-outbox") or "cli-outbox"
    with ConnectionFactory(str(db)).connection() as conn:
        ledger = ExternalOperationRepository(conn)
        if sub == "review":
            return _review(args, db, ledger)
        return _drain(args, conn, db, worker_id, ledger)


def _review(args, db, ledger) -> int:
    unresolved = ledger.list_unresolved(limit=_limit(args, 100))
    payload = {
        "command": "outbox review",
        "ok": not unresolved,
        "status": "HOLD" if unresolved else "DONE",
        "db": str(db),
        "needs_review": len(unresolved),
        "unresolved": [{"operation_id": r["operation_id"],
                        "tenant_id": r["tenant_id"],
                        "project_id": r["project_id"],
                        "provider": r["provider"],
                        "operation_kind": r["operation_kind"],
                        "idempotency_key": r["idempotency_key"],
                        "status": r["status"],
                        "attempt": r["attempt"],
                        "started_at": r["started_at"],
                        "external_reference": r["external_reference"],
                        "last_error": r["last_error"]}
                       for r in unresolved],
    }

    def prose():
        if not unresolved:
            print("外部操作台账无未收口项")
            return
        print(f"{len(unresolved)} 条外部操作未收口，需人工核对（不自动重发）：")
        for r in unresolved:
            print(f"  {r['operation_id']}  {r['status']}  "
                  f"{r['idempotency_key']}  {r['last_error'][:60]}")

    _emit(args, payload, prose)
    return 4 if unresolved else 0


def _drain(args, conn, db, worker_id, ledger) -> int:
    from aipd_os.execution.side_effects import build_rfq_dispatcher

    limit = _limit(args, 10)
    dispatcher = build_rfq_dispatcher(conn, worker_id=worker_id)
    results = dispatcher.run_once(limit=limit)
    statuses = {r["event_id"]: r.get("status", "") for r in results}
    notes = {row["event_id"]: (row["last_error"] or "") for row in conn.execute(
        "SELECT event_id, last_error FROM outbox_events"
        " WHERE completed_at IS NOT NULL")}
    sent = sum(1 for eid, st in statuses.items()
               if st == "COMPLETED" and not notes.get(eid))
    deduped = sum(1 for eid, st in statuses.items()
                  if st == "COMPLETED" and notes.get(eid))
    pending = conn.execute(
        "SELECT COUNT(*) FROM outbox_events WHERE completed_at IS NULL"
    ).fetchone()[0]
    unresolved_after = ledger.list_unresolved(limit=_limit(args, 100))

    payload = {
        "command": "outbox drain",
        "ok": all(r.get("status") != "TERMINAL" for r in results),
        "db": str(db),
        "results": results,
        "sent": sent,
        "deduped": deduped,
        "pending": pending,
        # 结果未知的行既不在 sent 也不在 pending 里，只有这一个数看得见它
        "needs_review": len(unresolved_after),
        "unresolved_statuses": sorted({r["status"] for r in unresolved_after}),
    }

    def prose():
        if not results:
            print(f"没有可消费的 outbox 事件（待办 {pending} 条）")
            if payload["needs_review"]:
                print(f"另有 {payload['needs_review']} 条外部操作未收口："
                      "用 aipd outbox review 查看")
            return
        print(f"本次消费 {len(results)} 件：真发 {sent}、幂等去重 {deduped}、"
              f"待办 {pending}、待核对 {payload['needs_review']}")
        for r in results:
            print(f"  {r['event_id']}  {r['status']}"
                  + (f"  {r['error']}" if r.get("error") else ""))

    _emit(args, payload, prose)
    return 0 if payload["ok"] else 4


__all__ = ["cmd_outbox"]
