"""AIPD-OS 遥测包（结构化日志 / trace / 指标 / 成本预算）。

- :mod:`logging`：JSON-lines 结构化日志，含 trace_id；
- :mod:`metrics`：指标计数 / 直方图，含成本预算（超限告警 / 停止）。
"""
from __future__ import annotations

from aipd_os.telemetry.logging import (
    JsonTraceFormatter,
    TelemetryLogger,
    get_telemetry_logger,
    new_trace_id,
)
from aipd_os.telemetry.metrics import (
    BudgetExceededError,
    BudgetState,
    CostBudget,
    Histogram,
    Metrics,
    Telemetry,
)

__all__ = [
    "new_trace_id",
    "JsonTraceFormatter",
    "TelemetryLogger",
    "get_telemetry_logger",
    "Metrics",
    "Histogram",
    "CostBudget",
    "BudgetState",
    "BudgetExceededError",
    "Telemetry",
]
