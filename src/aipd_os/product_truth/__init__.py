"""AIPD-OS Product Truth：结构化产品事实模型、血缘图与失效传播。

P1-1 提供结构化的 Product Truth（事实/假设/需求/CTQ/证据/决策/风险/制品版本），
显式依赖图与血缘图，以及失效传播 + 有界自动返工，全部基于 sqlite 持久化。
"""
from __future__ import annotations

from .lineage import CycleDetectedError, LineageGraph
from .models import (
                     REWORK_STATUS,
                     TRUST_LEVELS,
                     TRUTH_STATUS,
                     TRUTH_TYPES,
                     ReworkTask,
                     TrustAssessment,
                     TruthRecord,
)
from .propagation import PropagationEngine, ReworkExhaustedError
from .store import ProductTruthStore

__all__ = [
    "TRUTH_TYPES", "TRUST_LEVELS", "REWORK_STATUS", "TRUTH_STATUS",
    "TruthRecord", "ReworkTask", "TrustAssessment",
    "ProductTruthStore", "LineageGraph", "CycleDetectedError",
    "PropagationEngine", "ReworkExhaustedError",
]
