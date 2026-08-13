"""验证数据导入适配器（'validation.import-evt-dvt-pvt'）。

把 CSV/XLSX 导入委托给 supply_chain.lab，并用 supply_chain.analysis 做
阶段分析，产出纠偏任务与 BOM/CAD 影响传播。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aipd_os.execution.adapter import ToolAdapter
from aipd_os.supply_chain.analysis import (
    analyze_stage,
    create_correction_tasks,
    propagate_impact,
)
from aipd_os.supply_chain.lab import (
    import_lab_csv,
    import_lab_json,
    import_lab_report,
    import_lab_xlsx,
)
from aipd_os.tool_adapters._common import meta, token_meta

VALID_STAGES = {"evt", "dvt", "pvt"}


class ValidationDataAdapter(ToolAdapter):
    provider = "local"
    version = "1.1"

    def capability_id(self) -> str:
        return "validation.import-evt-dvt-pvt"

    def discover(self) -> dict[str, Any]:
        return meta(self.capability_id(), "Validation Data Importer", self.provider, self.version)

    def validate_input(self, input: dict[str, Any]) -> list:
        errors = []
        stage = str(input.get("stage", "")).lower()
        if stage and stage not in VALID_STAGES:
            errors.append(f"'stage' 必须是 {sorted(VALID_STAGES)} 之一")
        if not input.get("files"):
            errors.append("'files' 至少提供一个数据文件")
        return errors

    def side_effect_mode(self) -> str:
        """导入验证数据会写入实验室记录并传播影响：禁止自动重试。"""
        return "EXTERNAL_SIDE_EFFECT"

    def execute(self, input: dict[str, Any]) -> dict[str, Any]:
        stage = str(input.get("stage", "evt")).lower()
        files = input.get("files", [])
        all_records = []
        artifacts = []
        for f in files:
            path = str(f)
            ext = Path(path).suffix.lower()
            if ext == ".csv":
                res = import_lab_csv(path, stage)
            elif ext == ".xlsx":
                res = import_lab_xlsx(path, stage)
            elif ext == ".json":
                res = import_lab_json(path, stage)
            else:
                res = import_lab_report(path, stage)  # pdf/docx -> external_blocked
            all_records.extend(res.get("records", []))
            artifacts.append(path)

        analysis = analyze_stage(all_records, stage)
        correction_tasks = create_correction_tasks(analysis, stage)
        facts = input.get("facts") or {}
        bom = input.get("bom") or []
        affected_keys = [it["test_item"] for it in analysis.get("failing_items", [])]
        propagated_stale = propagate_impact(facts, bom, affected_keys)

        result = {
            "stage": stage,
            "records": all_records,
            "analysis": analysis,
            "correction_tasks": correction_tasks,
            "propagated_stale": propagated_stale,
            "imported_count": len(artifacts),
            "artifacts": artifacts,
            "_meta": token_meta(str(all_records)),
        }
        return result

    def normalize(self, result: Any) -> dict[str, Any]:
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
