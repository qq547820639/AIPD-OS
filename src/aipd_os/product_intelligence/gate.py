"""Product Definition Gate（v5.9.1 重构，§46-48/57）。

**分层**（§47 推荐）：
1. **Technical Gate**（deterministic，无 LLM）：READY / CONDITIONAL / BLOCKED；
2. **Authorization**（Owner Decision）：APPROVED / REJECTED / PENDING /
   APPROVED_WITH_WAIVER —— 绑定确切 snapshot（id + content_hash）；
3. **Commit Eligibility**：technical READY+APPROVED，或 technical
   CONDITIONAL+APPROVED_WITH_WAIVER；BLOCKED 永不 commit。

**结构化输出**（P0-01）：:class:`GateEvaluation` 含
``hard_blockers / conditional_blockers / warnings / information`` +
``criteria_results``（每条 criterion_id/status/severity/message/affected_refs）。
**0 contradiction 是 information，不是 blocker**；contradiction > 0 按
criticality/review/waiver 分类为 conditional 或 warning。

**Snapshot 输入**（P0-02/48）：Gate 评估对象是 immutable
:class:`ProductDefinitionSnapshot`（含 content_hash）。历史 approve 不自动
授权任何 snapshot；授权必须绑定同一 snapshot_id + content_hash
（:meth:`get_effective_decision`，最新 resolved 为准，P0-03）。

**Commit**（P0-04/08/29）：:meth:`commit_snapshot` 提交 **snapshot refs 的
exact versions**（不重查 live tables）；snapshot stale → 拒绝并要求新
snapshot；CONDITIONAL 无 waiver → 拒绝；ProductTruth trust_level 按真实
来源推导（Owner approval ≠ verified）。

**兼容**：:meth:`evaluate` / :meth:`commit_approved` 保留（评估 live
view 的确定性结果；commit_approved 走新语义）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aipd_os.idea.evidence_graph import EvidenceGraph
from aipd_os.idea.maturity import IdeaMaturity
from aipd_os.idea.service import IdeaService
from aipd_os.state.db import AIPDStateDB, now_iso
from aipd_os.state.lineage import LineageNodeRef, LineageService

from .models import (
    CRITICALITY_CRITICAL,
    LIFECYCLE_ARCHIVED,
)
from .service import (
    NODE_FEATURE,
    NODE_PRINCIPLE,
    NODE_REQUIREMENT,
    ProductIntelligenceService,
)
from .snapshot import (
    SNAPSHOT_STALE,
    ProductDefinitionSnapshot,
    ProductDefinitionSnapshotService,
)

# definition_status=CONFLICT（critical requirement 冲突检测）
DEFINITION_STATUS_CONFLICT = "CONFLICT"

# ---------------------------------------------------------------------------
# Gate 结果 / criteria
# ---------------------------------------------------------------------------
GATE_READY = "READY"
GATE_CONDITIONAL = "CONDITIONAL"
GATE_BLOCKED = "BLOCKED"

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

# Owner Decision topic（复用 canonical decisions 表）
GATE_DECISION_TOPIC = "product_definition_gate"
GATE_CHOICE_APPROVE = "approve"
GATE_CHOICE_REJECT = "reject"
GATE_CHOICE_REQUEST_REVISION = "request_revision"
GATE_CHOICE_APPROVE_WITH_WAIVER = "approve_with_waiver"
OWNER_CHOICES = frozenset({GATE_CHOICE_APPROVE, GATE_CHOICE_REJECT,
                           GATE_CHOICE_REQUEST_REVISION,
                           GATE_CHOICE_APPROVE_WITH_WAIVER})

# authorization states
AUTH_APPROVED = "APPROVED"
AUTH_REJECTED = "REJECTED"
AUTH_PENDING = "PENDING"
AUTH_APPROVED_WITH_WAIVER = "APPROVED_WITH_WAIVER"

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


class ProductDefinitionGate:
    """确定性 Product Definition Gate（技术评估 + 授权 + 提交资格）。"""

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
        if maturity.value < "I2":
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

    def _crit_opportunity(self) -> CriterionResult:
        """P0-07：显式 selection_status=selected；恰好 1 个非 archived。"""
        sel = [o for o in self._pi.list_opportunities(self._tenant,
                                                      self._project)
               if o.lifecycle_status != LIFECYCLE_ARCHIVED
               and o.selection_status == "selected"]
        if not sel:
            return _criterion(CRITERION_SELECTED_OPPORTUNITY, CRIT_FAIL,
                              SEV_HARD,
                              "no selected Opportunity (selection_status="
                              "selected required)")
        if len(sel) > 1:
            return _criterion(
                CRITERION_SELECTED_OPPORTUNITY, CRIT_FAIL, SEV_HARD,
                f"multiple selected Opportunities "
                f"({[o.opportunity_id for o in sel]}); exactly one required",
                [o.opportunity_id for o in sel])
        return _criterion(CRITERION_SELECTED_OPPORTUNITY, CRIT_PASS, SEV_HARD,
                          f"selected Opportunity {sel[0].opportunity_id}",
                          [sel[0].opportunity_id])

    def _crit_principles(self) -> CriterionResult:
        prins = [p for p in self._pi.list_principles(self._tenant,
                                                     self._project)
                 if p.lifecycle_status != LIFECYCLE_ARCHIVED]
        if not prins:
            return _criterion(CRITERION_PRINCIPLES_PRESENT, CRIT_FAIL,
                              SEV_HARD, "no Product Principles exist")
        return _criterion(CRITERION_PRINCIPLES_PRESENT, CRIT_PASS, SEV_HARD,
                          f"{len(prins)} principle(s) present")

    def _crit_requirement_lineage(self) -> CriterionResult:
        reqs = [r for r in self._pi.list_requirements(self._tenant,
                                                      self._project)
                if r.lifecycle_status != LIFECYCLE_ARCHIVED]
        missing = []
        for req in reqs:
            edges = self._lineage.outgoing(
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

    def _crit_feature_lineage(self) -> CriterionResult:
        feats = [f for f in self._pi.list_features(self._tenant,
                                                   self._project)
                 if f.lifecycle_status != LIFECYCLE_ARCHIVED]
        missing = []
        for feat in feats:
            edges = self._lineage.outgoing(
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

    def _crit_critical_requirements(self) -> list[CriterionResult]:
        reqs = [r for r in self._pi.list_requirements(self._tenant,
                                                      self._project)
                if r.lifecycle_status != LIFECYCLE_ARCHIVED
                and r.criticality == CRITICALITY_CRITICAL]
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

    def _crit_unknowns(self) -> CriterionResult:
        """critical unknown：无 waiver → CONDITIONAL（可 waiver）；带
        required_by_gate（waiver 标记）→ WARN。"""
        reqs = [r for r in self._pi.list_requirements(self._tenant,
                                                      self._project)
                if r.lifecycle_status != LIFECYCLE_ARCHIVED
                and r.criticality == CRITICALITY_CRITICAL
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

    def _crit_conflicts(self) -> CriterionResult:
        reqs = [r for r in self._pi.list_requirements(self._tenant,
                                                      self._project)
                if r.lifecycle_status != LIFECYCLE_ARCHIVED
                and r.definition_status == DEFINITION_STATUS_CONFLICT]
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
    def evaluate_snapshot(self, snap: ProductDefinitionSnapshot) -> GateEvaluation:
        """对**具体 snapshot** 做技术评估（§48：Gate 输入明确，不推断）。"""
        results: list[CriterionResult] = [
            self._crit_idea(),
            self._crit_assessments(),
            self._crit_contradictions(),
            self._crit_opportunity(),
            self._crit_principles(),
            self._crit_requirement_lineage(),
            self._crit_feature_lineage(),
        ]
        results.extend(self._crit_critical_requirements())
        results.append(self._crit_unknowns())
        results.append(self._crit_conflicts())
        results.append(self._crit_snapshot_freshness(snap))

        hard = [c for c in results if c.severity == SEV_HARD
                and c.status == CRIT_FAIL]
        conditional = [c for c in results
                       if c.severity == SEV_CONDITIONAL
                       and c.status in (CRIT_CONDITIONAL, CRIT_FAIL)]
        warnings = [c for c in results if c.severity == SEV_WARNING]
        information = [c for c in results if c.severity == SEV_INFO]

        if hard:
            result = GATE_BLOCKED
        elif conditional:
            result = GATE_CONDITIONAL
        else:
            result = GATE_READY

        return GateEvaluation(
            evaluation_id=self._db.next_sequence("gate_evaluation", "GEV"),
            tenant_id=self._tenant, project_id=self._project,
            snapshot_id=snap.snapshot_id, snapshot_hash=snap.content_hash,
            result=result,
            hard_blockers=[c.message for c in hard],
            conditional_blockers=[c.message for c in conditional],
            warnings=[c.message for c in warnings],
            information=[c.message for c in information],
            criteria_results=results,
            evaluated_at=now_iso())

    def evaluate(self, snapshot_id: str | None = None) -> dict[str, Any]:
        """兼容入口：评估指定（或最新）snapshot。返回 GateEvaluation dict。"""
        if snapshot_id is None:
            snap = self._snapshots.latest_snapshot(self._tenant, self._project)
            if snap is None:
                raise ValueError(
                    "no ProductDefinitionSnapshot exists; create one via "
                    "create_snapshot() before gate evaluation (P0-48)")
            snapshot_id = snap.snapshot_id
        snap = self._snapshots.get_snapshot(self._tenant, self._project,
                                            snapshot_id)
        return self.evaluate_snapshot(snap).to_dict()

    def record_gate(self, actor: str = "system",
                    snapshot_id: str | None = None) -> dict[str, Any]:
        """把 Gate 结果写入 gates 表（auditable）+ gate_evaluations 表。"""
        if snapshot_id is None:
            latest = self._snapshots.latest_snapshot(self._tenant,
                                                     self._project)
            if latest is None:
                raise ValueError(
                    "no ProductDefinitionSnapshot; create_snapshot() first")
            snapshot_id = latest.snapshot_id
        evaluation = self.evaluate_snapshot(
            self._snapshots.get_snapshot(self._tenant, self._project,
                                         snapshot_id))
        with self._db.transaction() as c:
            c.execute(
                "INSERT INTO gate_evaluations(evaluation_id,project_id,"
                "tenant_id,snapshot_id,snapshot_hash,result,"
                "hard_blockers_json,conditional_blockers_json,warnings_json,"
                "information_json,criteria_results_json,evaluated_at,"
                "evaluator_version,policy_version) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (evaluation.evaluation_id, evaluation.project_id,
                 evaluation.tenant_id, evaluation.snapshot_id,
                 evaluation.snapshot_hash, evaluation.result,
                 _json(evaluation.hard_blockers),
                 _json(evaluation.conditional_blockers),
                 _json(evaluation.warnings), _json(evaluation.information),
                 _json([c.to_dict() for c in evaluation.criteria_results]),
                 evaluation.evaluated_at, evaluation.evaluator_version,
                 evaluation.policy_version))
            self._db.add_audit(
                actor, "product_definition_gate.evaluate",
                evaluation.project_id, evaluation.tenant_id,
                after=evaluation.to_dict())
        return evaluation.to_dict()

    # ------------------------------------------------------------- owner
    def propose_owner_decision(self, recommendation: str = "",
                               actor: str = "system",
                               snapshot_id: str | None = None,
                               gate_evaluation_id: str = "") -> str:
        """创建 Owner Decision（绑定 snapshot + hash + evaluation）。"""
        if snapshot_id is None:
            latest = self._snapshots.latest_snapshot(self._tenant,
                                                     self._project)
            if latest is None:
                raise ValueError(
                    "no ProductDefinitionSnapshot; create_snapshot() first "
                    "(Owner Decision must bind an exact snapshot, P0-02)")
            snapshot_id = latest.snapshot_id
        snap = self._snapshots.get_snapshot(self._tenant, self._project,
                                            snapshot_id)
        return self._db.propose_decision(
            self._tenant, self._project, topic=GATE_DECISION_TOPIC,
            recommendation=recommendation or (
                "Approve to commit approved Product Definition Snapshot "
                f"{snap.snapshot_id} to Product Truth; reject/request_revision "
                "to keep EXPLORE state"),
            options=[GATE_CHOICE_APPROVE, GATE_CHOICE_REJECT,
                     GATE_CHOICE_REQUEST_REVISION,
                     GATE_CHOICE_APPROVE_WITH_WAIVER],
            trigger=f"{GATE_DECISION_TOPIC}:{self._project}",
            metadata={
                "snapshot_id": snap.snapshot_id,
                "snapshot_hash": snap.content_hash,
                "gate_evaluation_id": gate_evaluation_id,
                "decision_version": 1,
            })

    def resolve_owner_decision(self, decision_id: str, choice: str,
                               comment: str = "",
                               actor: str = "system",
                               waiver: dict[str, Any] | None = None) -> dict[str, Any]:
        """Owner 显式裁定。approve_with_waiver 需 waiver 记录
        （accepted_conditions/accepted_risks/owner/decision_id/snapshot_id/
        expires_if_changed/created_at，P0-04）。"""
        if choice not in OWNER_CHOICES:
            raise ValueError(f"invalid gate choice {choice!r}; expected one of "
                             f"{sorted(OWNER_CHOICES)}")
        decisions = self._db.list_decisions(self._tenant, self._project)
        decision = next((d for d in decisions if d["decision_id"] == decision_id),
                        None)
        if decision is None:
            raise KeyError(decision_id)
        metadata = dict(decision.get("metadata") or {})
        snap_id = metadata.get("snapshot_id")
        if choice == GATE_CHOICE_APPROVE_WITH_WAIVER:
            if not waiver:
                raise ValueError(
                    "approve_with_waiver requires explicit waiver "
                    "(accepted_conditions/accepted_risks/owner)")
            metadata["waiver"] = {
                **waiver,
                "decision_id": decision_id,
                "snapshot_id": snap_id,
                "created_at": now_iso(),
                "expires_if_changed": waiver.get("expires_if_changed", True),
            }
        with self._db.transaction() as c:
            c.execute(
                "UPDATE decisions SET status='resolved',choice=?,comment=?,"
                "resolved_at=?,version_no=version_no+1,metadata_json=? "
                "WHERE tenant_id=? AND project_id=? AND decision_id=?",
                (choice, comment or None, now_iso(), _json(metadata),
                 self._tenant, self._project, decision_id))
            open_count = c.execute(
                "SELECT COUNT(*) FROM decisions WHERE tenant_id=? AND "
                "project_id=? AND status='proposed'",
                (self._tenant, self._project)).fetchone()[0]
            new_status = "awaiting_owner_decision" if open_count else "active"
            c.execute("UPDATE projects SET status=?,updated_at=? "
                      "WHERE tenant_id=? AND project_id=?",
                      (new_status, now_iso(), self._tenant, self._project))
            self._db.add_audit(actor, "product_definition_gate.resolve",
                               self._project, self._tenant,
                               after={"decision_id": decision_id,
                                      "choice": choice,
                                      "snapshot_id": snap_id})
        return {"decision_id": decision_id, "choice": choice,
                "comment": comment, "snapshot_id": snap_id,
                "waiver": metadata.get("waiver"),
                "resolved_at": now_iso()}

    def get_effective_decision(self, snapshot_id: str) -> dict[str, Any] | None:
        """P0-03：该 snapshot 的最新 resolved decision（deterministic
        projection：resolved_at desc / version desc / created_at desc）。
        历史 decision 保留（不删除）；无 mutable boolean。"""
        decisions = self._db.list_decisions(self._tenant, self._project)
        bound = [d for d in decisions
                 if d["topic"] == GATE_DECISION_TOPIC
                 and d["status"] == "resolved"
                 and (d.get("metadata") or {}).get("snapshot_id") == snapshot_id]
        if not bound:
            return None
        bound.sort(key=lambda d: (
            d.get("resolved_at") or "", int(d.get("version_no", 1)),
            d.get("created_at") or ""))
        return bound[-1]

    def authorization_status(self, snapshot_id: str) -> dict[str, Any]:
        """Authorization 层（§47）：APPROVED / REJECTED / PENDING /
        APPROVED_WITH_WAIVER。"""
        effective = self.get_effective_decision(snapshot_id)
        if effective is None:
            return {"state": AUTH_PENDING, "decision_id": None,
                    "choice": None, "waiver": None}
        choice = effective["choice"]
        if choice == GATE_CHOICE_APPROVE_WITH_WAIVER:
            state = AUTH_APPROVED_WITH_WAIVER
        elif choice == GATE_CHOICE_APPROVE:
            state = AUTH_APPROVED
        elif choice == GATE_CHOICE_REJECT:
            state = AUTH_REJECTED
        else:
            state = AUTH_PENDING
        return {"state": state, "decision_id": effective["decision_id"],
                "choice": choice,
                "waiver": (effective.get("metadata") or {}).get("waiver")}

    def commit_eligibility(self, evaluation: GateEvaluation,
                           authorization: dict[str, Any]) -> dict[str, Any]:
        """Final Commit Eligibility（§47/62）：
        READY+APPROVED → YES；CONDITIONAL+APPROVED_WITH_WAIVER → YES；
        其余 → NO（含 reason）。BLOCKED 永不 commit。"""
        tech = evaluation.result
        auth = authorization["state"]
        if tech == GATE_BLOCKED:
            return {"eligible": False, "reason": "technical gate BLOCKED"}
        if auth in (AUTH_REJECTED,):
            return {"eligible": False, "reason": "owner REJECTED"}
        if auth == AUTH_PENDING:
            return {"eligible": False, "reason": "owner decision PENDING"}
        if tech == GATE_READY and auth == AUTH_APPROVED:
            return {"eligible": True, "reason": "READY + APPROVED"}
        if tech == GATE_CONDITIONAL and auth == AUTH_APPROVED_WITH_WAIVER:
            return {"eligible": True,
                    "reason": "CONDITIONAL + APPROVE_WITH_WAIVER (waiver "
                              "recorded)"}
        return {"eligible": False,
                "reason": f"{tech} requires explicit "
                          f"{'APPROVE' if tech == GATE_READY else 'APPROVE_WITH_WAIVER'}"}

    def owner_decision_status(self) -> dict[str, Any]:
        """当前 Owner 决策概览（owner UX）。"""
        decisions = self._db.list_decisions(self._tenant, self._project)
        gate_decisions = [d for d in decisions
                          if d["topic"] == GATE_DECISION_TOPIC]
        return {
            "pending": [d for d in gate_decisions if d["status"] == "proposed"],
            "resolved": [d for d in gate_decisions
                         if d["status"] == "resolved"],
            "latest_approved": any(
                d["status"] == "resolved" and d["choice"] in (
                    GATE_CHOICE_APPROVE, GATE_CHOICE_APPROVE_WITH_WAIVER)
                for d in gate_decisions),
        }

    # ------------------------------------------------------------- commit
    def commit_snapshot(self, snap: ProductDefinitionSnapshot,
                        actor: str = "system") -> dict[str, Any]:
        """P0-02/04/08/29：提交 **exact snapshot**（refs + versions）。

        1. snapshot 必须非 stale（变化 → 拒绝，要求新 snapshot 重评重批）；
        2. effective decision 必须绑定本 snapshot 且授权 commit；
        3. CONDITIONAL 必须显式 waiver；BLOCKED 永不 commit；
        4. ProductTruth trust_level 按真实来源推导（approval ≠ verified）；
        5. metadata 记录 approval_state/definition_status/source_snapshot_id/
           source_snapshot_hash/source_*_version/owner_decision_id。
        """
        from aipd_os.product_truth.lineage import LineageGraph
        from aipd_os.product_truth.models import SourceRef, TruthRecord
        from aipd_os.product_truth.store import ProductTruthStore

        stale, reasons = self._snapshots.is_stale(snap, self._tenant,
                                                  self._project)
        if stale:
            raise RuntimeError(
                f"snapshot {snap.snapshot_id} is STALE; create a new snapshot, "
                f"re-evaluate and re-approve: {'; '.join(reasons)}")
        if not snap.verify_hash():
            raise RuntimeError(
                f"snapshot {snap.snapshot_id} content_hash mismatch "
                "(integrity breach); refuse commit")

        evaluation = self.evaluate_snapshot(snap)
        authorization = self.authorization_status(snap.snapshot_id)
        eligibility = self.commit_eligibility(evaluation, authorization)
        if not eligibility["eligible"]:
            raise RuntimeError(
                f"cannot commit snapshot {snap.snapshot_id}: "
                f"{eligibility['reason']}")

        store = ProductTruthStore(str(self._db.path),
                                  tenant_id=self._tenant,
                                  project_id=self._project)
        graph = LineageGraph(store, tenant_id=self._tenant,
                             project_id=self._project,
                             canonical_db=self._db)
        committed: list[str] = []
        metadata_base = {
            "approval_state": "approved",
            "gate_approved": True,
            "definition_status": "approved",
            "source_snapshot_id": snap.snapshot_id,
            "source_snapshot_hash": snap.content_hash,
            "owner_decision_id": authorization["decision_id"],
            "owner_choice": authorization["choice"],
            "source_commit": _head_sha(),
        }
        if authorization["waiver"]:
            metadata_base["waiver"] = authorization["waiver"]

        # exact refs：不重查 live tables —— 提交 snapshot 冻结的版本
        for r in snap.requirement_refs:
            req = self._pi.get_requirement(self._tenant, self._project,
                                           r["id"])
            rid = store.add(TruthRecord(
                record_type="requirement",
                content=f"{req.title}: {req.statement}",
                source=SourceRef(
                    note=f"product_intelligence:{req.requirement_id}"),
                trust_level=_derive_trust(req.epistemic_status,
                                          req.verification_method,
                                          req.verification_test_refs),
                metadata={
                    **metadata_base,
                    "requirement_id": req.requirement_id,
                    "source_requirement_version": req.version_no,
                    "criticality": req.criticality,
                    "epistemic_status": req.epistemic_status,
                }))
            graph.add_edge(req.requirement_id, rid, relation="derived_from")
            committed.append(rid)
        for r in snap.feature_refs:
            feat = self._pi.get_feature(self._tenant, self._project, r["id"])
            fid = store.add(TruthRecord(
                record_type="feature",
                content=f"{feat.title}: {feat.description}",
                source=SourceRef(
                    note=f"product_intelligence:{feat.feature_id}"),
                trust_level=_derive_trust(feat.epistemic_status, "", []),
                metadata={
                    **metadata_base,
                    "feature_id": feat.feature_id,
                    "source_feature_version": feat.version_no,
                    "epistemic_status": feat.epistemic_status,
                }))
            graph.add_edge(feat.feature_id, fid, relation="derived_from")
            committed.append(fid)
        with self._db.transaction() as c:
            c.execute(
                "UPDATE product_definition_snapshots SET lifecycle_status=? "
                "WHERE snapshot_id=? AND project_id=? AND tenant_id=? "
                "AND lifecycle_status='frozen'",
                (SNAPSHOT_STALE, snap.snapshot_id, snap.project_id,
                 snap.tenant_id))
            self._db.add_audit(actor, "product_definition_gate.commit",
                               self._project, self._tenant,
                               after={"committed": committed,
                                      "snapshot_id": snap.snapshot_id,
                                      "snapshot_hash": snap.content_hash,
                                      "decision_id":
                                          authorization["decision_id"],
                                      "requirements": len(snap.requirement_refs),
                                      "features": len(snap.feature_refs)})
        return {"committed": committed,
                "requirements": len(snap.requirement_refs),
                "features": len(snap.feature_refs),
                "snapshot_id": snap.snapshot_id,
                "snapshot_hash": snap.content_hash,
                "decision_id": authorization["decision_id"],
                "gate": evaluation.result,
                "authorization": authorization["state"]}

    def commit_approved(self, actor: str = "system") -> dict[str, Any]:
        """兼容入口：最新 snapshot + 绑定决策 → commit_snapshot。

        旧语义（任意历史 approve 直接提交 live tables）已废弃 —— 新语义
        要求 snapshot 绑定（P0-02/29）。"""
        snap = self._snapshots.latest_snapshot(self._tenant, self._project)
        if snap is None:
            raise RuntimeError(
                "no snapshot; create_snapshot() then propose/resolve Owner "
                "Decision before commit (P0-02)")
        return self.commit_snapshot(snap, actor=actor)


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


__all__ = [
    "ProductDefinitionGate",
    "GateEvaluation",
    "CriterionResult",
    "GATE_READY", "GATE_CONDITIONAL", "GATE_BLOCKED",
    "GATE_DECISION_TOPIC",
    "GATE_CHOICE_APPROVE", "GATE_CHOICE_REJECT",
    "GATE_CHOICE_REQUEST_REVISION", "GATE_CHOICE_APPROVE_WITH_WAIVER",
    "OWNER_CHOICES",
    "AUTH_APPROVED", "AUTH_REJECTED", "AUTH_PENDING",
    "AUTH_APPROVED_WITH_WAIVER",
    "GATE_POLICY_VERSION", "GATE_EVALUATOR_VERSION",
    "CRITERION_IDEA_MATURITY", "CRITERION_KEY_CLAIM_ASSESSMENT",
    "CRITERION_CRITICAL_CONTRADICTIONS", "CRITERION_SELECTED_OPPORTUNITY",
    "CRITERION_PRINCIPLES_PRESENT", "CRITERION_REQUIREMENT_TRACEABILITY",
    "CRITERION_FEATURE_TRACEABILITY", "CRITERION_CRITICAL_REQUIREMENT_SOURCE",
    "CRITERION_CRITICAL_REQUIREMENT_VERIFICATION", "CRITERION_CRITICAL_UNKNOWN",
    "CRITERION_CRITICAL_CONFLICT", "CRITERION_SNAPSHOT_FRESHNESS",
    "CRITERION_OWNER_DECISION", "CRITERION_CONDITIONAL_WAIVER",
]
