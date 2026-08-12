"""v5.9.1 Product Definition Integrity 契约测试（§15/21/24/26/63）。

覆盖：
- P0-01：0 contradiction 不是 CONDITIONAL（information）；>0 才 conditional
- P0-02/03：decision 绑定 snapshot/hash；latest reject 覆盖旧 approve；
  旧 approve 不授权新 snapshot；snapshot 变化需新审批
- P0-04：CONDITIONAL 无 waiver 不能 commit；approve_with_waiver 记录 waiver；
  BLOCKED 永不 commit
- P0-05/18/19/20：update 先 validate 后 mutate；跨 project/audit/乐观锁失败
  全部回滚（object/lineage/audit 一致）
- P0-06/22/23/24：lineage reconcile（旧边 retire、新边 add、幂等）
- P0-07/26：Opportunity 显式 selection（候选不满足；多选阻塞；archived 无效）
- P0-08：Owner approval ≠ verified（trust_level 按真实来源推导）
- P0-29/30：commit exact snapshot；stale snapshot 拒绝
"""
from __future__ import annotations

import pytest

from aipd_os.idea.claim_service import ClaimService
from aipd_os.idea.claims import Claim
from aipd_os.idea.evidence_relations import (
    EvidenceRelation,
    EvidenceRelationService,
)
from aipd_os.idea.models import Idea
from aipd_os.idea.service import IdeaService
from aipd_os.product_intelligence import (
    GATE_BLOCKED,
    GATE_CONDITIONAL,
    GATE_READY,
    Feature,
    Insight,
    Opportunity,
    ProductDefinitionGate,
    ProductDefinitionSnapshot,
    ProductDefinitionSnapshotService,
    ProductIntelligenceService,
    ProductOptimisticLockError,
    ProductPrinciple,
    ProductScopeError,
    Requirement,
)
from aipd_os.state.db import AIPDStateDB
from aipd_os.state.lineage import LineageService


@pytest.fixture
def env(tmp_path):
    """Golden fixture：Idea I2 + 完整五域链。"""
    db = AIPDStateDB(str(tmp_path / "state.db"))
    db.ensure_default_tenant("default")
    db.init_project("default", "p1", "Golden", "d")
    db.init_project("default", "p2", "Other", "d")
    idea = IdeaService(db).create(
        Idea(idea_id="", tenant_id="default", project_id="p1",
             title="T", raw_input="r"))
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
    pi = ProductIntelligenceService(db)
    chain = _chain(db, pi, idea)
    return {"db": db, "idea": idea, "pi": pi, "chain": chain}


def _chain(db, pi, idea):
    with db.connect() as c:
        claim_rows = c.execute(
            "SELECT claim_id FROM claims WHERE project_id='p1' "
            "AND tenant_id='default'").fetchall()
    claims = [r["claim_id"] for r in claim_rows]
    ins = pi.create_insight(Insight(
        insight_id="", tenant_id="default", project_id="p1",
        idea_id=idea.idea_id, statement="ins",
        source_claim_ids=claims[:2]))
    opp = pi.create_opportunity(Opportunity(
        opportunity_id="", tenant_id="default", project_id="p1",
        idea_id=idea.idea_id, title="opp", statement="s",
        source_insight_ids=[ins.insight_id]))
    pi.select_opportunity("default", "p1", opp.opportunity_id)
    prin = pi.create_principle(ProductPrinciple(
        principle_id="", tenant_id="default", project_id="p1",
        opportunity_id=opp.opportunity_id, statement="p",
        source_insight_ids=[ins.insight_id]))
    req = pi.create_requirement(Requirement(
        requirement_id="", tenant_id="default", project_id="p1",
        title="r", statement="r", requirement_type="interaction",
        criticality="critical", verification_method="test",
        source_principle_ids=[prin.principle_id]))
    feat = pi.create_feature(Feature(
        feature_id="", tenant_id="default", project_id="p1",
        title="f", description="f",
        source_requirement_ids=[req.requirement_id]))
    return {"insight": ins, "opportunity": opp, "principle": prin,
            "requirement": req, "feature": feat}


def _snap(env) -> ProductDefinitionSnapshot:
    return ProductDefinitionSnapshotService(env["db"]).create_snapshot(
        "default", "p1")


