"""v5.8 Commit 14：Idea Truth projection + maturity（I0/I1/I2）测试。

覆盖：
- projection 正确列出 known/assumption/evidence/contradicted/unknown/gaps；
- snapshot 不可变（序列化后修改源不影响 snapshot）；
- maturity I0→I1→I2 判定正确（确定性）；
- 无 fake evidence（relation 必须有真实 evidence_id —— EvidenceRelationService
  已强制校验，测试断言 relation 的 evidence_id 真实存在于 evidence 表）；
- tenant/project scoped。
"""
from __future__ import annotations

import json

import pytest

from aipd_os.idea import (
    Claim,
    ClaimService,
    EvidenceGraph,
    EvidenceRelation,
    EvidenceRelationService,
    Idea,
    IdeaMaturity,
    IdeaService,
    IdeaTruthProjection,
    IdeaTruthSnapshot,
)
from aipd_os.state.db import AIPDStateDB


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
    claim_known = claims.create(Claim(claim_id="", tenant_id="default",
                                      project_id="P1", idea_id=idea.idea_id,
                                      claim_type="behavior",
                                      statement="视觉反馈改善动作完成",
                                      epistemic_status="A"))
    claim_contra = claims.create(Claim(claim_id="", tenant_id="default",
                                       project_id="P1", idea_id=idea.idea_id,
                                       claim_type="mechanism",
                                       statement="姿态估计可识别动作",
                                       epistemic_status="A"))
    claim_unknown = claims.create(Claim(claim_id="", tenant_id="default",
                                        project_id="P1", idea_id=idea.idea_id,
                                        claim_type="product",
                                        statement="离线推理可行",
                                        epistemic_status="U"))
    claim_gap = claims.create(Claim(claim_id="", tenant_id="default",
                                    project_id="P1", idea_id=idea.idea_id,
                                    claim_type="safety",
                                    statement="提示不应鼓励超范围动作",
                                    epistemic_status="A"))
    relations = EvidenceRelationService(db)
    graph = EvidenceGraph(db)

    # claim_known: supports；claim_contra: contradicts
    ev_sup = db.add_evidence("default", "P1", kind="paper", title="sup",
                             url="https://example.invalid/sup")
    ev_con = db.add_evidence("default", "P1", kind="paper", title="con",
                             url="https://example.invalid/con")
    relations.add(EvidenceRelation(relation_id="", tenant_id="default",
                                   project_id="P1", claim_id=claim_known.claim_id,
                                   evidence_id=ev_sup, relation_type="supports"))
    relations.add(EvidenceRelation(relation_id="", tenant_id="default",
                                   project_id="P1", claim_id=claim_contra.claim_id,
                                   evidence_id=ev_con, relation_type="contradicts"))
    return {"db": db, "idea": idea,
            "claims": (claim_known, claim_contra, claim_unknown, claim_gap),
            "relations": relations, "graph": graph}


def _projection(env):
    return IdeaTruthProjection(env["db"], env["graph"], "default", "P1")


# ---------------------------------------------------------------------------
# 1) projection 正确分类
# ---------------------------------------------------------------------------
def test_projection_classifies_claims(env):
    idea = env["idea"]
    p = _projection(env).project(idea.idea_id)

    assert p["maturity"] == "I2"  # 有真实 evidence
    assert p["counts"]["total_claims"] == 4
    assert p["counts"]["known"] == 1       # supports
    assert p["counts"]["contradicted"] == 1  # contradicts
    assert p["counts"]["evidence"] == 2    # 有 relation 的 claim 数
    assert p["counts"]["unknown"] == 1     # epistemic U
    assert p["counts"]["gaps"] == 2        # claim_unknown + claim_gap 均无 relation
    # known 列表内容
    assert p["known"][0]["statement"] == "视觉反馈改善动作完成"
    # contradicted
    assert p["contradicted"][0]["statement"] == "姿态估计可识别动作"


def test_projection_assumption_lists_a_claims(env):
    idea = env["idea"]
    p = _projection(env).project(idea.idea_id)
    # assumption = epistemic A 的 claims（claim_known/contra/gap 都是 A）
    assert p["counts"]["assumption"] == 3
    # unknown = epistemic U 的 claim
    assert [c["statement"] for c in p["unknown"]] == ["离线推理可行"]


