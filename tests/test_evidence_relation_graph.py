"""v5.8 Commit 11：EvidenceRelation + Evidence Graph 测试。

覆盖：
- link claim↔evidence（supports/contradicts/partially_supports/inconclusive/
  not_applicable 五种关系）；
- cross-project evidence link → 拒绝（project A 不能 link project B 的 evidence）；
- cross-tenant link → 拒绝；
- graph 查询各 API 正确 + project scoped；
- get_evidence_gaps 正确识别无证据 claim；
- 复用现有 AIPDStateDB.add_evidence 创建真实 evidence 后 link（证明复用
  canonical evidence 表，不建第二 truth source）。
"""
from __future__ import annotations

import pytest

from aipd_os.idea import (
    Claim,
    ClaimService,
    EvidenceGraph,
    EvidenceRelation,
    EvidenceRelationScopeError,
    EvidenceRelationService,
    Idea,
    IdeaService,
)
from aipd_os.state.db import AIPDStateDB


@pytest.fixture
def env(tmp_path):
    db = AIPDStateDB(str(tmp_path / "state.db"))
    db.ensure_default_tenant("default")
    db.init_project("default", "P1", "P1", "goal")
    db.init_project("default", "P2", "P2", "goal")
    db.ensure_default_tenant("tenantB")
    db.init_project("tenantB", "PB", "PB", "goal")

    ideas = IdeaService(db)
    idea = ideas.create(Idea(idea_id="", tenant_id="default", project_id="P1",
                             title="Idea 1", raw_input="raw"))
    claims = ClaimService(db)
    claim_a = claims.create(Claim(claim_id="", tenant_id="default", project_id="P1",
                                  idea_id=idea.idea_id, claim_type="problem",
                                  statement="老年人希望独立行走更久", epistemic_status="A"))
    claim_b = claims.create(Claim(claim_id="", tenant_id="default", project_id="P1",
                                  idea_id=idea.idea_id, claim_type="behavior",
                                  statement="每天行走 30 分钟", epistemic_status="A"))
    relations = EvidenceRelationService(db)
    graph = EvidenceGraph(db)
    return {"db": db, "idea": idea, "claims": (claim_a, claim_b),
            "relations": relations, "graph": graph}


def _evidence(db, tenant="default", project="P1", kind="paper", title="paper-1"):
    return db.add_evidence(tenant, project, kind=kind, title=title,
                           url=f"https://example.invalid/{title}")


def _rel(claim, evidence, rtype="supports", **kw):
    return EvidenceRelation(relation_id="", tenant_id="default", project_id="P1",
                            claim_id=claim.claim_id, evidence_id=evidence,
                            relation_type=rtype, **kw)


# ---------------------------------------------------------------------------
# 1) link claim↔evidence（五种关系）
# ---------------------------------------------------------------------------
def test_link_all_relation_types(env):
    db = env["db"]
    claim_a, _ = env["claims"]
    relations = env["relations"]
    ev = _evidence(db, title="ev-1")

    created = []
    for rtype in ("supports", "contradicts", "partially_supports",
                  "inconclusive", "not_applicable"):
        rel = relations.add(_rel(claim_a, ev, rtype), actor="alice")
        assert rel.relation_id.startswith("REL-")
        assert rel.relation_type == rtype
        created.append(rel.relation_id)

    got = relations.list_for_claim("default", "P1", claim_a.claim_id)
    assert {r.relation_type for r in got} == {
        "supports", "contradicts", "partially_supports", "inconclusive", "not_applicable"}
    # audit
    actions = [r["action"] for r in db.list_audit(limit=100)]
    assert "evidence_relation.add" in actions


# ---------------------------------------------------------------------------
# 2) cross-project / cross-tenant evidence link → 拒绝
# ---------------------------------------------------------------------------
def test_cross_project_evidence_link_rejected(env):
    db = env["db"]
    claim_a, _ = env["claims"]
    relations = env["relations"]
    # P2 的 evidence
    ev_p2 = _evidence(db, project="P2", title="ev-p2")
    with pytest.raises(EvidenceRelationScopeError, match="cross-scope"):
        relations.add(_rel(claim_a, ev_p2, "supports"))


def test_cross_tenant_evidence_link_rejected(env):
    db = env["db"]
    claim_a, _ = env["claims"]
    relations = env["relations"]
    ev_tb = _evidence(db, tenant="tenantB", project="PB", title="ev-tb")
    with pytest.raises(EvidenceRelationScopeError, match="cross-scope"):
        relations.add(_rel(claim_a, ev_tb, "supports"))


