"""v5.9.1 Security / tenant isolation（§50/63）。

验证：
- tenant A 不能读取 tenant B 的 snapshot（snapshot 表 tenant scoped）；
- project A 不能批准 project B 的 snapshot（decision 按 scope 过滤）；
- project A 不能引用 project B 的 requirement/insight（拒绝后**数据库无
  残留**，§50：拒绝后数据库不能变化）；
- 跨 tenant 引用拒绝；
- snapshot/gate_evaluation 表按 tenant+project scoped。
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
    Feature,
    Insight,
    Opportunity,
    ProductDefinitionGate,
    ProductDefinitionSnapshotService,
    ProductIntelligenceService,
    ProductPrinciple,
    ProductScopeError,
    Requirement,
    SnapshotNotFoundError,
)
from aipd_os.state.db import AIPDStateDB


def _project(db, tenant, project, title="P"):
    db.init_project(tenant, project, title, "d")
    idea = IdeaService(db).create(
        Idea(idea_id="", tenant_id=tenant, project_id=project,
             title="I", raw_input="r"))
    claims = {}
    for t in ("problem", "user", "mechanism", "technology"):
        claims[t] = ClaimService(db).create(
            Claim(claim_id="", tenant_id=tenant, project_id=project,
                  idea_id=idea.idea_id, claim_type=t,
                  statement=f"c-{t}", epistemic_status="A"))
    rels = EvidenceRelationService(db)
    for c in claims.values():
        ev = db.add_evidence(tenant, project, "paper", "t",
                             url=f"https://x/{c.claim_id}")
        rel = rels.add(EvidenceRelation(
            relation_id="", tenant_id=tenant, project_id=project,
            claim_id=c.claim_id, evidence_id=ev, relation_type="supports"))
        rels.review(tenant, project, rel.relation_id, "reviewed")
    pi = ProductIntelligenceService(db)
    ins = pi.create_insight(Insight(
        insight_id="", tenant_id=tenant, project_id=project,
        idea_id=idea.idea_id, statement="ins",
        source_claim_ids=[claims["user"].claim_id]))
    opp = pi.create_opportunity(Opportunity(
        opportunity_id="", tenant_id=tenant, project_id=project,
        idea_id=idea.idea_id, title="opp", statement="s",
        source_insight_ids=[ins.insight_id]))
    pi.select_opportunity(tenant, project, opp.opportunity_id)
    prin = pi.create_principle(ProductPrinciple(
        principle_id="", tenant_id=tenant, project_id=project,
        opportunity_id=opp.opportunity_id, statement="p",
        source_insight_ids=[ins.insight_id]))
    req = pi.create_requirement(Requirement(
        requirement_id="", tenant_id=tenant, project_id=project,
        title="r", statement="r", requirement_type="interaction",
        criticality="critical", verification_method="t",
        source_principle_ids=[prin.principle_id]))
    feat = pi.create_feature(Feature(
        feature_id="", tenant_id=tenant, project_id=project,
        title="f", description="f",
        source_requirement_ids=[req.requirement_id]))
    return {"idea": idea, "pi": pi, "insight": ins, "opp": opp,
            "principle": prin, "requirement": req, "feature": feat}


@pytest.fixture
def env(tmp_path):
    db = AIPDStateDB(str(tmp_path / "s.db"))
    db.ensure_default_tenant("default")
    db.create_tenant("t2")
    pa = _project(db, "default", "pa")
    pb = _project(db, "default", "pb")
    pc = _project(db, "t2", "pc")  # tenant B 的 project
    return {"db": db, "pa": pa, "pb": pb, "pc": pc}


def test_tenant_cannot_read_other_tenant_snapshot(env):
    """tenant t2 不能读取 default tenant 的 snapshot（§50）。"""
    db = env["db"]
    snap = ProductDefinitionSnapshotService(db).create_snapshot("default", "pa")
    svc = ProductDefinitionSnapshotService(db)
    # 同 tenant 可读
    got = svc.get_snapshot("default", "pa", snap.snapshot_id)
    assert got.snapshot_id == snap.snapshot_id
    # 其他 tenant 不可读（SnapshotNotFoundError）
    with pytest.raises(SnapshotNotFoundError):
        svc.get_snapshot("t2", "pc", snap.snapshot_id)
    # 其他 tenant 的 snapshot 列表不含该 id
    assert all(s.snapshot_id != snap.snapshot_id
               for s in svc.list_snapshots("t2", "pc"))


def test_project_cannot_approve_other_project_snapshot(env):
    """project pa 的 approve 不能授权 project pb 的 snapshot（§9/50）。"""
    db = env["db"]
    snap_a = ProductDefinitionSnapshotService(db).create_snapshot("default", "pa")
    snap_b = ProductDefinitionSnapshotService(db).create_snapshot("default", "pb")
    gate_a = ProductDefinitionGate(db, "default", "pa")
    did = gate_a.propose_owner_decision(actor="owner",
                                        snapshot_id=snap_a.snapshot_id)
    gate_a.resolve_owner_decision(did, "approve", "ok", actor="owner")
    # pb 的 snapshot 在 pb scope 下无任何 effective decision
    gate_b = ProductDefinitionGate(db, "default", "pb")
    assert gate_b.authorization_status(snap_b.snapshot_id)["state"] == "PENDING"
    # pb 的 commit 尝试 → 拒绝（PENDING）
    with pytest.raises(RuntimeError, match="PENDING"):
        gate_b.commit_snapshot(snap_b, actor="owner")


def test_cross_project_ref_rejected_with_no_residue(env):
    """pa 的 feature 引用 pb 的 requirement → 拒绝；数据库无任何变化（§50）。"""
    db = env["db"]
    pi = env["pa"]["pi"]
    feat = env["pa"]["feature"]
    before = pi.get_feature("default", "pa", feat.feature_id)
    req_b = env["pb"]["requirement"]
    with pytest.raises(ProductScopeError):
        pi.update_feature("default", "pa", feat.feature_id,
                          before.version_no, "t",
                          source_requirement_ids=[req_b.requirement_id])
    after = pi.get_feature("default", "pa", feat.feature_id)
    assert after.source_requirement_ids == before.source_requirement_ids
    assert after.version_no == before.version_no
    # lineage 无新边
    from aipd_os.state.lineage import LineageNodeRef, LineageService
    edges = LineageService(db).outgoing(
        LineageNodeRef("feature", feat.feature_id, "default", "pa"))
    assert all(e.target.node_id != req_b.requirement_id for e in edges)


def test_cross_tenant_ref_rejected_with_no_residue(env):
    """default/pa 的 insight 引用 t2/pc 的 claim → 拒绝且无残留。"""
    db = env["db"]
    pi = env["pa"]["pi"]
    claim_c = [c.claim_id for c in ClaimService(db).list("t2", "pc")][0]
    with pytest.raises(ProductScopeError):
        pi.create_insight(Insight(
            insight_id="", tenant_id="default", project_id="pa",
            statement="cross tenant", source_claim_ids=[claim_c]))
    # 无残留（insights 表无新增）
    assert all(i.statement != "cross tenant"
               for i in pi.list_insights("default", "pa"))


def test_snapshot_scope_enforced_on_commit_audit(env):
    """commit audit 按 scope 记录；其他 tenant 不可见。"""
    db = env["db"]
    snap = ProductDefinitionSnapshotService(db).create_snapshot("default", "pa")
    gate = ProductDefinitionGate(db, "default", "pa")
    did = gate.propose_owner_decision(actor="owner",
                                      snapshot_id=snap.snapshot_id)
    gate.resolve_owner_decision(did, "approve", "ok", actor="owner")
    out = gate.commit_snapshot(snap, actor="owner")
    assert out["requirements"] >= 1
    # ProductTruth 记录 tenant scoped
    from aipd_os.product_truth.store import ProductTruthStore
    store = ProductTruthStore(str(db.path), tenant_id="t2", project_id="pc")
    assert store.query(record_type="requirement") == []
    store_pa = ProductTruthStore(str(db.path), tenant_id="default",
                                 project_id="pa")
    assert len(store_pa.query(record_type="requirement")) >= 1
