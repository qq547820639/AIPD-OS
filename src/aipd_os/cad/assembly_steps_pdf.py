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

第 81 片加的是**图片层**（`draw_image`）：排的是作者提供的装配示意图。本仓没有
STEP → 栅格那条路（`cad/assembly.py` 只出 STEP，`layout/renderer.py` 的 PNG 是给手册
页面的），也没有约束与碰撞数据去证成一张自动生成的爆炸图，所以既不猜图也不画一张
没证过的示意图；没给图时由文档自己写明"本档没有装配示意图"，而不是留一张空白占位图。
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
# reportlab 没有类型存根，`mm` 在类型层面是未知的量：这两处常量按它们真正的
# 运行时类型（点浮点数）标出来，否则排版算式一路是 Any，返回值那道检查就形同虚设。
LINE_H: float = 6.2 * mm
IMAGE_CAPTION = "装配示意图（由作者提供）"

__all__ = ["FONT", "IMAGE_CAPTION", "read_image_size", "render_assembly_steps_pdf", "wrap_cjk"]


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


def _frame(c: Any, page_no: int, part_name: str, revision: str,
           not_covered: Sequence[str]) -> float:
    """画图框 + 标题栏，返回正文可用区顶端 y。

    标题栏那句"本文档不承载"读的是调用方传进来的同一份 ``not_covered``：原先这里
    自己写了一句"工时、扭矩值、检验点、维护指引"，与正文那份清单是两条各写一遍的事实，
    第 80 片之后就读成两个互不相符的边界声明了。
    """
    w, h = A4
    c.saveState()
    c.setLineWidth(0.9)
    c.rect(MARGIN, MARGIN, w - 2 * MARGIN, h - 2 * MARGIN)
    c.setLineWidth(0.4)
    block_h = 26 * mm
    c.rect(MARGIN, MARGIN, w - 2 * MARGIN, block_h)
    # `A4` 来自没有类型存根的 reportlab，这条算式在类型层面是 Any；按它落地的单位（pt）
    # 标成 float，`_frame` 才不是"宣称返回 float、实际回 Any"。
    top: float = h - MARGIN - block_h - LINE_H
    c.line(MARGIN, top + block_h * 0.5, w - MARGIN, top + block_h * 0.5)
    c.setFont(FONT, 9)
    left = MARGIN + 4 * mm
    c.drawString(left, top + block_h - 5 * mm, f"装配作业指导书  {part_name}  Rev {revision}")
    c.drawString(left, top + block_h * 0.5 - 5 * mm,
                 "本文档不承载：" + "、".join(not_covered))
    c.drawRightString(w - MARGIN - 4 * mm, top + block_h - 5 * mm, f"第 {page_no} 页")
    c.restoreState()
    return top - LINE_H


def read_image_size(path: Path | str) -> tuple[int, int]:
    """量一张要排进 PDF 的图；读不出格式或被截断就抛 ``ValueError``。

    这一格不是防御性包装，是本轮自己欠的：原先只有"文件在不在"这道前置检查，
    内容坏（文本冒充 .png、零字节、截断）要到排版时 ``Image.open`` 才炸
    ``PIL.UnidentifiedImageError``——那时 Markdown 已经落盘、PDF 还没写、侧车没写，
    而 CLI 只接 ``ValueError``，于是用户看到一段 traceback 加一个孤儿 .md。
    `verify()` 走的是格式识别与 chunk 完整性，不解码像素，所以量大也不贵。
    """
    from PIL import Image, UnidentifiedImageError

    p = Path(path)
    try:
        with Image.open(p) as im:
            im.verify()
        with Image.open(p) as im:
            return int(im.size[0]), int(im.size[1])
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        # DecompressionBombError 既不是 OSError 也不是 UnidentifiedImageError（它直接继承
        # Exception），PIL 的默认上限是 89,478,485 像素 —— 不接这一支，超大图会绕过
        # CLI 的 `except ValueError` 变成 traceback。
        raise ValueError(
            f"--draw-image 的文件不是可读图片：{p}"
            f"（{type(exc).__name__}: {exc}）") from exc


