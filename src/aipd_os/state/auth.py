"""认证与项目级授权。

- 密码哈希：``hashlib.pbkdf2_hmac``（sha256，每用户随机盐，迭代数随盐存储）；
- 令牌签发：HMAC-SHA256 签名令牌，携带 user_id 与到期时间戳；
- ``authenticate`` 校验令牌签名与有效期；
- ``require_project_access`` 校验用户是否有权访问指定 tenant/project；
- ``require_tenant_membership`` 校验用户属于指定租户（``users.tenant_id`` 归属）；
- ``AuthenticatedPrincipal``：外部 Transport（HTTP/MCP/RPC）认证通过后产生的
  最小可信身份，transport boundary 永远不得以 ``actor=None`` 直通 StateService。
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field
from typing import Optional

from .db import AIPDStateDB

PBKDF2_ITERATIONS = 200_000
TOKEN_TTL_SECONDS = 86_400  # 24h


class AuthError(Exception):
    """认证 / 授权失败。"""


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    """外部 Transport 认证通过后产生的最小可信身份。

    ``actor=None`` 仅保留给可信内部代码路径（系统/内部调用跳过授权）；
    任何外部 Transport 在调用 StateService 前必须解析出本 principal，
    并以 ``principal.user_id`` 作为 actor 注入，否则 fail-closed 拒绝。
    """

    user_id: str
    tenant_id: str
    auth_method: str
    scopes: frozenset[str] = field(default_factory=frozenset)


class AuthManager:
    def __init__(self, db: AIPDStateDB, secret: Optional[str] = None):
        if secret is None:
            raise ValueError("AuthManager requires a secret")
        self._db = db
        self._secret = secret.encode("utf-8")

    # ------------------------------------------------------------- password
    def _hash_password(self, password: str, salt: Optional[str] = None) -> str:
        iterations = PBKDF2_ITERATIONS
        if salt is None:
            salt = secrets.token_hex(16)
        else:
            iterations = PBKDF2_ITERATIONS
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                 bytes.fromhex(salt), iterations, dklen=32)
        return f"{iterations}${salt}${dk.hex()}"

    def _verify_password(self, password: str, stored: str) -> bool:
        iterations, salt, expected = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                 bytes.fromhex(salt), int(iterations), dklen=32)
        return hmac.compare_digest(dk.hex(), expected)

    def register_user(self, user_id: str, tenant_id: str, username: str, password: str) -> None:
        if self._db.get_user_by_username(username):
            raise AuthError(f"username {username!r} already registered")
        if self._db.get_tenant(tenant_id) is None:
            # 用户只能注册到已存在的租户（租户由引导流程/系统创建）。
            raise AuthError(
                f"tenant {tenant_id!r} does not exist; cannot register "
                "into a non-existent tenant")
        salt = secrets.token_hex(16)
        self._db.create_user(user_id, tenant_id, username,
                             self._hash_password(password, salt), salt)

    def verify_password(self, username: str, password: str) -> Optional[str]:
        """校验用户名密码，成功返回 user_id，失败返回 None。"""
        user = self._db.get_user_by_username(username)
        if not user:
            return None
        if not self._verify_password(password, user["password_hash"]):
            return None
        return user["user_id"]

    # ---------------------------------------------------------------- token
    def issue_token(self, user_id: str, ttl: int = TOKEN_TTL_SECONDS) -> str:
        expiry = int(time.time()) + ttl
        payload = f"{user_id}.{expiry}"
        sig = hmac.new(self._secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"{payload}.{sig}"

    def authenticate(self, user: str, token: str) -> bool:
        """校验令牌对 user 是否有效（签名 + 有效期 + 归属）。"""
        parts = token.split(".")
        if len(parts) != 3:
            return False
        user_id, expiry, sig = parts
        if user_id != user:
            return False
        try:
            if int(expiry) < int(time.time()):
                return False
        except ValueError:
            return False
        expected = hmac.new(self._secret, f"{user_id}.{expiry}".encode(),
                            hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected)

    # -------------------------------------------------- project authorization
    def require_tenant_membership(self, user: str, tenant_id: str) -> None:
        """用户必须属于该租户（``users.tenant_id == tenant_id``），否则 :class:`AuthError`。

        规则：普通用户只能在**自己所属租户**内创建项目、读取租户范围资源、
        接受项目授权。跨租户授权行由 ``grant_access`` 一并拦截。
        """
        row = self._db.get_user(user)
        if not row:
            raise AuthError(f"unknown user {user!r}")
        if row["tenant_id"] != tenant_id:
            raise AuthError(
                f"user {user!r} does not belong to tenant {tenant_id!r} "
                f"(user tenant: {row['tenant_id']!r})")

    def grant_access(self, user_id: str, tenant_id: str, project_id: Optional[str] = None) -> None:
        """授予用户项目访问权；被授权用户必须属于该租户（防跨租户授权行）。"""
        self.require_tenant_membership(user_id, tenant_id)
        self._db.grant_access(user_id, tenant_id, project_id)

    def require_project_access(self, user: str, tenant_id: str, project_id: str) -> None:
        """无权限时抛 :class:`AuthError`。项目级授权表 user_access。

        先校验租户成员资格（跨租户授权行一律拒绝），再查项目级访问授权。
        """
        self.require_tenant_membership(user, tenant_id)
        if not self._db.has_access(user, tenant_id, project_id):
            raise AuthError(f"user {user!r} has no access to {tenant_id}/{project_id}")

    def require_tenant_admin(self, user: str, tenant_id: str) -> None:
        """无租户管理员权限时抛 :class:`AuthError`。

        先校验租户成员资格（管理员必须是该租户成员），再查通配授权行。
        """
        self.require_tenant_membership(user, tenant_id)
        if not self._db.has_tenant_admin(user, tenant_id):
            raise AuthError(f"user {user!r} is not a tenant admin of {tenant_id!r}")


__all__ = ["AuthManager", "AuthError", "AuthenticatedPrincipal"]
