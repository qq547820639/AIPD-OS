"""制造就绪命令（v5.10 NPI）：``aipd bom``（物料清单）与 ``aipd cost``（成本核算）。

- ``aipd bom add``：给最新 BOM 添加一行（层级/数量/材料/供应商/单位成本/关联图纸）；
- ``aipd bom show``：BOM 汇总 + 发布检查清单（开模可用物料清单的确定性验收）；
- ``aipd cost calc``：确定性成本核算（材料小计 + 模具摊销 + NRE + 毛利），
  结果持久化为成本快照并写回 Product Truth（fact key ``cost.total``，status C）。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from aipd_os.cli._helpers import DEFAULT_TENANT, _emit


def _bom_store_path(db_path: str) -> Path:
    from aipd_os.bom.store import bom_store_path

    return bom_store_path(db_path)


def _resolve_project(db: Any, project_id: str | None) -> str:
    if project_id:
        return project_id
    projects = db.list_projects(DEFAULT_TENANT)
    if len(projects) == 1:
        return str(projects[0]["project_id"])
    if not projects:
        raise ValueError("no projects; initialize one first")
    raise ValueError(
        f"multiple projects: {[p['project_id'] for p in projects]}; --project 必填")


def _latest_bom_or_create(store: Any, tenant: str, project: str) -> Any:
    header = store.get_bom(tenant, project)
    if header is not None:
        return header
    return store.create_bom(tenant, project, f"{project} 主物料清单")


def cmd_bom(args: Any) -> int:
    """bom 命令分发（show / add / release）。"""
    if args.bom_cmd == "show":
        return _bom_show(args)
    if args.bom_cmd == "add":
        return _bom_add(args)
    if args.bom_cmd == "release":
        return _bom_release(args)
    raise ValueError(f"unknown bom subcommand: {args.bom_cmd}")


def _cost_inputs(args: Any) -> Any:
    """`bom show` / `bom release` 的成本口径：与 `cost calc` 同一套参数与默认值。

    两个子命令的 parser 都声明了这五个 flag，因此直接取属性；``--amortize-over``
    缺省是 None（= 按目标数量摊销），不是 0。
    """
    from aipd_os.bom import CostInputs

    return CostInputs(
        tooling_fee=float(args.tooling),
        target_quantity=int(args.quantity),
        amortize_over=int(args.amortize_over) if args.amortize_over else None,
        nre=float(args.nre),
        margin_pct=float(args.margin))


def _bom_release(args: Any) -> int:
    """把 BOM 头置为 released——但只在其余检查项已经全过时允许。

    没有这道闸，「发布检查清单」就只是事后统计：release 一个自己就说不清的 BOM
    会让 checklist 的 release_ready 变成一句可以随意勾选的话。
    """
    from aipd_os.bom import BomStore, release_checklist
    from aipd_os.state.db import AIPDStateDB

    db = AIPDStateDB(args.db)
    pid = _resolve_project(db, getattr(args, "project", None))
    store = BomStore(str(_bom_store_path(args.db)))
    header = store.get_bom(DEFAULT_TENANT, pid)
    if header is None:
        result = {"command": "bom release", "ok": False, "status": "HOLD",
                  "project": pid, "reason": "尚无 BOM，无从发布"}
        _emit(args, result, lambda: print(result["reason"]))
        return 4

    checklist = release_checklist(store, DEFAULT_TENANT, pid, bom_id=header.bom_id,
                                  cost_inputs=_cost_inputs(args))
    blocking = [name for name, passed in checklist["checks"].items()
                if not passed and name != "bom_released"]
    if blocking:
        result = {"command": "bom release", "ok": False, "status": "HOLD",
                  "project": pid, "bom_id": header.bom_id,
                  "blocking_checks": sorted(blocking), "checklist": checklist,
                  "reason": "发布检查清单未过，拒绝置为 released"}
        _emit(args, result,
              lambda: print("拒绝发布，未过项：" + ", ".join(sorted(blocking)))
              )
        return 4

    updated = store.set_bom_status(DEFAULT_TENANT, pid, header.bom_id, "released",
                                   expected_version=header.version_no)
    result = {"command": "bom release", "ok": True, "status": "DONE",
              "project": pid, "bom_id": updated.bom_id,
              "bom_status": updated.status, "version_no": updated.version_no,
              "reason": getattr(args, "reason", "") or "release"}
    _emit(args, result,
          lambda: print(f"BOM {updated.bom_id} 已置为 {updated.status}"
                        f"（version {updated.version_no}）"))
    return 0


def _bom_show(args: Any) -> int:
    from aipd_os.bom import BomStore, release_checklist, rollup
    from aipd_os.state.db import AIPDStateDB

    db = AIPDStateDB(args.db)
    pid = _resolve_project(db, getattr(args, "project", None))
    store = BomStore(str(_bom_store_path(args.db)))
    header = store.get_bom(DEFAULT_TENANT, pid)
    result: dict[str, Any] = {
        "command": "bom show", "ok": True, "project": pid,
        "bom": header.to_dict() if header else None,
        "rollup": rollup(store, DEFAULT_TENANT, pid),
        # 不传 cost_inputs 时 cost_calculated 永远是 False（F-BOM-01：这个清单在产品
        # 路径上根本不可能满足）。这里显式带上核算口径，并把口径 itself 打进结果里。
        "checklist": release_checklist(store, DEFAULT_TENANT, pid,
                                       cost_inputs=_cost_inputs(args)),
        "cost_inputs": _cost_inputs(args).__dict__,
    }

    def prose():
        if header is None:
            print("尚无 BOM（可用 `aipd bom add` 添加第一行）")
            return
        r = result["rollup"]
        print(f"BOM：{header.name}（{header.bom_id}，rev {header.revision}，"
              f"状态 {header.status}）")
        print(f"  行数：{r['line_count']}；根件：{', '.join(r['root_items']) or '无'}")
        if r["suppliers"]:
            print("  供应商分布：" + "，".join(
                f"{s}×{n}" for s, n in sorted(r["suppliers"].items())))
        if r["missing_cost_items"]:
            print("  缺成本/供应商的行：" + "，".join(r["missing_cost_items"]))
        if r["orphan_parents"]:
            print("  孤儿父项引用：" + "，".join(r["orphan_parents"]))
        c = result["checklist"]["checks"]
        flags = " ".join(
            ("✓" if ok else "✗") + name
            for name, ok in c.items())
        print(f"  发布检查：{flags}")
        print(f"  开模可用物料清单就绪：{'是' if result['checklist']['release_ready'] else '否'}")
    _emit(args, result, prose)
    return 0


def _bom_add(args: Any) -> int:
    from aipd_os.bom import BomLine, BomStore
    from aipd_os.state.db import AIPDStateDB

    db = AIPDStateDB(args.db)
    pid = _resolve_project(db, getattr(args, "project", None))
    store = BomStore(str(_bom_store_path(args.db)))
    header = _latest_bom_or_create(store, DEFAULT_TENANT, pid)
    line = BomLine(
        line_id="", bom_id=header.bom_id, tenant_id=DEFAULT_TENANT,
        project_id=pid, item=args.part, parent_item=args.parent,
        description=args.description or "", quantity=float(args.quantity),
        unit=args.unit, material=args.material,
        process=getattr(args, "process", None), supplier=args.supplier,
        unit_cost=float(args.unit_cost) if args.unit_cost is not None else None,
        currency=args.currency, source_deliverable=args.deliverable,
        quote_ref=args.quote_ref, status=args.status)
    line = store.add_line(line)
    result = {"command": "bom add", "ok": True, "line": line.to_dict()}

    def prose():
        print(f"已添加 BOM 行：{line.item}（{line.line_id}，数量 {line.quantity}"
              f"{line.unit}，材料 {line.material or '未填'}，"
              f"工艺 {line.process or '未填'}，"
              f"供应商 {line.supplier or '未填'}，"
              f"单位成本 {line.unit_cost if line.unit_cost is not None else '未填'}）")
    _emit(args, result, prose)
    return 0


def read_current_bom(db_path: str, project_id: str | None) -> dict[str, Any]:
    """读**项目当前那份 BOM** 的 header 与行；不写任何东西。

    `calc_current_cost` 与两条返工执行器（成本、BOM 版本）共用这一份「怎么取行」：
    各留一份迟早会与实现漂移（第 47/52 片同一条纪律）。
    """
    from aipd_os.bom import BomStore
    from aipd_os.state.db import AIPDStateDB

    db = AIPDStateDB(db_path)
    pid = _resolve_project(db, project_id)
    store = BomStore(str(_bom_store_path(db_path)))
    header = store.get_bom(DEFAULT_TENANT, pid)
    lines = store.list_lines(DEFAULT_TENANT, pid,
                             bom_id=header.bom_id if header else None)
    return {"project": pid, "header": header, "lines": lines}


def calc_current_cost(db_path: str, project_id: str | None, *, tooling_fee: Any,
                      target_quantity: Any, amortize_over: Any, nre: Any,
                      margin_pct: Any) -> dict[str, Any]:
    """按给定口径读**项目当前那份 BOM** 算一次成本；不写任何事实。

    `cmd_cost` 与返工执行器共用这一个入口：两边各留一份「怎么取行、怎么装 CostInputs」
    迟早会与实现漂移（第 47 片对出图走的是同一条纪律）。
    """
    from aipd_os.bom import CostInputs, compute_bom_cost

    out = read_current_bom(db_path, project_id)
    header, lines = out["header"], out["lines"]
    inputs = CostInputs(
        tooling_fee=float(tooling_fee), target_quantity=int(target_quantity),
        amortize_over=int(amortize_over) if amortize_over else None,
        nre=float(nre), margin_pct=float(margin_pct))
    return {"project": out["project"], "header": header, "lines": lines,
            "inputs": inputs, "cost": compute_bom_cost(lines, inputs)}


def bom_from_record(meta: dict[str, Any], *, db_path: str,
                    project_id: str | None) -> dict[str, Any]:
    """BOM 版本记录的重算器：只读当前 BOM 表，回报判定与投影所需字段。

    刻意**不**走 `cost calc --truth-lineage`：那条路会另起新版本并把旧版标 superseded，
    而引擎要的是「演进这一条」（同 `recalc_cost_from_record` 的理由）。
    """
    from aipd_os.bom.cost_lineage import bom_input_signature

    out = read_current_bom(db_path, project_id)
    header, lines = out["header"], out["lines"]
    if header is None:
        raise ValueError(f"项目 {out['project']} 当前没有 BOM 头，"
                         "重建不出这条记录描述的那张 BOM")
    return {"bom_id": str(header.bom_id),
            "bom_signature": bom_input_signature(
                bom_id=header.bom_id, revision=str(header.revision),
                version_no=header.version_no, lines=lines),
            "revision": str(header.revision), "version_no": header.version_no,
            "line_count": len(lines), "header": header, "lines": lines}


def recalc_cost_from_record(meta: dict[str, Any], *, db_path: str,
                            project_id: str | None) -> dict[str, Any]:
    """返工执行器的重算器：按记录里那份口径对**当前** BOM 再算一遍，回报判定所需字段。

    刻意**不**走 `cmd_cost` 的 `--truth-lineage` 分支：那条路在 BOM 真的动了时会另起
    一对新版本并标旧版 superseded，而引擎要的是「演进这一条」。
    """
    from aipd_os.bom.cost_lineage import bom_input_signature, cost_input_signature

    out = calc_current_cost(
        db_path, project_id,
        tooling_fee=meta.get("tooling_fee"),
        target_quantity=meta.get("target_quantity"),
        amortize_over=meta.get("amortize_over"),
        nre=meta.get("nre"), margin_pct=meta.get("margin_pct"))
    header, lines, inputs, cost = (out["header"], out["lines"], out["inputs"],
                                   out["cost"])
    if header is None or not lines:
        raise ValueError(f"BOM 读不到行（project={out['project']}）："
                         "空 BOM 上没有可重算的成本结论")
    cd = cost.to_dict() or {}
    bom_sig = bom_input_signature(bom_id=header.bom_id,
                                  revision=str(header.revision),
                                  version_no=header.version_no, lines=lines)
    cost_sig = cost_input_signature(
        bom_signature=bom_sig, tooling_fee=inputs.tooling_fee,
        target_quantity=inputs.target_quantity, amortize_over=inputs.amortize_over,
        nre=inputs.nre, margin_pct=inputs.margin_pct)
    return {"bom_id": str(header.bom_id), "bom_signature": bom_sig,
            "cost_signature": cost_sig, "total_cost": cd.get("total_cost"),
            "currency": cd.get("currency"),
            "cost_complete": bool(getattr(cost, "cost_complete", False))}


def cmd_cost(args: Any) -> int:
    """cost 命令分发（calc）。"""
    if args.cost_cmd != "calc":
        raise ValueError(f"unknown cost subcommand: {args.cost_cmd}")
    from aipd_os.state.db import AIPDStateDB

    db = AIPDStateDB(args.db)
    pid = _resolve_project(db, getattr(args, "project", None))
    calculated = calc_current_cost(
        args.db, pid, tooling_fee=args.tooling, target_quantity=args.quantity,
        amortize_over=args.amortize_over, nre=args.nre, margin_pct=args.margin)
    header, lines, inputs, cost = (calculated["header"], calculated["lines"],
                                   calculated["inputs"], calculated["cost"])

    # 血缘：opt-in。给了 --truth-lineage 才登记「BOM 版本 → 成本结论」；
    # 没给是**明说的跳过**，写不进去则判未收口（图纸那一跳同一条纪律）。
    lineage = None
    lineage_error = None
    lineage_skip_reason = None
    if getattr(args, "truth_lineage", False):
        from aipd_os.bom.cost_lineage import record_cost_lineage
        from aipd_os.product_truth import ProductTruthStore

        try:
            truth = ProductTruthStore(args.db, tenant_id=DEFAULT_TENANT,
                                      project_id=pid)
            lineage = record_cost_lineage(
                truth, header=header, lines=lines, inputs=inputs, cost=cost,
                tenant_id=DEFAULT_TENANT, project_id=pid)
        except Exception as exc:  # noqa: BLE001 - 下面判未收口，不静默
            lineage_error = f"{type(exc).__name__}: {exc}"
    else:
        lineage_skip_reason = "未给 --truth-lineage ⇒ 不登记「BOM → 成本」血缘"
    # 写回 Product Truth（status C=Calculation，来源可追溯）
    fact_id = None
    if header is not None and lines:
        fact_id = db.add_fact(
            DEFAULT_TENANT, pid, "cost.total",
            cost.to_dict(), "C", source="bom-cost",
            conditions=f"bom={header.bom_id} qty={inputs.target_quantity} "
                       f"tooling={inputs.tooling_fee} nre={inputs.nre} "
                       f"margin={inputs.margin_pct}%")
    result = {"command": "cost calc", "ok": True, "project": pid,
              "bom_id": header.bom_id if header else None,
              "inputs": {
                  "tooling_fee": inputs.tooling_fee,
                  "target_quantity": inputs.target_quantity,
                  "amortize_over": inputs.amortize_quantity(),
                  "nre": inputs.nre, "margin_pct": inputs.margin_pct,
              },
              "cost": cost.to_dict(), "fact_id": fact_id,
              "lineage": lineage, "lineage_error": lineage_error,
              "lineage_skipped": lineage_skip_reason}
    if lineage_error:
        result["ok"] = False

    def prose():
        if not lines:
            print("BOM 为空，先 `aipd bom add` 添加行")
            return
        d = result["cost"]
        print(f"BOM {result['bom_id']} 成本核算（目标 {inputs.target_quantity} 件）：")
        print(f"  材料小计：{d['material_subtotal']}；模具费：{d['tooling_fee']}"
              f"（单件摊销 {d['tooling_per_unit']}）；NRE：{d['nre']}")
        print(f"  单件成本：{d['unit_cost']}；单件售价（含 {inputs.margin_pct}% 毛利）："
              f"{d['unit_price']}")
        print(f"  总成本：{d['total_cost']}；总售价：{d['total_price']}")
        if not d["cost_complete"]:
            print("  成本不完整（以下行缺供应商/单位成本，未计入）：" +
                  "，".join(d["missing_cost_lines"]))
        print(f"  已写回 Product Truth（fact {fact_id}，status C）")
        if lineage is not None:
            if lineage.get("written"):
                print(f"  血缘：BOM 版本 {lineage['bom']['record_id']} → 成本结论 "
                      f"{lineage['cost']['record_id']}（边 {lineage['edges']} 条，"
                      f"签名 {lineage['cost_signature'][:16]}"
                      f"{'，新建' if lineage['cost']['created'] else '，同输入命中已有记录'}）")
            else:
                print(f"  血缘：未登记（{lineage['reason']}）")
        elif lineage_error:
            print(f"  血缘未落库：{lineage_error}（结论已算出，但传播到不了它 ⇒ 判未收口）")
        else:
            print(f"  血缘：{lineage_skip_reason}")
    _emit(args, result, prose)
    return 4 if lineage_error else 0


__all__ = ["cmd_bom", "cmd_cost"]
