"""真实多模态视觉审核 Provider 客户端（凭据门控）。

协议：OpenAI-compatible 多模态 ``/chat/completions``（messages 携带 image_url data URI + 问题），
要求模型以 JSON 结构化返回评分/结论：

.. code-block:: json
    {"score": 0.0-1.0, "passed": bool, "conclusion": "...", "dimensions": {...}}

--- 凭据门控 ---
未配置 ``AIPD_VISION_PROVIDER_URL`` / ``AIPD_VISION_API_KEY`` 时 ``available()`` 为 False；
``audit`` 抛 ``VisionAuditUnavailable``（链保持 HOLD）；可用 ``write_external_task_package()``
输出完整外部任务包。有凭据时真实调用并记录 provider / model / 网络 / token / 延迟 / trace。
绝不假装通过了视觉审核。
"""
from __future__ import annotations

import base64
import json
import os
import time
import urllib.request
import uuid
from pathlib import Path
from typing import cast


class VisionAuditUnavailable(RuntimeError):
    """视觉审核后端不可用（未配置 URL / API Key）。"""


class VisionAuditProvider:
    """真实多模态视觉审核 Provider 客户端。"""

    id = "vision"

    def __init__(
        self,
        url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 60.0,
    ):
        self.url = url or os.environ.get("AIPD_VISION_PROVIDER_URL")
        self.api_key = api_key or os.environ.get("AIPD_VISION_API_KEY")
        self.model = model or os.environ.get("AIPD_VISION_MODEL", "gpt-4o")
        self.timeout = float(os.environ.get("AIPD_VISION_TIMEOUT", timeout))

    def available(self) -> bool:
        return bool(self.url and self.api_key)

    def _endpoint(self) -> str:
        base = cast(str, self.url).rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return base + "/chat/completions"

    def audit(
        self,
        image_path: str,
        question: str,
        context: dict | None = None,
    ) -> dict:
        """请求图片 + 问题，解析结构化评分/结论。

        无凭据时抛 ``VisionAuditUnavailable``；有凭据时真实调用并记录
        provider / model / 网络 / token / 延迟 / trace。
        """
        if not self.available():
            raise VisionAuditUnavailable(
                "no vision provider configured (missing AIPD_VISION_PROVIDER_URL / "
                "AIPD_VISION_API_KEY); vision audit stays HOLD; no audit fabricated"
            )
        img = Path(image_path)
        b64 = base64.b64encode(img.read_bytes()).decode("ascii")
        mime = "image/png" if img.suffix.lower() == ".png" else "image/jpeg"
        system_hint = (
            "You are a rigorous visual auditor. Return ONLY a JSON object with keys "
            '"score" (0.0-1.0), "passed" (bool), "conclusion" (str), and "dimensions" (object).'
        )
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_hint},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": question},
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    ],
                },
            ],
            "context": context or {},
            "response_format": {"type": "json_object"},
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self._endpoint(), data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        if self.api_key:
            req.add_header("Authorization", f"Bearer {self.api_key}")

        trace_id = f"vision-{uuid.uuid4().hex[:12]}"
        t0 = time.monotonic()
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310 - 用户配置的可信端点
            raw = resp.read()
            http_status = getattr(resp, "status", 200)
        latency_ms = int((time.monotonic() - t0) * 1000)

        obj = json.loads(raw.decode("utf-8", "replace"))
        usage = obj.get("usage") or {}
        content = obj.get("choices", [{}])[0].get("message", {}).get("content", "{}")
        try:
            parsed = json.loads(content) if isinstance(content, str) else (content or {})
        except Exception:
            parsed = {}
        if not isinstance(parsed, dict):
            parsed = {}

        # 诚实护栏：`passed` 必须是真布尔。模型若返回字符串 "false"/"no"
        # （非空字符串 truthy）会被 bool() 误判为通过——显式拒绝。
        raw_passed = parsed.get("passed")
        passed = raw_passed if isinstance(raw_passed, bool) else False
        raw_score = parsed.get("score")
        if not isinstance(raw_score, (int, float)) or isinstance(raw_score, bool):
            raw_score = None
        conclusion = parsed.get("conclusion")
        if conclusion is not None and not isinstance(conclusion, str):
            conclusion = str(conclusion)

        return {
            "provider": {"id": self.id, "model": self.model, "url": self.url},
            "network": {"http_status": http_status, "latency_ms": latency_ms},
            "tokens": {
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
            },
            "trace_id": trace_id,
            "score": raw_score,
            "passed": passed,
            "parse_error": not isinstance(parsed.get("passed"), bool),
            "conclusion": conclusion,
            "dimensions": parsed.get("dimensions"),
        }

    def write_external_task_package(self, image_path: str, question: str, out_dir: str) -> dict:
        """无凭据时输出完整外部任务包（URL / API key / 模型名 / 期望输出格式），保持 HOLD。

        不执行任何审核，不写审核结论文件，绝不假装通过。
        """
        out_path = Path(out_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        pkg = {
            "job_type": "vision_audit",
            "provider": self.id,
            "status": "external_pending",
            "hold": True,
            "required_config": {
                "url": (
                    "AIPD_VISION_PROVIDER_URL  "
                    "(OpenAI-compatible 多模态 POST <url>/chat/completions)"
                ),
                "api_key": "AIPD_VISION_API_KEY",
                "model": (
                    f"AIPD_VISION_MODEL (default {self.model}; "
                    "e.g. gpt-4o / claude-3.5-sonnet)"
                ),
                "expected_output_format": (
                    'JSON: {"score": 0.0-1.0, "passed": bool, '
                    '"conclusion": str, "dimensions": {...}}'
                ),
            },
            "image_path": str(image_path),
            "question": question,
            "note": "no vision provider configured; vision audit stays HOLD; no audit fabricated",
        }
        task_path = out_path / f"vision_{uuid.uuid4().hex[:8]}.task.json"
        task_path.write_text(json.dumps(pkg, ensure_ascii=False, indent=2), encoding="utf-8")
        return pkg


__all__ = ["VisionAuditProvider", "VisionAuditUnavailable"]
