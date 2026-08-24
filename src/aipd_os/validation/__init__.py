"""Canonical Validation Domain（v5.10 Milestone 1-4）。

提供验证计划、测试定义、执行记录、结果、Issue、Corrective Action、
EVT/DVT/PVT 导入和 Manufacturing Readiness 的 canonical 模型与服务。

不是第二个 Truth Store：全部复用 AIPDStateDB（migration v13），
lineage 复用 canonical LineageService。
"""

from aipd_os.validation.ingestion import IngestionService
from aipd_os.validation.issues import (
    ACTION_COMPLETED,
    ACTION_IN_PROGRESS,
    ACTION_OPEN,
    ACTION_VERIFIED,
    DISPOSITION_DESIGN_CHANGE,
    DISPOSITION_FIX,
    DISPOSITION_NOT_APPLICABLE,
    DISPOSITION_WAIVE,
    ISSUE_CLOSED,
    ISSUE_IN_PROGRESS,
    ISSUE_OPEN,
    ISSUE_RESOLVED,
    ISSUE_WAIVED,
    PRIORITY_P0,
    PRIORITY_P1,
    PRIORITY_P2,
    PRIORITY_P3,
    SEVERITY_CRITICAL,
    SEVERITY_INFO,
    SEVERITY_MAJOR,
    SEVERITY_MINOR,
    CorrectiveAction,
    Issue,
    IssueService,
)
from aipd_os.validation.models import (
    PLAN_LIFECYCLE_ACTIVE,
    PLAN_LIFECYCLE_CANCELLED,
    PLAN_LIFECYCLE_COMPLETED,
    PLAN_LIFECYCLE_DRAFT,
    PLAN_LIFECYCLE_STATUSES,
    RESULT_FAIL,
    RESULT_HOLD,
    RESULT_IMPORT_ERROR,
    RESULT_NOT_RUN,
    RESULT_NOT_VERIFIED,
    RESULT_PASS,
    RESULT_RUNNING,
    RESULT_STALE,
    RESULT_STATUSES,
    STAGE_DVT,
    STAGE_EVT,
    STAGE_PVT,
    TEST_LIFECYCLE_ACTIVE,
    TEST_LIFECYCLE_DRAFT,
    TEST_LIFECYCLE_RETIRED,
    TEST_LIFECYCLE_STATUSES,
    VALIDATION_STAGES,
    ValidationPlan,
    ValidationResult,
    ValidationRun,
    ValidationTest,
)
from aipd_os.validation.readiness import ReadinessService
from aipd_os.validation.service import ValidationService

__all__ = [
    "RESULT_NOT_RUN", "RESULT_RUNNING", "RESULT_PASS", "RESULT_FAIL",
    "RESULT_HOLD", "RESULT_NOT_VERIFIED", "RESULT_STALE", "RESULT_IMPORT_ERROR",
    "RESULT_STATUSES",
    "STAGE_EVT", "STAGE_DVT", "STAGE_PVT", "VALIDATION_STAGES",
    "PLAN_LIFECYCLE_DRAFT", "PLAN_LIFECYCLE_ACTIVE", "PLAN_LIFECYCLE_COMPLETED",
    "PLAN_LIFECYCLE_CANCELLED", "PLAN_LIFECYCLE_STATUSES",
    "TEST_LIFECYCLE_DRAFT", "TEST_LIFECYCLE_ACTIVE", "TEST_LIFECYCLE_RETIRED",
    "TEST_LIFECYCLE_STATUSES",
    "ValidationPlan", "ValidationTest", "ValidationRun", "ValidationResult",
    "ValidationService",
    # Issue / Corrective Action
    "ISSUE_OPEN", "ISSUE_IN_PROGRESS", "ISSUE_RESOLVED", "ISSUE_CLOSED",
    "ISSUE_WAIVED", "SEVERITY_CRITICAL", "SEVERITY_MAJOR", "SEVERITY_MINOR",
    "SEVERITY_INFO", "PRIORITY_P0", "PRIORITY_P1", "PRIORITY_P2", "PRIORITY_P3",
    "ACTION_OPEN", "ACTION_IN_PROGRESS", "ACTION_COMPLETED", "ACTION_VERIFIED",
    "DISPOSITION_FIX", "DISPOSITION_WAIVE", "DISPOSITION_DESIGN_CHANGE",
    "DISPOSITION_NOT_APPLICABLE",
    "Issue", "CorrectiveAction", "IssueService",
    # Ingestion
    "IngestionService",
    # Readiness
    "ReadinessService",
]
