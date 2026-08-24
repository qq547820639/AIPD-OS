"""Validation Service — Canonical Validation Domain 的核心服务层。

提供验证计划、测试、执行和结果的 CRUD 操作，以及诚实性语义：
- 缺测试数据不能 PASS
- stale result 不能计入有效 PASS
- artifact revision 变化后自动标记 stale
- 所有自动判断保存依据

通过 AIPDStateDB 的 validation_* 表存储（migration v13）。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from aipd_os.validation.models import (
    RESULT_PASS,
    RESULT_STATUSES,
    VALIDATION_STAGES,
    ValidationPlan,
    ValidationResult,
    ValidationRun,
    ValidationTest,
)

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class ValidationService:
    """Canonical Validation Service。

    通过 AIPDStateDB 提供验证域的 CRUD 与业务逻辑。
    不创建新的独立数据库。
    """

    def __init__(self, db: Any) -> None:
        """初始化。

        Args:
            db: AIPDStateDB 实例（提供 connect() 方法）
        """
        self._db = db

    # ------------------------------------------------------------------
    # ValidationPlan CRUD
    # ------------------------------------------------------------------

    def create_plan(
        self,
        tenant_id: str,
        project_id: str,
        stage: str,
        title: str,
        objective: str = "",
        required: bool = True,
        owner: str = "",
        source: str = "",
    ) -> ValidationPlan:
        """创建验证计划。"""
        if stage not in VALIDATION_STAGES:
            raise ValueError(f"invalid stage {stage!r}")

        now = _now_iso()
        plan = ValidationPlan(
            plan_id=_new_id("vplan"),
            tenant_id=tenant_id,
            project_id=project_id,
            stage=stage,
            title=title,
            objective=objective,
            required=required,
            owner=owner,
            source=source,
            created_at=now,
            updated_at=now,
        )

        with self._db.connect() as conn:
            conn.execute(
                "INSERT INTO validation_plans "
                "(plan_id, tenant_id, project_id, stable_id, version, revision, "
                "lifecycle_status, stage, title, objective, required, owner, "
                "source, provenance, created_at, updated_at, optimistic_version) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (plan.plan_id, plan.tenant_id, plan.project_id, plan.stable_id,
                 plan.version, plan.revision, plan.lifecycle_status, plan.stage,
                 plan.title, plan.objective, int(plan.required), plan.owner,
                 plan.source, plan.provenance, plan.created_at, plan.updated_at,
                 plan.optimistic_version),
            )
        return plan

    def get_plan(self, tenant_id: str, project_id: str, plan_id: str) -> ValidationPlan | None:
        """获取验证计划。"""
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM validation_plans "
                "WHERE tenant_id=? AND project_id=? AND plan_id=?",
                (tenant_id, project_id, plan_id),
            ).fetchone()
        if row is None:
            return None
        return ValidationPlan.from_dict(dict(row))

    def list_plans(self, tenant_id: str, project_id: str) -> list[ValidationPlan]:
        """列出项目的所有验证计划。"""
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM validation_plans "
                "WHERE tenant_id=? AND project_id=? ORDER BY created_at",
                (tenant_id, project_id),
            ).fetchall()
        return [ValidationPlan.from_dict(dict(r)) for r in rows]

    # ------------------------------------------------------------------
    # ValidationTest CRUD
    # ------------------------------------------------------------------

    def create_test(
        self,
        tenant_id: str,
        project_id: str,
        plan_id: str,
        name: str,
        stage: str,
        category: str = "",
        procedure: str = "",
        pass_criteria: str = "",
        required: bool = True,
        requirement_refs: list[str] | None = None,
        ctq_refs: list[str] | None = None,
    ) -> ValidationTest:
        """创建验证测试定义。"""
        import json as _json

        if stage not in VALIDATION_STAGES:
            raise ValueError(f"invalid stage {stage!r}")

        now = _now_iso()
        test = ValidationTest(
            test_id=_new_id("vtest"),
            tenant_id=tenant_id,
            project_id=project_id,
            plan_id=plan_id,
            name=name,
            stage=stage,
            category=category,
            procedure=procedure,
            pass_criteria=pass_criteria,
            required=required,
            requirement_refs=requirement_refs or [],
            ctq_refs=ctq_refs or [],
            created_at=now,
            updated_at=now,
        )

        with self._db.connect() as conn:
            conn.execute(
                "INSERT INTO validation_tests "
                "(test_id, tenant_id, project_id, plan_id, name, stage, category, "
                "procedure, method, requirement_refs_json, ctq_refs_json, "
                "pass_criteria, measurement, unit, lower_limit, upper_limit, "
                "tolerance, required, evidence_requirements, test_equipment, "
                "version, lifecycle_state, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (test.test_id, test.tenant_id, test.project_id, test.plan_id,
                 test.name, test.stage, test.category, test.procedure, test.method,
                 _json.dumps(test.requirement_refs), _json.dumps(test.ctq_refs),
                 test.pass_criteria, test.measurement, test.unit,
                 test.lower_limit, test.upper_limit, test.tolerance,
                 int(test.required), test.evidence_requirements, test.test_equipment,
                 test.version, test.lifecycle_state, test.created_at, test.updated_at),
            )
        return test

    def get_test(self, tenant_id: str, project_id: str, test_id: str) -> ValidationTest | None:
        """获取验证测试定义。"""
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM validation_tests "
                "WHERE tenant_id=? AND project_id=? AND test_id=?",
                (tenant_id, project_id, test_id),
            ).fetchone()
        if row is None:
            return None
        return ValidationTest.from_dict(dict(row))

    def list_tests(self, tenant_id: str, project_id: str,
                   plan_id: str | None = None) -> list[ValidationTest]:
        """列出验证测试定义。"""
        with self._db.connect() as conn:
            if plan_id:
                rows = conn.execute(
                    "SELECT * FROM validation_tests "
                    "WHERE tenant_id=? AND project_id=? AND plan_id=? "
                    "ORDER BY created_at",
                    (tenant_id, project_id, plan_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM validation_tests "
                    "WHERE tenant_id=? AND project_id=? ORDER BY created_at",
                    (tenant_id, project_id),
                ).fetchall()
        return [ValidationTest.from_dict(dict(r)) for r in rows]

    # ------------------------------------------------------------------
    # ValidationRun CRUD
    # ------------------------------------------------------------------

    def create_run(
        self,
        tenant_id: str,
        project_id: str,
        test_id: str,
        tested_artifact_version: str = "",
        tested_artifact_hash: str = "",
        operator: str = "",
        environment: str = "",
        idempotency_key: str = "",
    ) -> ValidationRun:
        """创建验证执行记录。"""
        now = _now_iso()
        run = ValidationRun(
            run_id=_new_id("vrun"),
            tenant_id=tenant_id,
            project_id=project_id,
            test_id=test_id,
            tested_artifact_version=tested_artifact_version,
            tested_artifact_hash=tested_artifact_hash,
            operator=operator,
            environment=environment,
            idempotency_key=idempotency_key,
            started_at=now,
            created_at=now,
        )

        with self._db.connect() as conn:
            conn.execute(
                "INSERT INTO validation_runs "
                "(run_id, tenant_id, project_id, test_id, "
                "tested_artifact_version, tested_artifact_hash, "
                "operator, provider, started_at, finished_at, environment, "
                "execution_status, idempotency_key, external_operation_id, "
                "created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (run.run_id, run.tenant_id, run.project_id, run.test_id,
                 run.tested_artifact_version, run.tested_artifact_hash,
                 run.operator, run.provider, run.started_at, run.finished_at,
                 run.environment, run.execution_status, run.idempotency_key,
                 run.external_operation_id, run.created_at),
            )
        return run

    def complete_run(self, tenant_id: str, project_id: str,
                     run_id: str, status: str) -> ValidationRun | None:
        """完成执行记录。"""
        now = _now_iso()
        with self._db.connect() as conn:
            conn.execute(
                "UPDATE validation_runs SET finished_at=?, execution_status=? "
                "WHERE tenant_id=? AND project_id=? AND run_id=?",
                (now, status, tenant_id, project_id, run_id),
            )
            row = conn.execute(
                "SELECT * FROM validation_runs "
                "WHERE tenant_id=? AND project_id=? AND run_id=?",
                (tenant_id, project_id, run_id),
            ).fetchone()
        if row is None:
            return None
        return ValidationRun.from_dict(dict(row))

    # ------------------------------------------------------------------
    # ValidationResult CRUD
    # ------------------------------------------------------------------

    def record_result(
        self,
        tenant_id: str,
        project_id: str,
        run_id: str,
        test_id: str,
        result_status: str,
        measured_values: str = "",
        units: str = "",
        pass_evaluation: str = "",
        evidence_references: list[str] | None = None,
        reason: str = "",
        evaluator: str = "",
    ) -> ValidationResult:
        """记录验证结果。

        诚实性约束：
        - result_status 必须是有效状态
        - 缺测试数据不能自动设为 PASS（caller 负责提供依据）
        """
        if result_status not in RESULT_STATUSES:
            raise ValueError(f"invalid result_status {result_status!r}")

        import json as _json

        now = _now_iso()
        result = ValidationResult(
            result_id=_new_id("vres"),
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
            test_id=test_id,
            result_status=result_status,
            measured_values=measured_values,
            units=units,
            pass_evaluation=pass_evaluation,
            evidence_references=evidence_references or [],
            reason=reason,
            evaluator=evaluator,
            evaluated_at=now,
            created_at=now,
            updated_at=now,
        )

        with self._db.connect() as conn:
            conn.execute(
                "INSERT INTO validation_results "
                "(result_id, tenant_id, project_id, run_id, test_id, "
                "result_status, measured_values, units, pass_evaluation, "
                "evidence_references_json, raw_artifact_hash, reason, evaluator, "
                "evaluated_at, stale, stale_reason, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (result.result_id, result.tenant_id, result.project_id,
                 result.run_id, result.test_id, result.result_status,
                 result.measured_values, result.units, result.pass_evaluation,
                 _json.dumps(result.evidence_references),
                 result.raw_artifact_hash, result.reason, result.evaluator,
                 result.evaluated_at, int(result.stale), result.stale_reason,
                 result.created_at, result.updated_at),
            )
        return result

    def get_latest_result(self, tenant_id: str, project_id: str,
                          test_id: str) -> ValidationResult | None:
        """获取指定测试的最新结果。"""
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM validation_results "
                "WHERE tenant_id=? AND project_id=? AND test_id=? "
                "AND stale=0 "
                "ORDER BY evaluated_at DESC LIMIT 1",
                (tenant_id, project_id, test_id),
            ).fetchone()
        if row is None:
            return None
        return ValidationResult.from_dict(dict(row))

    def list_results(self, tenant_id: str, project_id: str,
                     test_id: str | None = None) -> list[ValidationResult]:
        """列出验证结果。"""
        with self._db.connect() as conn:
            if test_id:
                rows = conn.execute(
                    "SELECT * FROM validation_results "
                    "WHERE tenant_id=? AND project_id=? AND test_id=? "
                    "ORDER BY evaluated_at DESC",
                    (tenant_id, project_id, test_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM validation_results "
                    "WHERE tenant_id=? AND project_id=? "
                    "ORDER BY evaluated_at DESC",
                    (tenant_id, project_id),
                ).fetchall()
        return [ValidationResult.from_dict(dict(r)) for r in rows]

    # ------------------------------------------------------------------
    # Stale Propagation（§3.2 honest truth semantics）
    # ------------------------------------------------------------------

    def mark_stale_by_artifact_change(
        self,
        tenant_id: str,
        project_id: str,
        old_artifact_hash: str,
        new_artifact_hash: str,
        reason: str = "artifact_revision_changed",
    ) -> int:
        """当制品 revision 变化时，标记受影响的旧结果为 stale。

        返回被标记 stale 的结果数量。
        """
        now = _now_iso()
        with self._db.connect() as conn:
            # 找到关联旧 artifact hash 的非 stale 有效结果
            cursor = conn.execute(
                "UPDATE validation_results SET stale=1, stale_reason=?, updated_at=? "
                "WHERE tenant_id=? AND project_id=? AND stale=0 "
                "AND run_id IN ("
                "  SELECT run_id FROM validation_runs "
                "  WHERE tested_artifact_hash=?"
                ")",
                (reason, now, tenant_id, project_id, old_artifact_hash),
            )
            count = int(cursor.rowcount)
        if count > 0:
            logger.info(
                "Marked %d validation results as stale due to artifact change "
                "%s → %s", count, old_artifact_hash[:12], new_artifact_hash[:12])
        return count

    def mark_stale_results(self, tenant_id: str, project_id: str,
                           result_ids: list[str], reason: str) -> int:
        """显式标记指定结果为 stale。"""
        now = _now_iso()
        count: int = 0
        with self._db.connect() as conn:
            for rid in result_ids:
                cursor = conn.execute(
                    "UPDATE validation_results SET stale=1, stale_reason=?, "
                    "updated_at=? "
                    "WHERE tenant_id=? AND project_id=? AND result_id=? AND stale=0",
                    (reason, now, tenant_id, project_id, rid),
                )
                count += int(cursor.rowcount)
        return count

    # ------------------------------------------------------------------
    # Query helpers（供 readiness 计算使用）
    # ------------------------------------------------------------------

    def get_required_tests_for_plan(self, tenant_id: str, project_id: str,
                                    plan_id: str) -> list[ValidationTest]:
        """获取计划中所有必需的测试。"""
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM validation_tests "
                "WHERE tenant_id=? AND project_id=? AND plan_id=? AND required=1 "
                "AND lifecycle_state='active' "
                "ORDER BY created_at",
                (tenant_id, project_id, plan_id),
            ).fetchall()
        return [ValidationTest.from_dict(dict(r)) for r in rows]

    def get_effective_pass_count(self, tenant_id: str, project_id: str,
                                 test_id: str) -> int:
        """获取指定测试的有效 PASS 结果数（非 stale）。"""
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM validation_results "
                "WHERE tenant_id=? AND project_id=? AND test_id=? "
                "AND result_status=? AND stale=0",
                (tenant_id, project_id, test_id, RESULT_PASS),
            ).fetchone()
        return row["cnt"] if row else 0

    def get_blocking_results(self, tenant_id: str, project_id: str) -> list[ValidationResult]:
        """获取所有阻塞 readiness 的结果（FAIL/HOLD/IMPORT_ERROR）。"""
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM validation_results "
                "WHERE tenant_id=? AND project_id=? AND stale=0 "
                "AND result_status IN ('FAIL','HOLD','IMPORT_ERROR') "
                "ORDER BY evaluated_at DESC",
                (tenant_id, project_id),
            ).fetchall()
        return [ValidationResult.from_dict(dict(r)) for r in rows]


__all__ = ["ValidationService"]
