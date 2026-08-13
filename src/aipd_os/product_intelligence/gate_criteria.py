"""Product Definition Gate 的 criteria 层（v5.9.1，§46-48/57）。

从 ``gate.py`` 抽出：criteria 静态定义（criteria 表 / status / severity /
policy 版本）、结构化结果类型（CriterionResult / GateEvaluation）、
``_criterion`` 工厂、纯函数（``_derive_trust`` / ``_json`` / ``_head_sha``）
与逐条 criteria 评估（:class:`GateCriteriaEvaluator`）。

本模块只负责**确定性技术评估**（criteria 是否通过），不含授权 / commit
事务语义——那些留在 ``gate.py`` 的 :class:`ProductDefinitionGate`。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aipd_os.idea.evidence_graph import EvidenceGraph
from aipd_os.idea.maturity import IdeaMaturity
from aipd_os.idea.service import IdeaService
from aipd_os.state.db import AIPDStateDB
from aipd_os.state.lineage import LineageNodeRef, LineageService

from .models import CRITICALITY_CRITICAL
from .service import (
    NODE_FEATURE,
    NODE_PRINCIPLE,
    NODE_REQUIREMENT,
    ProductIntelligenceService,
)
from .snapshot import (
    ProductDefinitionSnapshot,
    ProductDefinitionSnapshotService,
    ProductDefinitionSnapshotView,
)

# definition_status=CONFLICT（critical requirement 冲突检测）
DEFINITION_STATUS_CONFLICT = "CONFLICT"

# criterion id
CRITERION_IDEA_MATURITY = "IDEA_MATURITY"
CRITERION_KEY_CLAIM_ASSESSMENT = "KEY_CLAIM_ASSESSMENT"
CRITERION_CRITICAL_CONTRADICTIONS = "CRITICAL_CONTRADICTIONS"
CRITERION_SELECTED_OPPORTUNITY = "SELECTED_OPPORTUNITY"
CRITERION_PRINCIPLES_PRESENT = "PRINCIPLES_PRESENT"
CRITERION_REQUIREMENT_TRACEABILITY = "REQUIREMENT_TRACEABILITY"
CRITERION_FEATURE_TRACEABILITY = "FEATURE_TRACEABILITY"
CRITERION_CRITICAL_REQUIREMENT_SOURCE = "CRITICAL_REQUIREMENT_SOURCE"
CRITERION_CRITICAL_REQUIREMENT_VERIFICATION = "CRITICAL_REQUIREMENT_VERIFICATION"
CRITERION_CRITICAL_UNKNOWN = "CRITICAL_UNKNOWN"
CRITERION_CRITICAL_CONFLICT = "CRITICAL_CONFLICT"
CRITERION_PRINCIPLES_BOUND = "PRINCIPLES_BOUND_TO_SELECTED_OPPORTUNITY"
CRITERION_SNAPSHOT_SET_INTEGRITY = "SNAPSHOT_SET_INTEGRITY"
CRITERION_SNAPSHOT_UPSTREAM_BASIS = "SNAPSHOT_UPSTREAM_BASIS"
CRITERION_SNAPSHOT_FRESHNESS = "SNAPSHOT_FRESHNESS"
CRITERION_OWNER_DECISION = "OWNER_DECISION"
CRITERION_CONDITIONAL_WAIVER = "CONDITIONAL_WAIVER"

# criterion status
CRIT_PASS = "PASS"
CRIT_FAIL = "FAIL"
CRIT_CONDITIONAL = "CONDITIONAL"
CRIT_WARN = "WARN"
CRIT_INFO = "INFO"

# severity（决定落入哪个列表）
SEV_HARD = "hard"
SEV_CONDITIONAL = "conditional"
SEV_WARNING = "warning"
SEV_INFO = "information"

GATE_POLICY_VERSION = "product_definition_gate_v2"
GATE_EVALUATOR_VERSION = "product_definition_gate_evaluator_v1"


@dataclass
class CriterionResult:
    """单条结构化 criterion 输出（§46）。"""

    criterion_id: str
    status: str  # PASS/FAIL/CONDITIONAL/WARN/INFO
    severity: str  # hard/conditional/warning/information
    message: str
    affected_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"criterion_id": self.criterion_id, "status": self.status,
                "severity": self.severity, "message": self.message,
                "affected_refs": self.affected_refs}


@dataclass
class GateEvaluation:
    """结构化 Gate 评估结果（P0-01：不再把文本全塞 blockers）。"""

    evaluation_id: str
    tenant_id: str
    project_id: str
    snapshot_id: str
    snapshot_hash: str
    result: str  # READY / CONDITIONAL / BLOCKED
    hard_blockers: list[str] = field(default_factory=list)
    conditional_blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    information: list[str] = field(default_factory=list)
    criteria_results: list[CriterionResult] = field(default_factory=list)
    evaluated_at: str = ""
    evaluator_version: str = GATE_EVALUATOR_VERSION
    policy_version: str = GATE_POLICY_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "evaluation_id": self.evaluation_id,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "snapshot_id": self.snapshot_id,
            "snapshot_hash": self.snapshot_hash,
            "result": self.result,
            "hard_blockers": self.hard_blockers,
            "conditional_blockers": self.conditional_blockers,
            "warnings": self.warnings,
            "information": self.information,
            "criteria_results": [c.to_dict()
                                 for c in self.criteria_results],
            "evaluated_at": self.evaluated_at,
            "evaluator_version": self.evaluator_version,
            "policy_version": self.policy_version,
        }


def _criterion(cid: str, status: str, severity: str, message: str,
               refs: list[str] | None = None) -> CriterionResult:
    return CriterionResult(criterion_id=cid, status=status,
                           severity=severity, message=message,
                           affected_refs=refs or [])


def _derive_trust(epistemic_status: str, verification_method: str,
                  verification_test_refs: list[str]) -> str:
    """P0-08：trust_level 按真实来源推导，Owner approval 本身 ≠ verified。

    - 有真实验证引用（verification_test_refs）+ 非 U → verified
      （工程验证证据存在）；
    - epistemic in (V, C, E)（有证据支撑/计算/外部验证）→ medium；
    - 其余（U/A 等）→ unverified。
    """
    if verification_test_refs and epistemic_status != "U":
        return "verified"
    if epistemic_status in ("V", "C", "E"):
        return "medium"
    return "unverified"


def _json(value: Any) -> str:
    import json
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _head_sha() -> str:
    """当前 git HEAD（product truth 提交锚点；非 git 环境 → 'unknown'）。"""
    try:
        import subprocess
        return subprocess.run(["git", "rev-parse", "HEAD"],
                              capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:  # noqa: BLE001 - 非 git 环境诚实标注
        return "unknown"


class GateCriteriaEvaluator:
    """逐条 criteria 的确定性评估（不含授权 / commit 语义）。"""

    def __init__(self, db: AIPDStateDB, tenant_id: str = "default",
                 project_id: str = "default") -> None:
        self._db = db
        self._tenant = tenant_id
        self._project = project_id
        self._pi = ProductIntelligenceService(db)
        self._ideas = IdeaService(db)
        self._graph = EvidenceGraph(db)
        self._lineage = LineageService(db)
        self._snapshots = ProductDefinitionSnapshotService(db)

    # ------------------------------------------------------------- criteria
    def _crit_idea(self) -> CriterionResult:
        ideas = self._ideas.list(self._tenant, self._project)
        if not ideas:
            return _criterion(CRITERION_IDEA_MATURITY, CRIT_FAIL, SEV_HARD,
                              "no canonical Idea exists")
        idea = ideas[-1]
        maturity = IdeaMaturity.evaluate(idea, self._graph)
        # 按枚举声明顺序比较成熟度（此前用字符串 "<" 依赖字典序，脆弱）
        order = list(IdeaMaturity)
        below_i2 = (maturity in order
                    and order.index(maturity)
                    < order.index(IdeaMaturity.I2_EVIDENCE_BACKED_IDEA))
        if below_i2:
            return _criterion(
                CRITERION_IDEA_MATURITY, CRIT_FAIL, SEV_HARD,
                f"Idea maturity {maturity.value} < I2: "
                f"{IdeaMaturity.gap_reasons(idea, self._graph)}",
                [idea.idea_id])
        return _criterion(CRITERION_IDEA_MATURITY, CRIT_PASS, SEV_HARD,
                          f"Idea maturity {maturity.value} >= I2",
                          [idea.idea_id])

    def _crit_assessments(self) -> CriterionResult:
        ideas = self._ideas.list(self._tenant, self._project)
        if not ideas:
            return _criterion(CRITERION_KEY_CLAIM_ASSESSMENT, CRIT_FAIL,
                              SEV_HARD, "no Idea to assess")
        idea = ideas[-1]
        data = self._graph.compute_idea_evidence(self._tenant, self._project,
                                                 idea.idea_id)
        not_searched = data["counts"]["not_searched_claims"]
        if not_searched:
            return _criterion(
                CRITERION_KEY_CLAIM_ASSESSMENT, CRIT_FAIL, SEV_HARD,
                f"{not_searched} claim(s) not searched/assessed",
                [idea.idea_id])
        return _criterion(CRITERION_KEY_CLAIM_ASSESSMENT, CRIT_PASS, SEV_HARD,
                          "all key claims assessed")

    def _crit_contradictions(self) -> CriterionResult:
        """P0-01：0 contradiction → INFO（不是 blocker）；>0 → 按
        criticality/review/waiver 分类（有隐藏 contradiction 时 conditional）。"""
        ideas = self._ideas.list(self._tenant, self._project)
        if not ideas:
            return _criterion(CRITERION_CRITICAL_CONTRADICTIONS, CRIT_INFO,
                              SEV_INFO, "no Idea; contradiction check n/a")
        idea = ideas[-1]
        data = self._graph.compute_idea_evidence(self._tenant, self._project,
                                                 idea.idea_id)
        contradicted = data["counts"]["contradicted"]
        if contradicted == 0:
            return _criterion(CRITERION_CRITICAL_CONTRADICTIONS, CRIT_PASS,
                              SEV_INFO,
                              "no contradicted claims (nothing hidden)")
        return _criterion(
            CRITERION_CRITICAL_CONTRADICTIONS, CRIT_CONDITIONAL,
            SEV_CONDITIONAL,
            f"{contradicted} contradicted claim(s) listed in projection; "
            "review required (diagnostic, not unconditional blocker)",
            [idea.idea_id])

    def _crit_opportunity(self, view: ProductDefinitionSnapshotView) -> CriterionResult:
        """§10/46：只读 snapshot view（不读 live）。"""
        sel = view.opportunity()
        if sel is None:
            return _criterion(CRITERION_SELECTED_OPPORTUNITY, CRIT_FAIL,
                              SEV_HARD,
                              "snapshot has no selected Opportunity "
                              "(selection_status=selected required)")
        return _criterion(CRITERION_SELECTED_OPPORTUNITY, CRIT_PASS, SEV_HARD,
                          f"selected Opportunity {sel.opportunity_id}",
                          [sel.opportunity_id])

    def _crit_principles_bound(self,
                               view: ProductDefinitionSnapshotView) -> CriterionResult:
        """§11/46 PRINCIPLES_BOUND_TO_SELECTED_OPPORTUNITY：全部 snapshot
        principle.opportunity_id == snapshot.selected_opportunity_id。"""
        sel_id = view.snap.opportunity_id
        unbound = [p.principle_id for p in view.principles()
                   if not sel_id or p.opportunity_id != sel_id]
        if unbound:
            return _criterion(
                CRITERION_PRINCIPLES_BOUND, CRIT_FAIL, SEV_HARD,
                f"{len(unbound)} principle(s) not bound to selected "
                f"Opportunity {sel_id}", unbound)
        return _criterion(CRITERION_PRINCIPLES_BOUND, CRIT_PASS, SEV_HARD,
                          "all principles bound to selected opportunity")

    def _crit_principles(self, view: ProductDefinitionSnapshotView) -> CriterionResult:
        prins = view.principles()
        if not prins:
            return _criterion(CRITERION_PRINCIPLES_PRESENT, CRIT_FAIL,
                              SEV_HARD, "no Product Principles in snapshot")
        return _criterion(CRITERION_PRINCIPLES_PRESENT, CRIT_PASS, SEV_HARD,
                          f"{len(prins)} principle(s) in snapshot")

    def _crit_requirement_lineage(self,
                                  view: ProductDefinitionSnapshotView) -> CriterionResult:
        lineage = view.lineage()
        missing = []
        for req in view.requirements():
            edges = lineage.outgoing(
                LineageNodeRef(NODE_REQUIREMENT, req.requirement_id,
                               self._tenant, self._project))
            if not any(e.target.node_type == NODE_PRINCIPLE for e in edges):
                missing.append(req.requirement_id)
        if missing:
            return _criterion(CRITERION_REQUIREMENT_TRACEABILITY, CRIT_FAIL,
                              SEV_HARD,
                              f"{len(missing)} requirement(s) missing "
                              "Principle upstream", missing)
        return _criterion(CRITERION_REQUIREMENT_TRACEABILITY, CRIT_PASS,
                          SEV_HARD, "all requirements trace to principles")

    def _crit_feature_lineage(self,
                              view: ProductDefinitionSnapshotView) -> CriterionResult:
        lineage = view.lineage()
        missing = []
        for feat in view.features():
            edges = lineage.outgoing(
                LineageNodeRef(NODE_FEATURE, feat.feature_id,
                               self._tenant, self._project))
            if not any(e.target.node_type == NODE_REQUIREMENT for e in edges):
                missing.append(feat.feature_id)
        if missing:
            return _criterion(CRITERION_FEATURE_TRACEABILITY, CRIT_FAIL,
                              SEV_HARD,
                              f"{len(missing)} feature(s) missing Requirement "
                              "upstream", missing)
        return _criterion(CRITERION_FEATURE_TRACEABILITY, CRIT_PASS, SEV_HARD,
                          "all features trace to requirements")

    def _crit_critical_requirements(
            self, view: ProductDefinitionSnapshotView) -> list[CriterionResult]:
        reqs = [r for r in view.requirements()
                if r.criticality == CRITICALITY_CRITICAL]
        missing_source = [r.requirement_id for r in reqs
                          if not r.source_principle_ids]
        missing_verification = [r.requirement_id for r in reqs
                                if not (r.verification_method
                                        or r.verification_test_refs)]
        # 两条独立 criterion（§46 CRITICAL_REQUIREMENT_SOURCE /
        # CRITICAL_REQUIREMENT_VERIFICATION）→ 返回列表由调用方展开
        results: list[CriterionResult] = []
        if missing_source:
            results.append(_criterion(
                CRITERION_CRITICAL_REQUIREMENT_SOURCE, CRIT_FAIL, SEV_HARD,
                f"{len(missing_source)} critical requirement(s) missing "
                "source principle", missing_source))
        else:
            results.append(_criterion(CRITERION_CRITICAL_REQUIREMENT_SOURCE,
                                      CRIT_PASS, SEV_HARD,
                                      "all critical requirements have source"))
        if missing_verification:
            results.append(_criterion(
                CRITERION_CRITICAL_REQUIREMENT_VERIFICATION, CRIT_FAIL,
                SEV_HARD,
                f"{len(missing_verification)} critical requirement(s) missing "
                "verification path", missing_verification))
        else:
            results.append(_criterion(
                CRITERION_CRITICAL_REQUIREMENT_VERIFICATION, CRIT_PASS,
                SEV_HARD, "all critical requirements have verification path"))
        return results

    def _crit_unknowns(self, view: ProductDefinitionSnapshotView) -> CriterionResult:
        """critical unknown：无 waiver → CONDITIONAL（可 waiver）；带
        required_by_gate（waiver 标记）→ WARN。"""
        reqs = [r for r in view.requirements()
                if r.criticality == CRITICALITY_CRITICAL
                and r.epistemic_status == "U"]
        if not reqs:
            return _criterion(CRITERION_CRITICAL_UNKNOWN, CRIT_PASS, SEV_HARD,
                              "no critical unknowns")
        waived = [r.requirement_id for r in reqs if r.required_by_gate]
        unwaived = [r.requirement_id for r in reqs if not r.required_by_gate]
        if unwaived:
            return _criterion(
                CRITERION_CRITICAL_UNKNOWN, CRIT_CONDITIONAL,
                SEV_CONDITIONAL,
                f"{len(unwaived)} critical unknown(s) without explicit waiver "
                "(approve_with_waiver required)", unwaived)
        return _criterion(CRITERION_CRITICAL_UNKNOWN, CRIT_WARN, SEV_WARNING,
                          f"{len(waived)} critical unknown(s) waived "
                          "(required_by_gate set)", waived)

    def _crit_conflicts(self, view: ProductDefinitionSnapshotView) -> CriterionResult:
        reqs = [r for r in view.requirements()
                if r.definition_status == DEFINITION_STATUS_CONFLICT]
        critical = [r.requirement_id for r in reqs
                    if r.criticality == CRITICALITY_CRITICAL]
        if critical:
            return _criterion(CRITERION_CRITICAL_CONFLICT, CRIT_FAIL,
                              SEV_HARD,
                              f"{len(critical)} critical requirement(s) in "
                              "CONFLICT", critical)
        if reqs:
            return _criterion(CRITERION_CRITICAL_CONFLICT, CRIT_WARN,
                              SEV_WARNING,
                              f"{len(reqs)} non-critical requirement(s) in "
                              "CONFLICT (diagnostic)",
                              [r.requirement_id for r in reqs])
        return _criterion(CRITERION_CRITICAL_CONFLICT, CRIT_PASS, SEV_HARD,
                          "no conflicts")

    def _crit_set_integrity(
            self, view: ProductDefinitionSnapshotView) -> CriterionResult:
        """§46 SNAPSHOT_SET_INTEGRITY：refs 与解析对象一致。"""
        problems = view.set_integrity()
        if problems:
            return _criterion(CRITERION_SNAPSHOT_SET_INTEGRITY, CRIT_FAIL,
                              SEV_HARD, "; ".join(problems),
                              [view.snap.snapshot_id])
        return _criterion(CRITERION_SNAPSHOT_SET_INTEGRITY, CRIT_PASS,
                          SEV_HARD, "snapshot refs fully resolved")

    def _crit_upstream_basis(self, snap: ProductDefinitionSnapshot) -> CriterionResult:
        """§35/46 SNAPSHOT_UPSTREAM_BASIS：upstream lineage basis 变化 →
        需重冻结（第二道防线）。"""
        if not snap.upstream_basis_hash:
            return _criterion(CRITERION_SNAPSHOT_UPSTREAM_BASIS, CRIT_WARN,
                              SEV_WARNING,
                              "snapshot has no upstream_basis_hash (legacy); "
                              "re-freeze to enable basis protection")
        from .snapshot import active_definition_set, compute_upstream_basis
        try:
            active = active_definition_set(self._pi, self._tenant,
                                           self._project)
        except ValueError as exc:
            return _criterion(CRITERION_SNAPSHOT_UPSTREAM_BASIS, CRIT_FAIL,
                              SEV_HARD, f"active set invalid: {exc}",
                              [snap.snapshot_id])
        active["_pi"] = self._pi
        ideas = self._ideas.list(self._tenant, self._project)
        idea_id = ideas[-1].idea_id if ideas else ""
        current = compute_upstream_basis(self._db, idea_id, self._tenant,
                                         self._project, active)
        if current != snap.upstream_basis_hash:
            return _criterion(CRITERION_SNAPSHOT_UPSTREAM_BASIS, CRIT_FAIL,
                              SEV_HARD,
                              "upstream basis changed (claim/relation/"
                              "insight lineage); re-freeze snapshot",
                              [snap.snapshot_id])
        return _criterion(CRITERION_SNAPSHOT_UPSTREAM_BASIS, CRIT_PASS,
                          SEV_HARD, "upstream basis unchanged")

    def _crit_snapshot_freshness(self, snap: ProductDefinitionSnapshot) -> CriterionResult:
        stale, reasons = self._snapshots.is_stale(snap, self._tenant,
                                                  self._project)
        if stale:
            return _criterion(CRITERION_SNAPSHOT_FRESHNESS, CRIT_FAIL,
                              SEV_HARD,
                              f"snapshot {snap.snapshot_id} is STALE: "
                              f"{'; '.join(reasons)}", [snap.snapshot_id])
        if not snap.verify_hash():
            return _criterion(CRITERION_SNAPSHOT_FRESHNESS, CRIT_FAIL,
                              SEV_HARD,
                              f"snapshot {snap.snapshot_id} content_hash "
                              "does not match content (integrity breach)",
                              [snap.snapshot_id])
        return _criterion(CRITERION_SNAPSHOT_FRESHNESS, CRIT_PASS, SEV_HARD,
                          f"snapshot {snap.snapshot_id} fresh "
                          f"(hash {snap.content_hash[:12]}…)",
                          [snap.snapshot_id])

    # ------------------------------------------------------------- evaluate
    def criteria_results(self, snap: ProductDefinitionSnapshot) -> list[CriterionResult]:
        """对具体 snapshot 逐条评估全部 criteria（§10 只读 snapshot view）。"""
        view = ProductDefinitionSnapshotView(self._db, snap)
        results: list[CriterionResult] = [
            self._crit_idea(),
            self._crit_assessments(),
            self._crit_contradictions(),
            self._crit_opportunity(view),
            self._crit_principles(view),
            self._crit_principles_bound(view),
            self._crit_requirement_lineage(view),
            self._crit_feature_lineage(view),
        ]
        results.extend(self._crit_critical_requirements(view))
        results.append(self._crit_unknowns(view))
        results.append(self._crit_conflicts(view))
        results.append(self._crit_set_integrity(view))
        results.append(self._crit_upstream_basis(snap))
        results.append(self._crit_snapshot_freshness(snap))
        return results


__all__ = [
    "GateCriteriaEvaluator",
    "CriterionResult",
    "GateEvaluation",
    "DEFINITION_STATUS_CONFLICT",
    "GATE_POLICY_VERSION",
    "GATE_EVALUATOR_VERSION",
    "CRITERION_IDEA_MATURITY", "CRITERION_KEY_CLAIM_ASSESSMENT",
    "CRITERION_CRITICAL_CONTRADICTIONS", "CRITERION_SELECTED_OPPORTUNITY",
    "CRITERION_PRINCIPLES_PRESENT", "CRITERION_REQUIREMENT_TRACEABILITY",
    "CRITERION_FEATURE_TRACEABILITY", "CRITERION_CRITICAL_REQUIREMENT_SOURCE",
    "CRITERION_CRITICAL_REQUIREMENT_VERIFICATION", "CRITERION_CRITICAL_UNKNOWN",
    "CRITERION_CRITICAL_CONFLICT", "CRITERION_PRINCIPLES_BOUND",
    "CRITERION_SNAPSHOT_SET_INTEGRITY", "CRITERION_SNAPSHOT_UPSTREAM_BASIS",
    "CRITERION_SNAPSHOT_FRESHNESS", "CRITERION_OWNER_DECISION",
    "CRITERION_CONDITIONAL_WAIVER",
    "CRIT_PASS", "CRIT_FAIL", "CRIT_CONDITIONAL", "CRIT_WARN", "CRIT_INFO",
    "SEV_HARD", "SEV_CONDITIONAL", "SEV_WARNING", "SEV_INFO",
    "_criterion", "_derive_trust", "_json", "_head_sha",
]
