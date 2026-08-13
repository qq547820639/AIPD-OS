"""中文 A4 页面光栅化渲染器（Pillow）。

在 300dpi 的 A4 画布（2480x3508）上真实光栅化 STHeiti 中文字体，绘制：
标题 / 正文（按字符换行）/ 图注 / 参数表 / 简单曲线 / 图标与注释形状 / 页码与页脚。
输出 PNG 并返回写入路径。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from aipd_os.layout.fonts import load_font

# A4 @ 300dpi
A4_PX = (2480, 3508)
MARGIN = 160
PAGE_W, PAGE_H = A4_PX
CONTENT_W = PAGE_W - MARGIN * 2

# 首选字体路径（macOS）；跨平台回退由 aipd_os.layout.fonts.load_font 处理。
FONT_PATH_DEFAULT = "/System/Library/Fonts/STHeiti Medium.ttc"


def _load_font(path: str, size: int) -> Any:
    """按给定路径优先加载字体；路径不可用时跨平台回退，绝不抛 OSError。"""
    return load_font(size, path)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    """中文字符级换行（同时兼容英文单词尽量不断开）。"""
    lines: list[str] = []
    for raw in text.split("\n"):
        buf = ""
        for ch in raw:
            if ch == " " and buf:
                probe = buf + ch
                if draw.textlength(probe, font=font) <= max_width:
                    buf = probe
                    continue
                lines.append(buf)
                buf = ""
                continue
            probe = buf + ch
            if draw.textlength(probe, font=font) <= max_width:
                buf = probe
            else:
                if buf:
                    lines.append(buf)
                buf = ch
        if buf:
            lines.append(buf)
    return lines or [""]


def _draw_body(draw, lines: list[str], x, y, font, fill, line_gap) -> float:
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += line_gap
    return y


def _draw_curve(draw, curve, x, y, w, h, font, label_fill, line_fill, grid_fill):
    """在 (x,y,w,h) 区域内绘制简单折线图。"""
    max_pts = 0
    all_vals: list[float] = []
    for series in curve:
        pts = series.get("points", [])
        max_pts = max(max_pts, len(pts))
        for p in pts:
            all_vals.append(float(p[1]))
    if max_pts == 0:
        return
    vmin, vmax = min(all_vals), max(all_vals)
    if vmax == vmin:
        vmax = vmin + 1
    # 网格
    for i in range(5):
        gy = y + h * i / 4
        draw.line([(x, gy), (x + w, gy)], fill=grid_fill, width=2)
    draw.rectangle([x, y, x + w, y + h], outline=grid_fill, width=3)
    colors = [(230, 60, 60), (40, 90, 200), (40, 160, 90), (200, 140, 30)]
    for idx, series in enumerate(curve):
        pts = series.get("points", [])
        if not pts:
            continue
        color = colors[idx % len(colors)]
        n = len(pts)
        coords = []
        for j, p in enumerate(pts):
            px = x + (w * j / max(1, n - 1))
            py = y + h - (h * (float(p[1]) - vmin) / (vmax - vmin))
            coords.append((px, py))
        draw.line(coords, fill=color, width=6, joint="curve")
    # 图例
    lx = x + 10
    for idx, series in enumerate(curve):
        color = colors[idx % len(colors)]
        label = series.get("label", f"序列{idx + 1}")
        draw.rectangle([lx, y + h + 14, lx + 40, y + h + 24], fill=color)
        draw.text((lx + 48, y + h + 12), label, font=font, fill=label_fill)
        lx += draw.textlength(label, font=font) + 48 + 60


def _draw_param_table(draw, rows, x, y, col_widths, header_font, cell_font, header_fill, line_fill, text_fill):
    if not rows:
        return y
    row_h = 90
    header_h = 80
    labels = ["参数", "数值", "单位"]
    # 表头
    yy = y
    draw.rectangle([x, yy, x + sum(col_widths), yy + header_h], fill=header_fill)
    cx = x
    for i, lab in enumerate(labels):
        draw.text((cx + 20, yy + 22), lab, font=header_font, fill=(255, 255, 255))
        cx += col_widths[i]
    yy += header_h
    for r in rows:
        draw.rectangle([x, yy, x + sum(col_widths), yy + row_h], outline=line_fill, width=3)
        cells = [r.get("label", r.get("param", "")), str(r.get("value", "")), r.get("unit", "")]
        cx = x
        for i, cel in enumerate(cells):
            draw.text((cx + 20, yy + 26), cel, font=cell_font, fill=text_fill)
            cx += col_widths[i]
        yy += row_h
    return yy


def render_page(defn: dict, out_png: str,
                font_path: str = FONT_PATH_DEFAULT, dpi: int = 300) -> str:
    """把页面定义光栅化为 A4 PNG。

    defn 支持：role, title, body(list[str]), caption, param_table(list[dict]),
    curve(list[{label,points}]), page_number, footer, expected_character, expected_cmf。
    """
    img = Image.new("RGB", A4_PX, (255, 255, 255))
    draw = ImageDraw.Draw(img)

    title = defn.get("title", "")
    body = defn.get("body", []) or []
    caption = defn.get("caption", "")
    param_table = defn.get("param_table", []) or []
    curve = defn.get("curve") or None
    page_number = defn.get("page_number", 1)
    footer = defn.get("footer", "")

    # 颜色
    primary = (30, 60, 120)
    text_fill = (40, 40, 40)
    muted = (120, 120, 120)
    gold = (200, 160, 60)

    y = MARGIN

    # 顶部装饰条 + 图标式标注色块（注释形状）
    draw.rectangle([MARGIN, y, MARGIN + 90, y + 90], fill=gold)
    draw.rectangle([MARGIN + 90, y, MARGIN + 96, y + 90], fill=primary)
    draw.text((MARGIN + 16, y + 22), "AIPD", font=_load_font(font_path, 40), fill=(255, 255, 255))
    y += 130

    # 标题
    if title:
        title_font = _load_font(font_path, 120)
        draw.text((MARGIN, y), title, font=title_font, fill=primary)
        y += 150
        draw.line([(MARGIN, y), (MARGIN + 420, y)], fill=gold, width=8)
        y += 60

    # 正文
    if body:
        body_font = _load_font(font_path, 52)
        line_gap = 78
        for para in body:
            lines = _wrap(draw, para, body_font, CONTENT_W)
            y = _draw_body(draw, lines, MARGIN, y, body_font, text_fill, line_gap)
            y += 36

    # 参数表
    if param_table:
        y += 30
        draw.text((MARGIN, y), "技术参数", font=_load_font(font_path, 64), fill=primary)
        y += 90
        col_widths = [CONTENT_W * 0.38, CONTENT_W * 0.42, CONTENT_W * 0.20]
        y = _draw_param_table(draw, param_table, MARGIN, y, col_widths,
                              _load_font(font_path, 44), _load_font(font_path, 44),
                              (30, 60, 120), (200, 200, 200), text_fill)
        y += 40

    # 图注区：若配置了曲线则绘制曲线，否则画一个占位图框 + 图注
    if curve:
        y += 20
        curve_h = 900
        draw.rectangle([MARGIN, y, MARGIN + CONTENT_W, y + curve_h], outline=(210, 210, 210), width=4)
        _draw_curve(draw, curve, MARGIN + 60, y + 60, CONTENT_W - 120, curve_h - 160,
                    _load_font(font_path, 40), muted, (30, 60, 120), (225, 225, 225))
        y += curve_h + 40
        if caption:
            draw.text((MARGIN + 20, y), caption, font=_load_font(font_path, 42), fill=muted)
            y += 70
    elif caption:
        y += 20
        box_h = 480
        draw.rectangle([MARGIN, y, MARGIN + CONTENT_W, y + box_h], outline=(210, 210, 210), width=4)
        draw.text((MARGIN + 40, y + box_h // 2), "【图：配图占位，待外部生成】",
                  font=_load_font(font_path, 48), fill=muted)
        y += box_h + 40
        draw.text((MARGIN + 20, y), caption, font=_load_font(font_path, 42), fill=muted)
        y += 70

    # 页脚 + 页码
    draw.line([(MARGIN, PAGE_H - MARGIN - 60), (PAGE_W - MARGIN, PAGE_H - MARGIN - 60)], fill=primary, width=4)
    if footer:
        draw.text((MARGIN, PAGE_H - MARGIN - 46), footer, font=_load_font(font_path, 36), fill=muted)
    pn_txt = f"第 {page_number} 页"
    pn_w = draw.textlength(pn_txt, font=_load_font(font_path, 36))
    draw.text((PAGE_W - MARGIN - pn_w, PAGE_H - MARGIN - 46), pn_txt,
              font=_load_font(font_path, 36), fill=primary)

    out = Path(out_png)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out), dpi=(dpi, dpi))
    return str(out)
