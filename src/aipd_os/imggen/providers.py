"""可替换的图像生成 Provider 接口（诚实的连续附件产品手册链）。

设计原则（诚实性）：
- ``ImageGenProvider`` 是抽象接口：接受一批页面定义 + 前一批的真实图像字节内容，
  返回真实图像字节（``data``）/文件对象，而不是仅返回路径字符串。
- ``PILImageGenProvider``：确定性本地后端。用 Pillow 真实渲染出每页配图字节，
  并把前一批的真实图像字节合成到新图（蒙太奇条带），从而让第二批真正“收到”第一批的字节。
  它同时记录 request_id / model_version / seed / prompt / 附件哈希 / 生成参数 / cost / latency / 产物哈希。
- ``ExternalImageGenProvider``：外部网络桩，标记 ``external_dependency``。未配置后端时
  ``available()`` 为 False，``generate_batch`` 抛 ``ImageGenUnavailable``，链保持 HOLD 并输出外部任务包，
  绝不假装生成了真实图像。
"""
from __future__ import annotations

import hashlib
import io
import os
import random
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from PIL import Image, ImageDraw, ImageFont

from aipd_os.imggen.adapter import ImageGenUnavailable

FIG_SIZE = (1024, 1024)
FONT_PATH_DEFAULT = "/System/Library/Fonts/STHeiti Medium.ttc"
MODEL_VERSION = "pil-deterministic-1.0"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_font(size: int) -> Any:
    try:
        return ImageFont.truetype(FONT_PATH_DEFAULT, size)
    except Exception:
        return ImageFont.load_default()


@dataclass
class GeneratedImage:
    """一张真实生成的配图（携带真实字节与生成元数据）。"""

    page_id: str
    data: bytes
    format: str
    width: int
    height: int
    sha256: str
    meta: Dict[str, Any] = field(default_factory=dict)
    external_pending: bool = False


@dataclass
class BatchRequest:
    """一次批量配图生成的请求。"""

    pages: List[dict]
    model_version: str
    prompt_template: str
    generation_params: Dict[str, Any]
    seed: Optional[int] = None
    request_id: Optional[str] = None


@dataclass
class PriorBatchContent:
    """前一批真实图像字节内容（不是路径字符串）。"""

    images: List[dict]  # each {page_id, data(bytes), sha256}

    def attachment_hash(self) -> str:
        h = hashlib.sha256()
        for im in self.images:
            h.update(im.get("data") or b"")
        return h.hexdigest()

    def total_bytes(self) -> int:
        return sum(len(im.get("data") or b"") for im in self.images)


class ImageGenProvider(ABC):
    """可替换的图像生成 Provider 抽象接口。"""

    id: str = "base"
    external_dependency: bool = False

    @abstractmethod
    def available(self) -> bool:
        """后端是否可用（是否已配置真实后端）。"""

    @abstractmethod
    def generate_batch(
        self,
        request: BatchRequest,
        prior_batch: Optional[PriorBatchContent] = None,
    ) -> List[GeneratedImage]:
        """为一批页面生成真实配图字节，并消费前一批的真实图像字节。"""


def _montage(prior_images: List[dict], thumb: int = 96, gap: int = 8, max_count: int = 8) -> Optional[Image.Image]:
    """把前一批真实图像字节合成为底部蒙太奇条带（证明字节被消费）。"""
    if not prior_images:
        return None
    thumbs = []
    for im in prior_images[:max_count]:
        try:
            p = Image.open(io.BytesIO(im.get("data") or b""))
            p = p.convert("RGB")
            p.thumbnail((thumb, thumb))
            thumbs.append(p)
        except Exception:
            continue
    if not thumbs:
        return None
    total_w = sum(p.width for p in thumbs) + gap * (len(thumbs) + 1)
    total_h = max(p.height for p in thumbs) + gap * 2
    strip = Image.new("RGB", (total_w, total_h), (240, 240, 240))
    x = gap
    for p in thumbs:
        strip.paste(p, (x, gap))
        x += p.width + gap
    return strip


