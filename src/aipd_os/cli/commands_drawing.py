"""``aipd drawing`` —— 从 3D 模型出二维工程图（DXF）。

诚实前提：出图需要真实 CAD 内核（cadquery/OCP）。内核缺失时**不外推**、
不产出占位文件，而是像其它外部能力一样给 HOLD + 外部任务包。
"""
from __future__ import annotations

from pathlib import Path

from aipd_os.cli._helpers import _emit


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
            provenance=provenance)
    except ValueError as exc:
        print(f"出图参数不合法：{exc}")
        return 2

    def prose():
        print(f"已出图：{out}（{evidence['sheet']} 1:{evidence['scale']}，"
              f"{len(evidence['views'])} 个视图）")
        for view in evidence["views"]:
            print(f"  {view['view']:6s} {view['size_mm'][0]}x{view['size_mm'][1]}mm "
                  f"实线 {view['visible_polylines']} 条 / 虚线 {view['hidden_polylines']} 条")
        print(f"证据文件：{evidence['evidence_file']}  sha256={evidence['sha256'][:16]}…")
        print("未含 GD&T/尺寸链/剖视，见 capability cad.2d_drawings 的 limitation。")
    _emit(args, evidence, prose)
    return 0
