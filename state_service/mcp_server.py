#!/usr/bin/env python3
"""AIPD 状态服务的 MCP 适配器（薄层）。

生产逻辑在 ``aipd_os.state``（StateService）。本文件仅做两层事：
  1) 把 MCP 工具语义映射到 StateService（多租户，principal 租户范围）；
  2) 仅在已安装 ``mcp`` 时才注册 FastMCP 工具并运行 —— 未安装 mcp 时
     本模块仍可安全导入（不会因 import 失败而崩溃）。

认证（v5.7 Commit 2：MCP Transport Authentication）：
  - 外部 Transport 必须产生 :class:`AuthenticatedPrincipal`（至少 user_id +
    tenant_id + auth_method + scopes）后才能调用 StateService；``actor=None``
    仅保留给可信内部代码路径，transport boundary 永远不可达。
  - MCP 使用 **service principal** 认证：环境变量 ``AIPD_MCP_USER`` +
    ``AIPD_MCP_TOKEN``，启动时验证（缺失/弱 token → fail-closed 拒绝启动）。
    ``AIPD_MCP_TOKEN`` 必须是该用户在 StateService 签发的有效令牌
    （``StateService.auth.authenticate`` 校验）。
  - 每个 MCP 工具调用都会解析 principal 并把 ``actor=principal.user_id`` 传入
    StateService；tenant 一律取 ``principal.tenant_id``（调用方不可指定/伪造），
    因此 tenant A principal 天然无法触达 tenant B 项目。

运行前可用环境变量配置：
  AIPD_DB_DIR / AIPD_ENCRYPTION_KEY / AIPD_SECRET / AIPD_RETENTION_DAYS /
  AIPD_MCP_USER / AIPD_MCP_TOKEN
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aipd_os.state.auth import AuthenticatedPrincipal  # noqa: E402
from aipd_os.state.server import StateService  # noqa: E402

DEFAULT_TENANT = os.environ.get("AIPD_DEFAULT_TENANT", "default")
DB_PATH = os.environ.get("AIPD_DB_DIR", str(Path.home() / ".aipd-projects" / "state.db"))

# MCP service principal 的 token 强度下限（与 server secret 策略一致）。
MIN_STRONG_MCP_TOKEN_LEN = 16
# 视为「弱/缺失」的 MCP token 取值（公开默认值）。
_WEAK_MCP_TOKEN_VALUES = ("", "change-me", "change-me-token", "changeme")
# MCP 默认 scopes：项目读写（当前工具集所需的最小集合）。
MCP_SCOPES = frozenset({"project:read", "project:write"})

_service: StateService | None = None


def _get_service() -> StateService:
    """懒创建 StateService（MCP 服务模式：缺/弱 secret 与 encryption key 时 fail-closed）。"""
    global _service
    if _service is None:
        _service = StateService(
            DB_PATH,
            encryption_key=os.environ.get("AIPD_ENCRYPTION_KEY", ""),
            secret=os.environ.get("AIPD_SECRET"),
            retention_days=int(os.environ.get("AIPD_RETENTION_DAYS", "90")),
            insecure_dev_mode=os.environ.get("AIPD_INSECURE_DEV_MODE", "")
            not in ("", "0", "false", "False"),
            require_strong_secret=True,  # MCP 服务视为服务模式：缺/弱 secret 时 fail-closed
            require_strong_encryption_key=True,  # 缺/弱 encryption key 时 fail-closed
        )
    return _service


# ---------------------------------------------------------------------------
# Service Principal（外部 Transport 认证边界）
# ---------------------------------------------------------------------------
def get_mcp_principal(service: StateService | None = None) -> AuthenticatedPrincipal:
    """解析并校验 MCP service principal；缺失/弱 token → fail-closed 抛错。

    返回的 principal 携带 user_id / tenant_id / auth_method / scopes，
    供所有 MCP 工具作为 actor 注入 StateService。
    """
    svc = service if service is not None else _get_service()
    user = os.environ.get("AIPD_MCP_USER", "").strip()
    token = os.environ.get("AIPD_MCP_TOKEN", "").strip()
    if not user or not token:
        raise RuntimeError(
            "MCP transport requires authentication: set AIPD_MCP_USER and "
            "AIPD_MCP_TOKEN (fail-closed; unauthenticated MCP calls are denied)")
    if token in _WEAK_MCP_TOKEN_VALUES or len(token) < MIN_STRONG_MCP_TOKEN_LEN:
        raise RuntimeError(
            f"weak AIPD_MCP_TOKEN: server mode requires a strong token "
            f"(>= {MIN_STRONG_MCP_TOKEN_LEN} chars and not a public default)")
    if not svc.auth.authenticate(user, token):
        raise RuntimeError(
            f"invalid or expired AIPD_MCP_TOKEN for user {user!r} "
            "(unauthenticated MCP calls are denied)")
    row = svc.db.get_user(user)
    if row is None:
        raise RuntimeError(f"AIPD_MCP_USER {user!r} does not exist in the state DB")
    return AuthenticatedPrincipal(
        user_id=user,
        tenant_id=row["tenant_id"],
        auth_method="service_principal",
        scopes=MCP_SCOPES,
    )


def require_mcp_principal(service: StateService | None = None) -> AuthenticatedPrincipal:
    """与 :func:`get_mcp_principal` 等价（fail-closed 语义别名）。"""
    return get_mcp_principal(service)


# ---------------------------------------------------------------------------
# 工具语义（与旧 server 一致，底层调用 StateService；actor 注入 principal）
# ---------------------------------------------------------------------------
def mcp_init_project(service: StateService, principal: AuthenticatedPrincipal,
                     project_id: str, name: str, goal: str) -> str:
    return json.dumps(service.init_project(principal.tenant_id, project_id, name, goal,
                                           actor=principal.user_id), ensure_ascii=False)


def mcp_project_summary(service: StateService, principal: AuthenticatedPrincipal,
                        project_id: str) -> str:
    return json.dumps(service.project_summary(principal.tenant_id, project_id,
                                              actor=principal.user_id), ensure_ascii=False)


def mcp_add_fact(service: StateService, principal: AuthenticatedPrincipal,
                 project_id: str, key: str, value_json: str, status: str,
                 unit: str = "", source: str = "", confidence: float = 0.5) -> str:
    value = json.loads(value_json)
    return service.add_fact(principal.tenant_id, project_id, key, value, status,
                            unit=unit or None, source=source or None,
                            confidence=confidence, actor=principal.user_id)


def mcp_propose_decision(service: StateService, principal: AuthenticatedPrincipal,
                         project_id: str, topic: str, recommendation: str,
                         options_json: str, trigger: str = "") -> str:
    return service.propose_decision(principal.tenant_id, project_id, topic, recommendation,
                                    json.loads(options_json), trigger or None,
                                    actor=principal.user_id)


def mcp_resolve_decision(service: StateService, principal: AuthenticatedPrincipal,
                         project_id: str, decision_id: str, choice: str,
                         comment: str = "") -> str:
    return service.resolve_decision(principal.tenant_id, project_id, decision_id, choice,
                                    comment or None, actor=principal.user_id)


def mcp_export_checkpoint(service: StateService, principal: AuthenticatedPrincipal,
                          project_id: str) -> str:
    return json.dumps(service.export_checkpoint(principal.tenant_id, project_id,
                                                actor=principal.user_id), ensure_ascii=False)


# ---- 仅在已安装 mcp 时注册 FastMCP 工具 ----
try:  # pragma: no cover - 取决于运行环境是否安装 mcp
    from mcp.server.fastmcp import FastMCP  # type: ignore

    mcp = FastMCP("aipd-state")

    @mcp.tool()
    def init_project(project_id: str, name: str, goal: str) -> str:  # noqa: F811
        return mcp_init_project(_get_service(), get_mcp_principal(), project_id, name, goal)

    @mcp.tool()
    def project_summary(project_id: str) -> str:  # noqa: F811
        return mcp_project_summary(_get_service(), get_mcp_principal(), project_id)

    @mcp.tool()
    def add_fact(project_id: str, key: str, value_json: str, status: str,  # noqa: F811
                 unit: str = "", source: str = "", confidence: float = 0.5) -> str:
        return mcp_add_fact(_get_service(), get_mcp_principal(), project_id, key, value_json,
                            status, unit=unit, source=source, confidence=confidence)

    @mcp.tool()
    def propose_decision(project_id: str, topic: str, recommendation: str,  # noqa: F811
                         options_json: str, trigger: str = "") -> str:
        return mcp_propose_decision(_get_service(), get_mcp_principal(), project_id, topic,
                                    recommendation, options_json, trigger=trigger)

    @mcp.tool()
    def resolve_decision(project_id: str, decision_id: str, choice: str,  # noqa: F811
                         comment: str = "") -> str:
        return mcp_resolve_decision(_get_service(), get_mcp_principal(), project_id,
                                    decision_id, choice, comment=comment)

    @mcp.tool()
    def export_checkpoint(project_id: str) -> str:  # noqa: F811
        return mcp_export_checkpoint(_get_service(), get_mcp_principal(), project_id)

    _MCP_AVAILABLE = True
except Exception:  # pragma: no cover - mcp 未安装时的安全回退
    mcp = None
    _MCP_AVAILABLE = False


def run() -> None:
    """启动 MCP 服务；启动前强制校验 service principal（fail-closed）。"""
    if mcp is None:
        raise SystemExit("mcp is not installed; cannot run the MCP transport. "
                         "Install `mcp` or use the built-in HTTP transport "
                         "(`python -m aipd_os.state.server --mode server`).")
    # 启动即验证：缺失/弱 token 直接拒绝启动。
    get_mcp_principal(_get_service())
    mcp.run()


if __name__ == "__main__":
    run()
