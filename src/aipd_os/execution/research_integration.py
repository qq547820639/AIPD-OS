"""研究能力的执行侧装配（ResearchToolAdapter + ResearchIntegration）。

从 ``aipd_os.idea.research_provider`` 下沉至此，消除 idea（数据/契约层）
对 execution（执行层）的反向依赖（Q-3 / N-4）。

- :class:`ResearchToolAdapter`：把 :class:`~aipd_os.idea.research_provider.ResearchProvider`
  适配为 :class:`ToolAdapter`，可注册进 AdapterRegistry 并被 ExecutionRouter 路由；
- :class:`ResearchIntegration`：Claim evidence gap → ExecutionRouter →
  canonical evidence（去重）→ per-source EvidenceRelation → EvidenceGraph 可查。

依赖方向：execution → idea（契约面），不再存在 idea → execution。
"""
from __future__ import annotations

from typing import Any, cast

from aipd_os.execution.adapter import ToolAdapter, external_blocked_error
from aipd_os.execution.execution_router import ExecutionRouter
from aipd_os.idea.claims import Claim
from aipd_os.idea.evidence_graph import EvidenceGraph
from aipd_os.idea.evidence_relations import EvidenceRelation, EvidenceRelationService
from aipd_os.idea.research_provider import (
    RELATION_KEY,
    EvidenceRequest,
    ResearchCapabilityUnavailable,
    ResearchProvider,
)
from aipd_os.state.db import AIPDStateDB, now_iso


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
    "ResearchToolAdapter",
    "ResearchIntegration",
]
