"""指标计数 / 直方图 / 成本预算。

- :class:`Histogram`：按桶统计观测值分布；
- :class:`Metrics`：命名指标集合（counter / histogram）；
- :class:`CostBudget`：成本预算（累计成本，超限告警 / 触发停止）；
- :class:`Telemetry`：组合入口，整合日志 + 指标 + 成本预算。

不引入任何第三方依赖。
"""
from __future__ import annotations

import json
import threading
from typing import Any


class BudgetState:
    """成本预算状态枚举常量。"""

    OK = "ok"
    WARNING = "warning"
    EXCEEDED = "exceeded"


class BudgetExceededError(Exception):
    """成本预算超限（应停止执行）。"""

    def __init__(self, budget_name: str, spent: float, limit: float) -> None:
        self.budget_name = budget_name
        self.spent = spent
        self.limit = limit
        super().__init__(f"cost budget exceeded: {budget_name} spent={spent} limit={limit}")


class Histogram:
    """按桶统计观测值；桶边界为升序数值列表。"""

    def __init__(self, buckets: list[float]) -> None:
        self._buckets = sorted(b for b in buckets if b >= 0)
        self._counts = [0] * (len(self._buckets) + 1)
        self._sum = 0.0
        self._n = 0

    def observe(self, value: float) -> None:
        value = float(value)
        self._sum += value
        self._n += 1
        idx = 0
        for i, b in enumerate(self._buckets):
            if value > b:
                idx = i + 1
            else:
                break
        self._counts[idx] += 1

    def snapshot(self) -> dict[str, Any]:
        return {
            "count": self._n,
            "sum": round(self._sum, 6),
            "buckets": list(self._buckets),
            "bucket_counts": list(self._counts),
        }


class Metrics:
    """命名指标集合：counter（累计计数）与 histogram（分布）。线程安全。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, float] = {}
        self._histograms: dict[str, Histogram] = {}

    def inc(self, name: str, by: float = 1.0) -> None:
        with self._lock:
            self._counters[name] = self._counters.get(name, 0.0) + float(by)

    def count(self, name: str) -> float:
        with self._lock:
            return self._counters.get(name, 0.0)

    def histogram(self, name: str, buckets: list[float] | None = None) -> Histogram:
        with self._lock:
            if name not in self._histograms:
                self._histograms[name] = Histogram(buckets if buckets is not None else [0.1, 0.5, 1.0, 5.0])  # noqa: E501
            return self._histograms[name]

    def observe(self, name: str, value: float, buckets: list[float] | None = None) -> None:
        self.histogram(name, buckets).observe(value)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "counters": dict(self._counters),
                "histograms": {k: v.snapshot() for k, v in self._histograms.items()},
            }

    def to_json(self) -> str:
        return json.dumps(self.snapshot(), ensure_ascii=False, default=str)


class CostBudget:
    """累计成本预算：跟踪已花费，超限告警 / 停止。

    - ``warn_after``：超过该值进入 warning 状态（默认同 limit）；
    - ``limit``：成本硬上限，超过触发 :class:`BudgetExceededError`。
    - ``stop_on_exceed``：为 True 时 ``track()`` 在超限后抛异常（停止执行）。
    """

    def __init__(self, limit: float, warn_after: float | None = None,
                 stop_on_exceed: bool = True, name: str = "budget") -> None:
        if limit < 0:
            raise ValueError("limit must be >= 0")
        self.limit = float(limit)
        self.warn_after = float(warn_after) if warn_after is not None else self.limit
        self.stop_on_exceed = stop_on_exceed
        self.name = name
        self.spent = 0.0
        # RLock：snapshot() 在持锁时可能调用 state()，需可重入
        self._lock = threading.RLock()

    def track(self, cost: float) -> str:
        """记录一次成本；超限时按 stop_on_exceed 决定告警或抛异常。"""
        with self._lock:
            self.spent += float(cost)
            if self.spent > self.limit:
                if self.stop_on_exceed:
                    raise BudgetExceededError(self.name, self.spent, self.limit)
                return BudgetState.EXCEEDED
            if self.spent > self.warn_after:
                return BudgetState.WARNING
            return BudgetState.OK

    def state(self) -> str:
        with self._lock:
            if self.spent > self.limit:
                return BudgetState.EXCEEDED
            if self.spent > self.warn_after:
                return BudgetState.WARNING
            return BudgetState.OK

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "name": self.name,
                "spent": round(self.spent, 6),
                "limit": self.limit,
                "warn_after": self.warn_after,
                "state": self.state(),
            }


class Telemetry:
    """组合入口：合并 metrics 与 budget。"""

    def __init__(self, budget_limit: float | None = None,
                 budget_warn_after: float | None = None,
                 stop_on_exceed: bool = True) -> None:
        self.metrics = Metrics()
        # budget_limit=None 语义为「无预算上限」（此前默认 0.0，任何正成本
        # 立即超限，默认构造即陷阱）。
        self.budget = CostBudget(
            limit=budget_limit if budget_limit is not None else float("inf"),
            warn_after=budget_warn_after, stop_on_exceed=stop_on_exceed)

    def snapshot(self) -> dict[str, Any]:
        return {"metrics": self.metrics.snapshot(), "budget": self.budget.snapshot()}


__all__ = [
    "BudgetState",
    "BudgetExceededError",
    "Histogram",
    "Metrics",
    "CostBudget",
    "Telemetry",
]
