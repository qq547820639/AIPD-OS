"""CAD 门禁与工业化/验证相关命令。

- ``aipd cad preflight`` / ``aipd cad build``：CAD 成熟度门禁；
- ``aipd industrialize``：供应链 + 验证执行（端到端，绝不虚构）；
- ``aipd validate``：生产发布证据门禁。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aipd_os.cli._helpers import (
    DEFAULT_TENANT,
    _cad_gate_summary,
    _emit,
    _import_module,
    _run_script_main,
)


# ---- cad preflight：运行时上限与成熟度约束检查 ----
def cmd_cad_preflight(args):
    cmg = _import_module("cad_maturity_gate")
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    s = _cad_gate_summary(cmg, manifest, args.target)
    result = {"command": "cad preflight", "ok": True, **s}
    result["passed"] = s["runtime_ceiling"] and cmg.idx(s["runtime_ceiling"]) >= cmg.idx(args.target)  # noqa: E501

    def prose():
        print(f"运行时：{s['runtime']}；上限 {s['runtime_ceiling']}；目标 {args.target}。")
        print(f"运行时上限允许目标：{'是' if result['passed'] else '否'}")
        if s["faceted_brep_capped"]:
            print("faceted_brep 运行时成熟度封顶于 C1。")
    _emit(args, result, prose)
    return 0 if result["passed"] else 4


# ---- cad build：运行 CAD 成熟度门禁（映射 run-cad-chain）----
def cmd_cad_build(args):
    cmg = _import_module("cad_maturity_gate")
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    s = _cad_gate_summary(cmg, manifest, args.target)
    result = {"command": "cad build", "ok": s["target_passed"], **s}

    def prose():
        print(f"CAD 成熟度：达到 {s['reached_level']}（运行时上限 {s['runtime_ceiling']}）")
        if s["faceted_brep_capped"]:
            print("faceted_brep 运行时成熟度封顶于 C1。")
        print(f"目标 {args.target} 通过：{'是' if s['target_passed'] else '否'}")
    _emit(args, result, prose)
    return 0 if s["target_passed"] else 4


# ---- industrialize：供应链 + 验证执行（端到端，绝不虚构）----
def cmd_industrialize(args):
    from aipd_os.supply_chain.analysis import analyze_stage, create_correction_tasks
    from aipd_os.supply_chain.lab import import_lab_csv
    from aipd_os.supply_chain.quotes import QuoteRegistry, parse_quote_file
    from aipd_os.supply_chain.stages import VALID_STAGES

    official_quotes = []
    quotes_note = None
    if args.quote:
        parsed = parse_quote_file(args.quote)
        registry = QuoteRegistry()
        for rec in parsed["records"]:
            q = registry.add_quote(supplier=rec["supplier"], part=rec["part"], data=rec,
                                   source_file=str(parsed.get("source", "")))
            official_quotes.append({
                "supplier": q.supplier, "part": q.part, "quote_id": q.quote_id,
                "unit_price": q.data["unit_price"], "status": q.status,
            })
        # 注册表是命令内的临时对象：这条路径只归一化、不落库也不改 BOM 的价。
        # 不说清就会被读成"报价已入账"（F-SUPPLY-01 的同一种误读）。
        quotes_note = (
            f"以上 {len(official_quotes)} 条报价仅完成解析与版本登记（临时注册表，"
            "本次运行结束即丢弃）：未写入 Product Truth，也未改 BOM 单价。"
            "要让报价成为成本，请用 aipd quote apply --db <state.db> --file <报价文件>")
    else:
        quotes_note = "未收到报价数据，未登记任何官方报价（不发散、不虚构）。"

    analysis = None
    lab_note = None
    correction_tasks = []
    if args.lab_data:
        stage = (args.stage or "validation").strip().lower()
        if stage != "validation" and stage not in VALID_STAGES:
            raise ValueError(
                f"无效 --stage {stage!r}；合法值: evt / dvt / pvt（缺省 validation）")
        lab = import_lab_csv(args.lab_data, stage)
        analysis = analyze_stage(lab["records"], stage)
        correction_tasks = create_correction_tasks(analysis, stage)
        pass_flag = analysis["total"] > 0 and analysis["failed"] == 0
        analysis = {"stage": stage, "total": analysis["total"],
                    "passed": analysis["passed"], "failed": analysis["failed"],
                    "items": analysis["items"],
                    "failing_items": analysis["failing_items"],
                    "pass_flag": pass_flag}
    else:
        lab_note = "未收到实验室数据，未执行阶段分析（不虚构）。"

    # 影响传播（F-SUPPLY-03）：只有拿得到状态库才可能真的落到制品上，
    # 否则如实报告"没传播"，不再让登记表那句 BOM/CAD 影响传播自证成立。
    impact: dict[str, Any] | None = None
    impact_note = None
    if analysis and args.lab_data:
        failing = analysis["failing_items"]
        if not getattr(args, "db", None):
            impact_note = ("未提供 --db：无法定位 BOM 与制品，本次未执行影响传播"
                           "（不落任何 stale 标记，也不写 impact 事实）。")
        else:
            from aipd_os.bom import BomStore
            from aipd_os.state.db import AIPDStateDB
            from aipd_os.supply_chain.impact import propagate_lab_impact

            from .commands_manufacturing import _bom_store_path, _resolve_project

            db_state = AIPDStateDB(args.db)
            pid = _resolve_project(db_state, getattr(args, "project", None))
            report = propagate_lab_impact(
                db_state, BomStore(str(_bom_store_path(args.db))),
                DEFAULT_TENANT, pid, failing, source=f"industrialize:{analysis['stage']}")
            impact = report.to_dict()

    stage_failed = bool(analysis) and not analysis["pass_flag"]
    impact_unclean = bool(impact) and not impact["clean"]
    result = {"command": "industrialize",
              "ok": not stage_failed and not impact_unclean,
              "official_quotes": official_quotes, "quotes_note": quotes_note,
              "analysis": analysis, "lab_note": lab_note,
              "impact": impact, "impact_note": impact_note,
              "correction_tasks": correction_tasks}

    def prose():
        print(f"官方报价：{len(official_quotes)} 条")
        for q in official_quotes:
            print(f"  · {q['supplier']}/{q['part']} {q['quote_id']} 单价 {q['unit_price']}")
        if quotes_note:
            print(quotes_note)
        if lab_note:
            print(lab_note)
        if analysis:
            print(f"阶段分析：共 {analysis['total']} 项，通过 {analysis['passed']}，失败 {analysis['failed']}"  # noqa: E501
                  f"；阶段通过：{'是' if analysis['pass_flag'] else '否'}")
            print(f"纠偏任务：{len(correction_tasks)} 个")
            for t in correction_tasks:
                print(f"  · {t['work_id']} {t['test_item']} -> {t['action']}")
        if impact_note:
            print(impact_note)
        if impact:
            print(f"影响传播：受影响 BOM 行 {len(impact['affected_lines'])}，"
                  f"已置 stale 的制品 {len(impact['stale_deliverables'])}，"
                  f"关联不到制品的行 {len(impact['unresolved_lines'])}"
                  f"（结论事实 {len(impact['fact_keys'])} 条）")
            for k in impact["fact_keys"]:
                print(f"  · {k}")
    _emit(args, result, prose)
    return 4 if (stage_failed or impact_unclean) else 0


# ---- validate：生产发布证据门禁（映射 production_release_gate）----
def cmd_validate(args):
    prg = _import_module("production_release_gate")
    rc, out = _run_script_main(prg, ["--manifest", args.manifest, "--target", args.target])
    try:
        gate = json.loads(out)
    except Exception:
        gate = {"passed": rc == 0}
    result = {"command": "validate", "ok": rc == 0, "target": args.target,
              "manifest": args.manifest, "passed": gate.get("passed", rc == 0),
              "gate": gate}
    _emit(args, result, lambda: print(out.rstrip()))
    return rc
