"""ProductDefinitionProjection（v5.9 + v5.9.1）。

汇总 Opportunity / Principles / Requirements / Features / Critical
assumptions / Unknowns / Conflicts / Validation gaps，回答
「当前产品到底定义到什么程度？」。

**Live Product Definition = Projection；Frozen Candidate = Snapshot；
Committed = ProductTruth**（§49）—— projection 不冻结任何状态。

v5.9.1：Gate 状态使用结构化 :class:`GateEvaluation`（hard/conditional/
warnings/information，P0-01）；Opportunity 显示显式 selection_status
（P0-07）；含最新 Snapshot 摘要（id/hash/fresh-stale）。
"""
from __future__ import annotations

from typing import Any

from aipd_os.state.db import AIPDStateDB

from .gate import ProductDefinitionGate
from .models import (
    CRITICALITY_CRITICAL,
    LIFECYCLE_ACTIVE,
    LIFECYCLE_CANDIDATE,
    SELECTION_SELECTED,
)
from .service import ProductIntelligenceService
from .snapshot import ProductDefinitionSnapshotService


class ProductDefinitionProjection:
    """Product Definition 的查询组合 projection（非 Store）。"""

    def __init__(self, db: AIPDStateDB, tenant_id: str = "default",
                 project_id: str = "default") -> None:
        self._db = db
        self._tenant = tenant_id
        self._project = project_id
        self._pi = ProductIntelligenceService(db)
        self._gate = ProductDefinitionGate(db, tenant_id, project_id)
        self._snapshots = ProductDefinitionSnapshotService(db)

    def project(self) -> dict[str, Any]:
        """当前产品定义状态（§55 Owner UX 数据源）。"""
        insights = self._pi.list_insights(self._tenant, self._project)
        opportunities = self._pi.list_opportunities(self._tenant,
                                                    self._project)
        principles = self._pi.list_principles(self._tenant, self._project)
        requirements = self._pi.list_requirements(self._tenant, self._project)
        features = self._pi.list_features(self._tenant, self._project)

        # 统计范围 = 非 archived（candidate 也是产品定义的一部分，与 Gate 一致）
        active_reqs = [r for r in requirements
                       if r.lifecycle_status != "archived"]
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
        selected = [o for o in opportunities
                    if o.lifecycle_status != "archived"
                    and o.selection_status == SELECTION_SELECTED]

        # Snapshot 摘要（最新；fresh/stale 动态判定）
        latest = self._snapshots.latest_snapshot(self._tenant, self._project)
        snapshot_summary: dict[str, Any] = {
            "id": None, "hash": None, "fresh": None,
            "stale_reasons": [], "lifecycle_status": None,
        }
        if latest is not None:
            stale, reasons = self._snapshots.is_stale(
                latest, self._tenant, self._project)
            snapshot_summary = {
                "id": latest.snapshot_id,
                "hash": latest.content_hash,
                "fresh": not stale,
                "stale_reasons": reasons,
                "lifecycle_status": latest.lifecycle_status,
            }

        # Gate：最新 snapshot 的技术评估 + authorization + eligibility
        gate: dict[str, Any] = {"snapshot": None, "technical": None,
                                "authorization": None, "eligibility": None}
        if latest is not None:
            evaluation = self._gate.evaluate_snapshot(latest)
            authorization = self._gate.authorization_status(
                latest.snapshot_id)
            eligibility = self._gate.commit_eligibility(evaluation,
                                                        authorization)
            gate = {
                "snapshot": {
                    "id": latest.snapshot_id,
                    "hash": latest.content_hash,
                    "fresh": snapshot_summary["fresh"],
                },
                "technical": {
                    "result": evaluation.result,
                    "hard_blockers": evaluation.hard_blockers,
                    "conditional_blockers": evaluation.conditional_blockers,
                    "warnings": evaluation.warnings,
                    "information": evaluation.information,
                },
                "authorization": authorization,
                "eligibility": eligibility,
            }

        return {
            "tenant_id": self._tenant,
            "project_id": self._project,
            "counts": {
                "insights": len(insights),
                "opportunities": len(opportunities),
                "principles": len(principles),
                "requirements": len(requirements),
                "active_requirements": len([r for r in requirements
                                            if r.lifecycle_status
                                            == LIFECYCLE_ACTIVE]),
                "critical_requirements": len(critical_reqs),
                "features": len(features),
            },
            "opportunity": {
                # P0-07：显式 selection_status（候选 ≠ 已选）
                "selected": [o.opportunity_id for o in selected],
                "candidates": [o.opportunity_id for o in opportunities
                               if o.lifecycle_status != "archived"
                               and o.selection_status
                               != SELECTION_SELECTED],
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
            "snapshot": snapshot_summary,
            "gate": gate,
        }

    def to_markdown(self) -> str:
        """Owner 可读摘要（§55/57 格式：不显示伪百分比）。"""
        p = self.project()
        c = p["counts"]
        lines = [
            "PRODUCT DEFINITION",
            f"Opportunity: selected={len(p['opportunity']['selected'])} "
            f"candidates={len(p['opportunity']['candidates'])}",
            f"Principles: {len(p['principles'])} active",
            f"Requirements: {c['active_requirements']} active, "
            f"critical: {c['critical_requirements']}, "
            f"TBD: {len(p['requirements']['tbd'])}, "
            f"conflicts: {len(p['requirements']['conflicts'])}",
            f"Features: {c['features']}",
        ]
        snap = p["snapshot"]
        if snap["id"]:
            lines.append(
                f"Snapshot: {snap['id']} hash={snap['hash'][:12]}… "
                f"fresh={snap['fresh']} ({snap['lifecycle_status']})")
            if snap["stale_reasons"]:
                for r in snap["stale_reasons"]:
                    lines.append(f"  stale: {r}")
        gate = p["gate"]
        if gate["technical"] is not None:
            tech = gate["technical"]
            lines.append(f"Technical Gate: {tech['result']}")
            for b in tech["hard_blockers"]:
                lines.append(f"  HARD: {b}")
            for b in tech["conditional_blockers"]:
                lines.append(f"  CONDITIONAL: {b}")
            for b in tech["warnings"]:
                lines.append(f"  WARN: {b}")
            auth = gate["authorization"]
            lines.append(f"Authorization: {auth['state']}")
            if auth["decision_id"]:
                lines.append(f"  decision {auth['decision_id']} "
                             f"choice={auth['choice']}")
            elig = gate["eligibility"]
            lines.append(f"Commit Eligibility: "
                         f"{'YES' if elig['eligible'] else 'NO'} "
                         f"({elig['reason']})")
        else:
            lines.append("Technical Gate: no snapshot yet "
                         "(create_snapshot to freeze)")
        return "\n".join(lines)


__all__ = ["ProductDefinitionProjection"]
