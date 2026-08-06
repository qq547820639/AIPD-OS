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

import base64
import hashlib
import io
import json
import os
import random
import time
import urllib.request
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image, ImageDraw

from aipd_os.imggen.adapter import ImageGenUnavailable
from aipd_os.layout.fonts import load_font

FIG_SIZE = (1024, 1024)
FONT_PATH_DEFAULT = "/System/Library/Fonts/STHeiti Medium.ttc"
MODEL_VERSION = "pil-deterministic-1.0"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_font(size: int) -> Any:
    # 跨平台优先 FONT_PATH_DEFAULT，不可用时自动回退；绝不抛 OSError。
    return load_font(size, FONT_PATH_DEFAULT)


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


class RealImageGenProvider(ImageGenProvider):
    """真实图像生成 Provider 客户端（凭据门控）。

    协议：OpenAI-compatible 图像端点（POST ``{url}/images/generations``，响应
    ``{"data": [{"b64_json": ...} | {"url": ...}]}``），或任意以原始二进制图返回的
    兼容端点。**必须真正发送 HTTP 请求并解析真实图像字节**（base64 或二进制），
    而不是 PIL 拼图。

    前一批真实图像作为 ``input_images``（base64 data URI）图像条件随请求发送，
    供兼容后端对后一批进行图像条件生成（而非仅拼成蒙太奇证明字节存在）。

    --- 凭据门控 ---
    未配置 ``AIPD_IMAGE_PROVIDER_URL`` / ``AIPD_IMAGE_API_KEY`` 时 ``available()`` 为
    False；``generate_batch`` 抛 ``ImageGenUnavailable``（链保持 HOLD）；可用
    ``write_external_task_package()`` 输出完整外部任务包（URL / API key / 模型名 /
    期望输出格式）。绝不假装生成图像。
    """

    id = "real"
    external_dependency = True

    def __init__(
        self,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        output_format: str = "png",
        timeout: float = 60.0,
    ):
        self.url = url or os.environ.get("AIPD_IMAGE_PROVIDER_URL")
        self.api_key = api_key or os.environ.get("AIPD_IMAGE_API_KEY")
        self.model = model or os.environ.get("AIPD_IMAGE_MODEL", "dall-e-3")
        self.output_format = (
            output_format or os.environ.get("AIPD_IMAGE_OUTPUT", "png")
        ).lower()
        self.timeout = float(os.environ.get("AIPD_IMAGE_TIMEOUT", timeout))

    def available(self) -> bool:
        return bool(self.url and self.api_key)

    def _endpoint(self) -> str:
        base = self.url.rstrip("/")
        if base.endswith("/images/generations"):
            return base
        return base + "/images/generations"

    def _send(self, payload: dict) -> tuple:
        """发送真实 HTTP POST 并返回 (raw_bytes, http_status, content_type, latency_ms)。"""
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self._endpoint(), data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        if self.api_key:
            req.add_header("Authorization", f"Bearer {self.api_key}")
        t0 = time.monotonic()
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310 - 用户配置的可信端点
            raw = resp.read()
            status = getattr(resp, "status", 200)
            content_type = resp.headers.get("Content-Type", "")
        latency_ms = int((time.monotonic() - t0) * 1000)
        return raw, status, content_type, latency_ms

    @staticmethod
    def _decode_image(raw: bytes, content_type: str) -> tuple:
        """解析真实图像字节，返回 (bytes, format, source)。"""
        # 优先解析 OpenAI-compatible JSON
        try:
            obj = json.loads(raw.decode("utf-8", "replace"))
        except Exception:
            obj = None
        if isinstance(obj, dict):
            data_list = obj.get("data")
            if isinstance(data_list, list) and data_list:
                first = data_list[0]
                b64 = first.get("b64_json")
                if b64:
                    return base64.b64decode(b64), "PNG", "b64_json"
                url_ = first.get("url")
                if url_:
                    with urllib.request.urlopen(url_, timeout=60) as r:  # noqa: S310
                        return r.read(), "PNG", "url"
        # 兜底：原始二进制图
        ct = (content_type or "").lower()
        fmt = "JPEG" if ("jpeg" in ct or "jpg" in ct) else "PNG"
        return raw, fmt, "binary"

    def generate_batch(
        self,
        request: BatchRequest,
        prior_batch: Optional[PriorBatchContent] = None,
    ) -> List[GeneratedImage]:
        if not self.available():
            raise ImageGenUnavailable(
                "real image provider not configured (missing AIPD_IMAGE_PROVIDER_URL / "
                "AIPD_IMAGE_API_KEY); chain stays HOLD; no image bytes fabricated"
            )
        prior_images = list((prior_batch.images or [])) if prior_batch and prior_batch.images else []
        # 前一批真实图像作为图像条件（base64 data URI），供后端做条件生成。
        prior_attachments = []
        for im in prior_images:
            data = im.get("data") or b""
            prior_attachments.append(
                "data:image/png;base64," + base64.b64encode(data).decode("ascii")
            )
        req_id = request.request_id or f"req-{uuid.uuid4().hex[:12]}"
        results: List[GeneratedImage] = []
        for page in request.pages:
            size = request.generation_params.get("size") or [1024, 1024]
            if isinstance(size, str):
                w, h = (int(x) for x in size.lower().split("x"))
            else:
                w, h = int(size[0]), int(size[1])
            prompt = (
                f"{request.prompt_template} {page.get('title', '')} / "
                f"{page.get('page_id', '')} / {page.get('expected_cmf', '')}"
            )
            payload = {
                "model": self.model,
                "prompt": prompt,
                "size": f"{w}x{h}",
                "n": 1,
                "response_format": "b64_json",
                "input_images": prior_attachments,
                "prior_image_count": len(prior_attachments),
            }
            raw, http_status, content_type, latency_ms = self._send(payload)
            data, fmt, source = self._decode_image(raw, content_type)
            artifact_hash = _sha(data)
            meta = {
                "provider_id": self.id,
                "request_id": req_id,
                "model": self.model,
                "http_status": http_status,
                "source": source,
                "prompt": prompt,
                "prior_image_count": len(prior_attachments),
                "prior_condition": True,
                "generation_params": dict(request.generation_params),
                "latency_ms": latency_ms,
                "cost": None,
                "cost_unit": "provider_billed",
                "artifact_hash": artifact_hash,
                "note": "real image provider; bytes parsed from real HTTP response",
            }
            results.append(
                GeneratedImage(
                    page_id=page.get("page_id"),
                    data=data,
                    format=fmt or "PNG",
                    width=w,
                    height=h,
                    sha256=artifact_hash,
                    meta=meta,
                )
            )
        return results

    def write_external_task_package(self, request: BatchRequest, out_dir: str) -> dict:
        """无凭据时输出完整外部任务包（URL / API key / 模型名 / 期望输出格式），保持 HOLD。

        不写任何图像文件。
        """
        out_path = Path(out_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        pkg = {
            "job_type": "image_generation",
            "provider": self.id,
            "status": "external_pending",
            "hold": True,
            "required_config": {
                "url": "AIPD_IMAGE_PROVIDER_URL  (OpenAI-compatible POST <url>/images/generations)",
                "api_key": "AIPD_IMAGE_API_KEY",
                "model": f"AIPD_IMAGE_MODEL (default {self.model}; e.g. dall-e-3 / stable-diffusion-xl)",
                "output_format": f"AIPD_IMAGE_OUTPUT (default {self.output_format}; e.g. png / jpeg)",
            },
            "request": {
                "pages": [p.get("page_id") for p in request.pages],
                "model_version": request.model_version,
                "prompt_template": request.prompt_template,
                "generation_params": request.generation_params,
            },
            "note": "no real image provider configured; chain stays HOLD; no image bytes fabricated",
        }
        task_path = out_path / f"real_{request.request_id or 'batch'}.task.json"
        task_path.write_text(json.dumps(pkg, ensure_ascii=False, indent=2), encoding="utf-8")
        return pkg


def provider_from_name(name: str) -> ImageGenProvider:
    """按名称构造 Provider（用于 CLI 选择与测试注入）。"""
    if name in ("real", "http", "openai", "comfy", "sd", "stable-diffusion"):
        return RealImageGenProvider()
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
    "RealImageGenProvider",
    "provider_from_name",
    "FIG_SIZE",
    "MODEL_VERSION",
]
