"""IdeaMaturityPolicy 测试（v5.8.2 Commit 6）。

提示词 §14-15：
- I2 必须区分「已有 key claims 都被调查」与「必要 key claim categories 都存在」；
- key claims 不硬编码死 —— 显式/可测/版本化 policy object；
- 只有 problem/user 都 reviewed、缺 mechanism/technology → I1+Evidence Gap。
"""
from __future__ import annotations

import pytest

from aipd_os.idea.claim_service import ClaimService
from aipd_os.idea.claims import Claim
from aipd_os.idea.evidence_graph import EvidenceGraph
from aipd_os.idea.evidence_relations import (
    EvidenceRelation,
    EvidenceRelationService,
)
from aipd_os.idea.maturity import IdeaMaturity, IdeaMaturityPolicy
from aipd_os.idea.models import Idea
from aipd_os.idea.service import IdeaService
from aipd_os.state.db import AIPDStateDB


@pytest.fixture
def env(tmp_path):
    db = AIPDStateDB(str(tmp_path / "state.db"))
    db.ensure_default_tenant("default")
    db.init_project("default", "P1", "P1", "goal")
    return {"db": db, "graph": EvidenceGraph(db)}


def _idea_with_claims(db, claim_types):
    idea = IdeaService(db).create(
        Idea(idea_id="", tenant_id="default", project_id="P1",
             title="I", raw_input="r"))
    claims = []
    for t in claim_types:
        claims.append(ClaimService(db).create(
            Claim(claim_id="", tenant_id="default", project_id="P1",
                  idea_id=idea.idea_id, claim_type=t,
                  statement=f"claim-{t}", epistemic_status="A")))
    return idea, claims


def _reviewed_supports(db, claim):
    svc = EvidenceRelationService(db)
    ev = db.add_evidence("default", "P1", kind="paper", title="t",
                         url="https://example.invalid/t")
    rel = svc.add(EvidenceRelation(relation_id="", tenant_id="default",
                                   project_id="P1", claim_id=claim.claim_id,
                                   evidence_id=ev, relation_type="supports"))
    svc.review("default", "P1", rel.relation_id, "reviewed")


def test_policy_is_versioned_and_explicit():
    """policy 显式/可测/版本化（不把 key claims 硬编码进 maturity 逻辑）。"""
    p = IdeaMaturityPolicy()
    assert p.policy_id == "idea_maturity_policy_v1"
    assert p.required_claim_types == {"problem", "user", "mechanism", "technology"}


def test_default_policy_is_module_contract():
    """KEY_CLAIM_TYPES 兼容常量 = policy.required_claim_types（不重复定义）。"""
    from aipd_os.idea.maturity import KEY_CLAIM_TYPES
    assert IdeaMaturityPolicy().required_claim_types == KEY_CLAIM_TYPES


def test_required_missing_reports_missing_categories(env):
    db = env["db"]
    graph = env["graph"]
    idea, _ = _idea_with_claims(db, ["problem", "user"])
    p = IdeaMaturityPolicy()
    missing = p.required_missing(idea, graph)
    assert missing == ["mechanism", "technology"]


def test_partial_coverage_does_not_reach_i2(env):
    """只有 problem/user 被调查（缺 mechanism/technology）→ I1 + Evidence Gap。"""
    db = env["db"]
    graph = env["graph"]
    idea, claims = _idea_with_claims(db, ["problem", "user"])
    for cl in claims:
        _reviewed_supports(db, cl)
    # 所有已有 claims 都 reviewed —— 但类别不齐全 → 不能 I2
    assert IdeaMaturity.evaluate(idea, graph) == IdeaMaturity.I1_STRUCTURED_IDEA
    reasons = IdeaMaturity.gap_reasons(idea, graph)
    assert any("missing required key claim types" in r for r in reasons)
    assert any("mechanism" in r and "technology" in r for r in reasons)


def test_full_coverage_reaches_i2(env):
    db = env["db"]
    graph = env["graph"]
    idea, claims = _idea_with_claims(
        db, ["problem", "user", "mechanism", "technology"])
    for cl in claims:
        _reviewed_supports(db, cl)
    assert IdeaMaturity.evaluate(idea, graph) == IdeaMaturity.I2_EVIDENCE_BACKED_IDEA
    assert IdeaMaturity.gap_reasons(idea, graph) == []


def test_assessment_not_searched_blocks_i2(env):
    """required claim 存在但未检索/评审（NOT_SEARCHED）→ I1。"""
    db = env["db"]
    graph = env["graph"]
    idea, claims = _idea_with_claims(
        db, ["problem", "user", "mechanism", "technology"])
    for cl in claims[:3]:
        _reviewed_supports(db, cl)
    # technology 无 reviewed relation → NOT_SEARCHED → I1
    assert IdeaMaturity.evaluate(idea, graph) == IdeaMaturity.I1_STRUCTURED_IDEA
    reasons = IdeaMaturity.gap_reasons(idea, graph)
    assert any("not searched/assessed" in r for r in reasons)


def test_policy_is_injectable(env):
    """自定义 policy 可注入（未来按 project type/domain/risk 升级）。"""
    db = env["db"]
    graph = env["graph"]
    idea, claims = _idea_with_claims(db, ["problem", "user"])
    for cl in claims:
        _reviewed_supports(db, cl)

    class MinimalPolicy(IdeaMaturityPolicy):
        policy_id = "idea_maturity_policy_test_v1"
        required_claim_types = frozenset({"problem", "user"})

    assert MinimalPolicy().required_missing(idea, graph) == []
    assert IdeaMaturity.evaluate(idea, graph, policy=MinimalPolicy()) \
        == IdeaMaturity.I2_EVIDENCE_BACKED_IDEA
    # 默认 policy 仍是 I1（不受注入影响）
    assert IdeaMaturity.evaluate(idea, graph) == IdeaMaturity.I1_STRUCTURED_IDEA


def test_gap_reasons_i0_no_claims(env):
    db = env["db"]
    graph = env["graph"]
    idea = IdeaService(db).create(
        Idea(idea_id="", tenant_id="default", project_id="P1",
             title="empty", raw_input="r"))
    assert IdeaMaturity.evaluate(idea, graph) == IdeaMaturity.I0_RAW_IDEA
    assert IdeaMaturity.gap_reasons(idea, graph) == \
        ["no claims (I0: idea not structured)"]
