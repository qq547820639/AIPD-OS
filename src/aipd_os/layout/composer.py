"""逐页 PNG 合成 PDF / ZIP。

- compose_pdf: 用 reportlab 把 A4 PNG 逐页合成单个 A4 PDF。
- build_zip: 把逐页 PNG + PDF 打包成 ZIP。
- assemble: 从 pages_dir 产出逐页 PNG、PDF 与 ZIP 到 out_dir。
"""
from __future__ import annotations

import zipfile
from collections.abc import Iterable
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def compose_pdf(pages: Iterable[str], out_pdf: str) -> str:
    """把若干 A4 PNG 路径按顺序合成一个 A4 PDF。"""
    page_paths = [str(p) for p in pages]
    out = Path(out_pdf)
    out.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out), pagesize=A4)
    a4_w, a4_h = A4
    for pth in page_paths:
        c.drawImage(pth, 0, 0, width=a4_w, height=a4_h)
        c.showPage()
    c.save()
    return str(out)


def build_zip(pages: Iterable[str], out_zip: str) -> str:
    """把逐页 PNG + 同名 PDF 打包成 ZIP。"""
    page_paths = [str(p) for p in pages]
    out = Path(out_zip)
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(str(out), "w", zipfile.ZIP_DEFLATED) as zf:
        for pth in page_paths:
            zf.write(pth, Path(pth).name)
        pdf = out.with_suffix(".pdf")
        if pdf.exists():
            zf.write(str(pdf), pdf.name)
    return str(out)


def assemble(pages_dir: str, out_dir: str) -> dict:
    """从 pages_dir 读取所有 PNG，产出 PDF + ZIP 到 out_dir。返回产物清单。"""
    pages_path = Path(pages_dir)
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    pngs = sorted(str(p) for p in pages_path.glob("*.png"))
    pdf = compose_pdf(pngs, str(out_path / "manual.pdf"))
    zipped = build_zip(pngs, str(out_path / "manual.zip"))
    return {
        "pages": [str(p) for p in pngs],
        "pdf": pdf,
        "zip": zipped,
    }
