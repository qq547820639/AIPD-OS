"""跨平台 CJK 字体加载工具。

在 macOS / Linux / Windows 上按优先级尝试常见中文字体路径；当所有路径都不可用时，
回退到 Pillow 内嵌的默认字体（绝不抛出 ``OSError: cannot open resource``）。

该模块是 CI 可复现性的关键：此前 factory 常量硬编码为 macOS 路径
``/System/Library/Fonts/STHeiti Medium.ttc``，导致 Ubuntu/Debian 运行器上
``ImageFont.truetype`` 直接抛 ``OSError``，进而使整批页面被诚实降级为
``external_pending``。统一字体加载器修复了这一跨平台差异。
"""
from __future__ import annotations

from typing import Any, Optional

from PIL import ImageFont

# 按平台优先级尝试的 CJK/通用字体路径（顺序即优先级）。
_FONT_CANDIDATES: tuple[str, ...] = (
    # macOS
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    # Linux (Debian/Ubuntu/常见发行版)
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    # Windows
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/arial.ttf",
)


def resolve_font_path(priority: Optional[str] = None) -> Optional[str]:
    """返回第一个真实存在的字体路径；无任何候选时返回 None。"""
    candidates = (priority,) + _FONT_CANDIDATES if priority else _FONT_CANDIDATES
    for candidate in candidates:
        if not candidate:
            continue
        try:
            if ImageFont.truetype(candidate, 40):  # 探活：能加载即可
                return candidate
        except Exception:
            continue
    return None


def load_font(size: int, path: Optional[str] = None) -> Any:
    """加载一个可用字体；无任何可用字体时回退到 Pillow 内嵌默认字体（绝不抛 OSError）。

    Args:
        size: 字体像素大小。
        path: 可选，优先尝试的字体路径；缺省使用内置候选列表。

    Returns:
        可直接用于 ``ImageDraw.text`` 的字体对象。
    """
    candidates = (path,) + _FONT_CANDIDATES if path else _FONT_CANDIDATES
    for candidate in candidates:
        if not candidate:
            continue
        try:
            return ImageFont.truetype(candidate, size)
        except Exception:
            continue
    # 兜底：无法加载任何真实字体时使用 Pillow 内嵌默认字体。
    try:
        return ImageFont.load_default()
    except Exception:
        # 极端兜底：某些 Pillow 版本 load_default 需要 size 参数。
        try:
            return ImageFont.load_default(size)
        except Exception:
            raise RuntimeError("no usable font and Pillow default font unavailable") from None