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
                  "（执行器只认登记了 SUPPORTED_ARTIFACT 的那几类制品；"
                  "没有真执行器时引擎只判 blocked，"
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


def cmd_truth_ctq_add(args) -> int:
    """``aipd ctq add``：把一条 CTQ **由人声明**进 Product Truth（链头的生产者）。

    判据与"为什么不能让 PI gate 顺带派生"都写在 `product_truth/ctq.py` 的模块 docstring：
    `record_type="ctq"` 在第 56 片之前只有读者（发布证据分母、`drawing spec` 的输入、返工重算），
    全仓排除 `tests/` 后没有任何写入点，所以链条第二跳在真库里根本没有输入——
    这一条就是那格的**生产者**（改动入口见 `aipd ctq revise` / `aipd ctq deprecate`）。

    数值参数**故意不用 `argparse type=float`**：校验只留 `declare_ctq` 一处，
    错误文案要能点名"是哪一格、为什么"，而不是 argparse 的 usage 半句。
    信任级不自封：由 `gate_criteria._derive_trust` 推导（无 `--test-ref` 就是
    `unverified`），与 P0-08「Owner 批准本身 ≠ verified」同一条规则。
    """
    from aipd_os.product_truth.ctq import CtqDeclarationError, declare_ctq

    store, err = _open_store(args)
    if err is not None:
        return err
    try:
        result = declare_ctq(
            store, feature=args.feature, drawing_feature=args.drawing_feature,
            nominal=args.nominal, lower_limit=args.lower, upper_limit=args.upper,
            inspection_method=args.inspection, declared_by=args.by,
            epistemic_status=args.epistemic, test_refs=args.test_ref or [],
            note=args.note)
    except CtqDeclarationError as exc:
        print(f"声明被拒：{exc}")
        return 2
    except Exception as exc:  # noqa: BLE001 - 写不进去不是"没写成功"
        print(f"CTQ 写入失败：{type(exc).__name__}: {exc}")
        return 2
    payload = {"command": "ctq add", "ok": True, **result}

    def prose():
        low, high = result["limits"]
        print(f"{'已写入' if result['created'] else '已存在，未另起一条'}"
              f" CTQ {result['record_id']}：{result['feature']} @ "
              f"{result['drawing_feature']}，合格域 [{low:g}, {high:g}]，"
              f"标称 {result['nominal']:g}，检验方法 {result['inspection_method']}")
        refs = result.get("test_refs") or []
        print(f"  信任级 {result['trust_level']}"
              f"（认识论态 {result['epistemic_status']}，验证引用 {len(refs)} 条"
              + ("" if refs else " ⇒ 没有引用就不自封 verified") + "）")
        if not result["created"]:
            print(f"  {result['reason']}")
        print("  下一步：aipd drawing spec --db <state.db> --out <spec.json>"
              "（按当前 active CTQ 生成图纸声明，再 aipd drawing generate 出图）")
    _emit(args, payload, prose)
    return 0


def _ctq_audit(args: Any, action: str, before: Any, after: Any) -> str | None:
    """把"谁在什么时候把什么改成了什么"写进既有的 `audit_log`；返回错误文案（None=成功）。

    本仓不新造审计通道：`AIPDStateDB.add_audit` 已经带 `before_json`/`after_json`
    （`state/db.py:1073`），形状正好。写不进去**不算收口**（调用方判 4），
    因为"改了但没人知道是谁改的"正是这两条命令要消除的那格。
    """
    try:
        from aipd_os.state.db import AIPDStateDB

        AIPDStateDB(str(args.db)).add_audit(
            actor=args.by, action=action, project_id=args.project,
            tenant_id=args.tenant, before=before, after=after)
    except Exception as exc:  # noqa: BLE001 - 报出来，由调用方判未收口
        return f"{type(exc).__name__}: {exc}"
    return None


