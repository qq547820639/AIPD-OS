"""v5.7 Commit 3：Tenant Membership 边界测试。

覆盖：
- tenantA user 不能创建 tenantB 项目（init_project 拒绝）；
- tenantA user 不能自助注册进不存在/跨租户（auth_register 拒绝新租户、
  grant_access 拒绝跨租户授权）；
- tenantA admin 不能静默授予无关租户用户（grant_access 校验归属）；
- 项目创建仅在自己租户内授予创建者；
- 跨租户读取（project_summary / list_projects）拒绝；
- 已有 test_authorization.py 的 HTTP 层测试继续通过（由全量回归保障）。
"""
from __future__ import annotations

import pytest

from aipd_os.state.auth import AuthError
from aipd_os.state.db import ProjectNotFoundError
from aipd_os.state.server import StateService


def _make_svc(tmp_path):
    return StateService(str(tmp_path / "state.db"),
                        encryption_key="tenant-test-key",
                        secret="tenant-test-secret")


def _register(svc, user_id, username, tenant="default", project=None):
    return svc.auth_register(user_id, tenant, username, "pw", project_id=project)


def _make_tenants(svc):
    svc.init_project("tenantA", "projA", "A", "goal-a")
    svc.init_project("tenantB", "projB", "B", "goal-b")


# ---------------------------------------------------------------------------
# 1) tenantA user 不能创建 tenantB 项目
# ---------------------------------------------------------------------------
def test_cannot_create_project_in_other_tenant(tmp_path):
    svc = _make_svc(tmp_path)
    _make_tenants(svc)
    _register(svc, "ua", "alice", tenant="tenantA")

    with pytest.raises(AuthError, match="does not belong to tenant"):
        svc.init_project("tenantB", "evil", "E", "goal", actor="ua")
    # 项目未被创建（原子性：校验发生在建项目之前）
    with pytest.raises(ProjectNotFoundError):
        svc.db.get_project("tenantB", "evil")
    # 自己租户内创建正常
    svc.init_project("tenantA", "mine", "M", "goal", actor="ua")
    svc.auth.require_project_access("ua", "tenantA", "mine")


# ---------------------------------------------------------------------------
# 2) tenantA user 不能自助注册/授权到 tenantB
# ---------------------------------------------------------------------------
def test_cannot_self_enroll_other_tenant(tmp_path):
    svc = _make_svc(tmp_path)
    _make_tenants(svc)
    _register(svc, "ua", "alice", tenant="tenantA")

    # 匿名注册到不存在的租户 → 拒绝（不能匿名创建新租户后自授访问）
    with pytest.raises(AuthError, match="does not exist"):
        svc.auth_register("u_evil", "tenantX", "mallory", "pw")
    # 跨租户 grant_access（系统路径 actor=None 同样拒绝：目标用户不属于该租户）
    with pytest.raises(AuthError, match="does not belong to tenant"):
        svc.grant_access("ua", "tenantB", "projB")
    # tenantA 用户跨租户 init_project → 拒绝
    with pytest.raises(AuthError, match="does not belong to tenant"):
        svc.init_project("tenantB", "evil", "E", "g", actor="ua")


def test_register_into_existing_tenant_without_grant_has_no_access(tmp_path):
    """注册到已存在租户但不授予项目 → 无任何项目访问权（不隐式授权）。"""
    svc = _make_svc(tmp_path)
    _make_tenants(svc)
    token = _register(svc, "u_b", "bob", tenant="tenantB")
    assert token
    with pytest.raises(AuthError):
        svc.project_summary("tenantB", "projB", actor="u_b")


# ---------------------------------------------------------------------------
# 3) tenantA admin 不能静默授予无关租户用户
# ---------------------------------------------------------------------------
def test_admin_cannot_grant_unrelated_tenant_user(tmp_path):
    svc = _make_svc(tmp_path)
    _make_tenants(svc)
    _register(svc, "u_admin_a", "adminA", tenant="tenantA")
    _register(svc, "u_other_b", "bob", tenant="tenantB")
    svc.grant_access("u_admin_a", "tenantA", None)  # tenantA 管理员

    # adminA 尝试把 tenantA 项目授予 tenantB 用户 → 拒绝（归属校验）
    with pytest.raises(AuthError, match="does not belong to tenant"):
        svc.grant_access("u_other_b", "tenantA", "projA", actor="u_admin_a")
    # 同租户用户 → 成功
    _register(svc, "u_member_a", "carol", tenant="tenantA")
    svc.grant_access("u_member_a", "tenantA", "projA", actor="u_admin_a")
    svc.auth.require_project_access("u_member_a", "tenantA", "projA")


# ---------------------------------------------------------------------------
# 4) 项目创建仅在自己租户内授予创建者
# ---------------------------------------------------------------------------
def test_project_creation_grants_creator_within_own_tenant(tmp_path):
    svc = _make_svc(tmp_path)
    _make_tenants(svc)  # 先让 tenantA/tenantB 存在（系统路径创建）
    _register(svc, "ua", "alice", tenant="tenantA")
    _register(svc, "ub", "bob", tenant="tenantA")

    svc.init_project("tenantA", "p1", "P1", "goal", actor="ua")
    # 创建者 ua 可访问
    svc.auth.require_project_access("ua", "tenantA", "p1")
    # 同租户非成员 ub 不可访问
    with pytest.raises(AuthError):
        svc.project_summary("tenantA", "p1", actor="ub")
    # tenantB 用户更不可访问
    _register(svc, "uc", "carol", tenant="tenantB")
    with pytest.raises(AuthError):
        svc.project_summary("tenantA", "p1", actor="uc")
    # list_projects：ua 仅见 p1；ub 可见空列表
    assert [p["project_id"] for p in svc.list_projects("tenantA", actor="ua")["projects"]] == ["p1"]
    assert svc.list_projects("tenantA", actor="ub")["projects"] == []


# ---------------------------------------------------------------------------
# 5) 跨租户读取拒绝
# ---------------------------------------------------------------------------
def test_cross_tenant_read_denied(tmp_path):
    svc = _make_svc(tmp_path)
    _make_tenants(svc)
    _register(svc, "ua", "alice", tenant="tenantA", project="projA")

    with pytest.raises(AuthError, match="does not belong to tenant"):
        svc.project_summary("tenantB", "projB", actor="ua")
    with pytest.raises(AuthError, match="does not belong to tenant"):
        svc.list_projects("tenantB", actor="ua")
    with pytest.raises(AuthError, match="does not belong to tenant"):
        svc.add_fact("tenantB", "projB", "k", 1, "V", actor="ua")


# ---------------------------------------------------------------------------
# 6) 系统内部路径（actor=None）保持兼容
# ---------------------------------------------------------------------------
def test_system_path_actor_none_still_works(tmp_path):
    """actor=None 的内部/系统调用仍可跨租户初始化（引导流程）。"""
    svc = _make_svc(tmp_path)
    svc.init_project("tenantB", "projB", "B", "goal-b")  # 无 actor → 系统路径
    assert svc.db.get_project("tenantB", "projB")["project_id"] == "projB"
