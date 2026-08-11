"""Idea Domain capability 声明 + Supervisor 调度辅助（v5.8.1 Commit 11）。

Supervisor（S0-S8 编号不变）只 plan/schedule/route/observe/gate，不实现业务
逻辑——真正执行走 ExecutionRouter → Adapter → Provider/Domain Service。

能力映射（§30-35）：
  - S0 Intake 承载 I0→I1：``idea.structure``（IdeaDecomposer 经
    IdeaStructureAdapter 执行，同一 Idea 身份连续性）；
  - S1 Theory/Research 承载 I1→I2：``claim.research``（ResearchIntegration
    经 ClaimResearchAdapter）+ ``evidence.assess_relation``（评审 relation）；
  - ``idea_truth.refresh``：查询时动态 projection（可选 IdeaTruthSnapshot
    artifact）。
"""
from __future__ import annotations

from typing import Any

# idea.* 能力标识（capability_floor）
IDEA_STRUCTURE_CAPABILITY = "idea.structure"
CLAIM_RESEARCH_CAPABILITY = "claim.research"
EVIDENCE_ASSESS_RELATION_CAPABILITY = "evidence.assess_relation"
IDEA_TRUTH_REFRESH_CAPABILITY = "idea_truth.refresh"

# capability → Supervisor 阶段（S0-S8 编号不变）
CAPABILITY_STAGE_MAP = {
    IDEA_STRUCTURE_CAPABILITY: "S0_intake",
    CLAIM_RESEARCH_CAPABILITY: "S1_theory",
    EVIDENCE_ASSESS_RELATION_CAPABILITY: "S1_theory",
    IDEA_TRUTH_REFRESH_CAPABILITY: "S1_theory",
}

# 全部 idea.* 能力
IDEA_CAPABILITIES = frozenset(CAPABILITY_STAGE_MAP)


def _scope_of(sup: Any) -> tuple[str, str]:
    """从 Supervisor 自身推导 tenant/project（避免调度时 scope 漂移）。"""
    tenant = getattr(sup, "_tenant_id", None) or "default"
    project = getattr(sup, "_project_id", None) or "default"
    return tenant, project


def schedule_idea_structure(sup: Any, idea_id: str, *,
                            tenant_id: str | None = None,
                            project_id: str | None = None,
                            actor: str = "system") -> str:
    """为 I0 Idea 调度 idea.structure 工作项（S0 Intake 承载 I0→I1）。

    返回 work_id。真正执行由 Supervisor → ExecutionRouter →
    IdeaStructureAdapter → IdeaDecomposer.decompose_existing（同一 Idea）。
    tenant/project 缺省取 Supervisor 自身 scope。
    """
    tenant_id, project_id = _scope_of(sup) if (tenant_id is None
                                               or project_id is None) \
        else (tenant_id, project_id)
    wid = sup.add_work(
        CAPABILITY_STAGE_MAP[IDEA_STRUCTURE_CAPABILITY], "idea",
        "结构化分解 Raw Idea（I0→I1）", "I0→I1",
        capability_floor=IDEA_STRUCTURE_CAPABILITY,
        inputs={"idea_id": idea_id, "tenant_id": tenant_id,
                "project_id": project_id, "actor": actor},
    )
    return str(wid)


def schedule_claim_research(sup: Any, claim_id: str, *,
                            capability: str = "research.academic_search",
                            query: str = "", gap_reason: str = "",
                            tenant_id: str | None = None,
                            project_id: str | None = None,
                            actor: str = "system") -> str:
    """为 claim 调度 claim.research 工作项（S1 Theory/Research，I1→I2）。

    返回 work_id。执行 → ClaimResearchAdapter → ResearchIntegration
    link_evidence_for_claim（Search ≠ Assessment：默认 relation
    inconclusive + pending）。tenant/project 缺省取 Supervisor 自身 scope。
    """
    tenant_id, project_id = _scope_of(sup) if (tenant_id is None
                                               or project_id is None) \
        else (tenant_id, project_id)
    wid = sup.add_work(
        CAPABILITY_STAGE_MAP[CLAIM_RESEARCH_CAPABILITY], "claim_research",
        "证据检索（claim.research）", "I1→I2",
        capability_floor=CLAIM_RESEARCH_CAPABILITY,
        inputs={"claim_id": claim_id, "tenant_id": tenant_id,
                "project_id": project_id, "capability": capability,
                "query": query, "gap_reason": gap_reason, "actor": actor},
    )
    return str(wid)


def schedule_idea_truth_refresh(sup: Any, idea_id: str, *,
                                tenant_id: str | None = None,
                                project_id: str | None = None) -> str:
    """调度 idea_truth.refresh 工作项（动态 projection；可选 snapshot artifact）。"""
    tenant_id, project_id = _scope_of(sup) if (tenant_id is None
                                               or project_id is None) \
        else (tenant_id, project_id)
    wid = sup.add_work(
        CAPABILITY_STAGE_MAP[IDEA_TRUTH_REFRESH_CAPABILITY], "idea_truth",
        "Idea Truth 刷新", "projection",
        capability_floor=IDEA_TRUTH_REFRESH_CAPABILITY,
        inputs={"idea_id": idea_id, "tenant_id": tenant_id,
                "project_id": project_id},
    )
    return str(wid)


__all__ = [
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
