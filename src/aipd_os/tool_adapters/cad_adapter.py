"""CAD 适配器（'cad.text-to-cad'）。

配置了 ``AIPD_CAD_PROVIDER`` 时才可用；否则返回 CAD 契约/工作包并标记
external_blocked，绝不伪造 CAD 结果。
"""

from __future__ import annotations

from typing import Any, cast

from aipd_os.execution.adapter import ToolAdapter, external_blocked_error
from aipd_os.tool_adapters._common import env, meta, token_meta

_PROVIDER_ENV = "AIPD_CAD_PROVIDER"


class CadAdapter(ToolAdapter):
    def capability_id(self) -> str:
        return "cad.text-to-cad"

    def discover(self) -> dict[str, Any]:
        return meta(
            self.capability_id(),
            "Text-to-CAD",
            cast(str, env(_PROVIDER_ENV, "none")),
            "1.0",
            available=self._is_available(),
        )

    def _is_available(self) -> bool:
        return bool(env(_PROVIDER_ENV))

    def validate_input(self, input: dict[str, Any]) -> list:
        errors = []
        if not input.get("description"):
            errors.append("'description' 必填")
        return errors

    def execute(self, input: dict[str, Any]) -> dict[str, Any]:
        if not self._is_available():
            raise external_blocked_error(
                self.capability_id(),
                "文本转 CAD 需要外部 CAD 提供商（配置 AIPD_CAD_PROVIDER）。"
                "请人工/外部工具完成建模并回填 STEP/参数化模型。\n"
                f"需求描述: {input.get('description', '')}",
                work_id=input.get("work_id"),
            )
        desc = input.get("description", "")
        contract = {
            "description": desc,
            "provider": env(_PROVIDER_ENV),
            "required_outputs": ["model.step", "model.stl", "model.glb", "inspection_report.json"],
            "status": "simulated",  # 诚实标注：未真实调用 CAD 引擎
        }
        result = {"cad_contract": contract, "_meta": token_meta(desc)}
        return result

    def normalize(self, result: Any) -> dict[str, Any]:
        return result if isinstance(result, dict) else {"result": result}


__all__ = ["CadAdapter"]
