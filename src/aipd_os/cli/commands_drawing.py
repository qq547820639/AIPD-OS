"""``aipd drawing`` —— 从 3D 模型出二维工程图（DXF）。

诚实前提：出图需要真实 CAD 内核（cadquery/OCP）。内核缺失时**不外推**、
不产出占位文件，而是像其它外部能力一样给 HOLD + 外部任务包。

公差只认 ``--spec`` 声明的 JSON，尺寸值一律由投影几何量出：spec 不参与测量。
"""
from __future__ import annotations

import json
from pathlib import Path

from aipd_os.cli._helpers import _emit


def _load_spec(path: str | None):
    """读公差声明文件。返回 (spec, 错误信息)；不传 spec 就是「无公差」。"""
    if not path:
        return None, None
    file = Path(path)
    if not file.is_file():
        return None, f"--spec 指向的文件不存在：{file}"
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, f"--spec 不是合法 JSON：{exc}"
    if not isinstance(data, dict):
        return None, "--spec 顶层必须是对象（features / global_tolerance）"
    return data, None


def _load_model(step: str | None, native: str | None):
    """加载几何：优先 STEP，其次可编辑原生源（.py）。"""
    import cadquery as cq

    if step:
        return cq.importers.importStep(str(Path(step).resolve()))
    from aipd_os.cad.backends import CadQueryBackend

    backend = CadQueryBackend()
    model = backend.load_native_model(Path(native) if native else None)
    return backend._build(model)


def _external_task_pack(args, reason: str, command: str = "drawing generate") -> int:
    pack = {
        "command": command,
        "ok": False,
        "status": "HOLD",
        "reason": reason,
        "external_task": {
            "capability": "cad.2d_drawings",
            "needs": "安装 CAD 内核后重跑：pip install -e '.[cad]'",
            "part": args.part,
            "revision": args.revision,
            "views": list(args.views.split(",")),
            "requested_output": args.out,
        },
    }

    def prose():
        print(f"出图未执行：{reason}")
        print("已给出外部任务包（不伪造 DXF）。")
    _emit(args, pack, prose)
    return 4


def cmd_drawing_spec(args):
    """从 Product Truth 的 CTQ 生成 ``--spec`` 吃的那份公差声明（F-DRAW-01 第 5 片）。

    有缺口就**不写文件**并返回 4：半成品声明看起来和完整的一模一样，
    差别只在漏标的那几条尺寸上，而漏标正是这套声明要防的事。
    """
    from aipd_os.cad.spec_from_truth import spec_from_ctq

    db = Path(args.db)
    if not db.is_file():
        print(f"状态库不存在：{db}")
        return 2
    out = Path(args.out)
    try:
        from aipd_os.product_truth.store import ProductTruthStore

        store = ProductTruthStore(str(db), tenant_id=args.tenant, project_id=args.project)
        records = store.query(record_type="ctq", status="active")
    except Exception as exc:      # 读不到权威需求不是「没有需求」
        print(f"Product Truth 读取失败：{type(exc).__name__}: {exc}")
        return 2

    spec, gaps = spec_from_ctq(records)
    held = bool(gaps)
    result = {"command": "drawing spec", "ok": not held, "ctq_records": len(records),
              "declared": len(spec["features"]), "gaps": gaps,
              "spec": None if held else spec, "out": None if held else str(out)}

    def prose():
        datum_count = len(spec.get("datums") or [])
        print(f"CTQ 记录 {len(records)} 条 → 尺寸/形位声明 {len(spec['features'])} 条"
              f" + 基准 {datum_count} 个"
              f"（{args.tenant}/{args.project}，只取 status=active）")
        for datum in spec.get("datums") or []:
            print(f"  基准 {datum['id']} → {datum['feature']}（CTQ {datum['ctq_ref']}）")
        for entry in spec["features"]:
            bits = []
            tol = entry.get("tolerance")
            if tol:
                lim = entry["limits"]
                bits.append(f"{tol['upper']:+g}/{tol['lower']:+g}"
                            f"（合格域 {lim['min']:g}–{lim['max']:g}）")
            for decl in entry.get("gdt") or []:
                bits.append(f"形位 {decl.get('characteristic')} 带 {decl.get('zone')}")
            refs = sorted({str(r) for r in [entry.get("ctq_ref")]
                           + [d.get("ctq_ref") for d in entry.get("gdt") or []] if r})
            print(f"  {entry['feature']}: {'；'.join(bits)} ← CTQ {'、'.join(refs)}")
        for gap in gaps:
            print(f"  未收口：{gap['kind']} — {gap['detail']}")
        if held:
            print(f"未写 {out}：{len(gaps)} 条 CTQ 还挂不上图纸，补齐后重跑。")
        else:
            print(f"已写 {out}：可直接 aipd drawing generate --spec {out}")

    _emit(args, result, prose)
    if held:
        return 4
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


