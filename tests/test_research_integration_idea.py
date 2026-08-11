"""v5.8 Commit 13：Research Provider contract + ResearchIntegration 测试。

ResearchStudio 检查：**/Volumes/Extra/CodeProj/ 下不存在 researchstudio** ——
本轮验证 Provider contract 本身 + Fake provider 经 ExecutionRouter/AdapterRegistry
路由（不依赖具体 provider 名），诚实 external_dependency。

覆盖：
- 无 provider → external_blocked（诚实，不伪造 evidence）；
- Fake research provider → Claim 有 evidence + relation（supports/contradicts）
  → graph 查询反映；
- capability 路由经 ExecutionRouter + AdapterRegistry（capability 架构对齐）；
- 无结果 → 不写 evidence（诚实降级）。
"""
from __future__ import annotations

import pytest

from aipd_os.execution.execution_router import ExecutionRouter
from aipd_os.execution.registry import AdapterRegistry
from aipd_os.execution.runs import RunStore
from aipd_os.idea import (
    EVIDENCE_ASSESS_RELATION_CAPABILITY,
    RESEARCH_CAPABILITIES,
    Claim,
    ClaimService,
    EvidenceGraph,
    EvidenceRelationService,
    EvidenceRequest,
    Idea,
    IdeaService,
    ResearchCapabilityUnavailable,
    ResearchIntegration,
    ResearchToolAdapter,
    UnavailableResearchProvider,
    research_capability_declaration,
)
from aipd_os.state.db import AIPDStateDB
from tests.fixtures.idea.research_fixtures import (
    FAKE_CONTRADICT_RESULT_PER_SOURCE,
    FAKE_PER_SOURCE_RESULT,
    FAKE_SUPPORT_RESULT,
    FAKE_SUPPORT_RESULT_PER_SOURCE,
    EmptyFakeResearchProvider,
    FakeResearchProvider,
)


@pytest.fixture
def env(tmp_path):
    db = AIPDStateDB(str(tmp_path / "state.db"))
    db.ensure_default_tenant("default")
    db.init_project("default", "P1", "P1", "goal")
    db.init_project("default", "P2", "P2", "goal")

    ideas = IdeaService(db)
    idea = ideas.create(Idea(idea_id="", tenant_id="default", project_id="P1",
                             title="Idea 1", raw_input="raw",
                             lifecycle_status="structured"))
    claims = ClaimService(db)
    claim_sup = claims.create(Claim(claim_id="", tenant_id="default", project_id="P1",
                                    idea_id=idea.idea_id, claim_type="behavior",
                                    statement="视觉反馈可能改善动作完成",
                                    epistemic_status="A"))
    claim_con = claims.create(Claim(claim_id="", tenant_id="default", project_id="P1",
                                    idea_id=idea.idea_id, claim_type="mechanism",
                                    statement="AI 姿态估计可识别动作正确性",
                                    epistemic_status="A"))
    relations = EvidenceRelationService(db)
    graph = EvidenceGraph(db)
    return {"db": db, "idea": idea, "claims": (claim_sup, claim_con),
            "relations": relations, "graph": graph}


def _integration(env, registry=None, router=None):
    return ResearchIntegration(
        env["db"], env["relations"], env["graph"], router=router)


def _make_router(env, provider):
    store = RunStore(str(env["db"].path.parent / "exec.db"))
    reg = AdapterRegistry()
    reg.register(ResearchToolAdapter(provider))
    return ExecutionRouter(store, reg)


# ---------------------------------------------------------------------------
# 1) 无 provider / 无 router → external_blocked（诚实，不伪造 evidence）
# ---------------------------------------------------------------------------
def test_no_router_raises_unavailable(env):
    claim_sup, _ = env["claims"]
    integ = _integration(env)  # router=None
    with pytest.raises(ResearchCapabilityUnavailable):
        integ.link_evidence_for_claim(EvidenceRequest(
            claim_id=claim_sup.claim_id, tenant_id="default", project_id="P1",
            capability="research.academic_search"))
    assert env["relations"].list_for_claim("default", "P1", claim_sup.claim_id) == []


def test_capability_not_registered_raises_unavailable(env):
    claim_sup, _ = env["claims"]
    reg = AdapterRegistry()  # 无 research adapter
    store = RunStore(str(env["db"].path.parent / "exec2.db"))
    router = ExecutionRouter(store, reg)
    integ = _integration(env, router=router)
    with pytest.raises(ResearchCapabilityUnavailable):
        integ.link_evidence_for_claim(EvidenceRequest(
            claim_id=claim_sup.claim_id, tenant_id="default", project_id="P1",
            capability="research.academic_search"))


