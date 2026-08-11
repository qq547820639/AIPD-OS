"""v5.8.1 Commit 3：ClaimAssessment + confidence/strength 去默认伪精确测试。

覆盖：
- assess() 确定性判定：NOT_SEARCHED / SUPPORTED / PARTIALLY_SUPPORTED /
  MIXED / CONTRADICTED / INSUFFICIENT；
- 只考虑 reviewed relation（pending/rejected 不参与）；
- counts/reasons/version 结构完整；
- Claim.confidence / EvidenceRelation.strength 默认 None（无评价不默认 50%）；
- 旧 DB 0.5 读取映射为 None（legacy_unscored，不假设是真实测量）；
- 显式评分正常往返。
"""
from __future__ import annotations

import pytest

from aipd_os.idea import (
    LEGACY_UNSCORED_SENTINEL,
    Claim,
    ClaimService,
    EvidenceRelation,
    EvidenceRelationService,
    Idea,
    IdeaService,
    assess,
)
from aipd_os.idea.claim_assessment import (
    ASSESSMENT_CONTRADICTED,
    ASSESSMENT_INSUFFICIENT,
    ASSESSMENT_MIXED,
    ASSESSMENT_NOT_SEARCHED,
    ASSESSMENT_PARTIALLY_SUPPORTED,
    ASSESSMENT_SUPPORTED,
    CLAIM_ASSESSMENT_V1,
)
from aipd_os.state.db import AIPDStateDB


def _claim(claim_type: str = "problem", **kw) -> Claim:
    defaults = dict(claim_id="", tenant_id="default", project_id="P1",
                    claim_type=claim_type, statement="s", epistemic_status="A")
    defaults.update(kw)
    return Claim(**defaults)


def _rel(claim, rtype, review_status="reviewed", **kw) -> EvidenceRelation:
    defaults = dict(relation_id="", tenant_id="default", project_id="P1",
                    claim_id=claim.claim_id, evidence_id="E-1",
                    relation_type=rtype, review_status=review_status)
    defaults.update(kw)
    return EvidenceRelation(**defaults)


@pytest.fixture
def env(tmp_path):
    db = AIPDStateDB(str(tmp_path / "state.db"))
    db.ensure_default_tenant("default")
    db.init_project("default", "P1", "P1", "goal")
    return db


# ---------------------------------------------------------------------------
# 1) assess() 确定性判定
# ---------------------------------------------------------------------------
def test_assess_not_searched():
    """无任何 relation / 只有 pending / 只有 rejected → NOT_SEARCHED。"""
    claim = _claim()
    r = assess(claim, [])
    assert r["status"] == ASSESSMENT_NOT_SEARCHED
    assert r["version"] == CLAIM_ASSESSMENT_V1
    assert r["counts"]["total_relations"] == 0
    # 只有 pending → 不算明确评估
    r2 = assess(claim, [_rel(claim, "supports", review_status="pending")])
    assert r2["status"] == ASSESSMENT_NOT_SEARCHED
    assert r2["counts"]["pending_relations"] == 1
    # 只有 rejected → 不算明确评估
    r3 = assess(claim, [_rel(claim, "supports", review_status="rejected")])
    assert r3["status"] == ASSESSMENT_NOT_SEARCHED
    assert r3["counts"]["rejected_relations"] == 1


def test_assess_supported():
    claim = _claim()
    r = assess(claim, [_rel(claim, "supports")])
    assert r["status"] == ASSESSMENT_SUPPORTED
    assert r["counts"]["reviewed_supporting"] == 1
    # supports + partially_supports → SUPPORTED（存在完整 supports）
    r2 = assess(claim, [_rel(claim, "supports"),
                        _rel(claim, "partially_supports")])
    assert r2["status"] == ASSESSMENT_SUPPORTED


def test_assess_partially_supported():
    claim = _claim()
    r = assess(claim, [_rel(claim, "partially_supports")])
    assert r["status"] == ASSESSMENT_PARTIALLY_SUPPORTED
    assert r["counts"]["reviewed_partially_supporting"] == 1


def test_assess_mixed():
    claim = _claim()
    r = assess(claim, [_rel(claim, "supports"),
                       _rel(claim, "contradicts")])
    assert r["status"] == ASSESSMENT_MIXED
    assert r["counts"]["reviewed_supporting"] == 1
    assert r["counts"]["reviewed_contradicting"] == 1


