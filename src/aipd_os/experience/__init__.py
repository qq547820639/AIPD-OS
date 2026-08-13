"""面向产品所有者的体验层（对话层）。

把多租户状态服务与执行层的内部细节封装成产品所有者能直接读懂的自然语言视图：
项目摘要、单一决策卡片、会话恢复摘要、制品预览、自然语言指令解析与传播，
以及 P2 新增的自然语言操作闭环、统一 Owner Dashboard 与首次使用引导。
"""
from __future__ import annotations

from .artifact_preview import artifact_preview
from .decision_card import build_decision_card
from .impact_analysis import analyze_impact, estimate_cost_time, type_cn
from .instructions import Instruction, apply_instruction, parse_instruction
from .intent_engine import Intent, build_clarifying_question, parse_intent
from .onboarding import (
    list_examples,
    onboard,
    provider_config_status,
    recover_project,
    reset_project,
)
from .operations import (
    ProgressTracker,
    auto_acceptance,
    auto_rework,
    revert_operation,
    run_operation_loop,
    update_summary,
)
from .owner_dashboard import (
    build_dashboard,
    render_dashboard_json,
    render_dashboard_text,
)
from .project_summary import GATE_NAMES, build_project_summary
from .resume_summary import build_resume_summary
from .views import OwnerView, render_markdown, to_markdown

__all__ = [
    "GATE_NAMES",
    "build_project_summary",
    "build_decision_card",
    "build_resume_summary",
    "artifact_preview",
    "Instruction",
    "parse_instruction",
    "apply_instruction",
    "OwnerView",
    "render_markdown",
    "to_markdown",
    "Intent",
    "parse_intent",
    "build_clarifying_question",
    "analyze_impact",
    "estimate_cost_time",
    "type_cn",
    "ProgressTracker",
    "run_operation_loop",
    "auto_rework",
    "auto_acceptance",
    "update_summary",
    "revert_operation",
    "build_dashboard",
    "render_dashboard_text",
    "render_dashboard_json",
    "onboard",
    "reset_project",
    "recover_project",
    "provider_config_status",
    "list_examples",
]