def test_cross_project_claim_rejected(env):
    db = env["db"]
    claims = env["claims"]
    claim_a, _ = claims
    relations = env["relations"]
    ev = _evidence(db, title="ev-1")
    # 用 P2 的 claim（通过查询得到 P2 下无 claim —— 直接用不存在 claim 触发 scope 拒绝）
    with pytest.raises(EvidenceRelationScopeError):
        relations.add(EvidenceRelation(relation_id="", tenant_id="default",
                                       project_id="P2",
                                       claim_id=claim_a.claim_id,
                                       evidence_id=ev, relation_type="supports"))


# ---------------------------------------------------------------------------
# 3) graph 查询 API
# ---------------------------------------------------------------------------
def test_graph_supporting_contradicting_inconclusive(env):
    db = env["db"]
    claim_a, _ = env["claims"]
    relations = env["relations"]
    graph = env["graph"]

    ev_sup = _evidence(db, title="ev-sup")
    ev_con = _evidence(db, title="ev-con")
    ev_inc = _evidence(db, title="ev-inc")
    relations.add(_rel(claim_a, ev_sup, "supports"))
    relations.add(_rel(claim_a, ev_con, "contradicts"))
    relations.add(_rel(claim_a, ev_inc, "inconclusive"))

    assert {r.evidence_id for r in graph.get_supporting_evidence(
        "default", "P1", claim_a.claim_id)} == {ev_sup}
    assert {r.evidence_id for r in graph.get_contradicting_evidence(
        "default", "P1", claim_a.claim_id)} == {ev_con}
    assert {r.evidence_id for r in graph.get_inconclusive_evidence(
        "default", "P1", claim_a.claim_id)} == {ev_inc}
    assert len(graph.get_claim_evidence("default", "P1", claim_a.claim_id)) == 3


def test_graph_project_scoped(env):
    db = env["db"]
    claim_a, _ = env["claims"]
    relations = env["relations"]
    graph = env["graph"]
    ev = _evidence(db, title="ev-scope")
    relations.add(_rel(claim_a, ev, "supports"))
    # 其他 project 查不到该 claim 的 relations
    assert graph.get_claim_evidence("default", "P2", claim_a.claim_id) == []
    with pytest.raises(Exception):
        graph.get_claim("default", "P2", claim_a.claim_id)


def test_graph_unknown_claims_and_evidence_gaps(env):
    claim_a, claim_b = env["claims"]
    db = env["db"]
    relations = env["relations"]
    graph = env["graph"]

    # 两个 claim 都默认 A（unknown）；claim_a 有证据，claim_b 无证据 → gap
    ev = _evidence(db, title="ev-gap")
    relations.add(_rel(claim_a, ev, "supports"))

    unknown = graph.get_unknown_claims("default", "P1")
    assert {c.claim_id for c in unknown} == {claim_a.claim_id, claim_b.claim_id}

    gaps = graph.get_evidence_gaps("default", "P1")
    assert [c.claim_id for c in gaps] == [claim_b.claim_id]

    summary = graph.get_idea_evidence_summary("default", "P1", env["idea"].idea_id)
    assert summary["total_claims"] == 2
    assert summary["supporting"] == 1
    assert summary["contradicting"] == 0
    assert summary["inconclusive"] == 0
    assert summary["unknown"] == 2
    assert summary["gaps"] == 1


def test_graph_not_applicable_counts_neither_support_nor_contradict(env):
    db = env["db"]
    claim_a, _ = env["claims"]
    relations = env["relations"]
    graph = env["graph"]
    ev = _evidence(db, title="ev-na")
    relations.add(_rel(claim_a, ev, "not_applicable"))
    summary = graph.get_idea_evidence_summary("default", "P1", env["idea"].idea_id)
    assert summary["supporting"] == 0
    assert summary["contradicting"] == 0
    # not_applicable 不算 gap（有关系存在）
    assert summary["gaps"] == 1  # 另一个 claim 无证据


def test_reuses_canonical_evidence_table(env):
    """复用现有 AIPDStateDB.add_evidence 创建的 evidence（不建第二 truth source）。"""
    db = env["db"]
    claim_a, _ = env["claims"]
    relations = env["relations"]
    graph = env["graph"]
    ev_id = db.add_evidence("default", "P1", kind="research", title="real-paper",
                            url="https://example.invalid/real-paper")
    # evidence 真实存在于 canonical evidence 表
    evs = db.list_evidence("default", "P1")
    assert any(e["evidence_id"] == ev_id for e in evs)
    # 可直接 link 并查询
    relations.add(_rel(claim_a, ev_id, "supports"))
    rels = graph.get_supporting_evidence("default", "P1", claim_a.claim_id)
    assert [r.evidence_id for r in rels] == [ev_id]
