"""EvidenceRelation ↔ Lineage review semantics（v5.8.2 Commit 5）。

锁定正式规则（提示词 §12-13）：
- pending EvidenceRelation **不得**建立 supported_by / contradicted_by 语义边；
- 只有 ``reviewed`` + supports/partially_supports → supported_by；
- 只有 ``reviewed`` + contradicts → contradicted_by；
- partially_supports 使用正式 relation type（不偷偷等同 supports）；
- inconclusive 不得支持 Claim Truth（不建边）；
- rejected 不得留下旧 semantic edge（retire，非物理删除，audit 留痕）；
- review → 事务化 lineage 更新（reviewed 建边 / rejected retire /
  类型变化 retire+重建），历史保留在 dependencies 行 + audit_log。
"""
from __future__ import annotations

from aipd_os.idea.evidence_relations import (
    EvidenceRelation,
    EvidenceRelationService,
)
from aipd_os.state.db import AIPDStateDB
from aipd_os.state.lineage import LineageNodeRef, LineageService


def _setup(tmp_path):
    db = AIPDStateDB(str(tmp_path / "state.db"))
    db.ensure_default_tenant()
    db.init_project("default", "p1", "proj", "goal")
    db.init_project("default", "p2", "proj2", "goal2")
    # claim + evidence（同 scope）
    from aipd_os.idea.claim_service import ClaimService
    from aipd_os.idea.claims import Claim
    cs = ClaimService(db)
    claim = cs.create(Claim(claim_id="", tenant_id="default", project_id="p1",
                            claim_type="problem", statement="s",
                            epistemic_status="A"), actor="t")
    eid = db.add_evidence("default", "p1", "paper", "title", url="https://x")
    eid2 = db.add_evidence("default", "p1", "paper", "title2", url="https://y")
    # 跨 project evidence
    eid_p2 = db.add_evidence("default", "p2", "paper", "other", url="https://z")
    return db, cs, claim, eid, eid2, eid_p2


def _claim_node(claim, project="p1"):
    return LineageNodeRef(node_type="claim", node_id=claim.claim_id,
                          tenant_id="default", project_id=project)


def _ev_node(eid, project="p1"):
    return LineageNodeRef(node_type="evidence", node_id=eid,
                          tenant_id="default", project_id=project)


def _semantic_edges(db, claim, eid, project="p1"):
    lineage = LineageService(db)
    return [e for e in lineage.outgoing(_claim_node(claim, project))
            if e.target.node_type == "evidence"
            and e.target.node_id == eid
            and e.relation_type in ("supported_by", "contradicted_by")]


# ---------------------------------------------------------------------------
def test_pending_relation_does_not_write_semantic_lineage(tmp_path):
    """R-08 核心：pending supports 不得建立 supported_by 边。"""
    db, _, claim, eid, _, _ = _setup(tmp_path)
    svc = EvidenceRelationService(db)
    rel = EvidenceRelation(relation_id="", tenant_id="default", project_id="p1",
                           claim_id=claim.claim_id, evidence_id=eid,
                           relation_type="supports", review_status="pending")
    svc.add(rel, actor="t")
    assert _semantic_edges(db, claim, eid) == []


def test_pending_contradicts_does_not_write_semantic_lineage(tmp_path):
    db, _, claim, eid, _, _ = _setup(tmp_path)
    svc = EvidenceRelationService(db)
    rel = EvidenceRelation(relation_id="", tenant_id="default", project_id="p1",
                           claim_id=claim.claim_id, evidence_id=eid,
                           relation_type="contradicts", review_status="pending")
    svc.add(rel, actor="t")
    assert _semantic_edges(db, claim, eid) == []


def test_add_reviewed_supports_creates_supported_by(tmp_path):
    db, _, claim, eid, _, _ = _setup(tmp_path)
    svc = EvidenceRelationService(db)
    rel = EvidenceRelation(relation_id="", tenant_id="default", project_id="p1",
                           claim_id=claim.claim_id, evidence_id=eid,
                           relation_type="supports", review_status="reviewed")
    created = svc.add(rel, actor="t")
    edges = _semantic_edges(db, claim, eid)
    assert len(edges) == 1
    assert edges[0].relation_type == "supported_by"
    assert edges[0].provenance.get("relation_id") == created.relation_id


