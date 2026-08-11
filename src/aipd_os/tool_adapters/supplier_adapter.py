"""供应商文件适配器（'supply.supplier-files'）。

登记供应商提供的文件作为产物与证据；若提供报价 CSV/JSON，则通过
supply_chain.quotes 解析并登记规范化报价。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from aipd_os.execution.adapter import ToolAdapter
from aipd_os.supply_chain.quotes import QuoteRegistry, parse_quote_file
from aipd_os.tool_adapters._common import meta, token_meta

QUOTE_EXTENSIONS = (".csv", ".json")


class SupplierAdapter(ToolAdapter):
    provider = "local"
    version = "1.1"

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

    def side_effect_mode(self) -> str:
        """登记供应商文件/报价会对外部供应商记录产生副作用：禁止自动重试。"""
        return "EXTERNAL_SIDE_EFFECT"

    def execute(self, input: Dict[str, Any]) -> Dict[str, Any]:
        files = input.get("files", [])
        supplier_meta = input.get("supplier_meta") or {}
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

        registry = input.get("quote_registry") or QuoteRegistry()
        parsed_quotes = []
        normalized = []
        for f in files:
            path = str(f)
            if Path(path).suffix.lower() not in QUOTE_EXTENSIONS:
                continue
            try:
                parsed = parse_quote_file(path)
            except (ValueError, FileNotFoundError):
                continue
            for rec in parsed.get("records", []):
                q = registry.add_quote(
                    supplier=rec["supplier"],
                    part=rec["part"],
                    data=rec,
                    source_file=str(path),
                )
                parsed_quotes.append(q.quote_id)
                normalized.append(rec)

        result = {
            "registered_files": registered,
            "parsed_quotes": parsed_quotes,
            "normalized": normalized,
            "supplier_meta": supplier_meta,
            "_meta": token_meta(str(registered)),
        }
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
