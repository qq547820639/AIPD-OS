"""CAD 门禁与工业化/验证相关命令。

- ``aipd cad preflight`` / ``aipd cad build``：CAD 成熟度门禁；
- ``aipd industrialize``：供应链 + 验证执行（端到端，绝不虚构）；
- ``aipd validate``：生产发布证据门禁。
"""

from __future__ import annotations

import json
from pathlib import Path

from aipd_os.cli._helpers import (
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
    else:
        quotes_note = "未收到报价数据，未登记任何官方报价（不发散、不虚构）。"

    analysis = None
    correction_tasks = []
    lab_note = None
    if args.lab_data:
        stage = args.stage or "validation"
        lab = import_lab_csv(args.lab_data, stage)
        analysis = analyze_stage(lab["records"], stage)
        correction_tasks = create_correction_tasks(analysis, stage)
        pass_flag = analysis["total"] > 0 and analysis["failed"] == 0
        analysis = {"stage": stage, "total": analysis["total"],
                    "passed": analysis["passed"], "failed": analysis["failed"],
                    "items": analysis["items"], "pass_flag": pass_flag}
    else:
        lab_note = "未收到实验室数据，未执行阶段分析（不虚构）。"

    result = {"command": "industrialize", "ok": True,
              "official_quotes": official_quotes, "quotes_note": quotes_note,
              "analysis": analysis, "lab_note": lab_note,
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
    _emit(args, result, prose)
    return 0


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
