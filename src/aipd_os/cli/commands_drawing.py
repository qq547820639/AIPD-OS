"""``aipd drawing`` —— 从 3D 模型出二维工程图（DXF）。

诚实前提：出图需要真实 CAD 内核（cadquery/OCP）。内核缺失时**不外推**、
不产出占位文件，而是像其它外部能力一样给 HOLD + 外部任务包。

公差只认 ``--spec`` 声明的 JSON，尺寸值一律由投影几何量出：spec 不参与测量。
"""
from __future__ import annotations

import argparse
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
    # 第 56 片实测补的一格：库里**一条 active CTQ 都没有**时 gaps 是空的，
    # 于是旧行为是"写一份 features=[] 的声明 + 落一条没有引用的血缘记录 + ok=true"——
    # 把"还没有人声明要求"读成"声明已完成"。链头（`aipd ctq add`）今天接上之后，
    # 这个状态有了明确的下一步动作，所以判未收口（退码 4，与 gaps 同档）而不是判成功。
    empty_declaration = not spec["features"] and not (spec.get("datums") or [])
    held = bool(gaps) or empty_declaration
    result = {"command": "drawing spec", "ok": not held, "ctq_records": len(records),
              "declared": len(spec["features"]), "gaps": gaps,
              "empty_declaration": empty_declaration,
              "spec": None if held else spec, "out": None if held else str(out)}

    lineage = None
    lineage_error = None

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
        if gaps:
            print(f"未写 {out}：{len(gaps)} 条 CTQ 还挂不上图纸，补齐后重跑。")
        elif empty_declaration:
            print(f"未写 {out}：库里 {len(records)} 条 active CTQ"
                  "没有声明出任何尺寸、形位或基准 ⇒ 这份声明是空的，"
                  "空声明不是交付物。先跑 aipd ctq add --feature … "
                  "--drawing-feature … --nominal … --lower … --upper … "
                  "--inspection … --by <谁>")
        else:
            print(f"已写 {out}：可直接 aipd drawing generate --spec {out}")
            if lineage is not None:
                print(f"  血缘：{lineage['record_id']} + "
                      f"{lineage['edges']} 条 CTQ→声明边"
                      f"（{'、'.join(lineage['ctq_refs']) or '无引用'}）")
            elif lineage_error:
                print(f"  血缘未落库：{lineage_error}"
                      "（声明已写出，但传播到不了它 ⇒ 判未收口）")

    if held:
        _emit(args, result, prose)
        return 4

    # 先落盘、再落血缘，最后统一输出：血缘写不进去时**不能**报成功——
    # 一份没有出处的声明正是这一族命令要防的东西（第 43 片）。
    out.parent.mkdir(parents=True, exist_ok=True)
    from aipd_os.cad.spec_lineage import record_spec_lineage, render_spec_text

    out.write_text(render_spec_text(spec), encoding="utf-8")

    try:
        lineage = record_spec_lineage(store, spec, path=out,
                                      tenant_id=args.tenant,
                                      project_id=args.project)
    except Exception as exc:      # noqa: BLE001 - 报错但不静默：下面判 4
        lineage_error = f"{type(exc).__name__}: {exc}"
    result["lineage"] = lineage
    result["lineage_error"] = lineage_error
    if lineage_error:
        # --json 的 ok 必须与退码同向：否则机器读到的是一份"成功"的判决，
        # 而终端退出码说没收口。
        result["ok"] = False
    _emit(args, result, prose)
    return 4 if lineage_error else 0


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

    # 血缘：给了 --db 才登记，没给就明说（图纸本身仍然成立，不是失败）。
    lineage = None
    lineage_error = None
    lineage_skip_reason = None
    db_arg = getattr(args, "db", None)
    spec_arg = getattr(args, "spec", None)
    if db_arg:
        import hashlib

        from aipd_os.cad.dxf_lineage import model_input_digest, record_dxf_lineage
        from aipd_os.product_truth.store import ProductTruthStore

        db = Path(db_arg)
        if not db.is_file():
            print(f"状态库不存在：{db}（读不到权威库不等于「没有血缘」）")
            return 2
        try:
            store = ProductTruthStore(str(db), tenant_id=args.tenant,
                                      project_id=args.project)
            lineage = record_dxf_lineage(
                store, dxf_path=out,
                spec_path=Path(spec_arg) if spec_arg else None,
                model=model_input_digest(step=args.step, native=args.native),
                part=args.part, revision=args.revision,
                views=[v.strip() for v in args.views.split(",") if v.strip()],
                scale=args.scale, sheet=args.sheet,
                material=args.material,
                sections=list(getattr(args, "section", None) or ()),
                details=list(getattr(args, "detail", None) or ()),
                dxf_sha256=hashlib.sha256(out.read_bytes()).hexdigest(),
                tenant_id=args.tenant, project_id=args.project)
        except Exception as exc:      # noqa: BLE001 - 下面判未收口，不静默
            lineage_error = f"{type(exc).__name__}: {exc}"
    else:
        lineage_skip_reason = "未给 --db ⇒ 不登记「声明 → 图纸」血缘"

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
        if lineage is not None:
            print(f"血缘：{lineage['record_id']}（输入签名 "
                  f"{lineage['input_signature'][:16]}，边 {lineage['edges']} 条"
                  f"{'，新建' if lineage['created'] else '，同输入命中已有记录'}）")
            if lineage["upstream_reason"]:
                print(f"  上游未连的原因：{lineage['upstream_reason']}")
        elif lineage_error:
            print(f"  血缘未落库：{lineage_error}"
                  "（图纸已写出，但传播到不了它 ⇒ 判未收口）")
        else:
            print(f"  血缘：{lineage_skip_reason}")
        print("未含阶梯剖/旋转剖，装配图请走 aipd drawing assembly；"
              "爆炸图/装配约束仍未含，详见 capability cad.2d_drawings 的 limitation。")
    emitted = {**evidence, "lineage": lineage, "lineage_error": lineage_error,
               "lineage_skipped": lineage_skip_reason}
    if lineage_error:
        # 与第 43 片同一条纪律：--json 的 ok 必须与退码同向，
        # 否则机器面读到的是"成功"，终端读到的是一句"没落库"。
        emitted["ok"] = False
    _emit(args, emitted, prose)
    held = bool(unmatched or evidence.get("stackup_inconsistent") or gdt_issues
                or gdt_unmatched or section_issues or limit_issues or detail_issues
                or lineage_error)
    return 4 if held else 0


