"""AIPD-OS 跨会话状态服务（生产级）。

提供多租户多项目状态存储、认证授权、加密、迁移、备份、检查点恢复、
追加式审计日志、健康检查与对象存储，并支持本地模式与 HTTP/JSON 传输。

本包不依赖 ``mcp`` / ``fastmcp``，可独立运行。
"""
from __future__ import annotations

from .audit import AuditLogger
from .auth import AuthError, AuthManager
from .backup import BackupManager
from .checkpoint import CheckpointManager
from .crypto import decrypt_secret, encrypt_secret
from .db import (
                 SENSITIVE_KEYS,
                 AIPDStateDB,
                 OptimisticLockError,
                 ProjectNotFoundError,
                 TenantNotFoundError,
)
from .health import health_check
from .lineage import (
                 DEFAULT_MAX_DEPTH,
                 LINEAGE_RELATION_TYPES,
                 LineageCycleError,
                 LineageEdge,
                 LineageNodeRef,
                 LineageRelationError,
                 LineageScopeError,
                 LineageService,
)
from .migrations import MIGRATIONS, current_version, migrate, rollback
from .objects import ObjectStore
from .recovery import (
                 APPROVAL_CATEGORIES,
                 OBJECT_TYPES,
                 AmbiguousProjectError,
                 ApprovalRequiredError,
                 UnifiedStateService,
)
from .server import StateService, main, run_http
from .state_backend import (
                 DEFAULT_TENANT,
                 ExternalDependencyError,
                 LocalStateBackend,
                 RemoteStateBackend,
                 StateBackend,
)

__version__ = "5.6.0"

__all__ = [
    "AIPDStateDB", "OptimisticLockError", "ProjectNotFoundError", "TenantNotFoundError",
    "SENSITIVE_KEYS", "AuthManager", "AuthError", "encrypt_secret", "decrypt_secret",
    "LineageService", "LineageNodeRef", "LineageEdge", "LINEAGE_RELATION_TYPES",
    "DEFAULT_MAX_DEPTH", "LineageScopeError", "LineageRelationError", "LineageCycleError",
    "migrate", "rollback", "MIGRATIONS", "current_version", "BackupManager",
    "CheckpointManager", "AuditLogger", "health_check", "ObjectStore",
    "StateService", "run_http", "main",
    # P1-5 跨会话恢复：统一状态服务 / 对象存储分层 / 备份恢复 / 恢复摘要
    "UnifiedStateService", "StateBackend", "LocalStateBackend", "RemoteStateBackend",
    "ExternalDependencyError", "AmbiguousProjectError", "ApprovalRequiredError",
    "OBJECT_TYPES", "APPROVAL_CATEGORIES", "DEFAULT_TENANT",
]
