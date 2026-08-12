"""Product Intelligence ToolAdapters（v5.9.1，§33-35/37-38）。

链：ExecutionRouter → Product*Adapter → ProductIntelligenceProvider →
candidate 结果 → schema validation → ProductIntelligenceService →
canonical objects（lifecycle=candidate）→ lineage → ExecutionResult。

诚实性（§35/38）：
- provider 未配置 → ``discover().available=False`` → runtime probe 报
  EXTERNAL_DEPENDENCY；execute 时写出外部任务包（external_blocked），
  绝不伪造"成功"；
- ``product.definition_gate`` / ``product.create_snapshot`` 是**本地
  deterministic** adapter（不调 LLM，§33）；
- 候选对象 persist 后默认 lifecycle=candidate —— Owner/Gate 负责 commit
  （§32）。
"""
from __future__ import annotations

from typing import Any

from aipd_os.execution.adapter import ToolAdapter, external_blocked_error
from aipd_os.product_intelligence.gate import ProductDefinitionGate
from aipd_os.product_intelligence.models import (
    Feature,
    Insight,
    Opportunity,
    ProductPrinciple,
    Requirement,
)
from aipd_os.product_intelligence.provider import (
    ProductIntelligenceProvider,
)
from aipd_os.product_intelligence.service import ProductIntelligenceService
from aipd_os.product_intelligence.snapshot import (
    ProductDefinitionSnapshotService,
)
from aipd_os.state.db import AIPDStateDB

# capability ids（与 supervisor/idea_capabilities.py 常量一致）
PRODUCT_DERIVE_INSIGHTS = "product.derive_insights"
PRODUCT_IDENTIFY_OPPORTUNITY = "product.identify_opportunity"
PRODUCT_DERIVE_PRINCIPLES = "product.derive_principles"
PRODUCT_DERIVE_REQUIREMENTS = "product.derive_requirements"
PRODUCT_DERIVE_FEATURES = "product.derive_features"
PRODUCT_CREATE_SNAPSHOT = "product.create_snapshot"
PRODUCT_DEFINITION_GATE = "product.definition_gate"

_DEFAULT_PROVIDER_HINT = (
    "需要配置真实 ProductIntelligenceProvider（当前未配置）。请接入模型/"
    "分析供应商后重试，或人工完成该阶段并把结果回填为 candidate。")


def _scope_of(input_: dict[str, Any]) -> tuple[str, str]:
    return (str(input_.get("tenant_id", "default")),
            str(input_.get("project_id", "default")))


class _ProductGenerationAdapter(ToolAdapter):
    """生成类 product adapter 基类（provider-backed）。"""

    provider = "product-intelligence"

    def __init__(self, db: AIPDStateDB,
                 provider: ProductIntelligenceProvider | None = None) -> None:
        self._db = db
        self._provider = provider
        self._pi = ProductIntelligenceService(db)

    def discover(self) -> dict[str, Any]:
        return {
            "id": self.capability_id(),
            "name": self.capability_id(),
            "provider": self.provider,
            "version": "1.0",
            "available": self._provider is not None
            and getattr(self._provider, "configured", True),
        }

    def _provider_or_blocked(self, input_: dict[str, Any]) -> ProductIntelligenceProvider:
        if self._provider is None:
            raise external_blocked_error(
                self.capability_id(),
                f"{self.capability_id()} 需要真实 ProductIntelligenceProvider："
                f"{_DEFAULT_PROVIDER_HINT}",
                work_id=input_.get("work_id"))
        return self._provider

    def _provenance_meta(self) -> dict[str, Any]:
        if self._provider is None:
            return {"provider": "unconfigured"}
        return self._provider.provenance().to_dict()


class ProductDeriveInsightsAdapter(_ProductGenerationAdapter):
    def capability_id(self) -> str:
        return PRODUCT_DERIVE_INSIGHTS

    def validate_input(self, input_: dict[str, Any]) -> list[str]:
        errors = []
        if not input_.get("idea_id"):
            errors.append("'idea_id' 必填")
        return errors

    def execute(self, input_: dict[str, Any]) -> dict[str, Any]:
        provider = self._provider_or_blocked(input_)
        tenant, project = _scope_of(input_)
        context = {
            "idea_id": input_.get("idea_id"), "tenant_id": tenant,
            "project_id": project,
            "claims": input_.get("claims", []),
            "assessments": input_.get("assessments", []),
        }
        candidates = provider.derive_insights(context)
        errors = provider.validate_candidates(candidates, "insight")
        if errors:
            raise ValueError(f"provider returned invalid insights: {errors}")
        created = []
        for c in candidates:
            obj = self._pi.create_insight(Insight(
                insight_id="", tenant_id=tenant, project_id=project,
                idea_id=input_.get("idea_id", ""),
                statement=c.statement, insight_type=c.insight_type,
                source_claim_ids=c.source_claim_ids,
                rationale=c.rationale, limitations=c.limitations))
            created.append(obj.insight_id)
        return {"created": created, "count": len(created),
                "provider": self._provenance_meta(),
                "status": "candidate_persisted"}


