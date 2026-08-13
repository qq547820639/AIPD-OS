"""Idea & Evidence Foundation（v5.8 Commit 9-11）。

- ``models``：canonical Idea 对象（经 AIPDStateDB 持久化，不建第二 DB）；
- ``service``：IdeaService（tenant+project scoped / audited / versioned CRUD）；
- ``maturity``：IdeaMaturity 枚举（I0-I3，I3 只定义 contract）；
- ``decomposer``：IdeaDecompositionProvider contract + CAPABILITY_UNAVAILABLE 路径
  （真实 LLM provider 由生产装配配置驱动：``AIPD_MODEL_API_KEY`` +
  ``AIPD_MODEL_BASE_URL`` 配置后注册 ``LlmIdeaDecompositionProvider``，
  见 ``aipd_os.runtime._register_external_providers``）；
- ``projections``：IdeaTruthProjection / IdeaTruthSnapshot（已实装，
  动态聚合 maturity / claims / evidence counts）；
- ``claims`` / ``claim_service``：Claim Domain（Candidate Claim 默认 A/U，绝不默认 V）；
- ``evidence_relations``：Claim ↔ 现有 evidence 表 的关系（复用 canonical evidence）；
- ``evidence_graph``：EvidenceGraph 查询 API（SQLite 实现）。
"""
from __future__ import annotations

from .claim_assessment import (
    ASSESSMENT_CONTRADICTED,
    ASSESSMENT_INSUFFICIENT,
    ASSESSMENT_MIXED,
    ASSESSMENT_NOT_APPLICABLE,
    ASSESSMENT_NOT_SEARCHED,
    ASSESSMENT_PARTIALLY_SUPPORTED,
    ASSESSMENT_STATUSES,
    ASSESSMENT_SUPPORTED,
    CLAIM_ASSESSMENT_V1,
    assess,
)
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
    LEGACY_UNSCORED_SENTINEL,
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
    EvidenceRelationConflictError,
    EvidenceRelationNotFoundError,
    EvidenceRelationOptimisticLockError,
    EvidenceRelationScopeError,
    EvidenceRelationService,
)
from .maturity import KEY_CLAIM_TYPES, IdeaMaturity
from .models import (
    EMPTY_CONSTRAINTS_JSON,
    IDEA_LIFECYCLE_ACTIVE,
    IDEA_LIFECYCLE_ARCHIVED,
    IDEA_LIFECYCLE_STATUSES,
    IDEA_LIFECYCLE_SUPERSEDED,
    Idea,
)
from .projections import IdeaTruthProjection, IdeaTruthSnapshot
from .research_provider import (
    EVIDENCE_ASSESS_RELATION_CAPABILITY,
    RESEARCH_CAPABILITIES,
    EvidenceRequest,
    ResearchCapabilityUnavailable,
    ResearchIntegration,
    ResearchProvider,
    ResearchToolAdapter,
    UnavailableResearchProvider,
    research_capability_declaration,
)
from .serializers import parse_constraints, serialize_constraints
from .service import (
    IdeaNotFoundError,
    IdeaOptimisticLockError,
    IdeaService,
)

__all__ = [
    # models
    "Idea",
    "IDEA_LIFECYCLE_ACTIVE",
    "IDEA_LIFECYCLE_ARCHIVED",
    "IDEA_LIFECYCLE_SUPERSEDED",
    "IDEA_LIFECYCLE_STATUSES",
    "EMPTY_CONSTRAINTS_JSON",
    # service
    "IdeaService",
    "IdeaNotFoundError",
    "IdeaOptimisticLockError",
    # maturity / decomposer / projections
    "IdeaMaturity",
    "KEY_CLAIM_TYPES",
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
    "serialize_constraints",
    "parse_constraints",
    "IdeaTruthProjection",
    "IdeaTruthSnapshot",
    # claim assessment (Commit 3)
    "CLAIM_ASSESSMENT_V1",
    "ASSESSMENT_STATUSES",
    "ASSESSMENT_NOT_SEARCHED",
    "ASSESSMENT_INSUFFICIENT",
    "ASSESSMENT_SUPPORTED",
    "ASSESSMENT_PARTIALLY_SUPPORTED",
    "ASSESSMENT_MIXED",
    "ASSESSMENT_CONTRADICTED",
    "ASSESSMENT_NOT_APPLICABLE",
    "assess",
    # research provider / integration
    "RESEARCH_CAPABILITIES",
    "EVIDENCE_ASSESS_RELATION_CAPABILITY",
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
    "LEGACY_UNSCORED_SENTINEL",
    "CLAIM_LIFECYCLE_ACTIVE",
    "CLAIM_LIFECYCLE_SUPERSEDED",
    "CLAIM_LIFECYCLE_ARCHIVED",
    "CLAIM_LIFECYCLE_STATUSES",
    # evidence relations / graph
    "EvidenceRelation",
    "EvidenceRelationService",
    "EvidenceRelationConflictError",
    "EvidenceRelationNotFoundError",
    "EvidenceRelationOptimisticLockError",
    "EvidenceRelationScopeError",
    "RELATION_TYPES",
    "REVIEW_STATUSES",
    "EvidenceGraph",
    "UNKNOWN_EPISTEMIC_STATUSES",
]
