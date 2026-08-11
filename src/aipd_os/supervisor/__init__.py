"""Supervisor 包（从 scripts/aipd_supervisor.py 迁移，P1-1）。

核心 Supervisor 已迁入 ``aipd_os.supervisor``；``scripts/aipd_supervisor.py``
保留为薄兼容 wrapper（CLI 与旧 ``from aipd_supervisor import Supervisor`` 用法
不受影响）。runtime 包不再依赖 scripts。

后续可细分为子模块：
- ``lifecycle``：阶段推进（supervisor_phase_runs）
- ``work_queue``：工作项领取/依赖/返工（supervisor_work_items）
- ``quality_gate``：独立质量门/审查（supervisor_reviews）
- ``models``：能力登记/血缘/声明（supervisor_capabilities/lineage/claims）
"""
from __future__ import annotations

from .idea_capabilities import (
    CAPABILITY_STAGE_MAP,
    CLAIM_RESEARCH_CAPABILITY,
    EVIDENCE_ASSESS_RELATION_CAPABILITY,
    IDEA_CAPABILITIES,
    IDEA_STRUCTURE_CAPABILITY,
    IDEA_TRUTH_REFRESH_CAPABILITY,
    schedule_claim_research,
    schedule_idea_structure,
    schedule_idea_truth_refresh,
)
from .supervisor import (
    PHASES,
    SCHEMA,
    SUPERVISOR_LEGACY_DECISIONS_SCHEMA,
    SUPERVISOR_LEGACY_DECISIONS_TABLE,
    WORK_STATUSES,
    Supervisor,
    jd,
    main,
    now,
    parser,
)

__all__ = [
    "Supervisor",
    "PHASES",
    "WORK_STATUSES",
    "SCHEMA",
    "SUPERVISOR_LEGACY_DECISIONS_TABLE",
    "SUPERVISOR_LEGACY_DECISIONS_SCHEMA",
    "now",
    "jd",
    "parser",
    "main",
    # v5.8.1 Commit 11：idea.* capability 声明 + 调度辅助
    "IDEA_STRUCTURE_CAPABILITY",
    "CLAIM_RESEARCH_CAPABILITY",
    "EVIDENCE_ASSESS_RELATION_CAPABILITY",
    "IDEA_TRUTH_REFRESH_CAPABILITY",
    "CAPABILITY_STAGE_MAP",
    "IDEA_CAPABILITIES",
    "schedule_idea_structure",
    "schedule_claim_research",
    "schedule_idea_truth_refresh",
]
