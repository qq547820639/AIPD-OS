"""Canonical Validation Domain Models（v5.10 Milestone 1）。

一等实体：
- ValidationPlan：某 project/version/stage 的验证计划
- ValidationTest：可重复执行的验证定义
- ValidationRun：一次实际执行
- ValidationResult：一次测试的判断结果

所有实体包含 tenant_id + project_id 作用域。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# 结果状态（§3.2 honest truth semantics）
# ---------------------------------------------------------------------------
RESULT_NOT_RUN = "NOT_RUN"
RESULT_RUNNING = "RUNNING"
RESULT_PASS = "PASS"
RESULT_FAIL = "FAIL"
RESULT_HOLD = "HOLD"
RESULT_NOT_VERIFIED = "NOT_VERIFIED"
RESULT_STALE = "STALE"
RESULT_IMPORT_ERROR = "IMPORT_ERROR"

RESULT_STATUSES = frozenset({
    RESULT_NOT_RUN, RESULT_RUNNING, RESULT_PASS, RESULT_FAIL,
    RESULT_HOLD, RESULT_NOT_VERIFIED, RESULT_STALE, RESULT_IMPORT_ERROR,
})

# 有效通过状态（用于 readiness 计算）
EFFECTIVE_PASS_STATUSES = frozenset({RESULT_PASS})
# 阻塞状态（阻止 readiness PASS）
BLOCKING_STATUSES = frozenset({RESULT_FAIL, RESULT_HOLD, RESULT_IMPORT_ERROR})
# 未完成状态（不计入有效结果）
INCOMPLETE_STATUSES = frozenset({
    RESULT_NOT_RUN, RESULT_RUNNING, RESULT_NOT_VERIFIED, RESULT_STALE,
})

# ---------------------------------------------------------------------------
# 验证阶段
# ---------------------------------------------------------------------------
STAGE_EVT = "EVT"
STAGE_DVT = "DVT"
STAGE_PVT = "PVT"
VALIDATION_STAGES = frozenset({STAGE_EVT, STAGE_DVT, STAGE_PVT})

# ---------------------------------------------------------------------------
# 生命周期状态
# ---------------------------------------------------------------------------
PLAN_LIFECYCLE_DRAFT = "draft"
PLAN_LIFECYCLE_ACTIVE = "active"
PLAN_LIFECYCLE_COMPLETED = "completed"
PLAN_LIFECYCLE_CANCELLED = "cancelled"
PLAN_LIFECYCLE_STATUSES = frozenset({
    PLAN_LIFECYCLE_DRAFT, PLAN_LIFECYCLE_ACTIVE,
    PLAN_LIFECYCLE_COMPLETED, PLAN_LIFECYCLE_CANCELLED,
})

TEST_LIFECYCLE_DRAFT = "draft"
TEST_LIFECYCLE_ACTIVE = "active"
TEST_LIFECYCLE_RETIRED = "retired"
TEST_LIFECYCLE_STATUSES = frozenset({
    TEST_LIFECYCLE_DRAFT, TEST_LIFECYCLE_ACTIVE, TEST_LIFECYCLE_RETIRED,
})


def _parse_json_list(raw: Any) -> list[str]:
    """兼容 DB 行（json 字符串）与模型 dict（原生 list）两种输入。"""
    if raw is None or raw == "":
        return []
    if isinstance(raw, (list, tuple)):
        return [str(x) for x in raw]
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return []
    if isinstance(parsed, list):
        return [str(x) for x in parsed]
    return []


def _parse_json_dict(raw: Any) -> dict[str, Any]:
    """解析 JSON dict（DB 字符串或原生 dict）。"""
    if raw is None or raw == "":
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


# ---------------------------------------------------------------------------
# ValidationPlan
# ---------------------------------------------------------------------------

@dataclass
class ValidationPlan:
    """某 project/version/stage 的验证计划。

    核心字段：
    - tenant_id, project_id：作用域
    - stable_id：稳定标识
    - version/revision：版本
    - lifecycle_status：生命周期
    - stage：EVT/DVT/PVT
    - title, objective：描述
    - required：是否必需
    - owner：负责人
    - source/provenance：来源
    - optimistic_version：乐观锁
    """

    plan_id: str
    tenant_id: str = "default"
    project_id: str = "default"
    stable_id: str = ""
    version: str = "1.0"
    revision: int = 1
    lifecycle_status: str = PLAN_LIFECYCLE_DRAFT
    stage: str = STAGE_EVT
    title: str = ""
    objective: str = ""
    required: bool = True
    owner: str = ""
    source: str = ""
    provenance: str = ""
    created_at: str | None = None
    updated_at: str | None = None
    optimistic_version: int = 1

    def __post_init__(self) -> None:
        if self.stage and self.stage not in VALIDATION_STAGES:
            raise ValueError(
                f"invalid stage {self.stage!r}; "
                f"expected one of {sorted(VALIDATION_STAGES)}")
        if self.lifecycle_status not in PLAN_LIFECYCLE_STATUSES:
            raise ValueError(f"invalid lifecycle_status {self.lifecycle_status!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id, "tenant_id": self.tenant_id,
            "project_id": self.project_id, "stable_id": self.stable_id,
            "version": self.version, "revision": self.revision,
            "lifecycle_status": self.lifecycle_status, "stage": self.stage,
            "title": self.title, "objective": self.objective,
            "required": self.required, "owner": self.owner,
            "source": self.source, "provenance": self.provenance,
            "created_at": self.created_at, "updated_at": self.updated_at,
            "optimistic_version": self.optimistic_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ValidationPlan:
        return cls(
            plan_id=data["plan_id"],
            tenant_id=data.get("tenant_id", "default"),
            project_id=data.get("project_id", "default"),
            stable_id=data.get("stable_id", ""),
            version=data.get("version", "1.0"),
            revision=data.get("revision", 1),
            lifecycle_status=data.get("lifecycle_status", PLAN_LIFECYCLE_DRAFT),
            stage=data.get("stage", STAGE_EVT),
            title=data.get("title", ""),
            objective=data.get("objective", ""),
            required=bool(data.get("required", True)),
            owner=data.get("owner", ""),
            source=data.get("source", ""),
            provenance=data.get("provenance", ""),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            optimistic_version=data.get("optimistic_version", 1),
        )


# ---------------------------------------------------------------------------
# ValidationTest
# ---------------------------------------------------------------------------

@dataclass
class ValidationTest:
    """可重复执行的验证定义。

    核心字段：
    - test_id：稳定标识
    - plan_id：关联计划
    - name：名称
    - stage：阶段
    - category：类别
    - procedure/method：测试方法
    - requirement_refs：关联需求
    - ctq_refs：关键质量特性
    - pass_criteria：通过标准（人类可读 + 机器可判断）
    - measurement/unit：测量值
    - lower/upper/tolerance：限值
    - required：是否必需
    - evidence_requirements：证据要求
    - test_equipment：测试设备/环境
    - version：版本
    - lifecycle_state：生命周期
    """

    test_id: str
    tenant_id: str = "default"
    project_id: str = "default"
    plan_id: str = ""
    name: str = ""
    stage: str = STAGE_EVT
    category: str = ""
    procedure: str = ""
    method: str = ""
    requirement_refs: list[str] = field(default_factory=list)
    ctq_refs: list[str] = field(default_factory=list)
    pass_criteria: str = ""
    # 机器可判断字段
    measurement: str | None = None
    unit: str | None = None
    lower_limit: float | None = None
    upper_limit: float | None = None
    tolerance: float | None = None
    # 元数据
    required: bool = True
    evidence_requirements: str = ""
    test_equipment: str = ""
    version: str = "1.0"
    lifecycle_state: str = TEST_LIFECYCLE_ACTIVE
    created_at: str | None = None
    updated_at: str | None = None

    def __post_init__(self) -> None:
        if self.stage and self.stage not in VALIDATION_STAGES:
            raise ValueError(f"invalid stage {self.stage!r}")
        if self.lifecycle_state not in TEST_LIFECYCLE_STATUSES:
            raise ValueError(f"invalid lifecycle_state {self.lifecycle_state!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_id": self.test_id, "tenant_id": self.tenant_id,
            "project_id": self.project_id, "plan_id": self.plan_id,
            "name": self.name, "stage": self.stage, "category": self.category,
            "procedure": self.procedure, "method": self.method,
            "requirement_refs": self.requirement_refs,
            "ctq_refs": self.ctq_refs,
            "pass_criteria": self.pass_criteria,
            "measurement": self.measurement, "unit": self.unit,
            "lower_limit": self.lower_limit, "upper_limit": self.upper_limit,
            "tolerance": self.tolerance,
            "required": self.required,
            "evidence_requirements": self.evidence_requirements,
            "test_equipment": self.test_equipment,
            "version": self.version, "lifecycle_state": self.lifecycle_state,
            "created_at": self.created_at, "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ValidationTest:
        return cls(
            test_id=data["test_id"],
            tenant_id=data.get("tenant_id", "default"),
            project_id=data.get("project_id", "default"),
            plan_id=data.get("plan_id", ""),
            name=data.get("name", ""),
            stage=data.get("stage", STAGE_EVT),
            category=data.get("category", ""),
            procedure=data.get("procedure", ""),
            method=data.get("method", ""),
            requirement_refs=_parse_json_list(data.get("requirement_refs_json")
                                              or data.get("requirement_refs")),
            ctq_refs=_parse_json_list(data.get("ctq_refs_json")
                                      or data.get("ctq_refs")),
            pass_criteria=data.get("pass_criteria", ""),
            measurement=data.get("measurement"),
            unit=data.get("unit"),
            lower_limit=data.get("lower_limit"),
            upper_limit=data.get("upper_limit"),
            tolerance=data.get("tolerance"),
            required=bool(data.get("required", True)),
            evidence_requirements=data.get("evidence_requirements", ""),
            test_equipment=data.get("test_equipment", ""),
            version=data.get("version", "1.0"),
            lifecycle_state=data.get("lifecycle_state", TEST_LIFECYCLE_ACTIVE),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


# ---------------------------------------------------------------------------
# ValidationRun
# ---------------------------------------------------------------------------

@dataclass
class ValidationRun:
    """一次实际执行。

    核心字段：
    - run_id：执行标识
    - test_id：关联测试
    - tested_artifact_version：被测制品版本
    - tested_artifact_hash：被测制品哈希
    - operator/provider：执行者
    - started/finished：时间
    - environment：环境
    - execution_status：执行状态
    - idempotency_key：幂等键
    - external_operation_id：外部操作 ID
    """

    run_id: str
    tenant_id: str = "default"
    project_id: str = "default"
    test_id: str = ""
    tested_artifact_version: str = ""
    tested_artifact_hash: str = ""
    operator: str = ""
    provider: str = ""
    started_at: str | None = None
    finished_at: str | None = None
    environment: str = ""
    execution_status: str = RESULT_NOT_RUN
    idempotency_key: str = ""
    external_operation_id: str = ""
    created_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id, "tenant_id": self.tenant_id,
            "project_id": self.project_id, "test_id": self.test_id,
            "tested_artifact_version": self.tested_artifact_version,
            "tested_artifact_hash": self.tested_artifact_hash,
            "operator": self.operator, "provider": self.provider,
            "started_at": self.started_at, "finished_at": self.finished_at,
            "environment": self.environment,
            "execution_status": self.execution_status,
            "idempotency_key": self.idempotency_key,
            "external_operation_id": self.external_operation_id,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ValidationRun:
        return cls(
            run_id=data["run_id"],
            tenant_id=data.get("tenant_id", "default"),
            project_id=data.get("project_id", "default"),
            test_id=data.get("test_id", ""),
            tested_artifact_version=data.get("tested_artifact_version", ""),
            tested_artifact_hash=data.get("tested_artifact_hash", ""),
            operator=data.get("operator", ""),
            provider=data.get("provider", ""),
            started_at=data.get("started_at"),
            finished_at=data.get("finished_at"),
            environment=data.get("environment", ""),
            execution_status=data.get("execution_status", RESULT_NOT_RUN),
            idempotency_key=data.get("idempotency_key", ""),
            external_operation_id=data.get("external_operation_id", ""),
            created_at=data.get("created_at"),
        )


# ---------------------------------------------------------------------------
# ValidationResult
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    """一次测试的判断结果。

    核心字段：
    - result_id：结果标识
    - run_id：关联执行
    - result_status：结果状态
    - measured_values：测量值
    - units：单位
    - pass/fail evaluation：通过/失败评估
    - evidence_references：证据引用
    - raw_artifact_hash：原始制品哈希
    - reason：原因
    - evaluator：评估者
    - evaluated_at：评估时间
    - stale：是否过时
    """

    result_id: str
    tenant_id: str = "default"
    project_id: str = "default"
    run_id: str = ""
    test_id: str = ""
    result_status: str = RESULT_NOT_RUN
    measured_values: str = ""
    units: str = ""
    pass_evaluation: str = ""
    evidence_references: list[str] = field(default_factory=list)
    raw_artifact_hash: str = ""
    reason: str = ""
    evaluator: str = ""
    evaluated_at: str | None = None
    stale: bool = False
    stale_reason: str = ""
    created_at: str | None = None
    updated_at: str | None = None

    def __post_init__(self) -> None:
        if self.result_status not in RESULT_STATUSES:
            raise ValueError(f"invalid result_status {self.result_status!r}")

    def is_effective_pass(self) -> bool:
        """判断是否为有效 PASS（非 stale、非 incomplete）。"""
        return self.result_status == RESULT_PASS and not self.stale

    def is_blocking(self) -> bool:
        """判断是否阻塞 readiness。"""
        return self.result_status in BLOCKING_STATUSES

    def to_dict(self) -> dict[str, Any]:
        return {
            "result_id": self.result_id, "tenant_id": self.tenant_id,
            "project_id": self.project_id, "run_id": self.run_id,
            "test_id": self.test_id, "result_status": self.result_status,
            "measured_values": self.measured_values, "units": self.units,
            "pass_evaluation": self.pass_evaluation,
            "evidence_references": self.evidence_references,
            "raw_artifact_hash": self.raw_artifact_hash,
            "reason": self.reason, "evaluator": self.evaluator,
            "evaluated_at": self.evaluated_at, "stale": self.stale,
            "stale_reason": self.stale_reason,
            "created_at": self.created_at, "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ValidationResult:
        return cls(
            result_id=data["result_id"],
            tenant_id=data.get("tenant_id", "default"),
            project_id=data.get("project_id", "default"),
            run_id=data.get("run_id", ""),
            test_id=data.get("test_id", ""),
            result_status=data.get("result_status", RESULT_NOT_RUN),
            measured_values=data.get("measured_values", ""),
            units=data.get("units", ""),
            pass_evaluation=data.get("pass_evaluation", ""),
            evidence_references=_parse_json_list(
                data.get("evidence_references_json")
                or data.get("evidence_references")),
            raw_artifact_hash=data.get("raw_artifact_hash", ""),
            reason=data.get("reason", ""),
            evaluator=data.get("evaluator", ""),
            evaluated_at=data.get("evaluated_at"),
            stale=bool(data.get("stale", False)),
            stale_reason=data.get("stale_reason", ""),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


__all__ = [
    "RESULT_NOT_RUN", "RESULT_RUNNING", "RESULT_PASS", "RESULT_FAIL",
    "RESULT_HOLD", "RESULT_NOT_VERIFIED", "RESULT_STALE", "RESULT_IMPORT_ERROR",
    "RESULT_STATUSES", "EFFECTIVE_PASS_STATUSES", "BLOCKING_STATUSES",
    "INCOMPLETE_STATUSES",
    "STAGE_EVT", "STAGE_DVT", "STAGE_PVT", "VALIDATION_STAGES",
    "PLAN_LIFECYCLE_DRAFT", "PLAN_LIFECYCLE_ACTIVE", "PLAN_LIFECYCLE_COMPLETED",
    "PLAN_LIFECYCLE_CANCELLED", "PLAN_LIFECYCLE_STATUSES",
    "TEST_LIFECYCLE_DRAFT", "TEST_LIFECYCLE_ACTIVE", "TEST_LIFECYCLE_RETIRED",
    "TEST_LIFECYCLE_STATUSES",
    "ValidationPlan", "ValidationTest", "ValidationRun", "ValidationResult",
]