# ---------------------------------------------------------------------------
# P0-01：contradiction 语义
# ---------------------------------------------------------------------------
def test_zero_contradiction_is_not_conditional(env):
    """0 contradiction → READY 相关 criterion 是 INFO（information），
    不得进入 conditional_blockers（P0-01）。"""
    snap = _snap(env)
    gate = ProductDefinitionGate(env["db"], "default", "p1")
    ev = gate.evaluate_snapshot(snap)
    assert ev.result in (GATE_READY, GATE_CONDITIONAL, GATE_BLOCKED)
    # 0 contradiction → 无 contradiction 相关 conditional 信息
    assert not any("contradict" in b for b in ev.conditional_blockers)
    # visibility 是 diagnostic information，不是 blocker
    info = " ".join(ev.information + ev.warnings)
    assert "no contradicted claims" in info


def test_contradiction_visible_as_conditional(env):
    """contradicted claim > 0 → conditional（可 review/waiver 语义），
    不再无条件 CONDITIONAL 但明确可见。"""
    db = env["db"]
    # 造一个 contradicts 且 reviewed 的 relation
    claim = ClaimService(db).list("default", "p1")[0]
    rels = EvidenceRelationService(db)
    ev2 = db.add_evidence("default", "p1", "paper", "t2",
                          url="https://x/contra")
    rel = rels.add(EvidenceRelation(
        relation_id="", tenant_id="default", project_id="p1",
        claim_id=claim.claim_id, evidence_id=ev2,
        relation_type="contradicts"))
    rels.review("default", "p1", rel.relation_id, "reviewed")
    snap = _snap(env)
    gate = ProductDefinitionGate(db, "default", "p1")
    ev = gate.evaluate_snapshot(snap)
    assert any("contradicted" in b for b in ev.conditional_blockers) or \
        any("contradicted" in b for b in ev.information)


# ---------------------------------------------------------------------------
# P0-02/03：decision 绑定与 latest semantics
# ---------------------------------------------------------------------------
def test_decision_bound_to_snapshot_hash(env):
    """decision metadata 绑定 snapshot_id + content_hash（P0-02）。"""
    snap = _snap(env)
    gate = ProductDefinitionGate(env["db"], "default", "p1")
    did = gate.propose_owner_decision(actor="owner",
                                      snapshot_id=snap.snapshot_id)
    decisions = env["db"].list_decisions("default", "p1")
    d = next(x for x in decisions if x["decision_id"] == did)
    assert d["metadata"]["snapshot_id"] == snap.snapshot_id
    assert d["metadata"]["snapshot_hash"] == snap.content_hash


def test_latest_reject_overrides_old_approve(env):
    """同一 snapshot：先 APPROVE 后 REJECT → effective = REJECT（P0-03）。"""
    snap = _snap(env)
    gate = ProductDefinitionGate(env["db"], "default", "p1")
    d1 = gate.propose_owner_decision(actor="owner",
                                     snapshot_id=snap.snapshot_id)
    gate.resolve_owner_decision(d1, "approve", "ok", actor="owner")
    d2 = gate.propose_owner_decision(actor="owner",
                                     snapshot_id=snap.snapshot_id)
    gate.resolve_owner_decision(d2, "reject", "no", actor="owner")
    effective = gate.get_effective_decision(snap.snapshot_id)
    assert effective["choice"] == "reject"
    assert effective["decision_id"] == d2
    auth = gate.authorization_status(snap.snapshot_id)
    assert auth["state"] == "REJECTED"
    # 历史 approve 保留（audit 可见）
    decisions = env["db"].list_decisions("default", "p1")
    assert any(x["decision_id"] == d1 and x["choice"] == "approve"
               for x in decisions)


def test_superseded_approval_is_audit_visible(env):
    """被覆盖的 approve 不删除，仍可审计（P0-14）。"""
    snap = _snap(env)
    gate = ProductDefinitionGate(env["db"], "default", "p1")
    d1 = gate.propose_owner_decision(actor="owner",
                                     snapshot_id=snap.snapshot_id)
    gate.resolve_owner_decision(d1, "approve", "ok", actor="owner")
    d2 = gate.propose_owner_decision(actor="owner",
                                     snapshot_id=snap.snapshot_id)
    gate.resolve_owner_decision(d2, "reject", "no", actor="owner")
    audits = env["db"].list_audit()
    resolved = [a for a in audits
                if "product_definition_gate.resolve" in (a.get("action") or "")]
    assert len(resolved) >= 2


