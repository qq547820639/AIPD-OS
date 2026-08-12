"""Product Definition Gate（v5.9 核心 Gate，§49-53）。

- **Gate 前（EXPLORE/CREATE）**：允许 candidate Insight/Opportunity/
  Principle/Requirement/Feature（lifecycle=candidate）实验与替换；
- **Gate 后（COMMIT/ENGINEER）**：冻结 Target User/Problem/Core Value/
  Core Mechanism/Approved Principles/Requirements/Features，由 Product
  Truth + Engineering Baseline 接管。

:class:`ProductDefinitionGate` 是 **deterministic**：LLM 可以解释 Gate，
**不能决定 READY**。Gate 结果 = 确定性 criteria + canonical Owner Decision
（复用 decisions 表：topic=`product_definition_gate`，choice=approve/
reject/request_revision）。

输出：READY / CONDITIONAL / BLOCKED + blockers（可读原因列表）。

v5.8.2 Gate 规则（第一版确定性）：
1. canonical Idea 存在；
2. Idea maturity >= I2（required key claim coverage）；
3. critical ClaimAssessment 无 NOT_SEARCHED（关键命题全部评估）；
4. 无隐藏 contradiction（contradicted/unknown 显式进入 projection ——
   gate 校验 projection 中 contradicts 可见；不要求零 contradiction）；
5. selected Opportunity 存在（≥1 个非 archived）；
6. Product Principles 存在（≥1 个非 archived）；
7. 每个 active Requirement 有 Principle 上游（derived_from 边）；
8. 每个 active Feature 有 Requirement 上游（implements 边）；
9. critical Requirement 有 source（source_principle_ids 非空）；
10. critical Requirement 有 verification path（verification_method 非空）；
11. 无未解决 critical conflict（critical Requirement 无 definition_status=CONFLICT）；
12. 无未经 waiver 的 critical unknown（critical Requirement 的
    epistemic_status != U；U 时需 required_by_gate 携带 waiver 标记）；
13. Owner approval 存在（canonical Decision approve）。

:meth:`commit_approved`：Gate=READY + Owner approve 后，把 approved
Requirements/Features 写入 Product Truth（record_type=requirement/feature，
metadata.gate_approved=True，lineage product_truth 边）。**Gate 前禁止
Product Truth commit**（commit 入口强制校验 gate 记录）。
"""
from __future__ import annotations

from typing import Any

from aipd_os.idea.evidence_graph import EvidenceGraph
from aipd_os.idea.maturity import IdeaMaturity
from aipd_os.idea.service import IdeaService
from aipd_os.state.db import AIPDStateDB, now_iso
from aipd_os.state.lineage import LineageNodeRef, LineageService

from .models import (
    CRITICALITY_CRITICAL,
    LIFECYCLE_ACTIVE,
    LIFECYCLE_ARCHIVED,
)
from .service import (
    NODE_FEATURE,
    NODE_PRINCIPLE,
    NODE_REQUIREMENT,
    ProductIntelligenceService,
)

# definition_status=CONFLICT（critical requirement 冲突检测）
DEFINITION_STATUS_CONFLICT = "CONFLICT"

# Gate 结果
GATE_READY = "READY"
GATE_CONDITIONAL = "CONDITIONAL"
GATE_BLOCKED = "BLOCKED"

# Owner Decision topic（复用 canonical decisions 表）
GATE_DECISION_TOPIC = "product_definition_gate"
GATE_CHOICE_APPROVE = "approve"
GATE_CHOICE_REJECT = "reject"
GATE_CHOICE_REQUEST_REVISION = "request_revision"

# 允许的 owner choices
OWNER_CHOICES = frozenset({GATE_CHOICE_APPROVE, GATE_CHOICE_REJECT,
                           GATE_CHOICE_REQUEST_REVISION})


