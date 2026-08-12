"""Product Intelligence package（v5.9）：Evidence → Product Definition 的
探索/转译过程。

- :mod:`models`：Insight / Opportunity / ProductPrinciple / Requirement /
  Feature 五个 canonical domain 对象；
- :mod:`service`：ProductIntelligenceService（CRUD + canonical lineage +
  deterministic 校验 + traceability）；
- :mod:`gate`：ProductDefinitionGate（deterministic + Owner Decision）；
- :mod:`projections`：ProductDefinitionProjection（查询组合，非 Store）。

原则：LLM/分析产出先是 **candidate**，绝不自动 committed；只有 Gate +
Owner approve 后才进入 Product Truth（product_truth 包）。lineage 全部复用
canonical LineageService，不建第二套 lineage。
"""
from __future__ import annotations

from .gate import (
    GATE_BLOCKED,
    GATE_CHOICE_APPROVE,
    GATE_CHOICE_REJECT,
    GATE_CHOICE_REQUEST_REVISION,
    GATE_CONDITIONAL,
    GATE_DECISION_TOPIC,
    GATE_READY,
    ProductDefinitionGate,
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

__all__ = [
    # models
    "Insight", "Opportunity", "ProductPrinciple", "Requirement", "Feature",
    "DEFINITION_STATUSES", "INSIGHT_TYPES", "OPPORTUNITY_TYPES",
    "REQUIREMENT_TYPES", "FEATURE_TYPES", "CRITICALITIES",
    "CRITICALITY_CRITICAL", "CRITICALITY_IMPORTANT", "CRITICALITY_NORMAL",
    "LIFECYCLE_STATUSES", "LIFECYCLE_CANDIDATE", "LIFECYCLE_ACTIVE",
    "LIFECYCLE_SUPERSEDED", "LIFECYCLE_ARCHIVED",
    # service
    "ProductIntelligenceService", "ProductScopeError",
    "ProductObjectNotFoundError", "ProductLineageMissingError",
    "ProductOptimisticLockError",
    "NODE_INSIGHT", "NODE_OPPORTUNITY", "NODE_PRINCIPLE",
    "NODE_REQUIREMENT", "NODE_FEATURE",
    # gate
    "ProductDefinitionGate",
    "GATE_READY", "GATE_CONDITIONAL", "GATE_BLOCKED",
    "GATE_DECISION_TOPIC",
    "GATE_CHOICE_APPROVE", "GATE_CHOICE_REJECT", "GATE_CHOICE_REQUEST_REVISION",
    # projections
    "ProductDefinitionProjection",
]