def test_old_approve_does_not_approve_new_snapshot(env):
    """approve snapshot A 不能授权 snapshot B（hash 绑定，P0-02）。"""
    snap_a = _snap(env)
    gate = ProductDefinitionGate(env["db"], "default", "p1")
    d1 = gate.propose_owner_decision(actor="owner",
                                     snapshot_id=snap_a.snapshot_id)
    gate.resolve_owner_decision(d1, "approve", "ok", actor="owner")
    # 新 snapshot（同内容 → 不同 snapshot_id；hash 相同但 id 不同）
    snap_b = _snap(env)
    assert snap_b.snapshot_id != snap_a.snapshot_id
    auth_b = gate.authorization_status(snap_b.snapshot_id)
    assert auth_b["state"] == "PENDING"
    with pytest.raises(RuntimeError, match="owner decision PENDING"):
        gate.commit_snapshot(snap_b, actor="owner")


def test_snapshot_change_requires_new_approval(env):
    """snapshot 内容改变（对象 version bump）→ 旧审批失效（P0-30）。"""
    snap = _snap(env)
    gate = ProductDefinitionGate(env["db"], "default", "p1")
    d1 = gate.propose_owner_decision(actor="owner",
                                     snapshot_id=snap.snapshot_id)
    gate.resolve_owner_decision(d1, "approve", "ok", actor="owner")
    # 修改 requirement（version bump）→ snapshot stale
    req = env["chain"]["requirement"]
    env["pi"].update_requirement("default", "p1", req.requirement_id,
                                 req.version_no, "t", statement="changed")
    stale, reasons = ProductDefinitionSnapshotService(env["db"]).is_stale(
        snap, "default", "p1")
    assert stale and any("version changed" in r for r in reasons)
    # stale snapshot 不能 commit（即使旧 approve 存在）
    with pytest.raises(RuntimeError, match="STALE"):
        gate.commit_snapshot(snap, actor="owner")


def test_rejected_snapshot_cannot_commit(env):
    snap = _snap(env)
    gate = ProductDefinitionGate(env["db"], "default", "p1")
    d1 = gate.propose_owner_decision(actor="owner",
                                     snapshot_id=snap.snapshot_id)
    gate.resolve_owner_decision(d1, "reject", "no", actor="owner")
    with pytest.raises(RuntimeError):
        gate.commit_snapshot(snap, actor="owner")


def test_approve_then_modify_then_commit_blocked(env):
    """A-D：APPROVE → 修改 requirement → snapshot stale → 不 commit（§62）。"""
    snap = _snap(env)
    gate = ProductDefinitionGate(env["db"], "default", "p1")
    d1 = gate.propose_owner_decision(actor="owner",
                                     snapshot_id=snap.snapshot_id)
    gate.resolve_owner_decision(d1, "approve", "ok", actor="owner")
    req = env["chain"]["requirement"]
    env["pi"].update_requirement("default", "p1", req.requirement_id,
                                 req.version_no, "t", title="renamed")
    with pytest.raises(RuntimeError, match="STALE"):
        gate.commit_snapshot(snap, actor="owner")


# ---------------------------------------------------------------------------
# P0-04：CONDITIONAL / waiver
# ---------------------------------------------------------------------------
def _make_conditional(env):
    """critical requirement epistemic=U → technical CONDITIONAL。"""
    req = env["chain"]["requirement"]
    env["pi"].update_requirement("default", "p1", req.requirement_id,
                                 req.version_no, "t", epistemic_status="U")
    snap = _snap(env)
    gate = ProductDefinitionGate(env["db"], "default", "p1")
    ev = gate.evaluate_snapshot(snap)
    assert ev.result == GATE_CONDITIONAL
    return snap, gate