class ProductDefinitionGate:
    """确定性 Product Definition Gate（无 LLM 自批）。"""

    def __init__(self, db: AIPDStateDB, tenant_id: str = "default",
                 project_id: str = "default") -> None:
        self._db = db
        self._tenant = tenant_id
        self._project = project_id
        self._pi = ProductIntelligenceService(db)
        self._ideas = IdeaService(db)
        self._graph = EvidenceGraph(db)
        self._lineage = LineageService(db)

    # ------------------------------------------------------------- criteria
    def _check_idea(self) -> list[str]:
        blockers: list[str] = []
        ideas = self._ideas.list(self._tenant, self._project)
        if not ideas:
            blockers.append("no canonical Idea exists")
            return blockers
        idea = ideas[-1]
        maturity = IdeaMaturity.evaluate(idea, self._graph)
        if maturity.value < "I2":
            blockers.append(
                f"Idea maturity {maturity.value} < I2 (required key claim "
                f"coverage not complete): {IdeaMaturity.gap_reasons(idea, self._graph)}")
        return blockers

    def _check_assessments(self) -> list[str]:
        blockers: list[str] = []
        ideas = self._ideas.list(self._tenant, self._project)
        if not ideas:
            return blockers
        idea = ideas[-1]
        data = self._graph.compute_idea_evidence(self._tenant, self._project,
                                                 idea.idea_id)
        not_searched = data["counts"]["not_searched_claims"]
        if not_searched:
            blockers.append(
                f"{not_searched} claim(s) not searched/assessed "
                "(critical ClaimAssessment incomplete)")
        # 无隐藏 contradiction：projection 显式列出 contradicted claims
        contradicted = data["counts"]["contradicted"]
        blockers.append(
            f"explicit contradiction visibility: {contradicted} contradicted "
            "claim(s) listed in projection (no hidden contradiction)")
        return blockers

    def _check_opportunity_and_principles(self) -> list[str]:
        blockers: list[str] = []
        opps = [o for o in self._pi.list_opportunities(self._tenant,
                                                       self._project)
                if o.lifecycle_status != LIFECYCLE_ARCHIVED]
        if not opps:
            blockers.append("no selected Opportunity exists")
        prins = [p for p in self._pi.list_principles(self._tenant,
                                                     self._project)
                 if p.lifecycle_status != LIFECYCLE_ARCHIVED]
        if not prins:
            blockers.append("no Product Principles exist")
        return blockers

    def _check_requirement_lineage(self) -> list[str]:
        blockers: list[str] = []
        reqs = [r for r in self._pi.list_requirements(self._tenant,
                                                      self._project)
                if r.lifecycle_status != LIFECYCLE_ARCHIVED]
        for req in reqs:
            edges = self._lineage.outgoing(
                LineageNodeRef(NODE_REQUIREMENT, req.requirement_id,
                               self._tenant, self._project))
            if not any(e.target.node_type == NODE_PRINCIPLE
                       for e in edges):
                blockers.append(
                    f"{req.requirement_id} has no Principle upstream "
                    "(requirement must trace to a principle)")
        return blockers

    def _check_feature_lineage(self) -> list[str]:
        blockers: list[str] = []
        feats = [f for f in self._pi.list_features(self._tenant,
                                                   self._project)
                 if f.lifecycle_status != LIFECYCLE_ARCHIVED]
        for feat in feats:
            edges = self._lineage.outgoing(
                LineageNodeRef(NODE_FEATURE, feat.feature_id,
                               self._tenant, self._project))
            if not any(e.target.node_type == NODE_REQUIREMENT
                       for e in edges):
                blockers.append(
                    f"{feat.feature_id} has no Requirement upstream "
                    "(feature must trace to a requirement)")
        return blockers

    def _check_critical_requirements(self) -> list[str]:
        blockers: list[str] = []
        reqs = [r for r in self._pi.list_requirements(self._tenant,
                                                      self._project)
                if r.lifecycle_status != LIFECYCLE_ARCHIVED
                and r.criticality == CRITICALITY_CRITICAL]
        for req in reqs:
            if not req.source_principle_ids:
                blockers.append(
                    f"{req.requirement_id} critical: missing source principle")
            if not (req.verification_method or req.verification_test_refs):
                blockers.append(
                    f"{req.requirement_id} critical: missing verification path")
            if req.definition_status == DEFINITION_STATUS_CONFLICT:
                blockers.append(
                    f"{req.requirement_id} critical: unresolved conflict "
                    "(definition_status=CONFLICT)")
            if req.epistemic_status == "U" and not req.required_by_gate:
                blockers.append(
                    f"{req.requirement_id} critical: unknown without explicit "
                    "waiver (required_by_gate empty)")
        return blockers

    def _check_owner_approval(self) -> list[str]:
        blockers: list[str] = []
        decisions = self._db.list_decisions(self._tenant, self._project)
        approved = [d for d in decisions
                    if d["topic"] == GATE_DECISION_TOPIC
                    and d["status"] == "resolved"
                    and d["choice"] == GATE_CHOICE_APPROVE]
        if not approved:
            blockers.append("Owner approval missing (no approved "
                            "product_definition_gate decision)")
        return blockers

    # ------------------------------------------------------------- evaluate
    def evaluate(self) -> dict[str, Any]:
        """deterministic gate evaluation（LLM 不可调用此结果覆盖）。"""
        checks = {
            "idea": self._check_idea(),
            "assessments": self._check_assessments(),
            "opportunity_principles": self._check_opportunity_and_principles(),
            "requirement_lineage": self._check_requirement_lineage(),
            "feature_lineage": self._check_feature_lineage(),
            "critical_requirements": self._check_critical_requirements(),
            "owner_approval": self._check_owner_approval(),
        }
        blockers = [b for lst in checks.values() for b in lst]
        # 分类：硬性 blocker（无验证通过的说明）vs 可观察信息
        hard = [b for b in blockers if not b.startswith("explicit contradiction")]
        # 无硬 blocker → READY；有 contradiction 观察信息但其余通过 →
        # CONDITIONAL；否则 BLOCKED
        if not hard:
            if any(b.startswith("explicit contradiction") for b in blockers):
                result = GATE_CONDITIONAL
            else:
                result = GATE_READY
        else:
            result = GATE_BLOCKED
        return {
            "result": result,
            "tenant_id": self._tenant,
            "project_id": self._project,
            "checks": checks,
            "blockers": blockers,
            "gate_version": "product_definition_gate_v1",
            "evaluated_at": now_iso(),
        }

    def record_gate(self, actor: str = "system") -> dict[str, Any]:
        """把 Gate 结果写入 gates 表（auditable）。"""
        result = self.evaluate()
        self._db.add_gate(self._tenant, self._project,
                          gate="product_definition",
                          result=result["result"],
                          checks={"blockers": result["blockers"],
                                  "gate_version": result["gate_version"]},
                          approved_by=actor)
        return result

    # ------------------------------------------------------------- owner
    def propose_owner_decision(self, recommendation: str = "",
                               actor: str = "system") -> str:
        """创建 Owner Decision（approve/reject/request_revision）。"""
        return self._db.propose_decision(
            self._tenant, self._project, topic=GATE_DECISION_TOPIC,
            recommendation=recommendation or (
                "Approve to commit approved Product Definition to Product "
                "Truth; reject/request_revision to keep EXPLORE state"),
            options=[GATE_CHOICE_APPROVE, GATE_CHOICE_REJECT,
                     GATE_CHOICE_REQUEST_REVISION],
            trigger=f"{GATE_DECISION_TOPIC}:{self._project}",
        )

    def resolve_owner_decision(self, decision_id: str, choice: str,
                               comment: str = "",
                               actor: str = "system") -> dict[str, Any]:
        """Owner 显式裁定 Gate。只有 approve 才允许后续 commit。"""
        if choice not in OWNER_CHOICES:
            raise ValueError(f"invalid gate choice {choice!r}; expected one of "
                             f"{sorted(OWNER_CHOICES)}")
        self._db.resolve_decision(self._tenant, self._project, decision_id,
                                  choice, comment or None)
        return {"decision_id": decision_id, "choice": choice,
                "comment": comment, "resolved_at": now_iso()}

    def owner_decision_status(self) -> dict[str, Any]:
        """当前 Gate 的 Owner 决策状态（owner UX）。"""
        decisions = self._db.list_decisions(self._tenant, self._project)
        gate_decisions = [d for d in decisions
                          if d["topic"] == GATE_DECISION_TOPIC]
        return {
            "pending": [d for d in gate_decisions if d["status"] == "proposed"],
            "resolved": [d for d in gate_decisions
                         if d["status"] == "resolved"],
            "latest_approved": any(
                d["status"] == "resolved" and d["choice"] == GATE_CHOICE_APPROVE
                for d in gate_decisions),
        }

    # ------------------------------------------------------------- commit
    def commit_approved(self, actor: str = "system") -> dict[str, Any]:
        """Gate READY + Owner approve → 把 approved Requirements/Features
        写入 Product Truth（record_type=requirement/feature）。

        任何前置不满足 → 抛错（**Gate 前禁止 Product Truth commit**）。
        """
        from aipd_os.product_truth.lineage import LineageGraph
        from aipd_os.product_truth.models import SourceRef, TruthRecord
        from aipd_os.product_truth.store import ProductTruthStore

        evaluation = self.evaluate()
        # Owner approval 是独立且最明确的硬前置（§52：只有 approved canonical
        # Decision 才能 commit）——先检查，错误信息不含糊。
        if evaluation["checks"]["owner_approval"]:
            raise RuntimeError(
                "Owner approval required before Product Truth commit: "
                f"{evaluation['checks']['owner_approval'][0]}")
        if evaluation["result"] == GATE_BLOCKED:
            raise RuntimeError(
                f"Product Definition Gate BLOCKED; cannot commit Product Truth: "
                f"{evaluation['blockers']}")
        store = ProductTruthStore(str(self._db.path),
                                  tenant_id=self._tenant,
                                  project_id=self._project)
        graph = LineageGraph(store, tenant_id=self._tenant,
                             project_id=self._project,
                             canonical_db=self._db)
        committed: list[str] = []
        reqs = [r for r in self._pi.list_requirements(self._tenant,
                                                      self._project)
                if r.lifecycle_status == LIFECYCLE_ACTIVE]
        for req in reqs:
            rid = store.add(TruthRecord(
                record_type="requirement",
                content=f"{req.title}: {req.statement}",
                source=SourceRef(note=f"product_intelligence:{req.requirement_id}"),
                trust_level="verified",
                metadata={"gate_approved": True,
                          "definition_status": req.definition_status,
                          "criticality": req.criticality,
                          "requirement_id": req.requirement_id,
                          "source_commit": _head_sha()}))
            graph.add_edge(req.requirement_id, rid, relation="derived_from")
            committed.append(rid)
        feats = [f for f in self._pi.list_features(self._tenant, self._project)
                 if f.lifecycle_status == LIFECYCLE_ACTIVE]
        for feat in feats:
            fid = store.add(TruthRecord(
                record_type="feature",
                content=f"{feat.title}: {feat.description}",
                source=SourceRef(note=f"product_intelligence:{feat.feature_id}"),
                trust_level="verified",
                metadata={"gate_approved": True,
                          "definition_status": feat.definition_status,
                          "feature_id": feat.feature_id,
                          "source_commit": _head_sha()}))
            graph.add_edge(feat.feature_id, fid, relation="derived_from")
            committed.append(fid)
        self._db.add_audit(actor, "product_definition_gate.commit",
                           self._project, self._tenant,
                           after={"committed": committed,
                                  "requirements": len(reqs),
                                  "features": len(feats)})
        return {"committed": committed, "requirements": len(reqs),
                "features": len(feats), "gate": evaluation["result"]}


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
    "GATE_READY", "GATE_CONDITIONAL", "GATE_BLOCKED",
    "GATE_DECISION_TOPIC",
    "GATE_CHOICE_APPROVE", "GATE_CHOICE_REJECT", "GATE_CHOICE_REQUEST_REVISION",
    "OWNER_CHOICES",
]
