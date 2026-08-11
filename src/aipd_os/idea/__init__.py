"""Idea & Evidence Foundation（v5.8 Commit 9-11）。

- ``models``：canonical Idea 对象（经 AIPDStateDB 持久化，不建第二 DB）；
- ``service``：IdeaService（tenant+project scoped / audited / versioned CRUD）；
- ``maturity``：IdeaMaturity 枚举（I0-I3，I3 只定义 contract）；
- ``decomposer``：IdeaDecompositionProvider contract + CAPABILITY_UNAVAILABLE 路径
  （真实 LLM provider 在 Commit 12）；
- ``projections``：Idea Truth projection 骨架（Commit 14 填充）；
- ``claims`` / ``claim_service``：Claim Domain（Candidate Claim 默认 A/U，绝不默认 V）；
- ``evidence_relations``：Claim ↔ 现有 evidence 表 的关系（复用 canonical evidence）；
- ``evidence_graph``：EvidenceGraph 查询 API（SQLite 实现）。
"""
from __future__ import annotations

from .claim_service import (
    ClaimNotFoundError,
    ClaimOptimisticLockError,
    ClaimScopeError,
    ClaimService,
)
from .claims import (
    CLAIM_LIFECYCLE_ACTIVE,
    CLAIM_LIFECYCLE_ARCHIVED,
    CLAIM_LIFECYCLE_STATUSES,
    CLAIM_LIFECYCLE_SUPERSEDED,
    CLAIM_TYPES,
    DEFAULT_EPISTEMIC_STATUS,
    Claim,
)
from .decomposer import (
    CAPABILITY_UNAVAILABLE,
    FAILED_VALIDATION,
    IDEA_DECOMPOSE_CAPABILITY,
    STRUCTURED_CANDIDATE_SCHEMA,
    IdeaDecomposer,
    IdeaDecompositionProvider,
    IdeaDecompositionProviderAdapter,
    IdeaDecompositionUnavailable,
    IdeaDecompositionValidationError,
    StructuredCandidate,
    UnavailableProvider,
)
from .evidence_graph import UNKNOWN_EPISTEMIC_STATUSES, EvidenceGraph
from .evidence_relations import (
    RELATION_TYPES,
    REVIEW_STATUSES,
    EvidenceRelation,
    EvidenceRelationNotFoundError,
    EvidenceRelationOptimisticLockError,
    EvidenceRelationScopeError,
    EvidenceRelationService,
)
from .maturity import IdeaMaturity
from .models import (
    EMPTY_CONSTRAINTS_JSON,
    IDEA_LIFECYCLE_ARCHIVED,
    IDEA_LIFECYCLE_EVIDENCE_BACKED,
    IDEA_LIFECYCLE_RAW,
    IDEA_LIFECYCLE_STATUSES,
    IDEA_LIFECYCLE_STRUCTURED,
    Idea,
)
from .projections import IdeaTruthProjection, IdeaTruthSnapshot
from .research_provider import (
    RESEARCH_CAPABILITIES,
    EvidenceRequest,
    ResearchCapabilityUnavailable,
    ResearchIntegration,
    ResearchProvider,
    ResearchToolAdapter,
    UnavailableResearchProvider,
    research_capability_declaration,
)
from .service import (
    IdeaNotFoundError,
    IdeaOptimisticLockError,
    IdeaService,
)

__all__ = [
    # models
    "Idea",
    "IDEA_LIFECYCLE_RAW",
    "IDEA_LIFECYCLE_STRUCTURED",
    "IDEA_LIFECYCLE_EVIDENCE_BACKED",
    "IDEA_LIFECYCLE_ARCHIVED",
    "IDEA_LIFECYCLE_STATUSES",
    "EMPTY_CONSTRAINTS_JSON",
    # service
    "IdeaService",
    "IdeaNotFoundError",
    "IdeaOptimisticLockError",
    # maturity / decomposer / projections
    "IdeaMaturity",
    "IdeaDecompositionProvider",
    "IdeaDecompositionProviderAdapter",
    "IdeaDecompositionUnavailable",
    "IdeaDecompositionValidationError",
    "IdeaDecomposer",
    "StructuredCandidate",
    "UnavailableProvider",
    "CAPABILITY_UNAVAILABLE",
    "FAILED_VALIDATION",
    "IDEA_DECOMPOSE_CAPABILITY",
    "STRUCTURED_CANDIDATE_SCHEMA",
    "IdeaTruthProjection",
    "IdeaTruthSnapshot",
    # research provider / integration
    "RESEARCH_CAPABILITIES",
    "ResearchProvider",
    "UnavailableResearchProvider",
    "ResearchCapabilityUnavailable",
    "ResearchToolAdapter",
    "research_capability_declaration",
    "EvidenceRequest",
    "ResearchIntegration",
    # claims
    "Claim",
    "ClaimService",
    "ClaimNotFoundError",
    "ClaimOptimisticLockError",
    "ClaimScopeError",
    "CLAIM_TYPES",
    "DEFAULT_EPISTEMIC_STATUS",
    "CLAIM_LIFECYCLE_ACTIVE",
    "CLAIM_LIFECYCLE_SUPERSEDED",
    "CLAIM_LIFECYCLE_ARCHIVED",
    "CLAIM_LIFECYCLE_STATUSES",
    # evidence relations / graph
    "EvidenceRelation",
    "EvidenceRelationService",
    "EvidenceRelationNotFoundError",
    "EvidenceRelationOptimisticLockError",
    "EvidenceRelationScopeError",
    "RELATION_TYPES",
    "REVIEW_STATUSES",
    "EvidenceGraph",
    "UNKNOWN_EPISTEMIC_STATUSES",
]
