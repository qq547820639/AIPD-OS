"""v5.8 Commit 14 / v5.8.1 Commit 3-4：Idea Truth projection + maturity 测试。

覆盖：
- projection 正确分类 supported_claims/assumption/evidence/contradicted/
  unknown/gaps（review-aware：只统计 reviewed relation）；
- snapshot 不可变（序列化后修改源不影响 snapshot）；
- maturity I0→I1→I2 判定正确（保守规则：key claims 全部检索+评审才 I2）；
- lifecycle_status 与 maturity 分离（Commit 3）；
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
    # v5.8.2 Commit 6：I2 需要 required key claim types 全覆盖
    # （problem/user/mechanism/technology）—— 补全缺失类别并全部评审。
    claim_prob = claims.create(Claim(claim_id="", tenant_id="default",
                                     project_id="P1", idea_id=idea.idea_id,
                                     claim_type="problem",
                                     statement="独居老人康复训练难以坚持",
                                     epistemic_status="A"))
    claim_user = claims.create(Claim(claim_id="", tenant_id="default",
                                     project_id="P1", idea_id=idea.idea_id,
                                     claim_type="user",
                                     statement="高龄用户认知负荷敏感",
                                     epistemic_status="A"))
    claim_tech = claims.create(Claim(claim_id="", tenant_id="default",
                                     project_id="P1", idea_id=idea.idea_id,
                                     claim_type="technology",
                                     statement="单目摄像头姿态估计可行",
                                     epistemic_status="A"))
    relations = EvidenceRelationService(db)
    graph = EvidenceGraph(db)

    # claim_known: supports（reviewed）；claim_contra: contradicts（reviewed）
    ev_sup = db.add_evidence("default", "P1", kind="paper", title="sup",
                             url="https://example.invalid/sup")
    ev_con = db.add_evidence("default", "P1", kind="paper", title="con",
                             url="https://example.invalid/con")
    rel_sup = relations.add(EvidenceRelation(relation_id="", tenant_id="default",
                                             project_id="P1", claim_id=claim_known.claim_id,
                                             evidence_id=ev_sup, relation_type="supports"))
    rel_con = relations.add(EvidenceRelation(relation_id="", tenant_id="default",
                                             project_id="P1", claim_id=claim_contra.claim_id,
                                             evidence_id=ev_con, relation_type="contradicts"))
    # required key claims（problem/user/technology）各挂 reviewed supports
    for cl in (claim_prob, claim_user, claim_tech):
        ev = db.add_evidence("default", "P1", kind="paper",
                             title=f"ev-{cl.claim_type}",
                             url=f"https://example.invalid/{cl.claim_type}")
        rel = relations.add(EvidenceRelation(relation_id="", tenant_id="default",
                                             project_id="P1", claim_id=cl.claim_id,
                                             evidence_id=ev, relation_type="supports"))
        relations.review("default", "P1", rel.relation_id, "reviewed")
    # v5.8.1 Commit 4：显式评审后 relations 才进入统计
    relations.review("default", "P1", rel_sup.relation_id, "reviewed")
    relations.review("default", "P1", rel_con.relation_id, "reviewed")
    return {"db": db, "idea": idea,
            "claims": (claim_known, claim_contra, claim_unknown, claim_gap,
                       claim_prob, claim_user, claim_tech),
            "relations": relations, "graph": graph}


def _projection(env):
    return IdeaTruthProjection(env["db"], env["graph"], "default", "P1")


# ---------------------------------------------------------------------------
# 1) projection 正确分类（review-aware）
# ---------------------------------------------------------------------------
def test_projection_classifies_claims(env):
    idea = env["idea"]
    p = _projection(env).project(idea.idea_id)

    # v5.8.2 Commit 6：required key claim types（problem/user/mechanism/
    # technology）全部存在且评审 → I2
    assert p["maturity"] == "I2"
    assert p["counts"]["total_claims"] == 7
    assert p["counts"]["supported_claims"] == 4  # behavior+problem+user+technology
    assert p["counts"]["contradicted"] == 1      # reviewed contradicts
    assert p["counts"]["evidence"] == 5          # 有 reviewed relation 的 claim 数
    assert p["counts"]["unknown"] == 1           # epistemic U
    assert p["counts"]["gaps"] == 2              # product + safety 无 reviewed relation
    assert p["counts"]["evidence_gaps"] == 2
    assert p["counts"]["pending_relations"] == 0
    assert p["counts"]["rejected_relations"] == 0
    # known 是 DEPRECATED 兼容字段（= supported_claims，只含 reviewed supports）
    assert p["known"] == p["supported_claims"]
    # supported_claims 列表内容
    assert p["supported_claims"][0]["statement"] == "视觉反馈改善动作完成"
    # contradicted
    assert p["contradicted"][0]["statement"] == "姿态估计可识别动作"
    # assessments
    assert p["assessments"][env["claims"][0].claim_id]["status"] == "SUPPORTED"
    assert p["assessments"][env["claims"][1].claim_id]["status"] == "CONTRADICTED"
    assert p["assessments"][env["claims"][2].claim_id]["status"] == "NOT_SEARCHED"
    assert p["assessments"][env["claims"][3].claim_id]["status"] == "NOT_SEARCHED"
    assert p["assessments"][env["claims"][4].claim_id]["status"] == "SUPPORTED"
    assert p["assessments"][env["claims"][5].claim_id]["status"] == "SUPPORTED"
    assert p["assessments"][env["claims"][6].claim_id]["status"] == "SUPPORTED"


def test_projection_assumption_lists_a_claims(env):
    idea = env["idea"]
    p = _projection(env).project(idea.idea_id)
    # assumption = epistemic A 的 claims（behavior/mechanism/safety +
    # problem/user/technology 都是 A）
    assert p["counts"]["assumption"] == 6
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

    # 修改源：给 claim_gap 加 evidence 并评审（reviewed）
    claim_gap = env["claims"][3]
    ev_new = db.add_evidence("default", "P1", kind="paper", title="new",
                             url="https://example.invalid/new")
    new_rel = env["relations"].add(EvidenceRelation(relation_id="", tenant_id="default",
                                                    project_id="P1",
                                                    claim_id=claim_gap.claim_id,
                                                    evidence_id=ev_new,
                                                    relation_type="supports"))
    env["relations"].review("default", "P1", new_rel.relation_id, "reviewed")

    # snapshot 不受影响（深拷贝）
    assert snap.projection["counts"]["gaps"] == before_gaps
    assert json.loads(snap.to_json())["projection"]["counts"]["gaps"] == before_gaps
    # 新 projection 反映变化：claim_gap 有 reviewed 证据后仅剩 claim_unknown 是 gap
    after = _projection(env).project(idea.idea_id)
    assert after["counts"]["gaps"] == 1


# ---------------------------------------------------------------------------
# 3) maturity I0→I1→I2 判定（保守规则）
# ---------------------------------------------------------------------------
def test_maturity_evaluation(env):
    db = env["db"]
    graph = env["graph"]
    idea = env["idea"]
    ideas = IdeaService(db)

    # I0：无 claims
    raw = ideas.create(Idea(idea_id="", tenant_id="default", project_id="P1",
                            title="Raw", raw_input="r", lifecycle_status="raw"))
    assert IdeaMaturity.evaluate(raw, graph) == IdeaMaturity.I0_RAW_IDEA

    # I1：有 claims 但无 evidence（key claim 未检索）
    structured = ideas.create(Idea(idea_id="", tenant_id="default", project_id="P1",
                                   title="Structured", raw_input="r",
                                   lifecycle_status="structured"))
    ClaimService(db).create(Claim(claim_id="", tenant_id="default", project_id="P1",
                                  idea_id=structured.idea_id, claim_type="problem",
                                  statement="c1", epistemic_status="A"))
    assert IdeaMaturity.evaluate(structured, graph) == IdeaMaturity.I1_STRUCTURED_IDEA

    # I2：key claim（mechanism）已检索 + 评审
    assert IdeaMaturity.evaluate(idea, graph) == IdeaMaturity.I2_EVIDENCE_BACKED_IDEA

    # from_lifecycle：DEPRECATED —— 旧值保留兼容映射；新值抛错
    assert IdeaMaturity.from_lifecycle("raw") == IdeaMaturity.I0_RAW_IDEA
    assert IdeaMaturity.from_lifecycle("structured") == IdeaMaturity.I1_STRUCTURED_IDEA
    assert IdeaMaturity.from_lifecycle("evidence_backed") == IdeaMaturity.I2_EVIDENCE_BACKED_IDEA
    with pytest.raises(ValueError, match="no longer encodes maturity"):
        IdeaMaturity.from_lifecycle("active")


def test_idea_lifecycle_independent_from_maturity(env):
    """Commit 3：lifecycle_status（对象生命状态）与 maturity（derived）分离。

    lifecycle=active 的 idea 可能 I0/I1/I2；lifecycle 不携带成熟度。
    """
    db = env["db"]
    graph = env["graph"]
    ideas = IdeaService(db)
    # 旧值 raw/structured/evidence_backed 读取时兼容映射为 active
    for legacy in ("raw", "structured", "evidence_backed"):
        idea = ideas.create(Idea(idea_id="", tenant_id="default", project_id="P1",
                                 title=legacy, raw_input="r",
                                 lifecycle_status=legacy))
        assert idea.lifecycle_status == "active"
        got = ideas.get("default", "P1", idea.idea_id)
        assert got.lifecycle_status == "active"
    # env idea：lifecycle=active 且 maturity=I2（maturity 由 graph 判定，非 lifecycle）
    assert env["idea"].lifecycle_status == "active"
    assert IdeaMaturity.evaluate(env["idea"], graph) == IdeaMaturity.I2_EVIDENCE_BACKED_IDEA
    # active + 无 claims → I0（lifecycle 相同但 maturity 不同）
    raw = ideas.create(Idea(idea_id="", tenant_id="default", project_id="P1",
                            title="no claims", raw_input="r"))
    assert raw.lifecycle_status == "active"
    assert IdeaMaturity.evaluate(raw, graph) == IdeaMaturity.I0_RAW_IDEA


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


# ---------------------------------------------------------------------------
# 6) Commit 4：保守 I2 + review semantics
# ---------------------------------------------------------------------------
def _idea_with_claims(db, claim_types):
    """建 idea + 指定 claim_type 的 claims（默认 A）。"""
    ideas = IdeaService(db)
    idea = ideas.create(Idea(idea_id="", tenant_id="default", project_id="P1",
                             title="I", raw_input="r"))
    claims = []
    for t in claim_types:
        claims.append(ClaimService(db).create(
            Claim(claim_id="", tenant_id="default", project_id="P1",
                  idea_id=idea.idea_id, claim_type=t,
                  statement=f"claim-{t}", epistemic_status="A")))
    return idea, claims


def _add_reviewed_relation(db, relations, claim, rtype="supports"):
    ev = db.add_evidence("default", "P1", kind="paper", title="t",
                         url="https://example.invalid/t")
    rel = relations.add(EvidenceRelation(relation_id="", tenant_id="default",
                                         project_id="P1", claim_id=claim.claim_id,
                                         evidence_id=ev, relation_type=rtype))
    relations.review("default", "P1", rel.relation_id, "reviewed")
    return rel


def test_one_relation_does_not_make_whole_idea_i2(env):
    """一条 pending/inconclusive relation 不使整个 Idea 升 I2。"""
    db = env["db"]
    graph = env["graph"]
    relations = env["relations"]
    idea, claims = _idea_with_claims(db, ["problem", "user"])  # 2 个 key claims
    # 只给 problem 挂一条 pending + inconclusive relation
    ev = db.add_evidence("default", "P1", kind="paper", title="t",
                         url="https://example.invalid/t")
    relations.add(EvidenceRelation(relation_id="", tenant_id="default",
                                   project_id="P1", claim_id=claims[0].claim_id,
                                   evidence_id=ev, relation_type="inconclusive"))
    assert IdeaMaturity.evaluate(idea, graph) == IdeaMaturity.I1_STRUCTURED_IDEA


def test_pending_support_does_not_count_as_supported(env):
    """pending supports 不进入 supported_claims / known（Commit 4）。"""
    db = env["db"]
    graph = env["graph"]
    relations = env["relations"]
    idea, claims = _idea_with_claims(db, ["problem", "user"])
    ev = db.add_evidence("default", "P1", kind="paper", title="t",
                         url="https://example.invalid/t")
    relations.add(EvidenceRelation(relation_id="", tenant_id="default",
                                   project_id="P1", claim_id=claims[0].claim_id,
                                   evidence_id=ev, relation_type="supports"))
    # 未评审：不算 supported、不算 searched 完成 → I1
    assert graph.get_supporting_evidence("default", "P1", claims[0].claim_id) == []
    p = IdeaTruthProjection(db, graph, "default", "P1").project(idea.idea_id)
    assert p["counts"]["supported_claims"] == 0
    assert p["counts"]["pending_relations"] == 1
    assert p["counts"]["not_searched_claims"] == 2
    assert p["maturity"] == "I1"


def test_rejected_relation_does_not_affect_truth(env):
    """rejected relation 不参与支持/反驳计数，单独列出。"""
    db = env["db"]
    graph = env["graph"]
    relations = env["relations"]
    idea, claims = _idea_with_claims(db, ["problem", "user"])
    ev = db.add_evidence("default", "P1", kind="paper", title="t",
                         url="https://example.invalid/t")
    rel = relations.add(EvidenceRelation(relation_id="", tenant_id="default",
                                         project_id="P1", claim_id=claims[0].claim_id,
                                         evidence_id=ev, relation_type="supports"))
    relations.review("default", "P1", rel.relation_id, "rejected")
    p = IdeaTruthProjection(db, graph, "default", "P1").project(idea.idea_id)
    assert p["counts"]["supported_claims"] == 0
    assert p["counts"]["contradicted"] == 0
    assert p["counts"]["rejected_relations"] == 1
    assert p["counts"]["pending_relations"] == 0
    assert p["maturity"] == "I1"


def test_maturity_requires_key_claim_coverage(env):
    """v5.8.2 Commit 6：I2 需要 **required key claim types 全覆盖**。

    只有部分 key claims 被调查（缺 technology）→ I1 + Evidence Gap；
    补全 required types 并全部评审 → I2。
    """
    db = env["db"]
    graph = env["graph"]
    relations = env["relations"]
    idea, claims = _idea_with_claims(db, ["problem", "user", "mechanism"])
    # 检索+评审已有 key claims（problem/user/mechanism）→ 仍 I1（缺 technology）
    for cl in claims:
        _add_reviewed_relation(db, relations, cl, "supports")
    assert IdeaMaturity.evaluate(idea, graph) == IdeaMaturity.I1_STRUCTURED_IDEA
    reasons = IdeaMaturity.gap_reasons(idea, graph)
    assert any("missing required key claim types: technology" in r
               for r in reasons), reasons
    # 补全 technology claim → 类型齐全 → I2
    tech = ClaimService(db).create(Claim(claim_id="", tenant_id="default",
                                         project_id="P1", idea_id=idea.idea_id,
                                         claim_type="technology",
                                         statement="claim-technology",
                                         epistemic_status="A"))
    assert IdeaMaturity.evaluate(idea, graph) == IdeaMaturity.I1_STRUCTURED_IDEA
    _add_reviewed_relation(db, relations, tech, "supports")
    assert IdeaMaturity.evaluate(idea, graph) == IdeaMaturity.I2_EVIDENCE_BACKED_IDEA
    assert IdeaMaturity.gap_reasons(idea, graph) == []
    # key_claims 辅助
    assert {c.claim_type for c in IdeaMaturity.key_claims(graph, idea)} == \
        {"problem", "user", "mechanism", "technology"}


def test_key_claims_exclude_non_key_types(env):
    """business/regulatory/safety 等非 key claim 不阻塞 I2（确定性规则），
    但**不能替代** required key claim types（v5.8.2 Commit 6）。"""
    db = env["db"]
    graph = env["graph"]
    relations = env["relations"]
    idea, claims = _idea_with_claims(db, ["safety", "business"])
    # 全部评审 safety/business → 仍 I1（无任何 required type）
    for cl in claims:
        _add_reviewed_relation(db, relations, cl, "supports")
    assert IdeaMaturity.evaluate(idea, graph) == IdeaMaturity.I1_STRUCTURED_IDEA
    assert any("missing required key claim types" in r
               for r in IdeaMaturity.gap_reasons(idea, graph))
    # 补全 4 个 required types 并评审 → I2
    for t in ("problem", "user", "mechanism", "technology"):
        cl = ClaimService(db).create(Claim(
            claim_id="", tenant_id="default", project_id="P1",
            idea_id=idea.idea_id, claim_type=t,
            statement=f"claim-{t}", epistemic_status="A"))
        _add_reviewed_relation(db, relations, cl, "supports")
    assert IdeaMaturity.evaluate(idea, graph) == IdeaMaturity.I2_EVIDENCE_BACKED_IDEA


def test_conflict_visible_in_projection(env):
    """reviewed contradicts 在 projection 中可见（contradicted + MIXED assessment）。"""
    db = env["db"]
    graph = env["graph"]
    relations = env["relations"]
    idea, claims = _idea_with_claims(db, ["problem", "user"])
    _add_reviewed_relation(db, relations, claims[0], "supports")
    _add_reviewed_relation(db, relations, claims[0], "contradicts")
    _add_reviewed_relation(db, relations, claims[1], "supports")
    p = IdeaTruthProjection(db, graph, "default", "P1").project(idea.idea_id)
    assert p["counts"]["supported_claims"] == 2  # problem + user 都有 reviewed supports
    assert p["counts"]["contradicted"] == 1      # problem 有 reviewed contradicts
    assert p["assessments"][claims[0].claim_id]["status"] == "MIXED"
    assert p["assessments"][claims[1].claim_id]["status"] == "SUPPORTED"
    # v5.8.2 Commit 6：缺 mechanism/technology → I1（contradiction 仍显式可见）
    assert p["maturity"] == "I1"
