"""认证与项目级授权。

- 密码哈希：``hashlib.pbkdf2_hmac``（sha256，每用户随机盐，迭代数随盐存储）；
- 令牌签发：HMAC-SHA256 签名令牌，携带 user_id 与到期时间戳；
- ``authenticate`` 校验令牌签名与有效期；
- ``require_project_access`` 校验用户是否有权访问指定 tenant/project。
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from typing import Any, Optional

from .db import AIPDStateDB

PBKDF2_ITERATIONS = 200_000
TOKEN_TTL_SECONDS = 86_400  # 24h


class AuthError(Exception):
    """认证 / 授权失败。"""


class AuthManager:
    def __init__(self, db: AIPDStateDB, secret: str = "change-me-secret"):
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
        expected = hmac.new(self._secret, f"{user_id}.{expiry}".encode("utf-8"),
                            hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected)

    # -------------------------------------------------- project authorization
    def grant_access(self, user_id: str, tenant_id: str, project_id: Optional[str] = None) -> None:
        self._db.grant_access(user_id, tenant_id, project_id)

    def require_project_access(self, user: str, tenant_id: str, project_id: str) -> None:
        """无权限时抛 :class:`AuthError`。项目级授权表 user_access。"""
        if not self._db.get_user(user):
            raise AuthError(f"unknown user {user!r}")
        if not self._db.has_access(user, tenant_id, project_id):
            raise AuthError(f"user {user!r} has no access to {tenant_id}/{project_id}")


__all__ = ["AuthManager", "AuthError"]
