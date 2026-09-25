"""发布就绪证据文档的**生产者**。

命令 ``aipd release manifest``，能力行 ``industrialize.release_evidence``。

门禁 `scripts/production_release_gate.py` 早就把 `gdt_covers_ctq` / `ctq_has_inspection`
写成 fail-closed，但本轮实测：全仓 `ctq`/`gdt` 两个数组只出现在测试夹具里
（`tests/test_production_release_gate.py:44`、`tests/test_cli.py:336`），`src/` 内零生产点
——即 C5/C6 的证据只能靠人手写 JSON，写什么就是什么。本模块把这些字段改成**现取**：

- BOM 行数 / 版本：`BomStore`（bom 库按产品口径放在 state.db 同目录的 ``bom.db``）；
- CTQ：Product Truth 的 ``record_type="ctq"`` 记录（``metadata.feature`` 是必填出处）；
- GD&T：**只从图纸证据长出来**——一条 gdt 项要求「图纸上真的标了公差」+「该声明显式带
  ``ctq_ref``」+「偏差与该 CTQ 的上下限数值一致」三条同时成立。CTQ 侧永远产不出 gdt，
  所以「有 CTQ 没画上」必然判未覆盖，不给空真通过的机会；
- 版本一致性：``bom_version`` 取 BOM 头修订、``drawings_version`` 取图纸标题栏修订、
  ``model_version`` 取模型文件内容哈希——三个互相独立的来源。不一致时**如实留在文档里**
  让门禁去判红，绝不为过门禁把三者填成同一个串（那正是 ``drawing_cad_same_revision``
  要抓的东西）。

不做的事：按名字模糊匹配 CTQ 与图纸特征（那是装饰性接线）；没有模型时编造
``model_part_count``；把 ``approval_status`` 默认写成 "approved"。
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_TENANT = "default"


def _issue(issues: list[dict[str, Any]], kind: str, detail: str, *, blocking: bool,
           feature: str | None = None) -> None:
    """一条问题项；涉及图纸特征时带上 ``feature``，让下游能按特征机读而不是解析中文。"""
    item: dict[str, Any] = {"kind": kind, "detail": detail, "blocking": blocking}
    if feature:
        item["feature"] = feature
    issues.append(item)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _evidence_path(dxf: Path) -> Path:
    return dxf.with_suffix(".evidence.json")


def _collect_ctq(truth: Any, issues: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """CTQ 记录 → {record_id: 条目}；缺 feature 的逐条点名（不静默少一条）。"""
    by_id: dict[str, dict[str, Any]] = {}
    for rec in truth.query(record_type="ctq", status="active"):
        meta = rec.metadata or {}
        feature = meta.get("feature")
        if not feature:
            _issue(issues, "ctq_missing_feature",
                   f"CTQ {rec.record_id}（{rec.content!r}）缺 metadata.feature，"
                   f"无法与图纸特征核对", blocking=True)
            continue
        inspection = meta.get("inspection_method") or meta.get("test_method")
        if not inspection:
            _issue(issues, "ctq_missing_inspection",
                   f"CTQ {feature}（{rec.record_id}）没有检验方法，"
                   f"门禁 ctq_has_inspection 会判红", blocking=True)
        by_id[str(rec.record_id)] = {
            "record_id": str(rec.record_id),
            "feature": str(feature),
            "inspection_method": inspection,
            "lower_limit": meta.get("lower_limit"),
            "upper_limit": meta.get("upper_limit"),
            "trust_level": rec.trust_level,
        }
    if not by_id:
        _issue(issues, "no_ctq", "Product Truth 里没有 active 的 ctq 记录；"
                                 "门禁 gdt_covers_ctq / ctq_has_inspection 都会 fail-closed",
               blocking=True)
    return by_id


def _agrees_with_ctq(declared: dict[str, float], nominal: float,
                     ctq: dict[str, Any]) -> bool | None:
    """图纸偏差 vs CTQ 绝对上下限。CTQ 没写限值时返回 None（不可核，不是通过）。"""
    lo, hi = ctq.get("lower_limit"), ctq.get("upper_limit")
    if lo is None or hi is None:
        return None
    return (abs(float(declared["upper"]) - (float(hi) - nominal)) <= 1e-9
            and abs(float(declared["lower"]) - (float(lo) - nominal)) <= 1e-9)


def _check_assembly(rel: str, evidence: dict[str, Any], bom_id: str | None,
                    issues: list[dict[str, Any]]) -> dict[str, Any]:
    """装配图特有的三条就绪判据，并带回这一张图的材料覆盖读数。

    「图上没号」与「数量来自另一张表」都会让这张图看起来完整而实际不完整，
    所以都是阻断项；没绑过 BOM 只是「数量没核」，装配图本身仍然成立 ⇒ 非阻断。
    第三条是覆盖判据：C6（``references/production-cad-deliverables.md``）要的是
    「材料**与**工艺」，所以两半各自点名到球标、各自一条问题——合成一条「信息不全」
    就看不出还差哪一半，也就没人知道该去补什么。压根没绑上的行**不重复计入**缺材料/缺工艺：
    那是 ``assembly_unresolved`` 已经判住的事，报两遍会淹掉真信号。
    """
    coverage: dict[str, Any] = {"bound_rows": 0, "with_material": 0, "with_process": 0,
                                "unbound_rows": 0, "missing_material": [],
                                "missing_process": [], "drawings_without_bom": 0}
    unresolved = list(evidence.get("assembly_issues") or [])
    if unresolved:
        first = str(unresolved[0])
        _issue(issues, "assembly_unresolved",
               f"{rel}：装配图有 {len(unresolved)} 条未收口（球标↔BOM 未闭合），"
               f"第一条：{first}", blocking=True)
    bound = str((evidence.get("bom") or {}).get("bom_id") or "")
    if not bound:
        _issue(issues, "assembly_bom_unverified",
               f"{rel}：这张装配图出图时没接 BOM，明细表不含数量与材料列（不算未收口）",
               blocking=False)
        coverage["drawings_without_bom"] = 1
        return coverage
    if bom_id and bound != bom_id:
        _issue(issues, "assembly_bom_mismatch",
               f"{rel}：图上的数量取自 BOM {bound}，本份证据核的是 BOM {bom_id}；"
               "两边不是同一张表，计数一致性不成立", blocking=True)
    # 爆炸事实单独判一条： exploded=true 却没有把每件从装配位连回来的线，
    # 就是一张「零件被摆开了但没人知道谁从哪儿来」的图——证据来自手改或旧版本时正好是这形状。
    for view in evidence.get("views") or []:
        if not view.get("exploded"):
            continue
        parts = view.get("assembly_parts") or []
        cons = view.get("connectors") or []
        if len(cons) < len(parts):
            _issue(issues, "explode_unconnected",
                   f"{rel}：视图 {view.get('view') or view.get('name')} "
                   f"标了爆炸视图，但 {len(parts)} 个零件"
                   f"只有 {len(cons)} 条装配位→爆炸位连接线：摆开的位置没有出处，"
                   "读图的人分不出谁从哪儿移开", blocking=True)
    rows = list((evidence.get("parts_list") or {}).get("rows") or [])
    for row in rows:
        if row.get("bom_line_id") is None:
            coverage["unbound_rows"] += 1
            continue
        coverage["bound_rows"] += 1
        # 两格各读各的：拿工艺顶材料（或反过来）会把真正缺的那一半盖住
        for cell in ("material", "process"):
            if row.get(cell):
                coverage["with_" + cell] += 1
            else:
                coverage["missing_" + cell].append(row.get("item"))
    for cell, label in (("material", "材料"), ("process", "工艺")):
        missing = coverage["missing_" + cell]
        if missing:
            _issue(issues, f"{cell}_missing",
                   f"{rel}：{len(missing)} 行已绑到 BOM 行但那一行没填{label}"
                   f"（球标 {sorted(missing)}）：C6 要材料与工艺，"
                   f"{label}没落到图上就不算交齐", blocking=True)
    return coverage


def _collect_drawings(drawings: Sequence[Path | str], root: Path,
                      ctq_by_id: dict[str, dict[str, Any]],
                      issues: list[dict[str, Any]],
                      bom_id: str | None = None) -> tuple[list[dict[str, Any]],
                                                          list[dict[str, Any]],
                                                          list[str]]:
    """读每张图的证据 sidecar，产出 (文件引用, gdt 项, 修订号)。

    装配图单独判：C6 要的是「总装图 + 零件图」都在，而装配图特有的
    ``assembly_issues``（球标↔BOM 没闭合）必须影响就绪结论——一张漏了零件的
    装配图不能读成 ``ok: true``。行级事实覆盖（材料/工艺）随各自的引用带着
    （哪张图缺哪几行，逐图可查），总数由调用方现算，不在这里预聚合。
    """
    refs: list[dict[str, Any]] = []
    gdt: list[dict[str, Any]] = []
    revisions: list[str] = []
    for raw in drawings:
        path = Path(raw)
        if not path.is_file():
            _issue(issues, "drawing_missing", f"图纸文件不存在：{path}", blocking=True)
            continue
        sidecar = _evidence_path(path)
        if not sidecar.is_file():
            _issue(issues, "drawing_evidence_missing",
                   f"{path.name} 没有 {sidecar.name}，图纸内容无法核验", blocking=True)
            continue
        evidence = json.loads(sidecar.read_text(encoding="utf-8"))
        rel = path.relative_to(root).as_posix() if path.parent == root else str(path)
        kind = "assembly" if evidence.get("assembly") else "part"
        file_ref: dict[str, Any] = {"path": rel, "sha256": _sha256(path), "kind": kind}
        if kind == "assembly":
            file_ref["bom_line_coverage"] = _check_assembly(
                rel, evidence, bom_id, issues)
        refs.append(file_ref)
        revisions.append(str(evidence.get("revision", "")))
        for view in evidence.get("views", []):
            for dim in view.get("dimensions", []):
                tolerance = dim.get("tolerance")
                if not tolerance:
                    continue
                if dim.get("inherited_from"):
                    # 局部放大图上的尺寸是从母视图**继承**的同一处测量：同一处测量
                    # 印两处算一条覆盖，否则放大图画得越多 gdt 覆盖率越虚高。
                    continue
                # 尺寸证据里的 feature 自带视图前缀（F-DRAW-01 第 1 片定的口径）
                feature = str(dim.get("feature", ""))
                ref = dim.get("ctq_ref")
                if not ref:
                    _issue(issues, "tolerance_unlinked",
                           f"{feature} 标了公差但没有 ctq_ref，无法计入 gdt 覆盖",
                           blocking=False, feature=feature)
                    continue
                ctq = ctq_by_id.get(str(ref))
                if ctq is None:
                    _issue(issues, "unknown_ctq_ref",
                           f"{feature} 的 ctq_ref={ref!r} 在 Product Truth 里不存在"
                           f"（不做名字模糊匹配）", blocking=True, feature=feature)
                    continue
                verdict = _agrees_with_ctq(tolerance, float(dim["value"]), ctq)
                if verdict is False:
                    _issue(issues, "tolerance_mismatch",
                           f"{feature} 图纸标 ±{tolerance} 但 CTQ {ctq['feature']} 的限值"
                           f"是 [{ctq['lower_limit']}, {ctq['upper_limit']}]",
                           blocking=True, feature=feature)
                    continue
                if verdict is None:
                    _issue(issues, "ctq_limits_missing",
                           f"CTQ {ctq['feature']} 没写上下限，{feature} 的数值一致性"
                           f"不可核（按引用成立计入覆盖）", blocking=False)
                gdt.append({"feature": ctq["feature"], "drawing_feature": feature,
                            "ctq_record_id": str(ref), "covered_by": "dimension",
                            "drawing": rel, "sha256": refs[-1]["sha256"],
                            "tolerance": tolerance, "nominal": dim["value"]})
        # GD&T 框也算覆盖凭据：只声明形位、不声明尺寸公差的 CTQ，画上去的框就是它上图的证据。
        # 这一半只核「框真在图上 + 挂在实测特征上」，**不核形位偏差实测值**（本仓还不测形位偏差）。
        covered = {str(g["ctq_record_id"]) for g in gdt}
        exceeded = {str(i.get("feature") or ""): i
                    for i in (evidence.get("gdt_issues") or [])
                    if i.get("kind") == "position_deviation_exceeded"}
        for frame in evidence.get("gdt_frames") or []:
            ref = str(frame.get("ctq_ref") or "")
            feature = str(frame.get("feature") or "")
            if feature in exceeded:
                # 偏差超带的框不是覆盖凭据：那等于拿一条没达成的要求给自己盖章放行。
                one = exceeded[feature]
                where = f"（CTQ {one.get('ctq_ref')}）" if one.get("ctq_ref") else ""
                _issue(issues, "position_deviation_exceeded",
                       f"{feature} 的位置度实测偏差 {one.get('deviation_mm')} "
                       f"超出公差带 {one.get('zone')}{where}",
                       blocking=True, feature=feature)
                continue
            if not ref:
                _issue(issues, "frame_unlinked",
                       f"{feature} 画了形位框但没有 ctq_ref，无法计入 gdt 覆盖",
                       blocking=False, feature=feature)
                continue
            ctq = ctq_by_id.get(ref)
            if ctq is None:
                _issue(issues, "unknown_ctq_ref",
                       f"{feature} 的框 ctq_ref={ref!r} 在 Product Truth 里不存在"
                       f"（不做名字模糊匹配）", blocking=True, feature=feature)
                continue
            if ref in covered:
                continue      # 同一条需求已由尺寸覆盖，不重复计第二条
            covered.add(ref)
            gdt.append({"feature": ctq["feature"], "drawing_feature": feature,
                        "ctq_record_id": ref, "covered_by": "feature_control_frame",
                        # verified 说明这一条覆盖到的是什么程度：deviation = 真核过偏差，
                        # presence_only = 只证到「框画上去了且挂在实测特征上」。
                        "verified": frame.get("verified"),
                        "frame": frame.get("text"), "drawing": rel,
                        "sha256": refs[-1]["sha256"]})
    if not drawings:
        _issue(issues, "no_drawings", "没有传入任何图纸：图纸侧产不出 gdt，"
                                     "发布就绪不成立", blocking=True)
    return refs, gdt, revisions


def _collect_bom(db_path: Path, tenant_id: str, project_id: str, bom_id: str | None,
                 issues: list[dict[str, Any]]) -> dict[str, Any]:
    from aipd_os.bom.store import BomStore, bom_store_path

    # BOM 走独立库（产品口径：不给权威状态库加表，状态库迁移已冻结）。
    # 库不在就明说「不在」：BomStore() 会建库建表，凭空造一个空 BOM 会被读成
    # 「接上了但没有行」，那是另一种假装完整。
    bom_db = bom_store_path(db_path)
    if not bom_db.is_file():
        _issue(issues, "bom_db_missing",
               f"BOM 库不存在：{bom_db}（--db 是状态库，BOM 取同目录的 bom.db）",
               blocking=True)
        return {}
    store = BomStore(bom_db)
    fields: dict[str, Any] = {}
    lines = store.list_lines(tenant_id, project_id, bom_id)
    if not lines:
        _issue(issues, "no_bom_lines",
               f"BOM 里没有行（bom_id={bom_id or '全部'}），计数一致性无从谈起", blocking=True)
        return fields
    fields["bom_line_count"] = len(lines)
    if bom_id is None:
        _issue(issues, "bom_not_bound",
               "未指定 --bom，bom_version 取不到唯一来源，本轮不写该字段", blocking=False)
        return fields
    header = store.get_bom(tenant_id, project_id, bom_id)
    if header is None:
        _issue(issues, "bom_missing", f"bom {bom_id!r} 不存在", blocking=True)
        return fields
    fields["bom_version"] = header.revision
    return fields


def _model_fields(model: Path | str | None, issues: list[dict[str, Any]]) -> dict[str, Any]:
    """模型侧只有真给了文件才产字段；没给就留 source 说明，不编数。"""
    if model is None:
        return {"model_version": {"source": "not_given"}}
    path = Path(model)
    if not path.is_file():
        _issue(issues, "model_missing", f"模型文件不存在：{path}", blocking=True)
        return {"model_version": {"source": "missing"}}
    out: dict[str, Any] = {"model_version": {"source": "content_sha256",
                                             "value": _sha256(path)[:12]}}
    try:
        if path.suffix.lower() != ".step":
            raise ValueError("目前只支持从 STEP 数实体（原生源需执行其构建脚本，未做）")
        import cadquery as cq

        # 实测：``importStep().val()`` 返回的是 cadquery 的 Solid 包装而不是
        # TopoDS_Shape，直接喂给 TopExp_Explorer 会 TypeError；用 cq 自己的选择器数。
        imported = cq.importers.importStep(str(path))
        out["model_part_count"] = imported.solids().size()
    except Exception as exc:  # 读不动模型不等于 0 个零件
        _issue(issues, "model_unreadable",
               f"{path.name}: {type(exc).__name__}: {exc}；不折算成 part 数", blocking=False)
    return out


def _collect_steps(steps_doc: Path | str | None, root: Path,
                   issues: list[dict[str, Any]]) -> dict[str, Any]:
    """读装配步骤文档的 sidecar，产出 C6 的 ``assembly_instructions`` 那一格。

    这一格在门里是 ``FILE_KEYS``（脚本 ``production_release_gate.py``）：值必须是一个
    真存在、哈希对得上的文件。所以**没交文档就不写这一格**——写一个空对象或
    ``step_count: 0`` 会让门把「没做」读成「做了但没内容」。
    """
    if steps_doc is None:
        return {}
    path = Path(steps_doc)
    if not path.is_file():
        _issue(issues, "steps_missing", f"装配步骤文档不存在：{path}", blocking=True)
        return {}
    rel = path.relative_to(root).as_posix() if path.parent == root else str(path)
    ref = {"path": rel, "sha256": _sha256(path)}
    sidecar = path.with_suffix(".evidence.json")
    if not sidecar.is_file():
        _issue(issues, "steps_evidence_missing",
               f"{path.name} 没有 {sidecar.name}，装配步骤内容无法核验", blocking=True)
        return {"assembly_instructions": ref}
    evidence = json.loads(sidecar.read_text(encoding="utf-8"))
    body = evidence.get("assembly_steps") or {}
    if "step_count" not in body:
        _issue(issues, "steps_evidence_incomplete",
               f"{sidecar.name} 里没有 assembly_steps.step_count：这一格读不出内容，"
               "不折成 0 步的文档", blocking=True)
        return {"assembly_instructions": ref}
    coverage = body.get("balloon_coverage") or {}
    unreferenced = sorted(int(b) for b in coverage.get("unreferenced") or [])
    doc_issues = list(evidence.get("assembly_step_issues") or [])
    if unreferenced:
        _issue(issues, "steps_balloons_uncovered",
               f"{rel}：球标 {unreferenced} 没有任何装配步骤引用——装配图编了号、"
               "说明书里没人装这一件", blocking=True)
    elif doc_issues:
        _issue(issues, "steps_not_closed",
               f"{rel}：装配步骤文档带着 {len(doc_issues)} 条未收口"
               "（BOM 绑定或步骤闭合），就绪判定不替它盖住", blocking=True)
    return {"assembly_instructions": ref,
            "assembly_steps": {
                "step_count": int(body["step_count"]),
                "declared_balloons": len(coverage.get("declared") or []),
                "unreferenced": unreferenced,
                "not_covered": list(evidence.get("not_covered") or []),
                "evidence": {"path": (sidecar.relative_to(root).as_posix()
                                      if sidecar.parent == root else str(sidecar)),
                             "sha256": _sha256(sidecar)}}}


def _collect_dfm(dfm_doc: Path | str | None, root: Path,
                 issues: list[dict[str, Any]]) -> dict[str, Any]:
    """读 DFM/DFA 分析报告的 sidecar，产出 C5/C6 的 ``dfm_dfa`` 那一格。

    分三档处置，**不合成一个数**：``hold``（深孔超上限、公差超出常规可达）阻断就绪——
    这些不是「图纸写紧一点」能自己解决的，要制造方确认；``flag``（薄壁告警）只提示；
    一条都没判成（全是盲区）也提示，但字段里带着 `measured_rule_count: 0`，
    读者不会把空分析读成「没有 DFM 问题」。
    """
    if dfm_doc is None:
        return {}
    path = Path(dfm_doc)
    if not path.is_file():
        _issue(issues, "dfm_missing", f"DFM/DFA 分析报告不存在：{path}", blocking=True)
        return {}
    rel = path.relative_to(root).as_posix() if path.parent == root else str(path)
    ref = {"path": rel, "sha256": _sha256(path)}
    sidecar = path.with_suffix(".evidence.json")
    if not sidecar.is_file():
        _issue(issues, "dfm_evidence_missing",
               f"{path.name} 没有 {sidecar.name}，分析结论无法核验", blocking=True)
        return {"dfm_dfa": ref}
    evidence = json.loads(sidecar.read_text(encoding="utf-8"))
    counts = evidence.get("counts") or {}
    holds = [f for f in evidence.get("findings") or [] if f.get("verdict") == "hold"]
    advisories = [f for f in evidence.get("findings") or [] if f.get("verdict") == "flag"]
    measured = int(counts.get("measured") or 0)
    if holds:
        _issue(issues, "dfm_hold_findings",
               f"{rel}：{len(holds)} 条需制造方确认（"
               + "、".join(sorted(str(h.get("rule")) for h in holds))
               + "）——这类问题不由发布文档代为点头", blocking=True)
    if advisories:
        _issue(issues, "dfm_advisory_findings",
               f"{rel}：{len(advisories)} 条告警（"
               + "、".join(sorted(str(a.get("rule")) for a in advisories))
               + "）；告警不阻断就绪，但也不会被抹掉", blocking=False)
    if measured == 0:
        _issue(issues, "dfm_unmeasured",
               f"{rel}：一条规则都没判成（全在盲区）。这份分析不能读成「没有 DFM 问题」",
               blocking=False)
    return {"dfm_dfa": ref,
            "dfm_summary": {
                "hold_count": len(holds), "advisory_count": len(advisories),
                "blind_rule_count": int(counts.get("blind") or 0),
                "measured_rule_count": measured,
                "material_class": evidence.get("material_class"),
                "not_covered": list(evidence.get("not_covered") or []),
                "evidence": {"path": (sidecar.relative_to(root).as_posix()
                                      if sidecar.parent == root else str(sidecar)),
                             "sha256": _sha256(sidecar)}}}


def build_release_manifest(*, db_path: Path | str, tenant_id: str = DEFAULT_TENANT,
                           project_id: str = DEFAULT_TENANT,
                           drawings: Sequence[Path | str] = (),
                           bom_id: str | None = None, model: Path | str | None = None,
                           steps_doc: Path | str | None = None,
                           dfm_doc: Path | str | None = None,
                           units: str = "mm", datum_scheme: str = "unspecified",
                           approval_status: str = "unapproved",
                           out_path: Path | str | None = None,
                           now: datetime | None = None) -> dict[str, Any]:
    """装配门禁可消费的发布就绪证据文档；返回同一份文档并附生产者判定。

    ``ok`` 只由「阻断类问题」决定，不看门禁脸色——文档写什么，磁盘上就是什么。
    """
    db = Path(db_path)
    root = Path(out_path).parent if out_path else db.parent
    issues: list[dict[str, Any]] = []

    from aipd_os.product_truth.store import ProductTruthStore

    truth = ProductTruthStore(str(db), tenant_id=tenant_id, project_id=project_id)
    ctq_by_id = _collect_ctq(truth, issues)
    refs, gdt, revisions = _collect_drawings(list(drawings), root, ctq_by_id, issues,
                                             bom_id=bom_id)
    doc: dict[str, Any] = {
        "runtime": "native_brep" if importlib.util.find_spec("cadquery") else "faceted_brep",
        "units": units,
        "datum_scheme": datum_scheme,
        "approval_status": approval_status,
        "timestamp": (now or datetime.now(timezone.utc)).isoformat().replace("+00:00", "Z"),
        "ctq": list(ctq_by_id.values()),
        "gdt": gdt,
        "drawing_count": len(refs),
        # C6 的「总装图 + 零件图」是两种东西，只报一个总数就读不出缺哪一类。
        # drawing_count 的既有含义不变（总数），这两条是新增的细分。
        "assembly_drawing_count": sum(1 for r in refs if r["kind"] == "assembly"),
        "part_drawing_count": sum(1 for r in refs if r["kind"] == "part"),
    }
    doc.update(_collect_bom(db, tenant_id, project_id, bom_id, issues))
    # 行级事实覆盖（材料 + 工艺）：只聚合**数得清**的几项。哪几个球标缺什么留在各自图纸的
    # 引用里——多张装配图的球标都从 1 开始编号，拍平成一份清单就分不清 2 号是谁家的 2 号。
    coverages = [r["bom_line_coverage"] for r in refs if "bom_line_coverage" in r]
    if coverages:
        doc["bom_line_coverage"] = {
            "bound_rows": sum(int(c["bound_rows"]) for c in coverages),
            "with_material": sum(int(c["with_material"]) for c in coverages),
            "with_process": sum(int(c["with_process"]) for c in coverages),
            "unbound_rows": sum(int(c["unbound_rows"]) for c in coverages),
            "drawings_without_bom": sum(int(c["drawings_without_bom"]) for c in coverages),
            "missing_material_drawings": sum(1 for c in coverages if c["missing_material"]),
            "missing_process_drawings": sum(1 for c in coverages if c["missing_process"]),
            "missing_detail": "evidence.drawings[].bom_line_coverage"
                              ".missing_material / .missing_process",
        }
    doc.update(_collect_steps(steps_doc, root, issues))
    doc.update(_collect_dfm(dfm_doc, root, issues))
    model_fields = _model_fields(model, issues)
    if "model_part_count" in model_fields:
        doc["model_part_count"] = model_fields["model_part_count"]
    if "value" in model_fields["model_version"]:
        doc["model_version"] = model_fields["model_version"]["value"]
    if revisions:
        doc["drawings_version"] = revisions[0]
        if len(set(revisions)) > 1:
            _issue(issues, "drawing_revision_split",
                   f"多张图修订不一致：{sorted(set(revisions))}", blocking=True)
    if "bom_version" in doc and "drawings_version" in doc \
            and doc["bom_version"] != doc["drawings_version"]:
        _issue(issues, "version_split",
               f"bom_version={doc.get('bom_version')} vs "
               f"drawings_version={doc.get('drawings_version')}（不代为对齐）",
               blocking=False)

    versions = {k: doc[k] for k in ("model_version", "bom_version", "drawings_version")
                if k in doc}
    doc["producer"] = {
        "model_version": model_fields["model_version"],
        "version_parity": {"values": versions,
                           "consistent": len(set(map(str, versions.values()))) <= 1
                           and len(versions) >= 2},
        "drawings_referenced": len(refs),
    }
    doc["evidence"] = {"drawings": refs,
                       "ctq_source": "product_truth",
                       "gdt_source": "drawing_evidence"}
    blocking = any(i["blocking"] for i in issues)
    doc["issues"] = issues
    doc["blocking"] = blocking
    doc["ok"] = not blocking

    if out_path:
        target = Path(out_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")
        doc["manifest_path"] = str(target)
    return doc
