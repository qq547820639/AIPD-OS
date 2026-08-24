"""统一 Repository / Service 错误语义。

禁止业务层直接处理 sqlite3.IntegrityError / ValueError / RuntimeError。
所有错误保留 original exception chain。

P2-M1: State Infrastructure Foundation
"""
from __future__ import annotations


class StateError(Exception):
    """所有状态层错误的基类。"""
    pass


class NotFoundError(StateError):
    """请求的实体不存在。"""
    pass


class ConflictError(StateError):
    """操作与当前状态冲突（例如唯一约束违反）。"""
    pass


class ConcurrentModificationError(ConflictError):
    """乐观并发控制检测到 lost update。

    发生在 version-based UPDATE 返回 0 rows 时。
    """
    pass


class TenantScopeViolation(StateError):
    """尝试访问或修改不属于当前 tenant 的数据。"""
    pass


class ProjectScopeViolation(StateError):
    """尝试访问或修改不属于当前 project 的数据。"""
    pass


class InvalidTransitionError(StateError):
    """状态转换不允许（例如 OPEN → CLOSED without disposition）。"""
    pass


class MigrationError(StateError):
    """数据库迁移失败。"""
    pass


class ExternalOperationUnknownError(StateError):
    """外部操作结果未知（timeout / network failure）。

    区别于 FAILED：不能推断外部系统没有执行该操作。
    """
    pass
