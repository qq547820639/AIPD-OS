"""Idea Domain 能力适配器（v5.8.1 Commit 11）。

把 Idea 域 Domain Service 包装为 :class:`ToolAdapter`，注册进 AdapterRegistry
后由 ExecutionRouter 路由；Supervisor 只调度 capability_floor，不直接调用
Domain Service（不建立第二套 Provider dispatch）。

能力：
  - ``idea.structure``：IdeaDecomposer.decompose_existing（同一 Idea I0→I1）；
  - ``claim.research``：ResearchIntegration.link_evidence_for_claim
    （Search ≠ Assessment：默认 relation inconclusive + pending）；
  - ``evidence.assess_relation``：评审 relation（reviewed/rejected）；
  - ``idea_truth.refresh``：IdeaTruthProjection 动态 projection。
"""
from __future__ import annotations

from typing import Any

from aipd_os.execution.adapter import ToolAdapter, external_blocked_error
from aipd_os.idea.decomposer import IdeaDecomposer, IdeaDecompositionUnavailable
from aipd_os.idea.evidence_relations import EvidenceRelationService
from aipd_os.idea.projections import IdeaTruthProjection
from aipd_os.idea.research_provider import (
    EvidenceRequest,
    ResearchCapabilityUnavailable,
    ResearchIntegration,
)
from aipd_os.state.db import AIPDStateDB
from aipd_os.supervisor.idea_capabilities import (
    CLAIM_RESEARCH_CAPABILITY,
    EVIDENCE_ASSESS_RELATION_CAPABILITY,
    IDEA_STRUCTURE_CAPABILITY,
    IDEA_TRUTH_REFRESH_CAPABILITY,
)


class IdeaStructureAdapter(ToolAdapter):
    """idea.structure：IdeaDecomposer.decompose_existing（I0→I1 同一 Idea）。"""

    provider = "idea-decomposer"
    version = "1.0"

    def __init__(self, decomposer: IdeaDecomposer) -> None:
        self._decomposer = decomposer

    def capability_id(self) -> str:
        return str(IDEA_STRUCTURE_CAPABILITY)

    def validate_input(self, input: dict[str, Any]) -> list[str]:
        errors = []
        if not input.get("idea_id"):
            errors.append("'idea_id' required")
        return errors

    def execute(self, input: dict[str, Any]) -> Any:
        try:
            result = self._decomposer.decompose_existing(
                input["idea_id"], actor=input.get("actor", "system"))
        except IdeaDecompositionUnavailable as exc:
            raise external_blocked_error(
                IDEA_STRUCTURE_CAPABILITY, str(exc),
                work_id=input.get("work_id")) from exc
        return {
            "capability": IDEA_STRUCTURE_CAPABILITY,
            "idea": result["idea"],
            "claims": result["claims"],
            "maturity": "I1",
        }

    def side_effect_mode(self) -> str:
        return "PURE"


class ClaimResearchAdapter(ToolAdapter):
    """claim.research：ResearchIntegration.link_evidence_for_claim。"""

    provider = "research-integration"
    version = "1.0"

    def __init__(self, integration: ResearchIntegration) -> None:
        self._integration = integration

    def capability_id(self) -> str:
        return str(CLAIM_RESEARCH_CAPABILITY)

    def validate_input(self, input: dict[str, Any]) -> list[str]:
        errors = []
        if not input.get("claim_id"):
            errors.append("'claim_id' required")
        if not input.get("capability"):
            errors.append("'capability' required")
        return errors

    def execute(self, input: dict[str, Any]) -> Any:
        request = EvidenceRequest(
            claim_id=input["claim_id"],
            tenant_id=input.get("tenant_id", "default"),
            project_id=input.get("project_id", "default"),
            capability=input.get("capability", "research.academic_search"),
            gap_reason=input.get("gap_reason", ""),
            inputs={"query": input.get("query", "")},
        )
        try:
            out = self._integration.link_evidence_for_claim(
                request, actor=input.get("actor", "system"))
        except ResearchCapabilityUnavailable as exc:
            raise external_blocked_error(
                CLAIM_RESEARCH_CAPABILITY, str(exc),
                work_id=input.get("work_id")) from exc
        return {
            "capability": CLAIM_RESEARCH_CAPABILITY,
            "evidence_ids": out["evidence_ids"],
            "relations": out["relations"],
            "relation_type": out["relation_type"],
        }

    def side_effect_mode(self) -> str:
        return "PURE"


