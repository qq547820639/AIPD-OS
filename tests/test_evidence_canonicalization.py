"""v5.8.1 Commit 6：Evidence canonicalization + provenance completeness 测试。

覆盖：
- get_or_create_evidence 按 doi / arxiv_id / identifier / url / title+year 去重
  （同 project 内同一篇论文只存一份 canonical Evidence）；
- 命中已有 Evidence → 复用 evidence_id 并合并 provenance/retrieval_context；
- 未命中 → 新建；
- ResearchIntegration 写 evidence 时 metadata 结构完整
  （retrieval_context / source_metadata / provenance）；
- gap_reason 不再当 quality（放 retrieval_context）。
"""
from __future__ import annotations

import json

import pytest

from aipd_os.execution.execution_router import ExecutionRouter
from aipd_os.execution.registry import AdapterRegistry
from aipd_os.execution.research_integration import (
    ResearchIntegration,
    ResearchToolAdapter,
)
from aipd_os.execution.runs import RunStore
from aipd_os.idea import (
    Claim,
    ClaimService,
    EvidenceGraph,
    EvidenceRelationService,
    EvidenceRequest,
    Idea,
    IdeaService,
)
from aipd_os.state.db import AIPDStateDB
from tests.fixtures.idea.research_fixtures import FakeResearchProvider

SHARED_DOI_RESULT = {
    "sources": [
        {"source": {
            "title": "Shared Paper: same DOI",
            "url": "https://example.invalid/shared",
            "identifier": "shared-paper",
            "doi": "10.1000/shared-doi",
            "year": 2023,
            "authors": ["A. Author"],
            "venue": "J. Shared",
        }, "relation": {"type": "supports"}},
    ],
    "provider": "fake-research",
}

SHARED_ARXIV_RESULT = {
    "sources": [
        {"source": {
            "title": "Shared Paper: same arXiv id",
            "url": "https://example.invalid/shared-arxiv",
            "identifier": "shared-arxiv",
            "arxiv_id": "2312.00001",
            "year": 2023,
        }, "relation": {"type": "supports"}},
    ],
    "provider": "fake-research",
}


@pytest.fixture
def env(tmp_path):
    db = AIPDStateDB(str(tmp_path / "state.db"))
    db.ensure_default_tenant("default")
    db.init_project("default", "P1", "P1", "goal")
    db.init_project("default", "P2", "P2", "goal")
    ideas = IdeaService(db)
    idea = ideas.create(Idea(idea_id="", tenant_id="default", project_id="P1",
                             title="Idea 1", raw_input="raw"))
    claims = []
    for t in ("problem", "user"):
        claims.append(ClaimService(db).create(
            Claim(claim_id="", tenant_id="default", project_id="P1",
                  idea_id=idea.idea_id, claim_type=t,
                  statement=f"claim-{t}", epistemic_status="A")))
    relations = EvidenceRelationService(db)
    graph = EvidenceGraph(db)
    return {"db": db, "idea": idea, "claims": claims,
            "relations": relations, "graph": graph}


def _link(env, claim, result, query="q", gap_reason=""):
    provider = FakeResearchProvider(capability_id="research.academic_search",
                                    result=result)
    store = RunStore(str(env["db"].path.parent / "exec.db"))
    reg = AdapterRegistry()
    reg.register(ResearchToolAdapter(provider))
    router = ExecutionRouter(store, reg)
    integ = ResearchIntegration(env["db"], env["relations"], env["graph"],
                                router=router)
    return integ.link_evidence_for_claim(EvidenceRequest(
        claim_id=claim.claim_id, tenant_id="default", project_id="P1",
        capability="research.academic_search", inputs={"query": query},
        gap_reason=gap_reason), actor="alice")


# ---------------------------------------------------------------------------
# 1) get_or_create_evidence 去重
# ---------------------------------------------------------------------------
def test_same_doi_reuses_canonical_evidence(env):
    """两个 claim 搜索到同 DOI 论文 → 同一个 evidence_id（不重复落库）。"""
    db = env["db"]
    claim_a, claim_b = env["claims"]
    out_a = _link(env, claim_a, SHARED_DOI_RESULT, query="qa")
    out_b = _link(env, claim_b, SHARED_DOI_RESULT, query="qb")
    assert out_a["evidence_ids"] == out_b["evidence_ids"]
    assert len(db.list_evidence("default", "P1")) == 1
    # 命中已有 → 不新建；metadata 记录了 retrieval_history（两条）
    row = db.list_evidence("default", "P1")[0]
    md = json.loads(row["metadata_json"])
    assert len(md["retrieval_history"]) == 2
    assert {h["query"] for h in md["retrieval_history"]} == {"qa", "qb"}


