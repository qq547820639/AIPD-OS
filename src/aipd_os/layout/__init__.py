"""AIPD-OS 中文手册排版层。

使用 Pillow 在 300dpi 的 A4（2480x3508）画布上真实光栅化中文内容，
并基于 reportlab 把逐页 PNG 合成 PDF / ZIP。
"""
from aipd_os.layout.composer import assemble, build_zip, compose_pdf
from aipd_os.layout.renderer import A4_PX, render_page

__all__ = ["A4_PX", "render_page", "compose_pdf", "build_zip", "assemble"]
