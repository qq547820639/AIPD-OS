"""Product Intelligence package（v5.9 + v5.9.1）：Evidence → Product
Definition 的探索/转译过程。

- :mod:`models`：Insight / Opportunity / ProductPrinciple / Requirement /
  Feature 五个 canonical domain 对象；
- :mod:`service`：ProductIntelligenceService（事务安全 CRUD + canonical
  lineage reconcile + deterministic 校验 + traceability + 显式 Opportunity
  selection）；
- :mod:`gate`：ProductDefinitionGate（结构化 GateEvaluation + snapshot
  绑定 Owner Decision + Commit Eligibility）；
- :mod:`snapshot`：ProductDefinitionSnapshot（immutable + deterministic
  hash + stale detection）；
- :mod:`projections`：ProductDefinitionProjection（查询组合，非 Store）；
- :mod:`provider`：ProductIntelligenceProvider 契约（candidate 输出）。

原则：LLM/分析产出先是 **candidate**，绝不自动 committed；只有 Gate +
Owner 对**确切 snapshot** approve 后才进入 Product Truth。lineage 全部复用
canonical LineageService，不建第二套 lineage。
"""
from __future__ import annotations

from .gate import (
    AUTH_APPROVED,
    AUTH_APPROVED_WITH_WAIVER,
    AUTH_PENDING,
    AUTH_REJECTED,
    GATE_BLOCKED,
    GATE_CHOICE_APPROVE,
    GATE_CHOICE_APPROVE_WITH_WAIVER,
    GATE_CHOICE_REJECT,
    GATE_CHOICE_REQUEST_REVISION,
    GATE_CONDITIONAL,
    GATE_DECISION_TOPIC,
    GATE_READY,
    CriterionResult,
    GateEvaluation,
    OWNER_CHOICES,
    ProductDefinitionGate,
    SnapshotAlreadyCommittedError,
)
from .models import (
    CRITICALITIES,
    CRITICALITY_CRITICAL,
    CRITICALITY_IMPORTANT,
    CRITICALITY_NORMAL,
    DEFINITION_STATUSES,
    FEATURE_TYPES,
    INSIGHT_TYPES,
    LIFECYCLE_ACTIVE,
    LIFECYCLE_ARCHIVED,
    LIFECYCLE_CANDIDATE,
    LIFECYCLE_STATUSES,
    LIFECYCLE_SUPERSEDED,
    OPPORTUNITY_TYPES,
    REQUIREMENT_TYPES,
    SELECTION_CANDIDATE,
    SELECTION_REJECTED,
    SELECTION_SELECTED,
    SELECTION_STATUSES,
    SELECTION_SUPERSEDED,
    Feature,
    Insight,
    Opportunity,
    ProductPrinciple,
    Requirement,
)
from .projections import ProductDefinitionProjection
from .service import (
    NODE_FEATURE,
    NODE_INSIGHT,
    NODE_OPPORTUNITY,
    NODE_PRINCIPLE,
    NODE_REQUIREMENT,
    ProductIntelligenceService,
    ProductLineageMissingError,
    ProductObjectNotFoundError,
    ProductOptimisticLockError,
    ProductScopeError,
)
from .snapshot import (
    SNAPSHOT_COMMITTED,
    SNAPSHOT_FROZEN,
    SNAPSHOT_SCHEMA_VERSION,
    SNAPSHOT_STALE,
    ProductDefinitionSnapshot,
    ProductDefinitionSnapshotService,
    SnapshotNotFoundError,
)

__all__ = [
    # models
    "Insight", "Opportunity", "ProductPrinciple", "Requirement", "Feature",
    "DEFINITION_STATUSES", "INSIGHT_TYPES", "OPPORTUNITY_TYPES",
    "REQUIREMENT_TYPES", "FEATURE_TYPES", "CRITICALITIES",
    "CRITICALITY_CRITICAL", "CRITICALITY_IMPORTANT", "CRITICALITY_NORMAL",
    "LIFECYCLE_STATUSES", "LIFECYCLE_CANDIDATE", "LIFECYCLE_ACTIVE",
    "LIFECYCLE_SUPERSEDED", "LIFECYCLE_ARCHIVED",
    "SELECTION_STATUSES", "SELECTION_CANDIDATE", "SELECTION_SELECTED",
    "SELECTION_REJECTED", "SELECTION_SUPERSEDED",
    # service
    "ProductIntelligenceService", "ProductScopeError",
    "ProductObjectNotFoundError", "ProductLineageMissingError",
    "ProductOptimisticLockError",
    "NODE_INSIGHT", "NODE_OPPORTUNITY", "NODE_PRINCIPLE",
    "NODE_REQUIREMENT", "NODE_FEATURE",
    # gate
    "ProductDefinitionGate", "GateEvaluation", "CriterionResult",
    "OWNER_CHOICES", "SnapshotAlreadyCommittedError",
    "GATE_READY", "GATE_CONDITIONAL", "GATE_BLOCKED",
    "GATE_DECISION_TOPIC",
    "GATE_CHOICE_APPROVE", "GATE_CHOICE_REJECT",
    "GATE_CHOICE_REQUEST_REVISION", "GATE_CHOICE_APPROVE_WITH_WAIVER",
    "AUTH_APPROVED", "AUTH_REJECTED", "AUTH_PENDING",
    "AUTH_APPROVED_WITH_WAIVER",
    # snapshot
    "ProductDefinitionSnapshot", "ProductDefinitionSnapshotService",
    "SnapshotNotFoundError",
    "SNAPSHOT_FROZEN", "SNAPSHOT_STALE", "SNAPSHOT_COMMITTED",
    "SNAPSHOT_SCHEMA_VERSION",
    # projections
    "ProductDefinitionProjection",
]