def _rework_failure_reason(stdout_text: str) -> str:
    """把一次未收口的出图压成一行原因。

    整份证据 JSON（几十 KB）塞进 `reason` 会把 `truth rework` 给 owner 看的那几行冲掉，
    而"为什么不收口"本来就只在那几个 issue 列表里。
    """
    for line in reversed(stdout_text.strip().splitlines()):
        try:
            data = json.loads(line)
        except ValueError:
            continue
        if not isinstance(data, dict):
            continue
        kinds = sorted({str(item.get("kind"))
                        for item in (data.get("spec_limit_issues") or [])
                        if isinstance(item, dict)})
        bits = [f"合格域未收口 {','.join(kinds)}"] if kinds else []
        for key, label in (("spec_unmatched_features", "声明落空"),
                           ("gdt_issues", "形位未收口"),
                           ("section_issues", "剖视未收口"),
                           ("detail_issues", "放大未收口"),
                           ("stackup_inconsistent", "图纸叠加矛盾"),
                           ("lineage_error", "血缘未落库")):
            if data.get(key):
                bits.append(label)
        return "；".join(bits) or "未收口（原因未识别）"
    tail = [ln for ln in stdout_text.strip().splitlines() if ln.strip()][-1:]
    return tail[0][:200] if tail else "（无输出）"