def test_conditional_without_waiver_cannot_commit(env):
    """F：CONDITIONAL + 普通 APPROVE → 不 commit（P0-04）。"""
    snap, gate = _make_conditional(env)
    d = gate.propose_owner_decision(actor="owner",
                                    snapshot_id=snap.snapshot_id)
    gate.resolve_owner_decision(d, "approve", "ok", actor="owner")
    with pytest.raises(RuntimeError, match="APPROVE_WITH_WAIVER"):
        gate.commit_snapshot(snap, actor="owner")


def test_conditional_with_waiver_commits_and_records(env):
    """G：CONDITIONAL + APPROVE_WITH_WAIVER → commit + waiver 记录。"""
    snap, gate = _make_conditional(env)
    d = gate.propose_owner_decision(actor="owner",
                                    snapshot_id=snap.snapshot_id)
    gate.resolve_owner_decision(
        d, "approve_with_waiver", "accept unknown", actor="owner",
        waiver={"accepted_conditions": ["critical unknown U"],
                "accepted_risks": ["verification pending"],
                "owner": "owner"})
    result = gate.commit_snapshot(snap, actor="owner")
    assert result["requirements"] >= 1
    # waiver 持久化（decision metadata + ProductTruth metadata）
    from aipd_os.product_truth.store import ProductTruthStore
    store = ProductTruthStore(str(env["db"].path), tenant_id="default",
                              project_id="p1")
    reqs = store.query(record_type="requirement")
    assert reqs and all(r.metadata.get("waiver") for r in reqs)
    assert reqs[0].metadata["waiver"]["decision_id"] == d
    assert reqs[0].metadata["waiver"]["snapshot_id"] == snap.snapshot_id
    # trust_level 仍是 unverified（waiver 不提升信任）
    assert all(r.trust_level == "unverified" for r in reqs)


def test_blocked_never_commits(env):
    """H：BLOCKED + 任何 decision → 不 commit（§62）。"""
    # 无 snapshot 时的 commit 入口
    gate = ProductDefinitionGate(env["db"], "default", "p1")
    with pytest.raises(RuntimeError):
        gate.commit_approved()
    # BLOCKED 场景：冲突
    req = env["chain"]["requirement"]
    env["pi"].update_requirement("default", "p1", req.requirement_id,
                                 req.version_no, "t",
                                 definition_status="CONFLICT")
    snap = _snap(env)
    ev = gate.evaluate_snapshot(snap)
    assert ev.result == GATE_BLOCKED
    d = gate.propose_owner_decision(actor="owner",
                                    snapshot_id=snap.snapshot_id)
    gate.resolve_owner_decision(d, "approve", "ok", actor="owner")
    with pytest.raises(RuntimeError, match="BLOCKED"):
        gate.commit_snapshot(snap, actor="owner")


# ---------------------------------------------------------------------------
# P0-05/18/20：事务化 update（§21/63）
# ---------------------------------------------------------------------------
def test_cross_project_update_rolls_back_object_change(env):
    """Opportunity update 引用 p2 insight → 先校验失败，对象零变化。"""
    pi = env["pi"]
    db = env["db"]
    # p2 的 insight
    idea2 = IdeaService(db).create(
        Idea(idea_id="", tenant_id="default", project_id="p2",
             title="I2", raw_input="r2"))
    claims2 = []
    for t in ("problem", "user", "mechanism", "technology"):
        claims2.append(ClaimService(db).create(
            Claim(claim_id="", tenant_id="default", project_id="p2",
                  idea_id=idea2.idea_id, claim_type=t,
                  statement=f"c2-{t}", epistemic_status="A")))
    ins2 = pi.create_insight(Insight(
        insight_id="", tenant_id="default", project_id="p2",
        idea_id=idea2.idea_id, statement="ins2",
        source_claim_ids=[claims2[0].claim_id]))
    opp = env["chain"]["opportunity"]
    before = pi.get_opportunity("default", "p1", opp.opportunity_id)
    with pytest.raises(ProductScopeError):
        pi.update_opportunity("default", "p1", opp.opportunity_id,
                              before.version_no, "t",
                              source_insight_ids=[ins2.insight_id])
    # 对象未变 + lineage 未变
    after = pi.get_opportunity("default", "p1", opp.opportunity_id)
    assert after.source_insight_ids == before.source_insight_ids
    assert after.version_no == before.version_no
    edges = LineageService(db).outgoing(
        __import__("aipd_os.state.lineage", fromlist=["LineageNodeRef"]).
        LineageNodeRef("opportunity", opp.opportunity_id, "default", "p1"))
    assert all(e.target.node_id in before.source_insight_ids for e in edges)


