"""中文排版层测试：真实 A4 渲染 + PDF/ZIP 合成。"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from aipd_os.layout.composer import build_zip, compose_pdf
from aipd_os.layout.renderer import A4_PX, render_page

SAMPLE = {
    "role": "parameter_table",
    "title": "产品技术参数表",
    "body": ["本产品为工业级外骨骼助力设备，面向重体力作业场景。"],
    "caption": "图 1：产品总体示意图",
    "page_number": 3,
    "footer": "AIPD-OS 产品手册",
    "param_table": [
        {"param": "peak_torque", "label": "峰值扭矩", "value": 120, "unit": "N·m"},
        {"param": "weight", "label": "整机重量", "value": 8.5, "unit": "kg"},
    ],
    "curve": [{"label": "效率曲线", "points": [[0, 10], [1, 20], [2, 18], [3, 30], [4, 40]]}],
}


def test_render_page_a4_dimensions(tmp_path) -> None:
    out = render_page(SAMPLE, str(tmp_path / "p1.png"))
    img = Image.open(out)
    assert img.size == A4_PX == (2480, 3508)
    assert img.mode == "RGB"


def test_compose_pdf_and_zip_nonempty(tmp_path) -> None:
    pngs = [render_page(SAMPLE, str(tmp_path / f"p{i}.png")) for i in range(3)]
    pdf = compose_pdf(pngs, str(tmp_path / "manual.pdf"))
    zf = build_zip(pngs, str(tmp_path / "manual.zip"))
    assert Path(pdf).exists() and Path(pdf).stat().st_size > 0
    assert Path(zf).exists() and Path(zf).stat().st_size > 0
    import zipfile
    with zipfile.ZipFile(zf) as z:
        assert len(z.namelist()) == 4  # 3 PNG + 1 PDF
