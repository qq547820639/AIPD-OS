"""Canonical Validation Domain 测试（v5.10 Milestone 1）。

覆盖：
- 模型验证（状态枚举、生命周期、阶段）
- CRUD 操作（Plan/Test/Run/Result）
- 诚实性语义（stale propagation、effective pass、blocking）
- 多租户隔离
- 负路径（无效状态、缺失数据）
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from aipd_os.state.db import AIPDStateDB
from aipd_os.validation.models import (
    BLOCKING_STATUSES,
    EFFECTIVE_PASS_STATUSES,
    INCOMPLETE_STATUSES,
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
    VALIDATION_STAGES,
    ValidationPlan,
    ValidationResult,
    ValidationTest,
)
from aipd_os.validation.service import ValidationService


@pytest.fixture
def db():
    """创建临时数据库。"""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        d = AIPDStateDB(str(db_path))
        d.ensure_default_tenant("t1")
        d.ensure_default_tenant("t2")
        d.init_project("t1", "p1", "Project 1", "Goal 1")
        d.init_project("t1", "p2", "Project 2", "Goal 2")
        d.init_project("t2", "p1", "Project 1 T2", "Goal 1 T2")
        yield d


@pytest.fixture
def svc(db):
    """创建 ValidationService。"""
    return ValidationService(db)


# =====================================================================
# Model validation tests
# =====================================================================

class TestModelValidation:
    """模型验证测试。"""

    def test_result_statuses_cover_all_expected(self):
        """结果状态必须覆盖所有预期状态。"""
        expected = {
            "NOT_RUN", "RUNNING", "PASS", "FAIL",
            "HOLD", "NOT_VERIFIED", "STALE", "IMPORT_ERROR",
        }
        assert expected == RESULT_STATUSES

    def test_validation_stages(self):
        """验证阶段必须包含 EVT/DVT/PVT。"""
        assert {"EVT", "DVT", "PVT"} == VALIDATION_STAGES

    def test_effective_pass_statuses(self):
        """有效通过状态只包含 PASS。"""
        assert {RESULT_PASS} == EFFECTIVE_PASS_STATUSES

    def test_blocking_statuses(self):
        """阻塞状态必须包含 FAIL/HOLD/IMPORT_ERROR。"""
        assert RESULT_FAIL in BLOCKING_STATUSES
        assert RESULT_HOLD in BLOCKING_STATUSES
        assert RESULT_IMPORT_ERROR in BLOCKING_STATUSES

    def test_incomplete_statuses(self):
        """未完成状态必须包含 NOT_RUN/RUNNING/NOT_VERIFIED/STALE。"""
        assert RESULT_NOT_RUN in INCOMPLETE_STATUSES
        assert RESULT_RUNNING in INCOMPLETE_STATUSES
        assert RESULT_NOT_VERIFIED in INCOMPLETE_STATUSES
        assert RESULT_STALE in INCOMPLETE_STATUSES

    def test_plan_invalid_stage_raises(self):
        """无效阶段必须抛出 ValueError。"""
        with pytest.raises(ValueError, match="invalid stage"):
            ValidationPlan(plan_id="p1", stage="INVALID")

    def test_plan_invalid_lifecycle_raises(self):
        """无效生命周期必须抛出 ValueError。"""
        with pytest.raises(ValueError, match="invalid lifecycle_status"):
            ValidationPlan(plan_id="p1", lifecycle_status="INVALID")

    def test_test_invalid_stage_raises(self):
        """无效阶段必须抛出 ValueError。"""
        with pytest.raises(ValueError, match="invalid stage"):
            ValidationTest(test_id="t1", stage="INVALID")

    def test_result_invalid_status_raises(self):
        """无效结果状态必须抛出 ValueError。"""
        with pytest.raises(ValueError, match="invalid result_status"):
            ValidationResult(result_id="r1", result_status="INVALID")

    def test_result_is_effective_pass(self):
        """有效 PASS 必须是非 stale 的 PASS。"""
        r = ValidationResult(result_id="r1", result_status=RESULT_PASS, stale=False)
        assert r.is_effective_pass()

        # stale 的 PASS 不是有效 PASS
        r.stale = True
        assert not r.is_effective_pass()

        # FAIL 不是有效 PASS
        r.stale = False
        r.result_status = RESULT_FAIL
        assert not r.is_effective_pass()

    def test_result_is_blocking(self):
        """阻塞状态必须正确判断。"""
        for status in BLOCKING_STATUSES:
            r = ValidationResult(result_id="r1", result_status=status)
            assert r.is_blocking(), f"{status} should be blocking"

        for status in (RESULT_NOT_RUN, RESULT_PASS, RESULT_STALE):
            r = ValidationResult(result_id="r1", result_status=status)
            assert not r.is_blocking(), f"{status} should not be blocking"

    def test_model_roundtrip(self):
        """模型 to_dict/from_dict 往返必须一致。"""
        plan = ValidationPlan(
            plan_id="p1", tenant_id="t1", project_id="proj",
            stage=STAGE_EVT, title="Test Plan",
        )
        d = plan.to_dict()
        plan2 = ValidationPlan.from_dict(d)
        assert plan2.plan_id == plan.plan_id
        assert plan2.stage == plan.stage

        test = ValidationTest(
            test_id="t1", tenant_id="t1", project_id="proj",
            plan_id="p1", name="Test 1", stage=STAGE_DVT,
            requirement_refs=["req1", "req2"],
        )
        d = test.to_dict()
        test2 = ValidationTest.from_dict(d)
        assert test2.test_id == test.test_id
        assert test2.requirement_refs == ["req1", "req2"]

        result = ValidationResult(
            result_id="r1", tenant_id="t1", project_id="proj",
            run_id="run1", test_id="t1", result_status=RESULT_PASS,
            evidence_references=["ev1"],
        )
        d = result.to_dict()
        result2 = ValidationResult.from_dict(d)
        assert result2.result_id == result.result_id
        assert result2.evidence_references == ["ev1"]


# =====================================================================
# CRUD tests
# =====================================================================

class TestCRUD:
    """CRUD 操作测试。"""

    def test_create_and_get_plan(self, svc):
        """创建和获取验证计划。"""
        plan = svc.create_plan("t1", "p1", STAGE_EVT, "EVT Plan", "验证 EVT 阶段")
        assert plan.plan_id.startswith("vplan_")
        assert plan.stage == STAGE_EVT

        got = svc.get_plan("t1", "p1", plan.plan_id)
        assert got is not None
        assert got.title == "EVT Plan"

    def test_list_plans(self, svc):
        """列出验证计划。"""
        svc.create_plan("t1", "p1", STAGE_EVT, "EVT Plan")
        svc.create_plan("t1", "p1", STAGE_DVT, "DVT Plan")
        svc.create_plan("t1", "p2", STAGE_EVT, "P2 EVT Plan")

        plans = svc.list_plans("t1", "p1")
        assert len(plans) == 2

        plans_p2 = svc.list_plans("t1", "p2")
        assert len(plans_p2) == 1

    def test_create_and_get_test(self, svc):
        """创建和获取验证测试。"""
        plan = svc.create_plan("t1", "p1", STAGE_EVT, "EVT Plan")
        test = svc.create_test(
            "t1", "p1", plan.plan_id, "Tensile Test", STAGE_EVT,
            category="mechanical", pass_criteria=">=100MPa",
            requirement_refs=["req1"],
        )
        assert test.test_id.startswith("vtest_")

        got = svc.get_test("t1", "p1", test.test_id)
        assert got is not None
        assert got.name == "Tensile Test"
        assert got.requirement_refs == ["req1"]

    def test_list_tests_by_plan(self, svc):
        """按计划列出测试。"""
        plan = svc.create_plan("t1", "p1", STAGE_EVT, "EVT Plan")
        svc.create_test("t1", "p1", plan.plan_id, "Test 1", STAGE_EVT)
        svc.create_test("t1", "p1", plan.plan_id, "Test 2", STAGE_EVT)

        tests = svc.list_tests("t1", "p1", plan_id=plan.plan_id)
        assert len(tests) == 2

    def test_create_and_complete_run(self, svc):
        """创建和完成执行记录。"""
        plan = svc.create_plan("t1", "p1", STAGE_EVT, "EVT Plan")
        test = svc.create_test("t1", "p1", plan.plan_id, "Test 1", STAGE_EVT)

        run = svc.create_run(
            "t1", "p1", test.test_id,
            tested_artifact_version="v1.0",
            tested_artifact_hash="abc123",
        )
        assert run.run_id.startswith("vrun_")
        assert run.execution_status == RESULT_NOT_RUN

        completed = svc.complete_run("t1", "p1", run.run_id, RESULT_PASS)
        assert completed is not None
        assert completed.execution_status == RESULT_PASS
        assert completed.finished_at is not None

    def test_record_and_get_result(self, svc):
        """记录和获取验证结果。"""
        plan = svc.create_plan("t1", "p1", STAGE_EVT, "EVT Plan")
        test = svc.create_test("t1", "p1", plan.plan_id, "Test 1", STAGE_EVT)
        run = svc.create_run("t1", "p1", test.test_id)

        result = svc.record_result(
            "t1", "p1", run.run_id, test.test_id, RESULT_PASS,
            measured_values="150 MPa", units="MPa",
            pass_evaluation=">=100 MPa: PASS",
            evidence_references=["ev1", "ev2"],
        )
        assert result.result_id.startswith("vres_")

        latest = svc.get_latest_result("t1", "p1", test.test_id)
        assert latest is not None
        assert latest.result_status == RESULT_PASS
        assert latest.measured_values == "150 MPa"

    def test_list_results(self, svc):
        """列出验证结果。"""
        plan = svc.create_plan("t1", "p1", STAGE_EVT, "EVT Plan")
        test = svc.create_test("t1", "p1", plan.plan_id, "Test 1", STAGE_EVT)
        run1 = svc.create_run("t1", "p1", test.test_id)
        run2 = svc.create_run("t1", "p1", test.test_id)

        svc.record_result("t1", "p1", run1.run_id, test.test_id, RESULT_FAIL)
        svc.record_result("t1", "p1", run2.run_id, test.test_id, RESULT_PASS)

        results = svc.list_results("t1", "p1", test_id=test.test_id)
        assert len(results) == 2


# =====================================================================
# Stale propagation tests（§3.2 honest truth semantics）
# =====================================================================

class TestStalePropagation:
    """Stale 传播测试。"""

    def test_mark_stale_by_artifact_change(self, svc):
        """制品 revision 变化时自动标记 stale。"""
        plan = svc.create_plan("t1", "p1", STAGE_EVT, "EVT Plan")
        test = svc.create_test("t1", "p1", plan.plan_id, "Test 1", STAGE_EVT)

        # 用旧 artifact hash 创建执行和结果
        run = svc.create_run(
            "t1", "p1", test.test_id,
            tested_artifact_hash="old_hash_123",
        )
        svc.record_result("t1", "p1", run.run_id, test.test_id, RESULT_PASS)

        # 验证结果是有效的
        latest = svc.get_latest_result("t1", "p1", test.test_id)
        assert latest is not None
        assert not latest.stale

        # 制品 revision 变化
        count = svc.mark_stale_by_artifact_change(
            "t1", "p1", "old_hash_123", "new_hash_456",
        )
        assert count == 1

        # 结果现在应该是 stale
        latest = svc.get_latest_result("t1", "p1", test.test_id)
        assert latest is None  # get_latest_result 过滤 stale

    def test_mark_stale_results(self, svc):
        """显式标记结果为 stale。"""
        plan = svc.create_plan("t1", "p1", STAGE_EVT, "EVT Plan")
        test = svc.create_test("t1", "p1", plan.plan_id, "Test 1", STAGE_EVT)
        run = svc.create_run("t1", "p1", test.test_id)
        result = svc.record_result("t1", "p1", run.run_id, test.test_id, RESULT_PASS)

        count = svc.mark_stale_results("t1", "p1", [result.result_id], "manual_review")
        assert count == 1

        # 结果现在应该是 stale
        latest = svc.get_latest_result("t1", "p1", test.test_id)
        assert latest is None

    def test_stale_result_not_effective_pass(self, svc):
        """Stale 结果不能计入有效 PASS。"""
        plan = svc.create_plan("t1", "p1", STAGE_EVT, "EVT Plan")
        test = svc.create_test("t1", "p1", plan.plan_id, "Test 1", STAGE_EVT)
        run = svc.create_run("t1", "p1", test.test_id)
        result = svc.record_result("t1", "p1", run.run_id, test.test_id, RESULT_PASS)

        # 标记 stale
        svc.mark_stale_results("t1", "p1", [result.result_id], "test")

        # get_effective_pass_count 应该返回 0
        count = svc.get_effective_pass_count("t1", "p1", test.test_id)
        assert count == 0


# =====================================================================
# Query helper tests
# =====================================================================

class TestQueryHelpers:
    """查询辅助函数测试。"""

    def test_get_required_tests(self, svc):
        """获取计划中必需的测试。"""
        plan = svc.create_plan("t1", "p1", STAGE_EVT, "EVT Plan")
        svc.create_test("t1", "p1", plan.plan_id, "Required Test", STAGE_EVT, required=True)
        svc.create_test("t1", "p1", plan.plan_id, "Optional Test", STAGE_EVT, required=False)

        required = svc.get_required_tests_for_plan("t1", "p1", plan.plan_id)
        assert len(required) == 1
        assert required[0].name == "Required Test"

    def test_get_blocking_results(self, svc):
        """获取阻塞结果。"""
        plan = svc.create_plan("t1", "p1", STAGE_EVT, "EVT Plan")
        test = svc.create_test("t1", "p1", plan.plan_id, "Test 1", STAGE_EVT)

        run1 = svc.create_run("t1", "p1", test.test_id)
        svc.record_result("t1", "p1", run1.run_id, test.test_id, RESULT_FAIL)

        run2 = svc.create_run("t1", "p1", test.test_id)
        svc.record_result("t1", "p1", run2.run_id, test.test_id, RESULT_PASS)

        blocking = svc.get_blocking_results("t1", "p1")
        assert len(blocking) == 1
        assert blocking[0].result_status == RESULT_FAIL


# =====================================================================
# Multi-tenant isolation tests
# =====================================================================

class TestMultiTenantIsolation:
    """多租户隔离测试。"""

    def test_plans_isolated_by_tenant(self, svc):
        """不同租户的计划互相隔离。"""
        svc.create_plan("t1", "p1", STAGE_EVT, "T1 Plan")
        svc.create_plan("t2", "p1", STAGE_EVT, "T2 Plan")

        t1_plans = svc.list_plans("t1", "p1")
        t2_plans = svc.list_plans("t2", "p1")
        assert len(t1_plans) == 1
        assert len(t2_plans) == 1
        assert t1_plans[0].title == "T1 Plan"
        assert t2_plans[0].title == "T2 Plan"

    def test_results_isolated_by_project(self, svc):
        """不同项目的结果互相隔离。"""
        plan1 = svc.create_plan("t1", "p1", STAGE_EVT, "P1 Plan")
        plan2 = svc.create_plan("t1", "p2", STAGE_EVT, "P2 Plan")

        test1 = svc.create_test("t1", "p1", plan1.plan_id, "Test 1", STAGE_EVT)
        test2 = svc.create_test("t1", "p2", plan2.plan_id, "Test 2", STAGE_EVT)

        run1 = svc.create_run("t1", "p1", test1.test_id)
        run2 = svc.create_run("t1", "p2", test2.test_id)

        svc.record_result("t1", "p1", run1.run_id, test1.test_id, RESULT_PASS)
        svc.record_result("t1", "p2", run2.run_id, test2.test_id, RESULT_FAIL)

        p1_results = svc.list_results("t1", "p1")
        p2_results = svc.list_results("t1", "p2")
        assert len(p1_results) == 1
        assert len(p2_results) == 1
        assert p1_results[0].result_status == RESULT_PASS
        assert p2_results[0].result_status == RESULT_FAIL


# =====================================================================
# Negative path tests
# =====================================================================

class TestNegativePaths:
    """负路径测试。"""

    def test_invalid_stage_rejected(self, svc):
        """无效阶段必须被拒绝。"""
        with pytest.raises(ValueError, match="invalid stage"):
            svc.create_plan("t1", "p1", "INVALID", "Bad Plan")

    def test_invalid_result_status_rejected(self, svc):
        """无效结果状态必须被拒绝。"""
        plan = svc.create_plan("t1", "p1", STAGE_EVT, "Plan")
        test = svc.create_test("t1", "p1", plan.plan_id, "Test", STAGE_EVT)
        run = svc.create_run("t1", "p1", test.test_id)

        with pytest.raises(ValueError, match="invalid result_status"):
            svc.record_result("t1", "p1", run.run_id, test.test_id, "INVALID")

    def test_get_nonexistent_plan_returns_none(self, svc):
        """获取不存在的计划返回 None。"""
        result = svc.get_plan("t1", "p1", "nonexistent")
        assert result is None

    def test_get_nonexistent_test_returns_none(self, svc):
        """获取不存在的测试返回 None。"""
        result = svc.get_test("t1", "p1", "nonexistent")
        assert result is None

    def test_get_latest_result_no_results_returns_none(self, svc):
        """没有结果时返回 None。"""
        result = svc.get_latest_result("t1", "p1", "nonexistent")
        assert result is None

    def test_complete_nonexistent_run_returns_none(self, svc):
        """完成不存在的执行返回 None。"""
        result = svc.complete_run("t1", "p1", "nonexistent", RESULT_PASS)
        assert result is None

    def test_mark_stale_no_matching_results(self, svc):
        """没有匹配结果时返回 0。"""
        count = svc.mark_stale_by_artifact_change("t1", "p1", "old", "new")
        assert count == 0
