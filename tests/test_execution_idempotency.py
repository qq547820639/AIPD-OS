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


# ---------------------------------------------------------------------------
# 7) 外部副作用没有显式 key 时的重驱动保护（F-EXEC-01）
# ---------------------------------------------------------------------------

def _external_router(tmp_path, adapter):
    reg = AdapterRegistry()
    reg.register(adapter)
    return _router(tmp_path, reg)


def test_external_side_effect_repeat_send_is_deduped(tmp_path):
    """同一封 RFQ 被重驱动时只对外发一次。

    回归背景：幂等去重只在调用方显式给 ``idempotency_key`` 时生效，
    而产品侧唯一给 key 的是实验室数据入库；RFQ/报价登记这类
    ``EXTERNAL_SIDE_EFFECT`` 从没给过 ⇒ supervisor 重跑/用户再点一次就再发一封。
    """
    a = CountingAdapter(side_effect_mode="EXTERNAL_SIDE_EFFECT",
                        result={"sent": True, "to": "acme"})
    store, router = _external_router(tmp_path, a)
    out1 = router.run("W1", "test.count", {"supplier": "acme", "part": "壳"},
                      project_id="p1", context={"tenant_id": "t1"})
    out2 = router.run("W2", "test.count", {"supplier": "acme", "part": "壳"},
                      project_id="p1", context={"tenant_id": "t1"})
    assert out1["record"].status == "succeeded"
    assert out2.get("deduped") is True, "重复的对外发送没被拦住"
    assert out2["record"].run_id == out1["record"].run_id
    assert a.execute_count == 1


def test_external_side_effect_different_content_still_sends(tmp_path):
    """键是内容派生的：换供应商/换零件必须是新的一次发送（不许一刀切拦死）。"""
    a = CountingAdapter(side_effect_mode="EXTERNAL_SIDE_EFFECT")
    store, router = _external_router(tmp_path, a)
    router.run("W1", "test.count", {"supplier": "acme"}, project_id="p1")
    out2 = router.run("W2", "test.count", {"supplier": "other"}, project_id="p1")
    assert out2.get("deduped") is None or out2.get("deduped") is not True
    assert a.execute_count == 2


def test_external_unknown_outcome_holds_redrive(tmp_path):
    """结果未知（发送中途 transient 失败）⇒ 重驱动要挂起等人工核对，不得再发。"""
    a = CountingAdapter(side_effect_mode="EXTERNAL_SIDE_EFFECT",
                        fail_attempts=1, classification="transient")
    store, router = _external_router(tmp_path, a)
    out1 = router.run("W1", "test.count", {"supplier": "acme"}, project_id="p1")
    assert out1["record"].status == "failed"
    out2 = router.run("W2", "test.count", {"supplier": "acme"}, project_id="p1")
    assert out2.get("unknown_outcome") is True, (
        "邮件可能已经出去了却没记上——重驱动必须停在核对，而不是再发一封")
    assert a.execute_count == 1


def test_external_blocked_redrive_is_allowed(tmp_path):
    """反向控制：``external_blocked`` 表示根本没对外发过 ⇒ 重驱动应当再试一次。

    没有这条，上一条断言可能只是因为"外部副作用一律拦死"而成立。
    """
    a = CountingAdapter(side_effect_mode="EXTERNAL_SIDE_EFFECT",
                        fail_attempts=1, classification="external_blocked")
    store, router = _external_router(tmp_path, a)
    out1 = router.run("W1", "test.count", {"supplier": "acme"}, project_id="p1")
    assert out1["record"].status == "blocked_external"
    out2 = router.run("W2", "test.count", {"supplier": "acme"}, project_id="p1")
    assert out2.get("unknown_outcome") is not True
    assert a.execute_count == 2


def test_pure_capability_still_needs_explicit_key(tmp_path):
    """范围控制：无副作用能力不自动上键（自动去重会吞掉合法的重复执行）。"""
    a = CountingAdapter(side_effect_mode="PURE")
    store, router = _external_router(tmp_path, a)
    router.run("W1", "test.count", {"x": 1}, project_id="p1")
    router.run("W2", "test.count", {"x": 1}, project_id="p1")
    assert a.execute_count == 2
