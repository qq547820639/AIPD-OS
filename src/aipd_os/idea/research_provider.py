"""Research Provider contract + ResearchIntegration（v5.8 Commit 13）。

ResearchStudio 检查结果：**/Volumes/Extra/CodeProj/ 下不存在 researchstudio /
research-studio 目录** —— 本轮只实现 Provider contract 与 capability 注册骨架，
诚实标注 external_dependency，不伪造 integration。

能力按真实研究语义拆分（上层 Domain 依赖 capability 不依赖具体 provider 名）：
  - research.academic_search  —— 学术检索
  - research.fulltext         —— 全文获取
  - research.related_work     —— 相关工作检索
  - research.novelty_check    —— 新颖性检查
  - research.idea_spark       —— 灵感/想法生成
  - research.asset_extract    —— 资产抽取

串联（不模拟成功）：
  Claim evidence gap → EvidenceRequest → ExecutionRouter.run(capability, inputs)
  → Evidence（add_evidence 复用 canonical evidence 表）→
  EvidenceRelationService.add（relation_type 由结果分类决定）→ EvidenceGraph 可查。

现有 ``research.search_papers``（Semantic Scholar adapter）保留兼容，不重复。
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any

from aipd_os.execution.adapter import ToolAdapter, external_blocked_error
from aipd_os.execution.execution_router import ExecutionRouter
from aipd_os.state.db import AIPDStateDB

from .claims import Claim
from .evidence_graph import EvidenceGraph
from .evidence_relations import EvidenceRelation, EvidenceRelationService

# 研究能力集合（注册骨架）
RESEARCH_CAPABILITIES: tuple = (
    "research.academic_search",
    "research.fulltext",
    "research.related_work",
    "research.novelty_check",
    "research.idea_spark",
    "research.asset_extract",
)

# relation_type 分类 key（provider 可在结果中显式声明）
RELATION_KEY = "evidence_relation"


class ResearchCapabilityUnavailable(RuntimeError):
    """研究能力不可用（external_dependency；不写 evidence，诚实降级）。"""


class ResearchProvider(abc.ABC):
    """研究 provider 契约（单能力 provider）。"""

    #: provider 唯一名称（子类覆盖）
    name: str = "unnamed"
    #: 单能力 id（如 research.academic_search）
    capability_id: str = ""

    @abc.abstractmethod
    def available(self) -> bool:
        """是否具备真实能力（False 表示 external_dependency）。"""

    @abc.abstractmethod
    def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """执行一次研究调用，返回规范化 payload。"""


class UnavailableResearchProvider(ResearchProvider):
    """无真实后端时的默认实现：available()=False，execute 诚实抛错。"""

    def __init__(self, capability_id: str, reason: str = "") -> None:
        self.capability_id = capability_id
        self.name = f"unavailable:{capability_id}"
        self._reason = reason or (
            f"research capability {capability_id} unavailable (external_dependency)")

    def available(self) -> bool:
        return False

    def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        raise ResearchCapabilityUnavailable(self._reason)


def research_capability_declaration(capability_id: str) -> dict[str, Any]:
    """capability 声明（ProviderRegistry capability_schema 兼容）。"""
    return {
        "id": capability_id,
        "name": capability_id.replace("research.", "").replace("_", " ").title(),
        "domain": "research",
        "category": "retrieval",
        "evidence": {"impl_file": "src/aipd_os/idea/research_provider.py"},
    }


class ResearchToolAdapter(ToolAdapter):
    """把 ResearchProvider 适配为 ToolAdapter（可注册进 AdapterRegistry 并被
    ExecutionRouter 路由；无 provider → external_blocked 诚实降级）。"""

    def __init__(self, provider: ResearchProvider) -> None:
        self._provider = provider

    def capability_id(self) -> str:
        return self._provider.capability_id

    def discover(self) -> dict[str, Any]:
        return {
            "id": self._provider.capability_id,
            "name": self._provider.name,
            "provider": "research-provider",
            "version": "1.0",
            "maturity_ceiling": None,
            "available": self._provider.available(),
        }

    def validate_input(self, input: dict[str, Any]) -> list[str]:
        errors = []
        if not input.get("query") and not input.get("topic"):
            errors.append("'query' or 'topic' required")
        return errors

    def execute(self, input: dict[str, Any]) -> Any:
        if not self._provider.available():
            raise external_blocked_error(
                self._provider.capability_id,
                f"research capability {self._provider.capability_id} unavailable; "
                "external_dependency (honest, no fake results)",
                work_id=input.get("work_id"),
            )
        return self._provider.execute(input)

    def normalize(self, result: Any) -> dict[str, Any]:
        return result if isinstance(result, dict) else {"sources": result}

    def collect_artifacts(self, result: Any) -> list:
        if isinstance(result, dict) and result.get("path"):
            return [result["path"]]
        return []

    def persist_evidence(self, result: Any, run_id: str) -> list:
        if not isinstance(result, dict):
            return []
        refs = [s.get("url") for s in result.get("sources", [])
                if isinstance(s, dict) and s.get("url")]
        refs.append(run_id)
        return refs

    def classify_failure(self, exc: Exception) -> str:
        return "external_blocked"

    def retry_limits(self) -> int:
        return 1

    def fallback_chain(self) -> list[str]:
        return []

    def side_effect_mode(self) -> str:
        return "PURE"


@dataclass
class EvidenceRequest:
    """Claim → 研究能力 的请求（evidence gap 驱动）。"""

    claim_id: str
    tenant_id: str = "default"
    project_id: str = "default"
    capability: str = "research.academic_search"
    gap_reason: str = ""
    inputs: dict[str, Any] = field(default_factory=dict)


class ResearchIntegration:
    """Claim evidence gap → ExecutionRouter → Evidence → EvidenceRelation。"""

    def __init__(self, db: AIPDStateDB,
                 relations: EvidenceRelationService,
                 graph: EvidenceGraph,
                 router: ExecutionRouter | None = None) -> None:
        self._db = db
        self._relations = relations
        self._graph = graph
        self._router = router

    @staticmethod
    def classify_relation(result: dict[str, Any]) -> str:
        """由结果分类决定 relation_type（默认 supports）。

        结果可显式声明 ``evidence_relation``；否则按证据数量保守分类：
        有 sources → supports；空 → inconclusive。
        """
        if not isinstance(result, dict):
            return "inconclusive"
        declared = result.get(RELATION_KEY)
        if declared in ("supports", "contradicts", "partially_supports",
                        "inconclusive", "not_applicable"):
            return declared
        sources = result.get("sources") or []
        return "supports" if sources else "inconclusive"

    def route(self, request: EvidenceRequest) -> dict[str, Any]:
        """经 ExecutionRouter 路由研究能力；无 provider/不可用 → external_blocked。"""
        if self._router is None:
            raise ResearchCapabilityUnavailable(
                f"no ExecutionRouter configured for capability {request.capability}; "
                "external_dependency")
        try:
            out = self._router.run(
                request.claim_id, request.capability, request.inputs,
                context={"work_id": request.claim_id,
                         "project_id": request.project_id,
                         "tenant_id": request.tenant_id})
        except KeyError as exc:
            # AdapterRegistry 无该 capability
            raise ResearchCapabilityUnavailable(
                f"capability {request.capability} not registered; "
                "external_dependency") from exc
        record = out["record"]
        if record.status in ("blocked_external", "failed"):
            raise ResearchCapabilityUnavailable(
                f"research capability {request.capability} unavailable "
                f"(status={record.status}); no evidence written")
        return out["result"] or {}

    def link_evidence_for_claim(self, request: EvidenceRequest,
                                relation_type: str | None = None,
                                actor: str = "system") -> dict[str, Any]:
        """为 claim 拉取研究结果 → 写 canonical evidence → 建 relation。

        无 provider / 无结果 → 抛 :class:`ResearchCapabilityUnavailable`，
        不写 evidence（不模拟成功）。
        """
        # claim 必须存在且同 scope（跨 scope 拒绝）
        self._graph.get_claim(request.tenant_id, request.project_id, request.claim_id)
        result = self.route(request)
        rtype = relation_type or self.classify_relation(result)
        sources = result.get("sources") or []
        if not sources:
            raise ResearchCapabilityUnavailable(
                "research returned no sources; no evidence written (honest)")
        evidence_ids = []
        for src in sources:
            if not isinstance(src, dict) or not src.get("title"):
                continue
            eid = self._db.add_evidence(
                request.tenant_id, request.project_id,
                kind=request.capability, title=src.get("title", "research result"),
                url=src.get("url"), identifier=src.get("identifier"),
                quality=request.gap_reason or "research",
                metadata={"capability": request.capability,
                          "evidence_relation": rtype,
                          "provider": result.get("provider", "")},
            )
            evidence_ids.append(eid)
        if not evidence_ids:
            raise ResearchCapabilityUnavailable(
                "research returned no usable evidence; no evidence written")
        relations = []
        for eid in evidence_ids:
            rel = self._relations.add(EvidenceRelation(
                relation_id="", tenant_id=request.tenant_id,
                project_id=request.project_id, claim_id=request.claim_id,
                evidence_id=eid, relation_type=rtype,
                reasoning_summary=result.get("reasoning_summary", ""),
                created_by=actor,
            ), actor=actor)
            relations.append(rel.to_dict())
        return {"evidence_ids": evidence_ids, "relations": relations,
                "relation_type": rtype}

    def evidence_gaps(self, tenant_id: str, project_id: str) -> list[Claim]:
        """返回无任何 relation 的 claims（evidence gaps）。"""
        return self._graph.get_evidence_gaps(tenant_id, project_id)


__all__ = [
    "RESEARCH_CAPABILITIES",
    "ResearchCapabilityUnavailable",
    "ResearchProvider",
    "UnavailableResearchProvider",
    "research_capability_declaration",
    "ResearchToolAdapter",
    "EvidenceRequest",
    "ResearchIntegration",
]