def test_invalid_ref_update_rolls_back_lineage(env):
    """feature update 引用不存在 requirement → 拒绝，lineage 无残留边。"""
    pi = env["pi"]
    feat = env["chain"]["feature"]
    before = pi.get_feature("default", "p1", feat.feature_id)
    with pytest.raises(ProductScopeError):
        pi.update_feature("default", "p1", feat.feature_id,
                          before.version_no, "t",
                          source_requirement_ids=["REQ-NOPE"])
    after = pi.get_feature("default", "p1", feat.feature_id)
    assert after.source_requirement_ids == before.source_requirement_ids
    assert after.version_no == before.version_no


def test_optimistic_lock_failure_changes_nothing(env):
    pi = env["pi"]
    req = env["chain"]["requirement"]
    v1 = pi.get_requirement("default", "p1", req.requirement_id).version_no
    # 先成功更新一次（version → v1+1），再用旧版本 v1 → 乐观锁冲突
    pi.update_requirement("default", "p1", req.requirement_id,
                          v1, "t", statement="v2")
    with pytest.raises(ProductOptimisticLockError):
        pi.update_requirement("default", "p1", req.requirement_id,
                              v1, "t", statement="hack")
    after = pi.get_requirement("default", "p1", req.requirement_id)
    assert after.statement == "v2"  # 冲突时不变
    assert after.version_no == v1 + 1


def test_audit_failure_rolls_back_update(env, monkeypatch):
    """audit 抛错 → 整个 update 回滚（对象不变）。"""
    pi = env["pi"]
    req = env["chain"]["requirement"]
    import aipd_os.state.db as dbmod
    orig = dbmod.AIPDStateDB.add_audit

    def boom(*a, **k):
        raise RuntimeError("audit exploded")

    monkeypatch.setattr(dbmod.AIPDStateDB, "add_audit", boom)
    try:
        with pytest.raises(RuntimeError, match="audit exploded"):
            pi.update_requirement("default", "p1", req.requirement_id,
                                  req.version_no, "t", statement="x")
    finally:
        monkeypatch.setattr(dbmod.AIPDStateDB, "add_audit", orig)
    after = pi.get_requirement("default", "p1", req.requirement_id)
    assert after.statement != "x"
    assert after.version_no == req.version_no


def test_lineage_failure_rolls_back_update(env, monkeypatch):
    """lineage reconcile 抛错 → update 回滚（对象 + lineage 一致）。"""
    pi = env["pi"]
    db = env["db"]
    req = env["chain"]["requirement"]
    # 备选 principle（ref 变更触发 reconcile）
    prin_b = pi.create_principle(ProductPrinciple(
        principle_id="", tenant_id="default", project_id="p1",
        opportunity_id=env["chain"]["opportunity"].opportunity_id,
        statement="pB", source_insight_ids=[env["chain"]["insight"].insight_id]))
    from aipd_os.product_intelligence import service as svc
    orig = svc.ProductIntelligenceService._reconcile_lineage

    def boom(*a, **k):
        raise RuntimeError("lineage exploded")

    monkeypatch.setattr(svc.ProductIntelligenceService,
                        "_reconcile_lineage", boom)
    try:
        with pytest.raises(RuntimeError, match="lineage exploded"):
            pi.update_requirement("default", "p1", req.requirement_id,
                                  req.version_no, "t",
                                  source_principle_ids=[prin_b.principle_id])
    finally:
        monkeypatch.setattr(svc.ProductIntelligenceService,
                            "_reconcile_lineage", orig)
    after = pi.get_requirement("default", "p1", req.requirement_id)
    # 对象回滚（仍是原 principle 源 + 原版本）
    assert after.source_principle_ids == [env["chain"]["principle"].principle_id]
    assert after.version_no == req.version_no
    # lineage 回滚（无 B 边）
    targets = _lineage_targets(db, "requirement", req.requirement_id)
    assert targets == [env["chain"]["principle"].principle_id]