def cmd_truth_ctq_revise(args: Any) -> int:
    """``aipd ctq revise``：改一条已声明 CTQ 的合格域，另起新版本并留下被取代的旧值。"""
    from aipd_os.product_truth.ctq import CtqDeclarationError, revise_ctq

    store, err = _open_store(args)
    if err is not None:
        return err
    try:
        result = revise_ctq(
            store, record_id=args.record, revised_by=args.by,
            nominal=args.nominal, lower_limit=args.lower, upper_limit=args.upper,
            inspection_method=args.inspection, epistemic_status=args.epistemic,
            test_refs=args.test_ref if args.test_ref is not None else None,
            note=args.note, tenant_id=args.tenant, project_id=args.project)
    except CtqDeclarationError as exc:
        print(f"修订被拒：{exc}")
        return 2
    except Exception as exc:  # noqa: BLE001 - 写不进去不是"没写成功"
        print(f"CTQ 修订失败：{type(exc).__name__}: {exc}")
        return 2

    audit_error = None
    if result["changed"]:
        audit_error = _ctq_audit(args, "ctq.revise", result["before"], result["after"])
    payload = {"command": "ctq revise", "ok": audit_error is None,
               "audit_error": audit_error, **result}

    def prose():
        if not result["changed"]:
            print(f"未改动：{result['reason']}（{result['record_id']} 保持原样）")
            return
        print(f"已修订：{result['superseded']} → 新版本 {result['record_id']}"
              f"（version {result['version']}，合格域 "
              f"[{result['limits'][0]:g}, {result['limits'][1]:g}]）")
        print(f"  旧值 [{result['before']['lower_limit']:g}, "
              f"{result['before']['upper_limit']:g}] 仍留在库里，状态 superseded")
        print(f"  信任级 {result['trust_level']}"
              f"（认识论态 {result['epistemic_status']}，验证引用 "
              f"{len(result.get('test_refs') or [])} 条）")
        print("  下一步：aipd truth drift → aipd truth sweep → aipd truth rework"
              "（引用旧版本的图纸声明会被源面点名漂移）")
        if audit_error:
            print(f"  未收口：审计行没写进去（{audit_error}）⇒"
                  " 要求内容已改但没人知道是谁改的，退码 4")
    _emit(args, payload, prose)
    return 4 if audit_error else 0


def cmd_truth_ctq_deprecate(args: Any) -> int:
    """``aipd ctq deprecate``：停用一条 CTQ，写明理由与取代它的那条（如果有）。"""
    from aipd_os.product_truth.ctq import deprecate_ctq

    store, err = _open_store(args)
    if err is not None:
        return err
    try:
        result = deprecate_ctq(store, record_id=args.record, by=args.by,
                               reason=args.reason, replaced_by=args.replaced_by,
                               tenant_id=args.tenant, project_id=args.project)
    except Exception as exc:  # noqa: BLE001 - 拒绝文案要点名是哪一格
        from aipd_os.product_truth.ctq import CtqDeclarationError

        if isinstance(exc, CtqDeclarationError):
            print(f"停用被拒：{exc}")
        else:
            print(f"CTQ 停用失败：{type(exc).__name__}: {exc}")
        return 2

    audit_error = _ctq_audit(args, "ctq.deprecate", result["before"], result["after"])
    payload = {"command": "ctq deprecate", "ok": audit_error is None,
               "audit_error": audit_error, **result}

    def prose():
        lim = result["limits"]
        print(f"已停用 {result['record_id']}：{result['feature']} @ "
              f"{result['drawing_feature']}（原合格域 "
              f"[{lim[0]:g}, {lim[1]:g}]）")
        print(f"  理由：{args.reason}")
        print("  取代它的那条：" + (result["replaced_by"] or "（未指明 —— "
                                   "发布门禁会把它当'要求被撤回'来读，请自行确认图上不再需要它）"))
        print("  下一步：aipd truth drift（引用它的声明会因上游不再 active 被判漂移）")
        if audit_error:
            print(f"  未收口：审计行没写进去（{audit_error}），退码 4")
    _emit(args, payload, prose)
    return 4 if audit_error else 0