def dxf_render_namespace(meta: dict, out_path: Path) -> argparse.Namespace:
    """把版本记录里那份输入还原成 `drawing generate` 的参数对象。

    刻意不 import `aipd_os.cli.main`：`main -> commands -> commands_truth -> 本模块 -> main`
    会成环（`tests/test_import_cycles.py` 常驻钉着，本轮实测翻过一次红），
    所以这里直接调**同一个模块**里的 `cmd_drawing` —— 仍然是同一份实现，没有第二套投影代码。
    参数面由 `tests/test_dxf_rework.py::TestRenderArgumentSurface` 对照 subparser 的
    `add_argument` 清单反查：以后给 `drawing generate` 新加一个旗子而这里没跟上就要红。
    """
    kind = str(meta.get("model_kind") or "")
    source = str(meta.get("model_source") or "")
    return argparse.Namespace(
        step=source if kind == "step" else None,
        native=source if kind == "native" else None,
        out=str(out_path),
        part=str(meta["part"]),
        revision=str(meta["revision"]),
        views=",".join(str(v) for v in meta["views"]),
        scale=float(meta["scale"]),
        material=str(meta.get("material") or "-"),
        sheet=str(meta["sheet"]),
        section=list(meta.get("sections") or []) or None,
        detail=list(meta.get("details") or []) or None,
        spec=str(meta["spec_path"]) if meta.get("spec_path") else None,
        db=None,          # 明说的跳过：血缘由返工执行器更新「这一条」记录
        tenant=None,      # db=None ⇒ 这两个作用域名不参与
        project=None,
        json=True,
        drawing_cmd="generate")


def render_dxf_from_record(meta: dict) -> str:
    """按版本记录里那份输入集合**重跑一次出图**，返回产物 sha256。

    刻意复用 `cmd_drawing`（`aipd drawing generate` 那条生产路径本身），
    不复制第二份投影代码：两份实现一旦对默认值/参数处理有差异，
    "返工重画出来的图"和"人跑出来的图"就会在同一条记录下不同形。

    刻意**不带 `--db`**：返工更新的是「这一条」记录（引擎随后 bump 版本、关 stale），
    生产面那条「换输入 ⇒ 另起一版、旧版标 superseded」的规则不适用于返工；
    不给 db 走的就是第 46 片写下的「明说的跳过」分支。

    先出到暂存目录，**确认收口之后**才替换正式产物与证据侧车：
    一次失败的返工不许把磁盘上那份还能用的图覆盖掉。

    只认退码 0。4 的含义是「图出来了但判未收口」（合格域冲突等），
    这时候把返工记成成功，等于让引擎替我们把一条未收口的事实 bump 成新版本。
    """
    import contextlib
    import hashlib
    import io
    import shutil
    import tempfile

    final = Path(str(meta["path"]))
    staging = Path(tempfile.mkdtemp(prefix="dxf-rework-"))
    staged = staging / final.name
    captured = io.StringIO()
    try:
        with contextlib.redirect_stdout(captured):
            rc = cmd_drawing(dxf_render_namespace(meta, staged))
        if rc != 0:
            raise RuntimeError(
                f"drawing generate 退码 {rc}："
                f"{_rework_failure_reason(captured.getvalue())}"
                "（暂存产物已丢弃，正式图纸未动）")
        final.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(staged), str(final))
        sidecar = staging / f"{final.name}.evidence.json"
        if sidecar.is_file():
            shutil.move(str(sidecar),
                        str(final.parent / f"{final.name}.evidence.json"))
        return hashlib.sha256(final.read_bytes()).hexdigest()
    finally:
        shutil.rmtree(staging, ignore_errors=True)

