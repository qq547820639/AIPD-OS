"""验证数据导入适配器（'validation.import-evt-dvt-pvt'）。

导入 EVT/DVT/PVT 原始验证数据文件。
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict

from aipd_os.execution.adapter import ToolAdapter
from aipd_os.tool_adapters._common import meta, token_meta

VALID_STAGES = {"evt", "dvt", "pvt"}


class ValidationDataAdapter(ToolAdapter):
    provider = "local"
    version = "1.0"

    def capability_id(self) -> str:
        return "validation.import-evt-dvt-pvt"

    def discover(self) -> Dict[str, Any]:
        return meta(self.capability_id(), "Validation Data Importer", self.provider, self.version)

    def validate_input(self, input: Dict[str, Any]) -> list:
        errors = []
        stage = str(input.get("stage", "")).lower()
        if stage and stage not in VALID_STAGES:
            errors.append(f"'stage' 必须是 {sorted(VALID_STAGES)} 之一")
        if not input.get("files"):
            errors.append("'files' 至少提供一个数据文件")
        return errors

    def execute(self, input: Dict[str, Any]) -> Dict[str, Any]:
        stage = str(input.get("stage", "evt")).lower()
        records = []
        artifacts = []
        for f in input.get("files", []):
            path = str(f)
            record = {"stage": stage, "path": path, "imported": os.path.isfile(path)}
            if os.path.isfile(path):
                try:
                    with open(path, "r", encoding="utf-8") as fh:
                        record["data"] = json.load(fh)
                except Exception:
                    record["data"] = None
            records.append(record)
            artifacts.append(path)
        result = {
            "stage": stage,
            "records": records,
            "imported_count": sum(1 for r in records if r["imported"]),
            "artifacts": artifacts,
            "_meta": token_meta(str(records)),
        }
        return result

    def normalize(self, result: Any) -> Dict[str, Any]:
        return result if isinstance(result, dict) else {"result": result}

    def collect_artifacts(self, result: Any) -> list:
        if isinstance(result, dict):
            return list(result.get("artifacts", []))
        return []

    def persist_evidence(self, result: Any, run_id: str) -> list:
        if isinstance(result, dict):
            return list(result.get("artifacts", []))
        return []


__all__ = ["ValidationDataAdapter"]
