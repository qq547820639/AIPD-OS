"""图像生成适配器（'manual.imggen'）。

仅在配置了 ``AIPD_IMGGEN_BACKEND`` 时才可用；未配置时绝不假装成图，
而是写出外部任务包并标记能力不可用（external_blocked）。
"""

from __future__ import annotations

from typing import Any, cast

from aipd_os.execution.adapter import ToolAdapter, external_blocked_error
from aipd_os.tool_adapters._common import env, meta, token_meta

_BACKEND_ENV = "AIPD_IMGGEN_BACKEND"


class ImageGenAdapter(ToolAdapter):
    def capability_id(self) -> str:
        return "manual.imggen"

    def discover(self) -> dict[str, Any]:
        return meta(
            self.capability_id(),
            "Image Generation (manual)",
            cast(str, env(_BACKEND_ENV, "none")),
            "1.0",
            available=self._is_available(),
        )

    def _is_available(self) -> bool:
        return bool(env(_BACKEND_ENV))

    def validate_input(self, input: dict[str, Any]) -> list:
        errors = []
        if not input.get("prompt"):
            errors.append("'prompt' 必填")
        return errors

    def execute(self, input: dict[str, Any]) -> dict[str, Any]:
        if not self._is_available():
            raise external_blocked_error(
                self.capability_id(),
                "图像生成需要外部文生图后端（配置 AIPD_IMGGEN_BACKEND）。"
                "请人工/外部工具按以下提示词生成并将成图回填。\n"
                f"提示词: {input.get('prompt', '')}",
                work_id=input.get("work_id"),
            )
        # 仅在配置了后端时的确定性占位（标注 simulated）
        prompt = input.get("prompt", "")
        result = {
            "prompt": prompt,
            "backend": env(_BACKEND_ENV),
            "status": "simulated",  # 诚实标注：未真实调用渲染，需后端回填
            "image_path": None,
            "_meta": token_meta(prompt),
        }
        return result

    def normalize(self, result: Any) -> dict[str, Any]:
        return result if isinstance(result, dict) else {"result": result}


__all__ = ["ImageGenAdapter"]