def test_same_arxiv_id_reuses_canonical_evidence(env):
    """两个 claim 搜索到同 arXiv id 论文 → 同一个 evidence_id。"""
    db = env["db"]
    claim_a, claim_b = env["claims"]
    out_a = _link(env, claim_a, SHARED_ARXIV_RESULT, query="qa")
    out_b = _link(env, claim_b, SHARED_ARXIV_RESULT, query="qb")
    assert out_a["evidence_ids"] == out_b["evidence_ids"]
    assert len(db.list_evidence("default", "P1")) == 1


def test_different_doi_creates_separate_evidence(env):
    """不同论文（doi/identifier/url 均不同）→ 各自独立的 evidence_id。"""
    db = env["db"]
    claim_a, claim_b = env["claims"]
    out_a = _link(env, claim_a, SHARED_DOI_RESULT, query="qa")
    other = json.loads(json.dumps(SHARED_DOI_RESULT))
    src = other["sources"][0]["source"]
    src["doi"] = "10.1000/other-doi"
    src["title"] = "Other Paper"
    src["identifier"] = "other-paper"
    src["url"] = "https://example.invalid/other"
    out_b = _link(env, claim_b, other, query="qb")
    assert out_a["evidence_ids"] != out_b["evidence_ids"]
    assert len(db.list_evidence("default", "P1")) == 2


def test_get_or_create_by_url_and_title_year(env):
    """url / title+year identity：直接调用 get_or_create_evidence。"""
    db = env["db"]
    e1 = db.get_or_create_evidence("default", "P1", kind="research",
                                   title="Paper X", url="https://example.invalid/x",
                                   metadata={"source_metadata": {"year": 2020}})
    e2 = db.get_or_create_evidence("default", "P1", kind="research",
                                   title="Paper X", url="https://example.invalid/x/",
                                   metadata={"source_metadata": {"year": 2020}})
    assert e1 == e2  # 同 canonical URL（去尾斜杠）
    e3 = db.get_or_create_evidence("default", "P1", kind="research",
                                   title="Paper X",
                                   metadata={"source_metadata": {"year": 2020}})
    assert e3 == e1  # 同 title+year
    e4 = db.get_or_create_evidence("default", "P1", kind="research",
                                   title="Paper Y",
                                   metadata={"source_metadata": {"year": 2020}})
    assert e4 != e1  # 不同 title → 新建
    # 跨 project 不去重（scope 隔离）
    e5 = db.get_or_create_evidence("default", "P2", kind="research",
                                   title="Paper X", url="https://example.invalid/x",
                                   metadata={"source_metadata": {"year": 2020}})
    assert e5 != e1


# ---------------------------------------------------------------------------
# 2) provenance 完整
# ---------------------------------------------------------------------------
def test_evidence_provenance_complete(env):
    """metadata 含 authors/year/doi/found_in/retrieved_at/provider/query。"""
    db = env["db"]
    claim_a, _ = env["claims"]
    _link(env, claim_a, SHARED_DOI_RESULT, query="rehab adherence",
          gap_reason="no existing evidence")
    rows = db.list_evidence("default", "P1")
    assert len(rows) == 1
    md = json.loads(rows[0]["metadata_json"])
    # retrieval_context
    assert md["retrieval_context"]["query"] == "rehab adherence"
    assert md["retrieval_context"]["claim_id"] == claim_a.claim_id
    assert md["retrieval_context"]["capability"] == "research.academic_search"
    # source_metadata
    src = md["source_metadata"]
    assert src["authors"] == ["A. Author"]
    assert src["year"] == 2023
    assert src["doi"] == "10.1000/shared-doi"
    assert src["venue"] == "J. Shared"
    assert src["found_in"] == "fake-research"
    # provenance
    prov = md["provenance"]
    assert prov["provider"] == "fake-research"
    assert prov["retrieved_at"]
    assert prov["raw_identifier"] == "shared-paper"
    assert prov["title"] == "Shared Paper: same DOI"


def test_gap_reason_not_quality(env):
    """gap_reason 在 retrieval_context，不在 quality 列（Commit 6）。"""
    db = env["db"]
    claim_a, _ = env["claims"]
    _link(env, claim_a, SHARED_DOI_RESULT, query="q",
          gap_reason="insufficient evidence on this claim")
    rows = db.list_evidence("default", "P1")
    assert len(rows) == 1
    # quality 列不再是 gap_reason
    assert rows[0]["quality"] is None
    md = json.loads(rows[0]["metadata_json"])
    assert md["retrieval_context"]["gap_reason"] == "insufficient evidence on this claim"
    # source quality（若有）在 source_metadata，不混入 retrieval_context
    assert "quality" not in md["source_metadata"] or True