def _bom_lines_or_none(args):
    """``--db`` + ``--bom`` 那一接线：返回 ``(bom_lines, rc)``，rc 非 None 就直接返回。

    装配图与装配步骤文档共用同一条读法（同一权威、同一失败文案），否则两条命令
    对「只给了一半参数」「库不存在」「BOM 编号写错」会给出不一致的处置。
    """
    db_arg = getattr(args, "db", None)
    bom_arg = getattr(args, "bom", None)
    if bool(db_arg) != bool(bom_arg):
        print("--db 与 --bom 要一起给：只给一个就是半条接线，"
              "要么两边都核、要么明说不核，不能画一张声称完整的图")
        return None, 2
    if not db_arg:
        return None, None
    from aipd_os.bom.store import BomStore, bom_store_path

    db = Path(db_arg)
    if not db.is_file():
        print(f"状态库不存在：{db}（读不到 BOM 权威表不等于「没有 BOM」）")
        return None, 2
    # --db 指的是**状态库**；BOM 按产品口径在同目录的 bom.db 里。直接
    # BomStore(db) 会给权威状态库加 BOM 表——状态库迁移已冻结，正是要防这个
    bom_db = bom_store_path(db)
    if not bom_db.is_file():
        print(f"BOM 库不存在：{bom_db}（--db 是状态库，BOM 取同目录的 bom.db；"
              "先用 aipd bom 建出来，不拿新建的空库当「已核对」）")
        return None, 2
    try:
        store = BomStore(bom_db)
        # 先确认那张表真在：读不到表就当空 BOM，会把「编号写错了」报成
        # 「每一行都对不上」——两句话的处置完全不同
        if store.get_bom(args.tenant, args.project, bom_arg) is None:
            print(f"BOM {bom_arg} 在 {args.tenant}/{args.project} 下不存在："
                  "先把 BOM 建出来或核对编号，不拿空表当「已核对」")
            return None, 2
        return store.list_lines(args.tenant, args.project, bom_arg), None
    except Exception as exc:          # 权威表读不动就不是「绑定了空 BOM」
        print(f"BOM 读取失败：{type(exc).__name__}: {exc}")
        return None, 2


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

    bom_lines, bom_rc = _bom_lines_or_none(args)
    if bom_rc is not None:
        return bom_rc

    provenance = {"tool": f"cadquery {CadQueryBackend().tool_version()}",
                  "model_source": str(manifest), "command": "drawing assembly",
                  "ok": True, "status": "DONE"}
    try:
        evidence = generate_assembly_drawing(
            out, manifest=str(manifest), part_name=args.part, revision=args.revision,
            views=tuple(v.strip() for v in args.views.split(",") if v.strip()),
            scale=args.scale, material=args.material, sheet=args.sheet,
            provenance=provenance, bom_lines=bom_lines, explode=args.explode)
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
        exploded = [v for v in evidence.get("views") or [] if v.get("exploded")]
        if exploded:
            total = sum(len(v.get("connectors") or []) for v in exploded)
            print(f"  爆炸视图：{len(exploded)} 个视图、{total} 条装配位→爆炸位连接线"
                  "（位移由 manifest 的 explode 声明，本命令不算拆卸方向）")
        listed = evidence.get("parts_list") or {}
        bound = evidence.get("bom")
        print(f"明细表：{len(listed.get('rows') or [])} 行，列 {listed.get('columns')}，"
              f"绘制方式 {listed.get('rendered_by')}")
        if bound:
            print(f"  数量、单位、材料与工艺都来自 BOM "
                  f"{bound['bom_id'] or bound['bom_ids']}"
                  f"（{bound['lines']} 行）；对应关系靠 manifest 的 bom_item 声明，"
                  f"不按零件名字猜")
            bound_rows = [r for r in (listed.get("rows") or [])
                          if r.get("bom_line_id") is not None]
            # 只数**绑上的**行：没绑上的已经被「装配未收口」点名，这里再报一遍就分不出缺的是哪一半
            for cell, label in (("material", "材料"), ("process", "工艺")):
                missing = sorted(int(r["item"]) for r in bound_rows if not r.get(cell))
                print(f"    {label}已填 {len(bound_rows) - len(missing)}/"
                      f"{len(bound_rows)} 行"
                      + (f"，缺的球标 {missing}" if missing else "，没有缺行"))
        else:
            print("  未接 BOM：明细表不含数量/材料/工艺列，一个猜测值都不印。")
        for msg in issues:
            print(f"  装配未收口：{msg}")
        for msg in warnings:
            print(f"  装配告警：{msg}")
        print("  没有做的事：干涉检查（只报包络投影重叠，不做实体求交）、"
              "装配约束/配合、爆炸位移的自动求解（要装配约束与无碰撞路径两样前提，本仓都没有）、"
              "多工序工艺路线（工艺只有那一格，工序顺序/工时/工序成本不建模）。")
        print(f"证据文件：{evidence['evidence_file']}  sha256={evidence['sha256'][:16]}…")
    _emit(args, evidence, prose)
    return 4 if issues else 0


