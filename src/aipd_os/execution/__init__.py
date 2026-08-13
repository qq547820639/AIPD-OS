"""AIPD-OS 执行引擎包。

提供统一执行路由（ExecutionRouter）、执行记录存储（RunStore）、
适配器抽象（ToolAdapter）与注册表（AdapterRegistry），以及决策策略。
"""

from __future__ import annotations

from aipd_os.execution.adapter import AdapterError, ToolAdapter
from aipd_os.execution.closure import ClosureRun, RunClosure
from aipd_os.execution.closure_core import (
    ArtifactVerifier,
    ClosureStep,
    ClosureStore,
    CostLedger,
    MaturityFloorError,
    ProgressEvent,
    ReworkMachine,
    RunControl,
    build_failure_message,
    check_maturity_floor,
    sha256_file,
    verify_file,
)
from aipd_os.execution.execution_router import ExecutionRouter
from aipd_os.execution.models import ExecutionRecord, ToolResult
from aipd_os.execution.registry import AdapterRegistry
from aipd_os.execution.runs import RunStore

__all__ = [
    "ExecutionRecord",
    "ToolResult",
    "AdapterError",
    "ToolAdapter",
    "AdapterRegistry",
    "RunStore",
    "ExecutionRouter",
    # P1-1 真实闭环
    "ClosureRun",
    "RunClosure",
    "ClosureStep",
    "ClosureStore",
    "CostLedger",
    "ProgressEvent",
    "RunControl",
    "ReworkMachine",
    "ArtifactVerifier",
    "verify_file",
    "sha256_file",
    "check_maturity_floor",
    "MaturityFloorError",
    "build_failure_message",
]
