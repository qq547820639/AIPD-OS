"""``aipd truth`` —— 结构化事实的失效传播、返工待办与**真实返工执行**（F-TRUTH-PROP-01、F-REWORK）。

第 31 片只接「标 stale + 生成有界返工任务 + 产出 owner 可读变更说明」这半条链，
``run_rework``（真的执行一次返工）刻意留着不接：那时本仓没有返工执行器，而引擎在没有执行器时
只会把任务判 ``blocked``（``product_truth/propagation.py`` 的 "refusing fake success"
分支）——一条永远不可能成功的命令，比没有这条命令更容易被读成「返工已经跑过了」。
第 45 片补上执行器（``aipd truth rework``，判据见 ``cad/spec_rework.py``），并把当时钉住
缺口的断言**翻了极性**：现在由
``tests/test_truth_propagate_cli.py::TestReworkHalfIsWiredAndItsBoundaryStaysVisible``
钉「产品侧真有调用点」，而边界（只认 ``drawing_spec`` 制品、重算出 gap 即失败、
不认识的制品在烧 attempts 之前就拒）由 ``tests/test_truth_rework_cli.py`` 逐条钉住。

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
            print("未收口：有下游处于待返工状态。跑一次返工：aipd truth rework "
                  "--db <state.db> --project <p> --all-pending"
                  "（执行器只认图纸声明这一类制品；没有真执行器时引擎只判 blocked，"
                  "绝不伪造成功）。")
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


def cmd_truth_rework(args):
    """``aipd truth rework``：用真实返工执行器跑一次返工（`run_rework` 的产品调用点）。

    三条不退让的判据：

    - **不认识就不烧 attempts**：`--all-pending` 会扫到别的制品类型。今天有执行器的是
      `drawing_spec`（重算声明）、`drawing_dxf`（重跑出图）、`bom`（第 53 片：按当前 BOM
      行演进这一条版本记录）与 `bom_cost`（第 49 片：重跑核算），其余（`quote_batch`）必须在
      调用引擎**之前**被点名拒掉——拿一次注定失败的尝试去烧配额，等于让引擎替我们把
      "这格还没接执行器"伪装成"返工失败了三次"。
    - **成功只由执行器说**：`rework_fn` 的返回值来自重算结论（unchanged / rewrote /
      file_restored 才算成），gap 一律假。引擎随后才 bump 版本、关 stale。
    - **backoff 未到不算红**：`pending` 且带 `backoff_until` 是引擎的合法中间态，
      这里如实报"退避中"，退码仍按"是否还有未收口"判 4，不额外伪造。
    """
    if not args.task and not args.all_pending:
        print("要么给 --task RW-xxx，要么给 --all-pending：不指定就不知道该跑哪一条")
        return 2
    store, err = _open_store(args)
    if err is not None:
        return err

    from aipd_os.bom.bom_rework import SUPPORTED_ARTIFACT as BOM_ARTIFACT
    from aipd_os.bom.bom_rework import rework_bom_artifact
    from aipd_os.bom.cost_rework import SUPPORTED_ARTIFACT as COST_ARTIFACT
    from aipd_os.bom.cost_rework import rework_cost_artifact
    from aipd_os.cad.dxf_rework import SUPPORTED_ARTIFACT as DXF_ARTIFACT
    from aipd_os.cad.dxf_rework import rework_dxf_artifact
    from aipd_os.cad.spec_rework import SUPPORTED_ARTIFACT, artifact_kind, rework_artifact
    from aipd_os.cli.commands_drawing import render_dxf_from_record
    from aipd_os.cli.commands_manufacturing import bom_from_record, recalc_cost_from_record
    from aipd_os.product_truth.propagation import PropagationEngine, ReworkExhaustedError

    supported = [SUPPORTED_ARTIFACT, DXF_ARTIFACT, BOM_ARTIFACT, COST_ARTIFACT]
    rework_db_path = str(args.db)
    rework_project = (getattr(args, "project", None)
                      or getattr(store, "project_id", None))

    def run_executor(kind: str, truth_id: str) -> dict:
        if kind == DXF_ARTIFACT:
            return rework_dxf_artifact(store, truth_id,
                                       render=render_dxf_from_record)
        if kind == BOM_ARTIFACT:
            return rework_bom_artifact(
                store, truth_id,
                recalc=lambda meta: bom_from_record(
                    meta, db_path=rework_db_path, project_id=rework_project))
        if kind == COST_ARTIFACT:
            return rework_cost_artifact(
                store, truth_id,
                recalc=lambda meta: recalc_cost_from_record(
                    meta, db_path=rework_db_path, project_id=rework_project))
        return rework_artifact(store, truth_id)

    engine = PropagationEngine(store)
    if args.task:
        wanted = [args.task]
    else:
        wanted = [str(t["task_id"]) for t in
                  (x.to_dict() for x in engine.list_tasks(status="pending"))
                  if t.get("task_id")]

    results, refused = [], []
    for task_id in wanted:
        try:
            task = engine.get_task(task_id)
        except Exception as exc:
            refused.append({"task_id": task_id, "truth_id": None,
                            "artifact_kind": None,
                            "reason": f"任务读不到：{type(exc).__name__}: {exc}"})
            continue
        kind = artifact_kind(store, task.truth_id)
        if kind not in supported:
            refused.append({"task_id": task_id, "truth_id": task.truth_id,
                            "artifact_kind": kind,
                            "reason": f"本执行器只认 {' / '.join(supported)}；"
                                      "不烧 attempts，这条任务仍是 pending 并如实点名"})
            continue
        detail: dict[str, Any] = {}

        def rework_fn(truth_id: str, _detail: dict[str, Any] = detail,
                      _kind: str = kind) -> bool:
            outcome = run_executor(_kind, truth_id)
            _detail.clear()
            _detail.update(outcome)
            return outcome["ok"] is True

        try:
            engine_outcome = engine.run_rework(task_id, rework_fn=rework_fn)
        except ReworkExhaustedError as exc:
            engine_outcome = {"task": None, "reworked": False, "exhausted": True,
                              "message": str(exc)}
        except Exception as exc:
            print(f"返工执行失败 {task_id}：{type(exc).__name__}: {exc}")
            return 2
        results.append({"task_id": task_id, "truth_id": task.truth_id,
                        "engine": engine_outcome, "executor": dict(detail)})

    unresolved = [r for r in results
                  if (r["engine"] or {}).get("task", {})
                  and r["engine"]["task"].get("status") != "succeeded"]
    pending = bool(unresolved or refused)
    result = {"command": "truth rework", "ok": not pending,
              "selected": wanted, "results": results, "refused": refused,
              "still_open": [r["task_id"] for r in unresolved],
              "supported_artifacts": supported}

    def prose():
        print(f"返工执行 {len(wanted)} 条（执行器认的制品："
              f"{', '.join(supported)}）")
        for r in results:
            task = (r["engine"] or {}).get("task") or {}
            ex = r["executor"] or {}
            print(f"  · {r['task_id']} → {r['truth_id']}："
                  f"执行器 {ex.get('outcome', '未执行')}，"
                  f"任务状态 {task.get('status', '?')} "
                  f"已试 {task.get('attempts', '?')}/{task.get('max_attempts', '?')}")
            if ex.get("path"):
                digest = ex.get("spec_sha256") or ex.get("dxf_sha256")
                print(f"      产物 {ex['path']} 哈希 {str(digest)[:16]}"
                      f" 边 {ex.get('edges', 0)} 条 文件写入 {ex.get('file_written')}")
            if ex.get("total_cost") is not None:
                print(f"      重算后总成本 {ex['total_cost']}"
                      f"（输入签名 {str(ex.get('input_signature') or '')[:16]}"
                      f" 边 {ex.get('edges', 0)} 条）")
            if r["engine"].get("exhausted"):
                print(f"      已达上限：{r['engine']['message']}")
            if task.get("status") == "pending" and task.get("backoff_until"):
                print(f"      退避中，下一次不早于 {task['backoff_until']}")
        for r in refused:
            print(f"  × {r['task_id']} {r.get('truth_id')}：{r['reason']}")
        if pending:
            print("未收口：仍有返工任务不是 succeeded（退码 4）。")
        else:
            print("本批返工全部 succeeded。")
    _emit(args, result, prose)
    return 4 if pending else 0


def cmd_truth_sweep(args):
    """``aipd truth sweep``：把「发现漂移」接到「沿边标 stale + 建返工任务」上。

    一次进程内现算现用（判据与不选 plan 文件的理由都写在 `product_truth/sweep.py` 的
    模块 docstring）：先用第 51/52 片那五支 resolver 算出「漂移且还 active」的清单，
    再按**边表**找每条记录的上游，对找得到的上游调用与 `truth propagate` **同一个**
    入口 `PropagationEngine.on_upstream_changed`；找不到的逐条点名不办。

    `--dry-run` 只交计划，一个字节都不写——这条命令的默认动作是写，
    所以判「本次到底改没改」要按 `dry_run` 这一格读，不能凭退码。
    """
    from aipd_os.cli.commands_drift import build_resolvers
    from aipd_os.cli.commands_manufacturing import _resolve_project
    from aipd_os.product_truth import ProductTruthStore
    from aipd_os.product_truth.drift import DRIFTED, scan_drift
    from aipd_os.product_truth.lineage import LineageGraph
    from aipd_os.product_truth.propagation import PropagationEngine
    from aipd_os.product_truth.sweep import plan_sweep
    from aipd_os.state.db import AIPDStateDB

    db = Path(args.db)
    if not db.is_file():
        print(f"状态库不存在：{db}")
        return 2
    tenant = str(getattr(args, "tenant", None) or "default")
    dry_run = bool(getattr(args, "dry_run", False))
    try:
        pid = _resolve_project(AIPDStateDB(str(db)), getattr(args, "project", None))
    except ValueError as exc:
        print(f"错误：{exc}")
        return 1
    store = ProductTruthStore(str(db), tenant_id=tenant, project_id=pid)
    graph = LineageGraph(store, tenant_id=tenant, project_id=pid)
    try:
        report = scan_drift(store, resolvers=build_resolvers(str(db), pid, tenant),
                            tenant_id=tenant, project_id=pid)
    except Exception as exc:  # noqa: BLE001 - 扫不出来不是「没漂移」，判用法错误
        print(f"漂移扫描失败：{type(exc).__name__}: {exc}")
        return 2
    if report["nothing_scanned"]:
        print("库里没有可扫的有效制品版本记录 ⇒  sweep 什么都不做"
              "（先把 aipd drawing generate --db / cost calc --truth-lineage 跑起来）")
        return 2

    plan = plan_sweep(report["buckets"][DRIFTED],
                      lambda rid: graph.upstream_of(rid, tenant_id=tenant,
                                                    project_id=pid))
    engine = PropagationEngine(store)
    applied = []
    for target in plan["targets"]:
        if dry_run:
            applied.append({"upstream_id": target["upstream_id"],
                            "reason": target["reason"], "dry_run": True,
                            "triggered_by": target["triggered_by"]})
            continue
        out = engine.on_upstream_changed(target["upstream_id"],
                                         reason=target["reason"])
        applied.append({"upstream_id": target["upstream_id"],
                        "reason": target["reason"], "dry_run": False,
                        "triggered_by": target["triggered_by"],
                        "affected": out.get("affected") or [],
                        "newly_stale": out.get("stale") or [],
                        "tasks": out.get("tasks") or []})
    # 曾想过一格「落了刀但 tasks 为空 = 这一刀什么都没做成」的读数，实测删掉：
    # 引擎对 affected 里每条**都**建任务（`propagation.py:54-61` 的建任务在状态判断之外），
    # 所以那一格恒为空 —— 留一个永远为空的字段就是对读者的假承诺。
    # 电池 S7 臂（把 pending 里这一项摘掉）当场存活，是它证明了这一点。
    pending = bool(plan["targets"] or plan["orphaned"])
    result = {
        "command": "truth sweep", "project": pid, "dry_run": dry_run,
        "ok": not pending, "scanned": report["scanned"],
        "drifted": report["counts"][DRIFTED],
        "drifted_active": plan["drifted_active"],
        "targets": applied, "orphaned": plan["orphaned"],
        "no_upstream_edge": len(plan["orphaned"]),
        "nothing_scanned": report["nothing_scanned"],
    }

    def prose():
        head = ("预演（--dry-run，不写任何东西）" if dry_run else "已落刀")
        print(f"扫描 {report['scanned']} 条有效制品记录：漂移 "
              f"{report['counts'][DRIFTED]}，其中还挂着 active 的 "
              f"{plan['drifted_active']} 条 ⇒ {head}")
        for a in applied:
            print(f"  · 上游 {a['upstream_id']}：{a['reason']}")
            for t in a["triggered_by"]:
                print(f"      由 {t['record_id']}（{t['artifact']}）触发")
            if not a.get("dry_run"):
                print(f"      新置 stale {len(a.get('newly_stale') or [])} 条、"
                      f"建返工任务 {len(a.get('tasks') or [])} 条"
                      f"（影响面 {len(a.get('affected') or [])} 条）")
        for o in plan["orphaned"]:
            print(f"  × 不办：{o['record_id']}（{o['artifact']}）{o['reason']}")
        if not pending:
            print("没有「漂移且还 active」的记录 ⇒ 无事可做。")
        elif dry_run:
            print("⇒ 以上是计划；去掉 --dry-run 才会真的标 stale 与建任务。")
        else:
            print("⇒ 已按边表落刀；下一步 `aipd truth rework --all-pending` 执行返工。")
    _emit(args, result, prose)
    return 4 if pending else 0