def cmd_drawing_assembly_step(args):
    """``aipd drawing assembly-step`` —— 按装配清单出总装 STEP（写完回读校验）。

    需要 CadQuery/OCP：这里不做投影，但要把每个零件的实体真读出来再摆放，
    写完还要重新导入逐件比对，所以内核不在就是外部任务包，不假产文件。
    """
    out = Path(args.out)
    if not args.part:
        print("--part 必填（总装 STEP 的产品名）")
        return 2
    manifest = Path(args.manifest)
    if not manifest.is_file():
        print(f"--manifest 指向的文件不存在：{manifest}")
        return 2
    try:
        import cadquery  # noqa: F401
    except ImportError as exc:
        return _external_task_pack(args, f"CAD 内核缺失（{exc}）",
                                   command="drawing assembly-step")

    from aipd_os.cad.assembly import export_assembly_step
    from aipd_os.cad.backends import CadQueryBackend

    provenance = {"tool": f"cadquery {CadQueryBackend().tool_version()}",
                  "model_source": str(manifest), "command": "drawing assembly-step",
                  "ok": True, "status": "DONE"}
    try:
        evidence = export_assembly_step(out, manifest=str(manifest), part_name=args.part,
                                        revision=args.revision, provenance=provenance)
    except ValueError as exc:
        print(f"总装 STEP 产不出来：{exc}")
        return 2

    def prose():
        print(f"已出总装 STEP：{out}（声明 {evidence['declared_part_count']} 件、"
              f"回读 {evidence['solid_count']} 个实体，逐件位置与体积已核对）")
        for one in evidence["parts"]:
            print(f"  {one['balloon']:>3d} {one['name']:12s} 摆放 "
                  f"({'、'.join(f'{v:g}' for v in one['placement'])}) "
                  f"体积 {one['volume_mm3']:g}mm³ 源实体 {one['source_solid_count']} 个")
        for msg in evidence["coincident_placements"]:
            print(f"  告警：{msg}")
        if not evidence["step_product_names_readable"]:
            print(f"  名字：{evidence['step_product_names_reason']}")
        print("  没做的事：" + "；".join(evidence["not_covered"]))
        print(f"证据文件：{evidence['evidence_file']}  "
              f"sha256={evidence['document_sha256'][:16]}…")
    _emit(args, evidence, prose)
    return 0


