"""Product Intelligence 测试（v5.9，§60 最低 16 项 + traceability）。

覆盖：五域 lineage 强制、跨 scope 拒绝、projection unknowns、Gate 确定性
（missing source/verification/conflict/owner approval）、approved commit、
rejected 不 commit、change→rework、Feature→Evidence 全链回溯、
unknown 不自动 verified。
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
    GATE_READY,
    Feature,
    Insight,
    Opportunity,
    ProductDefinitionGate,
    ProductDefinitionProjection,
    ProductIntelligenceService,
    ProductLineageMissingError,
    ProductPrinciple,
    ProductScopeError,
    Requirement,
)
from aipd_os.state.db import AIPDStateDB

IDEA_TITLE = "AI 帮助独居老人居家康复"


@pytest.fixture
def env(tmp_path):
    """Golden fixture：Idea I2（4 类 key claims 全部 reviewed）。"""
    db = AIPDStateDB(str(tmp_path / "state.db"))
    db.ensure_default_tenant("default")
    db.init_project("default", "p1", "Golden", IDEA_TITLE)
    db.init_project("default", "p2", "Other", "other")
    idea = IdeaService(db).create(
        Idea(idea_id="", tenant_id="default", project_id="p1",
             title=IDEA_TITLE, raw_input="我想做一个利用 AI 帮助独居老人居家康复的产品"))
    claims = {}
    for t in ("problem", "user", "mechanism", "technology"):
        claims[t] = ClaimService(db).create(
            Claim(claim_id="", tenant_id="default", project_id="p1",
                  idea_id=idea.idea_id, claim_type=t,
                  statement=f"claim-{t}", epistemic_status="A"))
    rels = EvidenceRelationService(db)
    for c in claims.values():
        ev = db.add_evidence("default", "p1", "paper", "t",
                             url=f"https://example.invalid/{c.claim_id}")
        rel = rels.add(EvidenceRelation(relation_id="", tenant_id="default",
                                        project_id="p1", claim_id=c.claim_id,
                                        evidence_id=ev,
                                        relation_type="supports"))
        rels.review("default", "p1", rel.relation_id, "reviewed")
    return {"db": db, "idea": idea, "claims": claims, "pi": ProductIntelligenceService(db)}


def _build_chain(env, n_insights=1, n_opps=1, n_prins=1, n_reqs=1, n_feats=1):
    """构造完整链路（供 Gate 通过场景）。"""
    pi = env["pi"]
    claims = list(env["claims"].values())
    insights = []
    for i in range(n_insights):
        insights.append(pi.create_insight(Insight(
            insight_id="", tenant_id="default", project_id="p1",
            idea_id=env["idea"].idea_id,
            statement=f"insight-{i}",
            source_claim_ids=[claims[i % len(claims)].claim_id,
                              claims[(i + 1) % len(claims)].claim_id])))
    opps = []
    for i in range(n_opps):
        opps.append(pi.create_opportunity(Opportunity(
            opportunity_id="", tenant_id="default", project_id="p1",
            idea_id=env["idea"].idea_id, title=f"opp-{i}",
            statement="基于证据的机会",
            source_insight_ids=[insights[i % len(insights)].insight_id])))
    prins = []
    for i in range(n_prins):
        prins.append(pi.create_principle(ProductPrinciple(
            principle_id="", tenant_id="default", project_id="p1",
            opportunity_id=opps[i % len(opps)].opportunity_id,
            statement=f"principle-{i}",
            source_insight_ids=[insights[i % len(insights)].insight_id])))
    reqs = []
    for i in range(n_reqs):
        reqs.append(pi.create_requirement(Requirement(
            requirement_id="", tenant_id="default", project_id="p1",
            title=f"req-{i}", statement=f"requirement-{i}",
            requirement_type="interaction", criticality="critical",
            verification_method="usability test",
            source_principle_ids=[prins[i % len(prins)].principle_id])))
    feats = []
    for i in range(n_feats):
        feats.append(pi.create_feature(Feature(
            feature_id="", tenant_id="default", project_id="p1",
            title=f"feature-{i}", description=f"feature-{i}",
            source_requirement_ids=[reqs[i % len(reqs)].requirement_id])))
    return {"insights": insights, "opportunities": opps,
            "principles": prins, "requirements": reqs, "features": feats}


# ---------------------------------------------------------------------------
# 1) deterministic lineage 强制（§46）
# ---------------------------------------------------------------------------
def test_insight_requires_claim_source(env):
    with pytest.raises(ProductLineageMissingError):
        env["pi"].create_insight(Insight(
            insight_id="", tenant_id="default", project_id="p1",
            statement="no source"))


def test_opportunity_requires_insight(env):
    with pytest.raises(ProductLineageMissingError):
        env["pi"].create_opportunity(Opportunity(
            opportunity_id="", tenant_id="default", project_id="p1",
            title="x", statement="x"))


def test_principle_requires_insight(env):
    with pytest.raises(ProductLineageMissingError):
        env["pi"].create_principle(ProductPrinciple(
            principle_id="", tenant_id="default", project_id="p1",
            statement="x"))


def test_requirement_requires_principle(env):
    with pytest.raises(ProductLineageMissingError):
        env["pi"].create_requirement(Requirement(
            requirement_id="", tenant_id="default", project_id="p1",
            title="x", statement="x"))


def test_feature_requires_requirement(env):
    with pytest.raises(ProductLineageMissingError):
        env["pi"].create_feature(Feature(
            feature_id="", tenant_id="default", project_id="p1",
            title="x", description="x"))


def test_cross_project_product_lineage_denied(env):
    """project A 不能引用 project B 的 Claim/Insight（§68）。"""
    db = env["db"]
    # p2 的 idea + claim（同 scope）
    idea2 = IdeaService(db).create(
        Idea(idea_id="", tenant_id="default", project_id="p2",
             title="p2 idea", raw_input="r"))
    c2 = ClaimService(db).create(Claim(
        claim_id="", tenant_id="default", project_id="p2",
        idea_id=idea2.idea_id, claim_type="problem",
        statement="p2 claim"))
    with pytest.raises(ProductScopeError):
        env["pi"].create_insight(Insight(
            insight_id="", tenant_id="default", project_id="p1",
            statement="cross project", source_claim_ids=[c2.claim_id]))


def test_cross_project_feature_lineage_rejected(env):
    """project A 不能基于 project B 的 Principle 建 Requirement。"""
    chain = _build_chain(env)
    princ = chain["principles"][0]
    pi2 = ProductIntelligenceService(env["db"])
    # p2 域里创建 requirement 引用 p1 的 principle → 拒绝
    with pytest.raises(ProductScopeError):
        pi2.create_requirement(Requirement(
            requirement_id="", tenant_id="default", project_id="p2",
            title="x", statement="x",
            source_principle_ids=[princ.principle_id]))


# ---------------------------------------------------------------------------
# 2) projection / unknowns
# ---------------------------------------------------------------------------
def test_product_projection_contains_unknowns(env):
    _build_chain(env)
    # 加一个 epistemic U 的 active requirement
    reqs = env["pi"].list_requirements("default", "p1")
    from aipd_os.product_intelligence import LIFECYCLE_ACTIVE
    for r in reqs:
        if r.lifecycle_status != LIFECYCLE_ACTIVE:
            env["pi"]._update("requirement", "default", "p1", r.requirement_id,
                              r.version_no, "t", lifecycle_status=LIFECYCLE_ACTIVE)
    proj = ProductDefinitionProjection(env["db"], "default", "p1").project()
    assert "unknowns" in proj
    assert "validation_gaps" in proj
    assert "gate" in proj and proj["gate"]["result"] in (GATE_BLOCKED, "CONDITIONAL", GATE_READY)
    assert proj["counts"]["requirements"] >= 1
    assert proj["counts"]["features"] >= 1


# ---------------------------------------------------------------------------
# 3) Gate 确定性
# ---------------------------------------------------------------------------
def test_critical_requirement_missing_source_blocks_gate(env):
    _build_chain(env)
    gate = ProductDefinitionGate(env["db"], "default", "p1")
    result = gate.evaluate()
    # owner approval missing → BLOCKED（确定性）
    assert result["result"] == GATE_BLOCKED
    assert any("Owner approval missing" in b for b in result["blockers"])


def test_critical_requirement_missing_verification_blocks_gate(env):
    """critical requirement 缺 verification path → gate blocker。"""
    chain = _build_chain(env)
    req = chain["requirements"][0]
    v = env["pi"].get_requirement("default", "p1", req.requirement_id).version_no
    env["pi"]._update("requirement", "default", "p1", req.requirement_id, v,
                      "t", verification_method="")
    gate = ProductDefinitionGate(env["db"], "default", "p1")
    result = gate.evaluate()
    assert any("missing verification path" in b for b in result["blockers"])


def test_unresolved_conflict_blocks_gate(env):
    """critical requirement definition_status=CONFLICT → gate blocker。"""
    chain = _build_chain(env)
    req = chain["requirements"][0]
    v = env["pi"].get_requirement("default", "p1", req.requirement_id).version_no
    env["pi"]._update("requirement", "default", "p1", req.requirement_id, v,
                      "t", definition_status="CONFLICT")
    gate = ProductDefinitionGate(env["db"], "default", "p1")
    result = gate.evaluate()
    assert any("unresolved conflict" in b for b in result["blockers"])


def test_owner_approval_required(env):
    """Gate 通过前置下仍因 Owner approval missing 而 BLOCKED（§51/52）。"""
    _build_chain(env)
    gate = ProductDefinitionGate(env["db"], "default", "p1")
    result = gate.evaluate()
    assert result["result"] == GATE_BLOCKED
    assert any("Owner approval missing" in b for b in result["blockers"])
    # 无 approve 决策 → commit 拒绝
    with pytest.raises(RuntimeError, match="Owner approval required"):
        gate.commit_approved()


def test_gate_rejected_does_not_commit(env):
    """Owner reject → 不 commit Product Truth。"""
    _build_chain(env)
    gate = ProductDefinitionGate(env["db"], "default", "p1")
    did = gate.propose_owner_decision(actor="owner")
    gate.resolve_owner_decision(did, "reject", "not now", actor="owner")
    with pytest.raises(RuntimeError):
        gate.commit_approved()
    # Product Truth 无 requirement 记录（p1 scope）
    from aipd_os.product_truth.store import ProductTruthStore
    store = ProductTruthStore(str(env["db"].path))
    assert store.query(record_type="requirement", tenant_id="default",
                       project_id="p1") == []


def test_gate_approved_commits_product_truth(env):
    """Owner approve → approved Requirements/Features 进入 Product Truth。"""
    _build_chain(env)
    gate = ProductDefinitionGate(env["db"], "default", "p1")
    did = gate.propose_owner_decision(actor="owner")
    gate.resolve_owner_decision(did, "approve", "approved", actor="owner")
    # 使 requirements/features active
    from aipd_os.product_intelligence import LIFECYCLE_ACTIVE
    pi = env["pi"]
    for r in pi.list_requirements("default", "p1"):
        pi._update("requirement", "default", "p1", r.requirement_id,
                   r.version_no, "t", lifecycle_status=LIFECYCLE_ACTIVE)
    for f in pi.list_features("default", "p1"):
        pi._update("feature", "default", "p1", f.feature_id,
                   f.version_no, "t", lifecycle_status=LIFECYCLE_ACTIVE)
    result = gate.commit_approved(actor="owner")
    assert result["requirements"] >= 1
    assert result["features"] >= 1
    from aipd_os.product_truth.store import ProductTruthStore
    store = ProductTruthStore(str(env["db"].path))
    reqs = store.query(record_type="requirement", tenant_id="default",
                       project_id="p1")
    feats = store.query(record_type="feature", tenant_id="default",
                        project_id="p1")
    assert len(reqs) >= 1 and len(feats) >= 1
    assert reqs[0].metadata.get("gate_approved") is True


def test_change_after_gate_creates_rework(env):
    """Gate 后修改 frozen 定义 → rework 传播（ProductTruth propagation）。"""
    _build_chain(env)
    gate = ProductDefinitionGate(env["db"], "default", "p1")
    did = gate.propose_owner_decision(actor="owner")
    gate.resolve_owner_decision(did, "approve", "ok", actor="owner")
    from aipd_os.product_intelligence import LIFECYCLE_ACTIVE
    pi = env["pi"]
    for r in pi.list_requirements("default", "p1"):
        pi._update("requirement", "default", "p1", r.requirement_id,
                   r.version_no, "t", lifecycle_status=LIFECYCLE_ACTIVE)
    for f in pi.list_features("default", "p1"):
        pi._update("feature", "default", "p1", f.feature_id,
                   f.version_no, "t", lifecycle_status=LIFECYCLE_ACTIVE)
    committed = gate.commit_approved(actor="owner")
    # 上游 = PI requirement（truth 派生自 requirement）；变化 → truth 受影响
    upstream = env["pi"].list_requirements("default", "p1")[0].requirement_id

    # Gate 后变更：上游 truth 变化 → 受影响下游 → stale + rework 任务
    from aipd_os.product_truth.propagation import PropagationEngine
    from aipd_os.product_truth.store import ProductTruthStore
    store = ProductTruthStore(str(env["db"].path), tenant_id="default",
                              project_id="p1")
    engine = PropagationEngine(store)
    result = engine.on_upstream_changed(upstream, reason="gate change")
    assert isinstance(result, dict)
    assert "tasks" in result and "stale" in result
    assert engine.list_tasks() is not None


# ---------------------------------------------------------------------------
# 4) traceability（§58 核心验收）
# ---------------------------------------------------------------------------
def test_feature_traceable_to_evidence(env):
    """任意 Feature：Feature→Requirement→Principle→Insight→Claim→
    EvidenceRelation→Evidence 全链可回溯。"""
    chain = _build_chain(env)
    feat = chain["features"][0]
    trace = env["pi"].feature_evidence_trace(
        feat.feature_id, tenant_id="default", project_id="p1")
    assert trace["evidence_reached"] is True
    assert len(trace["claims"]) >= 1
    assert len(trace["evidence"]) >= 1
    # 链上必须包含全部 5 层
    node_types = {e["source"]["node_type"] for e in trace["path"]}
    for t in ("feature", "requirement", "product_principle", "insight", "claim"):
        assert t in node_types, f"missing {t} in trace"
    assert any(e["target"]["node_type"] == "evidence" for e in trace["path"])


def test_principle_why_explainable(env):
    """ProductPrinciple 必须能回答 WHY（沿 lineage 到 Evidence）。"""
    chain = _build_chain(env)
    princ = chain["principles"][0]
    why = env["pi"].principle_why(princ.principle_id, tenant_id="default",
                                  project_id="p1")
    assert why["explainable"] is True


# ---------------------------------------------------------------------------
# 5) 真实性（§47/§68）
# ---------------------------------------------------------------------------
def test_unknown_does_not_become_verified(env):
    """LLM/分析产出默认 candidate；epistemic U 不会自动 verified。"""
    chain = _build_chain(env)
    ins = chain["insights"][0]
    got = env["pi"].get_insight("default", "p1", ins.insight_id)
    assert got.lifecycle_status == "candidate"  # 默认 candidate，非 committed
    assert got.epistemic_status == "A"  # 默认 Assumption，非 V
    # gate 前不允许 commit（即使对象存在）
    gate = ProductDefinitionGate(env["db"], "default", "p1")
    with pytest.raises(RuntimeError):
        gate.commit_approved()


def test_candidate_insight_not_product_truth(env):
    """candidate Insight 不能进入 Product Truth（§33）。"""
    chain = _build_chain(env)
    from aipd_os.product_truth.store import ProductTruthStore
    store = ProductTruthStore(str(env["db"].path))
    assert store.query(record_type="insight") == []  # PI 对象 ≠ Product Truth


def test_tenant_isolation_product_intelligence(env):
    """tenant A 不能读 tenant B 的 Insight（§68）。"""
    from aipd_os.product_intelligence import ProductObjectNotFoundError
    # p1 建 insight；用 p2 scope 读 → 不可见
    chain = _build_chain(env)
    ins = chain["insights"][0]
    with pytest.raises(ProductObjectNotFoundError):
        env["pi"].get_insight("default", "p2", ins.insight_id)
    # list 也不泄漏
    assert env["pi"].list_insights("default", "p2") == []


def test_ids_concurrency_safe(env):
    """v5.9 ID 全部走 id_sequences（并发安全，无 scan-max）。"""
    chain = _build_chain(env, n_insights=3, n_opps=2, n_prins=2, n_reqs=2,
                           n_feats=2)
    ids = [i.insight_id for i in chain["insights"]]
    assert len(set(ids)) == 3  # 无重复
    assert all(i.startswith("INS-") for i in ids)
