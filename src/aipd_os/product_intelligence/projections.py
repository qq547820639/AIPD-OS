"""ProductDefinitionProjection（v5.9，§48）。

汇总 Opportunity / Principles / Requirements / Features / Critical
assumptions / Unknowns / Conflicts / Validation gaps，回答
「当前产品到底定义到什么程度？」。

**不建第二套 Product Definition DB** —— 纯查询组合（同 IdeaTruthProjection
模式）。包含 Gate 状态（经 :class:`ProductDefinitionGate`）与 Owner 决策状态，
供 Owner UX / CLI / Supervisor 使用。
"""
from __future__ import annotations

from typing import Any

from aipd_os.state.db import AIPDStateDB

from .gate import ProductDefinitionGate
from .models import (
    CRITICALITY_CRITICAL,
    LIFECYCLE_ACTIVE,
    LIFECYCLE_CANDIDATE,
)
from .service import ProductIntelligenceService


class ProductDefinitionProjection:
    """Product Definition 的查询组合 projection（非 Store）。"""

    def __init__(self, db: AIPDStateDB, tenant_id: str = "default",
                 project_id: str = "default") -> None:
        self._db = db
        self._tenant = tenant_id
        self._project = project_id
        self._pi = ProductIntelligenceService(db)
        self._gate = ProductDefinitionGate(db, tenant_id, project_id)

    def project(self) -> dict[str, Any]:
        """当前产品定义状态（§55 Owner UX 数据源）。"""
        insights = self._pi.list_insights(self._tenant, self._project)
        opportunities = self._pi.list_opportunities(self._tenant,
                                                    self._project)
        principles = self._pi.list_principles(self._tenant, self._project)
        requirements = self._pi.list_requirements(self._tenant, self._project)
        features = self._pi.list_features(self._tenant, self._project)

        active_reqs = [r for r in requirements
                       if r.lifecycle_status == LIFECYCLE_ACTIVE]
        critical_reqs = [r for r in active_reqs
                         if r.criticality == CRITICALITY_CRITICAL]
        unknowns = [r for r in active_reqs
                    if r.epistemic_status == "U"]
        conflicts = [r for r in active_reqs
                     if r.definition_status == "CONFLICT"]
        validation_gaps = [r.requirement_id for r in critical_reqs
                           if not (r.verification_method
                                   or r.verification_test_refs)]
        assumptions = [i for i in insights
                       if i.epistemic_status == "A"]
        gate = self._gate.evaluate()

        return {
            "tenant_id": self._tenant,
            "project_id": self._project,
            "counts": {
                "insights": len(insights),
                "opportunities": len(opportunities),
                "principles": len(principles),
                "requirements": len(requirements),
                "active_requirements": len(active_reqs),
                "critical_requirements": len(critical_reqs),
                "features": len(features),
            },
            "opportunity": {
                "selected": [o.opportunity_id for o in opportunities
                             if o.lifecycle_status != "archived"],
                "unresolved": [o.opportunity_id for o in opportunities
                               if o.lifecycle_status == LIFECYCLE_CANDIDATE],
            },
            "principles": [p.principle_id for p in principles],
            "requirements": {
                "active": [r.requirement_id for r in active_reqs],
                "critical": [r.requirement_id for r in critical_reqs],
                "tbd": [r.requirement_id for r in active_reqs
                        if r.definition_status == "TBD"],
                "conflicts": [r.requirement_id for r in conflicts],
            },
            "features": [f.feature_id for f in features],
            "critical_assumptions": [i.insight_id for i in assumptions],
            "unknowns": [r.requirement_id for r in unknowns],
            "validation_gaps": validation_gaps,
            "gate": {
                "result": gate["result"],
                "blockers": gate["blockers"],
                "owner": self._gate.owner_decision_status(),
            },
        }

    def to_markdown(self) -> str:
        """Owner 可读摘要（§55 格式：不显示伪百分比）。"""
        p = self.project()
        c = p["counts"]
        g = p["gate"]
        lines = [
            "PRODUCT DEFINITION",
            f"Opportunity: selected={len(p['opportunity']['selected'])} "
            f"unresolved={len(p['opportunity']['unresolved'])}",
            f"Principles: {len(p['principles'])} active",
            f"Requirements: {c['active_requirements']} active, "
            f"critical: {c['critical_requirements']}, "
            f"TBD: {len(p['requirements']['tbd'])}, "
            f"conflicts: {len(p['requirements']['conflicts'])}",
            f"Features: {c['features']}",
            f"Gate: {g['result']}",
        ]
        blockers = g["blockers"]
        if blockers:
            lines.append("Blockers:")
            for b in blockers:
                lines.append(f"- {b}")
        owner = g["owner"]
        lines.append(f"Owner decision: "
                     f"approved={owner['latest_approved']} "
                     f"pending={len(owner['pending'])}")
        return "\n".join(lines)


__all__ = ["ProductDefinitionProjection"]