class EvidenceAssessRelationAdapter(ToolAdapter):
    """evidence.assess_relation：评审 relation（reviewed/rejected）。"""

    provider = "evidence-relations"
    version = "1.0"

    def __init__(self, relations: EvidenceRelationService) -> None:
        self._relations = relations

    def capability_id(self) -> str:
        return str(EVIDENCE_ASSESS_RELATION_CAPABILITY)

    def validate_input(self, input: dict[str, Any]) -> list[str]:
        errors = []
        if not input.get("relation_id"):
            errors.append("'relation_id' required")
        if input.get("review_status") not in ("reviewed", "rejected"):
            errors.append("'review_status' must be reviewed or rejected")
        return errors

    def execute(self, input: dict[str, Any]) -> Any:
        updated = self._relations.review(
            input.get("tenant_id", "default"),
            input.get("project_id", "default"),
            input["relation_id"],
            input["review_status"],
            actor=input.get("actor", "system"),
        )
        return {
            "capability": EVIDENCE_ASSESS_RELATION_CAPABILITY,
            "relation": updated.to_dict(),
        }

    def side_effect_mode(self) -> str:
        return "PURE"


class IdeaTruthRefreshAdapter(ToolAdapter):
    """idea_truth.refresh：IdeaTruthProjection 动态 projection。"""

    provider = "idea-truth"
    version = "1.0"

    def __init__(self, projection: IdeaTruthProjection) -> None:
        self._projection = projection

    def capability_id(self) -> str:
        return str(IDEA_TRUTH_REFRESH_CAPABILITY)

    def validate_input(self, input: dict[str, Any]) -> list[str]:
        errors = []
        if not input.get("idea_id"):
            errors.append("'idea_id' required")
        return errors

    def execute(self, input: dict[str, Any]) -> Any:
        projection = self._projection.project(input["idea_id"])
        return {
            "capability": IDEA_TRUTH_REFRESH_CAPABILITY,
            "projection": projection,
        }

    def side_effect_mode(self) -> str:
        return "PURE"


def register_idea_adapters(registry: Any, *, db: AIPDStateDB,
                           decomposer: IdeaDecomposer | None = None,
                           integration: ResearchIntegration | None = None,
                           relations: EvidenceRelationService | None = None,
                           projection: IdeaTruthProjection | None = None,
                           tenant_id: str = "default",
                           project_id: str = "default") -> list[ToolAdapter]:
    """把 idea.* 能力适配器注册进 AdapterRegistry。

    未提供的依赖用默认构造（decomposer 默认由调用方提供 provider；若缺省则
    不注册 idea.structure —— 避免无 provider 时误注册）。

    返回注册的适配器列表。
    """
    from aipd_os.idea.evidence_graph import EvidenceGraph

    registered: list[ToolAdapter] = []
    graph = EvidenceGraph(db)
    if decomposer is not None:
        registered.append(IdeaStructureAdapter(decomposer))
    if integration is None:
        from aipd_os.execution.execution_router import ExecutionRouter
        from aipd_os.execution.runs import RunStore
        from aipd_os.tool_adapters.builtin import build_registry
        base = build_registry()
        store = RunStore(str(db.path.parent / "idea_exec.db"))
        router = ExecutionRouter(store, base)
        integration = ResearchIntegration(db, EvidenceRelationService(db),
                                          graph, router=router)
    registered.append(ClaimResearchAdapter(integration))
    if relations is None:
        relations = EvidenceRelationService(db)
    registered.append(EvidenceAssessRelationAdapter(relations))
    if projection is None:
        projection = IdeaTruthProjection(db, graph, tenant_id, project_id)
    registered.append(IdeaTruthRefreshAdapter(projection))
    for adapter in registered:
        registry.register(adapter)
    return registered


__all__ = [
    "IDEA_STRUCTURE_CAPABILITY",
    "CLAIM_RESEARCH_CAPABILITY",
    "EVIDENCE_ASSESS_RELATION_CAPABILITY",
    "IDEA_TRUTH_REFRESH_CAPABILITY",
    "IdeaStructureAdapter",
    "ClaimResearchAdapter",
    "EvidenceAssessRelationAdapter",
    "IdeaTruthRefreshAdapter",
    "register_idea_adapters",
]
