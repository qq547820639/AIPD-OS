"""认证与项目级授权。"""
from __future__ import annotations

import pytest

from aipd_os.state.auth import AuthError, AuthManager
from aipd_os.state.db import AIPDStateDB


@pytest.fixture
def am(tmp_path):
    db = AIPDStateDB(str(tmp_path / "auth.db"))
    db.ensure_default_tenant()
    return AuthManager(db, secret="test-secret")


def test_register_issue_authenticate(am):
    am.register_user("u1", "default", "alice", "hunter2")
    token = am.issue_token("u1")
    assert am.authenticate("u1", token) is True


def test_invalid_token_rejected(am):
    am.register_user("u1", "default", "alice", "pw")
    assert am.authenticate("u1", "u1.9999999999.badsig") is False
    assert am.authenticate("u1", "garbage") is False


def test_wrong_password(am):
    am.register_user("u1", "default", "alice", "right")
    assert am.verify_password("alice", "wrong") is None
    assert am.verify_password("alice", "right") == "u1"


def test_project_access_denied_for_unauthorized(am):
    am.register_user("u1", "default", "alice", "pw")
    am.register_user("u2", "default", "bob", "pw")

    # 只授权 u1 访问 p1
    am.grant_access("u1", "default", "p1")

    am.require_project_access("u1", "default", "p1")  # 通过
    with pytest.raises(AuthError):
        am.require_project_access("u2", "default", "p1")  # 未授权
    with pytest.raises(AuthError):
        am.require_project_access("u1", "default", "other_proj")  # 未授权项目
