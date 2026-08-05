"""AIPD-OS 跨会话状态服务（生产级）。

提供多租户多项目状态存储、认证授权、加密、迁移、备份、检查点恢复、
追加式审计日志、健康检查与对象存储，并支持本地模式与 HTTP/JSON 传输。

本包不依赖 ``mcp`` / ``fastmcp``，可独立运行。
"""
from __future__ import annotations

from .auth import AuthError, AuthManager
from .backup import BackupManager
from .checkpoint import CheckpointManager
from .crypto import decrypt_secret, encrypt_secret
from .db import (AIPDStateDB, OptimisticLockError, ProjectNotFoundError,
                 SENSITIVE_KEYS, TenantNotFoundError)
from .health import health_check
from .migrations import MIGRATIONS, current_version, migrate, rollback
from .objects import ObjectStore
from .server import StateService, main, run_http
from .audit import AuditLogger

__version__ = "5.0.0"

__all__ = [
    "AIPDStateDB", "OptimisticLockError", "ProjectNotFoundError", "TenantNotFoundError",
    "SENSITIVE_KEYS", "AuthManager", "AuthError", "encrypt_secret", "decrypt_secret",
    "migrate", "rollback", "MIGRATIONS", "current_version", "BackupManager",
    "CheckpointManager", "AuditLogger", "health_check", "ObjectStore",
    "StateService", "run_http", "main",
]