def cmd_truth_ctq_list(args: Any) -> int:
    """``aipd ctq list``：链头第一个**面向人**的读面（第 62 片）。

    补的是第 60 片量具登记下的那条缺席：三个写者、四个读者，
    但没人能问出"现在有效的是哪几条、限值与版本各是几"。

    两条刻意的形状：
    1. **默认只列 `active`，且必须自报排除了几条各是什么态**——只报"1 条"而不说
       "另有 2 条不在有效名单里"，读面就成了第二个 `_collect_ctq`（它正是只含 active
       且不说明排除），而"要求被撤了几条"恰是属主最该看见的东西；
    2. **只读不写**：不碰 `audit_log`。那条通道记的是"谁改了事实"，
       把每次查看都写进去会让它再也回答不出那个问题。
    """
    from aipd_os.product_truth.ctq import list_ctq

    store, err = _open_store(args)
    if err is not None:
        return err
    try:
        result = list_ctq(store, tenant_id=args.tenant, project_id=args.project,
                          include_all=args.all)
    except Exception as exc:  # noqa: BLE001 - 读不出来必须点名，不能退成空清单
        print(f"CTQ 读取失败：{type(exc).__name__}: {exc}")
        return 2
    payload = {"command": "ctq list", "ok": True, **result}

    def prose():
        scope = result["scope"]
        view = "全部状态" if args.all else "只列 active"
        print(f"CTQ 名单（tenant={scope['tenant_id']} project={scope['project_id']}，"
              f"共 {result['total']} 条记录，{view}）")
        if not result["records"]:
            print("  0 条 —— 这个作用域里"
                  + ("没有可列的" if args.all else "没有有效的")
                  + " CTQ 声明；链条第二跳（aipd drawing spec）此刻没有输入")
            print("  （0 条只说明这个作用域没有 CTQ 声明行，不保证作用域本身存在——"
                  "`--project`/`--tenant` 拼错也会读到 0 条）")
        for r in result["records"]:
            # 限值一律原样打：`:g` 会把 8.050001 印成 8.05，而这条面存在的理由就是
            # 回答"限值到底是几"；format(10**400, 'g') 还会 OverflowError——
            # 展示层既不许改数也不许崩（两条都是第 62 片复核时实测出来的）。
            print(f"  {r['record_id']}  {r.get('feature')} @ {r.get('drawing_feature')}  "
                  f"合格域 [{r.get('lower_limit')}, {r.get('upper_limit')}]"
                  f"  标称 {r.get('nominal')}  "
                  f"v{r.get('version')}  {r.get('status')}  信任级 {r.get('trust_level')}"
                  f"  由 {r.get('declared_by')} 声明")
        excluded = result["excluded"]
        if excluded:
            detail = "、".join(f"{k} {v}" for k, v in sorted(excluded.items()))
            print(f"  另有 {sum(excluded.values())} 条未列出（排除：{detail}）"
                  " —— 加 --all 看全部状态")
        if not args.all:
            print("  注：退出发布分母的是**全部**非 active 态，不是只有 superseded——"
                  "superseded 特殊的只有一点：门口对它只出非阻断点名"
                  "（stale/expired/blocked 都算\"今天没收口的要求\"）。"
                  "另一处差别：缺 metadata.feature 的 active 记录这里仍会列出，"
                  "门口判 ctq_missing_feature 阻断")
    _emit(args, payload, prose)
    return 0


_MISSING = object()


def _audit_side(value: Any) -> Any:
    """审计行的 before/after 文本 → dict / None（没写值）/ `_MISSING`（不是合法 JSON）。

    三态分开是规矩：`None` 与"解析不了"在"有没有改动"这件事上含义完全不同，
    压成一件事就会把脏数据读成"那次没改东西"。
    """
    import json

    if value is None or value == "":
        return None
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return _MISSING
    return parsed if isinstance(parsed, dict) else _MISSING


def _audit_diff(before: Any, after: Any) -> list[str]:
    """两份快照 → 「字段: 旧 → 新」。

    借 django.contrib.admin 的形状：`LogEntry.get_change_message()`（`django/django`
    `contrib/admin/models.py`）把结构化 JSON 在**读侧**翻成人话，库里只存结构化那一份。
    本仓比它多一层——存的是 before/after 全量快照，所以能报出**值**（"8.05 → 8.10"），
    而不只是"改了 upper_limit 这个字段"。
    """
    if not isinstance(before, dict) and before is not None:
        return []
    if not isinstance(after, dict) and after is not None:
        return []
    keys = set(before or {}) | set(after or {})
    out: list[str] = []
    for key in sorted(keys):
        if key in _AUDIT_NOISE_KEYS:
            continue
        old, new = (before or {}).get(key), (after or {}).get(key)
        if old != new:
            out.append(f"{key}: {old} → {new}")
    return out