def render_assembly_steps_pdf(out_pdf: Path | str, *, part_name: str, revision: str,
                              manifest: str, columns: Sequence[str],
                              table: Sequence[Sequence[str]],
                              plan: dict[str, Any],
                              bound: bool,
                              draw_image: Path | str | None = None) -> dict[str, Any]:
    """把已经算好的文档模型排成 A4 PDF；返回 ``{path, sha256, pages, chars, image}``。"""
    _ensure_font()
    path = Path(out_pdf)
    path.parent.mkdir(parents=True, exist_ok=True)
    w, h = A4
    text_w = w - 2 * MARGIN - 6 * mm
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setTitle(f"装配步骤 {part_name} Rev {revision}")
    pages = 0
    written = 0
    not_covered = list(plan.get("not_covered", []))
    y = _frame(c, (pages := pages + 1), part_name, revision, not_covered)

    def new_page() -> None:
        nonlocal y, pages
        c.showPage()
        y = _frame(c, (pages := pages + 1), part_name, revision, not_covered)

    def line(text: str, size: float = 10, bold_gap: float = 0.0) -> None:
        nonlocal y, written
        for ln in wrap_cjk(text, text_w):
            if y < MARGIN + 30 * mm:
                new_page()
            c.setFont(FONT, size)
            c.drawString(MARGIN + 3 * mm, y, ln)
            written += len(ln)
            y -= LINE_H + bold_gap

    image_info = None
    if draw_image is not None:
        # 图是**作者给的**：本仓不自动出装配图 PNG（没有 2D/轴测栅格化那条路），
        # 所以这里既不猜图也不画一张没证过的示意图，只在有图时排版它。
        # 尺寸只走 `read_image_size` 一个来源：它与"落盘前那道校验"判的是同一件事，
        # 两处各写一遍时，一边认了这张图、另一边不认，就又是一次孤儿产物。
        img_path = Path(draw_image)
        iw, ih = read_image_size(img_path)
        box_w = text_w - 6 * mm
        box_h = 78 * mm
        scale = min(box_w / iw, box_h / ih, 1.0) if iw and ih else 1.0
        draw_w, draw_h = iw * scale, ih * scale
        # 这里原先有一条"放不下就整块换页"的分支，实测不可达：进这一支时 y=682.0 pt，
        # draw_h 被 78 mm(=221.1 pt) 上限压住，而触发条件是 y - draw_h < MARGIN + 34 mm，
        # 要 draw_h > 534.6 pt 才成立。留着它就等于在账上宣称了一种不会发生的行为
        # （CHANGELOG 那句"放不下就整块换页"因此也一并改掉）。图固定在首页顶部；
        # 若将来把图挪到正文中段，需要重做分页判据并配用例，而不是指望这行还活着。
        c.saveState()
        c.rect(MARGIN + 3 * mm, y - draw_h, draw_w, draw_h, stroke=1, fill=0)
        c.drawImage(str(img_path), MARGIN + 3 * mm, y - draw_h,
                    width=draw_w, height=draw_h)
        c.restoreState()
        y -= draw_h + LINE_H
        line(IMAGE_CAPTION)
        img_sha = hashlib.sha256(img_path.read_bytes()).hexdigest()
        image_info = {"path": str(img_path), "sha256": img_sha,
                    "pixels": [int(iw), int(ih)],
                    "bytes": img_path.stat().st_size,
                    # 排版后的实际毫米尺寸：等比缩放上限 1.0（不放大，放大是造像素），
                    # 所以一张 1×1 的图会在这里现成 0.4 mm 的小点——图注说"示意图"，
                    # 这一格负责让读者看得见它到底排了多大。
                    "placed_mm": [round(draw_w / mm, 1), round(draw_h / mm, 1)]}
        line(f"示意图文件：{img_path.name}"
             f"（{image_info['bytes']} 字节，sha256 {img_sha[:16]}…）")
        line("")

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
    if draw_image is None:
        line("- 本档没有装配示意图：--draw-image 未给（本仓不自动出装配图，见模块说明）")
    c.showPage()
    c.save()
    raw = path.read_bytes()
    out = {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
           "pages": pages, "chars": written}
    # 与 generate_assembly_steps 对 `pdf` 键同一条纪律：没图时写 None 而不是省键，
    # 读者要能区分"没要图"与"要了图但这一页没落地"
    out["image"] = image_info
    return out
