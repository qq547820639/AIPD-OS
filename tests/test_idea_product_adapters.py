"""idea_adapter / product_adapters 本地确定性适配器的直接测试（补盲区）。

此前这些适配器只有经 runtime 的间接覆盖；这里直接构造依赖（fake / 真实
AIPDStateDB）验证契约：discover 形状、validate_input、execute 返回值、
诚实降级路径。
"""
from __future__ import annotations

import pytest

from aipd_os.state.db import AIPDStateDB
from aipd_os.tool_adapters.product_adapters import (
    PRODUCT_CREATE_SNAPSHOT,
    PRODUCT_DEFINITION_GATE,
    ProductCreateSnapshotAdapter,
    ProductDefinitionGateAdapter,
)


@pytest.fixture
def pdb(tmp_path) -> AIPDStateDB:
    db = AIPDStateDB(str(tmp_path / "state.db"), encryption_key="test-key")
    db.ensure_default_tenant()
    db.init_project("default", "p1", "智能护理设备", "目标")
    return db


# ------------------------------------------------------------- idea adapters
def test_idea_structure_adapter_contract_and_unavailable(tmp_path):
    from aipd_os.execution.adapter import AdapterError
    from aipd_os.idea.decomposer import IdeaDecompositionUnavailable
    from aipd_os.tool_adapters.idea_adapter import IdeaStructureAdapter

    class _FakeDecomposer:
        def decompose_existing(self, idea_id, actor="system"):
            if idea_id == "boom":
                raise IdeaDecompositionUnavailable("no provider")
            return {"idea": {"idea_id": idea_id}, "claims": [{"claim_id": "c1"}]}

    adapter = IdeaStructureAdapter(_FakeDecomposer())  # type: ignore[arg-type]
    assert adapter.capability_id() == "idea.structure"
    assert adapter.validate_input({}) == ["'idea_id' required"]
    out = adapter.execute({"idea_id": "i1"})
    assert out["capability"] == "idea.structure"
    assert out["claims"][0]["claim_id"] == "c1"
    assert out["maturity"] == "I1"
    # 诚实降级：decomposer 不可用 → external_blocked
    with pytest.raises(AdapterError) as ei:
        adapter.execute({"idea_id": "boom", "work_id": "w1"})
    assert ei.value.classification == "external_blocked"


def test_claim_research_and_assess_and_refresh_adapters(pdb):
    from aipd_os.idea.claim_service import ClaimService
    from aipd_os.idea.claims import Claim
    from aipd_os.idea.evidence_graph import EvidenceGraph
    from aipd_os.idea.evidence_relations import EvidenceRelation, EvidenceRelationService
    from aipd_os.idea.models import Idea
    from aipd_os.idea.projections import IdeaTruthProjection
    from aipd_os.idea.service import IdeaService
    from aipd_os.tool_adapters.idea_adapter import (
        ClaimResearchAdapter,
        EvidenceAssessRelationAdapter,
        IdeaTruthRefreshAdapter,
    )

    idea_svc = IdeaService(pdb)
    idea = idea_svc.create(Idea(idea_id="", tenant_id="default", project_id="p1",
                                title="康复训练", raw_input="帮助独居老人康复"))

    # evidence.assess_relation：先建 relation 再评审
    graph = EvidenceGraph(pdb)
    claim = ClaimService(pdb).create(Claim(
        claim_id="", tenant_id="default", project_id="p1", idea_id=idea.idea_id,
        claim_type="problem", statement="高龄用户训练难坚持"))
    evidence_id = pdb.add_evidence("default", "p1", "paper", "一篇论文",
                                   identifier="doi:1")
    rel_svc = EvidenceRelationService(pdb)
    rel = rel_svc.add(EvidenceRelation(
        relation_id="", tenant_id="default", project_id="p1",
        claim_id=claim.claim_id, evidence_id=evidence_id,
        relation_type="supports"))
    assess = EvidenceAssessRelationAdapter(rel_svc)
    assert assess.validate_input({"relation_id": rel.relation_id}) == [
        "'review_status' must be reviewed or rejected"]
    out = assess.execute({"relation_id": rel.relation_id,
                          "review_status": "reviewed",
                          "tenant_id": "default", "project_id": "p1"})
    assert out["relation"]["review_status"] == "reviewed"

    # claim.research：无 router（能力未接线）→ external_blocked 诚实降级
    from aipd_os.execution.adapter import AdapterError
    from aipd_os.execution.research_integration import ResearchIntegration

    integration = ResearchIntegration(pdb, rel_svc, graph)  # router=None
    research = ClaimResearchAdapter(integration)
    with pytest.raises(AdapterError) as ei:
        research.execute({"claim_id": claim.claim_id,
                          "capability": "research.academic_search",
                          "tenant_id": "default", "project_id": "p1"})
    assert ei.value.classification == "external_blocked"

    # idea_truth.refresh：真实 projection（无 provider 也确定性可用）
    refresh = IdeaTruthRefreshAdapter(
        IdeaTruthProjection(pdb, graph, tenant_id="default", project_id="p1"))
    out = refresh.execute({"idea_id": idea.idea_id})
    assert out["capability"] == "idea_truth.refresh"
    assert out["projection"]["idea_id"] == idea.idea_id


# --------------------------------------------------------- product adapters
def test_product_snapshot_and_gate_adapters_local_deterministic(pdb):
    snap_adapter = ProductCreateSnapshotAdapter(pdb)
    assert snap_adapter.discover()["available"] is True
    assert snap_adapter.capability_id() == PRODUCT_CREATE_SNAPSHOT
    out = snap_adapter.execute({"tenant_id": "default", "project_id": "p1"})
    assert out["status"] == "snapshot_frozen"
    assert out["snapshot_id"]
    assert isinstance(out["requirements"], int) and isinstance(out["features"], int)

    gate_adapter = ProductDefinitionGateAdapter(pdb)
    assert gate_adapter.capability_id() == PRODUCT_DEFINITION_GATE
    # 有 snapshot → 返回完整评估结构（含 hard_blockers/authorization/eligibility）
    g = gate_adapter.execute({"tenant_id": "default", "project_id": "p1"})
    assert g["snapshot_id"] == out["snapshot_id"]
    assert "hard_blockers" in g and "authorization" in g and "eligibility" in g


def test_product_gate_without_snapshot_returns_no_snapshot(pdb):
    gate_adapter = ProductDefinitionGateAdapter(pdb)
    g = gate_adapter.execute({"tenant_id": "default", "project_id": "p1"})
    assert g["result"] == "NO_SNAPSHOT"
    assert g["eligibility"]["eligible"] is False
