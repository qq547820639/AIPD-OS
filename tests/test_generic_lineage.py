"""v5.8.1 Commit 9：Generic Lineage 测试。

覆盖：
- add_edge scope 校验（跨 tenant/project 拒绝）；
- outgoing / incoming 查询正确；
- path 查询（多跳 BFS 最短路径）；
- cycle detection（新增边成环拒绝）；
- relation_type 全集可用；
- supersedes 语义（新版本 supersedes 旧版本）；
- audit 记录；
- tenant/project 隔离；
- Idea 域自动接线（decompose → Idea→Claim derived_from；
  EvidenceRelation → Claim→Evidence supported_by/contradicted_by）。
"""
from __future__ import annotations

import pytest

from aipd_os.idea import (
    Claim,
    ClaimService,
    EvidenceRelation,
    EvidenceRelationService,
    Idea,
    IdeaDecomposer,
    IdeaDecompositionProvider,
    IdeaService,
    StructuredCandidate,
)
from aipd_os.state.db import AIPDStateDB
from aipd_os.state.lineage import (
    LINEAGE_RELATION_TYPES,
    LineageCycleError,
    LineageNodeRef,
    LineageRelationError,
    LineageScopeError,
    LineageService,
)


@pytest.fixture
def env(tmp_path):
    db = AIPDStateDB(str(tmp_path / "state.db"))
    db.ensure_default_tenant("default")
    db.init_project("default", "P1", "P1", "goal")
    db.init_project("default", "P2", "P2", "goal")
    db.ensure_default_tenant("tenantB")
    db.init_project("tenantB", "PB", "PB", "goal")
    return db


def _node(node_type, node_id, tenant="default", project="P1", version=None):
    return LineageNodeRef(node_type=node_type, node_id=node_id,
                          tenant_id=tenant, project_id=project, version=version)


# ---------------------------------------------------------------------------
# 1) add_edge + scope 校验
# ---------------------------------------------------------------------------
def test_add_edge_basic_and_scope_check(env):
    db = env
    ls = LineageService(db)
    idea = _node("idea", "IDEA-1")
    claim = _node("claim", "CLM-1")
    edge = ls.add_edge(idea, claim, "derived_from",
                       provenance={"source": "test"}, actor="alice")
    assert edge.edge_id
    assert edge.relation_type == "derived_from"
    assert edge.provenance == {"source": "test"}
    assert edge.created_at
    # 跨 project / 跨 tenant 拒绝
    with pytest.raises(LineageScopeError):
        ls.add_edge(_node("idea", "IDEA-1", project="P1"),
                    _node("claim", "CLM-1", project="P2"), "derived_from")
    with pytest.raises(LineageScopeError):
        ls.add_edge(_node("idea", "IDEA-1", tenant="default"),
                    _node("claim", "CLM-1", tenant="tenantB"), "derived_from")
    # 非法 relation_type 拒绝
    with pytest.raises(LineageRelationError):
        ls.add_edge(idea, claim, "bogus_relation")
    # 幂等：同边重复 add → 返回现有（不重复）
    again = ls.add_edge(idea, claim, "derived_from", actor="bob")
    assert again.edge_id == edge.edge_id


# ---------------------------------------------------------------------------
# 2) outgoing / incoming
# ---------------------------------------------------------------------------
def test_outgoing_incoming(env):
    db = env
    ls = LineageService(db)
    idea = _node("idea", "IDEA-1")
    c1 = _node("claim", "CLM-1")
    c2 = _node("claim", "CLM-2")
    ls.add_edge(idea, c1, "derived_from")
    ls.add_edge(idea, c2, "derived_from")
    assert len(ls.outgoing(idea)) == 2
    assert len(ls.incoming(c1)) == 1
    assert ls.incoming(c1)[0].source.node_id == "IDEA-1"
    # 反方向无边
    assert ls.outgoing(c1) == []


# ---------------------------------------------------------------------------
# 3) path 多跳
# ---------------------------------------------------------------------------
def test_path_multi_hop(env):
    db = env
    ls = LineageService(db)
    idea = _node("idea", "IDEA-1")
    claim = _node("claim", "CLM-1")
    ev = _node("evidence", "E-1")
    ls.add_edge(idea, claim, "derived_from")
    ls.add_edge(claim, ev, "supported_by")
    path = ls.path(idea, ev)
    assert path is not None
    assert len(path) == 2
    assert path[0].relation_type == "derived_from"
    assert path[1].relation_type == "supported_by"
    # 不存在路径
    assert ls.path(idea, _node("requirement", "REQ-1")) is None
    # 相同节点 → 空路径
    assert ls.path(idea, idea) == []


# ---------------------------------------------------------------------------
# 4) cycle detection
# ---------------------------------------------------------------------------
def test_cycle_detection(env):
    db = env
    ls = LineageService(db)
    a = _node("idea", "IDEA-1")
    b = _node("claim", "CLM-1")
    c = _node("evidence", "E-1")
    ls.add_edge(a, b, "derived_from")
    ls.add_edge(b, c, "supported_by")
    # b → a 会成环（a → b → c … 无 b→a，但 a→b 已存在，b→a 成环）
    with pytest.raises(LineageCycleError):
        ls.add_edge(b, a, "derived_from")
    # c → a 也会成环（a → b → c → a）
    with pytest.raises(LineageCycleError):
        ls.add_edge(c, a, "derived_from")
    # 合法反向（不闭环）
    ls.add_edge(c, _node("insight", "INS-1"), "validated_by")
    assert len(ls.outgoing(c)) == 1


