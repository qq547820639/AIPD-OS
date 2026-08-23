"""Execution Router 与 Supervisor 真实闭环（P1-1）测试。

覆盖：进度/心跳、超时、取消、检查点续跑（崩溃-重启-续跑）、时长/token/
成本/工具调用记录、产物校验、写回、stale 传播、有界返工（无死循环）、
面向用户的失败消息、成熟度门槛。
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from aipd_os.execution.adapter import AdapterError, ToolAdapter
from aipd_os.execution.closure import ClosureRun
from aipd_os.execution.closure_core import (
    ArtifactVerifier,
    ClosureStep,
    ClosureStore,
    ReworkMachine,
    RunControl,
    build_failure_message,
    check_maturity_floor,
    maturity_index,
    sha256_file,
    verify_file,
)
from aipd_os.execution.execution_router import ExecutionRouter
from aipd_os.execution.runs import RunStore
from aipd_os.state.db import AIPDStateDB
from aipd_os.tool_adapters.builtin import build_registry


def _make_env(tmp_path, registry=None):
    store = RunStore(str(tmp_path / "exec.db"))
    reg = registry or build_registry()
    router = ExecutionRouter(store, reg)
    cstore = ClosureStore(str(tmp_path / "closure.db"))
    return store, reg, router, cstore


def _doc_step(step_id="s1", title="T", sections=None):
    return ClosureStep(
        step_id=step_id,
        capability_id="doc.generate",
        inputs={"title": title, "sections": sections or [{"heading": "H", "body": "b"}]},
    )


def _bind(run, cstore, registry, router, **kw):
    return run.bind(cstore, router, registry, **kw)


# ---------------------------------------------------------------------------
# 1) 进度 / 心跳
# ---------------------------------------------------------------------------
def test_progress_and_heartbeat_events(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPD_OUTPUT_DIR", str(tmp_path))
    _, registry, router, cstore = _make_env(tmp_path)
    control = RunControl()
    run = _bind(ClosureRun(control=control), cstore, registry, router,
                heartbeat_interval_s=0.001)
    result = run.execute("W1", [_doc_step()], project_id="P1")

    assert result["status"] == "complete"
    kinds = [e["kind"] for e in result["events"]]
    assert "start" in kinds
    assert "heartbeat" in kinds
    assert "step_start" in kinds
    assert "step_complete" in kinds
    assert "complete" in kinds
    seqs = [e["seq"] for e in result["events"]]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)
    hb = [e for e in result["events"] if e["kind"] == "heartbeat"]
    assert all(e["timestamp"] for e in hb)


# ---------------------------------------------------------------------------
# 2) 超时
# ---------------------------------------------------------------------------
class SlowAdapter(ToolAdapter):
    def __init__(self, sleep_s=1.0):
        self.sleep_s = sleep_s

    def capability_id(self):
        return "test.slow"

    def discover(self):
        return {"id": self.capability_id(), "name": "slow", "provider": "local",
                "version": "1", "maturity_ceiling": None, "available": True}

    def execute(self, inp):
        time.sleep(self.sleep_s)
        return {"ok": True}


# ---------------------------------------------------------------------------
# 2b) EXTERNAL_SIDE_EFFECT 失败不得被 closure 返工循环重跑
# ---------------------------------------------------------------------------
class ExternalFailingAdapter(ToolAdapter):
    """EXTERNAL_SIDE_EFFECT 且总是失败（如发邮件被 SMTP 拒绝）。"""

    def __init__(self):
        self.calls = 0

    def capability_id(self):
        return "test.external_fail"

    def discover(self):
        return {"id": self.capability_id(), "name": "ext", "provider": "local",
                "version": "1", "maturity_ceiling": None, "available": True}

    def side_effect_mode(self):
        return "EXTERNAL_SIDE_EFFECT"

    def retry_limits(self):
        return 3

    def execute(self, inp):
        self.calls += 1
        raise AdapterError("smtp rejected", classification="transient")


def test_external_side_effect_failure_not_reworked(tmp_path, monkeypatch):
    """router 层已禁重试；closure 返工循环同样不得重跑外部副作用失败记录。"""
    monkeypatch.setenv("AIPD_OUTPUT_DIR", str(tmp_path))
    reg = build_registry()
    adapter = ExternalFailingAdapter()
    reg.register(adapter)
    _, registry, router, cstore = _make_env(tmp_path, reg)
    run = _bind(ClosureRun(), cstore, registry, router, max_rework=2)
    result = run.execute("WX", [ClosureStep(step_id="ext",
                                            capability_id="test.external_fail",
                                            inputs={})])
    # 外部副作用只允许执行 1 次（此前会被返工循环重复执行）
    assert adapter.calls == 1
    # 终态 failed 并留痕（fail 事件），不进入 rework
    assert result["status"] == "failed"
    kinds = [e["kind"] for e in result["events"]]
    assert "rework" not in kinds
    assert "fail" in kinds
    assert result["failure_message"] is not None


def test_step_timeout_marks_timed_out(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPD_OUTPUT_DIR", str(tmp_path))
    reg = build_registry()
    reg.register(SlowAdapter(sleep_s=5.0))
    _, registry, router, cstore = _make_env(tmp_path, reg)
    run = _bind(ClosureRun(), cstore, registry, router, max_step_duration_s=0.05,
                max_duration_s=5.0)
    result = run.execute("TO", [ClosureStep(step_id="slow", capability_id="test.slow",
                                            inputs={})])
    assert result["status"] == "timed_out"
    assert "timed_out" in [e["kind"] for e in result["events"]]
    assert result["failure_message"] is not None
    assert "超时" in result["failure_message"]["summary"]


def test_wall_clock_timeout(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPD_OUTPUT_DIR", str(tmp_path))
    reg = build_registry()
    reg.register(SlowAdapter(sleep_s=5.0))
    _, registry, router, cstore = _make_env(tmp_path, reg)
    run = _bind(ClosureRun(), cstore, registry, router, max_duration_s=0.05,
                max_step_duration_s=10.0)
    result = run.execute("TW", [ClosureStep(step_id="slow", capability_id="test.slow",
                                            inputs={})])
    assert result["status"] == "timed_out"


# ---------------------------------------------------------------------------
# 3) 用户取消
# ---------------------------------------------------------------------------
def test_cancellation_stops_inflight(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPD_OUTPUT_DIR", str(tmp_path))
    reg = build_registry()
    reg.register(SlowAdapter(sleep_s=5.0))
    _, registry, router, cstore = _make_env(tmp_path, reg)
    control = RunControl()
    run = _bind(ClosureRun(control=control), cstore, registry, router,
                max_step_duration_s=30.0, max_duration_s=30.0)

    holder = {}

    def _worker():
        holder["result"] = run.execute(
            "CAN", [ClosureStep(step_id="slow", capability_id="test.slow", inputs={})])

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    time.sleep(0.1)
    control.cancel()
    t.join(timeout=5)
    result = holder.get("result")
    assert result is not None
    assert result["status"] == "cancelled"
    assert "cancelled" in [e["kind"] for e in result["events"]]
    assert "已取消" in result["failure_message"]["summary"]


# ---------------------------------------------------------------------------
# 4) 检查点续跑（崩溃-重启-续跑）
# ---------------------------------------------------------------------------
def test_checkpoint_resume_skips_completed_and_completes(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPD_OUTPUT_DIR", str(tmp_path))
    _, registry, router, cstore = _make_env(tmp_path)
    steps = [_doc_step("s1"), _doc_step("s2", title="Two"), _doc_step("s3", title="Three")]

    # 第一次"会话"：只完成 s1（模拟崩溃发生在 s1 检查点之后）
    run1 = _bind(ClosureRun(), cstore, registry, router)
    res1 = run1.execute("CK", [steps[0]], project_id="P1")
    assert res1["status"] == "complete"
    assert res1["steps_completed"] == ["s1"]
    run_id = res1["run_id"]
    assert len(res1["tool_calls"]) == 1  # 仅 s1

    # 崩溃-重启：全新 ClosureRun，绑定同一 store，resume 完整 steps
    run2 = _bind(ClosureRun(), cstore, registry, router)
    res2 = run2.resume(run_id, steps)
    assert res2["status"] == "complete"
    assert res2["steps_completed"] == ["s1", "s2", "s3"]
    # 若 s1 被重复执行，则工具调用总数为 4（2×s1 + s2 + s3）；实际为 3 -> 证明 s1 未重跑
    assert len(res2["tool_calls"]) == 3


# ---------------------------------------------------------------------------
# 5) 时长 / token / 成本 / 工具调用记录（诚实成本）
# ---------------------------------------------------------------------------
def test_duration_token_cost_toolcall_recording(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPD_OUTPUT_DIR", str(tmp_path))
    _, registry, router, cstore = _make_env(tmp_path)
    run = _bind(ClosureRun(), cstore, registry, router)
    result = run.execute("M", [_doc_step()])
    assert result["status"] == "complete"
    ledger = result["ledger"]
    assert ledger["duration_ms"] >= 0
    assert ledger["tokens_in"] >= 0 and ledger["tokens_out"] >= 0
    # 诚实成本：本地适配器无真实模型 -> cost=0、real_model=False
    assert ledger["cost"] == 0.0
    assert ledger["real_model"] is False
    assert result["tool_calls"]
    tc = result["tool_calls"][0]
    assert tc["tool"] == "doc.generate"
    assert tc["status"] == "succeeded"
    assert tc["real_model"] == 0
    assert tc["duration_ms"] >= 0


# ---------------------------------------------------------------------------
# 6) 产物校验
# ---------------------------------------------------------------------------
def test_artifact_verification_checks_hash_and_semantic(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPD_OUTPUT_DIR", str(tmp_path))
    _, registry, router, cstore = _make_env(tmp_path)

    def _sem(result, produced):
        md = result.get("markdown", "")
        if "T" in md:
            return True, "ok", []
        return False, "missing title", ["title not found"]

    step = ClosureStep(
        step_id="s1", capability_id="doc.generate",
        inputs={"title": "T", "sections": [{"heading": "H", "body": "b"}]},
        semantic_check=_sem)
    run = _bind(ClosureRun(), cstore, registry, router)
    result = run.execute("AV", [step])
    assert result["status"] == "complete"

    p = Path(tmp_path) / "T.md"
    assert p.exists()
    chk = verify_file(str(p), fmt="markdown", expected_sha256=sha256_file(str(p)))
    assert chk["ok"] is True
    assert chk["exists"] is True and chk["non_empty"] is True
    assert chk["format_ok"] is True and chk["sha256_ok"] is True

    # 语义不满足 -> 触发返工 -> 升级
    def _bad_sem(result, produced):
        return False, "semantic fail", ["bad"]

    bad_run = _bind(ClosureRun(), cstore, registry, router, max_rework=1)
    bad_step = ClosureStep(
        step_id="bad", capability_id="doc.generate",
        inputs={"title": "T", "sections": [{"heading": "H", "body": "b"}]},
        semantic_check=_bad_sem)
    bad_res = bad_run.execute("AVB", [bad_step])
    assert bad_res["status"] == "escalated_user"


def test_verify_file_missing(tmp_path):
    miss = verify_file(str(tmp_path / "nope.json"), fmt="json", non_empty=True)
    assert miss["exists"] is False and miss["ok"] is False


# ---------------------------------------------------------------------------
# 7) 写回 Product Truth 与 Evidence Register
# ---------------------------------------------------------------------------
def test_write_back_to_state_db(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPD_OUTPUT_DIR", str(tmp_path))
    db = AIPDStateDB(str(tmp_path / "state.db"))
    db.ensure_default_tenant("default")
    db.init_project("default", "P1", "Proj", "Goal")
    _, registry, router, cstore = _make_env(tmp_path)
    step = ClosureStep(
        step_id="s1", capability_id="doc.generate",
        inputs={"title": "T", "sections": [{"heading": "H", "body": "b"}]},
        write_back={
            "fact_key": "document.title", "fact_value": "T",
            "evidence_title": "Document generated", "evidence_kind": "execution",
        })
    run = _bind(ClosureRun(), cstore, registry, router, state_db=db, tenant_id="default")
    result = run.execute("WB", [step], project_id="P1")
    assert result["status"] == "complete"
    facts = db.list_facts("default", "P1")
    assert any(f["key"] == "document.title" and f["value"] == "T" for f in facts)
    evidence = db.list_evidence("default", "P1")
    assert any(e["title"] == "Document generated" for e in evidence)


def test_write_back_links_fact_to_evidence_not_evidence_to_itself(tmp_path, monkeypatch):
    """回归：closure 写回必须把 fact 与 evidence 正确关联。

    此前把 evidence_id 同时当 fact_id 传入 link_evidence，证据被链到它自己
    身上，``list_evidence_for_fact`` 永远查不到该事实的证据。
    """
    monkeypatch.setenv("AIPD_OUTPUT_DIR", str(tmp_path))
    db = AIPDStateDB(str(tmp_path / "state.db"))
    db.ensure_default_tenant("default")
    db.init_project("default", "P1", "Proj", "Goal")
    _, registry, router, cstore = _make_env(tmp_path)
    step = ClosureStep(
        step_id="s1", capability_id="doc.generate",
        inputs={"title": "T", "sections": [{"heading": "H", "body": "b"}]},
        write_back={
            "fact_key": "document.title", "fact_value": "T",
            "evidence_title": "Document generated", "evidence_kind": "execution",
        })
    run = _bind(ClosureRun(), cstore, registry, router, state_db=db, tenant_id="default")
    result = run.execute("WB", [step], project_id="P1")
    assert result["status"] == "complete"
    fact = next(f for f in db.list_facts("default", "P1")
                if f["key"] == "document.title")
    linked = db.list_evidence_for_fact("default", "P1", fact["fact_id"])
    assert linked, "fact 必须有证据关联（不能是 evidence→evidence 自链）"
    assert any(e["title"] == "Document generated" for e in linked)


# ---------------------------------------------------------------------------
# 8) stale 影响传播
# ---------------------------------------------------------------------------
def test_stale_propagation(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPD_OUTPUT_DIR", str(tmp_path))
    _, registry, router, cstore = _make_env(tmp_path)
    run = _bind(ClosureRun(), cstore, registry, router)
    run.start("ST", project_id="P1")
    cstore.add_dependency(run.run_id, "up", "down", "hash1")
    cstore.add_dependency(run.run_id, "up", "down2", "hash1")
    cstore.add_dependency(run.run_id, "other", "down3", "hash2")
    stale = run.propagate_stale("up", reason="input changed")
    assert {s["step_id"] for s in stale} == {"down", "down2"}
    assert len(cstore.list_stale(run.run_id)) == 2


# ---------------------------------------------------------------------------
# 9) 有界自动返工（无死循环、防重复生成）
# ---------------------------------------------------------------------------
class FlakyAdapter(ToolAdapter):
    def capability_id(self):
        return "test.flaky"

    def discover(self):
        return {"id": self.capability_id(), "name": "flaky", "provider": "local",
                "version": "1", "maturity_ceiling": None, "available": True}

    def execute(self, inp):
        raise AdapterError("boom", classification="transient")

    def retry_limits(self):
        return 1


def test_bounded_rework_no_infinite_loop(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPD_OUTPUT_DIR", str(tmp_path))
    reg = build_registry()
    reg.register(FlakyAdapter())
    _, registry, router, cstore = _make_env(tmp_path, reg)
    run = _bind(ClosureRun(), cstore, registry, router, max_rework=2)
    result = run.execute("RW", [ClosureStep(step_id="f", capability_id="test.flaky",
                                            inputs={})])
    assert result["status"] == "escalated_user"
    # 初始 1 次 + 2 次自动重做 = 3 次工具调用，有界、无死循环
    assert len(result["tool_calls"]) == 3
    assert "escalated_user" in [e["kind"] for e in result["events"]]
    assert result["failure_message"]["next_step"]


def test_rework_machine_bounds():
    rm = ReworkMachine(max_attempts=2)
    assert rm.record_failure("transient") == "rework"
    assert rm.record_failure("transient") == "rework"
    assert rm.record_failure("transient") == "escalate"
    assert rm.state == "escalated_user"
    assert rm.attempts == 3


# ---------------------------------------------------------------------------
# 10) 面向用户的失败消息
# ---------------------------------------------------------------------------
def test_failure_message_fields():
    msg = build_failure_message({
        "run_id": "R1", "work_id": "W1", "step": "s2", "reason": "超时",
        "kind": "已超时", "saved": "前 1 步已保存", "next_step": "延长超时后重试"})
    assert msg["summary"]
    assert msg["where"] == "失败位置：s2"
    assert "超时" in msg["reason"]
    assert "已保存" in msg["saved"]
    assert "重试" in msg["next_step"]
    assert msg["run_id"] == "R1"


# ---------------------------------------------------------------------------
# 11) 成熟度门槛（校验真实上限，而非仅适配器存在）
# ---------------------------------------------------------------------------
def test_maturity_floor_check(tmp_path):
    reg = build_registry()
    assert check_maturity_floor(reg, "cad.none", "C1")["ok"] is False
    assert check_maturity_floor(reg, "doc.generate", None)["ok"] is True
    assert check_maturity_floor(reg, "doc.generate", "C1")["ok"] is False
    c2 = check_maturity_floor(reg, "cad.local-brep", "C1")
    assert c2["ok"] is True and c2["actual"] == "C2"
    assert check_maturity_floor(reg, "cad.local-brep", "C3")["ok"] is False
    assert maturity_index("C2") > maturity_index("C1")


def test_maturity_floor_gates_closure_run(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPD_OUTPUT_DIR", str(tmp_path))
    _, registry, router, cstore = _make_env(tmp_path)
    run = _bind(ClosureRun(), cstore, registry, router)
    # 要求 doc.generate 达到 C1，但其未声明真实上限 -> 升级
    result = run.execute("MF", [_doc_step()], required_floors={"doc.generate": "C1"})
    assert result["status"] == "escalated_user"
    assert result["failure_message"] is not None


# ---------------------------------------------------------------------------
# ArtifactVerifier 直接校验（语义检查回调）
# ---------------------------------------------------------------------------
def test_artifact_verifier_semantic_ok_and_fail():
    verifier = ArtifactVerifier()
    ok_step = ClosureStep(step_id="s", capability_id="x", inputs={},
                          semantic_check=lambda r, p: (True, "ok", []))
    assert verifier.all_ok(verifier.verify(ok_step, [], {})) is True

    bad_step = ClosureStep(step_id="s", capability_id="x", inputs={},
                           semantic_check=lambda r, p: (False, "no", ["x"]))
    checks = verifier.verify(bad_step, [], {})
    assert verifier.all_ok(checks) is False
    sem = [c for c in checks if c.get("type") == "semantic"][0]
    assert sem["ok"] is False and sem["message"] == "no"
