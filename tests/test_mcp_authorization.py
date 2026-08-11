"""v5.7 Commit 2：MCP Transport Authentication 测试。

覆盖（直接调用 mcp_server 暴露的函数/服务验证 actor 注入与 fail-closed，
不必真的起 MCP server 进程；FastMCP 未安装时跳过 MCP 注册部分，但认证函数
本身必须可测）：
- 未认证 MCP（AIPD_MCP_USER/TOKEN 缺失）→ denied（fail-closed RuntimeError）；
- 无效 principal（错误/过期 token、弱 token）→ denied；
- tenant A principal → 不能触达 tenant B 项目（MCP tenant 取自 principal，
  且 StateService 层 require_tenant_membership 拒绝跨租户 actor）；
- project A principal → 不能访问 project B（项目级授权拒绝）；
- 授权 principal → allowed（actor 注入后创建者成为项目成员并可访问）；
- MCP 调用方无法伪造 tenant（tenant 恒取 principal.tenant_id）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "state_service"))

import mcp_server  # noqa: E402, I001
from aipd_os.state.auth import AuthError, AuthenticatedPrincipal  # noqa: E402
from aipd_os.state.server import StateService  # noqa: E402

pytestmark = pytest.mark.usefixtures("_mcp_service")


@pytest.fixture
def _mcp_service(tmp_path):
    """构造测试用 StateService（强 secret + 强 encryption key）。"""
    svc = StateService(
        str(tmp_path / "mcp.db"),
        encryption_key="mcp-strong-encryption-key-000",
        secret="mcp-strong-test-secret-000",
        require_strong_secret=True,
        require_strong_encryption_key=True,
    )
    return svc


def _principal(service: StateService, user_id: str, tenant_id: str) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(user_id=user_id, tenant_id=tenant_id,
                                  auth_method="service_principal",
                                  scopes=mcp_server.MCP_SCOPES)


def _register(service: StateService, user_id: str, username: str, tenant: str,
              project: str | None = None) -> str:
    return service.auth_register(user_id, tenant, username, "pw", project_id=project)


def test_module_imports_without_mcp_installed():
    """未安装 mcp 时模块仍可导入且安全降级（_MCP_AVAILABLE=False）。"""
    import mcp_server as ms

    assert ms.mcp is None or ms._MCP_AVAILABLE is not None
    assert callable(ms.get_mcp_principal)
    assert callable(ms.mcp_init_project)


# ---------------------------------------------------------------------------
# 1) 未认证 MCP → denied
# ---------------------------------------------------------------------------
def test_unauthenticated_mcp_denied(monkeypatch, _mcp_service):
    """AIPD_MCP_USER / AIPD_MCP_TOKEN 缺失 → fail-closed 拒绝。"""
    monkeypatch.delenv("AIPD_MCP_USER", raising=False)
    monkeypatch.delenv("AIPD_MCP_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="AIPD_MCP_USER"):
        mcp_server.get_mcp_principal(_mcp_service)
    # 仅设置 user 而没有 token 同样拒绝
    monkeypatch.setenv("AIPD_MCP_USER", "ua")
    with pytest.raises(RuntimeError, match="AIPD_MCP_TOKEN"):
        mcp_server.get_mcp_principal(_mcp_service)


# ---------------------------------------------------------------------------
# 2) 无效 principal → denied
# ---------------------------------------------------------------------------
def test_invalid_principal_denied(monkeypatch, _mcp_service):
    """错误 token / 弱 token / 不存在的用户 → fail-closed 拒绝。"""
    svc = _mcp_service
    svc.init_project("tenantA", "projA", "A", "goal-a")
    token_a = _register(svc, "ua", "alice", "tenantA")

    # 错误 token
    monkeypatch.setenv("AIPD_MCP_USER", "ua")
    monkeypatch.setenv("AIPD_MCP_TOKEN", "x" * 32)
    with pytest.raises(RuntimeError, match="invalid or expired"):
        mcp_server.get_mcp_principal(svc)

    # 弱 token（长度不足 / 公开默认值）
    monkeypatch.setenv("AIPD_MCP_TOKEN", "short")
    with pytest.raises(RuntimeError, match="weak AIPD_MCP_TOKEN"):
        mcp_server.get_mcp_principal(svc)
    monkeypatch.setenv("AIPD_MCP_TOKEN", "change-me-token")
    with pytest.raises(RuntimeError, match="weak AIPD_MCP_TOKEN"):
        mcp_server.get_mcp_principal(svc)

    # 不存在的用户（即使 token 是别的用户的合法 token 也不行）
    monkeypatch.setenv("AIPD_MCP_USER", "ghost")
    monkeypatch.setenv("AIPD_MCP_TOKEN", token_a)
    with pytest.raises(RuntimeError, match="invalid or expired"):
        mcp_server.get_mcp_principal(svc)


# ---------------------------------------------------------------------------
# 3) 授权 principal → allowed（actor 注入）
# ---------------------------------------------------------------------------
def test_authorized_principal_allowed(monkeypatch, _mcp_service):
    """合法 principal → MCP 调用成功，actor 注入后创建者成为项目成员。"""
    svc = _mcp_service
    svc.init_project("tenantA", "projA", "A", "goal-a")
    token_a = _register(svc, "ua", "alice", "tenantA")

    monkeypatch.setenv("AIPD_MCP_USER", "ua")
    monkeypatch.setenv("AIPD_MCP_TOKEN", token_a)
    principal = mcp_server.get_mcp_principal(svc)
    assert principal.user_id == "ua"
    assert principal.tenant_id == "tenantA"
    assert principal.auth_method == "service_principal"
    assert "project:write" in principal.scopes

    # MCP init_project：tenant 取 principal.tenant_id，actor 注入 principal.user_id
    result = json.loads(mcp_server.mcp_init_project(svc, principal, "projB", "B", "goal-b"))
    assert result["project"]["project_id"] == "projB"
    assert result["project"]["tenant_id"] == "tenantA"
    svc.auth.require_project_access("ua", "tenantA", "projB")  # 创建者成为成员

    # MCP project_summary / add_fact / export_checkpoint 同一 principal 均可访问
    summary = json.loads(mcp_server.mcp_project_summary(svc, principal, "projB"))
    assert summary["project"]["project_id"] == "projB"
    fid = mcp_server.mcp_add_fact(svc, principal, "projB", "k", "42", "V")
    assert fid.startswith("F-")
    exported = json.loads(mcp_server.mcp_export_checkpoint(svc, principal, "projB"))
    assert exported["project"]["project_id"] == "projB"


# ---------------------------------------------------------------------------
# 4) project A principal → 不能访问 project B（项目级隔离）
# ---------------------------------------------------------------------------
def test_project_boundary_denied_for_other_project(_mcp_service):
    """项目 A principal 不能读/写项目 B（同租户内项目隔离）。"""
    svc = _mcp_service
    svc.init_project("tenantA", "pA", "A", "goal-a")
    svc.init_project("tenantA", "pB", "B", "goal-b")
    _register(svc, "ua", "alice", "tenantA", project="pA")
    principal = _principal(svc, "ua", "tenantA")

    with pytest.raises(AuthError):
        mcp_server.mcp_project_summary(svc, principal, "pB")
    with pytest.raises(AuthError):
        mcp_server.mcp_add_fact(svc, principal, "pB", "k", "1", "V")
    with pytest.raises(AuthError):
        mcp_server.mcp_export_checkpoint(svc, principal, "pB")

    # 自己的项目 pA 正常
    summary = json.loads(mcp_server.mcp_project_summary(svc, principal, "pA"))
    assert summary["project"]["project_id"] == "pA"


# ---------------------------------------------------------------------------
# 5) tenant A principal → 不能触达 tenant B（跨租户隔离）
# ---------------------------------------------------------------------------
def test_tenant_boundary_denied_for_other_tenant(_mcp_service):
    """tenant A principal 不能触达 tenant B 项目。"""
    svc = _mcp_service
    svc.init_project("tenantA", "projA", "A", "goal-a")
    svc.init_project("tenantB", "projB", "B", "goal-b")
    _register(svc, "ua", "alice", "tenantA", project="projA")
    principal = _principal(svc, "ua", "tenantA")

    # MCP tenant 恒取 principal.tenant_id → 无法把调用定向到 tenantB
    result = json.loads(mcp_server.mcp_init_project(svc, principal, "newB", "N", "g"))
    assert result["project"]["tenant_id"] == "tenantA"

    # 即便显式用 tenantB 调 StateService（绕过 MCP 层），成员资格校验也会拒绝
    with pytest.raises(AuthError, match="does not belong to tenant"):
        svc.init_project("tenantB", "x", "X", "g", actor="ua")
    with pytest.raises(AuthError, match="does not belong to tenant"):
        svc.project_summary("tenantB", "projB", actor="ua")
    with pytest.raises(AuthError):
        svc.list_projects("tenantB", actor="ua")


def test_mcp_cannot_spoof_tenant_via_principal(_mcp_service):
    """伪造 principal（把 tenant_id 改成别人的租户）→ StateService 拒绝。"""
    svc = _mcp_service
    svc.init_project("tenantA", "projA", "A", "goal-a")
    _register(svc, "ua", "alice", "tenantA", project="projA")
    # 手工构造 principal，把 tenant 改成 tenantB（模拟调用方伪造）
    forged = AuthenticatedPrincipal(user_id="ua", tenant_id="tenantB",
                                    auth_method="service_principal",
                                    scopes=mcp_server.MCP_SCOPES)
    with pytest.raises(AuthError, match="does not belong to tenant"):
        mcp_server.mcp_project_summary(svc, forged, "projB")
    with pytest.raises(AuthError, match="does not belong to tenant"):
        mcp_server.mcp_init_project(svc, forged, "x", "X", "g")
