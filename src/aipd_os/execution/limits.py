"""长任务资源限制 / 并发 / 取消 / 断点恢复。

提供：

- :class:`CancellationToken`：取消标志，支持父→子取消传播；
- :class:`ResourceLimits`：资源上限（并发 / 累计时长 / 重试次数）；
- :class:`ConcurrencyGate`：并发上限（线程安全）；
- :class:`DurationBudget`：累计时长预算；
- :class:`RetryPolicy`：重试次数上限；
- :class:`TaskLimiter`：组合资源限制 + 取消传播 + 有界重试的执行器；
- :class:`CheckpointStore` / :class:`ResumableLimiter`：断点保存 / 恢复。

不引入任何第三方依赖（仅标准库）。
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional


class LimitError(Exception):
    """资源限制被触发（并发 / 时长 / 重试 / 取消）。"""


class CancelledError(LimitError):
    """任务被取消。"""


# ---------------------------------------------------------------------------
# 取消传播
# ---------------------------------------------------------------------------
class CancellationToken:
    """取消标志；子 token 与其父 token 的取消状态联动（取消传播）。"""

    def __init__(self, parent: Optional["CancellationToken"] = None) -> None:
        self._parent = parent
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def child(self) -> "CancellationToken":
        """创建一个联动父 token 的子 token（父被取消则子视为取消）。"""
        return CancellationToken(parent=self)

    def is_cancelled(self) -> bool:
        if self._cancelled:
            return True
        if self._parent is not None:
            return self._parent.is_cancelled()
        return False

    def check(self) -> None:
        """若已取消则抛 :class:`CancelledError`。"""
        if self.is_cancelled():
            raise CancelledError("task cancelled")


# ---------------------------------------------------------------------------
# 资源上限定义
# ---------------------------------------------------------------------------
@dataclass
class ResourceLimits:
    """任务资源上限。"""

    #: 并发执行 slot 上限
    max_concurrency: int = 1
    #: 累计执行时长上限（秒）；<= 0 表示不限
    max_total_duration: float = 0.0
    #: 重试次数上限；<= 0 表示不重试
    max_retries: int = 0

    def __post_init__(self) -> None:
        if self.max_concurrency < 1:
            raise ValueError("max_concurrency must be >= 1")


# ---------------------------------------------------------------------------
# 并发门
# ---------------------------------------------------------------------------
class ConcurrencyGate:
    """线程安全的并发 slot 门。"""

    def __init__(self, limit: int) -> None:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        self._limit = limit
        self._active = 0
        self._lock = threading.Condition()

    def acquire(self, timeout: Optional[float] = None) -> bool:
        """尝试获取一个 slot；超时返回 False。"""
        with self._lock:
            if self._active >= self._limit:
                return False
            self._active += 1
            return True

    def release(self) -> None:
        with self._lock:
            self._active -= 1
            if self._active < 0:
                self._active = 0

    def active(self) -> int:
        with self._lock:
            return self._active

    @property
    def limit(self) -> int:
        return self._limit

    def busy(self) -> bool:
        return self.active() >= self._limit


# ---------------------------------------------------------------------------
# 时长预算
# ---------------------------------------------------------------------------
class DurationBudget:
    """累计执行时长预算。"""

    def __init__(self, limit_seconds: float) -> None:
        self._limit = float(limit_seconds)
        self._spent = 0.0
        self._lock = threading.Lock()

    def spend(self, seconds: float) -> float:
        """记录一段执行时长，返回剩余预算。"""
        with self._lock:
            self._spent += float(seconds)
            return self._limit - self._spent

    def remaining(self) -> float:
        with self._lock:
            return self._limit - self._spent

    def exceeded(self) -> bool:
        if self._limit <= 0:
            return False  # 不限时长
        return self.remaining() < 0

    def spent(self) -> float:
        with self._lock:
            return self._spent


# ---------------------------------------------------------------------------
# 重试策略
# ---------------------------------------------------------------------------
class RetryPolicy:
    """重试次数上限控制。"""

    def __init__(self, max_retries: int) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        self._max = max_retries
        self._attempts = 0

    def record_failure(self) -> bool:
        """记录一次失败；返回是否还能重试。"""
        self._attempts += 1
        return self._attempts <= self._max

    def can_retry(self) -> bool:
        return self._attempts < self._max

    def exceeded(self) -> bool:
        return self._attempts > self._max

    def attempts(self) -> int:
        return self._attempts

    @property
    def max_retries(self) -> int:
        return self._max


# ---------------------------------------------------------------------------
# 组合执行器
# ---------------------------------------------------------------------------
class TaskLimiter:
    """组合 并发门 + 时长预算 + 重试策略 + 取消传播 的任务执行器。"""

    def __init__(self, limits: Optional[ResourceLimits] = None,
                 token: Optional[CancellationToken] = None) -> None:
        self.limits = limits or ResourceLimits()
        self.token = token or CancellationToken()
        self.concurrency = ConcurrencyGate(self.limits.max_concurrency)
        self.duration = DurationBudget(self.limits.max_total_duration)
        self.retry = RetryPolicy(self.limits.max_retries)

    def run(self, fn: Callable[[], Any]) -> Any:
        """在限制内执行 ``fn``；取消 / 并发 / 时长超限时抛 :class:`LimitError`。

        失败时按重试上限有界重试；超过上限抛出最后一次异常。
        """
        self.token.check()
        if not self.concurrency.acquire():
            raise LimitError("concurrency limit reached")
        try:
            import time
            started = time.monotonic()
            try:
                result = self._run_with_retry(fn)
            finally:
                self.duration.spend(time.monotonic() - started)
        finally:
            self.concurrency.release()
        return result

    def _run_with_retry(self, fn: Callable[[], Any]) -> Any:
        while True:
            self.token.check()
            if self.duration.exceeded():
                raise LimitError(
                    f"cumulative duration budget exceeded "
                    f"(spent={self.duration.spent():.2f}s)"
                )
            try:
                return fn()
            except (CancelledError, LimitError):
                raise
            except Exception as exc:  # noqa: BLE001 - 有界重试
                # record_failure 返回是否还能重试；不能则抛最后一次异常
                if not self.retry.record_failure():
                    raise exc


# ---------------------------------------------------------------------------
# 断点保存 / 恢复
# ---------------------------------------------------------------------------
class CheckpointStore:
    """断点存储：按名称保存 / 读取 / 列出 checkpoint。线程安全。"""

    def __init__(self, storage: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
        self._storage: Dict[str, Dict[str, Any]] = storage if storage is not None else {}
        self._lock = threading.Lock()

    def save(self, name: str, state: Any) -> str:
        """保存一个 checkpoint，返回 checkpoint id。"""
        cid = "cp-" + uuid.uuid4().hex[:12]
        with self._lock:
            self._storage[name] = {"id": cid, "state": state}
        return cid

    def load(self, name: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            entry = self._storage.get(name)
            if entry is None:
                return None
            return {"id": entry["id"], "state": entry["state"]}

    def latest(self, name: str) -> Optional[Any]:
        entry = self.load(name)
        return entry["state"] if entry else None

    def names(self) -> List[str]:
        with self._lock:
            return list(self._storage.keys())

    def clear(self, name: Optional[str] = None) -> None:
        with self._lock:
            if name is None:
                self._storage.clear()
            else:
                self._storage.pop(name, None)


class ResumableLimiter:
    """带断点恢复的长任务执行器。

    按 ``task_name`` 先恢复上次 checkpoint，再以受限方式执行；每步把进度写入
     ``CheckpointStore``，从而支持断点恢复。压力测试语义：反复保存/恢复
     过程中数据保持一致。
    """

    def __init__(self, limiter: Optional[TaskLimiter] = None,
                 store: Optional[CheckpointStore] = None) -> None:
        self.limiter = limiter or TaskLimiter()
        self.store = store or CheckpointStore()

    def resume_latest(self, task_name: str) -> Optional[Any]:
        """返回该任务上次保存的进度（无则 None）。"""
        return self.store.latest(task_name)

    def run_steps(self, task_name: str, steps: List[Callable[[], Any]],
                  checkpoint_every: int = 1) -> Dict[str, Any]:
        """恢复后按步骤执行，每步执行后保存 checkpoint。返回 {completed, checkpoint}。

        若该任务已有 checkpoint，则从上次 ``completed`` 计数继续（断点恢复语义），
        从而支持多次调用 ``run_steps`` 分段推进同一任务。
        """
        prior = self.resume_latest(task_name)
        completed = 0
        if isinstance(prior, dict) and isinstance(prior.get("completed"), (int, float)):
            completed = int(prior["completed"])
        for step in steps:
            self.limiter.run(step)
            completed += 1
            if checkpoint_every > 0 and completed % checkpoint_every == 0:
                self.store.save(task_name, {"completed": completed})
        self.store.save(task_name, {"completed": completed, "done": True})
        return {"completed": completed, "checkpoint": self.store.latest(task_name)}


__all__ = [
    "LimitError",
    "CancelledError",
    "CancellationToken",
    "ResourceLimits",
    "ConcurrencyGate",
    "DurationBudget",
    "RetryPolicy",
    "TaskLimiter",
    "CheckpointStore",
    "ResumableLimiter",
]