def test_transaction_context_rolls_back_on_exception(env):
    """db.transaction() 异常 → 无部分写入（§19）。"""
    db = env["db"]
    before = len(db.list_audit())
    with pytest.raises(RuntimeError), db.transaction():
        db.add_audit("t", "tx.test", "p1", "default")
        raise RuntimeError("boom")
    assert len(db.list_audit()) == before


# ---------------------------------------------------------------------------
# P0-06/22/23/24：lineage reconciliation
# ---------------------------------------------------------------------------
def _lineage_targets(db, node_type, node_id):
    ls = LineageService(db)
    return sorted(e.target.node_id for e in ls.outgoing(
        __import__("aipd_os.state.lineage", fromlist=["LineageNodeRef"]).
        LineageNodeRef(node_type, node_id, "default", "p1")))


def test_requirement_source_change_retires_old_edge(env):
    """Requirement 从 Principle A → B：A 边 retired、B 边 active（§23）。"""
    pi = env["pi"]
    db = env["db"]
    # 建 principle B（同 insight 源）
    ins = env["chain"]["insight"]
    prin_b = pi.create_principle(ProductPrinciple(
        principle_id="", tenant_id="default", project_id="p1",
        opportunity_id=env["chain"]["opportunity"].opportunity_id,
        statement="pB", source_insight_ids=[ins.insight_id]))
    req = env["chain"]["requirement"]
    before = pi.get_requirement("default", "p1", req.requirement_id)
    assert _lineage_targets(db, "requirement", req.requirement_id) == \
        [env["chain"]["principle"].principle_id]
    pi.update_requirement("default", "p1", req.requirement_id,
                          before.version_no, "t",
                          source_principle_ids=[prin_b.principle_id])
    targets = _lineage_targets(db, "requirement", req.requirement_id)
    assert targets == [prin_b.principle_id]  # 只有 B（A retired）
    # A 边仍在历史（audit 可见 retired）
    edges = LineageService(db).outgoing(
        __import__("aipd_os.state.lineage", fromlist=["LineageNodeRef"]).
        LineageNodeRef("requirement", req.requirement_id, "default", "p1"))
    assert all(e.relation_type for e in edges)


def test_feature_requirement_change_retires_old_edge(env):
    pi = env["pi"]
    db = env["db"]
    req_b = pi.create_requirement(Requirement(
        requirement_id="", tenant_id="default", project_id="p1",
        title="rB", statement="rB", requirement_type="interaction",
        criticality="critical", verification_method="t",
        source_principle_ids=[env["chain"]["principle"].principle_id]))
    feat = env["chain"]["feature"]
    before = pi.get_feature("default", "p1", feat.feature_id)
    pi.update_feature("default", "p1", feat.feature_id,
                      before.version_no, "t",
                      source_requirement_ids=[req_b.requirement_id])
    targets = _lineage_targets(db, "feature", feat.feature_id)
    assert targets == [req_b.requirement_id]


def test_principle_insight_change_reconciles_edges(env):
    pi = env["pi"]
    db = env["db"]
    with db.connect() as c:
        claim_rows = c.execute(
            "SELECT claim_id FROM claims WHERE project_id='p1' "
            "AND tenant_id='default'").fetchall()
    claims = [r["claim_id"] for r in claim_rows]
    ins2 = pi.create_insight(Insight(
        insight_id="", tenant_id="default", project_id="p1",
        idea_id=env["idea"].idea_id, statement="ins2",
        source_claim_ids=[claims[2]]))
    prin = env["chain"]["principle"]
    before = pi.get_principle("default", "p1", prin.principle_id)
    pi.update_principle("default", "p1", prin.principle_id,
                        before.version_no, "t",
                        source_insight_ids=[ins2.insight_id])
    # v5.9.2 多源 lineage（§14）：principle → insight + opportunity 双边
    targets = _lineage_targets(db, "product_principle", prin.principle_id)
    assert ins2.insight_id in targets
    assert env["chain"]["opportunity"].opportunity_id in targets
    assert env["chain"]["insight"].insight_id not in targets  # 旧边 retired