# ---------------------------------------------------------------------------
# 2) snapshot 不可变
# ---------------------------------------------------------------------------
def test_snapshot_immutable_after_source_change(env):
    idea = env["idea"]
    db = env["db"]
    proj = _projection(env)
    snap = proj.snapshot(idea.idea_id)
    assert isinstance(snap, IdeaTruthSnapshot)
    before_gaps = snap.projection["counts"]["gaps"]

    # 修改源：给 claim_gap 加 evidence（通过 db + relation service）
    claim_gap = env["claims"][3]
    ev_new = db.add_evidence("default", "P1", kind="paper", title="new",
                             url="https://example.invalid/new")
    env["relations"].add(EvidenceRelation(relation_id="", tenant_id="default",
                                          project_id="P1",
                                          claim_id=claim_gap.claim_id,
                                          evidence_id=ev_new,
                                          relation_type="supports"))

    # snapshot 不受影响（深拷贝）
    assert snap.projection["counts"]["gaps"] == before_gaps
    assert json.loads(snap.to_json())["projection"]["counts"]["gaps"] == before_gaps
    # 新 projection 反映变化：claim_gap 有证据后仅剩 claim_unknown 是 gap
    after = _projection(env).project(idea.idea_id)
    assert after["counts"]["gaps"] == 1


# ---------------------------------------------------------------------------
# 3) maturity I0→I1→I2 判定
# ---------------------------------------------------------------------------
def test_maturity_evaluation(env):
    db = env["db"]
    graph = env["graph"]
    idea = env["idea"]
    ideas = IdeaService(db)

    # I0：raw idea 无 claims
    raw = ideas.create(Idea(idea_id="", tenant_id="default", project_id="P1",
                            title="Raw", raw_input="r", lifecycle_status="raw"))
    assert IdeaMaturity.evaluate(raw, graph) == IdeaMaturity.I0_RAW_IDEA

    # I1：有 claims 但无 evidence
    structured = ideas.create(Idea(idea_id="", tenant_id="default", project_id="P1",
                                   title="Structured", raw_input="r",
                                   lifecycle_status="structured"))
    ClaimService(db).create(Claim(claim_id="", tenant_id="default", project_id="P1",
                                  idea_id=structured.idea_id, claim_type="problem",
                                  statement="c1", epistemic_status="A"))
    assert IdeaMaturity.evaluate(structured, graph) == IdeaMaturity.I1_STRUCTURED_IDEA

    # I2：idea 的 claims 有真实 evidence
    assert IdeaMaturity.evaluate(idea, graph) == IdeaMaturity.I2_EVIDENCE_BACKED_IDEA

    # from_lifecycle 映射
    assert IdeaMaturity.from_lifecycle("raw") == IdeaMaturity.I0_RAW_IDEA
    assert IdeaMaturity.from_lifecycle("structured") == IdeaMaturity.I1_STRUCTURED_IDEA
    assert IdeaMaturity.from_lifecycle("evidence_backed") == IdeaMaturity.I2_EVIDENCE_BACKED_IDEA


# ---------------------------------------------------------------------------
# 4) 无 fake evidence：relation 的 evidence_id 必须真实存在
# ---------------------------------------------------------------------------
def test_relations_reference_real_evidence(env):
    idea = env["idea"]
    db = env["db"]
    graph = env["graph"]
    real_ids = {e["evidence_id"] for e in db.list_evidence("default", "P1")}
    for cl in graph.list_claims("default", "P1", idea_id=idea.idea_id):
        for rel in graph.get_claim_evidence("default", "P1", cl.claim_id):
            assert rel.evidence_id in real_ids  # 无 fake evidence


# ---------------------------------------------------------------------------
# 5) tenant/project scoped
# ---------------------------------------------------------------------------
def test_projection_tenant_project_scoped(env):
    db = env["db"]
    idea = env["idea"]
    # P2 无该 idea（P1 scope）→ get 抛 NotFound（不跨项目读取）
    p2 = IdeaTruthProjection(db, env["graph"], "default", "P2")
    from aipd_os.idea import IdeaNotFoundError
    with pytest.raises(IdeaNotFoundError):
        p2.project(idea.idea_id)
