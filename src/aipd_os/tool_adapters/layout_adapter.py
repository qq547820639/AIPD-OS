"""布局适配器（'manual.layout'）。

生成 A4 2480x3508 @300dpi 的排版方案（真实渲染属于 Task 4）。
"""

from __future__ import annotations

from typing import Any

from aipd_os.execution.adapter import ToolAdapter
from aipd_os.tool_adapters._common import meta, token_meta

PAGE_SPEC = {
    "page_size": "A4",
    "width_px": 2480,
    "height_px": 3508,
    "dpi": 300,
    "width_mm": 210,
    "height_mm": 297,
}


class LayoutAdapter(ToolAdapter):
    provider = "local"
    version = "1.0"

    def capability_id(self) -> str:
        return "manual.layout"

    def discover(self) -> dict[str, Any]:
        return meta(self.capability_id(), "Layout Planner", self.provider, self.version)

    def validate_input(self, input: dict[str, Any]) -> list:
        errors = []
        if not input.get("assets") and not input.get("slots"):
            errors.append("'assets' 或 'slots' 至少提供一个")
        return errors

    def execute(self, input: dict[str, Any]) -> dict[str, Any]:
        slots = input.get("slots") or [
            {
                "id": f"slot_{i + 1}",
                "asset": a if isinstance(a, str) else a.get("path"),
            }
            for i, a in enumerate(input.get("assets", []))
        ]
        plan = {
            "page": dict(PAGE_SPEC),
            "slots": slots,
            "strategy": input.get("strategy", "balanced"),
            "margins_mm": input.get("margins_mm", 10),
            "note": "布局方案（真实渲染属于 Task 4）",
        }
        result = {
            "layout_plan": plan,
            "page_spec": dict(PAGE_SPEC),
            "_meta": token_meta(str(plan)),
        }
        return result

    def normalize(self, result: Any) -> dict[str, Any]:
        return result if isinstance(result, dict) else {"result": result}


__all__ = ["LayoutAdapter", "PAGE_SPEC"]