class PILImageGenProvider(ImageGenProvider):
    """确定性本地后端：用 Pillow 真实渲染配图字节。

    诚实标注为本地确定性后端（非真实文生图模型）。它确实产生真实图像字节，
    因此可用于连续批次之间的字节流转验证，但绝不冒充真实视觉模型。
    """

    id = "pil"
    external_dependency = False

    def __init__(self, font_path: str = FONT_PATH_DEFAULT):
        self.font_path = font_path

    def available(self) -> bool:
        return True

    def generate_batch(
        self,
        request: BatchRequest,
        prior_batch: Optional[PriorBatchContent] = None,
    ) -> List[GeneratedImage]:
        seed = request.seed if request.seed is not None else 1
        rng = random.Random(seed)
        req_id = request.request_id or f"req-{uuid.uuid4().hex[:12]}"
        prior_images = list((prior_batch.images or [])) if prior_batch else []
        prior_data = [im.get("data") or b"" for im in prior_images]
        att_hash = prior_batch.attachment_hash() if prior_batch else None

        results: List[GeneratedImage] = []
        for page in request.pages:
            t0 = time.monotonic()
            prompt = f"{request.prompt_template} {page.get('title', '')} / {page.get('page_id', '')}"
            prompt_hash = _sha(prompt.encode("utf-8"))

            img = Image.new("RGB", FIG_SIZE, (rng.randint(30, 60), rng.randint(60, 110), rng.randint(120, 180)))
            draw = ImageDraw.Draw(img)
            draw.text((60, 60), str(page.get("title", "")), font=_load_font(56), fill=(255, 255, 255))
            draw.text((60, 150), f"page:{page.get('page_id', '')}", font=_load_font(36), fill=(230, 230, 230))
            draw.text((60, 210), f"seed:{seed} prompt_hash:{prompt_hash[:12]}", font=_load_font(28), fill=(200, 200, 200))

            strip = _montage(prior_images)
            if strip is not None:
                strip = strip.resize((min(FIG_SIZE[0], strip.width), strip.height))
                top = FIG_SIZE[1] - strip.height
                img.paste(strip, (0, top))
                draw.rectangle([0, top - 2, FIG_SIZE[0], top], fill=(255, 255, 255))
                draw.text(
                    (10, max(0, top - 34)),
                    f"prior:{len(prior_images)} imgs att_hash:{att_hash[:12] if att_hash else '-'}",
                    font=_load_font(24),
                    fill=(255, 255, 255),
                )

            buf = io.BytesIO()
            img.save(buf, format="PNG")
            data = buf.getvalue()
            latency_ms = int((time.monotonic() - t0) * 1000)
            artifact_hash = _sha(data)
            meta = {
                "provider_id": self.id,
                "request_id": req_id,
                "model_version": request.model_version,
                "seed": seed,
                "prompt": prompt,
                "prompt_hash": prompt_hash,
                "attachment_hash": att_hash,
                "prior_image_count": len(prior_images),
                "prior_total_bytes": sum(len(b) for b in prior_data),
                "generation_params": dict(request.generation_params),
                "cost": 0.0,
                "cost_unit": "local_deterministic",
                "latency_ms": latency_ms,
                "artifact_hash": artifact_hash,
            }
            results.append(
                GeneratedImage(
                    page_id=page.get("page_id"),
                    data=data,
                    format="PNG",
                    width=FIG_SIZE[0],
                    height=FIG_SIZE[1],
                    sha256=artifact_hash,
                    meta=meta,
                )
            )
        return results


class ExternalImageGenProvider(ImageGenProvider):
    """外部/网络图像生成桩（external_dependency）。

    未配置真实后端时 ``available()`` 为 False，``generate_batch`` 抛
    ``ImageGenUnavailable``，链对外输出外部任务包并保持 HOLD。即便配置了环境变量，
    本仓也没有真实文生图客户端，因此同样拒绝假装成图。
    """

    id = "external"
    external_dependency = True

    def __init__(self, backend: Optional[str] = None, api_key: Optional[str] = None):
        self.backend = backend or os.environ.get("AIPD_IMGGEN_BACKEND")
        self.api_key = api_key or os.environ.get("AIPD_IMGGEN_API_KEY")

    def available(self) -> bool:
        return bool(self.backend and self.api_key)

    def generate_batch(
        self,
        request: BatchRequest,
        prior_batch: Optional[PriorBatchContent] = None,
    ) -> List[GeneratedImage]:
        if not self.available():
            raise ImageGenUnavailable(
                "no image generation backend configured; chain stays HOLD and emits external task package"
            )
        raise ImageGenUnavailable(
            "external backend client is not wired up; refusing to fabricate real image bytes"
        )


def provider_from_name(name: str) -> ImageGenProvider:
    """按名称构造 Provider（用于 CLI 选择与测试注入）。"""
    if name in ("pil", "PILImageGenProvider", "local", "deterministic"):
        return PILImageGenProvider()
    return ExternalImageGenProvider()


__all__ = [
    "GeneratedImage",
    "BatchRequest",
    "PriorBatchContent",
    "ImageGenProvider",
    "PILImageGenProvider",
    "ExternalImageGenProvider",
    "provider_from_name",
    "FIG_SIZE",
    "MODEL_VERSION",
]