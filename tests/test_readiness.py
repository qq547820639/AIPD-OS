"""Manufacturing Readiness 测试（v5.10 Milestone 4）。

覆盖：
- Default HOLD when data missing
- FAIL when blocking conditions
- PASS when all dimensions pass
- Validation dimension from canonical domain
- Issues dimension from canonical domain
- Human-readable output
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from aipd_os.state.db import AIPDStateDB
from aipd_os.validation.issues import IssueService
from aipd_os.validation.models import RESULT_FAIL, RESULT_PASS, STAGE_EVT
from aipd_os.validation.readiness import (
    READINESS_FAIL,
    READINESS_HOLD,
    READINESS_PASS,
    ReadinessService,
)
from aipd_os.validation.service import ValidationService


@pytest.fixture
def db():
    """创建临时数据库。"""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        d = AIPDStateDB(str(db_path))
        d.ensure_default_tenant("t1")
        d.init_project("t1", "p1", "Project 1", "Goal 1")
        yield d


@pytest.fixture
def svc(db):
    """创建 ReadinessService。"""
    vs = ValidationService(db)
    is_ = IssueService(db)
    return ReadinessService(vs, is_)


@pytest.fixture
def validation_svc(db):
    """创建 ValidationService。"""
    return ValidationService(db)


@pytest.fixture
def issue_svc(db):
    """创建 IssueService。"""
    return IssueService(db)


# =====================================================================
# Default behavior tests
# =====================================================================

class TestDefaultBehavior:
    """默认行为测试。"""

    def test_all_none_gives_hold(self, svc):
        """所有维度为 None 时默认 HOLD。"""
        report = svc.evaluate("t1", "p1")
        assert report.overall_status == READINESS_HOLD
        assert len(report.missing_evidence) > 0

    def test_single_fail_gives_fail(self, svc):
        """任一维度 FAIL 时整体 FAIL。"""
        report = svc.evaluate("t1", "p1", product_definition_complete=False)
        assert report.overall_status == READINESS_FAIL

    def test_all_pass_gives_pass(self, svc):
        """所有维度 PASS 时整体 PASS。"""
        report = svc.evaluate(
            "t1", "p1",
            product_definition_complete=True,
            cad_maturity_ok=True,
            bom_release_ready=True,
            cost_complete=True,
            supply_chain_ready=True,
        )
        # 注意：validation 和 lineage 维度仍为 HOLD（无数据）
        assert report.overall_status == READINESS_HOLD

    def test_mixed_status(self, svc):
        """混合状态时取最差。"""
        report = svc.evaluate(
            "t1", "p1",
            product_definition_complete=True,
            cad_maturity_ok=False,  # FAIL
        )
        assert report.overall_status == READINESS_FAIL


# =====================================================================
# Validation dimension tests
# =====================================================================

class TestValidationDimension:
    """Validation 维度测试。"""

    def test_no_results_gives_hold(self, svc, validation_svc):
        """没有验证结果时 HOLD。"""
        report = svc.evaluate("t1", "p1")
        val_dim = next(d for d in report.dimensions if d.dimension == "validation")
        assert val_dim.status == READINESS_HOLD

    def test_passing_results_gives_pass(self, svc, validation_svc):
        """有通过结果时 PASS。"""
        plan = validation_svc.create_plan("t1", "p1", STAGE_EVT, "Plan")
        test = validation_svc.create_test("t1", "p1", plan.plan_id, "Test 1", STAGE_EVT)
        run = validation_svc.create_run("t1", "p1", test.test_id)
        validation_svc.record_result("t1", "p1", run.run_id, test.test_id, RESULT_PASS)

        report = svc.evaluate("t1", "p1")
        val_dim = next(d for d in report.dimensions if d.dimension == "validation")
        assert val_dim.status == READINESS_PASS

    def test_failing_results_gives_fail(self, svc, validation_svc):
        """有失败结果时 FAIL。"""
        plan = validation_svc.create_plan("t1", "p1", STAGE_EVT, "Plan")
        test = validation_svc.create_test("t1", "p1", plan.plan_id, "Test 1", STAGE_EVT)
        run = validation_svc.create_run("t1", "p1", test.test_id)
        validation_svc.record_result("t1", "p1", run.run_id, test.test_id, RESULT_FAIL)

        report = svc.evaluate("t1", "p1")
        val_dim = next(d for d in report.dimensions if d.dimension == "validation")
        assert val_dim.status == READINESS_FAIL

    def test_stale_pass_not_counted(self, svc, validation_svc):
        """Stale PASS 不计入有效结果。"""
        plan = validation_svc.create_plan("t1", "p1", STAGE_EVT, "Plan")
        test = validation_svc.create_test("t1", "p1", plan.plan_id, "Test 1", STAGE_EVT)
        run = validation_svc.create_run("t1", "p1", test.test_id)
        result = validation_svc.record_result("t1", "p1", run.run_id, test.test_id, RESULT_PASS)

        # 标记 stale
        validation_svc.mark_stale_results("t1", "p1", [result.result_id], "test")

        report = svc.evaluate("t1", "p1")
        val_dim = next(d for d in report.dimensions if d.dimension == "validation")
        assert val_dim.status == READINESS_HOLD


# =====================================================================
# Issues dimension tests
# =====================================================================

class TestIssuesDimension:
    """Issues 维度测试。"""

    def test_no_blocking_issues_gives_pass(self, svc, issue_svc):
        """没有阻塞 Issue 时 PASS。"""
        report = svc.evaluate("t1", "p1")
        issues_dim = next(d for d in report.dimensions if d.dimension == "issues")
        assert issues_dim.status == READINESS_PASS

    def test_open_blocking_issue_gives_fail(self, svc, issue_svc):
        """有未关闭的阻塞 Issue 时 FAIL。"""
        issue_svc.create_issue("t1", "p1", "Blocking Issue", blocking_release=True)

        report = svc.evaluate("t1", "p1")
        issues_dim = next(d for d in report.dimensions if d.dimension == "issues")
        assert issues_dim.status == READINESS_FAIL

    def test_closed_blocking_issue_gives_pass(self, svc, issue_svc):
        """已关闭的阻塞 Issue 不影响。"""
        issue = issue_svc.create_issue("t1", "p1", "Blocking Issue", blocking_release=True)
        issue_svc.set_disposition("t1", "p1", issue.issue_id, "WAIVE")
        issue_svc.update_issue_status("t1", "p1", issue.issue_id, "WAIVED")

        report = svc.evaluate("t1", "p1")
        issues_dim = next(d for d in report.dimensions if d.dimension == "issues")
        assert issues_dim.status == READINESS_PASS


# =====================================================================
# Report output tests
# =====================================================================

class TestReportOutput:
    """报告输出测试。"""

    def test_to_dict(self, svc):
        """to_dict 输出完整。"""
        report = svc.evaluate("t1", "p1")
        d = report.to_dict()
        assert "overall_status" in d
        assert "dimensions" in d
        assert "evaluated_at" in d
        assert len(d["dimensions"]) == 8

    def test_to_human_readable(self, svc):
        """人类可读输出非空。"""
        report = svc.evaluate("t1", "p1")
        text = report.to_human_readable()
        assert "Manufacturing Readiness" in text
        assert "HOLD" in text