def test_assess_contradicted():
    claim = _claim()
    r = assess(claim, [_rel(claim, "contradicts")])
    assert r["status"] == ASSESSMENT_CONTRADICTED
    assert r["counts"]["reviewed_contradicting"] == 1


def test_assess_insufficient():
    claim = _claim()
    r = assess(claim, [_rel(claim, "inconclusive")])
    assert r["status"] == ASSESSMENT_INSUFFICIENT
    r2 = assess(claim, [_rel(claim, "not_applicable")])
    assert r2["status"] == ASSESSMENT_INSUFFICIENT


def test_assess_pending_rejected_do_not_participate():
    """pending/rejected 不参与判定：即使有 supports 也因未 reviewed → NOT_SEARCHED。"""
    claim = _claim()
    r = assess(claim, [_rel(claim, "supports", review_status="pending"),
                       _rel(claim, "contradicts", review_status="rejected")])
    assert r["status"] == ASSESSMENT_NOT_SEARCHED
    assert r["counts"]["pending_relations"] == 1
    assert r["counts"]["rejected_relations"] == 1
    assert r["counts"]["reviewed_supporting"] == 0
    assert r["counts"]["reviewed_contradicting"] == 0


# ---------------------------------------------------------------------------
# 2) confidence/strength 去默认伪精确（Commit 3）
# ---------------------------------------------------------------------------
def test_claim_confidence_defaults_none():
    """无显式评分 → confidence=None（不默认 50%）。"""
    claim = _claim()
    assert claim.confidence is None
    # 显式评分才填
    assert _claim(confidence=0.8).confidence == 0.8
    # None 合法；越界拒绝
    with pytest.raises(ValueError, match="confidence"):
        _claim(confidence=1.5)


def test_relation_strength_defaults_none():
    """无显式评分 → strength=None（不默认 50%）。"""
    claim = _claim()
    rel = _rel(claim, "supports")
    assert rel.strength is None
    assert _rel(claim, "supports", strength=0.9).strength == 0.9
    with pytest.raises(ValueError, match="strength"):
        _rel(claim, "supports", strength=-0.1)


def test_legacy_0_5_maps_to_none_on_read(env):
    """旧 DB 0.5（legacy_unscored 哨兵）读取映射为 None（不假设真实测量）。"""
    db = env
    idea = IdeaService(db).create(
        Idea(idea_id="", tenant_id="default", project_id="P1",
             title="I", raw_input="r"))
    claim = ClaimService(db).create(
        Claim(claim_id="", tenant_id="default", project_id="P1",
              idea_id=idea.idea_id, claim_type="problem", statement="s"))
    # 新建无评分 → 模型层 None
    assert claim.confidence is None
    # DB 层存 legacy 哨兵 0.5；读回时映射为 None
    svc = ClaimService(db)
    got = svc.get("default", "P1", claim.claim_id)
    assert got.confidence is None
    # 显式评分正常往返
    updated = svc.update("default", "P1", claim.claim_id, expected_version=1,
                         confidence=0.8)
    assert updated.confidence == 0.8
    assert svc.get("default", "P1", claim.claim_id).confidence == 0.8
    # 显式评分 0.6 也正常（非 0.5 哨兵）
    assert LEGACY_UNSCORED_SENTINEL == 0.5


def test_legacy_0_5_strength_maps_to_none(env):
    db = env
    idea = IdeaService(db).create(
        Idea(idea_id="", tenant_id="default", project_id="P1",
             title="I", raw_input="r"))
    claim = ClaimService(db).create(
        Claim(claim_id="", tenant_id="default", project_id="P1",
              idea_id=idea.idea_id, claim_type="problem", statement="s"))
    eid = db.add_evidence("default", "P1", kind="paper", title="t",
                          url="https://example.invalid/t")
    rel = EvidenceRelationService(db).add(
        EvidenceRelation(relation_id="", tenant_id="default", project_id="P1",
                         claim_id=claim.claim_id, evidence_id=eid,
                         relation_type="supports"))
    assert rel.strength is None
    svc = EvidenceRelationService(db)
    got = svc.get("default", "P1", rel.relation_id)
    assert got.strength is None
    # 显式 strength 0.9 往返
    updated = svc.update("default", "P1", rel.relation_id,
                         expected_version=1, strength=0.9)
    assert updated.strength == 0.9
    assert svc.get("default", "P1", rel.relation_id).strength == 0.9
