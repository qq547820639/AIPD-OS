"""Research Provider contract + ResearchIntegration（v5.8 Commit 13 / v5.8.1 Commit 5-6）。

本模块实现研究能力的 Provider contract（ResearchProvider /
UnavailableResearchProvider / EvidenceRequest / capability 声明）与
:class:`ResearchIntegration` 的**完整实现**（``link_evidence_for_claim``：
Claim evidence gap → 路由 → canonical evidence 去重落库 → per-source
EvidenceRelation → EvidenceGraph 可查）。无真实后端时经
``UnavailableResearchProvider`` 诚实标注 external_dependency，不伪造 integration。

能力按真实研究语义拆分（上层 Domain 依赖 capability 不依赖具体 provider 名）：
  - research.academic_search  —— 学术检索（Search）
  - research.fulltext         —— 全文获取
  - research.related_work     —— 相关工作检索
  - research.novelty_check    —— 新颖性检查
  - research.idea_spark       —— 灵感/想法生成
  - research.asset_extract    —— 资产抽取
  - evidence.assess_relation  —— 关系评估（Assessment，v5.8.1 Commit 5）

v5.8.1 Commit 5（Search ≠ Assessment）：Search provider 只输出 sources，
**不承担关系评估**；检索命中 ≠ 支持 —— 无显式评估时 relation 默认
``inconclusive`` + ``pending``；每 source 单独建 EvidenceRelation。

v5.8.1 Commit 6（canonicalization + provenance）：同一论文经
``get_or_create_evidence`` 按 doi/arxiv_id/identifier/url/title+year 去重，
不重复落库；metadata 记录 retrieval_context / source_metadata / provenance
（gap_reason 不再当 quality）。

串联（不模拟成功）：
  Claim evidence gap → EvidenceRequest → ExecutionRouter.run(capability, inputs)
  → Evidence（get_or_create_evidence 复用 canonical evidence 表）→
  EvidenceRelationService.add（per-source relation）→ EvidenceGraph 可查。

现有 ``research.search_papers``（Semantic Scholar adapter）保留兼容，不重复。
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, cast

from aipd_os.execution.adapter import ToolAdapter, external_blocked_error
from aipd_os.execution.execution_router import ExecutionRouter
from aipd_os.state.db import AIPDStateDB, now_iso

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
    # v5.8.1 Commit 5：Search ≠ Assessment 拆层 —— 关系评估是独立 capability。
    "evidence.assess_relation",
)

# relation_type 分类 key（provider 可在结果中显式声明；legacy）
RELATION_KEY = "evidence_relation"

# v5.8.1 Commit 5：evidence↔claim 关系评估能力（Assessment，独立于 Search）
EVIDENCE_ASSESS_RELATION_CAPABILITY = "evidence.assess_relation"


class ResearchCapabilityUnavailable(RuntimeError):
    """研究能力不可用（external_dependency；不写 evidence，诚实降级）。"""


class ResearchProvider(abc.ABC):
    """研究 provider 契约（单能力 provider）。

    v5.8.1 Commit 5（Search ≠ Assessment 拆层）：Search provider 只负责
    **检索**（输出 sources），**不承担关系评估**。evidence↔claim 的关系判定由
    独立 capability ``evidence.assess_relation`` 提供（:meth:`assess_relation`）；
    本轮定义 contract + CAPABILITY_UNAVAILABLE 路径，完整实现放后续 Commit。
    """

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

    def assess_relation(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """【Assessment capability】评估 evidence↔claim 关系（独立 capability）。

        Search provider 默认不承担评估 → 诚实抛
        :class:`ResearchCapabilityUnavailable`（external_dependency）。
        实现 assess_relation 的 provider 应注册 capability
        ``evidence.assess_relation``。
        """
        raise ResearchCapabilityUnavailable(
            f"evidence assess_relation capability unavailable: provider "
            f"{self.name!r} is a Search provider and does not assess relations "
            "(external_dependency, no fake reasoning)")


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
        """【保守语义，v5.8.1 Commit 5】检索结果不证明支持。

        无显式评估时默认 ``inconclusive`` —— 「检索到 sources」绝不推导为
        ``supports``（Search ≠ Assessment）。结果级显式声明 ``evidence_relation``
        仍尊重（legacy provider 兼容），但新 contract 使用
        ``sources[i].relation.type`` + 调用方显式传 ``relation_type``。
        """
        if not isinstance(result, dict):
            return "inconclusive"
        declared = result.get(RELATION_KEY)
        if declared in ("supports", "contradicts", "partially_supports",
                        "inconclusive", "not_applicable"):
            return cast(str, declared)
        return "inconclusive"

    @staticmethod
    def _extract_source_and_relation(src: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        """从 provider source item 提取 (source_dict, relation_dict)。

        新 contract：``sources: [{source: {...}, relation: {...}}]``；
        legacy contract：``sources: [{title, url, identifier, ...}]``（无 relation）。
        """
        if isinstance(src, dict) and isinstance(src.get("source"), dict):
            source = src["source"]
            relation = src.get("relation") or {}
            if not isinstance(relation, dict):
                relation = {}
            return source, relation
        if isinstance(src, dict):
            return src, {}
        return {}, {}

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
        """为 claim 拉取研究结果 → 写 canonical evidence（去重）→ per-source relation。

        v5.8.1 Commit 5（Search ≠ Assessment + per-source relation）：
        - 检索命中 ≠ 支持：provider 未对某 source 给出 relation 时，该 source
          默认 ``relation_type="inconclusive"``、``review_status="pending"``；
        - 每个 Evidence item 单独建 EvidenceRelation（不同 source 可有不同
          关系：supports / contradicts / inconclusive ...）；
        - ``relation_type`` 参数为调用方显式覆盖（强制所有 source 用该类型）；
        - 不写 quality 伪值：gap_reason 属 retrieval_context，source quality
          放 source_metadata（Commit 6 provenance 完整）。

        无 provider / 无结果 → 抛 :class:`ResearchCapabilityUnavailable`，
        不写 evidence（不模拟成功）。
        """
        # claim 必须存在且同 scope（跨 scope 拒绝）
        self._graph.get_claim(request.tenant_id, request.project_id, request.claim_id)
        result = self.route(request)
        sources = result.get("sources") or []
        if not sources:
            raise ResearchCapabilityUnavailable(
                "research returned no sources; no evidence written (honest)")
        provider_name = result.get("provider", "")
        retrieved_at = now_iso()
        query = (request.inputs.get("query") or request.inputs.get("topic")
                 or request.inputs.get("title") or "")
        evidence_ids = []
        relations = []
        relation_types: list[str] = []
        used_sources = 0
        for src in sources:
            source, relation = self._extract_source_and_relation(src)
            title = source.get("title")
            if not title:
                continue
            used_sources += 1
            # 每 source 独立 relation_type（显式覆盖 > source.relation > 保守默认）
            rtype = relation_type or relation.get("type") or "inconclusive"
            if rtype not in ("supports", "contradicts", "partially_supports",
                             "inconclusive", "not_applicable"):
                rtype = "inconclusive"
            review_status = relation.get("review_status", "pending")
            if review_status not in ("pending", "reviewed", "rejected"):
                review_status = "pending"
            relation_types.append(rtype)
            # v5.8.1 Commit 6：完整 provenance（gap_reason 不再当 quality）
            metadata = {
                "retrieval_context": {
                    "gap_reason": request.gap_reason,
                    "claim_id": request.claim_id,
                    "capability": request.capability,
                    "query": query,
                },
                "source_metadata": {
                    "authors": source.get("authors", []),
                    "year": source.get("year"),
                    "venue": source.get("venue"),
                    "citation_count": source.get("citation_count"),
                    "publication_date": source.get("publication_date"),
                    "doi": source.get("doi"),
                    "arxiv_id": source.get("arxiv_id"),
                    "found_in": source.get("found_in") or provider_name,
                },
                "provenance": {
                    "provider": provider_name,
                    "retrieved_at": retrieved_at,
                    "raw_identifier": source.get("identifier")
                                       or source.get("raw_identifier"),
                    "url": source.get("url"),
                    "title": title,
                },
            }
            eid = self._db.get_or_create_evidence(
                request.tenant_id, request.project_id,
                kind=request.capability, title=title,
                url=source.get("url"), identifier=source.get("identifier"),
                doi=source.get("doi"), arxiv_id=source.get("arxiv_id"),
                metadata=metadata,
            )
            evidence_ids.append(eid)
            # Commit 7：幂等创建 relation（同 claim+evidence+type 已存在 →
            # 返回现有，不重复插入、不误抛 conflict）
            rel, _created = self._relations.get_or_create(EvidenceRelation(
                relation_id="", tenant_id=request.tenant_id,
                project_id=request.project_id, claim_id=request.claim_id,
                evidence_id=eid, relation_type=rtype,
                applicability=relation.get("applicability", ""),
                reasoning_summary=relation.get("reasoning_summary", ""),
                limitations=relation.get("limitations", ""),
                review_status=review_status,
                created_by=actor,
            ), actor=actor)
            relations.append(rel.to_dict())
        if not used_sources:
            raise ResearchCapabilityUnavailable(
                "research returned no usable evidence; no evidence written")
        # 顶层 relation_type：全部同型 → 该型；否则 mixed（per-source 语义）
        if relation_types and len(set(relation_types)) == 1:
            top_type = relation_types[0]
        else:
            top_type = "mixed"
        return {"evidence_ids": evidence_ids, "relations": relations,
                "relation_type": top_type}

    def evidence_gaps(self, tenant_id: str, project_id: str) -> list[Claim]:
        """返回无任何 relation 的 claims（evidence gaps）。"""
        return self._graph.get_evidence_gaps(tenant_id, project_id)


__all__ = [
    "RESEARCH_CAPABILITIES",
    "EVIDENCE_ASSESS_RELATION_CAPABILITY",
    "ResearchCapabilityUnavailable",
    "ResearchProvider",
    "UnavailableResearchProvider",
    "research_capability_declaration",
    "ResearchToolAdapter",
    "EvidenceRequest",
    "ResearchIntegration",
]
