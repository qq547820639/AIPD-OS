"""Manufacturing Readiness Projection + Gate（v5.10 Milestone 4）。

确定性 Manufacturing Readiness Service。
不要让 LLM 决定 PASS/FAIL — readiness truth 由确定性规则计算。

规则：任何必要信息未知时默认 HOLD，而不是 PASS。
- FAIL 代表存在明确不满足条件
- HOLD 代表尚未验证、数据缺失、stale 或需人工合法 waiver
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from aipd_os.validation.issues import ISSUE_OPEN, IssueService
from aipd_os.validation.models import (
    BLOCKING_STATUSES,
    RESULT_PASS,
)
from aipd_os.validation.service import ValidationService

logger = logging.getLogger(__name__)

# Overall readiness status
READINESS_PASS = "PASS"
READINESS_HOLD = "HOLD"
READINESS_FAIL = "FAIL"
READINESS_STATUSES = frozenset({READINESS_PASS, READINESS_HOLD, READINESS_FAIL})

# Dimension names
DIM_PRODUCT_DEFINITION = "product_definition"
DIM_CAD = "cad"
DIM_BOM = "bom"
DIM_COST = "cost"
DIM_VALIDATION = "validation"
DIM_ISSUES = "issues"
DIM_SUPPLY_CHAIN = "supply_chain"
DIM_LINEAGE = "lineage"

ALL_DIMENSIONS = frozenset({
    DIM_PRODUCT_DEFINITION, DIM_CAD, DIM_BOM, DIM_COST,
    DIM_VALIDATION, DIM_ISSUES, DIM_SUPPLY_CHAIN, DIM_LINEAGE,
})


@dataclass
class DimensionStatus:
    """单个维度的 readiness 状态。"""
    dimension: str
    status: str  # PASS / HOLD / FAIL
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    remediation: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "status": self.status,
            "blockers": self.blockers,
            "warnings": self.warnings,
            "missing_evidence": self.missing_evidence,
            "remediation": self.remediation,
        }


@dataclass
class ReadinessReport:
    """Manufacturing Readiness 报告。"""
    overall_status: str  # PASS / HOLD / FAIL
    dimensions: list[DimensionStatus] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    stale_dependencies: list[str] = field(default_factory=list)
    relevant_object_ids: list[str] = field(default_factory=list)
    remediation_actions: list[str] = field(default_factory=list)
    evaluated_at: str = ""
    input_snapshot: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_status": self.overall_status,
            "dimensions": [d.to_dict() for d in self.dimensions],
            "blockers": self.blockers,
            "warnings": self.warnings,
            "missing_evidence": self.missing_evidence,
            "stale_dependencies": self.stale_dependencies,
            "relevant_object_ids": self.relevant_object_ids,
            "remediation_actions": self.remediation_actions,
            "evaluated_at": self.evaluated_at,
            "input_snapshot": self.input_snapshot,
        }

    def to_human_readable(self) -> str:
        """生成人类可读的报告。"""
        lines = [
            f"Manufacturing Readiness: {self.overall_status}",
            f"Evaluated at: {self.evaluated_at}",
            "",
        ]
        for dim in self.dimensions:
            lines.append(f"  {dim.dimension}: {dim.status}")
            for b in dim.blockers:
                lines.append(f"    ✗ {b}")
            for w in dim.warnings:
                lines.append(f"    ⚠ {w}")
        if self.blockers:
            lines.append("")
            lines.append("Overall Blockers:")
            for b in self.blockers:
                lines.append(f"  ✗ {b}")
        if self.remediation_actions:
            lines.append("")
            lines.append("Remediation Actions:")
            for a in self.remediation_actions:
                lines.append(f"  → {a}")
        return "\n".join(lines)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ReadinessService:
    """Manufacturing Readiness Service。

    确定性计算 readiness 状态，不依赖 LLM。
    """

    def __init__(
        self,
        validation_svc: ValidationService,
        issue_svc: IssueService,
    ) -> None:
        self._validation = validation_svc
        self._issues = issue_svc

    def evaluate(
        self,
        tenant_id: str,
        project_id: str,
        product_definition_complete: bool | None = None,
        cad_maturity_ok: bool | None = None,
        bom_release_ready: bool | None = None,
        cost_complete: bool | None = None,
        supply_chain_ready: bool | None = None,
    ) -> ReadinessReport:
        """评估制造就绪度。

        所有维度默认为 None（未知），导致 HOLD。
        只有显式传入 True/False 才会计算确定性结果。
        """
        now = _now_iso()
        dimensions: list[DimensionStatus] = []
        all_blockers: list[str] = []
        all_warnings: list[str] = []
        all_missing: list[str] = []
        all_remediation: list[str] = []

        # 1. Product Definition
        dim_pd = self._eval_product_definition(product_definition_complete)
        dimensions.append(dim_pd)

        # 2. CAD
        dim_cad = self._eval_cad(cad_maturity_ok)
        dimensions.append(dim_cad)

        # 3. BOM
        dim_bom = self._eval_bom(bom_release_ready)
        dimensions.append(dim_bom)

        # 4. Cost
        dim_cost = self._eval_cost(cost_complete)
        dimensions.append(dim_cost)

        # 5. Validation (from canonical domain)
        dim_val = self._eval_validation(tenant_id, project_id)
        dimensions.append(dim_val)

        # 6. Issues (from canonical domain)
        dim_issues = self._eval_issues(tenant_id, project_id)
        dimensions.append(dim_issues)

        # 7. Supply Chain
        dim_sc = self._eval_supply_chain(supply_chain_ready)
        dimensions.append(dim_sc)

        # 8. Lineage (simplified - always HOLD unless explicitly provided)
        dim_lin = DimensionStatus(
            dimension=DIM_LINEAGE,
            status=READINESS_HOLD,
            warnings=["Lineage completeness not yet evaluated"],
        )
        dimensions.append(dim_lin)

        # Aggregate
        for dim in dimensions:
            all_blockers.extend(dim.blockers)
            all_warnings.extend(dim.warnings)
            all_missing.extend(dim.missing_evidence)
            all_remediation.extend(dim.remediation)

        # Overall status: worst of all dimensions
        if any(d.status == READINESS_FAIL for d in dimensions):
            overall = READINESS_FAIL
        elif any(d.status == READINESS_HOLD for d in dimensions):
            overall = READINESS_HOLD
        else:
            overall = READINESS_PASS

        report = ReadinessReport(
            overall_status=overall,
            dimensions=dimensions,
            blockers=all_blockers,
            warnings=all_warnings,
            missing_evidence=all_missing,
            remediation_actions=all_remediation,
            evaluated_at=now,
            input_snapshot={
                "tenant_id": tenant_id,
                "project_id": project_id,
            },
        )

        # P2-M7: Persist readiness snapshot for audit trail
        self._persist_snapshot(tenant_id, project_id, report)

        return report

    def _persist_snapshot(
        self,
        tenant_id: str,
        project_id: str,
        report: ReadinessReport,
    ) -> None:
        """持久化 readiness 快照到 readiness_snapshots 表。"""
        try:
            import uuid as _uuid

            from aipd_os.validation.readiness_snapshot_repo import (
                ReadinessSnapshotRepository,
                compute_input_fingerprint,
            )
            snapshot_id = f"rsnap-{_uuid.uuid4().hex[:12]}"
            fingerprint = compute_input_fingerprint(report.input_snapshot)
            with self._validation._db.connect() as conn:
                repo = ReadinessSnapshotRepository(conn)
                repo.mark_superseded(tenant_id, project_id)
                repo.create(
                    snapshot_id=snapshot_id,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    overall_status=report.overall_status,
                    dimension_results=[d.to_dict() for d in report.dimensions],
                    blockers=report.blockers,
                    warnings=report.warnings,
                    missing_evidence=report.missing_evidence,
                    stale_dependencies=report.stale_dependencies,
                    remediation_actions=report.remediation_actions,
                    input_fingerprint=fingerprint,
                )
        except Exception:
            # Snapshot persistence should never break readiness evaluation
            pass

    def _eval_product_definition(self, complete: bool | None) -> DimensionStatus:
        if complete is None:
            return DimensionStatus(
                dimension=DIM_PRODUCT_DEFINITION,
                status=READINESS_HOLD,
                missing_evidence=["product_definition_completeness"],
                remediation=["Verify product definition completeness"],
            )
        if not complete:
            return DimensionStatus(
                dimension=DIM_PRODUCT_DEFINITION,
                status=READINESS_FAIL,
                blockers=["Product definition incomplete"],
                remediation=["Complete all mandatory requirements/CTQs"],
            )
        return DimensionStatus(dimension=DIM_PRODUCT_DEFINITION, status=READINESS_PASS)

    def _eval_cad(self, ok: bool | None) -> DimensionStatus:
        if ok is None:
            return DimensionStatus(
                dimension=DIM_CAD,
                status=READINESS_HOLD,
                missing_evidence=["cad_maturity_status"],
                remediation=["Verify CAD maturity and release artifact"],
            )
        if not ok:
            return DimensionStatus(
                dimension=DIM_CAD,
                status=READINESS_FAIL,
                blockers=["CAD maturity insufficient"],
                remediation=["Reach required CAD maturity level"],
            )
        return DimensionStatus(dimension=DIM_CAD, status=READINESS_PASS)

    def _eval_bom(self, ready: bool | None) -> DimensionStatus:
        if ready is None:
            return DimensionStatus(
                dimension=DIM_BOM,
                status=READINESS_HOLD,
                missing_evidence=["bom_release_status"],
                remediation=["Verify BOM release readiness"],
            )
        if not ready:
            return DimensionStatus(
                dimension=DIM_BOM,
                status=READINESS_FAIL,
                blockers=["BOM not release-ready"],
                remediation=["Complete BOM structure and resolve errors"],
            )
        return DimensionStatus(dimension=DIM_BOM, status=READINESS_PASS)

    def _eval_cost(self, complete: bool | None) -> DimensionStatus:
        if complete is None:
            return DimensionStatus(
                dimension=DIM_COST,
                status=READINESS_HOLD,
                missing_evidence=["cost_completeness"],
                remediation=["Verify cost completeness (unit cost required)"],
            )
        if not complete:
            return DimensionStatus(
                dimension=DIM_COST,
                status=READINESS_FAIL,
                blockers=["Cost analysis incomplete"],
                remediation=["Complete unit cost analysis"],
            )
        return DimensionStatus(dimension=DIM_COST, status=READINESS_PASS)

    def _eval_validation(self, tenant_id: str, project_id: str) -> DimensionStatus:
        """从 canonical validation 域计算 validation readiness。"""
        # 获取所有非 stale 的结果
        results = self._validation.list_results(tenant_id, project_id)

        # 过滤非 stale
        active_results = [r for r in results if not r.stale]

        if not active_results:
            return DimensionStatus(
                dimension=DIM_VALIDATION,
                status=READINESS_HOLD,
                missing_evidence=["validation_results"],
                remediation=["Run required validation tests"],
            )

        # 检查是否有阻塞结果
        blocking = [r for r in active_results if r.result_status in BLOCKING_STATUSES]
        if blocking:
            blockers = [
                f"Test {r.test_id}: {r.result_status}" for r in blocking
            ]
            return DimensionStatus(
                dimension=DIM_VALIDATION,
                status=READINESS_FAIL,
                blockers=blockers,
                remediation=["Resolve all failing/hold validation tests"],
            )

        # 检查是否有有效 PASS
        effective_pass = [r for r in active_results
                         if r.result_status == RESULT_PASS and not r.stale]
        if not effective_pass:
            return DimensionStatus(
                dimension=DIM_VALIDATION,
                status=READINESS_HOLD,
                missing_evidence=["effective_pass_results"],
                remediation=["Obtain passing validation results for current artifact"],
            )

        return DimensionStatus(dimension=DIM_VALIDATION, status=READINESS_PASS)

    def _eval_issues(self, tenant_id: str, project_id: str) -> DimensionStatus:
        """从 canonical issue 域计算 issues readiness。"""
        blocking_issues = self._issues.list_issues(
            tenant_id, project_id, blocking_only=True)

        # 过滤未关闭的
        open_blocking = [i for i in blocking_issues
                        if i.status in (ISSUE_OPEN, "IN_PROGRESS")]

        if open_blocking:
            blockers = [
                f"Issue {i.issue_id}: {i.title}" for i in open_blocking
            ]
            return DimensionStatus(
                dimension=DIM_ISSUES,
                status=READINESS_FAIL,
                blockers=blockers,
                remediation=["Resolve all blocking issues before release"],
            )

        return DimensionStatus(dimension=DIM_ISSUES, status=READINESS_PASS)

    def _eval_supply_chain(self, ready: bool | None) -> DimensionStatus:
        if ready is None:
            return DimensionStatus(
                dimension=DIM_SUPPLY_CHAIN,
                status=READINESS_HOLD,
                missing_evidence=["supply_chain_status"],
                remediation=["Verify supplier/certificate/qualification status"],
            )
        if not ready:
            return DimensionStatus(
                dimension=DIM_SUPPLY_CHAIN,
                status=READINESS_FAIL,
                blockers=["Supply chain not ready"],
                remediation=["Complete supplier qualification"],
            )
        return DimensionStatus(dimension=DIM_SUPPLY_CHAIN, status=READINESS_PASS)


__all__ = [
    "READINESS_PASS", "READINESS_HOLD", "READINESS_FAIL",
    "DimensionStatus", "ReadinessReport", "ReadinessService",
]
