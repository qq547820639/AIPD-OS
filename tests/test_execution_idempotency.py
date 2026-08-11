"""Change Set 4 执行幂等测试（P0-6）+ Change Set 5 router simulated 防御（P0-7）。

覆盖：
- PURE + transient → 自动重试（与现有行为一致）；
- EXTERNAL_SIDE_EFFECT + transient → 不重试、execute 仅调 1 次、status failed；
- idempotency_key 去重：首次 succeeded 后同 key 再跑 → 返回同记录、不重复执行；
- 同 key 首跑 running → 第二次返回 in_progress、不执行；
- remote_operation_id 成功时落库并可读回；
- 无 idempotency_key 时行为与现状完全一致（向后兼容）；
- router 对 simulated 占位（顶层标记 / status=simulated / cad_contract 嵌套）降级
  blocked_external，绝不标 succeeded；
- imggen / cad 内置适配器经 router 仅占位 → blocked_external。
"""
from __future__ import annotations

from aipd_os.execution.adapter import AdapterError, ToolAdapter
from aipd_os.execution.execution_router import ExecutionRouter
from aipd_os.execution.registry import AdapterRegistry
from aipd_os.execution.runs import RunStore
from aipd_os.tool_adapters.builtin import build_registry


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


def _router(tmp_path, registry=None):
    store = RunStore(str(tmp_path / "exec.db"))
    reg = registry or build_registry()
    return store, ExecutionRouter(store, reg)


# ---------------------------------------------------------------------------
# 1) PURE + transient → 自动重试（与现有行为一致）
# ---------------------------------------------------------------------------
def test_pure_transient_retries(tmp_path):
    reg = AdapterRegistry()
    a = CountingAdapter(fail_attempts=1, side_effect_mode="PURE")
    reg.register(a)
    store, router = _router(tmp_path, reg)
    out = router.run("W", "test.count", {})
    assert out["record"].status == "succeeded"
    assert a.execute_count == 2


# ---------------------------------------------------------------------------
# 2) EXTERNAL_SIDE_EFFECT + transient → 不重试、execute 仅 1 次、status failed
# ---------------------------------------------------------------------------
def test_external_side_effect_no_retry(tmp_path):
    reg = AdapterRegistry()
    a = CountingAdapter(fail_attempts=2, side_effect_mode="EXTERNAL_SIDE_EFFECT",
                        classification="transient")
    reg.register(a)
    store, router = _router(tmp_path, reg)
    out = router.run("W", "test.count", {})
    assert out["record"].status == "failed"
    assert a.execute_count == 1


def test_external_side_effect_record_marks_mode(tmp_path):
    reg = AdapterRegistry()
    a = CountingAdapter(side_effect_mode="EXTERNAL_SIDE_EFFECT")
    reg.register(a)
    store, router = _router(tmp_path, reg)
    out = router.run("W", "test.count", {})
    assert out["record"].status == "succeeded"
    assert out["record"].side_effect_mode == "EXTERNAL_SIDE_EFFECT"
    assert store.get_run(out["record"].run_id).side_effect_mode == "EXTERNAL_SIDE_EFFECT"


# ---------------------------------------------------------------------------
# 3) idempotency_key 去重：首次 succeeded 后同 key 再跑 → 同记录、不重复执行
# ---------------------------------------------------------------------------
def test_idempotency_key_dedup_succeeded(tmp_path):
    reg = AdapterRegistry()
    a = CountingAdapter(side_effect_mode="PURE")
    reg.register(a)
    store, router = _router(tmp_path, reg)

    out1 = router.run("W", "test.count", {"x": 1}, idempotency_key="k1")
    assert out1["record"].status == "succeeded"
    assert a.execute_count == 1

    out2 = router.run("W", "test.count", {"x": 1}, idempotency_key="k1")
    assert out2["deduped"] is True
    assert out2["record"].run_id == out1["record"].run_id
    assert out2["result"] == {"ok": True}
    assert a.execute_count == 1  # 未重复调用 adapter


# ---------------------------------------------------------------------------
# 4) 同 key 首跑 running → 第二次返回 in_progress、不执行
# ---------------------------------------------------------------------------
def test_idempotency_key_in_progress(tmp_path):
    reg = AdapterRegistry()
    a = CountingAdapter(side_effect_mode="PURE")
    reg.register(a)
    store, router = _router(tmp_path, reg)
    store.create_run("W", "test.count", "local", "1", "h", idempotency_key="k2",
                     side_effect_mode="PURE", capability="test.count",
                     adapter_id="test.count")

    out = router.run("W", "test.count", {}, idempotency_key="k2")
    assert out["deduped"] is True
    assert out["in_progress"] is True
    assert out["result"] is None
    assert a.execute_count == 0