def test_review_pending_to_reviewed_creates_edge(tmp_path):
    """R-09：review → reviewed + supports → add supported_by。"""
    db, _, claim, eid, _, _ = _setup(tmp_path)
    svc = EvidenceRelationService(db)
    rel = svc.add(EvidenceRelation(
        relation_id="", tenant_id="default", project_id="p1",
        claim_id=claim.claim_id, evidence_id=eid,
        relation_type="supports", review_status="pending"), actor="t")
    assert _semantic_edges(db, claim, eid) == []
    svc.review("default", "p1", rel.relation_id, "reviewed", actor="t")
    edges = _semantic_edges(db, claim, eid)
    assert len(edges) == 1 and edges[0].relation_type == "supported_by"


def test_reject_retires_existing_semantic_edge(tmp_path):
    """R-09：rejected 不得留下旧 semantic edge（retire 而非删除）。"""
    db, _, claim, eid, _, _ = _setup(tmp_path)
    svc = EvidenceRelationService(db)
    rel = svc.add(EvidenceRelation(
        relation_id="", tenant_id="default", project_id="p1",
        claim_id=claim.claim_id, evidence_id=eid,
        relation_type="supports", review_status="reviewed"), actor="t")
    assert len(_semantic_edges(db, claim, eid)) == 1
    svc.review("default", "p1", rel.relation_id, "rejected", actor="t")
    # active 查询不可见
    assert _semantic_edges(db, claim, eid) == []
    # 历史保留：retired 行 + audit
    lineage = LineageService(db)
    retired = [e for e in lineage.outgoing(_claim_node(claim),
                                           include_retired=True)
               if e.retired and e.relation_type == "supported_by"]
    assert len(retired) == 1
    audit_actions = [a["action"] for a in db.list_audit(limit=50)]
    assert "lineage.retire_edge" in audit_actions


def test_rejected_relation_has_no_semantic_edge_even_if_type_supports(tmp_path):
    db, _, claim, eid, _, _ = _setup(tmp_path)
    svc = EvidenceRelationService(db)
    rel = EvidenceRelation(relation_id="", tenant_id="default", project_id="p1",
                           claim_id=claim.claim_id, evidence_id=eid,
                           relation_type="supports", review_status="rejected")
    svc.add(rel, actor="t")
    assert _semantic_edges(db, claim, eid) == []


def test_relation_type_change_retires_and_rebuilds(tmp_path):
    """reviewed supports → contradicts：retire supported_by + create contradicted_by。"""
    db, _, claim, eid, _, _ = _setup(tmp_path)
    svc = EvidenceRelationService(db)
    rel = svc.add(EvidenceRelation(
        relation_id="", tenant_id="default", project_id="p1",
        claim_id=claim.claim_id, evidence_id=eid,
        relation_type="supports", review_status="reviewed"), actor="t")
    v2 = svc.get("default", "p1", rel.relation_id).version_no
    svc.update("default", "p1", rel.relation_id, expected_version=v2,
               relation_type="contradicts", actor="t")
    edges = _semantic_edges(db, claim, eid)
    assert len(edges) == 1 and edges[0].relation_type == "contradicted_by"
    # 旧 supported_by 已 retire（include_retired 可见）
    lineage = LineageService(db)
    all_edges = lineage.outgoing(_claim_node(claim), include_retired=True)
    retired_sup = [e for e in all_edges if e.retired
                   and e.relation_type == "supported_by"]
    assert len(retired_sup) == 1


def test_reviewed_inconclusive_creates_no_semantic_edge(tmp_path):
    """inconclusive 不得支持 Claim Truth（不建边）。"""
    db, _, claim, eid, _, _ = _setup(tmp_path)
    svc = EvidenceRelationService(db)
    svc.add(EvidenceRelation(
        relation_id="", tenant_id="default", project_id="p1",
        claim_id=claim.claim_id, evidence_id=eid,
        relation_type="inconclusive", review_status="reviewed"), actor="t")
    assert _semantic_edges(db, claim, eid) == []