def cmd_drawing(args):
    out = Path(args.out)
    if not args.part:
        print("--part 必填（标题栏 PART 字段）")
        return 2
    try:
        import cadquery  # noqa: F401
        import ezdxf  # noqa: F401
    except ImportError as exc:
        return _external_task_pack(args, f"CAD 内核缺失（{exc}）")

    from aipd_os.cad.backends import CadQueryBackend
    from aipd_os.cad.drawings2d import generate_drawing

    spec, spec_error = _load_spec(getattr(args, "spec", None))
    if spec_error:
        print(spec_error)
        return 2

    try:
        model = _load_model(args.step, args.native)
    except Exception as exc:  # 读不到的模型不是「出图成功」
        print(f"模型加载失败：{type(exc).__name__}: {exc}")
        return 2

    provenance = {"tool": f"cadquery {CadQueryBackend().tool_version()}",
                  "model_source": args.step or args.native or "golden_default",
                  "command": "drawing generate", "ok": True, "status": "DONE"}
    try:
        evidence = generate_drawing(
            model, out, part_name=args.part, revision=args.revision,
            views=tuple(v.strip() for v in args.views.split(",") if v.strip()),
            scale=args.scale, material=args.material, sheet=args.sheet,
            provenance=provenance, spec=spec,
            sections=tuple(getattr(args, "section", None) or ()),
            details=tuple(getattr(args, "detail", None) or ()))
    except ValueError as exc:
        print(f"出图参数不合法：{exc}")
        return 2

    unmatched = list(evidence.get("spec_unmatched_features") or [])
    stackups = evidence.get("stackup_check") or {}
    gdt_issues = list(evidence.get("gdt_issues") or [])
    gdt_unmatched = list(evidence.get("gdt_unmatched_features") or [])
    limit_issues = list(evidence.get("spec_limit_issues") or [])
    section_issues = list(evidence.get("section_issues") or [])
    section_warnings = list(evidence.get("section_warnings") or [])
    detail_issues = list(evidence.get("detail_issues") or [])

    def prose():
        print(f"已出图：{out}（{evidence['sheet']} 1:{evidence['scale']}，"
              f"{len(evidence['views'])} 个视图）")
        for view in evidence["views"]:
            print(f"  {view['view']:6s} {view['size_mm'][0]}x{view['size_mm'][1]}mm "
                  f"实线 {view['visible_polylines']} 条 / 虚线 {view['hidden_polylines']} 条")
            check = view.get("chain_check") or {}
            if check.get("segments"):
                print(f"         尺寸链 {check['segments']} 段，"
                      f"各段之和 {check['sum']} vs 总体宽 {check['overall_width']}，"
                      f"闭合差 {check['delta']}")
            section_of = view.get("section_of")
            if section_of:
                print(f"         剖切 {section_of['axis']}={section_of['offset']:g}"
                      f"（保留 {section_of['kept']}）：材料区 {view['cut_regions']} 个 / "
                      f"{view['material_area_mm2']}mm²，剖面线 {view['cut_regions']} 条")
            detail_of = view.get("detail_of")
            if detail_of:
                where = (f"放大 ×{detail_of['factor']:g} ←{detail_of['parent']} "
                         f"圆({detail_of['center'][0]:g},{detail_of['center'][1]:g})"
                         f"/R{detail_of['radius']:g}")
                if view["detail_empty"]:
                    print(f"         {where}：圈空，未编号未标注")
                else:
                    print(f"         {where}：按 {view['drawn_scale']:g} 画，"
                          f"继承尺寸 {len(view['dimensions'])} 条"
                          f"（母视图上已画裁剪圈）")
        print(f"公差：声明 {len(evidence.get('spec_declared_features') or [])} 项、"
              f"落到图上 {evidence.get('tolerance_applied', 0)} 处"
              f"（无声明则不写任何公差）")
        for name, stack in sorted(stackups.items()):
            verdict = stack["verdict"]
            if verdict == "consistent":
                print(f"  公差叠加 {name}：一致（封闭带 {stack['closing_band']} ≥ "
                      f"各段合成 {stack['worst_case']}，余量 {stack['margin']}）")
            elif verdict == "inconsistent":
                print(f"  公差叠加 {name}：**图纸自相矛盾** —— 各段公差带之和 "
                      f"{stack['worst_case']} 超出封闭环 {stack['closing_feature']} "
                      f"的公差带 {stack['closing_band']}，超出 {stack['excess']}")
            elif verdict != "no_chain":
                missing = ", ".join(stack["undeclared"])
                suffix = f"，缺声明：{missing}" if missing else ""
                print(f"  公差叠加 {name}：不可判定（{verdict}）{suffix}")
        if unmatched:
            print(f"未收口：spec 声明的这些特征在图上找不到 ⇒ 少标了公差：{unmatched}")
        if evidence.get("stackup_inconsistent"):
            print("未收口：叠加判定的矛盾意味着这些公差无法同时达成，需改声明或改标注方案。")
        for frame in evidence.get("gdt_frames") or []:
            verdict = ""
            if frame.get("verified") == "deviation":
                verdict = (f"，位置度实测偏差 {frame['deviation_mm']:g}"
                           f" / 带 {frame['zone']:g}"
                           f"{'（合格）' if frame.get('within_zone') else '（超带）'}")
            elif frame.get("characteristic") == "position":
                verdict = "，位置度无理论精确位置，未核偏差"
            print(f"  GD&T 框 {frame['view']}→{frame['feature']}："
                  f"{frame['text']}（挂点 {frame['attach']}，来自实测{verdict}）")
        for issue in gdt_issues:
            datum = issue.get("datum") or issue.get("datum_feature") or ""
            numbers = ""
            if issue.get("deviation_mm") is not None:
                numbers = f" 偏差 {issue['deviation_mm']:g} > 带 {issue.get('zone'):g}"
            print(f"  GD&T 形位未收口：{issue['kind']} {issue.get('feature')}"
                  f"{(' 基准 ' + datum) if datum else ''}"
                  f"{(' 特征 ' + issue['datum_feature']) if issue.get('datum_feature') else ''}"
                  f"{(' 类型 ' + issue['characteristic']) if issue.get('characteristic') else ''}"
                  f"{numbers}")
        if gdt_unmatched:
            print(f"  GD&T 未收口：声明了框但图上没有这些特征：{gdt_unmatched}")
        for msg in section_issues:
            print(f"  剖视未收口：{msg}")
        for msg in section_warnings:
            print(f"  剖视告警：{msg}")
        for msg in detail_issues:
            print(f"  放大未收口：{msg}")
        for issue in limit_issues:
            print(f"  合格域未收口：{issue['feature']} 实测 {issue['measured']:g} 不在 "
                  f"CTQ 的 {issue['min']:g}–{issue['max']:g} 内"
                  f"{('（CTQ ' + issue['ctq_ref'] + '）') if issue['ctq_ref'] else ''}")
        print(f"证据文件：{evidence['evidence_file']}  sha256={evidence['sha256'][:16]}…")
        print("未含阶梯剖/旋转剖，装配图请走 aipd drawing assembly；"
              "爆炸图/装配约束仍未含，详见 capability cad.2d_drawings 的 limitation。")
    _emit(args, evidence, prose)
    held = bool(unmatched or evidence.get("stackup_inconsistent") or gdt_issues
                or gdt_unmatched or section_issues or limit_issues or detail_issues)
    return 4 if held else 0


