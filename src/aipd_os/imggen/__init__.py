"""AIPD-OS 图像生成适配层与可替换 Provider。

该包负责把手册执行链中的“配图生成”需求对接可替换的图像生成 Provider。
- adapter：诚实的外部任务包降级（无后端时输出外部执行任务包，绝不假装生成）。
- providers：``ImageGenProvider`` 接口 + PIL 确定性本地后端 + 外部网络桩。
- registry：锚点注册表与 Visual Bible 一致性结构。
"""

from aipd_os.imggen.adapter import ImageGenAdapter, ImageGenUnavailable
from aipd_os.imggen.providers import (
    ImageGenProvider,
    PILImageGenProvider,
    ExternalImageGenProvider,
    RealImageGenProvider,
    provider_from_name,
)
from aipd_os.imggen.registry import AnchorRegistry, VisualBible

__all__ = [
    "ImageGenAdapter",
    "ImageGenUnavailable",
    "ImageGenProvider",
    "PILImageGenProvider",
    "ExternalImageGenProvider",
    "RealImageGenProvider",
    "provider_from_name",
    "AnchorRegistry",
    "VisualBible",
]
