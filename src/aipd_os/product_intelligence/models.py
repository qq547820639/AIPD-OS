"""Product Intelligence Domain：Insight → Opportunity → ProductPrinciple →
Requirement → Feature（v5.9）。

**不是第二个 Truth Store**：全部复用 AIPDStateDB（migration v10 五张表），
lineage 复用 canonical LineageService（dependencies 表），不建平行 lineage。

域语义（提示词 §31-47）：
- **Insight**：从 ≥1 个 ClaimAssessment 推导出的可决策解释性结论（非论文摘要）；
- **Opportunity**：基于 Evidence 真正值得解决的产品机会（必须能追溯
  ClaimAssessment → Insight）；
- **ProductPrinciple**：Evidence-backed 设计/产品规则（必须回答 WHY，
  沿 lineage 追溯到 Evidence→Source）；
- **Requirement**：连接 Product Intelligence 与 Engineering/NPI/MMD 的关键对象
  （definition_status 与 epistemic_status 完全分离；不适用字段 = NULL）；
- **Feature**：Requirement 的产品实现选择（必须关联 ≥1 个 Requirement；
  Gate 前是 candidate，不得自行成为 Requirement / Product Truth）。

真实性子（§33/43/47）：LLM/分析产出先是 **candidate**（lifecycle=candidate /
definition_status=RECOMMENDED 等），**绝不自动 verified/committed**；只有
Product Definition Gate + Owner Decision 批准后才进入 Product Truth。

本模块不依赖任何 LLM SDK；provider 契约见 :mod:`provider`。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# 共享枚举
# ---------------------------------------------------------------------------

# Definition Status（第三正交维度；与 epistemic_status 完全分离）
DEFINITION_STATUSES = frozenset({
    "CONFIRMED", "DERIVED", "RECOMMENDED", "ESTIMATED",
    "TBD", "CONFLICT", "OBSOLETE",
})
DEFINITION_STATUS_DEFAULT = "RECOMMENDED"

# 对象生命周期（candidate = Gate 前/未批准；active = 推进中）
LIFECYCLE_CANDIDATE = "candidate"
LIFECYCLE_ACTIVE = "active"
LIFECYCLE_SUPERSEDED = "superseded"
LIFECYCLE_ARCHIVED = "archived"
LIFECYCLE_STATUSES = frozenset({
    LIFECYCLE_CANDIDATE, LIFECYCLE_ACTIVE,
    LIFECYCLE_SUPERSEDED, LIFECYCLE_ARCHIVED,
})

# criticality（Requirement/Principle；未来可扩 CTQ）
CRITICALITY_CRITICAL = "critical"
CRITICALITY_IMPORTANT = "important"
CRITICALITY_NORMAL = "normal"
CRITICALITIES = frozenset({CRITICALITY_CRITICAL, CRITICALITY_IMPORTANT,
                           CRITICALITY_NORMAL})

# Insight 类型（可扩展；不硬约束）
INSIGHT_TYPES = frozenset({
    "user_problem", "behavior", "mechanism", "technology",
    "market", "business", "safety", "regulatory", "competitive",
})

# Opportunity 类型
OPPORTUNITY_TYPES = frozenset({
    "new_product", "improvement", "cost_reduction", "market_entry",
    "risk_mitigation", "platform",
})

# Requirement 类型（§39：为 NPI/MMD 预留，不过度约束）
REQUIREMENT_TYPES = frozenset({
    "user", "functional", "performance", "interaction", "interface",
    "safety", "regulatory", "mechanical", "electrical", "thermal",
    "material", "manufacturing", "quality", "service", "cost", "business",
})

# Feature 类型
FEATURE_TYPES = frozenset({
    "capability", "mode", "workflow", "interface", "automation",
    "integration", "optimization",
})

# 空 JSON 序列化
_EMPTY_JSON = "[]"


def _json(value: Any) -> str:
    return json.dumps(list(value) if isinstance(value, (list, tuple, set))
                      else value, ensure_ascii=False, sort_keys=True)


def _parse_json_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return []
    if isinstance(parsed, list):
        return [str(x) for x in parsed]
    return []


# ---------------------------------------------------------------------------
# Domain 对象
# ---------------------------------------------------------------------------


@dataclass
class Insight:
    """从 ClaimAssessment 推导的可决策解释性结论。

    - ``source_claim_ids`` 至少 1 个（deterministic lineage 校验）；
    - ``epistemic_status`` 表达认知状态（默认 A=Assumption，绝不默认 V）。
    """

    insight_id: str
    tenant_id: str = "default"
    project_id: str = "default"
    idea_id: str = ""
    statement: str = ""
    insight_type: str = "user_problem"
    source_claim_ids: list[str] = field(default_factory=list)
    source_assessment_versions: list[str] = field(default_factory=list)
    epistemic_status: str = "A"
    lifecycle_status: str = LIFECYCLE_CANDIDATE
    rationale: str = ""
    limitations: str = ""
    version_no: int = 1
    created_at: str | None = None
    updated_at: str | None = None

    def __post_init__(self) -> None:
        if self.insight_type not in INSIGHT_TYPES:
            raise ValueError(f"invalid insight_type {self.insight_type!r}")
        if self.lifecycle_status not in LIFECYCLE_STATUSES:
            raise ValueError(
                f"invalid lifecycle_status {self.lifecycle_status!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "insight_id": self.insight_id, "tenant_id": self.tenant_id,
            "project_id": self.project_id, "idea_id": self.idea_id,
            "statement": self.statement, "insight_type": self.insight_type,
            "source_claim_ids": self.source_claim_ids,
            "source_assessment_versions": self.source_assessment_versions,
            "epistemic_status": self.epistemic_status,
            "lifecycle_status": self.lifecycle_status,
            "rationale": self.rationale, "limitations": self.limitations,
            "version_no": self.version_no, "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Insight:
        return cls(
            insight_id=data["insight_id"],
            tenant_id=data.get("tenant_id", "default"),
            project_id=data.get("project_id", "default"),
            idea_id=data.get("idea_id", ""),
            statement=data.get("statement", ""),
            insight_type=data.get("insight_type", "user_problem"),
            source_claim_ids=_parse_json_list(data.get("source_claim_ids_json")
                                              or data.get("source_claim_ids")),
            source_assessment_versions=_parse_json_list(
                data.get("source_assessment_versions_json")
                or data.get("source_assessment_versions")),
            epistemic_status=data.get("epistemic_status", "A"),
            lifecycle_status=data.get("lifecycle_status", LIFECYCLE_CANDIDATE),
            rationale=data.get("rationale", ""),
            limitations=data.get("limitations", ""),
            version_no=data.get("version_no", 1),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


@dataclass
class Opportunity:
    """基于 Evidence 的产品机会（必须可追溯 ClaimAssessment → Insight）。"""

    opportunity_id: str
    tenant_id: str = "default"
    project_id: str = "default"
    idea_id: str = ""
    title: str = ""
    statement: str = ""
    target_user: str = ""
    problem: str = ""
    desired_outcome: str = ""
    opportunity_type: str = "new_product"
    source_insight_ids: list[str] = field(default_factory=list)
    differentiation: str = ""
    known_alternatives: list[str] = field(default_factory=list)
    evidence_gaps: list[str] = field(default_factory=list)
    lifecycle_status: str = LIFECYCLE_CANDIDATE
    epistemic_status: str = "A"
    version_no: int = 1
    created_at: str | None = None
    updated_at: str | None = None

    def __post_init__(self) -> None:
        if self.opportunity_type not in OPPORTUNITY_TYPES:
            raise ValueError(
                f"invalid opportunity_type {self.opportunity_type!r}")
        if self.lifecycle_status not in LIFECYCLE_STATUSES:
            raise ValueError(
                f"invalid lifecycle_status {self.lifecycle_status!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "tenant_id": self.tenant_id, "project_id": self.project_id,
            "idea_id": self.idea_id, "title": self.title,
            "statement": self.statement, "target_user": self.target_user,
            "problem": self.problem, "desired_outcome": self.desired_outcome,
            "opportunity_type": self.opportunity_type,
            "source_insight_ids": self.source_insight_ids,
            "differentiation": self.differentiation,
            "known_alternatives": self.known_alternatives,
            "evidence_gaps": self.evidence_gaps,
            "lifecycle_status": self.lifecycle_status,
            "epistemic_status": self.epistemic_status,
            "version_no": self.version_no, "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Opportunity:
        return cls(
            opportunity_id=data["opportunity_id"],
            tenant_id=data.get("tenant_id", "default"),
            project_id=data.get("project_id", "default"),
            idea_id=data.get("idea_id", ""),
            title=data.get("title", ""),
            statement=data.get("statement", ""),
            target_user=data.get("target_user", ""),
            problem=data.get("problem", ""),
            desired_outcome=data.get("desired_outcome", ""),
            opportunity_type=data.get("opportunity_type", "new_product"),
            source_insight_ids=_parse_json_list(
                data.get("source_insight_ids_json")
                or data.get("source_insight_ids")),
            differentiation=data.get("differentiation", ""),
            known_alternatives=_parse_json_list(
                data.get("known_alternatives_json")
                or data.get("known_alternatives")),
            evidence_gaps=_parse_json_list(data.get("evidence_gaps_json")
                                           or data.get("evidence_gaps")),
            lifecycle_status=data.get("lifecycle_status", LIFECYCLE_CANDIDATE),
            epistemic_status=data.get("epistemic_status", "A"),
            version_no=data.get("version_no", 1),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


@dataclass
class ProductPrinciple:
    """Evidence-backed 设计/产品规则（必须能回答 WHY）。"""

    principle_id: str
    tenant_id: str = "default"
    project_id: str = "default"
    opportunity_id: str = ""
    statement: str = ""
    rationale: str = ""
    source_insight_ids: list[str] = field(default_factory=list)
    source_claim_ids: list[str] = field(default_factory=list)
    definition_status: str = DEFINITION_STATUS_DEFAULT
    epistemic_status: str = "A"
    lifecycle_status: str = LIFECYCLE_CANDIDATE
    criticality: str = CRITICALITY_NORMAL
    version_no: int = 1
    created_at: str | None = None
    updated_at: str | None = None

    def __post_init__(self) -> None:
        if self.definition_status not in DEFINITION_STATUSES:
            raise ValueError(
                f"invalid definition_status {self.definition_status!r}")
        if self.lifecycle_status not in LIFECYCLE_STATUSES:
            raise ValueError(
                f"invalid lifecycle_status {self.lifecycle_status!r}")
        if self.criticality not in CRITICALITIES:
            raise ValueError(f"invalid criticality {self.criticality!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "principle_id": self.principle_id, "tenant_id": self.tenant_id,
            "project_id": self.project_id, "opportunity_id": self.opportunity_id,
            "statement": self.statement, "rationale": self.rationale,
            "source_insight_ids": self.source_insight_ids,
            "source_claim_ids": self.source_claim_ids,
            "definition_status": self.definition_status,
            "epistemic_status": self.epistemic_status,
            "lifecycle_status": self.lifecycle_status,
            "criticality": self.criticality, "version_no": self.version_no,
            "created_at": self.created_at, "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProductPrinciple:
        return cls(
            principle_id=data["principle_id"],
            tenant_id=data.get("tenant_id", "default"),
            project_id=data.get("project_id", "default"),
            opportunity_id=data.get("opportunity_id", ""),
            statement=data.get("statement", ""),
            rationale=data.get("rationale", ""),
            source_insight_ids=_parse_json_list(
                data.get("source_insight_ids_json")
                or data.get("source_insight_ids")),
            source_claim_ids=_parse_json_list(
                data.get("source_claim_ids_json")
                or data.get("source_claim_ids")),
            definition_status=data.get("definition_status",
                                       DEFINITION_STATUS_DEFAULT),
            epistemic_status=data.get("epistemic_status", "A"),
            lifecycle_status=data.get("lifecycle_status", LIFECYCLE_CANDIDATE),
            criticality=data.get("criticality", CRITICALITY_NORMAL),
            version_no=data.get("version_no", 1),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


@dataclass
class Requirement:
    """v5.9 最关键对象：连接 Product Intelligence 与 Engineering/NPI/MMD。

    不适用字段一律 NULL（禁止空字符串/0/0.5 作为 unknown sentinel）。
    """

    requirement_id: str
    tenant_id: str = "default"
    project_id: str = "default"
    title: str = ""
    statement: str = ""
    requirement_type: str = "functional"
    definition_status: str = DEFINITION_STATUS_DEFAULT
    epistemic_status: str = "A"
    lifecycle_status: str = LIFECYCLE_CANDIDATE
    criticality: str = CRITICALITY_NORMAL
    nominal_value: str | None = None
    unit: str | None = None
    lower_limit: str | None = None
    upper_limit: str | None = None
    tolerance: str | None = None
    test_condition: str | None = None
    rationale: str = ""
    source_principle_ids: list[str] = field(default_factory=list)
    source_evidence_refs: list[str] = field(default_factory=list)
    derivation_method: str = ""
    derivation_input_refs: list[str] = field(default_factory=list)
    verification_method: str = ""
    verification_test_refs: list[str] = field(default_factory=list)
    affected_item_refs: list[str] = field(default_factory=list)
    required_by_gate: str = ""
    owner: str = ""
    version_no: int = 1
    created_at: str | None = None
    updated_at: str | None = None

    def __post_init__(self) -> None:
        if self.requirement_type not in REQUIREMENT_TYPES:
            raise ValueError(
                f"invalid requirement_type {self.requirement_type!r}")
        if self.definition_status not in DEFINITION_STATUSES:
            raise ValueError(
                f"invalid definition_status {self.definition_status!r}")
        if self.lifecycle_status not in LIFECYCLE_STATUSES:
            raise ValueError(
                f"invalid lifecycle_status {self.lifecycle_status!r}")
        if self.criticality not in CRITICALITIES:
            raise ValueError(f"invalid criticality {self.criticality!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "tenant_id": self.tenant_id, "project_id": self.project_id,
            "title": self.title, "statement": self.statement,
            "requirement_type": self.requirement_type,
            "definition_status": self.definition_status,
            "epistemic_status": self.epistemic_status,
            "lifecycle_status": self.lifecycle_status,
            "criticality": self.criticality,
            "nominal_value": self.nominal_value, "unit": self.unit,
            "lower_limit": self.lower_limit, "upper_limit": self.upper_limit,
            "tolerance": self.tolerance, "test_condition": self.test_condition,
            "rationale": self.rationale,
            "source_principle_ids": self.source_principle_ids,
            "source_evidence_refs": self.source_evidence_refs,
            "derivation_method": self.derivation_method,
            "derivation_input_refs": self.derivation_input_refs,
            "verification_method": self.verification_method,
            "verification_test_refs": self.verification_test_refs,
            "affected_item_refs": self.affected_item_refs,
            "required_by_gate": self.required_by_gate, "owner": self.owner,
            "version_no": self.version_no, "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Requirement:
        return cls(
            requirement_id=data["requirement_id"],
            tenant_id=data.get("tenant_id", "default"),
            project_id=data.get("project_id", "default"),
            title=data.get("title", ""),
            statement=data.get("statement", ""),
            requirement_type=data.get("requirement_type", "functional"),
            definition_status=data.get("definition_status",
                                       DEFINITION_STATUS_DEFAULT),
            epistemic_status=data.get("epistemic_status", "A"),
            lifecycle_status=data.get("lifecycle_status", LIFECYCLE_CANDIDATE),
            criticality=data.get("criticality", CRITICALITY_NORMAL),
            nominal_value=data.get("nominal_value"),
            unit=data.get("unit"),
            lower_limit=data.get("lower_limit"),
            upper_limit=data.get("upper_limit"),
            tolerance=data.get("tolerance"),
            test_condition=data.get("test_condition"),
            rationale=data.get("rationale", ""),
            source_principle_ids=_parse_json_list(
                data.get("source_principle_ids_json")
                or data.get("source_principle_ids")),
            source_evidence_refs=_parse_json_list(
                data.get("source_evidence_refs_json")
                or data.get("source_evidence_refs")),
            derivation_method=data.get("derivation_method", ""),
            derivation_input_refs=_parse_json_list(
                data.get("derivation_input_refs_json")
                or data.get("derivation_input_refs")),
            verification_method=data.get("verification_method", ""),
            verification_test_refs=_parse_json_list(
                data.get("verification_test_refs_json")
                or data.get("verification_test_refs")),
            affected_item_refs=_parse_json_list(
                data.get("affected_item_refs_json")
                or data.get("affected_item_refs")),
            required_by_gate=data.get("required_by_gate", ""),
            owner=data.get("owner", ""),
            version_no=data.get("version_no", 1),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


@dataclass
class Feature:
    """Requirement 的产品实现选择（必须关联 ≥1 个 Requirement）。

    Gate 前是 candidate；Gate 批准后才进入 Product Truth。
    """

    feature_id: str
    tenant_id: str = "default"
    project_id: str = "default"
    title: str = ""
    description: str = ""
    feature_type: str = "capability"
    source_requirement_ids: list[str] = field(default_factory=list)
    source_principle_ids: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    definition_status: str = DEFINITION_STATUS_DEFAULT
    epistemic_status: str = "A"
    lifecycle_status: str = LIFECYCLE_CANDIDATE
    validation_required: bool = False
    version_no: int = 1
    created_at: str | None = None
    updated_at: str | None = None

    def __post_init__(self) -> None:
        if self.feature_type not in FEATURE_TYPES:
            raise ValueError(f"invalid feature_type {self.feature_type!r}")
        if self.definition_status not in DEFINITION_STATUSES:
            raise ValueError(
                f"invalid definition_status {self.definition_status!r}")
        if self.lifecycle_status not in LIFECYCLE_STATUSES:
            raise ValueError(
                f"invalid lifecycle_status {self.lifecycle_status!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_id": self.feature_id, "tenant_id": self.tenant_id,
            "project_id": self.project_id, "title": self.title,
            "description": self.description, "feature_type": self.feature_type,
            "source_requirement_ids": self.source_requirement_ids,
            "source_principle_ids": self.source_principle_ids,
            "assumptions": self.assumptions, "constraints": self.constraints,
            "definition_status": self.definition_status,
            "epistemic_status": self.epistemic_status,
            "lifecycle_status": self.lifecycle_status,
            "validation_required": self.validation_required,
            "version_no": self.version_no, "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Feature:
        return cls(
            feature_id=data["feature_id"],
            tenant_id=data.get("tenant_id", "default"),
            project_id=data.get("project_id", "default"),
            title=data.get("title", ""),
            description=data.get("description", ""),
            feature_type=data.get("feature_type", "capability"),
            source_requirement_ids=_parse_json_list(
                data.get("source_requirement_ids_json")
                or data.get("source_requirement_ids")),
            source_principle_ids=_parse_json_list(
                data.get("source_principle_ids_json")
                or data.get("source_principle_ids")),
            assumptions=_parse_json_list(data.get("assumptions_json")
                                         or data.get("assumptions")),
            constraints=_parse_json_list(data.get("constraints_json")
                                         or data.get("constraints")),
            definition_status=data.get("definition_status",
                                       DEFINITION_STATUS_DEFAULT),
            epistemic_status=data.get("epistemic_status", "A"),
            lifecycle_status=data.get("lifecycle_status", LIFECYCLE_CANDIDATE),
            validation_required=bool(data.get("validation_required", False)),
            version_no=data.get("version_no", 1),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


__all__ = [
    "DEFINITION_STATUSES", "DEFINITION_STATUS_DEFAULT",
    "LIFECYCLE_CANDIDATE", "LIFECYCLE_ACTIVE", "LIFECYCLE_SUPERSEDED",
    "LIFECYCLE_ARCHIVED", "LIFECYCLE_STATUSES",
    "CRITICALITY_CRITICAL", "CRITICALITY_IMPORTANT", "CRITICALITY_NORMAL",
    "CRITICALITIES",
    "INSIGHT_TYPES", "OPPORTUNITY_TYPES", "REQUIREMENT_TYPES", "FEATURE_TYPES",
    "Insight", "Opportunity", "ProductPrinciple", "Requirement", "Feature",
]
