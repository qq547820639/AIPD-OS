"""v5.9.1 Runtime Golden E2E（§59-62/64）：Product Intelligence 全链
Supervisor → ExecutionRouter → ProductAdapter → FakeProvider → Domain Service。

**不是 Domain E2E**（Domain E2E 保留在 test_product_intelligence_golden_e2e.py）：
本文件所有阶段都由真实 Runtime routing 触发 —— Supervisor 调度 →
ExecutionRouter 路由 → ToolAdapter 执行 → Provider 生成候选 → Service
persist（lifecycle=candidate）→ Snapshot → Gate → Owner Decision →
ProductTruth。

**FakeProvider 仅测试内使用**（tests/fixtures/product）；生产 bootstrap 绝不
注册 fake（runtime probe 缺 provider 时报 EXTERNAL_DEPENDENCY，§35/38）。

覆盖：
- 完整链可执行（work items 全部 complete；5 域对象 + snapshot + gate 全产生）；
- A-H 决策场景（§62）：READY+APPROVE / REJECT / 后 REJECT 覆盖 /
  stale / 新 snapshot 需新决策 / CONDITIONAL+approve 拒绝 /
  CONDITIONAL+waiver commit / BLOCKED 永不 commit；
- Feature→Evidence 全链回溯 + Snapshot→Gate→Decision→ProductTruth 回溯；
- capability runtime（§64）：provider available→route 成功；
  provider missing→EXTERNAL_DEPENDENCY；provider exception→normalized failure；
- RuntimeContext 共享（§41/65）：同 process 单 runtime。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from aipd_os.execution.execution_router import ExecutionRouter
from aipd_os.execution.runs import RunStore
from aipd_os.idea import (
    Claim,
    ClaimService,
    EvidenceRelation,
    EvidenceRelationService,
    Idea,
    IdeaService,
)
from aipd_os.product_intelligence import (
    GATE_BLOCKED,
    GATE_CONDITIONAL,
    GATE_READY,
    ProductDefinitionGate,
    ProductDefinitionProjection,
    ProductDefinitionSnapshotService,
    ProductIntelligenceService,
)
from aipd_os.runtime import (
    PROBE_EXTERNAL,
    RuntimeContext,
    build_runtime,
)
from aipd_os.state.db import AIPDStateDB
from aipd_os.supervisor import Supervisor
from aipd_os.supervisor.idea_capabilities import (
    schedule_product_intelligence_chain,
)
from aipd_os.tool_adapters.product_adapters import (
    register_product_adapters,
)
from tests.fixtures.product.fake_product_provider import (
    FakeProductIntelligenceProvider,
)


# ---------------------------------------------------------------------------
# 装配
# ---------------------------------------------------------------------------
def _env(tmp_path):
    """Idea I2 + reviewed relations + runtime（product adapters + FakeProvider）。"""
    db_path = str(Path(tmp_path) / "state.db")
    db = AIPDStateDB(db_path)
    db.ensure_default_tenant("default")
    db.init_project("default", "p1", "Golden", "AI 帮助独居老人居家康复")
    idea = IdeaService(db).create(
        Idea(idea_id="", tenant_id="default", project_id="p1",
             title="康复", raw_input="r"))
    claims = {}
    for t in ("problem", "user", "mechanism", "technology"):
        claims[t] = ClaimService(db).create(
            Claim(claim_id="", tenant_id="default", project_id="p1",
                  idea_id=idea.idea_id, claim_type=t,
                  statement=f"c-{t}", epistemic_status="A"))
    rels = EvidenceRelationService(db)
    for c in claims.values():
        ev = db.add_evidence("default", "p1", "paper", "t",
                             url=f"https://x/{c.claim_id}")
        rel = rels.add(EvidenceRelation(
            relation_id="", tenant_id="default", project_id="p1",
            claim_id=c.claim_id, evidence_id=ev, relation_type="supports"))
        rels.review("default", "p1", rel.relation_id, "reviewed")
    provider = FakeProductIntelligenceProvider()
    sup = Supervisor(db_path, tenant_id="default", project_id="p1",
                     state_db=db)
    sup.init_lifecycle()
    reg = register_product_adapters(
        _base_registry(), db, provider=provider)
    reg2 = _base_registry()
    register_product_adapters(reg2, db, provider=provider)
    router = ExecutionRouter(RunStore(str(Path(tmp_path) / "exec.db")), reg2)
    return {"db": db, "idea": idea, "claims": claims, "provider": provider,
            "sup": sup, "registry": reg2, "router": router,
            "pi": ProductIntelligenceService(db)}


def _base_registry():
    from aipd_os.tool_adapters.builtin import build_registry
    return build_registry()


def _run_all(env, steps: int) -> list[dict]:
    results = env["sup"].run_supervisor(
        steps=steps, adapter_registry=env["registry"],
        router=env["router"], project_id="p1")
    return results or []


def _work_status(env, work_id: str) -> str:
    with sqlite3.connect(str(env["db"].path)) as conn:
        row = conn.execute(
            "SELECT status FROM supervisor_work_items WHERE work_id=?",
            (work_id,)).fetchone()
    return row[0] if row else "missing"


# ---------------------------------------------------------------------------
# 1) 完整 Runtime 链（§60/76）
# ---------------------------------------------------------------------------
def test_runtime_full_product_chain(tmp_path):
    """Idea I2 → Supervisor S2 → Router → Adapter → FakeProvider → Service
    （Insights/Opportunity/Principles/Requirements/Features）→ Snapshot →
    Gate → Owner Decision → ProductTruth。"""
    env = _env(tmp_path)
    pi = env["pi"]
    # 断言所有阶段由 Runtime 触发（对象在调度前不存在）
    assert pi.list_insights("default", "p1") == []
    assert pi.list_opportunities("default", "p1") == []

    wids_a = schedule_product_intelligence_chain(
        env["sup"], env["idea"].idea_id, steps=(
            "derive_insights", "identify_opportunity"))
    for _ in range(3):
        _run_all(env, steps=1)
    for wid in wids_a:
        assert _work_status(env, wid) == "complete", f"{wid} not complete"
    # STOP for selection（§15：Opportunity 候选后必须显式选择）
    opps = env["pi"].list_opportunities("default", "p1")
    assert len(opps) >= 1
    env["pi"].select_opportunity("default", "p1", opps[0].opportunity_id)
    wids_b = schedule_product_intelligence_chain(
        env["sup"], env["idea"].idea_id, steps=(
            "derive_principles", "derive_requirements", "derive_features",
            "create_snapshot", "definition_gate"))
    for _ in range(6):
        _run_all(env, steps=1)
    work_ids = wids_a + wids_b
    assert len(work_ids) == 7
    for wid in work_ids:
        assert _work_status(env, wid) == "complete", f"{wid} not complete"

    # 5 域对象全部由 Runtime 产生（FakeProvider candidates）
    insights = pi.list_insights("default", "p1")
    opportunities = pi.list_opportunities("default", "p1")
    principles = pi.list_principles("default", "p1")
    requirements = pi.list_requirements("default", "p1")
    features = pi.list_features("default", "p1")
    assert len(insights) >= 1
    assert len(opportunities) >= 1
    assert len(principles) >= 1
    assert len(requirements) >= 1
    assert len(features) >= 1
    # 全部 candidate（Provider 输出永远是 Candidate，§32）
    assert all(o.lifecycle_status == "candidate"
               for o in insights + opportunities + principles
               + requirements + features)
    # §15 分段语义：Segment A 产出候选，显式选择后恰好 1 个 selected
    assert sum(1 for o in opportunities
               if o.selection_status == "selected") == 1
    assert all(o.selection_status in ("candidate", "selected")
               for o in opportunities)

    # Snapshot + Gate（Runtime create_snapshot + definition_gate work items）
    snaps = ProductDefinitionSnapshotService(env["db"]).list_snapshots(
        "default", "p1")
    assert len(snaps) == 1
    proj = ProductDefinitionProjection(env["db"], "default", "p1").project()
    assert proj["snapshot"]["id"] == snaps[0].snapshot_id
    assert proj["snapshot"]["fresh"] is True

    # provider 被真实调用
    assert "insights" in env["provider"].derive_calls
    assert "features" in env["provider"].derive_calls


def test_runtime_owner_approve_commits_exact_snapshot(tmp_path):
    """Runtime 链（分段）→ owner approve（绑定 snapshot）→ ProductTruth
    commit。"""
    env = _env(tmp_path)
    _derive_runtime(env)  # §15 分段：A → select → B（snapshot+gate 已生成）
    gate = ProductDefinitionGate(env["db"], "default", "p1")
    snap = ProductDefinitionSnapshotService(env["db"]).latest_snapshot(
        "default", "p1")
    assert snap is not None
    evaluation = gate.evaluate_snapshot(snap)
    # §15：Segment B 在显式 selection 后执行 → technical 可 READY 但
    # authorization PENDING（commit eligibility NO）
    assert evaluation.result == GATE_READY
    assert gate.authorization_status(snap.snapshot_id)["state"] == "PENDING"
    # Owner approve（绑定 snapshot）+ commit
    opp = env["pi"].list_opportunities("default", "p1")[0]
    for r in env["pi"].list_requirements("default", "p1"):
        env["pi"].update_requirement("default", "p1", r.requirement_id,
                                     r.version_no, "t",
                                     lifecycle_status="active")
    for f in env["pi"].list_features("default", "p1"):
        env["pi"].update_feature("default", "p1", f.feature_id,
                                 f.version_no, "t",
                                 lifecycle_status="active")
    snap2 = ProductDefinitionSnapshotService(env["db"]).create_snapshot(
        "default", "p1")
    ev2 = gate.evaluate_snapshot(snap2)
    assert ev2.result == GATE_READY
    did = gate.propose_owner_decision(actor="owner",
                                      snapshot_id=snap2.snapshot_id)
    gate.resolve_owner_decision(did, "approve", "ok", actor="owner")
    committed = gate.commit_snapshot(snap2, actor="owner")
    assert committed["requirements"] >= 1
    assert committed["features"] >= 1
    assert committed["snapshot_id"] == snap2.snapshot_id
    # Snapshot → Gate → Decision → ProductTruth 可追溯（§61）
    from aipd_os.product_truth.store import ProductTruthStore
    store = ProductTruthStore(str(env["db"].path), tenant_id="default",
                              project_id="p1")
    reqs = store.query(record_type="requirement")
    assert all(r.metadata["source_snapshot_id"] == snap2.snapshot_id
               for r in reqs)
    assert all(r.metadata["owner_decision_id"] == did for r in reqs)
    # Feature → Evidence 全链（§61/76）
    feat = env["pi"].list_features("default", "p1")[0]
    trace = env["pi"].feature_evidence_trace(feat.feature_id, "default", "p1")
    assert trace["evidence_reached"] is True
    assert len(trace["claims"]) >= 1
    node_types = {e["source"]["node_type"] for e in trace["path"]}
    for t in ("feature", "requirement", "product_principle", "insight",
              "claim"):
        assert t in node_types
    assert any(e["target"]["node_type"] == "evidence" for e in trace["path"])


# ---------------------------------------------------------------------------
# 2) §62 A-H 决策场景（Domain 层驱动；Runtime 链已在上方验证）
# ---------------------------------------------------------------------------
def _ready_snapshot(env):
    """建到 READY 状态（select + active + freeze）。"""
    pi = env["pi"]
    opp = pi.list_opportunities("default", "p1")[0]
    pi.select_opportunity("default", "p1", opp.opportunity_id)
    for r in pi.list_requirements("default", "p1"):
        pi.update_requirement("default", "p1", r.requirement_id,
                              r.version_no, "t", lifecycle_status="active")
    for f in pi.list_features("default", "p1"):
        pi.update_feature("default", "p1", f.feature_id,
                          f.version_no, "t", lifecycle_status="active")
    return ProductDefinitionSnapshotService(env["db"]).create_snapshot(
        "default", "p1")


def test_a_ready_approve_commits(tmp_path):
    env = _env(tmp_path)
    _derive_runtime(env)
    snap = _ready_snapshot(env)
    gate = ProductDefinitionGate(env["db"], "default", "p1")
    assert gate.evaluate_snapshot(snap).result == GATE_READY
    did = gate.propose_owner_decision(actor="owner",
                                      snapshot_id=snap.snapshot_id)
    gate.resolve_owner_decision(did, "approve", "ok", actor="owner")
    out = gate.commit_snapshot(snap, actor="owner")
    assert out["requirements"] >= 1


def test_b_ready_reject_no_commit(tmp_path):
    env = _env(tmp_path)
    _derive_runtime(env)
    snap = _ready_snapshot(env)
    gate = ProductDefinitionGate(env["db"], "default", "p1")
    did = gate.propose_owner_decision(actor="owner",
                                      snapshot_id=snap.snapshot_id)
    gate.resolve_owner_decision(did, "reject", "no", actor="owner")
    with pytest.raises(RuntimeError):
        gate.commit_snapshot(snap, actor="owner")


def test_c_approve_then_reject_same_snapshot_no_commit(tmp_path):
    env = _env(tmp_path)
    _derive_runtime(env)
    snap = _ready_snapshot(env)
    gate = ProductDefinitionGate(env["db"], "default", "p1")
    d1 = gate.propose_owner_decision(actor="owner",
                                     snapshot_id=snap.snapshot_id)
    gate.resolve_owner_decision(d1, "approve", "ok", actor="owner")
    d2 = gate.propose_owner_decision(actor="owner",
                                     snapshot_id=snap.snapshot_id)
    gate.resolve_owner_decision(d2, "reject", "no", actor="owner")
    with pytest.raises(RuntimeError):
        gate.commit_snapshot(snap, actor="owner")


def test_d_approve_then_modify_then_stale_no_commit(tmp_path):
    env = _env(tmp_path)
    _derive_runtime(env)
    snap = _ready_snapshot(env)
    gate = ProductDefinitionGate(env["db"], "default", "p1")
    d1 = gate.propose_owner_decision(actor="owner",
                                     snapshot_id=snap.snapshot_id)
    gate.resolve_owner_decision(d1, "approve", "ok", actor="owner")
    req = env["pi"].list_requirements("default", "p1")[0]
    env["pi"].update_requirement("default", "p1", req.requirement_id,
                                 req.version_no, "t", title="renamed")
    with pytest.raises(RuntimeError, match="STALE"):
        gate.commit_snapshot(snap, actor="owner")


def test_e_new_snapshot_requires_new_decision(tmp_path):
    env = _env(tmp_path)
    _derive_runtime(env)
    snap_a = _ready_snapshot(env)
    gate = ProductDefinitionGate(env["db"], "default", "p1")
    d1 = gate.propose_owner_decision(actor="owner",
                                     snapshot_id=snap_a.snapshot_id)
    gate.resolve_owner_decision(d1, "approve", "ok", actor="owner")
    snap_b = _ready_snapshot(env)  # 新 snapshot（内容相同但 id 不同）
    assert gate.authorization_status(snap_b.snapshot_id)["state"] == "PENDING"
    with pytest.raises(RuntimeError, match="PENDING"):
        gate.commit_snapshot(snap_b, actor="owner")


def test_f_conditional_approve_no_commit(tmp_path):
    env = _env(tmp_path)
    _derive_runtime(env)
    req = env["pi"].list_requirements("default", "p1")[0]
    env["pi"].update_requirement("default", "p1", req.requirement_id,
                                 req.version_no, "t", epistemic_status="U")
    snap = _ready_snapshot(env)
    gate = ProductDefinitionGate(env["db"], "default", "p1")
    assert gate.evaluate_snapshot(snap).result == GATE_CONDITIONAL
    d = gate.propose_owner_decision(actor="owner",
                                    snapshot_id=snap.snapshot_id)
    gate.resolve_owner_decision(d, "approve", "ok", actor="owner")
    with pytest.raises(RuntimeError, match="APPROVE_WITH_WAIVER"):
        gate.commit_snapshot(snap, actor="owner")


def test_g_conditional_waiver_commits(tmp_path):
    env = _env(tmp_path)
    _derive_runtime(env)
    req = env["pi"].list_requirements("default", "p1")[0]
    env["pi"].update_requirement("default", "p1", req.requirement_id,
                                 req.version_no, "t", epistemic_status="U")
    snap = _ready_snapshot(env)
    gate = ProductDefinitionGate(env["db"], "default", "p1")
    d = gate.propose_owner_decision(actor="owner",
                                    snapshot_id=snap.snapshot_id)
    gate.resolve_owner_decision(
        d, "approve_with_waiver", "accept", actor="owner",
        waiver={"accepted_conditions": ["U"], "accepted_risks": ["x"],
                "owner": "owner"})
    out = gate.commit_snapshot(snap, actor="owner")
    assert out["requirements"] >= 1
    from aipd_os.product_truth.store import ProductTruthStore
    store = ProductTruthStore(str(env["db"].path), tenant_id="default",
                              project_id="p1")
    assert all(r.metadata["waiver"]["decision_id"] == d
               for r in store.query(record_type="requirement"))


def test_h_blocked_any_decision_no_commit(tmp_path):
    env = _env(tmp_path)
    _derive_runtime(env)
    req = env["pi"].list_requirements("default", "p1")[0]
    env["pi"].update_requirement("default", "p1", req.requirement_id,
                                 req.version_no, "t",
                                 definition_status="CONFLICT")
    snap = _ready_snapshot(env)
    gate = ProductDefinitionGate(env["db"], "default", "p1")
    assert gate.evaluate_snapshot(snap).result == GATE_BLOCKED
    d = gate.propose_owner_decision(actor="owner",
                                    snapshot_id=snap.snapshot_id)
    gate.resolve_owner_decision(d, "approve", "ok", actor="owner")
    with pytest.raises(RuntimeError, match="BLOCKED"):
        gate.commit_snapshot(snap, actor="owner")


def _derive_runtime(env):
    """§15 分段 Runtime 链：Segment A（insights+opportunities）→ 显式
    selection（Owner 动作）→ Segment B（principles..gate）。"""
    wids_a = schedule_product_intelligence_chain(
        env["sup"], env["idea"].idea_id, steps=(
            "derive_insights", "identify_opportunity"))
    for _ in range(3):
        _run_all(env, steps=1)
    # STOP for selection：显式选择第一个 opportunity（Owner/Policy 动作，
    # 非 provider；§15/§40）
    opps = env["pi"].list_opportunities("default", "p1")
    assert opps, "Segment A must produce opportunities"
    env["pi"].select_opportunity("default", "p1", opps[0].opportunity_id)
    wids_b = schedule_product_intelligence_chain(
        env["sup"], env["idea"].idea_id, steps=(
            "derive_principles", "derive_requirements", "derive_features",
            "create_snapshot", "definition_gate"))
    for _ in range(6):
        _run_all(env, steps=1)
    return wids_a + wids_b


# ---------------------------------------------------------------------------
# 3) Capability runtime（§64/35/38）
# ---------------------------------------------------------------------------
def test_provider_missing_is_external_dependency(tmp_path):
    """production bootstrap（provider=None）→ discover.available=False →
    probe EXTERNAL_DEPENDENCY；execute 不产生对象。"""
    env = _env(tmp_path)
    from aipd_os.tool_adapters.product_adapters import (
        ProductDeriveInsightsAdapter,
    )
    adapter = ProductDeriveInsightsAdapter(env["db"], provider=None)
    assert adapter.discover()["available"] is False
    # 独立装配 provider=None 的 registry + router（production 语义）
    reg = _base_registry()
    from aipd_os.tool_adapters.product_adapters import register_product_adapters
    register_product_adapters(reg, env["db"], provider=None)
    router = ExecutionRouter(RunStore(str(Path(tmp_path) / "exec-nop.db")),
                             reg)
    work_ids = schedule_product_intelligence_chain(
        env["sup"], env["idea"].idea_id,
        steps=("derive_insights",))
    results = env["sup"].run_supervisor(
        steps=1, adapter_registry=reg, router=router, project_id="p1") or []
    assert results and results[0]["action"] in ("blocked_external",
                                                "internal_rework")
    assert env["pi"].list_insights("default", "p1") == []
    # fail-closed（§17/49）：downstream 保持 queued/dependency-blocked
    with sqlite3.connect(str(env["db"].path)) as conn:
        statuses = [r[0] for r in conn.execute(
            "SELECT status FROM supervisor_work_items").fetchall()]
    assert "queued" in statuses or "blocked" in "".join(statuses)


def test_provider_exception_normalized_failure(tmp_path, monkeypatch):
    """provider 抛错 → 执行失败（不产生对象，不伪造成功）。"""
    env = _env(tmp_path)
    from aipd_os.product_intelligence import provider as prov_mod

    def boom(context):
        raise prov_mod.ProductProviderError("provider exploded")

    monkeypatch.setattr(env["provider"], "derive_insights", boom)
    schedule_product_intelligence_chain(
        env["sup"], env["idea"].idea_id, steps=("derive_insights",))
    results = _run_all(env, steps=1)
    assert results
    assert results[0]["action"] in ("blocked_external", "internal_rework",
                                    "failed")
    assert env["pi"].list_insights("default", "p1") == []


def test_runtime_probe_matches_provider_state(tmp_path):
    """§41/64：RuntimeContext probe 与 provider 状态一致。"""
    import os
    os.environ["AIPD_DB_DIR"] = str(tmp_path)
    rt = build_runtime(register_external=True)
    probe = rt.probe()
    assert probe["product"]["product.derive_insights"] == PROBE_EXTERNAL
    assert probe["product"]["product.definition_gate"] == "AVAILABLE"
    assert isinstance(rt, RuntimeContext)
