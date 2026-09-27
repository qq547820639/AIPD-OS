"""装配步骤文档：把「先装谁、后装谁」交成一份可核验的产物（capability
``cad.assembly_instructions``，对应 C6 的「装配/维护」里**装配**那一半）。

三条硬规矩，都能机器核：

1. **顺序是作者声明的，不是算出来的。** 步骤号（``no``）与它引用哪些球标（``balloons``）
   都在装配清单里写；缺号、重号、断档、引用没声明过的球标一律 ``ValueError``。
   本模块不按遍历顺序代发编号，也不补断档——印出 1、2、4 的文档是在操作者面前
   把第 3 步抹掉，而"从爆炸位移/装配约束反推顺序"需要约束数据与实体求交两样前提，
   本仓都没有（见 ``assembly.py`` 的裁决），硬推等于交一份没证过的顺序。
2. **步骤只认球标，不认名字。** 一步引用哪些零件，靠的是 ``assembly.py`` 那套
   作者声明的 ``balloon``；数量/单位/材料/工艺仍旧只来自绑上的 BOM 行（``bind_bom``），
   绑不上留空，不写占位符也不折算成 0。
3. **这份骨架不承载什么，文档自己要说。** 工时、工序成本、扭矩、维护指引都不建模，
   证据里 ``not_covered`` 逐条列出。清单里写 ``torque`` 一类字段会被**拒**而不是被丢——
   静默丢掉作者写过的东西，产出的就是一份自称完整、其实少了格子的文档。

为什么不做成工序路线（operations/routing）：那是第 16 片已经裁决过、并在
``bom/models.py`` 与 ``assembly.py`` 里写明「本仓不建」的对象——成熟实现把每道工序
做成独立记录（本机读取 Odoo ``addons/mrp/models/mrp_routing.py``，commit f254c797：
``mrp.routing.workcenter`` 带必填 ``workcenter_id``、``sequence``、工时与成本算式、
``blocked_by_operation_ids`` 依赖图与环检测）。本模块只交**文档**：步骤是文档正文里的
序号（打印给人读），不是可排产、可核算的工作中心记录。两者的区别也解释了为什么这里
要求序号连续——``sequence`` 是内部排序键（Odoo 默认 100、允许留空档插队），
而印出来的「步骤 N」是受控文件的一部分，断档就是缺页。

为什么不是生成式装配说明：GitHub 检索到的同类开源实现
（``Ayaan577/Assembly_Instruction_Generation-IITK``，本机读取其 README 与仓库根目录
清单）是 T5 seq2seq 从 BoM 生成自然语言步骤，**根目录没有 LICENSE 文件**、权重放在
一个 83 字节的 Google Drive 链接文件里、只有硬编码路径的 notebook。不可复现的输出
不能进发布证据链，无许可证也不能复用——这里借的是它「步骤从物料结构长出来」的形态，
把结构换成作者声明。S1000D 那种「步骤 + 图上件号 callout」的程序化结构本模块**没有**
按其 XML 实现：本机只取到一份中文导读（不含 FWA/CTA 细节），其「标准可在 s1000d.org
免费下载」的说法未能验证（该站点抓取失败）。

版式用 Markdown + ``.evidence.json`` sidecar，不用 PDF/docx：reportlab 5.0.0 本机实测
能用 ``STSong-Light`` 出中文（2374 字节 PDF），所以 PDF 不是不能做，是**本轮不做**
（要再加一套排版与分页判据）；``python-docx`` 未安装，且本仓契约把 .docx 当外部输入
拒绝（``supply_chain/lab.py``）。Markdown 能被逐字断言、能被门哈希，就够 C6 这一项了。

明确**未实现**：维护指引（要属主给内容）、工时/工序成本、扭矩值、按检验项逐点检的
检验步骤、PDF 版式。
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STEP_KEYS = ("no", "action", "balloons")

# 顺序与措辞都是常驻用例钉住的（tests/test_cad_assembly_steps.py）。
NOT_COVERED = ["维护指引", "工时与工序成本", "扭矩或拧紧值", "PDF/图框版式"]

_VALUE_COLUMNS = ["QTY", "UNIT", "MATERIAL", "PROCESS"]


def parse_assembly_steps(path: str | Path) -> list[dict[str, Any]]:
    """读装配清单里作者声明的步骤序列；**不合规一律抛错**，不补号、不猜引用。

    ``{"assembly_steps": [{"no": 1, "action": "支架贴合基面", "balloons": [1]}]}``。
    球标是否真的存在由 ``parse_assembly_manifest`` 那一份校验说了算（同一个文件、
    同一个判据），这里只把步骤引用逐个对回去。
    """
    from aipd_os.cad.assembly import parse_assembly_manifest

    file = Path(path)
    parts = parse_assembly_manifest(file)          # 零件侧的全部前置校验
    declared = {int(one["balloon"]) for one in parts}
    names = {int(one["balloon"]): str(one["name"]) for one in parts}
    data = json.loads(file.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "assembly_steps" not in data:
        raise ValueError('装配清单里没有 "assembly_steps" 那一段：步骤顺序由作者声明，'
                         "本模块不从爆炸位移或遍历顺序反推")
    raw_steps = data["assembly_steps"]
    if not isinstance(raw_steps, list):
        raise ValueError(f'assembly_steps 必须是步骤列表，实得 {type(raw_steps).__name__}')
    if not raw_steps:
        raise ValueError("assembly_steps 一个步骤都没有：没有步骤的装配步骤文档不是交付物")

    out: list[dict[str, Any]] = []
    seen_no: set[int] = set()
    for idx, raw in enumerate(raw_steps):
        if not isinstance(raw, dict):
            raise ValueError(f"assembly_steps 每一项都得是对象，第 {idx + 1} 项实得 {raw!r}")
        _reject_unknown(raw, idx)
        number = _step_no(raw, idx)
        if number in seen_no:
            raise ValueError(f"步骤号重复：{number}；两个步骤不能共用一个序号，"
                             f"文档会印出两个「步骤 {number}」")
        seen_no.add(number)
        action = str(raw.get("action") or "").strip()
        if not action:
            raise ValueError(f"步骤 {number} 没写 action（这一步做什么，作者的原话）："
                             "本模块不代拟动作描述")
        balloons = _balloons(raw, number, declared, names)
        out.append({"no": number, "action": action, "balloons": balloons})

    ordered = sorted(out, key=lambda s: s["no"])
    _require_consecutive(ordered)
    return ordered


def _reject_unknown(raw: dict[str, Any], idx: int) -> None:
    """清单里写了本模块不承载的字段 ⇒ 拒绝，不静默丢。

    丢掉作者写过的扭矩/工时，产出的文档就少了一格而**照样自称完整**——
    那比报错糟得多：报错会逼作者把值写进 ``action`` 原文，或先建本仓还没有的对象。
    """
    extra = sorted(k for k in raw if k not in STEP_KEYS)
    if extra:
        raise ValueError(
            f"第 {idx + 1} 步写了本模块不承载的字段：{extra}；"
            f"可声明的只有 {list(STEP_KEYS)}。要表达这些事实请先写进 action 原文"
            "（或先建 operations/扭矩表——见模块 docstring 的裁决）")


def _step_no(raw: dict[str, Any], idx: int) -> int:
    if "no" not in raw:
        raise ValueError(f"第 {idx + 1} 步没写步骤号（no）：步骤号由作者声明，"
                         "本模块不按遍历顺序代发")
    number = raw["no"]
    if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
        raise ValueError(f"步骤号必须是正整数（文档里印出的「步骤 N」），实得 {number!r}")
    return int(number)


def _balloons(raw: dict[str, Any], number: int, declared: set[int],
              names: dict[int, str]) -> list[int]:
    value = raw.get("balloons")
    if not isinstance(value, list) or not value:
        raise ValueError(f"步骤 {number} 没引用任何球标：这一步装哪些零件由你说，"
                         f"实得 {value!r}")
    got: list[int] = []
    for one in value:
        if isinstance(one, bool) or not isinstance(one, int) or one <= 0:
            raise ValueError(f"步骤 {number} 的 balloons 每项都得是正整数球标号，实得 {one!r}")
        if one in got:
            raise ValueError(f"步骤 {number} 的 balloons 里球标 {one} 重复："
                             "同步重复一次会让读者以为要装两件")
        if one not in declared:
            raise ValueError(f"步骤 {number} 引用了球标 {one}，装配清单里没声明过这个号："
                             "文档不能指着图纸上不存在的零件")
        got.append(int(one))
    return sorted(got)


def _require_consecutive(steps: list[dict[str, Any]]) -> None:
    printed = [s["no"] for s in steps]
    gaps = sorted({n for n in range(1, max(printed) + 1)} - set(printed))
    if gaps:
        raise ValueError(
            f"步骤号断档：{'、'.join(str(g) for g in gaps)} 没有对应步骤。"
            "印出来的序号必须 1..N 连续——断档等于在操作者面前把那一页抹掉。"
            "要删步骤就重排后面的号（这一步本模块不做，因为顺序是作者的声明）")


def build_step_plan(parts: Sequence[dict[str, Any]], steps: Sequence[dict[str, Any]],
                    rows: Sequence[dict[str, Any]] | None) -> dict[str, Any]:
    """把声明的步骤与图纸球标做双向闭合，并准备明细表要的那张表。

    两头都核（与 ``bind_bom`` 同一纪律）：步骤引用没声明的号在 ``parse_assembly_steps``
    就拒绝；反过来**球标有号而没有任何步骤装配它**不报错——文档照样能出，但记进
    ``issues``，读的人知道这一件在这份说明书里没人装。
    ``rows`` 是 ``bind_bom`` 的结果（或没接 BOM 时 ``parts_list_rows`` 的两列行）。
    """
    by_balloon = {int(one["balloon"]): str(one["name"]) for one in parts}
    named_rows = {int(r["item"]): r for r in (rows or [])}
    referenced: list[int] = []
    rendered: list[dict[str, Any]] = []
    for step in steps:
        cited = [{"balloon": b, "part": by_balloon.get(b, f"球标 {b}（清单里没有）")}
                 for b in step["balloons"]]
        rendered.append({"no": step["no"], "action": step["action"],
                         "balloons": list(step["balloons"]), "cited": cited})
        for b in step["balloons"]:
            if b not in referenced:
                referenced.append(b)

    declared = sorted(int(one["balloon"]) for one in parts)
    unreferenced = [b for b in declared if b not in set(referenced)]
    issues = [f"球标 {b}（{named_rows.get(b, {}).get('part', by_balloon.get(b, ''))}）"
              f"没有任何步骤装配它：这份文档交出去，操作者不会装这一件"
              for b in unreferenced]
    return {"steps": rendered,
            "balloon_coverage": {"declared": declared, "referenced": sorted(referenced),
                                 "unreferenced": unreferenced},
            "issues": issues}


def _markdown(part_name: str, revision: str, manifest: Path, table: list[list[str]],
              columns: list[str], plan: dict[str, Any], bound: bool) -> str:
    lines = [f"# 装配步骤：{part_name}（Rev {revision}）", "",
             f"来源：装配清单 `{manifest}`——步骤顺序与各步引用哪些球标都在清单里声明，"
             "本文档不发明顺序、不改写动作原文。", "",
             "零件清单：", "",
             "| " + " | ".join(columns) + " |",
             "|" + "|".join(["---"] * len(columns)) + "|"]
    for row in table:
        lines.append("| " + " | ".join(row) + " |")
    for step in plan["steps"]:
        lines += ["", f"## 步骤 {step['no']}：{step['action']}",
                  "- 引用球标：" + "、".join(
                      f"{c['balloon']}（{c['part']}）" for c in step["cited"])]
    if plan["issues"]:
        lines += ["", "## 未收口"] + [f"- {msg}" for msg in plan["issues"]]
    lines += ["", "## 本文档不承载", ""]
    if not bound:
        lines.append("- 没有接 BOM 权威，零件清单只有 ITEM/PART 两列（数量/单位/材料/工艺"
                     "都不印；印空列会被读成「有这一格但没填」）")
    lines += [f"- {item}" for item in NOT_COVERED]
    lines.append("")
    return "\n".join(lines)


def generate_assembly_steps(out_path: Path | str, *, manifest: str, part_name: str,
                            revision: str = "A",
                            bom_lines: Sequence[Any] | None = None,
                            provenance: dict[str, Any] | None = None,
                            pdf_path: Path | str | None = None) -> dict[str, Any]:
    """端到端出装配步骤文档：清单 -> 声明校验 -> Markdown -> ``.evidence.json``。

    这里**不做投影**（不需要几何），所以不 import CadQuery；STEP 文件存在性照样由
    ``parse_assembly_manifest`` 校验——步骤引用的零件连模型都不存在，文档就是空话。
    明细表那一路与装配图共用 ``bind_bom``：数量的权威永远在 BOM 行上。
    """
    from aipd_os.cad.assembly import (
        bind_bom,
        parse_assembly_manifest,
        parts_list_rows,
    )

    path = Path(out_path)
    man = Path(manifest)
    parts = parse_assembly_manifest(man)
    steps = parse_assembly_steps(man)

    binding_issues: list[str] = []
    bom_evidence: dict[str, Any] | None = None
    if bom_lines is None:
        rows = parts_list_rows(parts)
        columns = ["ITEM", "PART"]
    else:
        rows, binding_issues = bind_bom(parts, list(bom_lines))
        columns = ["ITEM", "PART"] + _VALUE_COLUMNS
        bom_ids = sorted({str(line.bom_id) for line in bom_lines})
        bom_evidence = {"bom_id": bom_ids[0] if len(bom_ids) == 1 else None,
                        "bom_ids": bom_ids, "lines": len(bom_lines)}

    table = []
    for row in rows:
        cells = [str(row["item"]), str(row["part"])]
        if bom_evidence is not None:
            cells += ["" if row.get("qty") is None else f"{row['qty']:g}",
                      row.get("unit") or "", row.get("material") or "",
                      row.get("process") or ""]
        table.append(cells)

    plan = build_step_plan(parts, steps, rows)
    text = _markdown(part_name, revision, man, table, columns, plan,
                     bound=bom_evidence is not None)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

    if pdf_path is not None:
        # 同一份投影：零件行 / 列名 / 步骤计划都直接传过去，PDF 那边不再解析一遍清单
        from aipd_os.cad.assembly_steps_pdf import render_assembly_steps_pdf

        pdf = render_assembly_steps_pdf(
            pdf_path, part_name=part_name, revision=revision, manifest=str(man),
            columns=columns, table=table,
            plan={**plan, "not_covered": list(NOT_COVERED)},
            bound=bom_evidence is not None)
    else:
        pdf = None

    evidence: dict[str, Any] = {
        "document": "assembly_steps",
        "manifest": str(man),
        "manifest_sha256": hashlib.sha256(man.read_bytes()).hexdigest(),
        "document_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "columns": columns,
        "steps": plan["steps"],
        "assembly_steps": {"step_count": len(plan["steps"]),
                           "balloon_coverage": plan["balloon_coverage"]},
        # 绑定问题与步骤闭合问题分开记：来源不同（BOM 那一侧没对上 / 图纸有号没人装），
        # 处置也不同（前者补 bom_item，后者补步骤声明）
        "assembly_step_issues": sorted(set(plan["issues"]) | set(binding_issues)),
        "parts_list": rows,
        "bom": bom_evidence,
        "not_covered": list(NOT_COVERED),
        # PDF 不在时写 None 而不是省略这个键：读者/程序能区分"没要"与"要了但没生成"
        "pdf": pdf,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    evidence.update(provenance or {})
    # 不复用 drawings2d._finish_evidence：那条收尾会盖 hidden_line_method——
    # 隐藏线求法是图纸的事实，写进步骤文档的证据里就是给读者一个不相干的字段
    from aipd_os.cad.evidence import sidecar_path

    sidecar = sidecar_path(path)
    sidecar.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
    evidence["evidence_file"] = str(sidecar)
    return evidence
