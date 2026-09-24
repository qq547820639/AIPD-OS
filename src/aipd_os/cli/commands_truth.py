"""``aipd truth`` —— 结构化事实的失效传播与返工待办（F-TRUTH-PROP-01）。

诚实前提：本轮只接「标 stale + 生成有界返工任务 + 产出 owner 可读变更说明」这半条链。
``run_rework``（真的执行一次返工）**刻意不接**：本仓没有返工执行器，而引擎在没有执行器时
只会把任务判 ``blocked``（``product_truth/propagation.py`` 的 "refusing fake success"
分支）——一条永远不可能成功的命令，比没有这条命令更容易被读成「返工已经跑过了」。
这个缺口由 ``tests/test_truth_propagate_cli.py::TestUnwiredHalfStaysVisible`` 钉成断言。

「本次新置 stale」与「此前已 stale」必须分开报：引擎的 ``stale`` 只含本次新置的那批，
空列表如果原样转述，读的人会把「下游早就过期、还欠着返工」听成「这次什么都没影响」。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from aipd_os.cli._helpers import _emit


def _open_store(args) -> tuple[Any, int | None]:
    """返回 ``(store, None)`` 或 ``(None, 退出码)``。

    库不存在与「库在但读不出 truth」都是 2：读不到不等于「没有记录」，
    拿空结果往下走就会把一次坏路径判成「传播过了，什么都没影响」。
    """
    db = Path(args.db)
    if not db.is_file():
        print(f"状态库不存在：{db}")
        return None, 2
    try:
        from aipd_os.product_truth.store import ProductTruthStore

        store = ProductTruthStore(str(db), tenant_id=args.tenant,
                                  project_id=args.project)
        return store, None
    except Exception as exc:      # 读不到权威事实不是「没有事实」
        print(f"Product Truth 读取失败：{type(exc).__name__}: {exc}")
        return None, 2


def _upstream_kind(store: Any, upstream_id: str) -> str:
    """上游是不是本作用域内的 truth 记录——认不出就说是 PI/外部上游，不编详情。"""
    try:
        store.get(upstream_id)
        return "truth"
    except KeyError:
        return "intelligence_or_external"


def cmd_truth_propagate(args):
    """``aipd truth propagate``：沿血缘把下游标 stale 并生成有界返工任务。"""
    if args.max_attempts is not None and args.max_attempts <= 0:
        print("--max-attempts 必须 > 0：<=0 会被引擎当合法上限"
              "（一跑就 blocked，或永不 blocked），不静默接受")
        return 2
    store, err = _open_store(args)
    if err is not None:
        return err
    from aipd_os.product_truth.propagation import PropagationEngine

    engine = PropagationEngine(store)
    if args.max_attempts is not None:
        engine.default_max_attempts = int(args.max_attempts)
    try:
        outcome = engine.on_upstream_changed(args.upstream, reason=args.reason)
    except Exception as exc:
        print(f"失效传播失败：{type(exc).__name__}: {exc}")
        return 2

    affected = [str(r) for r in outcome["affected"]]
    marked = [str(r) for r in outcome["stale"]]
    already = [r for r in affected if r not in set(marked)]
    tasks = list(outcome["tasks"])
    pending = bool(affected)
    result = {"command": "truth propagate", "ok": not pending,
              "upstream": args.upstream,
              "upstream_kind": _upstream_kind(store, args.upstream),
              "affected": affected, "marked_stale": marked,
              "already_stale": already, "tasks": tasks,
              "pending_rework": pending,
              "explanation": outcome["explanation"]}

    def prose():
        print(f"上游 {args.upstream}（{result['upstream_kind']}）→ 受影响下游 "
              f"{len(affected)} 条：本次新置 stale {len(marked)}，"
              f"此前已 stale {len(already)}")
        for rid in marked:
            print(f"  · {rid} → stale")
        for rid in already:
            print(f"  · {rid} 早已 stale（未重复标记），返工任务已另计")
        print(f"返工任务：{len(tasks)} 条（有界，上限 "
              f"{engine.default_max_attempts} 次尝试）")
        for t in tasks:
            print(f"  · {t['task_id']} → {t['truth_id']} 状态 {t['status']} "
                  f"已试 {t['attempts']}/{t['max_attempts']}")
        exp = result["explanation"]
        print(f"变更说明：{exp['what_changed']}")
        print(f"  为何影响：{exp['why_affected']}")
        print(f"  修复计划：{exp['fix_plan']}")
        print(f"  需要批准：{exp['approval_needed']}")
        if pending:
            print("未收口：有下游处于待返工状态。返工的**执行**（run_rework）本仓尚未接线"
                  "（没有真实返工执行器时引擎只判 blocked，绝不伪造成功）。")
    _emit(args, result, prose)
    return 4 if pending else 0


def cmd_truth_tasks(args):
    """``aipd truth tasks``：列本作用域的返工待办（只读，不改任何状态）。"""
    store, err = _open_store(args)
    if err is not None:
        return err
    from aipd_os.product_truth.propagation import PropagationEngine

    engine = PropagationEngine(store)
    try:
        tasks = [t.to_dict() for t in engine.list_tasks(status=args.status)]
    except Exception as exc:
        print(f"返工待办读取失败：{type(exc).__name__}: {exc}")
        return 2

    def prose():
        scope = f"{args.tenant}/{args.project}"
        filtered = f"（按状态 {args.status} 过滤）" if args.status else ""
        print(f"返工待办 {len(tasks)} 条{filtered}，作用域 {scope}")
        for t in tasks:
            backoff = f"，退避至 {t['backoff_until']}" if t.get("backoff_until") else ""
            print(f"  · {t['task_id']} {t['truth_id']} 状态 {t['status']} "
                  f"已试 {t['attempts']}/{t['max_attempts']} 原因 {t['reason']}"
                  f"{backoff}")
        if not tasks:
            print("空列表只说明本作用域没有**任务**行，不代表没有 stale 记录"
                  "（任务由 aipd truth propagate 生成）。")
    _emit(args, {"command": "truth tasks", "ok": True, "count": len(tasks),
                 "status_filter": args.status, "tasks": tasks}, prose)
    return 0