def cmd_drawing_dfm(args):
    """``aipd drawing dfm`` —— DFM/DFA 分析报告（实测几何 + 带来源的阈值判定）。

    需要 CadQuery/OCP：这里量的是实体（圆柱面参数、射线求交），不是读图纸注记。
    ``--spec`` 走的是出图那条同一个公差声明文件：有声明才判「公差超出常规可达」，
    没声明就记盲区，**不拿无声明当宽松合格**。
    """
    out = Path(args.out)
    if not args.part:
        print("--part 必填（报告标题里的零件代号）")
        return 2
    if not args.step:
        print("--step 必填（要分析的 STEP 文件；DFM 判的是实体几何，不是图纸）")
        return 2
    step = Path(args.step)
    if not step.is_file():
        print(f"--step 指向的文件不存在：{step}")
        return 2
    try:
        import cadquery  # noqa: F401
    except ImportError as exc:
        return _external_task_pack(args, f"CAD 内核缺失（{exc}）", command="drawing dfm")

    from aipd_os.cad.backends import CadQueryBackend
    from aipd_os.cad.dfm import generate_dfm_report

    spec, spec_error = _load_spec(args.spec)
    if spec_error:
        print(spec_error)
        return 2
    try:
        import cadquery as cq

        model = cq.importers.importStep(str(step))
    except Exception as exc:
        print(f"STEP 读不出来：{type(exc).__name__}: {exc}（读不出实体就没有几何可量，"
              "不交一份空分析）")
        return 2

    provenance = {"tool": f"cadquery {CadQueryBackend().tool_version()}",
                  "model_source": str(step), "command": "drawing dfm",
                  "ok": True, "status": "DONE"}
    try:
        evidence = generate_dfm_report(
            out, model=model, part_name=args.part, revision=args.revision,
            material=args.material, spec=spec, spacing_mm=args.spacing,
            provenance=provenance)
    except ValueError as exc:
        print(f"DFM 分析做不了：{exc}")
        return 2

    holds = [f for f in evidence["findings"] if f["verdict"] == "hold"]
    advisories = [f for f in evidence["findings"] if f["verdict"] == "flag"]

    def prose():
        facts = evidence["facts"]
        wall = facts["wall_measurement"]
        counts = evidence["counts"]
        print(f"已出 DFM/DFA 分析报告：{out}（判了 {counts['measured']} 条、"
              f"盲区 {counts['blind']} 条）")
        envelope = "x".join(f"{v:g}" for v in facts["envelope_mm"])
        print(f"  包络 {envelope}mm "
              f"体积 {facts['volume_mm3']:g}mm³ 面 {facts['face_count']} 个 "
              f"整孔 {len(facts['holes'])} 个")
        print(f"  最小壁厚 {wall['min_mm'] if wall['min_mm'] is not None else '没量出来'}mm"
              f"（网格间距 {wall['spacing_mm']:g}mm，有命中射线 {wall['rays_with_hits']} 条，"
              f"奇数命中 {wall['odd_hit_rays']} 条——斜置薄壁会测厚不测薄）")
        print(f"  材料 {evidence['material'] or '未给'} ⇒ 按 {evidence['material_class']} 类判")
        for item in evidence["findings"]:
            limit = f"{item['limit']:g}{item['unit']}" if item["limit"] is not None else "不设阈值"
            print(f"    [{item['verdict']}] {item['name']}："
                  f"实测 {item['value']:g}{item['unit']} vs {limit}（{item['measured']}）")
        for item in evidence["blind"]:
            print(f"    [盲区] {item['name']}：{item['reason']}")
        for item in holds:
            print(f"  需制造方确认：{item['rule']}（{item['measured']}）")
        if advisories:
            print("  告警（不阻断）：" + "、".join(i["rule"] for i in advisories))
        print("  本次没看：" + "、".join(evidence["not_covered"]))
        print(f"证据文件：{evidence['evidence_file']}  "
              f"sha256={evidence['document_sha256'][:16]}…")
    _emit(args, evidence, prose)
    return 4 if holds else 0


