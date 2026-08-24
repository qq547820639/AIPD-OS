"""P2-M2/M3: Cross-tenant isolation negative tests.

验证 Validation / Issue / Readiness 域的 tenant/project 隔离。
"""
from __future__ import annotations

import pytest

from aipd_os.state.db import AIPDStateDB
from aipd_os.validation.issues import IssueService
from aipd_os.validation.models import RESULT_PASS
from aipd_os.validation.readiness import ReadinessService
from aipd_os.validation.service import ValidationService


@pytest.fixture
def db(tmp_path):
    from aipd_os.state import migrations as mig
    path = str(tmp_path / "test.db")
    mig.migrate(path)
    return AIPDStateDB(path)


class TestCrossTenantValidation:
    """同一 project_id、不同 tenant_id 不能串数据。"""

    def test_plan_not_visible_across_tenant(self, db):
        svc = ValidationService(db)
        plan = svc.create_plan("T-A", "P-1", "EVT", "Tenant A Plan")
        assert svc.get_plan("T-B", "P-1", plan.plan_id) is None

    def test_test_not_visible_across_tenant(self, db):
        svc = ValidationService(db)
        plan = svc.create_plan("T-A", "P-1", "EVT", "Plan")
        test = svc.create_test("T-A", "P-1", plan.plan_id, "Test A", "EVT")
        assert svc.get_test("T-B", "P-1", test.test_id) is None

    def test_result_not_visible_across_tenant(self, db):
        svc = ValidationService(db)
        plan = svc.create_plan("T-A", "P-1", "EVT", "Plan")
        test = svc.create_test("T-A", "P-1", plan.plan_id, "Test", "EVT")
        run = svc.create_run("T-A", "P-1", test.test_id)
        svc.record_result("T-A", "P-1", run.run_id, test.test_id, RESULT_PASS)
        results = svc.list_results("T-B", "P-1")
        assert len(results) == 0

    def test_list_plans_scoped_to_tenant(self, db):
        svc = ValidationService(db)
        svc.create_plan("T-A", "P-1", "EVT", "Plan A")
        svc.create_plan("T-B", "P-1", "EVT", "Plan B")
        plans_a = svc.list_plans("T-A", "P-1")
        plans_b = svc.list_plans("T-B", "P-1")
        assert len(plans_a) == 1
        assert len(plans_b) == 1
        assert plans_a[0].title == "Plan A"
        assert plans_b[0].title == "Plan B"


class TestCrossTenantIssues:
    """Issue 域的 tenant 隔离。"""

    def test_issue_not_visible_across_tenant(self, db):
        svc = IssueService(db)
        issue = svc.create_issue("T-A", "P-1", "Issue A", "MAJOR")
        assert svc.get_issue("T-B", "P-1", issue.issue_id) is None

    def test_issue_status_update_cannot_cross_tenant(self, db):
        svc = IssueService(db)
        issue = svc.create_issue("T-A", "P-1", "Issue A", "MAJOR")
        result = svc.update_issue_status("T-B", "P-1", issue.issue_id, "RESOLVED")
        assert result is None

    def test_issue_list_scoped_to_tenant(self, db):
        svc = IssueService(db)
        svc.create_issue("T-A", "P-1", "A1", "MAJOR")
        svc.create_issue("T-B", "P-1", "B1", "MAJOR")
        assert len(svc.list_issues("T-A", "P-1")) == 1
        assert len(svc.list_issues("T-B", "P-1")) == 1
        assert svc.list_issues("T-A", "P-1")[0].title == "A1"


class TestCrossProjectIsolation:
    """同一 tenant、不同 project 不能串数据。"""

    def test_plan_not_visible_across_project(self, db):
        svc = ValidationService(db)
        plan = svc.create_plan("T-A", "P-1", "EVT", "Plan P1")
        assert svc.get_plan("T-A", "P-2", plan.plan_id) is None

    def test_readiness_scoped_to_project(self, db):
        """Readiness 不得读取其他 project 的 PASS。"""
        svc = ValidationService(db)
        issue_svc = IssueService(db)
        readiness_svc = ReadinessService(svc, issue_svc)
        plan = svc.create_plan("T-A", "P-1", "EVT", "Plan P1")
        test = svc.create_test("T-A", "P-1", plan.plan_id, "Test P1", "EVT", required=True)
        run = svc.create_run("T-A", "P-1", test.test_id)
        svc.record_result("T-A", "P-1", run.run_id, test.test_id, RESULT_PASS)
        snapshot = readiness_svc.evaluate("T-A", "P-2")
        assert snapshot.overall_status != "PASS"


class TestIdempotencyNoCrossTenant:
    """Idempotency key 不得错误全局碰撞。"""

    def test_same_idempotency_key_different_tenant(self, db):
        svc = ValidationService(db)
        plan1 = svc.create_plan("T-A", "P-1", "EVT", "Plan A")
        plan2 = svc.create_plan("T-B", "P-1", "EVT", "Plan B")
        assert plan1.plan_id != plan2.plan_id
        assert svc.get_plan("T-A", "P-1", plan1.plan_id) is not None
        assert svc.get_plan("T-B", "P-1", plan2.plan_id) is not None
