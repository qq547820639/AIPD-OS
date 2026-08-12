"""ProductIntelligenceProvider 契约（v5.9.1，§31-32/35-36）。

**职责**：把 Evidence（ClaimAssessment 等）转译为 Product Intelligence
**candidate** 输出（typed input / typed candidate output / schema validation /
provider metadata / generation provenance）。

**核心真实性原则（§4/32）**：
- Provider 输出**永远是 Candidate**（lifecycle=candidate）—— 绝不直接创建
  approved Requirement、绝不直接写 ProductTruth、绝不直接判 READY；
- Domain Service 负责 validate + persist candidate；Owner/Gate 负责 commit；
- **本模块不绑定任何模型供应商**；不内置第二套 LLM client（§36 —— 仓库无
  通用 completion provider 可复用；只建 clean contract + configured hook）；
- 未配置真实 Provider 时，production bootstrap **绝不默认注册 fake**；
  Adapter discover().available=False → runtime probe 诚实
  EXTERNAL_DEPENDENCY / UNAVAILABLE（§35/38）。

候选对象全部带 ``provenance``（provider/model/prompt_version/generated_at），
落库时写入对象 rationale/limitations 或 audit。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Generation provenance（§31）
# ---------------------------------------------------------------------------


@dataclass
class GenerationProvenance:
    """一次生成的来源元信息（可审计）。"""

    provider: str
    model: str = ""
    prompt_version: str = ""
    generated_at: str = ""
    raw_ref: str = ""  # provider 侧原始记录引用（如 request id）

    def to_dict(self) -> dict[str, Any]:
        return {"provider": self.provider, "model": self.model,
                "prompt_version": self.prompt_version,
                "generated_at": self.generated_at, "raw_ref": self.raw_ref}


# ---------------------------------------------------------------------------
# Typed candidate outputs（§32：输出永远是 Candidate）
# ---------------------------------------------------------------------------


@dataclass
class CandidateInsight:
    statement: str
    insight_type: str = "user_problem"
    source_claim_ids: list[str] = field(default_factory=list)
    rationale: str = ""
    limitations: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"statement": self.statement, "insight_type": self.insight_type,
                "source_claim_ids": list(self.source_claim_ids),
                "rationale": self.rationale, "limitations": self.limitations}


@dataclass
class CandidateOpportunity:
    title: str
    statement: str
    source_insight_ids: list[str] = field(default_factory=list)
    target_user: str = ""
    problem: str = ""
    desired_outcome: str = ""
    differentiation: str = ""
    known_alternatives: list[str] = field(default_factory=list)
    evidence_gaps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"title": self.title, "statement": self.statement,
                "source_insight_ids": list(self.source_insight_ids),
                "target_user": self.target_user, "problem": self.problem,
                "desired_outcome": self.desired_outcome,
                "differentiation": self.differentiation,
                "known_alternatives": list(self.known_alternatives),
                "evidence_gaps": list(self.evidence_gaps)}


@dataclass
class CandidatePrinciple:
    statement: str
    source_insight_ids: list[str] = field(default_factory=list)
    rationale: str = ""
    criticality: str = "normal"

    def to_dict(self) -> dict[str, Any]:
        return {"statement": self.statement,
                "source_insight_ids": list(self.source_insight_ids),
                "rationale": self.rationale, "criticality": self.criticality}


@dataclass
class CandidateRequirement:
    title: str
    statement: str
    source_principle_ids: list[str] = field(default_factory=list)
    requirement_type: str = "functional"
    criticality: str = "normal"
    verification_method: str = ""
    nominal_value: str | None = None
    unit: str | None = None
    lower_limit: str | None = None
    upper_limit: str | None = None
    tolerance: str | None = None
    test_condition: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"title": self.title, "statement": self.statement,
                "source_principle_ids": list(self.source_principle_ids),
                "requirement_type": self.requirement_type,
                "criticality": self.criticality,
                "verification_method": self.verification_method,
                "nominal_value": self.nominal_value, "unit": self.unit,
                "lower_limit": self.lower_limit,
                "upper_limit": self.upper_limit,
                "tolerance": self.tolerance,
                "test_condition": self.test_condition}


@dataclass
class CandidateFeature:
    title: str
    description: str
    source_requirement_ids: list[str] = field(default_factory=list)
    feature_type: str = "capability"
    assumptions: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"title": self.title, "description": self.description,
                "source_requirement_ids": list(self.source_requirement_ids),
                "feature_type": self.feature_type,
                "assumptions": list(self.assumptions),
                "constraints": list(self.constraints)}


# ---------------------------------------------------------------------------
# Provider contract
# ---------------------------------------------------------------------------


class ProductProviderError(RuntimeError):
    """Provider 生成失败（配置缺失 / schema 非法 / 生成异常）。"""


class ProductIntelligenceProvider(ABC):
    """Product Intelligence 生成契约（candidate-only）。"""

    provider_name: str = "base"
    model_name: str = ""
    prompt_version: str = ""

    def __init__(self) -> None:
        self.configured: bool = False  # 真实可用凭据/后端（子类覆写）

    # ---- typed generation（每阶段返回 candidate 列表）----
    @abstractmethod
    def derive_insights(self, context: dict[str, Any]) -> list[CandidateInsight]:
        """ClaimAssessment → Insight 候选。context 含 idea/claims/evidence。"""

    @abstractmethod
    def identify_opportunities(
            self, context: dict[str, Any]) -> list[CandidateOpportunity]:
        """Insights → Opportunity 候选（不自动 select —— selection 是
        Owner/Gate 层决策，P0-07）。"""

    @abstractmethod
    def derive_principles(self, context: dict[str, Any]) -> list[CandidatePrinciple]:
        """Insights + Opportunity → ProductPrinciple 候选。"""

    @abstractmethod
    def derive_requirements(
            self, context: dict[str, Any]) -> list[CandidateRequirement]:
        """Principles → Requirement 候选（candidate，非 approved）。"""

    @abstractmethod
    def derive_features(self, context: dict[str, Any]) -> list[CandidateFeature]:
        """Requirements → Feature 候选（candidate，非 approved）。"""

    # ---- provenance ----
    def provenance(self) -> GenerationProvenance:
        from aipd_os.state.db import now_iso
        return GenerationProvenance(
            provider=self.provider_name, model=self.model_name,
            prompt_version=self.prompt_version, generated_at=now_iso())

    # ---- schema validation ----
    @staticmethod
    def validate_candidates(candidates: list[Any], kind: str) -> list[str]:
        """候选对象 schema 校验（§31）。返回错误列表；空 = 合法。"""
        errors: list[str] = []
        for i, c in enumerate(candidates):
            if not isinstance(c, _CANDIDATE_KINDS[kind]):
                errors.append(f"candidate[{i}] not a {kind}")
                continue
            if not getattr(c, "statement", "").strip() and \
                    not getattr(c, "title", "").strip():
                errors.append(f"candidate[{i}] empty statement/title")
        return errors


_CANDIDATE_KINDS = {
    "insight": CandidateInsight,
    "opportunity": CandidateOpportunity,
    "principle": CandidatePrinciple,
    "requirement": CandidateRequirement,
    "feature": CandidateFeature,
}


__all__ = [
    "ProductIntelligenceProvider",
    "ProductProviderError",
    "GenerationProvenance",
    "CandidateInsight",
    "CandidateOpportunity",
    "CandidatePrinciple",
    "CandidateRequirement",
    "CandidateFeature",
]