def cmd_drawing_assembly(args):
    """``aipd drawing assembly`` —— 多零件装配图：逐件投影 + 序号球标 + 明细表。

    几何来自 manifest 里每个零件自己的 STEP，不是单个模型；所以这里**不加载**
    ``--step/--native``，也不接受 ``--spec``：装配视图只有包络尺寸，件级特征公差
    属于单件图（``drawing generate``），在这里声明只会得到「声明了图上没有的特征」。
    """
    out = Path(args.out)
    if not args.part:
        print("--part 必填（标题栏 PART 字段）")
        return 2
    if not args.manifest:
        print("--manifest 必填（装配清单 JSON：{\"parts\":[{name,step,balloon,offset}]}）")
        return 2
    manifest = Path(args.manifest)
    if not manifest.is_file():
        print(f"--manifest 指向的文件不存在：{manifest}")
        return 2
    try:
        import cadquery  # noqa: F401
        import ezdxf  # noqa: F401
    except ImportError as exc:
        return _external_task_pack(args, f"CAD 内核缺失（{exc}）",
                                   command="drawing assembly")

    from aipd_os.cad.assembly import generate_assembly_drawing
    from aipd_os.cad.backends import CadQueryBackend

    provenance = {"tool": f"cadquery {CadQueryBackend().tool_version()}",
                  "model_source": str(manifest), "command": "drawing assembly",
                  "ok": True, "status": "DONE"}
    try:
        evidence = generate_assembly_drawing(
            out, manifest=str(manifest), part_name=args.part, revision=args.revision,
            views=tuple(v.strip() for v in args.views.split(",") if v.strip()),
            scale=args.scale, material=args.material, sheet=args.sheet,
            provenance=provenance)
    except ValueError as exc:
        print(f"装配声明不合法：{exc}")
        return 2

    issues = list(evidence.get("assembly_issues") or [])
    warnings = list(evidence.get("assembly_warnings") or [])

    def prose():
        parts = (evidence.get("assembly") or {}).get("parts") or []
        print(f"已出装配图：{out}（{evidence['sheet']} 1:{evidence['scale']}，"
              f"{len(parts)} 个零件 / {len(evidence['views'])} 个视图）")
        for view in evidence["views"]:
            segments = view.get("segments")
            print(f"  {view['view']:11s} 包络 {view['size_mm'][0]}x{view['size_mm'][1]}mm "
                  f"实线 {view['visible_polylines']} 条 / 虚线 {view['hidden_polylines']} 条"
                  f"（分段按零件归属：{len(segments or [])} 段）")
            for one in view.get("assembly_parts") or []:
                print(f"      {one['balloon']:>3d} {one['part']:12s} "
                      f"可见折线 {one['visible_polylines']} 条 / "
                      f"隐藏 {one['hidden_polylines']} 条 "
                      f"挂点 ({one['centroid'][0]:g}, {one['centroid'][1]:g})")
            balloons = view.get("balloons")
            if view.get("balloon_view"):
                print(f"      球标 {len(balloons or [])} 个，包络投影重叠 "
                      f"{view['overlap_area_mm2']}mm²")
            else:
                print("      本视图不标球标（装配图只在一个视图上编号）")
        listed = evidence.get("parts_list") or {}
        print(f"明细表：{len(listed.get('rows') or [])} 行，列 {listed.get('columns')}，"
              f"绘制方式 {listed.get('rendered_by')}")
        for msg in issues:
            print(f"  装配未收口：{msg}")
        for msg in warnings:
            print(f"  装配告警：{msg}")
        print("  没有做的事：干涉检查（只报包络投影重叠，不做实体求交）、"
              "爆炸图/装配约束、明细表数量与材料列（数量权威在 BOM，尚未接线）。")
        print(f"证据文件：{evidence['evidence_file']}  sha256={evidence['sha256'][:16]}…")
    _emit(args, evidence, prose)
    return 4 if issues else 0
