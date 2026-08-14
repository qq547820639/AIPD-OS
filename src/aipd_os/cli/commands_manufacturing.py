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
    return Path(db_path).parent / "bom.db"


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
    """bom 命令分发（show / add）。"""
    if args.bom_cmd == "show":
        return _bom_show(args)
    if args.bom_cmd == "add":
        return _bom_add(args)
    raise ValueError(f"unknown bom subcommand: {args.bom_cmd}")


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
        "checklist": release_checklist(store, DEFAULT_TENANT, pid),
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
        unit=args.unit, material=args.material, supplier=args.supplier,
        unit_cost=float(args.unit_cost) if args.unit_cost is not None else None,
        currency=args.currency, source_deliverable=args.deliverable,
        quote_ref=args.quote_ref, status=args.status)
    line = store.add_line(line)
    result = {"command": "bom add", "ok": True, "line": line.to_dict()}

    def prose():
        print(f"已添加 BOM 行：{line.item}（{line.line_id}，数量 {line.quantity}"
              f"{line.unit}，供应商 {line.supplier or '未填'}，"
              f"单位成本 {line.unit_cost if line.unit_cost is not None else '未填'}）")
    _emit(args, result, prose)
    return 0


def cmd_cost(args: Any) -> int:
    """cost 命令分发（calc）。"""
    if args.cost_cmd != "calc":
        raise ValueError(f"unknown cost subcommand: {args.cost_cmd}")
    from aipd_os.bom import BomStore, CostInputs, compute_bom_cost
    from aipd_os.state.db import AIPDStateDB

    db = AIPDStateDB(args.db)
    pid = _resolve_project(db, getattr(args, "project", None))
    store = BomStore(str(_bom_store_path(args.db)))
    header = store.get_bom(DEFAULT_TENANT, pid)
    lines = store.list_lines(DEFAULT_TENANT, pid,
                             bom_id=header.bom_id if header else None)
    inputs = CostInputs(
        tooling_fee=float(args.tooling), target_quantity=int(args.quantity),
        amortize_over=int(args.amortize_over) if args.amortize_over else None,
        nre=float(args.nre), margin_pct=float(args.margin))
    cost = compute_bom_cost(lines, inputs)
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
              "cost": cost.to_dict(), "fact_id": fact_id}

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
    _emit(args, result, prose)
    return 0


__all__ = ["cmd_bom", "cmd_cost"]
