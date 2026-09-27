"""装配步骤文档的 PDF 版式（F-ASSEMBLY-PDF，第 80 片）。

第 56 片交付装配步骤时留的原话是"版式只有 Markdown，PDF/图框未做
（reportlab 5.0.0 出中文本机实测可用，是本轮不排而非排不出）"。
这一片把它排上：A4 矢量 PDF + 图框（标题栏），中文用 reportlab 内置 CID 字体
`STSong-Light`——**不需要字体文件**，且文字是**可抽取的**（实测 pypdf 能读回
"安装支架并使用扭力扳手拧紧至 12 N·m"），所以验收可以拿独立解码器核，而不是只看文件存在。

与手册那条路（`layout/composer.compose_pdf`）刻意不同：那条是把逐页 PNG 拼成 PDF，
文字在图里、抽不出来；这里要的是可检索、可复制、能进打印流程的作业文件。

投影只有一份：零件行、列名、步骤计划全部由 `generate_assembly_steps` 传进来，
本模块**不重新解析清单**——两边各写一遍时，"Markdown 里有这一步而 PDF 里没有"
那种错谁都不会红（第 52/53 片同一格）。
"""
from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

FONT = "STSong-Light"
MARGIN = 18 * mm
LINE_H = 6.2 * mm

__all__ = ["FONT", "render_assembly_steps_pdf", "wrap_cjk"]


def _ensure_font() -> None:
    if FONT not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont(FONT))


def wrap_cjk(text: str, max_units: float) -> list[str]:
    """按字符串宽度折行（中日韩混排也适用：宽度用 reportlab 的量法，不是数字符）。"""
    width = pdfmetrics.stringWidth
    out: list[str] = []
    cur = ""
    for ch in text:
        probe = cur + ch
        if cur and width(probe, FONT, 10) > max_units:
            out.append(cur)
            cur = ch
        else:
            cur = probe
    if cur.strip():
        out.append(cur)
    return out or [""]


def _frame(c: Any, page_no: int, part_name: str, revision: str) -> tuple[float, float]:
    """画图框 + 标题栏，返回正文可用区顶端 y。"""
    w, h = A4
    c.saveState()
    c.setLineWidth(0.9)
    c.rect(MARGIN, MARGIN, w - 2 * MARGIN, h - 2 * MARGIN)
    c.setLineWidth(0.4)
    block_h = 26 * mm
    c.rect(MARGIN, MARGIN, w - 2 * MARGIN, block_h)
    top = h - MARGIN - block_h - LINE_H
    c.line(MARGIN, top + block_h * 0.5, MARGIN + 60 * mm, top + block_h * 0.5)
    c.setFont(FONT, 9)
    left = MARGIN + 4 * mm
    c.drawString(left, top + block_h - 5 * mm, f"装配作业指导书  {part_name}  Rev {revision}")
    c.drawString(left, top + block_h * 0.5 - 5 * mm, "本文档不承载：工时、扭矩值、检验点、维护指引")
    c.drawRightString(w - MARGIN - 4 * mm, top + block_h - 5 * mm, f"第 {page_no} 页")
    c.restoreState()
    return top - LINE_H


def render_assembly_steps_pdf(out_pdf: Path | str, *, part_name: str, revision: str,
                              manifest: str, columns: Sequence[str],
                              table: Sequence[Sequence[str]],
                              plan: dict[str, Any],
                              bound: bool) -> dict[str, Any]:
    """把已经算好的文档模型排成 A4 PDF；返回 ``{path, sha256, pages, chars}``。"""
    _ensure_font()
    path = Path(out_pdf)
    path.parent.mkdir(parents=True, exist_ok=True)
    w, h = A4
    text_w = w - 2 * MARGIN - 6 * mm
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setTitle(f"装配步骤 {part_name} Rev {revision}")
    pages = 0
    written = 0
    y = _frame(c, (pages := pages + 1), part_name, revision)

    def new_page() -> None:
        nonlocal y, pages
        c.showPage()
        y = _frame(c, (pages := pages + 1), part_name, revision)

    def line(text: str, size: float = 10, bold_gap: float = 0.0) -> None:
        nonlocal y, written
        for ln in wrap_cjk(text, text_w):
            if y < MARGIN + 30 * mm:
                new_page()
            c.setFont(FONT, size)
            c.drawString(MARGIN + 3 * mm, y, ln)
            written += len(ln)
            y -= LINE_H + bold_gap

    line(f"装配步骤：{part_name}（Rev {revision}）", 14, 1.2 * mm)
    line(f"来源：装配清单 {manifest}；步骤顺序与各步引用哪些球标都在清单里声明，本文档不发明顺序。")
    line("")
    line("零件清单：" + ("" if bound else "（未接 BOM 权威，只有 ITEM/PART 两列）"))
    line(" | ".join(str(col) for col in columns))
    for row in table:
        line(" | ".join(str(cell) for cell in row))
    for step in plan.get("steps", []):
        line("")
        cited = "、".join(f"{c['balloon']}（{c['part']}）" for c in step.get("cited", []))
        line(f"步骤 {step['no']}：{step['action']}", 12, 0.8 * mm)
        line(f"引用球标：{cited or '（无）'}")
    if plan.get("issues"):
        line("")
        line("未收口：")
        for msg in plan["issues"]:
            line(f"- {msg}")
    line("")
    line("本文档不承载：")
    for item in plan.get("not_covered", []):
        line(f"- {item}")
    c.showPage()
    c.save()
    raw = path.read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
            "pages": pages, "chars": written}