def cmd_drawing_assembly_steps(args):
    """``aipd drawing assembly-steps`` —— 装配步骤文档（Markdown，可加 `--pdf` 的 A4 图框矢量
    PDF，PDF 那一面还能排 `--draw-image` 的作者示意图；两条版式都带证据 sidecar）。

    这一步**不投影几何**（文档不需要视图），所以不检查 CadQuery/ezdxf 在不在；
    但零件的 STEP 文件存在性照样要过 —— 连模型都不存在的零件，步骤里引用它就是空话。
    顺序、各步引用哪些球标、动作原文都来自 manifest；本命令不补号也不代拟。
    """
    from aipd_os.cad.assembly_steps import generate_assembly_steps

    out = Path(args.out)
    if not args.part:
        print("--part 必填（文档标题里的装配体代号）")
        return 2
    if not args.manifest:
        print('--manifest 必填（装配清单 JSON：{"parts":[...],"assembly_steps":'
              '[{"no":1,"action":"…","balloons":[1]}]}）')
        return 2
    manifest = Path(args.manifest)
    if not manifest.is_file():
        print(f"--manifest 指向的文件不存在：{manifest}")
        return 2
    bom_lines, bom_rc = _bom_lines_or_none(args)
    if bom_rc is not None:
        return bom_rc

    provenance = {"tool": "aipd_os.cad.assembly_steps（声明渲染，无几何投影）",
                  "model_source": str(manifest), "command": "drawing assembly-steps",
                  "ok": True, "status": "DONE"}
    draw_image = getattr(args, "draw_image", None)
    if draw_image is not None and not str(draw_image).strip():
        # 与上面 --db/--bom 那条不同：那里"空值"就是没给，这里空值是"给了但没给对"。
        # 按没给处理等于把作者要的图静默丢掉，本仓对这一类一律当场拒。
        print("--draw-image 给了空值：要么给图片路径，要么别给这个旗子")
        return 2
    if draw_image is not None and not Path(draw_image).is_file():
        print(f"--draw-image 指向的文件不存在：{draw_image}")
        return 2
    if draw_image is not None and not getattr(args, "pdf", None):
        print("--draw-image 要和 --pdf 一起给：Markdown 版式不嵌图，"
              "只给图就等于把这张图丢掉")
        return 2
    pdf_arg = getattr(args, "pdf", None)
    pdf_path = None
    if pdf_arg:
        pdf_path = (out.with_suffix(".pdf") if pdf_arg == "@AUTO@" else Path(pdf_arg))
    try:
        evidence = generate_assembly_steps(
            out, manifest=str(manifest), part_name=args.part, revision=args.revision,
            bom_lines=bom_lines, provenance=provenance, pdf_path=pdf_path,
            draw_image=draw_image)
    except ValueError as exc:
        print(f"装配步骤声明不合法：{exc}")
        return 2

    issues = list(evidence.get("assembly_step_issues") or [])
    coverage = evidence["assembly_steps"]["balloon_coverage"]

    def prose():
        print(f"已出装配步骤文档：{out}（{evidence['assembly_steps']['step_count']} 步，"
              f"球标覆盖 {len(coverage['referenced'])}/{len(coverage['declared'])}，"
              f"清单 {manifest.name}）")
        if evidence.get("pdf"):
            print(f"  PDF：{evidence['pdf']['path']}"
                  f"（{evidence['pdf']['pages']} 页，图框 + 标题栏，文字可抽取）")
        for step in evidence["steps"]:
            cited = "、".join(f"{c['balloon']}（{c['part']}）" for c in step["cited"])
            print(f"  步骤 {step['no']:>2d}  引用球标 {cited}：{step['action']}")
        if evidence.get("bom"):
            print(f"  数量/单位/材料/工艺取自 BOM "
                  f"{evidence['bom']['bom_id'] or evidence['bom']['bom_ids']}"
                  f"（{evidence['bom']['lines']} 行）；对应关系靠 manifest 的 bom_item 声明")
        else:
            print("  未接 BOM：零件清单只有 ITEM/PART 两列，一个猜测值都不印。")
        for msg in issues:
            print(f"  装配步骤未收口：{msg}")
        print("  本文档不承载：" + "、".join(evidence["not_covered"])
              + "（维护那一半要属主给内容，见 capability cad.assembly_instructions）")
        print(f"证据文件：{evidence['evidence_file']}  "
              f"sha256={evidence['document_sha256'][:16]}…")
    _emit(args, evidence, prose)
    return 4 if issues else 0
