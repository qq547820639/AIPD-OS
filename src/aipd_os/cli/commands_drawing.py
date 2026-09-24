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


def _external_task_pack(args, reason: str) -> int:
    pack = {
        "command": "drawing generate",
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
            provenance=provenance, spec=spec)
    except ValueError as exc:
        print(f"出图参数不合法：{exc}")
        return 2

    unmatched = list(evidence.get("spec_unmatched_features") or [])
    stackups = evidence.get("stackup_check") or {}
    gdt_issues = list(evidence.get("gdt_issues") or [])
    gdt_unmatched = list(evidence.get("gdt_unmatched_features") or [])

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
            print(f"  GD&T 框 {frame['view']}→{frame['feature']}："
                  f"{frame['text']}（挂点 {frame['attach']}，来自实测）")
        for issue in gdt_issues:
            datum = issue.get("datum") or issue.get("datum_feature") or ""
            print(f"  GD&T 未收口：{issue['kind']} {issue.get('feature')}"
                  f"{(' 基准 ' + datum) if datum else ''}"
                  f"{(' 特征 ' + issue['datum_feature']) if issue.get('datum_feature') else ''}"
                  f"{(' 类型 ' + issue['characteristic']) if issue.get('characteristic') else ''}")
        if gdt_unmatched:
            print(f"  GD&T 未收口：声明了框但图上没有这些特征：{gdt_unmatched}")
        print(f"证据文件：{evidence['evidence_file']}  sha256={evidence['sha256'][:16]}…")
        print("未含 GD&T 形位公差框/剖视/局部放大，见 capability cad.2d_drawings 的 limitation。")
    _emit(args, evidence, prose)
    held = bool(unmatched or evidence.get("stackup_inconsistent") or gdt_issues
                or gdt_unmatched)
    return 4 if held else 0
