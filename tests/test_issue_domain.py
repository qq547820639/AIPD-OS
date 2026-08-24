"""Issue / Corrective Action Domain 测试（v5.10 Milestone 2）。

覆盖：
- Issue CRUD
- Corrective Action CRUD
- Issue close 语义（can_close 检查）
- Idempotent issue creation
- Multi-tenant isolation
- Negative paths
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from aipd_os.state.db import AIPDStateDB
from aipd_os.validation.issues import (
    ACTION_COMPLETED,
    ACTION_VERIFIED,
    DISPOSITION_FIX,
    ISSUE_CLOSED,
    ISSUE_IN_PROGRESS,
    ISSUE_OPEN,
    ISSUE_RESOLVED,
    ISSUE_WAIVED,
    PRIORITY_P0,
    SEVERITY_CRITICAL,
    IssueService,
)


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
    """创建 IssueService。"""
    return IssueService(db)


# =====================================================================
# Issue CRUD
# =====================================================================

class TestIssueCRUD:
    """Issue CRUD 测试。"""

    def test_create_and_get_issue(self, svc):
        """创建和获取 Issue。"""
        issue = svc.create_issue(
            "t1", "p1", "Test Issue", "Description",
            severity=SEVERITY_CRITICAL, priority=PRIORITY_P0,
        )
        assert issue.issue_id.startswith("issue_")
        assert issue.status == ISSUE_OPEN

        got = svc.get_issue("t1", "p1", issue.issue_id)
        assert got is not None
        assert got.title == "Test Issue"
        assert got.severity == SEVERITY_CRITICAL

    def test_list_issues(self, svc):
        """列出 Issue。"""
        svc.create_issue("t1", "p1", "Issue 1")
        svc.create_issue("t1", "p1", "Issue 2")
        svc.create_issue("t1", "p2", "Issue 3")

        issues = svc.list_issues("t1", "p1")
        assert len(issues) == 2

        issues_p2 = svc.list_issues("t1", "p2")
        assert len(issues_p2) == 1

    def test_list_issues_by_status(self, svc):
        """按状态列出 Issue。"""
        issue = svc.create_issue("t1", "p1", "Issue 1")
        svc.update_issue_status("t1", "p1", issue.issue_id, ISSUE_RESOLVED)
        svc.create_issue("t1", "p1", "Issue 2")

        open_issues = svc.list_issues("t1", "p1", status=ISSUE_OPEN)
        resolved_issues = svc.list_issues("t1", "p1", status=ISSUE_RESOLVED)
        assert len(open_issues) == 1
        assert len(resolved_issues) == 1

    def test_list_blocking_issues(self, svc):
        """列出阻塞发布 Issue。"""
        svc.create_issue("t1", "p1", "Blocking", blocking_release=True)
        svc.create_issue("t1", "p1", "Non-blocking", blocking_release=False)

        blocking = svc.list_issues("t1", "p1", blocking_only=True)
        assert len(blocking) == 1
        assert blocking[0].title == "Blocking"

    def test_update_issue_status(self, svc):
        """更新 Issue 状态。"""
        issue = svc.create_issue("t1", "p1", "Issue 1")

        updated = svc.update_issue_status(
            "t1", "p1", issue.issue_id, ISSUE_IN_PROGRESS)
        assert updated is not None
        assert updated.status == ISSUE_IN_PROGRESS

    def test_set_disposition(self, svc):
        """设置处置方式。"""
        issue = svc.create_issue("t1", "p1", "Issue 1")

        updated = svc.set_disposition(
            "t1", "p1", issue.issue_id, DISPOSITION_FIX,
            root_cause="material defect",
            revalidation_required=True,
        )
        assert updated is not None
        assert updated.disposition == DISPOSITION_FIX
        assert updated.root_cause == "material defect"
        assert updated.revalidation_required is True


# =====================================================================
# Issue close semantics
# =====================================================================

class TestIssueCloseSemantics:
    """Issue 关闭语义测试。"""

    def test_cannot_close_without_disposition(self, svc):
        """没有处置方式不能关闭。"""
        issue = svc.create_issue("t1", "p1", "Issue 1")
        can, reason = issue.can_close()
        assert not can
        assert "disposition" in reason

    def test_cannot_close_with_pending_revalidation(self, svc):
        """需要重新验证但没有结果不能关闭。"""
        issue = svc.create_issue("t1", "p1", "Issue 1")
        svc.set_disposition(
            "t1", "p1", issue.issue_id, DISPOSITION_FIX,
            revalidation_required=True,
        )
        issue = svc.get_issue("t1", "p1", issue.issue_id)
        can, reason = issue.can_close()
        assert not can
        assert "revalidation" in reason

    def test_can_close_with_disposition_and_revalidation(self, svc):
        """有处置方式和重新验证结果可以关闭。"""
        issue = svc.create_issue("t1", "p1", "Issue 1")
        svc.set_disposition(
            "t1", "p1", issue.issue_id, DISPOSITION_FIX,
            revalidation_required=True,
        )

        # 设置 revalidation result
        issue = svc.get_issue("t1", "p1", issue.issue_id)
        issue.revalidation_result_ref = "vres_123"
        # 直接更新数据库
        with svc._db.connect() as conn:
            conn.execute(
                "UPDATE issues SET revalidation_result_ref=? "
                "WHERE tenant_id=? AND project_id=? AND issue_id=?",
                ("vres_123", "t1", "p1", issue.issue_id),
            )

        # 先 resolve 再 close
        svc.update_issue_status("t1", "p1", issue.issue_id, ISSUE_RESOLVED)
        svc.update_issue_status("t1", "p1", issue.issue_id, ISSUE_CLOSED)

        closed = svc.get_issue("t1", "p1", issue.issue_id)
        assert closed is not None
        assert closed.status == ISSUE_CLOSED

    def test_can_waive_issue(self, svc):
        """可以 waive Issue。"""
        issue = svc.create_issue("t1", "p1", "Issue 1")
        svc.update_issue_status(
            "t1", "p1", issue.issue_id, ISSUE_WAIVED, reason="accepted risk")

        waived = svc.get_issue("t1", "p1", issue.issue_id)
        assert waived is not None
        assert waived.status == ISSUE_WAIVED

    def test_audit_trail_recorded(self, svc):
        """状态变更必须记录审计轨迹。"""
        issue = svc.create_issue("t1", "p1", "Issue 1")
        svc.update_issue_status(
            "t1", "p1", issue.issue_id, ISSUE_IN_PROGRESS, reason="started")

        updated = svc.get_issue("t1", "p1", issue.issue_id)
        assert len(updated.audit_trail) >= 2  # created + status change


# =====================================================================
# Idempotent issue creation
# =====================================================================

class TestIdempotency:
    """幂等性测试。"""

    def test_same_validation_ref_creates_only_one_issue(self, svc):
        """相同 validation_result_ref 不会创建重复 Issue。"""
        issue1 = svc.create_issue(
            "t1", "p1", "Issue 1",
            validation_result_ref="vres_123",
        )
        issue2 = svc.create_issue(
            "t1", "p1", "Issue 2",
            validation_result_ref="vres_123",
        )
        assert issue1.issue_id == issue2.issue_id

    def test_different_validation_refs_create_different_issues(self, svc):
        """不同 validation_result_ref 创建不同 Issue。"""
        issue1 = svc.create_issue(
            "t1", "p1", "Issue 1",
            validation_result_ref="vres_123",
        )
        issue2 = svc.create_issue(
            "t1", "p1", "Issue 2",
            validation_result_ref="vres_456",
        )
        assert issue1.issue_id != issue2.issue_id


# =====================================================================
# Corrective Action CRUD
# =====================================================================

class TestCorrectiveActionCRUD:
    """Corrective Action CRUD 测试。"""

    def test_create_and_get_action(self, svc):
        """创建和获取纠正措施。"""
        issue = svc.create_issue("t1", "p1", "Issue 1")
        action = svc.create_action(
            "t1", "p1", issue.issue_id,
            "Replace material", change="Aluminum → Steel",
        )
        assert action.action_id.startswith("caction_")

        got = svc.get_action("t1", "p1", action.action_id)
        assert got is not None
        assert got.description == "Replace material"

    def test_list_actions(self, svc):
        """列出纠正措施。"""
        issue = svc.create_issue("t1", "p1", "Issue 1")
        svc.create_action("t1", "p1", issue.issue_id, "Action 1")
        svc.create_action("t1", "p1", issue.issue_id, "Action 2")

        actions = svc.list_actions("t1", "p1", issue_id=issue.issue_id)
        assert len(actions) == 2

    def test_complete_action(self, svc):
        """完成纠正措施。"""
        issue = svc.create_issue("t1", "p1", "Issue 1")
        action = svc.create_action("t1", "p1", issue.issue_id, "Action 1")

        completed = svc.complete_action(
            "t1", "p1", action.action_id,
            verification_result_ref="vres_789",
        )
        assert completed is not None
        assert completed.status == ACTION_COMPLETED
        assert completed.completed_at is not None

    def test_verify_action(self, svc):
        """验证纠正措施。"""
        issue = svc.create_issue("t1", "p1", "Issue 1")
        action = svc.create_action("t1", "p1", issue.issue_id, "Action 1")
        svc.complete_action("t1", "p1", action.action_id)

        verified = svc.verify_action("t1", "p1", action.action_id)
        assert verified is not None
        assert verified.status == ACTION_VERIFIED
        assert verified.verified_at is not None


# =====================================================================
# Multi-tenant isolation
# =====================================================================

class TestMultiTenantIsolation:
    """多租户隔离测试。"""

    def test_issues_isolated_by_tenant(self, svc):
        """不同租户的 Issue 互相隔离。"""
        svc.create_issue("t1", "p1", "T1 Issue")
        svc.create_issue("t2", "p1", "T2 Issue")

        t1_issues = svc.list_issues("t1", "p1")
        t2_issues = svc.list_issues("t2", "p1")
        assert len(t1_issues) == 1
        assert len(t2_issues) == 1

    def test_issues_isolated_by_project(self, svc):
        """不同项目的 Issue 互相隔离。"""
        svc.create_issue("t1", "p1", "P1 Issue")
        svc.create_issue("t1", "p2", "P2 Issue")

        p1_issues = svc.list_issues("t1", "p1")
        p2_issues = svc.list_issues("t1", "p2")
        assert len(p1_issues) == 1
        assert len(p2_issues) == 1


# =====================================================================
# Negative paths
# =====================================================================

class TestNegativePaths:
    """负路径测试。"""

    def test_invalid_severity_raises(self, svc):
        """无效严重程度必须被拒绝。"""
        with pytest.raises(ValueError, match="invalid severity"):
            svc.create_issue("t1", "p1", "Issue", severity="INVALID")

    def test_invalid_priority_raises(self, svc):
        """无效优先级必须被拒绝。"""
        with pytest.raises(ValueError, match="invalid priority"):
            svc.create_issue("t1", "p1", "Issue", priority="INVALID")

    def test_invalid_status_raises(self, svc):
        """无效状态必须被拒绝。"""
        issue = svc.create_issue("t1", "p1", "Issue")
        with pytest.raises(ValueError, match="invalid status"):
            svc.update_issue_status("t1", "p1", issue.issue_id, "INVALID")

    def test_invalid_disposition_raises(self, svc):
        """无效处置方式必须被拒绝。"""
        issue = svc.create_issue("t1", "p1", "Issue")
        with pytest.raises(ValueError, match="invalid disposition"):
            svc.set_disposition("t1", "p1", issue.issue_id, "INVALID")

    def test_get_nonexistent_issue_returns_none(self, svc):
        """获取不存在的 Issue 返回 None。"""
        result = svc.get_issue("t1", "p1", "nonexistent")
        assert result is None

    def test_update_nonexistent_issue_returns_none(self, svc):
        """更新不存在的 Issue 返回 None。"""
        result = svc.update_issue_status("t1", "p1", "nonexistent", ISSUE_OPEN)
        assert result is None
