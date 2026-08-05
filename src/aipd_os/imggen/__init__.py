"""AIPD-OS 图像生成适配层。

该包负责把手册执行链中的“配图生成”需求对接真实图像生成后端。
当没有可用的后端/API Key 时保持诚实：绝不生成假图，而是输出外部执行任务包。
"""

from aipd_os.imggen.adapter import ImageGenAdapter, ImageGenUnavailable

__all__ = ["ImageGenAdapter", "ImageGenUnavailable"]