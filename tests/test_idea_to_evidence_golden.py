"""v5.8 Commit 15：Golden E2E（离线 fixture 验证 Idea → Evidence 系统行为）。

fixture 位于 tests/golden/idea_to_evidence/，明确标注 EPISTEMIC_NOTE：
**fixture 非真实医学事实**，仅用于测试系统行为。

覆盖：
- 1 Structured Idea / 8 Claims / support evidence / contradict evidence /
  unknown claim / provenance / Idea Truth projection / I0→I1→I2 /
  restore 后一致 / tenant+project isolation / lineage 可追溯 / audit 可查。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from aipd_os.execution.execution_router import ExecutionRouter
from aipd_os.execution.registry import AdapterRegistry
from aipd_os.execution.runs import RunStore
from aipd_os.idea import (
    ClaimService,
    EvidenceGraph,
    EvidenceRelationService,
    EvidenceRequest,
    Idea,
    IdeaDecomposer,
    IdeaMaturity,
    IdeaService,
    IdeaTruthProjection,
    ResearchIntegration,
    ResearchToolAdapter,
)
from aipd_os.state.db import AIPDStateDB
from tests.fixtures.idea.research_fixtures import FakeResearchProvider

GOLDEN_DIR = Path(__file__).resolve().parent / "golden" / "idea_to_evidence"
PROMPT = (GOLDEN_DIR / "prompt.txt").read_text(encoding="utf-8").strip()
DECOMPOSER_JSON = json.loads(
    (GOLDEN_DIR / "fake_decomposer_output.json").read_text(encoding="utf-8"))
SUPPORT_JSON = json.loads(
    (GOLDEN_DIR / "fake_research_support.json").read_text(encoding="utf-8"))
CONTRADICT_JSON = json.loads(
    (GOLDEN_DIR / "fake_research_contradict.json").read_text(encoding="utf-8"))


class GoldenDecomposerProvider:
    """从 golden fixture 读确定性候选（仅测试路径）。"""

    name = "golden-idea-decomposer"

    def available(self) -> bool:
        return True

    def decompose(self, raw_input, idea_context=None):
        from aipd_os.idea import StructuredCandidate
        data = dict(DECOMPOSER_JSON)
        data.pop("EPISTEMIC_NOTE", None)
        return StructuredCandidate.from_dict(data)


def _env(tmp_path):
    db = AIPDStateDB(str(tmp_path / "state.db"))
    db.ensure_default_tenant("default")
    db.init_project("default", "P1", "P1", "goal")
    db.ensure_default_tenant("tenantB")
    db.init_project("tenantB", "PB", "PB", "goal")
    return db


@pytest.fixture
def env(tmp_path):
    return _env(tmp_path)


def _decompose(db):
    """intake + decompose → Structured Idea + Claims（真实 service 层）。"""
    ideas = IdeaService(db)
    raw = ideas.create(Idea(idea_id="", tenant_id="default", project_id="P1",
                            title="AI 独居老人居家康复助手", raw_input=PROMPT,
                            goal=PROMPT, lifecycle_status="raw"), actor="alice")
    assert IdeaMaturity.evaluate(raw, EvidenceGraph(db)) == IdeaMaturity.I0_RAW_IDEA

    decomposer = IdeaDecomposer(db, provider=GoldenDecomposerProvider(),
                                tenant_id="default", project_id="P1")
    result = decomposer.decompose_and_persist(PROMPT, actor="alice")
    return result


def _link_research(db, claims):
    """support / contradict / unknown（真实 service 层 + Fake provider）。"""
    claim_sup, claim_con = claims[0], claims[1]  # problem / user → support
    claim_unknown = claims[7]  # engineering → 留 unknown（不 link）

    relations = EvidenceRelationService(db)
    graph = EvidenceGraph(db)
    store = RunStore(str(db.path.parent / "exec.db"))
    reg = AdapterRegistry()
    reg.register(ResearchToolAdapter(
        FakeResearchProvider(capability_id="research.academic_search",
                             result=SUPPORT_JSON)))
    reg.register(ResearchToolAdapter(
        FakeResearchProvider(capability_id="research.related_work",
                             result=CONTRADICT_JSON)))
    router = ExecutionRouter(store, reg)
    integ = ResearchIntegration(db, relations, graph, router=router)

    integ.link_evidence_for_claim(EvidenceRequest(
        claim_id=claim_sup.claim_id, tenant_id="default", project_id="P1",
        capability="research.academic_search", inputs={"query": "rehab adherence"}),
        actor="alice")
    integ.link_evidence_for_claim(EvidenceRequest(
        claim_id=claim_con.claim_id, tenant_id="default", project_id="P1",
        capability="research.related_work", inputs={"query": "pose rehab"}),
        actor="alice")
    return claim_sup, claim_con, claim_unknown


# ---------------------------------------------------------------------------
# 1) 1 Structured Idea / 8 Claims（默认 A/U 非 V）
# ---------------------------------------------------------------------------
def test_golden_decompose_produces_idea_and_claims(env):
    db = env
    result = _decompose(db)
    assert result["idea"]["lifecycle_status"] == "structured"
    assert result["idea"]["tenant_id"] == "default"
    assert len(result["claims"]) == 8
    claims = ClaimService(db).list("default", "P1")
    assert len(claims) == 8
    for c in claims:
        assert c.epistemic_status in ("A", "U")
        assert c.epistemic_status != "V"


# ---------------------------------------------------------------------------
# 2) support / contradict / unknown → projection + maturity I1→I2
# ---------------------------------------------------------------------------
def test_golden_evidence_chain_and_projection(env):
    db = env
    result = _decompose(db)
    claims = ClaimService(db).list("default", "P1")
    _link_research(db, claims)

    graph = EvidenceGraph(db)
    proj = IdeaTruthProjection(db, graph, "default", "P1")
    p = proj.project(result["idea"]["idea_id"])
    assert p["maturity"] == "I2"
    assert p["counts"]["known"] == 1
    assert p["counts"]["contradicted"] == 1
    assert p["counts"]["gaps"] >= 1  # 未 link 的 claims 是 gaps
    # relation 的 evidence_id 必须真实存在（无 fake evidence）
    real_ids = {e["evidence_id"] for e in db.list_evidence("default", "P1")}
    for cl in claims:
        for rel in graph.get_claim_evidence("default", "P1", cl.claim_id):
            assert rel.evidence_id in real_ids
    # audit 可查
    actions = [r["action"] for r in db.list_audit(limit=100)]
    assert "idea.decompose" in actions and "evidence_relation.add" in actions


# ---------------------------------------------------------------------------
# 3) restore 后一致
# ---------------------------------------------------------------------------
def test_golden_restore_consistent(tmp_path):
    db_path = str(tmp_path / "state.db")
    db = AIPDStateDB(db_path)
    db.ensure_default_tenant("default")
    db.init_project("default", "P1", "P1", "goal")
    result = _decompose(db)
    claims = ClaimService(db).list("default", "P1")
    _link_research(db, claims)
    idea_id = result["idea"]["idea_id"]
    del db

    # 重开同一 DB → 数据一致
    db2 = AIPDStateDB(db_path)
    graph2 = EvidenceGraph(db2)
    proj2 = IdeaTruthProjection(db2, graph2, "default", "P1")
    p2 = proj2.project(idea_id)
    assert p2["maturity"] == "I2"
    assert len(ClaimService(db2).list("default", "P1")) == 8
    assert len(db2.list_evidence("default", "P1")) == 2


# ---------------------------------------------------------------------------
# 4) tenant+project isolation
# ---------------------------------------------------------------------------
def test_golden_tenant_project_isolation(env):
    db = env
    result = _decompose(db)
    idea_id = result["idea"]["idea_id"]
    # tenantB / PB 看不到（跨 scope get → NotFound）
    from aipd_os.idea import IdeaNotFoundError

    with pytest.raises(IdeaNotFoundError):
        IdeaTruthProjection(db, EvidenceGraph(db), "tenantB", "PB").project(idea_id)
    assert ClaimService(db).list("tenantB", "PB") == []


# ---------------------------------------------------------------------------
# 5) lineage 可追溯（evidence relation 作为可追溯 lineage）
# ---------------------------------------------------------------------------
def test_golden_lineage_traceable(env):
    db = env
    _decompose(db)
    claims = ClaimService(db).list("default", "P1")
    claim_sup, claim_con, claim_unknown = _link_research(db, claims)
    graph = EvidenceGraph(db)

    sup_rels = graph.get_supporting_evidence("default", "P1", claim_sup.claim_id)
    assert len(sup_rels) == 1
    # evidence 可追溯到 claim（relation 记录了 evidence_id + created_by）
    rel = sup_rels[0]
    assert rel.created_by == "alice"
    ev = db.list_evidence("default", "P1")
    assert any(e["evidence_id"] == rel.evidence_id for e in ev)
    # unknown claim 无 relation（不可追溯 evidence）
    assert graph.get_claim_evidence("default", "P1", claim_unknown.claim_id) == []


# ---------------------------------------------------------------------------
# 6) fixture 明确标注非真实医学事实
# ---------------------------------------------------------------------------
def test_golden_fixture_epistemic_note():
    for name in ("fake_decomposer_output.json", "fake_research_support.json",
                 "fake_research_contradict.json"):
        data = json.loads((GOLDEN_DIR / name).read_text(encoding="utf-8"))
        assert "EPISTEMIC_NOTE" in data
        assert "非真实" in data["EPISTEMIC_NOTE"] or "FIXTURE ONLY" in data["EPISTEMIC_NOTE"]
    readme = (GOLDEN_DIR / "README.md").read_text(encoding="utf-8")
    assert "EPISTEMIC_NOTE" in readme
    assert "不代表真实医学" in readme