def test_unavailable_provider_adapter_honest(env):
    claim_sup, _ = env["claims"]
    provider = UnavailableResearchProvider("research.academic_search")
    router = _make_router(env, provider)
    integ = _integration(env, router=router)
    with pytest.raises(ResearchCapabilityUnavailable):
        integ.link_evidence_for_claim(EvidenceRequest(
            claim_id=claim_sup.claim_id, tenant_id="default", project_id="P1",
            capability="research.academic_search"))
    # 无 evidence 被写
    assert env["db"].list_evidence("default", "P1") == []


# ---------------------------------------------------------------------------
# 2) Fake provider → evidence + relation（per-source；Search ≠ Assessment）
# ---------------------------------------------------------------------------
def test_search_result_defaults_to_inconclusive(env):
    """Commit 5：检索到 sources 但无显式评估 → relation_type=inconclusive + pending。

    legacy FAKE_SUPPORT_RESULT 顶层声明 evidence_relation 不再被当作
    「检索→支持」的推理；source 无 per-source relation → 保守 inconclusive。
    """
    claim_sup, _ = env["claims"]
    provider = FakeResearchProvider(capability_id="research.academic_search",
                                    result=FAKE_SUPPORT_RESULT)
    router = _make_router(env, provider)
    integ = _integration(env, router=router)
    out = integ.link_evidence_for_claim(EvidenceRequest(
        claim_id=claim_sup.claim_id, tenant_id="default", project_id="P1",
        capability="research.academic_search",
        inputs={"query": "home-based rehab adherence"}), actor="alice")
    assert out["relation_type"] == "inconclusive"
    assert len(out["evidence_ids"]) == 1
    assert out["relations"][0]["review_status"] == "pending"
    assert out["relations"][0]["relation_type"] == "inconclusive"
    # 未评审：语义 getter 不返回
    assert env["graph"].get_supporting_evidence(
        "default", "P1", claim_sup.claim_id) == []
    # 评审后进入 inconclusive 视图
    env["relations"].review("default", "P1",
                            out["relations"][0]["relation_id"], "reviewed")
    rels = env["graph"].get_inconclusive_evidence("default", "P1", claim_sup.claim_id)
    assert [r.evidence_id for r in rels] == out["evidence_ids"]
    assert provider.execute_count == 1
    # 证据真实存在于 canonical evidence 表
    evs = env["db"].list_evidence("default", "P1")
    assert len(evs) == 1
    # audit
    actions = [r["action"] for r in env["db"].list_audit(limit=100)]
    assert "evidence_relation.add" in actions
    assert "evidence_relation.review" in actions


def test_fake_provider_supports_relation_per_source(env):
    """per-source contract：source.relation.type=supports → supports（仍 pending）。"""
    claim_sup, _ = env["claims"]
    provider = FakeResearchProvider(capability_id="research.academic_search",
                                    result=FAKE_SUPPORT_RESULT_PER_SOURCE)
    router = _make_router(env, provider)
    integ = _integration(env, router=router)
    out = integ.link_evidence_for_claim(EvidenceRequest(
        claim_id=claim_sup.claim_id, tenant_id="default", project_id="P1",
        capability="research.academic_search",
        inputs={"query": "home-based rehab adherence"}), actor="alice")
    assert out["relation_type"] == "supports"
    assert out["relations"][0]["review_status"] == "pending"  # 显式评估后 review
    assert len(out["evidence_ids"]) == 1
    # 评审后进入支持视图
    env["relations"].review("default", "P1",
                            out["relations"][0]["relation_id"], "reviewed")
    rels = env["graph"].get_supporting_evidence("default", "P1", claim_sup.claim_id)
    assert [r.evidence_id for r in rels] == out["evidence_ids"]


def test_fake_provider_contradicts_relation(env):
    _, claim_con = env["claims"]
    provider = FakeResearchProvider(capability_id="research.academic_search",
                                    result=FAKE_CONTRADICT_RESULT_PER_SOURCE)
    router = _make_router(env, provider)
    integ = _integration(env, router=router)
    out = integ.link_evidence_for_claim(EvidenceRequest(
        claim_id=claim_con.claim_id, tenant_id="default", project_id="P1",
        capability="research.academic_search",
        inputs={"query": "pose estimation rehab accuracy"}))
    assert out["relation_type"] == "contradicts"
    assert out["relations"][0]["review_status"] == "pending"
    # 评审后 contradicts 进入语义视图
    env["relations"].review("default", "P1",
                            out["relations"][0]["relation_id"], "reviewed")
    rels = env["graph"].get_contradicting_evidence("default", "P1", claim_con.claim_id)
    assert len(rels) == 1