def test_reject_then_review_rebuilds_edge(tmp_path):
    """rejected 后重新 reviewed：语义边重建（同键 retired 行让位）。"""
    db, _, claim, eid, _, _ = _setup(tmp_path)
    svc = EvidenceRelationService(db)
    rel = svc.add(EvidenceRelation(
        relation_id="", tenant_id="default", project_id="p1",
        claim_id=claim.claim_id, evidence_id=eid,
        relation_type="supports", review_status="reviewed"), actor="t")
    svc.review("default", "p1", rel.relation_id, "rejected", actor="t")
    assert _semantic_edges(db, claim, eid) == []
    v = svc.get("default", "p1", rel.relation_id).version_no
    svc.review("default", "p1", rel.relation_id, "reviewed",
               actor="t", expected_version=v)
    edges = _semantic_edges(db, claim, eid)
    assert len(edges) == 1 and edges[0].relation_type == "supported_by"


def test_partially_supports_uses_formal_relation_type(tmp_path):
    """partially_supports：正式 relation type（映射 supported_by，但保持类型）。"""
    db, _, claim, eid, _, _ = _setup(tmp_path)
    svc = EvidenceRelationService(db)
    rel = svc.add(EvidenceRelation(
        relation_id="", tenant_id="default", project_id="p1",
        claim_id=claim.claim_id, evidence_id=eid,
        relation_type="partially_supports", review_status="reviewed"), actor="t")
    assert rel.relation_type == "partially_supports"  # 不被静默改成 supports
    edges = _semantic_edges(db, claim, eid)
    assert len(edges) == 1 and edges[0].relation_type == "supported_by"
    assert edges[0].provenance.get("relation_type") == "partially_supports"


def test_review_does_not_touch_other_relation_edges(tmp_path):
    """一条 relation 的 review 不影响同 claim 的其他证据边。"""
    db, _, claim, eid, eid2, _ = _setup(tmp_path)
    svc = EvidenceRelationService(db)
    r1 = svc.add(EvidenceRelation(
        relation_id="", tenant_id="default", project_id="p1",
        claim_id=claim.claim_id, evidence_id=eid,
        relation_type="supports", review_status="reviewed"), actor="t")
    svc.add(EvidenceRelation(
        relation_id="", tenant_id="default", project_id="p1",
        claim_id=claim.claim_id, evidence_id=eid2,
        relation_type="supports", review_status="pending"), actor="t")
    svc.review("default", "p1", r1.relation_id, "rejected", actor="t")
    # eid2 pending 无边；eid 的边被 retire —— 无残留 active 边
    assert _semantic_edges(db, claim, eid) == []
    assert _semantic_edges(db, claim, eid2) == []


def test_mixed_supports_and_contradicts_coexist(tmp_path):
    """同一 (claim, evidence) 的 supports+contradicts 两条 relation 可并存
    （ClaimAssessment MIXED 是合法状态）——review 各自建边，互不误 retire。"""
    db, _, claim, eid, _, _ = _setup(tmp_path)
    svc = EvidenceRelationService(db)
    sup = svc.add(EvidenceRelation(
        relation_id="", tenant_id="default", project_id="p1",
        claim_id=claim.claim_id, evidence_id=eid,
        relation_type="supports", review_status="reviewed"), actor="t")
    con = svc.add(EvidenceRelation(
        relation_id="", tenant_id="default", project_id="p1",
        claim_id=claim.claim_id, evidence_id=eid,
        relation_type="contradicts", review_status="reviewed"), actor="t")
    edges = _semantic_edges(db, claim, eid)
    assert {e.relation_type for e in edges} == {"supported_by", "contradicted_by"}
    # 只 retire 其中一条 → 另一条边保留
    svc.review("default", "p1", con.relation_id, "rejected", actor="t")
    edges = _semantic_edges(db, claim, eid)
    assert {e.relation_type for e in edges} == {"supported_by"}
    assert sup.relation_id != con.relation_id
