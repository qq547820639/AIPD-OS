"""本地 B-Rep 适配器（'cad.local-brep'）。

本地参数化建模的轻量通道，成熟度上限 C2。
"""

from __future__ import annotations

from typing import Any, Dict

from aipd_os.execution.adapter import ToolAdapter
from aipd_os.tool_adapters._common import meta, token_meta


class LocalBrepAdapter(ToolAdapter):
    provider = "local-opencascade-proxy"
    version = "1.0"
    maturity_ceiling = "C2"

    def capability_id(self) -> str:
        return "cad.local-brep"

    def discover(self) -> Dict[str, Any]:
        return meta(
            self.capability_id(),
            "Local B-Rep Parametric CAD",
            self.provider,
            self.version,
            maturity_ceiling=self.maturity_ceiling,
        )

    def validate_input(self, input: Dict[str, Any]) -> list:
        errors = []
        if not input.get("features") and not input.get("model_script"):
            errors.append("'features' 或 'model_script' 至少提供一个")
        return errors

    def execute(self, input: Dict[str, Any]) -> Dict[str, Any]:
        features = input.get("features", [])
        model_script = input.get("model_script")
        work_pkg = {
            "mode": "local_parametric",
            "model_script": model_script,
            "features": features,
            "expected_outputs": ["model.step", "inspection_report.json"],
            "maturity_ceiling": self.maturity_ceiling,
        }
        result = {"brep_work_package": work_pkg, "_meta": token_meta(str(work_pkg))}
        return result

    def normalize(self, result: Any) -> Dict[str, Any]:
        return result if isinstance(result, dict) else {"result": result}


__all__ = ["LocalBrepAdapter"]
