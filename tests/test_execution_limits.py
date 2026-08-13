"""长任务资源限制 / 并发 / 取消 / 断点恢复测试。"""
from __future__ import annotations

import pytest

from aipd_os.execution.limits import (
    CancellationToken,
    CancelledError,
    CheckpointStore,
    ConcurrencyGate,
    DurationBudget,
    LimitError,
    ResourceLimits,
    ResumableLimiter,
    RetryPolicy,
    TaskLimiter,
)


def test_concurrency_gate_honors_limit():
    gate = ConcurrencyGate(2)
    assert gate.acquire() is True
    assert gate.acquire() is True
    assert gate.acquire() is False  # 超限
    assert gate.active() == 2
    assert gate.busy() is True
    gate.release()
    assert gate.active() == 1
    assert gate.acquire() is True


def test_duration_budget():
    b = DurationBudget(10.0)
    assert b.spend(4.0) == pytest.approx(6.0)
    assert b.remaining() == pytest.approx(6.0)
    assert b.exceeded() is False
    b.spend(7.0)
    assert b.exceeded() is True


def test_duration_budget_unlimited():
    b = DurationBudget(0.0)
    assert b.exceeded() is False  # 不限时长


def test_retry_policy_bounds():
    rp = RetryPolicy(max_retries=2)
    assert rp.record_failure() is True
    assert rp.record_failure() is True
    assert rp.record_failure() is False
    assert rp.exceeded() is True
    assert rp.attempts() == 3


def test_cancellation_propagates_to_child():
    parent = CancellationToken()
    child = parent.child()
    assert child.is_cancelled() is False
    parent.cancel()
    assert child.is_cancelled() is True
    with pytest.raises(CancelledError):
        child.check()


def test_tasklimiter_raises_on_cancelled():
    limiter = TaskLimiter()
    limiter.token.cancel()
    with pytest.raises(CancelledError):
        limiter.run(lambda: "never")


def test_tasklimiter_concurrency_limit():
    limiter = TaskLimiter(ResourceLimits(max_concurrency=1))
    # 占用唯一 slot
    limiter.concurrency.acquire()
    with pytest.raises(LimitError):
        limiter.run(lambda: "x")


def test_tasklimiter_duration_exceeded():
    limiter = TaskLimiter(ResourceLimits(max_concurrency=1, max_total_duration=0.05))
    limiter.duration.spend(0.06)  # 已超累计时长预算
    with pytest.raises(LimitError):
        limiter.run(lambda: None)


def test_tasklimiter_bounded_retry():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("transient")
        return "done"

    limiter = TaskLimiter(ResourceLimits(max_concurrency=1, max_retries=3))
    assert limiter.run(flaky) == "done"
    assert calls["n"] == 3


def test_tasklimiter_retry_exhausted_raises():
    calls = {"n": 0}

    def always_fail():
        calls["n"] += 1
        raise ValueError("boom")

    limiter = TaskLimiter(ResourceLimits(max_concurrency=1, max_retries=1))
    with pytest.raises(ValueError):
        limiter.run(always_fail)
    assert calls["n"] == 2  # 首次 + 1 次重试


def test_checkpoint_save_restore_consistency():
    store = CheckpointStore()
    store.save("taskA", {"completed": 3})
    cp = store.load("taskA")
    assert cp["state"]["completed"] == 3
    assert store.latest("taskA") == {"completed": 3}
    assert "taskA" in store.names()
    assert store.load("missing") is None


def test_resumable_limiter_resume_and_stress():
    store = CheckpointStore()
    limiter = ResumableLimiter(store=store)
    steps = [lambda: None, lambda: None, lambda: None]

    # 第一轮：执行 3 步，每步保存 checkpoint
    res = limiter.run_steps("job", steps, checkpoint_every=1)
    assert res["completed"] == 3
    assert res["checkpoint"]["completed"] == 3

    # 模拟“崩溃后恢复”：新执行器从同一 store 读取到上次进度
    limiter2 = ResumableLimiter(store=store)
    assert limiter2.resume_latest("job") == {"completed": 3, "done": True}

    # 压力：反复保存/恢复，数据保持一致
    prev = None
    for _ in range(50):
        store.save("job", {"completed": 3, "done": True})
        cur = store.latest("job")
        assert cur == {"completed": 3, "done": True}
        prev = cur
    assert prev == {"completed": 3, "done": True}


def test_resumable_limiter_continues_from_checkpoint():
    executed = {"n": 0}

    def step():
        executed["n"] += 1
        return executed["n"]

    store = CheckpointStore()
    limiter = ResumableLimiter(store=store)
    # 先跑 2 步
    limiter.run_steps("job2", [step, step], checkpoint_every=1)
    assert store.latest("job2")["completed"] == 2
    # 复用同一执行器继续跑第 3 步 → 断点恢复语义
    limiter.run_steps("job2", [step], checkpoint_every=1)
    assert store.latest("job2")["completed"] == 3
    assert executed["n"] == 3
