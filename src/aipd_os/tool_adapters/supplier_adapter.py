"""供应商文件适配器（'supply.supplier-files'）。

登记供应商提供的文件作为产物与证据。
"""

from __future__ import annotations

import os
from typing import Any, Dict

from aipd_os.execution.adapter import ToolAdapter
from aipd_os.tool_adapters._common import meta, token_meta


class SupplierAdapter(ToolAdapter):
    provider = "local"
    version = "1.0"

    def capability_id(self) -> str:
        return "supply.supplier-files"

    def discover(self) -> Dict[str, Any]:
        return meta(self.capability_id(), "Supplier Files Registrar", self.provider, self.version)

    def validate_input(self, input: Dict[str, Any]) -> list:
        errors = []
        files = input.get("files") or []
        if not files:
            errors.append("'files' 至少提供一个文件路径")
        return errors

    def execute(self, input: Dict[str, Any]) -> Dict[str, Any]:
        files = input.get("files", [])
        registered = []
        for f in files:
            path = str(f)
            registered.append(
                {
                    "path": path,
                    "exists": os.path.isfile(path),
                    "size": os.path.getsize(path) if os.path.isfile(path) else 0,
                }
            )
        result = {"registered_files": registered, "_meta": token_meta(str(registered))}
        return result

    def normalize(self, result: Any) -> Dict[str, Any]:
        return result if isinstance(result, dict) else {"result": result}

    def collect_artifacts(self, result: Any) -> list:
        if isinstance(result, dict):
            return [r["path"] for r in result.get("registered_files", []) if r.get("path")]
        return []

    def persist_evidence(self, result: Any, run_id: str) -> list:
        if isinstance(result, dict):
            return [r["path"] for r in result.get("registered_files", []) if r.get("path")]
        return []


__all__ = ["SupplierAdapter"]
