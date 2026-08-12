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

# v5.9 Product Intelligence 能力（S2_product_definition 承载）
PRODUCT_DERIVE_INSIGHTS_CAPABILITY = "product.derive_insights"
PRODUCT_IDENTIFY_OPPORTUNITY_CAPABILITY = "product.identify_opportunity"
PRODUCT_DERIVE_PRINCIPLES_CAPABILITY = "product.derive_principles"
PRODUCT_DERIVE_REQUIREMENTS_CAPABILITY = "product.derive_requirements"
PRODUCT_DERIVE_FEATURES_CAPABILITY = "product.derive_features"
PRODUCT_CREATE_SNAPSHOT_CAPABILITY = "product.create_snapshot"
PRODUCT_DEFINITION_GATE_CAPABILITY = "product.definition_gate"

# capability → Supervisor 阶段（S0-S8 编号不变）
CAPABILITY_STAGE_MAP = {
    IDEA_STRUCTURE_CAPABILITY: "S0_intake",
    CLAIM_RESEARCH_CAPABILITY: "S1_theory",
    EVIDENCE_ASSESS_RELATION_CAPABILITY: "S1_theory",
    IDEA_TRUTH_REFRESH_CAPABILITY: "S1_theory",
    # v5.9：Product Intelligence 编排（Supervisor 只调度，不生成内容）
    PRODUCT_DERIVE_INSIGHTS_CAPABILITY: "S2_product_definition",
    PRODUCT_IDENTIFY_OPPORTUNITY_CAPABILITY: "S2_product_definition",
    PRODUCT_DERIVE_PRINCIPLES_CAPABILITY: "S2_product_definition",
    PRODUCT_DERIVE_REQUIREMENTS_CAPABILITY: "S2_product_definition",
    PRODUCT_DERIVE_FEATURES_CAPABILITY: "S2_product_definition",
    PRODUCT_CREATE_SNAPSHOT_CAPABILITY: "S2_product_definition",
    PRODUCT_DEFINITION_GATE_CAPABILITY: "S2_product_definition",
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


# ---------------------------------------------------------------------------
# v5.9：Product Intelligence 调度（Supervisor 只编排，不生成 Product 内容）
# ---------------------------------------------------------------------------
def schedule_product_derive_insights(sup: Any, idea_id: str, *,
                                     tenant_id: str | None = None,
                                     project_id: str | None = None) -> str:
    """调度 product.derive_insights（S2）：ClaimAssessment → Insight 候选。"""
    tenant_id, project_id = _scope_of(sup) if (tenant_id is None
                                               or project_id is None) \
        else (tenant_id, project_id)
    return str(sup.add_work(
        CAPABILITY_STAGE_MAP[PRODUCT_DERIVE_INSIGHTS_CAPABILITY],
        "product_intelligence", "Insight 推导（candidate）", "I2→PD",
        capability_floor=PRODUCT_DERIVE_INSIGHTS_CAPABILITY,
        inputs={"idea_id": idea_id, "tenant_id": tenant_id,
                "project_id": project_id},
    ))


def schedule_product_definition_gate(sup: Any, *,
                                     tenant_id: str | None = None,
                                     project_id: str | None = None) -> str:
    """调度 product.definition_gate（S2）：deterministic Gate 评估。"""
    tenant_id, project_id = _scope_of(sup) if (tenant_id is None
                                               or project_id is None) \
        else (tenant_id, project_id)
    return str(sup.add_work(
        CAPABILITY_STAGE_MAP[PRODUCT_DEFINITION_GATE_CAPABILITY],
        "product_intelligence", "Product Definition Gate", "gate",
        capability_floor=PRODUCT_DEFINITION_GATE_CAPABILITY,
        inputs={"tenant_id": tenant_id, "project_id": project_id},
    ))


def schedule_product_identify_opportunity(sup: Any, idea_id: str, *,
                                          tenant_id: str | None = None,
                                          project_id: str | None = None) -> str:
    """调度 product.identify_opportunity（S2）：Insights → Opportunity 候选。"""
    tenant_id, project_id = _scope_of(sup) if (tenant_id is None
                                               or project_id is None) \
        else (tenant_id, project_id)
    return str(sup.add_work(
        CAPABILITY_STAGE_MAP[PRODUCT_IDENTIFY_OPPORTUNITY_CAPABILITY],
        "product_intelligence", "Opportunity 识别（candidate）", "I2→PD",
        capability_floor=PRODUCT_IDENTIFY_OPPORTUNITY_CAPABILITY,
        inputs={"idea_id": idea_id, "tenant_id": tenant_id,
                "project_id": project_id},
    ))


def schedule_product_derive_principles(sup: Any, idea_id: str, *,
                                       tenant_id: str | None = None,
                                       project_id: str | None = None) -> str:
    """调度 product.derive_principles（S2）：Insights+Opportunity → 原则候选。"""
    tenant_id, project_id = _scope_of(sup) if (tenant_id is None
                                               or project_id is None) \
        else (tenant_id, project_id)
    return str(sup.add_work(
        CAPABILITY_STAGE_MAP[PRODUCT_DERIVE_PRINCIPLES_CAPABILITY],
        "product_intelligence", "ProductPrinciple 推导（candidate）", "I2→PD",
        capability_floor=PRODUCT_DERIVE_PRINCIPLES_CAPABILITY,
        inputs={"idea_id": idea_id, "tenant_id": tenant_id,
                "project_id": project_id},
    ))


def schedule_product_derive_requirements(sup: Any, idea_id: str, *,
                                         tenant_id: str | None = None,
                                         project_id: str | None = None) -> str:
    """调度 product.derive_requirements（S2）：Principles → Requirement 候选。"""
    tenant_id, project_id = _scope_of(sup) if (tenant_id is None
                                               or project_id is None) \
        else (tenant_id, project_id)
    return str(sup.add_work(
        CAPABILITY_STAGE_MAP[PRODUCT_DERIVE_REQUIREMENTS_CAPABILITY],
        "product_intelligence", "Requirement 推导（candidate）", "I2→PD",
        capability_floor=PRODUCT_DERIVE_REQUIREMENTS_CAPABILITY,
        inputs={"idea_id": idea_id, "tenant_id": tenant_id,
                "project_id": project_id},
    ))


def schedule_product_derive_features(sup: Any, idea_id: str, *,
                                     tenant_id: str | None = None,
                                     project_id: str | None = None) -> str:
    """调度 product.derive_features（S2）：Requirements → Feature 候选。"""
    tenant_id, project_id = _scope_of(sup) if (tenant_id is None
                                               or project_id is None) \
        else (tenant_id, project_id)
    return str(sup.add_work(
        CAPABILITY_STAGE_MAP[PRODUCT_DERIVE_FEATURES_CAPABILITY],
        "product_intelligence", "Feature 推导（candidate）", "I2→PD",
        capability_floor=PRODUCT_DERIVE_FEATURES_CAPABILITY,
        inputs={"idea_id": idea_id, "tenant_id": tenant_id,
                "project_id": project_id},
    ))


def schedule_product_create_snapshot(sup: Any, *,
                                     tenant_id: str | None = None,
                                     project_id: str | None = None) -> str:
    """调度 product.create_snapshot（S2）：冻结 immutable snapshot。"""
    tenant_id, project_id = _scope_of(sup) if (tenant_id is None
                                               or project_id is None) \
        else (tenant_id, project_id)
    return str(sup.add_work(
        CAPABILITY_STAGE_MAP[PRODUCT_CREATE_SNAPSHOT_CAPABILITY],
        "product_intelligence", "冻结 Product Definition Snapshot", "PD",
        capability_floor=PRODUCT_CREATE_SNAPSHOT_CAPABILITY,
        inputs={"tenant_id": tenant_id, "project_id": project_id},
    ))


# §42/44：正式 S2 执行链（Supervisor 只调度；Provider/Domain 生成内容）
PRODUCT_CHAIN_STEPS = (
    ("derive_insights", "product.derive_insights",
     schedule_product_derive_insights),
    ("identify_opportunity", "product.identify_opportunity",
     schedule_product_identify_opportunity),
    ("derive_principles", "product.derive_principles",
     schedule_product_derive_principles),
    ("derive_requirements", "product.derive_requirements",
     schedule_product_derive_requirements),
    ("derive_features", "product.derive_features",
     schedule_product_derive_features),
    ("create_snapshot", "product.create_snapshot",
     schedule_product_create_snapshot),
    ("definition_gate", "product.definition_gate",
     schedule_product_definition_gate),
)


def schedule_product_intelligence_chain(sup: Any, idea_id: str, *,
                                        tenant_id: str | None = None,
                                        project_id: str | None = None,
                                        steps: tuple[str, ...] | None = None
                                        ) -> list[str]:
    """调度完整 S2 链（§42）：derive_insights → identify_opportunity →
    derive_principles → derive_requirements → derive_features →
    create_snapshot → definition_gate。steps 可裁剪（按阶段名）。

    Supervisor 不生成任何产品内容 —— 全部经 Adapter → Provider → Service。
    """
    tenant_id, project_id = _scope_of(sup) if (tenant_id is None
                                               or project_id is None) \
        else (tenant_id, project_id)
    want = set(steps or [s[0] for s in PRODUCT_CHAIN_STEPS])
    work_ids: list[str] = []
    # 显式分支（mypy：不同 fn 签名不合并循环）
    if "derive_insights" in want:
        work_ids.append(schedule_product_derive_insights(
            sup, idea_id, tenant_id=tenant_id, project_id=project_id))
    if "identify_opportunity" in want:
        work_ids.append(schedule_product_identify_opportunity(
            sup, idea_id, tenant_id=tenant_id, project_id=project_id))
    if "derive_principles" in want:
        work_ids.append(schedule_product_derive_principles(
            sup, idea_id, tenant_id=tenant_id, project_id=project_id))
    if "derive_requirements" in want:
        work_ids.append(schedule_product_derive_requirements(
            sup, idea_id, tenant_id=tenant_id, project_id=project_id))
    if "derive_features" in want:
        work_ids.append(schedule_product_derive_features(
            sup, idea_id, tenant_id=tenant_id, project_id=project_id))
    if "create_snapshot" in want:
        work_ids.append(schedule_product_create_snapshot(
            sup, tenant_id=tenant_id, project_id=project_id))
    if "definition_gate" in want:
        work_ids.append(schedule_product_definition_gate(
            sup, tenant_id=tenant_id, project_id=project_id))
    return work_ids


__all__ = [
    "IDEA_STRUCTURE_CAPABILITY",
    "CLAIM_RESEARCH_CAPABILITY",
    "EVIDENCE_ASSESS_RELATION_CAPABILITY",
    "IDEA_TRUTH_REFRESH_CAPABILITY",
    "PRODUCT_DERIVE_INSIGHTS_CAPABILITY",
    "PRODUCT_IDENTIFY_OPPORTUNITY_CAPABILITY",
    "PRODUCT_DERIVE_PRINCIPLES_CAPABILITY",
    "PRODUCT_DERIVE_REQUIREMENTS_CAPABILITY",
    "PRODUCT_DERIVE_FEATURES_CAPABILITY",
    "PRODUCT_CREATE_SNAPSHOT_CAPABILITY",
    "PRODUCT_DEFINITION_GATE_CAPABILITY",
    "CAPABILITY_STAGE_MAP",
    "IDEA_CAPABILITIES",
    "schedule_idea_structure",
    "schedule_claim_research",
    "schedule_idea_truth_refresh",
    "schedule_product_derive_insights",
    "schedule_product_identify_opportunity",
    "schedule_product_derive_principles",
    "schedule_product_derive_requirements",
    "schedule_product_derive_features",
    "schedule_product_create_snapshot",
    "schedule_product_definition_gate",
    "schedule_product_intelligence_chain",
    "PRODUCT_CHAIN_STEPS",
]
