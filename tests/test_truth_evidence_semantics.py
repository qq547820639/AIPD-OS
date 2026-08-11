"""v5.7 Commit 7：Truth/Evidence 语义收敛测试。

覆盖（Commit 7A/7B/7C/7F）：
- external paper exists → 不创建 V fact（retrieval verified → E 而非 V）；
- full text retrieved → 不自动创建 V fact；
- is_fact=False → 绝不写 V fact（非事实结论只登记证据）；
- one supporting evidence → 不自动 verify claim（assess_trust 不自动 verified）；
- contradictory evidence → visible contradiction（resolve_conflicts 冲突标记）；
- no evidence → U / unknown（add_fact U 合法 + 默认认知状态 U）。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from aipd_os.product_truth.models import TruthRecord
from aipd_os.product_truth.store import ProductTruthStore
from aipd_os.product_truth.lineage import LineageGraph
from aipd_os.research import (
    EPISTEMIC_EXTERNAL_EVIDENCE,
    EPISTEMIC_UNKNOWN,
    STATUS_VERIFIED,
    Citation,
    ContractFetcher,
    ResearchBackend,
    ResearchFinding,
    default_epistemic_status,
    resolve_conflicts,
    run_research_chain,
)
from aipd_os.state.db import AIPDStateDB


@pytest.fixture
def db(tmp_path):
    d = AIPDStateDB(str(tmp_path / "state.db"), encryption_key="test-key")
    d.ensure_default_tenant()
    d.init_project("default", "p1", "P1", "goal")
    return d


@pytest.fixture
def store(tmp_path):
    return ProductTruthStore(str(tmp_path / "truth.db"))


def _finding(**kw):
    defaults = dict(
        key="k", value="v", status=STATUS_VERIFIED, confidence=0.8,
        citations=[Citation(source="official_standard", title="ISO-9001:2015",
                             confidence=0.9, kind="standard")],
    )
    defaults.update(kw)
    return ResearchFinding(**defaults)


# ---------------------------------------------------------------------------
# 1) external paper exists → 不创建 V fact（retrieval verified → E 而非 V）
# ---------------------------------------------------------------------------
def test_external_paper_does_not_create_v_fact(db):
    backend = ResearchBackend(db, "default", "p1")
    finding = _finding(key="copper_thickness", value="1.6 mm")
    fact_id = backend.write_finding(finding)
    assert fact_id is not None
    fact = db.get_fact("default", "p1", fact_id)
    assert fact["status"] == EPISTEMIC_EXTERNAL_EVIDENCE  # E
    assert fact["status"] != "V"
    # 证据 metadata 记录认知状态说明
    evs = db.list_evidence("default", "p1")
    ev_meta = json.loads(evs[0]["metadata_json"] or "{}")
    assert ev_meta.get("epistemic_status") == "E"
    assert "does NOT imply verified truth" in ev_meta.get("epistemic_note", "")


# ---------------------------------------------------------------------------
# 2) full text retrieved → 不自动创建 V fact
# ---------------------------------------------------------------------------
def test_fulltext_retrieved_does_not_auto_verify(db):
    finding = _finding(key="quality", value="requirements met",
                       status="not_verified")
    out = run_research_chain(db, "default", "p1", finding,
                             fetcher=ContractFetcher())
    assert out["fact_id"] is not None
    fact = db.get_fact("default", "p1", out["fact_id"])
    assert fact["status"] == "E"  # 拿到全文（retrieval verified）≠ verified truth


# ---------------------------------------------------------------------------
# 3) is_fact=False → 绝不写 V fact（非事实结论只登记证据）
# ---------------------------------------------------------------------------
def test_is_fact_false_never_writes_v_fact(db):
    backend = ResearchBackend(db, "default", "p1")
    finding = _finding(key="observation", value="x", is_fact=False)
    fact_id = backend.write_finding(finding)
    assert fact_id is None  # 非事实不固化为 Product Truth
    assert db.list_facts("default", "p1") == []
    # 证据仍被登记
    assert len(db.list_evidence("default", "p1")) == 1


# ---------------------------------------------------------------------------
# 4) one supporting evidence → 不自动 verify claim（assess_trust 保守）
# ---------------------------------------------------------------------------
def test_one_evidence_does_not_auto_verify_claim(store):
    lineage = LineageGraph(store)
    claim_id = store.add(TruthRecord(record_type="fact", content="claim X"))
    ev_id = store.add(TruthRecord(record_type="evidence", content="paper says X"))
    lineage.add_edge(ev_id, claim_id)

    assessment = store.assess_trust(claim_id)
    assert assessment.trust_level != "verified"  # 一条证据不自动 verified
    assert assessment.trust_level == "medium"    # 有上游依赖
    # evidence 本身是来源可信度 high，也不是 verified
    ev_assessment = store.assess_trust(ev_id)
    assert ev_assessment.trust_level == "high"
    assert ev_assessment.trust_level != "verified"


def test_explicit_owner_confirmation_can_verify(store):
    """verified 仅在显式 Owner/工程确认标记时返回。"""
    rid = store.add(TruthRecord(record_type="fact", content="confirmed",
                                metadata={"confirm_by_owner": True}))
    assert store.assess_trust(rid).trust_level == "verified"


# ---------------------------------------------------------------------------
# 5) contradictory evidence → visible contradiction
# ---------------------------------------------------------------------------
def test_contradictory_evidence_visible_conflict():
    findings = [
        {"key": "thickness", "value": "1.6 mm",
         "citations": [{"source": "paperA"}]},
        {"key": "thickness", "value": "2.4 mm",
         "citations": [{"source": "paperB"}]},
    ]
    out = resolve_conflicts(findings)
    assert out["conflict"] is True
    assert out["resolved"] is False
    assert any(c["key"] == "thickness" for c in out["conflicts"])


# ---------------------------------------------------------------------------
# 6) no evidence → U / unknown（add_fact U 合法 + 默认认知状态 U）
# ---------------------------------------------------------------------------
def test_no_evidence_add_fact_u_legal(db):
    # U（Unknown / 未验证）是合法认知状态
    fact_id = db.add_fact("default", "p1", "unknown_claim", "x", "U")
    fact = db.get_fact("default", "p1", fact_id)
    assert fact["status"] == "U"


def test_fact_schema_accepts_u_status():
    """fact.schema.json 的 status enum 必须包含 U。"""
    schema_path = Path(__file__).resolve().parent.parent / "assets" / "schemas" / "fact.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert "U" in schema["properties"]["status"]["enum"]
    assert "V" in schema["properties"]["status"]["enum"]
    # 状态描述存在（V/E/U 语义明确）
    desc = schema["properties"]["status"]["description"]
    assert "U=Unknown" in desc
    assert "E=Reliable external evidence" in desc


def test_default_epistemic_status_unknown_without_evidence():
    # 无证据 → U（unknown）
    assert default_epistemic_status(_finding(citations=[])) == EPISTEMIC_UNKNOWN
    # 有外部证据 → E
    assert default_epistemic_status(_finding()) == EPISTEMIC_EXTERNAL_EVIDENCE
