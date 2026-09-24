#!/usr/bin/env python3
"""C6 生产图纸包交付物**覆盖度普查**（诊断档，不进发布门禁）。

分母不是抄来的：逐字从 `references/production-cad-deliverables.md` 里那一行
「C6生产图纸包至少包括：…」现算。改了契约文件里的清单，这张表必须跟着红——
否则普查会悄悄停在旧口径上。

每一项三档读数：

- ``producer``  有生产者**且**有常驻用例：映射里至少一个 `src/` 下的实现文件 +
  至少一个测试文件，而且那个测试文件里真的数得出 `def test_`。
- ``checker_only``  只有校验方/声明，没有产品侧生产者：例如 `implementation_file`
  只指向 `scripts/production_release_gate.py`（那是判据不是生产者），或只指向模板。
  「手写一份 JSON 让门过去」就落在这一档——它不等于交付物存在。
- ``absent``  零实现：映射里既没有实现也没有用例。

`--self-test` 会注入四种坏读数并**要求每一条都红**（判据不在自己手里时，
先证明尺子能红再信它的绿）。退出码：0 一致，4 判未收口（口径漂移/映射自相矛盾）。
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import re
import sys
from pathlib import Path
from typing import Any

REFERENCE = "references/production-cad-deliverables.md"
LINE_PREFIX = "C6生产图纸包至少包括："

# 每一项：能力行 id + 产品侧生产者 + 常驻用例 + 判读与理由。
# 这个表是**人下的判断**，本脚本的活是把判断里可核的部分钉住：
# 路径真在吗、测试文件里真有 test 吗、能力行真存在吗、档位与所列文件自相矛盾吗。
MAPPING: dict[str, dict[str, Any]] = {
    "参数化源模型": {
        "verdict": "producer", "capabilities": ["cad.parametric_model", "cad.local_native_brep"],
        "producers": ["src/aipd_os/cad/backends.py",
                      "src/aipd_os/tool_adapters/local_brep_adapter.py"],
        "tests": ["tests/test_cad_golden_loop.py", "tests/test_adapters.py"],
        "note": "CadQuery 参数化脚本真跑（golden bracket 的孔位就是它算出来的），不是黑盒模型。"},
    "总装/单件STEP": {
        "verdict": "producer", "capabilities": ["cad.local_native_brep", "cad.2d_drawings"],
        "producers": ["src/aipd_os/cad/backends.py", "src/aipd_os/cad/assembly.py"],
        "tests": ["tests/test_cad_golden_loop.py", "tests/test_cad_assembly_balloons.py"],
        "note": "单件 STEP 有导出点（backends.py exportType='STEP'）；**装配级 STEP 未导出**——"
                "assembly.py 只按 manifest 逐件 importStep 再投影，不产总装 STEP 文件。"},
    "总装图": {
        "verdict": "producer", "capabilities": ["cad.2d_drawings"],
        "producers": ["src/aipd_os/cad/assembly.py", "src/aipd_os/cad/drawings2d.py"],
        "tests": ["tests/test_cad_assembly_balloons.py", "tests/test_cad_assembly_bom_link.py"],
        "note": "逐件投影 + 球标 + 六列明细表；爆炸图与装配约束不在其中。"},
    "零件图": {
        "verdict": "producer", "capabilities": ["cad.2d_drawings"],
        "producers": ["src/aipd_os/cad/drawings2d.py"],
        "tests": ["tests/test_cad_drawings2d.py", "tests/test_cad_section_views.py",
                  "tests/test_cad_detail_views.py"],
        "note": "正投影 + 剖视 + 局部放大 + 尺寸/公差/GD&T 框 + 标题栏。"},
    "爆炸图": {
        "verdict": "producer", "capabilities": ["cad.2d_drawings"],
        "producers": ["src/aipd_os/cad/assembly.py", "src/aipd_os/cad/drawings2d.py"],
        "tests": ["tests/test_cad_assembly_explode.py", "tests/test_release_manifest.py"],
        "note": "位移**由作者声明**（manifest 的 explode，每件一条装配位→爆炸位连接线），"
                "不自动求拆卸方向——那要装配约束与无碰撞路径两样前提，本仓都没有；"
                "缺声明直接拒绝出图。sidecar 被手改出「说爆炸却没连线」的形状由 "
                "release manifest 的 explode_unconnected 判阻断。"},
    "BOM": {
        "verdict": "producer", "capabilities": ["industrialize.bom_model_cost",
                                                "industrialize.quote_to_bom_cost",
                                                "cad.bom_consistency"],
        "producers": ["src/aipd_os/bom/models.py", "src/aipd_os/bom/store.py",
                      "src/aipd_os/bom/cost.py", "src/aipd_os/bom/projection.py"],
        "tests": ["tests/test_bom.py", "tests/test_quote_to_cost_chain.py"],
        "note": "独立库 bom.db；乐观锁 + 审计 + 成本 + 发布检查清单。"},
    "ICD": {
        "verdict": "absent", "capabilities": [], "producers": [], "tests": [],
        "note": "接口控制文档：src/tests/scripts 三处按词边界查 `ICD` 全为 0 命中，"
                "能力表里也没有任何一行提到它。"},
    "尺寸链": {
        "verdict": "producer", "capabilities": ["cad.tolerance_chain"],
        "producers": ["src/aipd_os/cad/stackup.py", "src/aipd_os/cad/drawings2d.py"],
        "tests": ["tests/test_cad_stackup.py", "tests/test_cad_drawings_chain_tolerance.py"],
        "note": "一维叠加（各段公差带之和 vs 封闭环）已真做；三维/角度叠加与统计分布（Cpk）未做。"
                "另注：`cad.tolerance_chain` 这行的 implementation_file 只写了门禁脚本，"
                "真正的生产者 `cad/stackup.py` 没被那行点名（见诊断里的未声明清单）。"},
    "GD&T": {
        "verdict": "producer", "capabilities": ["cad.gdt"],
        "producers": ["src/aipd_os/cad/gdt.py", "src/aipd_os/cad/drawings2d.py"],
        "tests": ["tests/test_cad_gdt_frames.py", "tests/test_cad_gdt_deviation.py"],
        "note": "特征控制框可绘制可回读，位置度偏差按投影实测数值核对；"
                "用的是 drawn 几何而不是 DXF TOLERANCE 语义实体，且形位偏差本仓不测。"},
    "材料与工艺": {
        "verdict": "producer", "capabilities": ["industrialize.bom_model_cost",
                                                "cad.2d_drawings",
                                                "industrialize.release_evidence"],
        "producers": ["src/aipd_os/bom/models.py", "src/aipd_os/cad/assembly.py",
                      "src/aipd_os/release_manifest.py"],
        "tests": ["tests/test_bom.py", "tests/test_cad_assembly_bom_link.py",
                  "tests/test_release_manifest.py"],
        "note": "两半各自取值、各自点名（material_missing / process_missing）。"
                "**工艺只有一格**：多工序路线（顺序/工时/工序成本）未建模。"},
    "DFM/DFA": {
        "verdict": "checker_only", "capabilities": ["cad.dfm_dfa"],
        "producers": [], "tests": ["tests/test_production_release_gate.py"],
        "note": "该行 implementation_file 只有模板 + 门禁脚本：门会判「声明了什么」，"
                "但产品侧没有 DFM/DFA 分析的生产者。"},
    "装配/维护": {
        "verdict": "absent", "capabilities": ["cad.assembly_constraints"],
        "producers": [], "tests": [],
        "note": "装配说明与维护指引都没有落点。顺带暴露：`cad.assembly_constraints` 这一行"
                "implementation_file 与 unit_test **两栏皆空**——一行不可核验的声明。"},
    "CTQ与检验": {
        "verdict": "producer", "capabilities": ["cad.inspection_plan",
                                                "industrialize.release_evidence"],
        "producers": ["src/aipd_os/release_manifest.py", "src/aipd_os/cad/spec_from_truth.py"],
        "tests": ["tests/test_release_manifest.py", "tests/test_cad_spec_from_truth.py"],
        "note": "CTQ 取 Product Truth、检验方法随 CTQ 的 inspection_method 走，"
                "gdt 覆盖只从图纸证据长出来（不手抄）。独立的检验计划文档未做。"},
    "验证证据": {
        "verdict": "producer", "capabilities": ["industrialize.release_evidence",
                                                "cad.production_release_gate"],
        "producers": ["src/aipd_os/release_manifest.py", "scripts/release_evidence.py"],
        "tests": ["tests/test_release_manifest.py", "tests/test_packaging.py"],
        "note": "SOURCE_MANIFEST / RELEASE_MANIFEST / PROVENANCE 三份带哈希与 source_commit，"
                "门禁真读它们。"},
    "版本与ECR/ECO": {
        "verdict": "checker_only", "capabilities": ["ux.checkpoint",
                                                    "industrialize.release_evidence"],
        "producers": [], "tests": ["tests/test_backup_checkpoint.py",
                                   "tests/test_production_release_gate.py"],
        "note": "版本这一半有生产者（三源哈希 + 不一致只如实记录不对齐）；"
                "**ECR/ECO 变更单零实现**：本仓有 changes/decisions 表但没有工程变更单实体。"
                "注意此前 grep `ECO`/`ECR` 命中上百文件全是子串噪声"
                "（SECONDS/SECRET 之类），按词边界重查才是 0——计数必须由判据现算。"},
}


@dataclasses.dataclass
class Problem:
    item: str
    kind: str
    detail: str


def c6_items(reference: Path) -> list[str]:
    """从契约文件现算分母；找不到那一行就抛错（宁可不读，不猜）。"""
    text = reference.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith(LINE_PREFIX):
            body = line[len(LINE_PREFIX):].rstrip("。").strip()
            return [p.strip() for p in body.split("、") if p.strip()]
    raise ValueError(f"{reference} 里找不到以 {LINE_PREFIX!r} 开头的行：分母无法现算")


def _test_count(path: Path) -> int:
    if not path.is_file():
        return -1
    return len(re.findall(r"^\s*def test_", path.read_text("utf-8", "replace"), re.M))


def audit(root: Path) -> dict[str, Any]:
    """跑一遍普查；返回逐项读数与全部一致性问题。"""
    items = c6_items(root / REFERENCE)
    try:
        from aipd_os.registry_data import CAPABILITIES
        registry_rows = list(CAPABILITIES)
        known = {c["id"] for c in registry_rows}
    except Exception as exc:                              # 能力表读不到 ⇒ 整轮不可判
        registry_rows, known = [], set()
        registry_error = f"{type(exc).__name__}: {exc}"
    else:
        registry_error = None

    problems: list[Problem] = []
    rows: list[dict[str, Any]] = []

    for item in items:
        entry = MAPPING.get(item)
        if entry is None:
            problems.append(Problem(item, "unmapped",
                                    "契约里有这一项，但普查映射没有它——分母漂移"))
            continue
        caps = list(entry["capabilities"])
        producers = list(entry["producers"])
        tests = list(entry["tests"])
        verdict = entry["verdict"]

        for cap in caps:
            if cap not in known:
                problems.append(Problem(item, "unknown_capability",
                                        f"{cap} 不在能力表里（改名或删行了，映射还指着它）"))
        for path in producers:
            if not (root / path).is_file():
                problems.append(Problem(item, "producer_missing", f"{path} 不存在"))
        counts = {}
        for path in tests:
            n = _test_count(root / path)
            if n < 0:
                problems.append(Problem(item, "test_missing", f"{path} 不存在"))
            elif n == 0:
                problems.append(Problem(item, "test_empty",
                                        f"{path} 里一个 test 都没有（用例被清空或改名了）"))
            counts[path] = n
        under_src = [p for p in producers if p.startswith("src/")]
        if verdict == "producer" and (not under_src or not tests):
            problems.append(Problem(item, "verdict_inconsistent",
                                    "标了 producer 但没列出 src 下的生产者或没有常驻用例"))
        if verdict == "checker_only" and under_src:
            problems.append(Problem(item, "verdict_inconsistent",
                                    "标了 checker_only 却列出了 src/ 下的生产者："
                                    "有产品侧落点就不该报成只有校验方"))
        if verdict == "absent" and (producers or tests):
            problems.append(Problem(item, "verdict_inconsistent",
                                    "标了 absent 却列出了文件或用例"))
        rows.append({"item": item, "verdict": verdict, "capabilities": caps,
                     "producers": producers, "tests": counts, "note": entry["note"]})

    for extra in sorted(set(MAPPING) - set(items)):
        problems.append(Problem(extra, "stale_mapping",
                                "映射里有这一项，但契约文件已经不再要求它——请删掉这条映射"))

    declared: set[str] = set()
    empty_rows: list[str] = []
    # 注意别把这里的行变量也叫 caps/cap：本函数上面已用 caps 装每一项的能力行名，
    # 同名会在这里静默拿到一串字符串（踩过一次，AttributeError 才露出来）。
    for row_cap in registry_rows:
        raw = str(row_cap.get("implementation_file") or "")
        files = [f.strip() for f in raw.split(";") if f.strip()]
        declared.update(f for f in files if "{" not in f)
        if not files and not str(row_cap.get("unit_test") or "").strip():
            empty_rows.append(row_cap["id"])
    # 「没被任何能力行的 implementation_file 点名」是精确判据，不含推断：
    # 没点名不等于没被测（很多模块是被同域别的行的用例顺带跑到的），
    # 但它等于「顺着能力表找不到这个文件」——声明完整度的信号。
    undeclared = [path.relative_to(root).as_posix()
                  for path in sorted((root / "src" / "aipd_os").rglob("*.py"))
                  if path.name != "__init__.py"
                  and path.relative_to(root).as_posix() not in declared]

    counts = {v: sum(1 for r in rows if r["verdict"] == v)
              for v in ("producer", "checker_only", "absent")}
    return {
        "reference": REFERENCE,
        "item_count": len(items),
        "mapped_count": len(rows),
        "verdict_counts": counts,
        "rows": rows,
        "problems": [dataclasses.asdict(p) for p in problems],
        "diagnostics": {
            "registry_error": registry_error,
            "rows_with_no_implementation_and_no_test": empty_rows,
            "product_modules_not_named_by_any_row": undeclared,
        },
        "ok": not problems and registry_error is None,
    }


def render(report: dict[str, Any]) -> str:
    order = {"producer": "①", "checker_only": "②", "absent": "③"}
    lines = ["C6 交付物覆盖度（分母现算自 references/production-cad-deliverables.md）", ""]
    for row in report["rows"]:
        tests = ", ".join(f"{p}({n})" for p, n in row["tests"].items()) or "无用例"
        lines.append(f"{order[row['verdict']]} {row['item']}  [{row['verdict']}]")
        lines.append(f"    能力行：{', '.join(row['capabilities']) or '无'}")
        lines.append(f"    生产者：{', '.join(row['producers']) or '无（产品侧没有落点）'}")
        lines.append(f"    用例：{tests}")
        lines.append(f"    判读：{row['note']}")
    c = report["verdict_counts"]
    lines.append("")
    lines.append(f"合计 {report['item_count']} 项：有生产者 {c['producer']} / "
                 f"只有校验方 {c['checker_only']} / 零实现 {c['absent']}")
    if report["problems"]:
        lines.append(f"一致性问题 {len(report['problems'])} 条：")
        for p in report["problems"]:
            lines.append(f"  ✗ [{p['kind']}] {p['item']}：{p['detail']}")
    diag = report["diagnostics"]
    if diag["registry_error"]:
        lines.append(f"  ✗ 能力表读不到：{diag['registry_error']}（整轮不可判，不是 0 命中）")
    if diag["rows_with_no_implementation_and_no_test"]:
        lines.append("  · 两栏皆空的能力行（声明了但无从核验）："
                     + ", ".join(diag["rows_with_no_implementation_and_no_test"]))
    mods = diag["product_modules_not_named_by_any_row"]
    if mods:
        lines.append(f"  · implementation_file 一栏里没有点到的产品模块 {len(mods)} 个"
                     "（不等于没被测，只是顺着能力表找不到落点）："
                     + ", ".join(mods[:12]) + ("…" if len(mods) > 12 else ""))
    return "\n".join(lines)


def _an_absent_item() -> str:
    """取一项当前判为零实现的，用于「档位与所列文件矛盾」这条注入。"""
    return next(k for k, v in MAPPING.items() if v["verdict"] == "absent")


def _self_test(root: Path) -> int:
    """四条注入反证：每条都必须让 audit 红，否则这条判据是摆设。"""
    cases = [
        ("分母多一项（映射缺项）", lambda: MAPPING.pop("ICD"), "unmapped"),
        ("映射留了旧项（契约已不要求）", lambda: MAPPING.update({"旧项xyz": {
            "verdict": "absent", "capabilities": [], "producers": [], "tests": [],
            "note": "注入"}}), "stale_mapping"),
        ("生产者路径不存在", lambda: MAPPING["BOM"]["producers"].append(
            "src/aipd_os/bom/nope.py"), "producer_missing"),
        # 注入对象按**当前档位**动态挑，不钉死某一项：那一项哪天升档，这条反证就会
        # 静默变成等价注入（本来就该允许列文件），判据看着没红而已。
        ("档位与所列文件矛盾", lambda: MAPPING[_an_absent_item()].update(
            {"producers": ["src/aipd_os/cad/assembly.py"]}), "verdict_inconsistent"),
        ("能力行 id 不存在", lambda: MAPPING["BOM"]["capabilities"].append("no.such.row"),
         "unknown_capability"),
        ("用例文件里一个 test 都没有", lambda: MAPPING["BOM"]["tests"].append(
            "src/aipd_os/bom/models.py"), "test_empty"),
        ("用例文件路径不存在", lambda: MAPPING["BOM"]["tests"].append(
            "tests/test_no_such_thing.py"), "test_missing"),
    ]
    snapshot = json.dumps(MAPPING, ensure_ascii=False, sort_keys=True)
    survived = []
    for label, mutate, expect in cases:
        before = json.dumps(MAPPING, ensure_ascii=False, sort_keys=True)
        try:
            mutate()
            kinds = {p["kind"] for p in audit(root)["problems"]}
        finally:
            MAPPING.clear()
            MAPPING.update(json.loads(before))
        if expect not in kinds:
            survived.append(f"{label}（期望 {expect} 红，实际判据没开火：{sorted(kinds)}）")
        print(f"{'✓开火' if expect in kinds else '✗没开火'} {label} → {expect}")
    MAPPING.clear()
    MAPPING.update(json.loads(snapshot))
    if survived:
        print("反证没立住的判据：")
        for s in survived:
            print("  ", s)
        return 1
    print(f"--self-test：{len(cases)}/{len(cases)} 条注入都被抓住")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default=".")
    ap.add_argument("--json", dest="json_out", help="把报告写成 JSON（诊断档，不进主线门禁）")
    ap.add_argument("--self-test", action="store_true", help="注入反证：每条判据都必须能红")
    args = ap.parse_args(argv)
    root = Path(args.repo).resolve()
    if args.self_test:
        return _self_test(root)
    report = audit(root)
    print(render(report))
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                                       encoding="utf-8")
    return 0 if report["ok"] else 4


if __name__ == "__main__":
    sys.exit(main())