class ProductIdentifyOpportunityAdapter(_ProductGenerationAdapter):
    def capability_id(self) -> str:
        return PRODUCT_IDENTIFY_OPPORTUNITY

    def execute(self, input_: dict[str, Any]) -> dict[str, Any]:
        provider = self._provider_or_blocked(input_)
        tenant, project = _scope_of(input_)
        context = {
            "idea_id": input_.get("idea_id"), "tenant_id": tenant,
            "project_id": project,
            "insights": input_.get("insights", []),
        }
        candidates = provider.identify_opportunities(context)
        errors = provider.validate_candidates(candidates, "opportunity")
        if errors:
            raise ValueError(f"provider returned invalid opportunities: {errors}")
        created = []
        for c in candidates:
            obj = self._pi.create_opportunity(Opportunity(
                opportunity_id="", tenant_id=tenant, project_id=project,
                idea_id=input_.get("idea_id", ""),
                title=c.title, statement=c.statement,
                source_insight_ids=c.source_insight_ids,
                target_user=c.target_user, problem=c.problem,
                desired_outcome=c.desired_outcome,
                differentiation=c.differentiation,
                known_alternatives=c.known_alternatives,
                evidence_gaps=c.evidence_gaps))
            created.append(obj.opportunity_id)
        return {"created": created, "count": len(created),
                "provider": self._provenance_meta(),
                "status": "candidate_persisted"}


class ProductDerivePrinciplesAdapter(_ProductGenerationAdapter):
    def capability_id(self) -> str:
        return PRODUCT_DERIVE_PRINCIPLES

    def execute(self, input_: dict[str, Any]) -> dict[str, Any]:
        provider = self._provider_or_blocked(input_)
        tenant, project = _scope_of(input_)
        context = {
            "idea_id": input_.get("idea_id"), "tenant_id": tenant,
            "project_id": project,
            "insights": input_.get("insights", []),
            "opportunity": input_.get("opportunity"),
        }
        candidates = provider.derive_principles(context)
        errors = provider.validate_candidates(candidates, "principle")
        if errors:
            raise ValueError(f"provider returned invalid principles: {errors}")
        created = []
        for c in candidates:
            obj = self._pi.create_principle(ProductPrinciple(
                principle_id="", tenant_id=tenant, project_id=project,
                opportunity_id=input_.get("opportunity_id", ""),
                statement=c.statement, rationale=c.rationale,
                source_insight_ids=c.source_insight_ids,
                criticality=c.criticality))
            created.append(obj.principle_id)
        return {"created": created, "count": len(created),
                "provider": self._provenance_meta(),
                "status": "candidate_persisted"}


class ProductDeriveRequirementsAdapter(_ProductGenerationAdapter):
    def capability_id(self) -> str:
        return PRODUCT_DERIVE_REQUIREMENTS

    def execute(self, input_: dict[str, Any]) -> dict[str, Any]:
        provider = self._provider_or_blocked(input_)
        tenant, project = _scope_of(input_)
        context = {
            "idea_id": input_.get("idea_id"), "tenant_id": tenant,
            "project_id": project,
            "principles": input_.get("principles", []),
        }
        candidates = provider.derive_requirements(context)
        errors = provider.validate_candidates(candidates, "requirement")
        if errors:
            raise ValueError(f"provider returned invalid requirements: {errors}")
        created = []
        for c in candidates:
            obj = self._pi.create_requirement(Requirement(
                requirement_id="", tenant_id=tenant, project_id=project,
                title=c.title, statement=c.statement,
                requirement_type=c.requirement_type,
                criticality=c.criticality,
                verification_method=c.verification_method,
                source_principle_ids=c.source_principle_ids,
                nominal_value=c.nominal_value, unit=c.unit,
                lower_limit=c.lower_limit, upper_limit=c.upper_limit,
                tolerance=c.tolerance, test_condition=c.test_condition))
            created.append(obj.requirement_id)
        return {"created": created, "count": len(created),
                "provider": self._provenance_meta(),
                "status": "candidate_persisted"}


class ProductDeriveFeaturesAdapter(_ProductGenerationAdapter):
    def capability_id(self) -> str:
        return PRODUCT_DERIVE_FEATURES

    def execute(self, input_: dict[str, Any]) -> dict[str, Any]:
        provider = self._provider_or_blocked(input_)
        tenant, project = _scope_of(input_)
        context = {
            "idea_id": input_.get("idea_id"), "tenant_id": tenant,
            "project_id": project,
            "requirements": input_.get("requirements", []),
        }
        candidates = provider.derive_features(context)
        errors = provider.validate_candidates(candidates, "feature")
        if errors:
            raise ValueError(f"provider returned invalid features: {errors}")
        created = []
        for c in candidates:
            obj = self._pi.create_feature(Feature(
                feature_id="", tenant_id=tenant, project_id=project,
                title=c.title, description=c.description,
                feature_type=c.feature_type,
                source_requirement_ids=c.source_requirement_ids,
                assumptions=c.assumptions, constraints=c.constraints))
            created.append(obj.feature_id)
        return {"created": created, "count": len(created),
                "provider": self._provenance_meta(),
                "status": "candidate_persisted"}


