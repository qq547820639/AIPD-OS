"""EVT/DVT/PVT Ingestion Canonicalization（v5.10 Milestone 3）。

正确链路：
external CSV/XLSX/JSON → parser → normalized DTO → schema validation
→ ValidationService → canonical Test/Run/Result → IssueService → derived projections

而不是把临时 dict 当最终真相。
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aipd_os.supply_chain.lab import (
    import_lab_csv,
    import_lab_json,
    import_lab_xlsx,
)
from aipd_os.validation.issues import (
    SEVERITY_MAJOR,
    IssueService,
)
from aipd_os.validation.models import (
    RESULT_FAIL,
    RESULT_IMPORT_ERROR,
    RESULT_PASS,
    VALIDATION_STAGES,
)
from aipd_os.validation.service import ValidationService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Normalized DTO
# ---------------------------------------------------------------------------

@dataclass
class LabRecordDTO:
    """解析后的标准化实验室记录。"""
    stage: str
    test_item: str
    sample_id: str = ""
    result: str = ""
    pass_fail: str = ""
    notes: str = ""
    source_file: str = ""
    source_format: str = ""
    raw_data: dict[str, Any] = field(default_factory=dict)

    def is_pass(self) -> bool:
        return self.pass_fail.lower() == "pass"

    def is_fail(self) -> bool:
        return self.pass_fail.lower() == "fail"


@dataclass
class IngestionResult:
    """导入结果。"""
    stage: str
    records_imported: int
    tests_created: int
    runs_created: int
    results_created: int
    issues_created: int
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    idempotent_skips: int = 0


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

_REQUIRED_COLUMNS = {"test_item", "pass_fail"}


def _validate_record(record: LabRecordDTO) -> list[str]:
    """验证单条记录的 schema。返回错误列表。"""
    errors = []
    if not record.test_item:
        errors.append("missing test_item")
    if record.pass_fail and record.pass_fail.lower() not in ("pass", "fail", ""):
        errors.append(f"invalid pass_fail value: {record.pass_fail!r}")
    if record.stage and record.stage.lower() not in ("evt", "dvt", "pvt"):
        errors.append(f"invalid stage: {record.stage!r}")
    return errors


# ---------------------------------------------------------------------------
# Parser layer
# ---------------------------------------------------------------------------

def _parse_file(path: str | Path, stage: str) -> list[LabRecordDTO]:
    """解析外部文件为标准化 DTO 列表。"""
    p = Path(path)
    ext = p.suffix.lower()

    if ext == ".csv":
        raw = import_lab_csv(str(p), stage)
    elif ext == ".xlsx":
        raw = import_lab_xlsx(str(p), stage)
    elif ext == ".json":
        raw = import_lab_json(str(p), stage)
    else:
        raise ValueError(f"unsupported file format: {ext}")

    records = []
    for r in raw.get("records", []):
        records.append(LabRecordDTO(
            stage=str(r.get("stage", stage)).lower(),
            test_item=str(r.get("test_item", "")).strip(),
            sample_id=str(r.get("sample_id", "")).strip(),
            result=str(r.get("result", "")).strip(),
            pass_fail=str(r.get("pass_fail", "")).strip().lower(),
            notes=str(r.get("notes", "")).strip(),
            source_file=str(p),
            source_format=ext,
            raw_data=r,
        ))
    return records


def _compute_artifact_hash(records: list[LabRecordDTO]) -> str:
    """计算导入数据的确定性哈希（用于 artifact revision tracking）。"""
    h = hashlib.sha256()
    for r in records:
        h.update(f"{r.test_item}:{r.pass_fail}:{r.sample_id}".encode())
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Canonical Ingestion Service
# ---------------------------------------------------------------------------

class IngestionService:
    """EVT/DVT/PVT 导入服务。

    将外部验证数据导入到 canonical Validation/Issue 域。
    """

    def __init__(
        self,
        validation_svc: ValidationService,
        issue_svc: IssueService,
    ) -> None:
        self._validation = validation_svc
        self._issues = issue_svc

    def ingest_file(
        self,
        tenant_id: str,
        project_id: str,
        file_path: str | Path,
        stage: str,
        plan_id: str = "",
        operator: str = "system",
        idempotency_key: str = "",
    ) -> IngestionResult:
        """导入单个文件到 canonical validation 域。

        Args:
            tenant_id: 租户 ID
            project_id: 项目 ID
            file_path: 文件路径
            stage: 验证阶段（EVT/DVT/PVT）
            plan_id: 关联的验证计划 ID（可选）
            operator: 导入操作者
            idempotency_key: 幂等键（防止重复导入）

        Returns:
            IngestionResult
        """
        if stage.upper() not in VALIDATION_STAGES:
            return IngestionResult(
                stage=stage, records_imported=0, tests_created=0,
                runs_created=0, results_created=0, issues_created=0,
                errors=[f"invalid stage: {stage!r}"],
            )

        stage_lower = stage.lower()

        # 1. Parse
        try:
            records = _parse_file(file_path, stage_lower)
        except Exception as e:
            return IngestionResult(
                stage=stage, records_imported=0, tests_created=0,
                runs_created=0, results_created=0, issues_created=0,
                errors=[f"parse error: {e}"],
            )

        if not records:
            return IngestionResult(
                stage=stage, records_imported=0, tests_created=0,
                runs_created=0, results_created=0, issues_created=0,
                warnings=["no records found in file"],
            )

        # 2. Validate schema
        validation_errors: list[str] = []
        for i, rec in enumerate(records):
            errs = _validate_record(rec)
            for err in errs:
                validation_errors.append(f"record {i}: {err}")

        if validation_errors:
            return IngestionResult(
                stage=stage, records_imported=0, tests_created=0,
                runs_created=0, results_created=0, issues_created=0,
                errors=validation_errors,
            )

        # 3. Compute artifact hash
        artifact_hash = _compute_artifact_hash(records)

        # 4. Ingest into canonical domain
        tests_created = 0
        runs_created = 0
        results_created = 0
        issues_created = 0
        idempotent_skips = 0
        errors: list[str] = []
        warnings: list[str] = []

        # Group by test_item
        by_item: dict[str, list[LabRecordDTO]] = {}
        for rec in records:
            by_item.setdefault(rec.test_item, []).append(rec)

        for test_item, item_records in by_item.items():
            # Find or create ValidationTest
            test = self._find_or_create_test(
                tenant_id, project_id, plan_id, test_item, stage_lower)
            if test is None:
                # Create test
                test = self._validation.create_test(
                    tenant_id, project_id, plan_id,
                    name=test_item, stage=stage_lower.upper(),
                    category="lab_validation",
                )
                tests_created += 1

            # Process each record as a run + result
            for rec in item_records:
                # Create run
                run = self._validation.create_run(
                    tenant_id, project_id, test.test_id,
                    tested_artifact_version=f"import_{artifact_hash[:8]}",
                    tested_artifact_hash=artifact_hash,
                    operator=operator,
                    environment=rec.source_file,
                    idempotency_key=idempotency_key or f"{test_item}_{rec.sample_id}",
                )
                runs_created += 1

                # Map pass_fail to canonical status
                if rec.is_pass():
                    result_status = RESULT_PASS
                elif rec.is_fail():
                    result_status = RESULT_FAIL
                else:
                    result_status = RESULT_IMPORT_ERROR
                    warnings.append(
                        f"unknown pass_fail value for {test_item}: {rec.pass_fail!r}")

                # Record result
                result = self._validation.record_result(
                    tenant_id, project_id, run.run_id, test.test_id,
                    result_status=result_status,
                    measured_values=rec.result,
                    pass_evaluation=rec.pass_fail,
                    reason=rec.notes,
                    evaluator=operator,
                )
                results_created += 1

                # If FAIL, create issue (idempotent)
                if result_status == RESULT_FAIL:
                    self._issues.create_issue(
                        tenant_id, project_id,
                        title=f"Validation failure: {test_item} ({stage.upper()})",
                        description=(
                            f"Test item '{test_item}' failed in {stage.upper()} "
                            f"stage. Sample: {rec.sample_id}. "
                            f"Result: {rec.result}. Notes: {rec.notes}"
                        ),
                        severity=SEVERITY_MAJOR,
                        source_object_type="validation_result",
                        source_object_id=result.result_id,
                        validation_result_ref=result.result_id,
                    )
                    issues_created += 1

        return IngestionResult(
            stage=stage,
            records_imported=len(records),
            tests_created=tests_created,
            runs_created=runs_created,
            results_created=results_created,
            issues_created=issues_created,
            errors=errors,
            warnings=warnings,
            idempotent_skips=idempotent_skips,
        )

    def _find_or_create_test(
        self,
        tenant_id: str,
        project_id: str,
        plan_id: str,
        test_name: str,
        stage: str,
    ) -> Any:
        """查找已有的验证测试（按名称匹配）。"""
        tests = self._validation.list_tests(tenant_id, project_id, plan_id)
        for t in tests:
            if t.name == test_name and t.stage.lower() == stage:
                return t
        return None

    def ingest_files(
        self,
        tenant_id: str,
        project_id: str,
        file_paths: list[str | Path],
        stage: str,
        plan_id: str = "",
        operator: str = "system",
    ) -> IngestionResult:
        """导入多个文件。"""
        total = IngestionResult(
            stage=stage, records_imported=0, tests_created=0,
            runs_created=0, results_created=0, issues_created=0,
        )

        for fp in file_paths:
            result = self.ingest_file(
                tenant_id, project_id, fp, stage,
                plan_id=plan_id, operator=operator,
            )
            total.records_imported += result.records_imported
            total.tests_created += result.tests_created
            total.runs_created += result.runs_created
            total.results_created += result.results_created
            total.issues_created += result.issues_created
            total.errors.extend(result.errors)
            total.warnings.extend(result.warnings)
            total.idempotent_skips += result.idempotent_skips

        return total


__all__ = ["IngestionService", "IngestionResult", "LabRecordDTO"]