# ---------------------------------------------------------------------------
# 5) remote_operation_id 成功时落库并可读回
# ---------------------------------------------------------------------------
def test_remote_operation_id_recorded(tmp_path):
    reg = AdapterRegistry()
    a = CountingAdapter(side_effect_mode="EXTERNAL_SIDE_EFFECT",
                        result={"ok": True, "remote_operation_id": "op-123"})
    reg.register(a)
    store, router = _router(tmp_path, reg)
    out = router.run("W", "test.count", {})
    assert out["record"].status == "succeeded"
    assert out["record"].remote_operation_id == "op-123"
    from_db = store.get_run(out["record"].run_id)
    assert from_db.remote_operation_id == "op-123"


def test_remote_operation_id_from_meta(tmp_path):
    reg = AdapterRegistry()
    a = CountingAdapter(side_effect_mode="EXTERNAL_SIDE_EFFECT",
                        result={"ok": True, "_meta": {"remote_operation_id": "op-meta"}})
    reg.register(a)
    store, router = _router(tmp_path, reg)
    out = router.run("W", "test.count", {})
    assert out["record"].status == "succeeded"
    assert out["record"].remote_operation_id == "op-meta"


# ---------------------------------------------------------------------------
# 6) 无 idempotency_key 时行为与现状一致（向后兼容）
# ---------------------------------------------------------------------------
def test_no_idempotency_key_runs_twice(tmp_path):
    reg = AdapterRegistry()
    a = CountingAdapter(side_effect_mode="PURE")
    reg.register(a)
    store, router = _router(tmp_path, reg)
    router.run("W", "test.count", {})
    router.run("W", "test.count", {})
    assert a.execute_count == 2
    assert len(store.list_runs(work_id="W")) == 2


# ---------------------------------------------------------------------------
# CS5: router simulated 防御
# ---------------------------------------------------------------------------
class SimulatedAdapter(ToolAdapter):
    def __init__(self, result):
        self._result = result
        self.execute_count = 0

    def capability_id(self):
        return "test.sim"

    def discover(self):
        return {"id": self.capability_id(), "name": "sim", "provider": "local",
                "version": "1", "maturity_ceiling": None, "available": True}

    def execute(self, input):
        self.execute_count += 1
        return self._result

    def normalize(self, result):
        return result if isinstance(result, dict) else {"result": result}

    def retry_limits(self):
        return 1

    def side_effect_mode(self):
        return "PURE"


def test_router_rejects_simulated_flag(tmp_path):
    reg = AdapterRegistry()
    a = SimulatedAdapter({"simulated": True, "data": "x"})
    reg.register(a)
    store, router = _router(tmp_path, reg)
    out = router.run("W", "test.sim", {})
    assert out["record"].status == "blocked_external"
    assert out["record"].error_classification == "external_blocked"
    assert out["result"] is None
    assert a.execute_count == 1


def test_router_rejects_simulated_status(tmp_path):
    reg = AdapterRegistry()
    a = SimulatedAdapter({"status": "simulated", "prompt": "p"})
    reg.register(a)
    store, router = _router(tmp_path, reg)
    out = router.run("W", "test.sim", {})
    assert out["record"].status == "blocked_external"
    assert "simulated" in out["record"].error_message
    assert out["result"] is None


def test_router_rejects_simulated_nested_contract(tmp_path):
    reg = AdapterRegistry()
    a = SimulatedAdapter({"cad_contract": {"status": "simulated", "desc": "d"}})
    reg.register(a)
    store, router = _router(tmp_path, reg)
    out = router.run("W", "test.sim", {})
    assert out["record"].status == "blocked_external"
    assert out["result"] is None


def test_router_accepts_normal_result(tmp_path):
    reg = AdapterRegistry()
    a = SimulatedAdapter({"ok": True})
    reg.register(a)
    store, router = _router(tmp_path, reg)
    out = router.run("W", "test.sim", {})
    assert out["record"].status == "succeeded"
    assert out["result"] == {"ok": True}


def test_imggen_placeholder_blocked_via_router(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPD_IMGGEN_BACKEND", "dummy")
    monkeypatch.setenv("AIPD_OUTPUT_DIR", str(tmp_path))
    reg = build_registry()
    store, router = _router(tmp_path, reg)
    out = router.run("W", "manual.imggen", {"prompt": "p"})
    assert out["record"].status == "blocked_external"
    assert out["record"].error_classification == "external_blocked"
    assert out["result"] is None


def test_cad_placeholder_blocked_via_router(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPD_CAD_PROVIDER", "dummy")
    monkeypatch.setenv("AIPD_OUTPUT_DIR", str(tmp_path))
    reg = build_registry()
    store, router = _router(tmp_path, reg)
    out = router.run("W", "cad.text-to-cad", {"description": "a bracket"})
    assert out["record"].status == "blocked_external"
    assert out["record"].error_classification == "external_blocked"
    assert out["result"] is None