# ---------------------------------------------------------------------------
# 5) relation_type 全集可用 + supersedes 语义
# ---------------------------------------------------------------------------
def test_all_relation_types_usable(env):
    db = env
    ls = LineageService(db)
    for i, rtype in enumerate(sorted(LINEAGE_RELATION_TYPES)):
        src = _node("idea", f"SRC-{i}")
        tgt = _node("claim", f"TGT-{i}")
        edge = ls.add_edge(src, tgt, rtype)
        assert edge.relation_type == rtype
    assert len(ls.edges("default", "P1")) == len(LINEAGE_RELATION_TYPES)


def test_supersedes_semantics(env):
    """新版本 supersedes 旧版本（version 字段承载版本信息）。"""
    db = env
    ls = LineageService(db)
    old = _node("requirement", "REQ-1", version="v1")
    new = _node("requirement", "REQ-1", version="v2")
    ls.add_edge(new, old, "supersedes",
                provenance={"reason": "revised scope"}, actor="alice")
    incoming_old = ls.incoming(old)
    assert len(incoming_old) == 1
    assert incoming_old[0].relation_type == "supersedes"
    assert incoming_old[0].source.node_id == "REQ-1"
    assert incoming_old[0].source.version == "v2"
    assert incoming_old[0].provenance == {"reason": "revised scope"}


# ---------------------------------------------------------------------------
# 6) audit + tenant/project 隔离
# ---------------------------------------------------------------------------
def test_lineage_audit_recorded(env):
    db = env
    ls = LineageService(db)
    ls.add_edge(_node("idea", "IDEA-1"), _node("claim", "CLM-1"),
                "derived_from", actor="alice")
    actions = [r["action"] for r in db.list_audit(limit=100)]
    assert "lineage.add_edge" in actions
    rec = next(r for r in db.list_audit(limit=100) if r["action"] == "lineage.add_edge")
    assert rec["actor"] == "alice"
    assert rec["tenant_id"] == "default" and rec["project_id"] == "P1"


def test_tenant_project_isolation(env):
    db = env
    ls = LineageService(db)
    ls.add_edge(_node("idea", "IDEA-1"), _node("claim", "CLM-1"), "derived_from")
    ls.add_edge(_node("idea", "IDEA-1", project="P2"),
                _node("claim", "CLM-1", project="P2"), "derived_from")
    ls.add_edge(_node("idea", "IDEA-1", tenant="tenantB", project="PB"),
                _node("claim", "CLM-1", tenant="tenantB", project="PB"),
                "derived_from")
    # 各 scope 只见自己的边
    assert len(ls.edges("default", "P1")) == 1
    assert len(ls.edges("default", "P2")) == 1
    assert len(ls.edges("tenantB", "PB")) == 1
    # 跨 scope 查询不存在的节点 → 空
    assert ls.outgoing(_node("idea", "IDEA-NOPE", project="P2")) == []
    assert ls.incoming(_node("claim", "CLM-NOPE", project="P2")) == []


# ---------------------------------------------------------------------------
# 7) Idea 域自动接线
# ---------------------------------------------------------------------------
class _FakeProvider(IdeaDecompositionProvider):
    name = "lineage-fake"

    def available(self) -> bool:
        return True

    def decompose(self, raw_input, idea_context=None):
        return StructuredCandidate.from_dict({
            "title": "T", "goal": "g", "problem": "p", "target_user": "u",
            "desired_outcome": "o", "constraints": ["c"],
            "claims": [
                {"claim_type": "problem", "statement": "s1"},
                {"claim_type": "user", "statement": "s2"},
            ],
            "source": "lineage-fake",
        })


def test_decompose_wires_idea_to_claim_edges(env):
    """decompose_existing → Idea→Claim derived_from 边自动建立。"""
    db = env
    svc = IdeaService(db)
    raw = svc.create(Idea(idea_id="", tenant_id="default", project_id="P1",
                          title="raw", raw_input="prompt", goal="prompt",
                          lifecycle_status="raw"), actor="alice")
    IdeaDecomposer(db, provider=_FakeProvider(), tenant_id="default",
                   project_id="P1").decompose_existing(raw.idea_id, actor="alice")
    ls = LineageService(db)
    idea_node = _node("idea", raw.idea_id)
    outgoing = ls.outgoing(idea_node)
    assert len(outgoing) == 2
    assert all(e.relation_type == "derived_from" for e in outgoing)
    assert {e.target.node_type for e in outgoing} == {"claim"}


def test_evidence_relation_wires_claim_to_evidence_edges(env):
    """EvidenceRelation 创建 → Claim→Evidence supported_by/contradicted_by 边。"""
    db = env
    idea = IdeaService(db).create(
        Idea(idea_id="", tenant_id="default", project_id="P1",
             title="I", raw_input="r"))
    claim = ClaimService(db).create(
        Claim(claim_id="", tenant_id="default", project_id="P1",
              idea_id=idea.idea_id, claim_type="problem",
              statement="s", epistemic_status="A"))
    ev_id = db.add_evidence("default", "P1", kind="paper", title="t",
                            url="https://example.invalid/t")
    rels = EvidenceRelationService(db)
    rels.add(EvidenceRelation(relation_id="", tenant_id="default", project_id="P1",
                              claim_id=claim.claim_id, evidence_id=ev_id,
                              relation_type="supports"), actor="alice")
    rels.add(EvidenceRelation(relation_id="", tenant_id="default", project_id="P1",
                              claim_id=claim.claim_id, evidence_id=ev_id,
                              relation_type="contradicts"), actor="alice")
    ls = LineageService(db)
    claim_node = _node("claim", claim.claim_id)
    edges = ls.outgoing(claim_node)
    assert {e.relation_type for e in edges} == {"supported_by", "contradicted_by"}
    assert all(e.target.node_type == "evidence" for e in edges)
