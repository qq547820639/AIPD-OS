"""Idea Decomposition（v5.8 Commit 12）。

Raw Idea → Structured Idea + Candidate Claims 的完整分解编排：

- :class:`IdeaDecompositionProvider`：provider 抽象（decompose → StructuredCandidate）；
- :class:`IdeaDecomposer`：schema validation → normalize → persist
  （IdeaService.create + ClaimService.batch_create，默认 A/U）→ audit；
- 无 provider / provider 不可用 → :class:`IdeaDecompositionUnavailable`
  （CAPABILITY_UNAVAILABLE），绝不模拟成功；
- 验证失败 → :class:`IdeaDecompositionValidationError`（FAILED_VALIDATION），
  不写 DB；
- provider 经 :class:`providers.sdk.ProviderRegistry` 注册 capability
  ``idea.decompose``（capability 架构对齐）。

诚实原则：输出 Candidate Claims 是「待验证命题」（默认 epistemic_status=A 或 U），
**绝不产出最终产品事实（V）**。
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any

from jsonschema import Draft7Validator

from aipd_os.providers.sdk import (
    ProbeResult,
    available,
    unavailable,
)
from aipd_os.providers.sdk import (
    Provider as SdkProvider,
)
from aipd_os.state.db import AIPDStateDB

from .claim_service import ClaimService
from .claims import CLAIM_TYPES, Claim
from .models import Idea
from .service import IdeaService

# 分解能力不可用的明确标记（调用方据此诚实降级，不伪造结构化 Idea）。
CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"
# 校验失败的明确标记（不写 DB）。
FAILED_VALIDATION = "FAILED_VALIDATION"

# capability id（ProviderRegistry 注册键）
IDEA_DECOMPOSE_CAPABILITY = "idea.decompose"

# StructuredCandidate 的 JSON Schema（Draft7，jsonschema 校验）
STRUCTURED_CANDIDATE_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": [
        "title", "goal", "problem", "target_user", "desired_outcome",
        "constraints", "claims",
    ],
    "properties": {
        "title": {"type": "string", "minLength": 1},
        "goal": {"type": "string"},
        "problem": {"type": "string"},
        "target_user": {"type": "string"},
        "desired_outcome": {"type": "string"},
        "constraints": {
            "type": "array",
            "items": {"type": "string"},
        },
        "claims": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["claim_type", "statement"],
                "properties": {
                    "claim_type": {
                        "type": "string",
                        "enum": sorted(CLAIM_TYPES),
                    },
                    "statement": {"type": "string", "minLength": 1},
                },
            },
        },
    },
}


@dataclass
class StructuredCandidate:
    """Raw Idea 分解的结构化候选（schema validation 后 persist）。"""

    title: str
    goal: str
    problem: str
    target_user: str
    desired_outcome: str
    constraints: list[str] = field(default_factory=list)
    claims: list[dict[str, str]] = field(default_factory=list)
    source: str = "idea_decomposer"

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "goal": self.goal,
            "problem": self.problem,
            "target_user": self.target_user,
            "desired_outcome": self.desired_outcome,
            "constraints": list(self.constraints),
            "claims": [dict(c) for c in self.claims],
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StructuredCandidate:
        return cls(
            title=data["title"],
            goal=data.get("goal", ""),
            problem=data.get("problem", ""),
            target_user=data.get("target_user", ""),
            desired_outcome=data.get("desired_outcome", ""),
            constraints=list(data.get("constraints", [])),
            claims=[dict(c) for c in data.get("claims", [])],
            source=data.get("source", "idea_decomposer"),
        )


class IdeaDecompositionProvider(abc.ABC):
    """Raw Idea → Structured Idea 的分解契约（provider 实现）。"""

    #: provider 唯一名称（子类覆盖）
    name: str = "unnamed"

    @abc.abstractmethod
    def available(self) -> bool:
        """是否具备真实分解能力（False 表示 external_dependency）。"""

    @abc.abstractmethod
    def decompose(self, raw_input: str,
                  idea_context: dict[str, Any | None] = None) -> StructuredCandidate:
        """把 Raw Idea 分解为结构化候选。能力不可用抛
        :class:`IdeaDecompositionUnavailable`。"""


class IdeaDecompositionUnavailable(RuntimeError):
    """分解能力不可用（CAPABILITY_UNAVAILABLE）。"""

    def __init__(self, message: str = CAPABILITY_UNAVAILABLE) -> None:
        super().__init__(message)


class IdeaDecompositionValidationError(ValueError):
    """结构化候选未通过 schema validation（FAILED_VALIDATION，不写 DB）。"""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(f"idea decomposition validation failed: {'; '.join(errors)}")


class UnavailableProvider(IdeaDecompositionProvider):
    """无真实 provider 时的默认实现：available()=False，decompose 诚实抛错。"""

    name = "unavailable"

    def available(self) -> bool:
        return False

    def decompose(self, raw_input: str,
                  idea_context: dict[str, Any | None] = None) -> StructuredCandidate:
        raise IdeaDecompositionUnavailable(
            f"idea decomposition capability unavailable for input {raw_input!r}; "
            "external_dependency (CAPABILITY_UNAVAILABLE)")


class IdeaDecompositionProviderAdapter(SdkProvider):
    """把 IdeaDecompositionProvider 适配为 providers.sdk.Provider。

    注册到 ProviderRegistry 后以 capability ``idea.decompose`` 路由。
    """

    def __init__(self, inner: IdeaDecompositionProvider) -> None:
        self._inner = inner
        self.name = f"idea-decompose:{inner.name}"

    def capabilities(self) -> list[dict[str, Any]]:
        return [{
            "id": IDEA_DECOMPOSE_CAPABILITY,
            "name": "Idea Decompose",
            "domain": "idea",
            "category": "analysis",
            "evidence": {"impl_file": "src/aipd_os/idea/decomposer.py"},
        }]

    def probe(self) -> ProbeResult:
        if self._inner.available():
            return available()
        return unavailable("idea decomposition provider unavailable (external_dependency)")

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        raw_input = context["raw_input"]
        candidate = self._inner.decompose(raw_input, context.get("idea_context"))
        return {"candidate": candidate.to_dict()}


class IdeaDecomposer:
    """分解编排：provider → schema validation → persist（Idea + Claims）→ audit。"""

    def __init__(self, db: AIPDStateDB,
                 provider: IdeaDecompositionProvider | None = None,
                 tenant_id: str = "default", project_id: str = "default") -> None:
        self._db = db
        self._provider = provider
        self._tenant = tenant_id
        self._project = project_id
        self._ideas = IdeaService(db)
        self._claims = ClaimService(db)

    # ------------------------------------------------------------- validation
    @staticmethod
    def validate(candidate: StructuredCandidate) -> list[str]:
        """校验结构化候选，返回错误列表（空=通过）。"""
        validator = Draft7Validator(STRUCTURED_CANDIDATE_SCHEMA)
        errors: list[str] = []
        data = candidate.to_dict()
        for err in validator.iter_errors(data):
            path = "/".join(str(p) for p in err.absolute_path) or "<root>"
            errors.append(f"{path}: {err.message}")
        return errors

    # ------------------------------------------------------------- persist
    def _persist(self, candidate: StructuredCandidate,
                 actor: str) -> dict[str, Any]:
        idea = self._ideas.create(Idea(
            idea_id="", tenant_id=self._tenant, project_id=self._project,
            title=candidate.title, raw_input="",
            goal=candidate.goal, problem=candidate.problem,
            target_user=candidate.target_user,
            desired_outcome=candidate.desired_outcome,
            constraints_json=str({"constraints": candidate.constraints}),
            source=candidate.source,
            lifecycle_status="structured",
        ), actor=actor)
        created_claims = []
        for c in candidate.claims:
            claim = self._claims.create(Claim(
                claim_id="", tenant_id=self._tenant, project_id=self._project,
                idea_id=idea.idea_id, claim_type=c["claim_type"],
                statement=c["statement"], epistemic_status="A",  # 默认 A，绝不 V
                source="idea_decomposer",
            ), actor=actor)
            created_claims.append(claim.to_dict())
        return {"idea": idea.to_dict(), "claims": created_claims}

    # ------------------------------------------------------------- orchestrate
    def decompose_and_persist(self, raw_input: str,
                              actor: str = "system") -> dict[str, Any]:
        """Raw Idea → Structured Idea + Candidate Claims（默认 A/U，绝不 V）。

        无 provider / provider 不可用 → :class:`IdeaDecompositionUnavailable`
        （不写 DB）；校验失败 → :class:`IdeaDecompositionValidationError`
        （FAILED_VALIDATION，不写 DB）。
        """
        if self._provider is None or not self._provider.available():
            raise IdeaDecompositionUnavailable(
                "idea decomposition capability unavailable; provide a registered "
                "IdeaDecompositionProvider (CAPABILITY_UNAVAILABLE)")
        candidate = self._provider.decompose(
            raw_input, {"raw_input": raw_input, "tenant_id": self._tenant,
                        "project_id": self._project})
        errors = self.validate(candidate)
        if errors:
            raise IdeaDecompositionValidationError(errors)
        result = self._persist(candidate, actor)
        self._db.add_audit(actor, "idea.decompose", self._project, self._tenant,
                           before={"raw_input": raw_input},
                           after={"idea_id": result["idea"]["idea_id"],
                                  "claims": len(result["claims"]),
                                  "status": "ok"})
        return result


__all__ = [
    "CAPABILITY_UNAVAILABLE",
    "FAILED_VALIDATION",
    "IDEA_DECOMPOSE_CAPABILITY",
    "STRUCTURED_CANDIDATE_SCHEMA",
    "StructuredCandidate",
    "IdeaDecompositionProvider",
    "IdeaDecompositionUnavailable",
    "IdeaDecompositionValidationError",
    "UnavailableProvider",
    "IdeaDecompositionProviderAdapter",
    "IdeaDecomposer",
]
