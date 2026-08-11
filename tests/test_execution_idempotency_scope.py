"""v5.7 Commit 6：Execution Idempotency Scope 测试。

Idempotency Scope = (tenant_id, project_id, capability, idempotency_key)。
覆盖：
- same key same project same capability → dedupe（返回同记录）；
- same key different project → NOT dedupe（各执行一次）；
- same key different tenant → NOT dedupe；
- same key different capability → NOT dedupe；
- retry keeps scope（record_retry 后新 run 同 scope 且继承全部字段）；
- external side effect no duplicate execution（幂等键 + EXTERNAL_SIDE_EFFECT）；
- store 层 find_by_idempotency_scope / find_by_idempotency_key 兼容。
"""
from __future__ import annotations

import pytest

from aipd_os.execution.adapter import AdapterError, ToolAdapter
from aipd_os.execution.execution_router import ExecutionRouter
from aipd_os.execution.registry import AdapterRegistry
from aipd_os.execution.runs import RunStore


class CountingAdapter(ToolAdapter):
    """记录 execute 调用次数，支持按副作用模式/故障注入配置。"""

    def __init__(self, capability_id="test.count", classification="transient",
                 side_effect_mode="PURE", fail_attempts=0, result=None):
        self._cid = capability_id
        self._classification = classification
        self._mode = side_effect_mode
        self._fail_attempts = fail_attempts
        self._result = result if result is not None else {"ok": True}
        self.execute_count = 0

    def capability_id(self):
        return self._cid

    def discover(self):
        return {"id": self._cid, "name": self._cid, "provider": "local",
                "version": "1", "maturity_ceiling": None, "available": True}

    def execute(self, input):
        self.execute_count += 1
        if self.execute_count <= self._fail_attempts:
            raise AdapterError("boom", classification=self._classification)
        return self._result

    def normalize(self, result):
        return result if isinstance(result, dict) else {"result": result}

    def retry_limits(self):
        return 3

    def side_effect_mode(self):
        return self._mode


def _router(tmp_path):
    store = RunStore(str(tmp_path / "exec.db"))
    reg = AdapterRegistry()
    a = CountingAdapter()
    reg.register(a)
    return store, ExecutionRouter(store, reg), a


def _ctx(tenant="t1", project="p1"):
    return {"tenant_id": tenant, "project_id": project}


# ---------------------------------------------------------------------------
# 1) same key same project same capability → dedupe
# ---------------------------------------------------------------------------
def test_same_scope_dedupes(tmp_path):
    store, router, a = _router(tmp_path)
    out1 = router.run("W1", "test.count", {"x": 1},
                      context=_ctx("t1", "p1"), idempotency_key="k")
    assert out1["record"].status == "succeeded"
    out2 = router.run("W1", "test.count", {"x": 1},
                      context=_ctx("t1", "p1"), idempotency_key="k")
    assert out2["deduped"] is True
    assert out2["record"].run_id == out1["record"].run_id
    assert a.execute_count == 1


# ---------------------------------------------------------------------------
# 2) same key different project → NOT dedupe
# ---------------------------------------------------------------------------
def test_different_project_not_deduped(tmp_path):
    store, router, a = _router(tmp_path)
    out1 = router.run("W1", "test.count", {"x": 1},
                      context=_ctx("t1", "p1"), idempotency_key="k")
    out2 = router.run("W2", "test.count", {"x": 1},
                      context=_ctx("t1", "p2"), idempotency_key="k")
    assert out2.get("deduped") is not True
    assert out2["record"].run_id != out1["record"].run_id
    assert a.execute_count == 2
    assert store.get_run(out2["record"].run_id).project_id == "p2"
    assert store.get_run(out2["record"].run_id).tenant_id == "t1"


# ---------------------------------------------------------------------------
# 3) same key different tenant → NOT dedupe
# ---------------------------------------------------------------------------
def test_different_tenant_not_deduped(tmp_path):
    store, router, a = _router(tmp_path)
    out1 = router.run("W1", "test.count", {"x": 1},
                      context=_ctx("t1", "p1"), idempotency_key="k")
    out2 = router.run("W1", "test.count", {"x": 1},
                      context=_ctx("t2", "p1"), idempotency_key="k")
    assert out2.get("deduped") is not True
    assert out2["record"].run_id != out1["record"].run_id
    assert a.execute_count == 2
    assert store.get_run(out2["record"].run_id).tenant_id == "t2"


