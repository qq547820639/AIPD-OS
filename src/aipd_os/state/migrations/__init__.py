"""Schema 迁移运行器（包入口）。

向后兼容：所有公开符号通过本包 re-export，现有
``from aipd_os.state import migrations`` 和
``from aipd_os.state.migrations import migrate`` 等导入路径不变。

拆分结构：
- ``schema.py``       — V1 冻结文本 + SHA-256 校验
- ``helpers.py``      — 迁移步骤中使用的 callable 辅助函数
- ``definitions.py``  — MIGRATIONS 列表（每版本 up/down 定义）
- ``sqlsplit.py``     — 语句拆分/执行工具（叶子模块，打断 definitions→helpers→runner 环）
- ``runner.py``       — migrate / rollback / current_version / applied_versions
"""
from __future__ import annotations

from .definitions import MIGRATIONS
from .runner import (
    applied_versions,
    current_version,
    migrate,
    rollback,
)
from .schema import V1_FROZEN_SHA256, V1_INITIAL_SCHEMA, _v1_frozen_sha256
from .sqlsplit import exec_script, split_statements

__all__ = [
    "MIGRATIONS",
    "migrate",
    "rollback",
    "applied_versions",
    "current_version",
    "V1_INITIAL_SCHEMA",
    "V1_FROZEN_SHA256",
    "_v1_frozen_sha256",
    "split_statements",
    "exec_script",
]