_AUDIT_NOISE_KEYS = ("record_id", "created_at", "updated_at", "timestamp")


def cmd_truth_history(args: Any) -> int:
    """``aipd truth history``：谁在什么时候把哪条事实从什么改成了什么。

    闭的是 registry 与 `ctq.py` 都记过的那笔账：审计行本来就落在 `audit_log`，
    但 `AIPDStateDB.list_audit` 不分作用域且默认 100 条**静默截断**，
    于是"谁把 8.05 改成 8.10"问得出、却要读者自己去按 before/after JSON 筛。

    三条刻意的形状：
    1. 谓词全在 SQL 侧（含 payload 里的 `record_id`）——先截断再筛会把
       "窗口里没有"与"整库没有"压成同一个读数，`total` 就跟着说谎；
    2. `total` / `returned` / `truncated` / `unparseable_rows` 四件事分开报，
       被 `--limit` 切掉的与解析不了的都是**看得见的差额**，不是少掉的行；
    3. 渲染只在读面做，库里仍只存结构化快照；`--json` 给的是未截断的原文
       （prose 每行最多展示 4 处改动并写明"另有 N 处"，payload 不裁）。
    """
    from datetime import datetime, timezone

    from aipd_os.state.db import AIPDStateDB

    db = Path(args.db)
    if not db.is_file():
        print(f"状态库不存在：{db}")
        return 2
    since = None
    if args.since:
        try:
            moment = datetime.fromisoformat(str(args.since).replace("Z", "+00:00"))
        except ValueError as exc:
            print(f"--since 不是合法 ISO 8601 时间：{args.since}（{exc}）")
            return 2
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        since = moment.astimezone(timezone.utc).isoformat()
    try:
        result = AIPDStateDB(str(db)).audit_history(
            tenant_id=args.tenant, project_id=args.project,
            actors=tuple(args.actor or ()), actions=tuple(args.action or ()),
            record_id=args.record, since=since, limit=args.limit)
    except Exception as exc:  # noqa: BLE001 - 读不出来不等于没有历史
        print(f"审计历史读取失败：{type(exc).__name__}: {exc}")
        return 2
    payload = {"command": "truth history", "ok": True, **result}

    def prose() -> None:
        scope = result["scope"]
        print(f"审计历史（tenant={scope['tenant_id']} project={scope['project_id']}，"
              f"作用域内 {result['total']} 条，本次给出 {result['returned']} 条）")
        if result["truncated"]:
            print(f"  ！还有 {result['total'] - result['returned']} 条没给出"
                  f"（是 --limit {result['filters']['limit']} 切的），"
                  "加大它或加过滤条件再看")
        if result["unparseable_rows"]:
            print(f"  ！作用域内有 {result['unparseable_rows']} 条的 before/after "
                  "不是合法 JSON，比不了值——它们算在 total 里，不等于「没有改动」")
        if not result["entries"]:
            print("  0 条 —— 这个作用域里没有审计行"
                  "（--project/--tenant 拼错与真的没有，在这张读数上同形，先核对作用域）")
        for entry in result["entries"]:
            before = _audit_side(entry.get("before_json"))
            after = _audit_side(entry.get("after_json"))
            # 一次 revise 会另起一条记录：改的是 T-001、写出来的是 T-002。只报一个号
            # 就会让人按号去查另一条而查不到，所以两侧不同就两个都报。
            ids = [str(side["record_id"]) for side in (before, after)
                   if isinstance(side, dict) and side.get("record_id")]
            record = " → ".join(dict.fromkeys(ids)) if ids else "-"
            if before is _MISSING or after is _MISSING:
                detail = "（payload 不是合法 JSON，比不了值）"
            elif before is None and after is None:
                detail = "（这一行只记了动作，没有前后值）"
            else:
                changes = _audit_diff(before, after)
                if changes:
                    detail = "；".join(changes[:4])
                    if len(changes) > 4:
                        detail += f"（另有 {len(changes) - 4} 处）"
                else:
                    detail = "（无值变化）"
            print(f"  {entry['timestamp']}  {entry['actor']}  {entry['action']}  "
                  f"record={record}  {detail}")
    _emit(args, payload, prose)
    return 0
