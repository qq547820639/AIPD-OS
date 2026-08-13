"""v5.8 Commit 15 / v5.8.1 Commit 11：Golden E2E（离线 fixture 验证
Idea → Evidence 系统行为，正式 Supervisor → ExecutionRouter 运行路径）。

fixture 位于 tests/golden/idea_to_evidence/，明确标注 EPISTEMIC_NOTE：
**fixture 非真实医学事实**，仅用于测试系统行为。

覆盖（v5.8.1 Commit 11 §46 正式流程）：
1 intake → 2 创建 ONE canonical Idea → 3 I0 → 4 Supervisor 调度
idea.structure → 5 fake deterministic decomposer → 6 SAME Idea → I1 →
7 8 Candidate Claims → 8 raw_input preserved → 9 constraints valid JSON →
10 Supervisor 调度 claim.research → 11 fake research 返回多 source →
12 sources canonicalized/deduped → 13 default relations pending →
14 evidence.assess_relation 评审 → 15 ClaimAssessment → 16 key claims
searched → 17 I2 → 18 contradiction visible → 19 unknown visible →
20 snapshot/audit → 21 DB close → 22 restore → 23 status identical。
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from aipd_os.execution.execution_router import ExecutionRouter
from aipd_os.execution.research_integration import (
    ResearchIntegration,
    ResearchToolAdapter,
)
from aipd_os.execution.runs import RunStore
from aipd_os.idea import (
    ClaimService,
    EvidenceGraph,
    EvidenceRelationService,
    Idea,
    IdeaDecomposer,
    IdeaMaturity,
    IdeaService,
    IdeaTruthProjection,
)
from aipd_os.state.db import AIPDStateDB
from aipd_os.supervisor import Supervisor
from aipd_os.supervisor.idea_capabilities import (
    EVIDENCE_ASSESS_RELATION_CAPABILITY,
    schedule_claim_research,
    schedule_idea_structure,
)
from aipd_os.tool_adapters.builtin import build_registry
from aipd_os.tool_adapters.idea_adapter import register_idea_adapters
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


def _runtime(db):
    """Supervisor + registry + router（§46：正式运行路径）。

    Supervisor 只调度；执行经 ExecutionRouter → idea.* adapter →
    Domain Service（不 bypass）。
    """
    sup = Supervisor(str(db.path), tenant_id="default", project_id="P1",
                     state_db=db)
    sup.init_lifecycle()
    reg = build_registry()
    # 内层 research 路由（claim.research adapter 的 integration 使用）
    research_reg = build_registry()
    research_reg.register(ResearchToolAdapter(FakeResearchProvider(
        capability_id="research.academic_search", result=SUPPORT_JSON)))
    research_reg.register(ResearchToolAdapter(FakeResearchProvider(
        capability_id="research.related_work", result=CONTRADICT_JSON)))
    research_router = ExecutionRouter(RunStore(str(db.path.parent / "research.db")),
                                      research_reg)
    graph = EvidenceGraph(db)
    relations = EvidenceRelationService(db)
    integ = ResearchIntegration(db, relations, graph, router=research_router)
    decomposer = IdeaDecomposer(db, provider=GoldenDecomposerProvider(),
                                tenant_id="default", project_id="P1")
    register_idea_adapters(reg, db=db, decomposer=decomposer,
                           integration=integ, relations=relations,
                           tenant_id="default", project_id="P1")
    router = ExecutionRouter(RunStore(str(db.path.parent / "exec.db")), reg)
    return sup, reg, router


def _decompose(db):
    """intake（I0）→ Supervisor 调度 idea.structure → SAME Idea → I1（§46 1-9）。

    v5.8.1 Commit 2：I0→I1 不新建第二个 Idea，而是 update 同一个 raw Idea
    （idea_id/raw_input/created_at 不变），Candidate Claims 挂在同一 idea 下。
    v5.8.1 Commit 3：lifecycle_status 只表达对象生命状态（active）。
    v5.8.1 Commit 11：执行经 Supervisor → ExecutionRouter → idea.structure adapter。
    """
    ideas = IdeaService(db)
    raw = ideas.create(Idea(idea_id="", tenant_id="default", project_id="P1",
                            title="AI 独居老人居家康复助手", raw_input=PROMPT,
                            goal=PROMPT, lifecycle_status="raw"), actor="alice")
    assert IdeaMaturity.evaluate(raw, EvidenceGraph(db)) == IdeaMaturity.I0_RAW_IDEA

    sup, reg, router = _runtime(db)
    wid = schedule_idea_structure(sup, raw.idea_id, actor="alice")
    results = sup.run_supervisor(steps=1, adapter_registry=reg,
                                 router=router, project_id="P1")
    assert results and results[0]["action"] == "complete"
    # 结果从 work item outputs_json 读（Supervisor.complete 固化）
    conn = sqlite3.connect(str(db.path))
    out = json.loads(conn.execute(
        "SELECT outputs_json FROM supervisor_work_items WHERE work_id=?",
        (wid,)).fetchone()[0])
    conn.close()
    # 身份连续性：结构化后仍是同一个 idea_id
    assert out["idea"]["idea_id"] == raw.idea_id
    assert out["idea"]["raw_input"] == PROMPT
    assert out["idea"]["lifecycle_status"] == "active"
    assert out["maturity"] == "I1"
    return out


def _link_research(db, claims):
    """Supervisor 调度 claim.research + evidence.assess_relation（§46 10-16）。

    v5.8.1 Commit 4：I2 需要所有 key claims（problem/user/mechanism/technology）
    完成检索+评审 —— 对 4 个 key claims 都调度 research + assessment。
    """
    claim_problem, claim_user, _, claim_mech, claim_tech, *_ = claims
    claim_unknown = claims[7]  # engineering → 留 unknown（不 link）

    sup, reg, router = _runtime(db)
    # 10-12：调度 4 个 key claims 的 claim.research（多 source；deduped）
    wid_research = []
    for claim, capability, query in [
        (claim_problem, "research.academic_search", "rehab adherence"),
        (claim_user, "research.related_work", "pose rehab"),
        (claim_mech, "research.academic_search", "pose estimation"),
        (claim_tech, "research.academic_search", "monocular camera"),
    ]:
        wid_research.append(schedule_claim_research(
            sup, claim.claim_id, capability=capability, query=query,
            actor="alice"))
    results = sup.run_supervisor(steps=len(wid_research), adapter_registry=reg,
                                 router=router, project_id="P1")
    assert all(r["action"] == "complete" for r in results)
    # 13：默认 relations pending/inconclusive（Search ≠ Assessment）
    all_rels = []
    for cl in (claim_problem, claim_user, claim_mech, claim_tech):
        for r in EvidenceRelationService(db).list_for_claim(
                "default", "P1", cl.claim_id):
            assert r.review_status == "pending"
            all_rels.append(r)
    # 14：evidence.assess_relation 评审全部 relations（reviewed）
    for rel in all_rels:
        sup.add_work("S1_theory", "assess", "assess relation", "I1→I2",
                     capability_floor=EVIDENCE_ASSESS_RELATION_CAPABILITY,
                     inputs={"relation_id": rel.relation_id,
                             "review_status": "reviewed",
                             "tenant_id": "default", "project_id": "P1"})
    results_assess = sup.run_supervisor(steps=len(all_rels),
                                        adapter_registry=reg,
                                        router=router, project_id="P1")
    assert all(r["action"] == "complete" for r in results_assess)
    return claim_problem, claim_user, claim_unknown


# ---------------------------------------------------------------------------
# 1) 1 Structured Idea / 8 Claims（默认 A/U 非 V）
# ---------------------------------------------------------------------------
def test_golden_decompose_produces_idea_and_claims(env):
    db = env
    result = _decompose(db)
    assert result["idea"]["lifecycle_status"] == "active"  # 对象生命状态（Commit 3）
    assert result["idea"]["tenant_id"] == "default"
    assert len(result["claims"]) == 8
    claims = ClaimService(db).list("default", "P1")
    assert len(claims) == 8
    for c in claims:
        assert c.epistemic_status in ("A", "U")
        assert c.epistemic_status != "V"
    # §9：constraints valid JSON
    json.loads(result["idea"]["constraints_json"])
    # §20：audit 可查（idea.structure work 经 router）
    actions = [r["action"] for r in db.list_audit(limit=100)]
    assert "idea.structure" in actions


# ---------------------------------------------------------------------------
# 2) support / contradict / unknown → projection + maturity I1→I2（review-aware）
# ---------------------------------------------------------------------------
def test_golden_evidence_chain_and_projection(env):
    db = env
    result = _decompose(db)
    claims = ClaimService(db).list("default", "P1")
    claim_problem, claim_user, _ = _link_research(db, claims)

    graph = EvidenceGraph(db)
    proj = IdeaTruthProjection(db, graph, "default", "P1")
    p = proj.project(result["idea"]["idea_id"])
    assert p["maturity"] == "I2"  # 4 个 key claims 全部检索+评审
    # key claims: problem(支持+inconclusive) user(反驳) mechanism(支持+inconclusive)
    #            technology(支持+inconclusive)
    assert p["counts"]["supported_claims"] == 3
    assert p["counts"]["contradicted"] == 1
    assert p["counts"]["gaps"] == 4  # behavior/product/safety/engineering 未 link
    assert p["counts"]["pending_relations"] == 0
    assert p["counts"]["rejected_relations"] == 0
    assert p["counts"]["not_searched_claims"] == 4
    # §14：inconclusive 评估可见（golden fixture 含 inconclusive source）
    assert p["counts"]["reviewed_inconclusive"] == 3
    # §15：ClaimAssessment 显式状态
    assessments = p["assessments"]
    assert assessments[claim_problem.claim_id]["status"] == "SUPPORTED"
    assert assessments[claim_user.claim_id]["status"] == "CONTRADICTED"
    # §18/19：contradiction + 未检索（gaps/unknown-like）可见
    assert p["contradicted"][0]["statement"]
    assert len(p["gaps"]) == 4  # behavior/product/safety/engineering 无证据可见
    # §20：snapshot artifact（深拷贝 + 生成时间戳）
    snap = proj.snapshot(result["idea"]["idea_id"])
    assert snap.generated_at and snap.projection["maturity"] == "I2"
    assert snap.projection["counts"]["reviewed_supporting"] == 3
    # relation 的 evidence_id 必须真实存在（无 fake evidence）
    real_ids = {e["evidence_id"] for e in db.list_evidence("default", "P1")}
    for cl in claims:
        for rel in graph.get_claim_evidence("default", "P1", cl.claim_id):
            assert rel.evidence_id in real_ids
    # audit 可查（idea.structure + evidence_relation.add + evidence_relation.review）
    actions = [r["action"] for r in db.list_audit(limit=100)]
    assert "idea.structure" in actions and "evidence_relation.add" in actions
    assert "evidence_relation.review" in actions


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
    # §21：DB close
    del db

    # §22-23：重开同一 DB → 数据一致
    db2 = AIPDStateDB(db_path)
    graph2 = EvidenceGraph(db2)
    proj2 = IdeaTruthProjection(db2, graph2, "default", "P1")
    p2 = proj2.project(idea_id)
    assert p2["maturity"] == "I2"
    assert len(ClaimService(db2).list("default", "P1")) == 8
    # v5.8.1 Commit 6/14：canonical evidence 去重 —— 4 次 link 命中 3 篇论文
    # （supports 论文被 problem/mechanism/technology 复用；inconclusive 论文同样
    #  被三者复用；contradict 论文被 user 使用）
    assert len(db2.list_evidence("default", "P1")) == 3


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
