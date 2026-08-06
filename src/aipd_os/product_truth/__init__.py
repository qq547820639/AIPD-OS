"""AIPD-OS Product Truth：结构化产品事实模型、血缘图与失效传播。

P1-1 提供结构化的 Product Truth（事实/假设/需求/CTQ/证据/决策/风险/制品版本），
显式依赖图与血缘图，以及失效传播 + 有界自动返工，全部基于 sqlite 持久化。
"""
from __future__ import annotations

from .models import (TRUTH_TYPES, TRUST_LEVELS, REWORK_STATUS, TRUTH_STATUS,
                     TruthRecord, ReworkTask, TrustAssessment)
from .store import ProductTruthStore
from .lineage import LineageGraph, CycleDetectedError
from .propagation import PropagationEngine, ReworkExhaustedError

__all__ = [
    "TRUTH_TYPES", "TRUST_LEVELS", "REWORK_STATUS", "TRUTH_STATUS",
    "TruthRecord", "ReworkTask", "TrustAssessment",
    "ProductTruthStore", "LineageGraph", "CycleDetectedError",
    "PropagationEngine", "ReworkExhaustedError",
]