def test_repeated_same_update_is_idempotent(env):
    pi = env["pi"]
    db = env["db"]
    req = env["chain"]["requirement"]
    b1 = pi.get_requirement("default", "p1", req.requirement_id)
    pi.update_requirement("default", "p1", req.requirement_id,
                          b1.version_no, "t", statement="same")
    r2 = pi.get_requirement("default", "p1", req.requirement_id)
    pi.update_requirement("default", "p1", req.requirement_id,
                          r2.version_no, "t", statement="same")
    targets = _lineage_targets(db, "requirement", req.requirement_id)
    assert targets == [env["chain"]["principle"].principle_id]


def test_retired_edge_not_used_by_active_trace(env):
    """active trace 只用 active 边（§24）。"""
    pi = env["pi"]
    # feature → req → (retired) principle B 后，trace 仍到 evidence
    trace = pi.feature_evidence_trace(env["chain"]["feature"].feature_id,
                                      "default", "p1")
    assert trace["evidence_reached"] is True


# ---------------------------------------------------------------------------
# P0-07/26：Opportunity 显式 selection
# ---------------------------------------------------------------------------
def test_candidate_opportunity_does_not_satisfy_selection_gate(env):
    """candidate（未 select）→ SELECTED_OPPORTUNITY FAIL。"""
    pi = env["pi"]
    db = env["db"]
    # 取消选择（用当前版本号：select_opportunity 已 bump）
    cur = pi.get_opportunity("default", "p1",
                             env["chain"]["opportunity"].opportunity_id)
    pi.update_opportunity("default", "p1", cur.opportunity_id,
                          cur.version_no, "t", selection_status="candidate")
    snap = _snap(env)
    gate = ProductDefinitionGate(db, "default", "p1")
    ev = gate.evaluate_snapshot(snap)
    assert any("no selected Opportunity" in b for b in ev.hard_blockers)
    assert ev.result == GATE_BLOCKED


def test_selected_opportunity_satisfies_gate(env):
    snap = _snap(env)
    gate = ProductDefinitionGate(env["db"], "default", "p1")
    ev = gate.evaluate_snapshot(snap)
    crit = next(c for c in ev.criteria_results
                if c.criterion_id == "SELECTED_OPPORTUNITY")
    assert crit.status == "PASS"


def test_multiple_selected_opportunities_block_gate(env):
    """两个 selected → 硬 blocker（单 selected 约束，§25）。"""
    pi = env["pi"]
    ins = env["chain"]["insight"]
    opp2 = pi.create_opportunity(Opportunity(
        opportunity_id="", tenant_id="default", project_id="p1",
        idea_id=env["idea"].idea_id, title="opp2", statement="s",
        source_insight_ids=[ins.insight_id]))
    snap = _snap(env)  # 先冻结（1 selected）
    pi.select_opportunity("default", "p1", opp2.opportunity_id)
    # 强制第二个 selected（绕过 select_opportunity 单约束，模拟数据损坏）
    with env["db"].connect() as c:
        c.execute("UPDATE opportunities SET selection_status='selected' "
                  "WHERE opportunity_id=? AND project_id=? AND tenant_id=?",
                  (env["chain"]["opportunity"].opportunity_id, "p1",
                   "default"))
    gate = ProductDefinitionGate(env["db"], "default", "p1")
    ev = gate.evaluate_snapshot(snap)
    assert any("multiple selected Opportunities" in b
               for b in ev.hard_blockers)


def test_archived_selected_opportunity_invalid(env):
    db = env["db"]
    opp = env["chain"]["opportunity"]
    # 直接 SQL 置 archived + selected（模拟异常状态）
    with db.connect() as c:
        c.execute("UPDATE opportunities SET lifecycle_status='archived', "
                  "selection_status='selected' WHERE opportunity_id=? "
                  "AND project_id=? AND tenant_id=?",
                  (opp.opportunity_id, "p1", "default"))
    snap = _snap(env)
    gate = ProductDefinitionGate(db, "default", "p1")
    ev = gate.evaluate_snapshot(snap)
    assert any("no selected Opportunity" in b for b in ev.hard_blockers)


