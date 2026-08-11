"""v5.8.1 Commit 11：Supervisor runtime wiring（idea.* capabilities）测试。

覆盖：
- Supervisor 调度 idea.structure（I0→I1，同一 Idea）经 ExecutionRouter；
- Supervisor 调度 claim.research（I1→I2 evidence，默认 pending relation）；
- idea_truth.refresh（relation reviewed → projection 更新）；
- CLI intake 无 --run 不自动 decompose（创建与执行分离）；
- CLI intake --run + provider → I1；
- Supervisor 经 router 执行，不 bypass（未注册 adapter → internal_rework）。
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from aipd_os.execution.execution_router import ExecutionRouter
from aipd_os.execution.runs import RunStore
from aipd_os.idea import (
    Claim,
    ClaimService,
    EvidenceGraph,
    EvidenceRelation,
    EvidenceRelationService,
    Idea,
    IdeaDecomposer,
    IdeaDecompositionProvider,
    IdeaMaturity,
    IdeaService,
    IdeaTruthProjection,
    ResearchIntegration,
    ResearchToolAdapter,
    StructuredCandidate,
)
from aipd_os.state.db import AIPDStateDB
from aipd_os.supervisor import Supervisor
from aipd_os.supervisor.idea_capabilities import (
    schedule_claim_research,
    schedule_idea_structure,
    schedule_idea_truth_refresh,
)
from aipd_os.tool_adapters.idea_adapter import register_idea_adapters
from tests.fixtures.idea.research_fixtures import (
    FAKE_SUPPORT_RESULT_PER_SOURCE,
    FakeResearchProvider,
)


class _FakeDecomposerProvider(IdeaDecompositionProvider):
    name = "runtime-fake-decomposer"

    def available(self) -> bool:
        return True

    def decompose(self, raw_input, idea_context=None):
        return StructuredCandidate.from_dict({
            "title": "T", "goal": "g", "problem": "p", "target_user": "u",
            "desired_outcome": "o", "constraints": ["c"],
            "claims": [
                {"claim_type": "problem", "statement": "s1"},
                {"claim_type": "user", "statement": "s2"},
                {"claim_type": "mechanism", "statement": "s3"},
            ],
            "source": "runtime-fake",
        })


def _env(tmp_path):
    db_path = str(tmp_path / "state.db")
    db = AIPDStateDB(db_path)
    db.ensure_default_tenant("default")
    db.init_project("default", "P1", "P1", "goal")
    sup = Supervisor(db_path, tenant_id="default", project_id="P1", state_db=db)
    sup.init_lifecycle()
    return db, sup


def _registry(db, router=None):
    """含 idea.* 适配器的 registry（decomposer 用 fake provider）。"""
    from aipd_os.tool_adapters.builtin import build_registry
    reg = build_registry()
    decomposer = IdeaDecomposer(db, provider=_FakeDecomposerProvider(),
                                tenant_id="default", project_id="P1")
    register_idea_adapters(reg, db=db, decomposer=decomposer,
                           tenant_id="default", project_id="P1")
    return reg


def _router(tmp_path, reg):
    return ExecutionRouter(RunStore(str(tmp_path / "exec.db")), reg)


# ---------------------------------------------------------------------------
# 1) Supervisor 调度 idea.structure（I0→I1 同一 Idea）
# ---------------------------------------------------------------------------
def test_supervisor_schedules_idea_structure(tmp_path):
    db, sup = _env(tmp_path)
    idea = IdeaService(db).create(
        Idea(idea_id="", tenant_id="default", project_id="P1",
             title="raw", raw_input="prompt", goal="prompt",
             lifecycle_status="raw"), actor="alice")
    wid = schedule_idea_structure(sup, idea.idea_id)
    reg = _registry(db)
    router = _router(tmp_path, reg)
    results = sup.run_supervisor(steps=1, adapter_registry=reg,
                                 router=router, project_id="P1")
    assert results and results[0]["action"] == "complete"
    # 同一 Idea → I1 + claims（身份连续性）
    got = IdeaService(db).get("default", "P1", idea.idea_id)
    assert got.idea_id == idea.idea_id
    assert got.raw_input == "prompt"
    claims = ClaimService(db).list("default", "P1")
    assert len(claims) == 3
    assert IdeaMaturity.evaluate(got, EvidenceGraph(db)) == IdeaMaturity.I1_STRUCTURED_IDEA
    # work item complete
    import sqlite3
    conn = sqlite3.connect(str(tmp_path / "state.db"))
    status = conn.execute(
        "SELECT status FROM supervisor_work_items WHERE work_id=?",
        (wid,)).fetchone()[0]
    conn.close()
    assert status == "complete"


# ---------------------------------------------------------------------------
# 2) Supervisor 调度 claim.research（evidence + pending relation）
# ---------------------------------------------------------------------------
def _research_registry(tmp_path, db):
    """含 idea.* 适配器 + research provider 的 registry（claim.research 可路由）。"""
    from aipd_os.execution.execution_router import ExecutionRouter
    from aipd_os.tool_adapters.builtin import build_registry
    reg = build_registry()
    # 内层 research 路由（ClaimResearchAdapter 的 integration 使用）
    research_reg = build_registry()
    research_reg.register(ResearchToolAdapter(FakeResearchProvider(
        capability_id="research.academic_search",
        result=FAKE_SUPPORT_RESULT_PER_SOURCE)))
    research_router = ExecutionRouter(RunStore(str(tmp_path / "research.db")),
                                      research_reg)
    integ = ResearchIntegration(db, EvidenceRelationService(db),
                                EvidenceGraph(db), router=research_router)
    decomposer = IdeaDecomposer(db, provider=_FakeDecomposerProvider(),
                                tenant_id="default", project_id="P1")
    register_idea_adapters(reg, db=db, decomposer=decomposer,
                           integration=integ, tenant_id="default",
                           project_id="P1")
    return reg


def test_supervisor_schedules_claim_research(tmp_path):
    db, sup = _env(tmp_path)
    idea = IdeaService(db).create(
        Idea(idea_id="", tenant_id="default", project_id="P1",
             title="I", raw_input="r"))
    claim = ClaimService(db).create(
        Claim(claim_id="", tenant_id="default", project_id="P1",
              idea_id=idea.idea_id, claim_type="problem",
              statement="s", epistemic_status="A"))
    reg = _research_registry(tmp_path, db)
    router = ExecutionRouter(RunStore(str(tmp_path / "exec.db")), reg)
    schedule_claim_research(sup, claim.claim_id,
                            query="rehab adherence")
    results = sup.run_supervisor(steps=1, adapter_registry=reg,
                                 router=router, project_id="P1")
    assert results and results[0]["action"] == "complete"
    rels = EvidenceRelationService(db).list_for_claim("default", "P1", claim.claim_id)
    assert len(rels) == 1
    assert rels[0].review_status == "pending"  # Search ≠ Assessment
    assert len(db.list_evidence("default", "P1")) == 1


# ---------------------------------------------------------------------------
# 3) idea_truth.refresh（relation reviewed → projection 更新）
# ---------------------------------------------------------------------------
def test_supervisor_idea_truth_refresh(tmp_path):
    db, sup = _env(tmp_path)
    idea = IdeaService(db).create(
        Idea(idea_id="", tenant_id="default", project_id="P1", title="I", raw_input="r"))
    claim = ClaimService(db).create(
        Claim(claim_id="", tenant_id="default", project_id="P1",
              idea_id=idea.idea_id, claim_type="problem",
              statement="s", epistemic_status="A"))
    ev = db.add_evidence("default", "P1", kind="paper", title="t",
                         url="https://example.invalid/t")
    rel = EvidenceRelationService(db).add(
        EvidenceRelation(relation_id="", tenant_id="default", project_id="P1",
                         claim_id=claim.claim_id, evidence_id=ev,
                         relation_type="supports"), actor="alice")
    # reviewed 前：I1（pending 不算完成）
    reg = _registry(db)
    router = _router(tmp_path, reg)
    p1 = IdeaTruthProjection(db, EvidenceGraph(db), "default", "P1").project(idea.idea_id)
    assert p1["maturity"] == "I1"
    assert p1["counts"]["pending_relations"] == 1
    # 评审（evidence.assess_relation 能力）→ reviewed
    from aipd_os.supervisor import EVIDENCE_ASSESS_RELATION_CAPABILITY
    sup.add_work("S1_theory", "assess", "assess relation", "I1→I2",
                 capability_floor=EVIDENCE_ASSESS_RELATION_CAPABILITY,
                 inputs={"relation_id": rel.relation_id,
                         "review_status": "reviewed",
                         "tenant_id": "default", "project_id": "P1"})
    results = sup.run_supervisor(steps=1, adapter_registry=reg,
                                 router=router, project_id="P1")
    assert results and results[0]["action"] == "complete"
    # refresh → projection 更新（I2 + reviewed_supporting）
    schedule_idea_truth_refresh(sup, idea.idea_id)
    results3 = sup.run_supervisor(steps=1, adapter_registry=reg,
                                  router=router, project_id="P1")
    assert results3 and results3[0]["action"] == "complete"
    # 通过 projection 验证（IdeaTruthRefreshAdapter 返回动态 projection）
    fresh = IdeaTruthProjection(db, EvidenceGraph(db), "default", "P1").project(idea.idea_id)
    assert fresh["maturity"] == "I2"
    assert fresh["counts"]["reviewed_supporting"] == 1
    assert fresh["counts"]["pending_relations"] == 0


# ---------------------------------------------------------------------------
# 4) CLI intake 创建与执行分离
# ---------------------------------------------------------------------------
def _intake_args(db_path, run=False, prompt="做一款外骨骼助力系统"):
    return SimpleNamespace(db=db_path, prompt=prompt, project=None,
                           run=run, json=True)


def test_intake_no_run_does_not_decompose(tmp_path, monkeypatch, capsys):
    from aipd_os.cli import commands
    db_path = str(tmp_path / "state.db")
    rc = commands.cmd_intake(_intake_args(db_path, run=False))
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["command"] == "intake"
    assert data["idea_maturity"] == "I0"
    assert data["decompose_status"] == "CAPABILITY_UNAVAILABLE"
    # 无 claims（未 decompose）
    db = AIPDStateDB(db_path)
    assert ClaimService(db).list("default", data["project_id"]) == []
    assert IdeaService(db).get("default", data["project_id"],
                               data["idea_id"]).lifecycle_status == "active"


def test_intake_with_run_decomposes(tmp_path, monkeypatch, capsys):
    from aipd_os.cli import commands
    db_path = str(tmp_path / "state.db")
    monkeypatch.setattr(commands, "_find_idea_decompose_provider",
                        lambda: _FakeDecomposerProvider())
    rc = commands.cmd_intake(_intake_args(db_path, run=True))
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["idea_maturity"] == "I1"
    assert data["decompose_status"] == "COMPLETED"
    db = AIPDStateDB(db_path)
    claims = ClaimService(db).list("default", data["project_id"])
    assert len(claims) == 3
    got = IdeaService(db).get("default", data["project_id"], data["idea_id"])
    assert got.raw_input == "做一款外骨骼助力系统"
    assert got.lifecycle_status == "active"


# ---------------------------------------------------------------------------
# 5) Supervisor 经 router 执行，不 bypass
# ---------------------------------------------------------------------------
def test_supervisor_uses_router_not_direct_provider(tmp_path):
    db, sup = _env(tmp_path)
    idea = IdeaService(db).create(
        Idea(idea_id="", tenant_id="default", project_id="P1",
             title="raw", raw_input="prompt", goal="prompt",
             lifecycle_status="raw"), actor="alice")
    # registry 不含 idea.structure adapter → run_supervisor → internal_rework
    from aipd_os.tool_adapters.builtin import build_registry
    reg = build_registry()
    router = _router(tmp_path, reg)
    schedule_idea_structure(sup, idea.idea_id)
    results = sup.run_supervisor(steps=1, adapter_registry=reg,
                                 router=router, project_id="P1")
    assert results and results[0]["action"] == "internal_rework"
    assert "no adapter registered for idea.structure" in results[0]["reason"]
    # 未执行：仍 I0、无 claims（不 bypass 直接调 decomposer）
    got = IdeaService(db).get("default", "P1", idea.idea_id)
    assert IdeaMaturity.evaluate(got, EvidenceGraph(db)) == IdeaMaturity.I0_RAW_IDEA
    assert ClaimService(db).list("default", "P1") == []
    # 注册 adapter 后执行成功（证明 routing 是唯一路径）
    reg2 = _registry(db)
    results2 = sup.run_supervisor(steps=1, adapter_registry=reg2,
                                  router=_router(tmp_path, reg2), project_id="P1")
    assert results2 and results2[0]["action"] == "complete"
