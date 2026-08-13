"""图像生成适配器。

设计原则（诚实性）：
- 只有当配置了真实后端与 API Key 时 ``available()`` 才返回 True。
- 后端不可用时 ``generate()`` 必须抛 ``ImageGenUnavailable``，绝不写假图。
- 不可用时应通过 ``write_external_task_package()`` 输出外部执行任务包，
  描述“需要外部产出的图片/页面”，供人工或外部管线消费。
"""
from __future__ import annotations

import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Union

Size = Union[tuple[int, int], Sequence[int], str]


class ImageGenUnavailable(RuntimeError):
    """图像生成后端不可用（未配置后端或 API Key）。"""


def _normalize_size(size: Size) -> tuple[int, int]:
    from typing import Any
    if isinstance(size, str):
        parts = size.lower().split("x")
        if len(parts) != 2:
            raise ValueError(f"无法解析图像尺寸 {size!r}；应为 'WxH'（如 '1024x1024'）")
        w_raw: Any = parts[0]
        h_raw: Any = parts[1]
    else:
        if len(size) < 2:
            raise ValueError(f"图像尺寸必须为 (width, height)，收到: {size!r}")
        w_raw, h_raw = size[0], size[1]
    try:
        w, h = int(w_raw), int(h_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"无法解析图像尺寸 {size!r}；宽高必须为整数") from exc
    if w <= 0 or h <= 0:
        raise ValueError(f"图像尺寸必须为正整数，收到: {size!r}")
    return w, h


class ImageGenAdapter:
    """把一次配图生成请求路由到真实后端，或诚实降级为外部任务包。"""

    def __init__(self, backend: str | None = None, api_key: str | None = None):
        self.backend = backend or os.environ.get("AIPD_IMGGEN_BACKEND")
        self.api_key = api_key or os.environ.get("AIPD_IMGGEN_API_KEY")

    def available(self) -> bool:
        """后端与密钥都配置好才算可用。"""
        return bool(self.backend and self.api_key)

    def generate(self, prompt: str, size: Size, out_path: str, seed: int | None = None) -> str:
        """调用真实后端生成一张图并写入 out_path，返回写入路径。

        后端不可用时抛出 ImageGenUnavailable，绝不伪造图片文件。
        """
        if not self.available():
            raise ImageGenUnavailable(
                f"image generation backend unavailable (backend={self.backend!r}, "
                f"api_key_configured={bool(self.api_key)}); cannot generate {out_path!r}"
            )
        # 真实后端在此并无通用实现：诚实抛出，避免假装生成了图。
        raise ImageGenUnavailable(
            "no real backend client is wired up; refusing to fabricate an image"
        )

    def write_external_task_package(self, prompt: str, size: Size, out_path: str) -> dict:
        """把一次生成任务写成 JSON 外部执行任务包，返回该包 dict。

        不写任何图片，只写一份可被外部口径消费的任务描述。
        """
        w, h = _normalize_size(size)
        pkg = {
            "job_type": "image_generation",
            "status": "external_pending",
            "prompt": prompt,
            "size": {"width": w, "height": h, "width_px": w, "height_px": h},
            "expected_path": str(out_path),
            "backend": self.backend,
            "api_key_configured": bool(self.api_key),
            "note": "generated externally; not fabricated by adapter",
        }
        target = Path(out_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        # 任务包路径与图片期望路径相邻，便于外部消费。
        task_path = target.with_suffix(target.suffix + ".task.json") if target.suffix else target.with_name(target.name + ".task.json")  # noqa: E501
        task_path.write_text(json.dumps(pkg, ensure_ascii=False, indent=2), encoding="utf-8")
        return pkg