# ---------------------------------------------------------------------------
# P0-08：approval ≠ verified
# ---------------------------------------------------------------------------
def test_owner_approval_not_verified_truth(env):
    """approve 后 trust_level 仍按真实来源（无 verification_test_refs →
    unverified）。"""
    snap = _snap(env)
    gate = ProductDefinitionGate(env["db"], "default", "p1")
    d = gate.propose_owner_decision(actor="owner",
                                    snapshot_id=snap.snapshot_id)
    gate.resolve_owner_decision(d, "approve", "ok", actor="owner")
    gate.commit_snapshot(snap, actor="owner")
    from aipd_os.product_truth.store import ProductTruthStore
    store = ProductTruthStore(str(env["db"].path), tenant_id="default",
                              project_id="p1")
    reqs = store.query(record_type="requirement")
    assert all(r.trust_level == "unverified" for r in reqs)
    assert all(r.metadata["approval_state"] == "approved" for r in reqs)
    assert all(r.metadata["definition_status"] == "approved" for r in reqs)


def test_trust_level_derived_from_verification_refs(env):
    """有 verification_test_refs → verified（真实验证证据，非 approve）。"""
    req = env["chain"]["requirement"]
    env["pi"].update_requirement("default", "p1", req.requirement_id,
                                 req.version_no, "t",
                                 verification_test_refs=["TEST-001"])
    snap = _snap(env)
    gate = ProductDefinitionGate(env["db"], "default", "p1")
    d = gate.propose_owner_decision(actor="owner",
                                    snapshot_id=snap.snapshot_id)
    gate.resolve_owner_decision(d, "approve", "ok", actor="owner")
    gate.commit_snapshot(snap, actor="owner")
    from aipd_os.product_truth.store import ProductTruthStore
    store = ProductTruthStore(str(env["db"].path), tenant_id="default",
                              project_id="p1")
    reqs = store.query(record_type="requirement")
    assert any(r.trust_level == "verified" for r in reqs)


# ---------------------------------------------------------------------------
# Snapshot：immutable + deterministic hash
# ---------------------------------------------------------------------------
def test_snapshot_hash_covers_id_and_version(env):
    """同 id 更新后 version 变化 → hash 变化（P0-11）。"""
    snap_a = _snap(env)
    req = env["chain"]["requirement"]
    env["pi"].update_requirement("default", "p1", req.requirement_id,
                                 req.version_no, "t", statement="v2")
    snap_b = _snap(env)
    assert snap_a.content_hash != snap_b.content_hash
    assert snap_a.requirement_refs[0]["id"] == snap_b.requirement_refs[0]["id"]
    assert snap_b.requirement_refs[0]["version"] > \
        snap_a.requirement_refs[0]["version"]


def test_snapshot_hash_deterministic(env):
    snap = _snap(env)
    assert snap.verify_hash()
    assert snap.content_hash == snap.compute_hash()
    assert len(snap.content_hash) == 64


def test_snapshot_immutable_no_update_api(env):
    """snapshot 无 UPDATE content API（immutable，P0-10）。"""
    svc = ProductDefinitionSnapshotService(env["db"])
    snap = _snap(env)
    # 没有更新方法可调（断言 API 面）
    assert not hasattr(svc, "update_snapshot")
    # 直接 SQL 改 content → hash 校验失败
    with env["db"].connect() as c:
        c.execute("UPDATE product_definition_snapshots SET "
                  "requirement_refs_json='[]' WHERE snapshot_id=? "
                  "AND project_id=? AND tenant_id=?",
                  (snap.snapshot_id, "p1", "default"))
    got = svc.get_snapshot("default", "p1", snap.snapshot_id)
    # immutable + deterministic hash：篡改 content → hash 校验失败
    assert not got.verify_hash()
    # commit 路径：closed-world stale 与 hash 完整性双防线均拒绝
    gate = ProductDefinitionGate(env["db"], "default", "p1")
    d = gate.propose_owner_decision(actor="owner",
                                    snapshot_id=snap.snapshot_id)
    gate.resolve_owner_decision(d, "approve", "ok", actor="owner")
    with pytest.raises(RuntimeError):
        gate.commit_snapshot(got, actor="owner")