class ProductCreateSnapshotAdapter(ToolAdapter):
    """本地 deterministic：冻结当前 Product Definition 为 immutable
    snapshot（§33 —— 不调 LLM）。"""

    provider = "aipd-os-local"

    def __init__(self, db: AIPDStateDB) -> None:
        self._db = db
        self._snapshots = ProductDefinitionSnapshotService(db)

    def capability_id(self) -> str:
        return PRODUCT_CREATE_SNAPSHOT

    def discover(self) -> dict[str, Any]:
        return {"id": self.capability_id(), "name": self.capability_id(),
                "provider": self.provider, "version": "1.0",
                "available": True}

    def execute(self, input_: dict[str, Any]) -> dict[str, Any]:
        tenant, project = _scope_of(input_)
        snap = self._snapshots.create_snapshot(
            tenant, project, actor=str(input_.get("actor", "system")))
        return {"snapshot_id": snap.snapshot_id,
                "content_hash": snap.content_hash,
                "opportunity_id": snap.opportunity_id,
                "requirements": len(snap.requirement_refs),
                "features": len(snap.feature_refs),
                "status": "snapshot_frozen"}


class ProductDefinitionGateAdapter(ToolAdapter):
    """本地 deterministic：对最新 snapshot 做技术 Gate 评估 + authorization
    + eligibility（§33 —— Gate 不调 LLM，LLM 只能解释不能决定）。"""

    provider = "aipd-os-local"

    def __init__(self, db: AIPDStateDB) -> None:
        self._db = db
        self._gate = None  # 懒构造（依赖 tenant/project）

    def capability_id(self) -> str:
        return PRODUCT_DEFINITION_GATE

    def discover(self) -> dict[str, Any]:
        return {"id": self.capability_id(), "name": self.capability_id(),
                "provider": self.provider, "version": "1.0",
                "available": True}

    def execute(self, input_: dict[str, Any]) -> dict[str, Any]:
        tenant, project = _scope_of(input_)
        gate = ProductDefinitionGate(self._db, tenant, project)
        snapshots = ProductDefinitionSnapshotService(self._db)
        latest = snapshots.latest_snapshot(tenant, project)
        if latest is None:
            return {"result": "NO_SNAPSHOT",
                    "information": ["create_snapshot() first"],
                    "authorization": {"state": "PENDING"},
                    "eligibility": {"eligible": False,
                                    "reason": "no snapshot"}}
        evaluation = gate.evaluate_snapshot(latest)
        authorization = gate.authorization_status(latest.snapshot_id)
        eligibility = gate.commit_eligibility(evaluation, authorization)
        return {
            "snapshot_id": latest.snapshot_id,
            "snapshot_hash": latest.content_hash,
            "result": evaluation.result,
            "hard_blockers": evaluation.hard_blockers,
            "conditional_blockers": evaluation.conditional_blockers,
            "warnings": evaluation.warnings,
            "information": evaluation.information,
            "authorization": authorization,
            "eligibility": eligibility,
        }


def register_product_adapters(
        registry: Any, db: AIPDStateDB,
        provider: ProductIntelligenceProvider | None = None) -> list[ToolAdapter]:
    """注册全部 product.* adapters（provider 可选；None → 诚实不可用）。"""
    adapters: list[ToolAdapter] = [
        ProductDeriveInsightsAdapter(db, provider=provider),
        ProductIdentifyOpportunityAdapter(db, provider=provider),
        ProductDerivePrinciplesAdapter(db, provider=provider),
        ProductDeriveRequirementsAdapter(db, provider=provider),
        ProductDeriveFeaturesAdapter(db, provider=provider),
        ProductCreateSnapshotAdapter(db),
        ProductDefinitionGateAdapter(db),
    ]
    for a in adapters:
        registry.register(a)
    return adapters


__all__ = [
    "PRODUCT_DERIVE_INSIGHTS", "PRODUCT_IDENTIFY_OPPORTUNITY",
    "PRODUCT_DERIVE_PRINCIPLES", "PRODUCT_DERIVE_REQUIREMENTS",
    "PRODUCT_DERIVE_FEATURES", "PRODUCT_CREATE_SNAPSHOT",
    "PRODUCT_DEFINITION_GATE",
    "ProductDeriveInsightsAdapter", "ProductIdentifyOpportunityAdapter",
    "ProductDerivePrinciplesAdapter", "ProductDeriveRequirementsAdapter",
    "ProductDeriveFeaturesAdapter", "ProductCreateSnapshotAdapter",
    "ProductDefinitionGateAdapter",
    "register_product_adapters",
]