def test_each_source_can_have_different_relation(env):
    """Paper A supports / Paper B contradicts / Paper C irrelevant → 三条独立 relation。"""
    claim_sup, _ = env["claims"]
    provider = FakeResearchProvider(capability_id="research.academic_search",
                                    result=FAKE_PER_SOURCE_RESULT)
    router = _make_router(env, provider)
    integ = _integration(env, router=router)
    out = integ.link_evidence_for_claim(EvidenceRequest(
        claim_id=claim_sup.claim_id, tenant_id="default", project_id="P1",
        capability="research.academic_search", inputs={"query": "q"}), actor="alice")
    assert len(out["evidence_ids"]) == 3
    assert out["relation_type"] == "mixed"  # 三种不同类型
    by_id = {r["evidence_id"]: r for r in out["relations"]}
    assert {by_id[eid]["relation_type"] for eid in out["evidence_ids"]} == \
        {"supports", "contradicts", "inconclusive"}
    # 三条 relation 各自独立（evidence_id 不同）
    assert len({r["relation_id"] for r in out["relations"]}) == 3
    # Paper C（无 relation）→ inconclusive + pending
    rel_c = next(r for r in out["relations"] if r["relation_type"] == "inconclusive")
    assert rel_c["review_status"] == "pending"


# ---------------------------------------------------------------------------
# 3) capability 路由经 ExecutionRouter + AdapterRegistry（不依赖 provider 名）
# ---------------------------------------------------------------------------
def test_capability_routed_by_id_not_provider_name(env):
    claim_sup, _ = env["claims"]
    provider = FakeResearchProvider(capability_id="research.related_work",
                                    result=FAKE_SUPPORT_RESULT)
    router = _make_router(env, provider)
    integ = _integration(env, router=router)
    out = integ.link_evidence_for_claim(EvidenceRequest(
        claim_id=claim_sup.claim_id, tenant_id="default", project_id="P1",
        capability="research.related_work", inputs={"topic": "rehab"}))
    # legacy fixture（无 per-source relation）→ 保守 inconclusive
    assert out["relation_type"] == "inconclusive"
    # capability 声明（ProviderRegistry schema 兼容）
    decl = research_capability_declaration("research.related_work")
    assert decl["id"] == "research.related_work"
    assert decl["domain"] == "research"
    assert RESEARCH_CAPABILITIES  # 能力注册骨架非空


# ---------------------------------------------------------------------------
# 3b) Commit 5：Search ≠ Assessment 拆层
# ---------------------------------------------------------------------------
def test_assess_relation_capability_declared(env):
    """evidence.assess_relation 是独立 capability（Search 不承担评估）。"""
    assert EVIDENCE_ASSESS_RELATION_CAPABILITY == "evidence.assess_relation"
    assert EVIDENCE_ASSESS_RELATION_CAPABILITY in RESEARCH_CAPABILITIES
    # Search provider 的 assess_relation 诚实不可用（external_dependency）
    claim_sup, _ = env["claims"]
    provider = FakeResearchProvider(capability_id="research.academic_search",
                                    result=FAKE_SUPPORT_RESULT_PER_SOURCE)
    with pytest.raises(ResearchCapabilityUnavailable, match="assess_relation"):
        provider.assess_relation({"claim_id": claim_sup.claim_id})
    # UnavailableResearchProvider 同样诚实
    up = UnavailableResearchProvider("research.academic_search")
    with pytest.raises(ResearchCapabilityUnavailable):
        up.assess_relation({"claim_id": claim_sup.claim_id})


# ---------------------------------------------------------------------------
# 4) 无结果 → 不写 evidence（诚实降级）
# ---------------------------------------------------------------------------
def test_empty_result_writes_no_evidence(env):
    claim_sup, _ = env["claims"]
    provider = EmptyFakeResearchProvider(capability_id="research.academic_search")
    router = _make_router(env, provider)
    integ = _integration(env, router=router)
    with pytest.raises(ResearchCapabilityUnavailable):
        integ.link_evidence_for_claim(EvidenceRequest(
            claim_id=claim_sup.claim_id, tenant_id="default", project_id="P1",
            capability="research.academic_search",
            inputs={"query": "no results query"}))
    assert env["db"].list_evidence("default", "P1") == []
    assert env["relations"].list_for_claim("default", "P1", claim_sup.claim_id) == []


# ---------------------------------------------------------------------------
# 5) evidence gaps 驱动
# ---------------------------------------------------------------------------
def test_evidence_gaps_drives_requests(env):
    claim_sup, claim_con = env["claims"]
    integ = _integration(env)
    gaps = integ.evidence_gaps("default", "P1")
    assert {c.claim_id for c in gaps} == {claim_sup.claim_id, claim_con.claim_id}
