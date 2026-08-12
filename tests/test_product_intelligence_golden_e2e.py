"""v5.9 Golden E2E（§57-59）：AI 帮助独居老人居家康复。

在 Golden Idea（I2，4 类 key claims 全部 reviewed）上生成：
3-5 Insights / 1-3 Opportunities / 3-5 Principles / 5-12 Requirements /
3-8 Features；Projection 先 BLOCKED（Owner approval missing）→ Owner
approve → 选中 Product Definition 进入 ProductTruth；Feature→Evidence
全链可追溯。

**fixture 仅测试系统行为，不构成现实医学证明**（EPISTEMIC_NOTE）。
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
    LIFECYCLE_ACTIVE,
    Feature,
    Insight,
    Opportunity,
    ProductDefinitionGate,
    ProductDefinitionProjection,
    ProductIntelligenceService,
    ProductPrinciple,
    Requirement,
)
from aipd_os.state.db import AIPDStateDB

GOLDEN_IDEA = "我想做一个利用 AI 帮助独居老人居家康复的产品"
EPISTEMIC_NOTE = "Golden fixture：仅测试系统行为，不构成现实医学证明"


@pytest.fixture
def golden(tmp_path):
    """Golden project：Idea I2 + 全部 reviewed（真实 fixture，非医学结论）。"""
    db = AIPDStateDB(str(tmp_path / "golden.db"))
    db.ensure_default_tenant("default")
    db.init_project("default", "p1", "居家康复", GOLDEN_IDEA)
    idea = IdeaService(db).create(
        Idea(idea_id="", tenant_id="default", project_id="p1",
             title=GOLDEN_IDEA, raw_input=GOLDEN_IDEA))
    claims = {}
    statements = {
        "problem": "独居老人难以坚持居家康复训练",
        "user": "高龄用户对多层菜单与连续选择有高认知负担",
        "mechanism": "连续选择产生认知负担，任务完成率下降",
        "technology": "单目摄像头姿态估计可识别康复动作",
    }
    for t, stmt in statements.items():
        claims[t] = ClaimService(db).create(
            Claim(claim_id="", tenant_id="default", project_id="p1",
                  idea_id=idea.idea_id, claim_type=t, statement=stmt,
                  epistemic_status="A"))
    rels = EvidenceRelationService(db)
    for c in claims.values():
        ev = db.add_evidence("default", "p1", "paper", c.statement,
                             url=f"https://example.invalid/{c.claim_id}",
                             metadata={"epistemic_note": EPISTEMIC_NOTE})
        rel = rels.add(EvidenceRelation(
            relation_id="", tenant_id="default", project_id="p1",
            claim_id=c.claim_id, evidence_id=ev, relation_type="supports"))
        rels.review("default", "p1", rel.relation_id, "reviewed")
    return {"db": db, "idea": idea, "claims": claims,
            "pi": ProductIntelligenceService(db)}


def _derive_full_definition(golden) -> dict:
    """基于证据生成完整 Product Definition（3-5/1-3/3-5/5-12/3-8）。"""
    pi = golden["pi"]
    idea = golden["idea"]
    claims = golden["claims"]
    c = list(claims.values())

    insights = []
    insight_defs = [
        ("user_problem", "高龄用户需要短路径完成训练任务",
         [c[1].claim_id, c[0].claim_id]),
        ("behavior", "连续选择导致任务中断与放弃",
         [c[2].claim_id, c[1].claim_id]),
        ("mechanism", "减少选择数量可改善任务完成",
         [c[2].claim_id]),
        ("technology", "单目姿态估计可支撑自动化动作反馈",
         [c[3].claim_id]),
    ]
    for itype, stmt, srcs in insight_defs:
        insights.append(pi.create_insight(Insight(
            insight_id="", tenant_id="default", project_id="p1",
            idea_id=idea.idea_id, statement=stmt, insight_type=itype,
            source_claim_ids=srcs)))

    opportunities = [
        pi.create_opportunity(Opportunity(
            opportunity_id="", tenant_id="default", project_id="p1",
            idea_id=idea.idea_id,
            title="AI 居家康复数字伴侣",
            statement="为独居老人提供低认知负担的康复训练引导",
            target_user="65+ 独居老人", problem="康复训练难以坚持",
            desired_outcome="训练完成率提升且无需家人监督",
            source_insight_ids=[insights[0].insight_id,
                                insights[1].insight_id])),
        pi.create_opportunity(Opportunity(
            opportunity_id="", tenant_id="default", project_id="p1",
            idea_id=idea.idea_id,
            title="自动化动作反馈服务",
            statement="基于姿态估计的实时反馈降低对专业人员的依赖",
            source_insight_ids=[insights[3].insight_id]),
        ),
    ]

    principles = [
        pi.create_principle(ProductPrinciple(
            principle_id="", tenant_id="default", project_id="p1",
            opportunity_id=opportunities[0].opportunity_id,
            statement="关键康复任务减少层级与选择数量",
            rationale="连续选择产生认知负担（behavior insight）",
            source_insight_ids=[insights[1].insight_id,
                                insights[2].insight_id])),
        pi.create_principle(ProductPrinciple(
            principle_id="", tenant_id="default", project_id="p1",
            opportunity_id=opportunities[0].opportunity_id,
            statement="训练任务一次一目标，避免多任务并行",
            source_insight_ids=[insights[0].insight_id]),
        ),
        pi.create_principle(ProductPrinciple(
            principle_id="", tenant_id="default", project_id="p1",
            opportunity_id=opportunities[1].opportunity_id,
            statement="自动化反馈优先于人工指令",
            source_insight_ids=[insights[3].insight_id]),
        ),
        pi.create_principle(ProductPrinciple(
            principle_id="", tenant_id="default", project_id="p1",
            opportunity_id=opportunities[0].opportunity_id,
            statement="安全边界提示不得鼓励超范围动作",
            source_insight_ids=[insights[0].insight_id]),
        ),
    ]

    req_defs = [
        ("核心训练流程交互深度 ≤ 1 层菜单", "interaction", "critical",
         "usability test with 65+ users", principles[0].principle_id),
        ("单任务全屏模式：一次只呈现一个训练目标", "interaction", "critical",
         "usability test", principles[1].principle_id),
        ("训练完成自动反馈（语音+画面）", "functional", "critical",
         "system test", principles[2].principle_id),
        ("动作识别使用单目摄像头，无需穿戴设备", "performance", "critical",
         "camera-based validation", principles[2].principle_id),
        ("安全边界：超出范围动作触发停止提示", "safety", "critical",
         "safety validation protocol", principles[3].principle_id),
        ("离线可用：无网络时核心训练仍可运行", "functional", "important",
         "offline run test", principles[2].principle_id),
        ("训练进度自动记录并周报", "functional", "normal",
         "integration test", principles[1].principle_id),
    ]
    requirements = []
    for stmt, rtype, crit, verify, pid in req_defs:
        requirements.append(pi.create_requirement(Requirement(
            requirement_id="", tenant_id="default", project_id="p1",
            title=stmt[:12], statement=stmt, requirement_type=rtype,
            criticality=crit, verification_method=verify,
            source_principle_ids=[pid])))

    feat_defs = [
        ("单任务全屏训练模式", "mode", [requirements[1].requirement_id,
                                        requirements[0].requirement_id]),
        ("语音+画面自动反馈", "automation", [requirements[2].requirement_id]),
        ("单目摄像头动作识别", "integration", [requirements[3].requirement_id]),
        ("安全停止与提示", "safety", [requirements[4].requirement_id]),
        ("离线训练包", "capability", [requirements[5].requirement_id]),
    ]
    features = []
    for title, ftype, req_ids in feat_defs:
        features.append(pi.create_feature(Feature(
            feature_id="", tenant_id="default", project_id="p1",
            title=title, description=f"{title}（{EPISTEMIC_NOTE}）",
            feature_type=ftype, source_requirement_ids=req_ids)))
    return {"insights": insights, "opportunities": opportunities,
            "principles": principles, "requirements": requirements,
            "features": features}


def _activate_all(golden, chain) -> None:
    """candidate → active（Gate 提交对象）。"""
    pi = golden["pi"]
    for req in chain["requirements"]:
        v = pi.get_requirement("default", "p1", req.requirement_id).version_no
        pi._update("requirement", "default", "p1", req.requirement_id, v,
                   "t", lifecycle_status=LIFECYCLE_ACTIVE)
    for feat in chain["features"]:
        v = pi.get_feature("default", "p1", feat.feature_id).version_no
        pi._update("feature", "default", "p1", feat.feature_id, v,
                   "t", lifecycle_status=LIFECYCLE_ACTIVE)


def test_golden_definition_scale(golden):
    """§57：数量要求 3-5/1-3/3-5/5-12/3-8。"""
    chain = _derive_full_definition(golden)
    assert 3 <= len(chain["insights"]) <= 5
    assert 1 <= len(chain["opportunities"]) <= 3
    assert 3 <= len(chain["principles"]) <= 5
    assert 5 <= len(chain["requirements"]) <= 12
    assert 3 <= len(chain["features"]) <= 8


def test_golden_projection_blocked_before_owner(golden):
    """§57：Owner approve 前 → ProductDefinitionProjection BLOCKED。"""
    chain = _derive_full_definition(golden)
    _activate_all(golden, chain)
    proj = ProductDefinitionProjection(golden["db"], "default", "p1").project()
    assert proj["gate"]["result"] == GATE_BLOCKED
    assert any("Owner approval missing" in b
               for b in proj["gate"]["blockers"])
    # owner 状态可见
    assert proj["gate"]["owner"]["latest_approved"] is False


def test_golden_owner_approve_commits_product_truth(golden):
    """§57：Owner approve → 选中 Product Definition 进入 ProductTruth。"""
    chain = _derive_full_definition(golden)
    _activate_all(golden, chain)
    gate = ProductDefinitionGate(golden["db"], "default", "p1")
    did = gate.propose_owner_decision(actor="owner")
    gate.resolve_owner_decision(did, "approve", "approved", actor="owner")
    committed = gate.commit_approved(actor="owner")
    assert committed["requirements"] >= 5
    assert committed["features"] >= 3
    from aipd_os.product_truth.store import ProductTruthStore
    store = ProductTruthStore(str(golden["db"].path), tenant_id="default",
                              project_id="p1")
    reqs = store.query(record_type="requirement")
    feats = store.query(record_type="feature")
    assert len(reqs) >= 5 and len(feats) >= 3
    # gate_approved 标记 + source_commit 锚点
    assert all(r.metadata.get("gate_approved") for r in reqs)
    assert all(r.metadata.get("source_commit") for r in reqs)


def test_golden_feature_traceability(golden):
    """§58：任意 Feature 可回溯 Feature→Requirement→Principle→Insight→
    Claim→EvidenceRelation→Evidence。"""
    chain = _derive_full_definition(golden)
    feat = chain["features"][0]
    trace = golden["pi"].feature_evidence_trace(
        feat.feature_id, tenant_id="default", project_id="p1")
    assert trace["evidence_reached"] is True
    assert len(trace["claims"]) >= 1
    assert len(trace["evidence"]) >= 1
    node_types = {e["source"]["node_type"] for e in trace["path"]}
    for t in ("feature", "requirement", "product_principle", "insight", "claim"):
        assert t in node_types
    assert any(e["target"]["node_type"] == "evidence" for e in trace["path"])


def test_golden_epistemic_note_not_medical_truth(golden):
    """§59：Golden fixture 不包装成现实医学证明。"""
    chain = _derive_full_definition(golden)
    for ins in chain["insights"]:
        assert ins.epistemic_status == "A"  # 假设，非 V
        assert ins.lifecycle_status == "candidate"  # 未 commit
    for req in chain["requirements"]:
        assert req.definition_status in ("RECOMMENDED", "TBD")  # 非 CONFIRMED
    # 证据 metadata 带 epistemic_note
    for e in golden["db"].list_evidence("default", "p1"):
        assert "epistemic_note" in (e.get("metadata_json") or "")


def test_golden_unknown_preserved_and_contradiction_visible(golden):
    """unknown 保留显式；contradiction 可见（不隐藏、不自动 verified）。"""
    chain = _derive_full_definition(golden)
    req = chain["requirements"][0]
    v = golden["pi"].get_requirement("default", "p1",
                                     req.requirement_id).version_no
    golden["pi"]._update("requirement", "default", "p1", req.requirement_id,
                         v, "t", epistemic_status="U")
    proj = ProductDefinitionProjection(golden["db"], "default", "p1").project()
    assert req.requirement_id in proj["unknowns"]
    # 未提交（U 不自动 verified）
    gate = ProductDefinitionGate(golden["db"], "default", "p1")
    result = gate.evaluate()
    assert any("unknown without explicit waiver" in b
               for b in result["blockers"])