# ---------------------------------------------------------------------------
# 4) same key different capability → NOT dedupe
# ---------------------------------------------------------------------------
def test_different_capability_not_deduped(tmp_path):
    store = RunStore(str(tmp_path / "exec.db"))
    reg = AdapterRegistry()
    a1 = CountingAdapter(capability_id="test.count")
    a2 = CountingAdapter(capability_id="test.count2")
    reg.register(a1)
    reg.register(a2)
    router = ExecutionRouter(store, reg)

    out1 = router.run("W1", "test.count", {"x": 1},
                      context=_ctx("t1", "p1"), idempotency_key="k")
    out2 = router.run("W1", "test.count2", {"x": 1},
                      context=_ctx("t1", "p1"), idempotency_key="k")
    assert out2.get("deduped") is not True
    assert out2["record"].capability == "test.count2"
    assert out2["record"].run_id != out1["record"].run_id
    assert a1.execute_count == 1 and a2.execute_count == 1


# ---------------------------------------------------------------------------
# 5) retry keeps scope（record_retry 后新 run 同 scope 且继承全部字段）
# ---------------------------------------------------------------------------
def test_retry_keeps_scope(tmp_path):
    store = RunStore(str(tmp_path / "exec.db"))
    reg = AdapterRegistry()
    a = CountingAdapter(fail_attempts=1, classification="transient",
                        side_effect_mode="PURE")
    reg.register(a)
    router = ExecutionRouter(store, reg)

    out = router.run("W1", "test.count", {"x": 1},
                     context=_ctx("t9", "p9"), idempotency_key="k9")
    assert out["record"].status == "succeeded"
    runs = store.list_runs(work_id="W1")
    assert len(runs) == 2  # 首次 + 重试
    for r in runs:
        assert r.tenant_id == "t9"
        assert r.project_id == "p9"
        assert r.idempotency_key == "k9"
        assert r.capability == "test.count"
        assert r.side_effect_mode == "PURE"
    retried = [r for r in runs if r.status == "retried"][0]
    active = [r for r in runs if r.status == "succeeded"][0]
    assert active.retry_parent == retried.run_id
    assert active.retry_lineage == [retried.run_id]


# ---------------------------------------------------------------------------
# 6) external side effect no duplicate execution
# ---------------------------------------------------------------------------
def test_external_side_effect_no_duplicate_execution(tmp_path):
    store = RunStore(str(tmp_path / "exec.db"))
    reg = AdapterRegistry()
    a = CountingAdapter(side_effect_mode="EXTERNAL_SIDE_EFFECT")
    reg.register(a)
    router = ExecutionRouter(store, reg)

    out1 = router.run("W1", "test.count", {"x": 1},
                      context=_ctx("t1", "p1"), idempotency_key="ext")
    assert out1["record"].status == "succeeded"
    out2 = router.run("W1", "test.count", {"x": 1},
                      context=_ctx("t1", "p1"), idempotency_key="ext")
    assert out2["deduped"] is True
    assert out2["record"].run_id == out1["record"].run_id
    assert a.execute_count == 1  # adapter 只执行一次


def test_external_side_effect_transient_no_retry_then_scoped_dedup(tmp_path):
    """EXTERNAL_SIDE_EFFECT + transient 失败不重试（既有行为）；失败记录不参与 succeeded 去重。"""
    store = RunStore(str(tmp_path / "exec.db"))
    reg = AdapterRegistry()
    a = CountingAdapter(fail_attempts=5, classification="transient",
                        side_effect_mode="EXTERNAL_SIDE_EFFECT")
    reg.register(a)
    router = ExecutionRouter(store, reg)

    out1 = router.run("W1", "test.count", {"x": 1},
                      context=_ctx("t1", "p1"), idempotency_key="ext2")
    assert out1["record"].status == "failed"
    assert a.execute_count == 1  # 外部副作用失败即停，不重试

    # 失败记录不参与 succeeded 去重：同 scope 换成功能力再跑 → 正常执行
    a2 = CountingAdapter(capability_id="test.count2",
                         side_effect_mode="EXTERNAL_SIDE_EFFECT")
    reg.register(a2)
    out2 = router.run("W1", "test.count2", {"x": 1},
                      context=_ctx("t1", "p1"), idempotency_key="ext2")
    assert out2["record"].status == "succeeded"
    assert out2.get("deduped") is not True
    assert a2.execute_count == 1


# ---------------------------------------------------------------------------
# 7) store 层 find_by_idempotency_scope / 旧签名兼容
# ---------------------------------------------------------------------------
def test_find_by_idempotency_scope_matches_only_same_scope(tmp_path):
    store = RunStore(str(tmp_path / "exec.db"))
    store.create_run("W1", "t", "p", "1", "h", project_id="p1", tenant_id="t1",
                     capability="c1", idempotency_key="k")

    assert store.find_by_idempotency_scope("k", "t1", "p1", "c1") is not None
    assert store.find_by_idempotency_scope("k", "t2", "p1", "c1") is None
    assert store.find_by_idempotency_scope("k", "t1", "p2", "c1") is None
    assert store.find_by_idempotency_scope("k", "t1", "p1", "c2") is None
    # 旧签名（仅 key）保持全局查询兼容
    assert store.find_by_idempotency_key("k") is not None
    assert store.find_by_idempotency_key("nope") is None
