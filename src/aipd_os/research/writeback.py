"""研究结果回写：Product Truth（事实）与 Evidence Register（证据）。

基于 ``aipd_os.state.db.AIPDStateDB`` 的既有事实/证据/关联能力：
  - Product Truth  -> facts 表（``add_fact``）；
  - Evidence Register -> evidence 表（``add_evidence``）；
  - 证据支撑关系 -> fact_evidence（``link_evidence``）。

仅当 finding 状态为 ``verified`` 时才写入确定性结论；``not_verified`` 的
finding 只登记证据，不写事实，避免把未验证结论固化为 Product Truth。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .fetchers import DocumentFetcher
from .models import (
    STATUS_NOT_VERIFIED,
    STATUS_VERIFIED,
    Citation,
    ResearchFinding,
)
from .retrieval import Retriever


class ResearchBackend:
    """研究链回写后端：把研究结果写入 Product Truth 与 Evidence Register。"""

    def __init__(self, db: Any, tenant_id: str = "default", project_id: str = "p1") -> None:
        self._db = db
        self._tenant = tenant_id
        self._project = project_id

    # ---------------------------------------------------------- Evidence Register
    def register_evidence(self, citation: Citation, scope: str = "abstract") -> str:
        """把一条引用写入 Evidence Register，返回 evidence_id。"""
        meta = citation.to_dict()
        meta["scope"] = scope  # abstract / full_text
        return self._db.add_evidence(
            self._tenant,
            self._project,
            kind=citation.kind,
            title=citation.title,
            url=citation.url,
            identifier=citation.identifier,
            quality=scope,
            summary=meta.get("snippet"),
            metadata=meta,
            accessed_at=citation.accessed_at,
        )

    # ------------------------------------------------------------ Product Truth
    def write_finding(self, finding: ResearchFinding) -> Optional[str]:
        """把已验证 finding 写入 Product Truth（facts）。

        仅 ``verified`` 状态才写事实；``not_verified`` 返回 None 且不固化结论。
        """
        if finding.status == STATUS_NOT_VERIFIED:
            return None
        evidence_ids = [self.register_evidence(c, scope="full_text") for c in finding.citations]
        fact_id = self._db.add_fact(
            self._tenant,
            self._project,
            key=finding.key,
            value=finding.value,
            status="V",
            confidence=finding.confidence,
            source=";".join(c.source for c in finding.citations) or "research",
        )
        for eid in evidence_ids:
            self._db.link_evidence(self._tenant, self._project, fact_id, eid, relation="supports")
        return fact_id

    def write_evidence_only(self, finding: ResearchFinding) -> List[str]:
        """仅登记证据（用于 not_verified / 摘要级发现），不写 Product Truth。"""
        return [self.register_evidence(c, scope="abstract") for c in finding.citations]


def run_research_chain(
    db: Any,
    tenant_id: str,
    project_id: str,
    finding: ResearchFinding,
    retriever: Optional[Retriever] = None,
    fetcher: Optional[DocumentFetcher] = None,
) -> Dict[str, Any]:
    """（可选编排）检索 -> 取全文 -> 写出 Product Truth / Evidence Register。

    - 检索失败 / 无法获取全文时，finding 状态保持 not_verified；
    - 不产生确定性结论，不写事实。
    """
    backend = ResearchBackend(db, tenant_id, project_id)
    if retriever is None and fetcher is None:
        # 无任何检索能力：诚实登记证据并保持 not_verified
        eids = [backend.register_evidence(c, scope="abstract") for c in finding.citations]
        return {"status": finding.status, "evidence_ids": eids, "fact_id": None}

    if retriever is not None:
        docs = retriever.search(finding.key)
        if not docs or all(d.status == STATUS_NOT_VERIFIED for d in docs):
            finding.status = STATUS_NOT_VERIFIED
            eids = [backend.register_evidence(c, scope="abstract") for c in finding.citations]
            return {"status": finding.status, "evidence_ids": eids, "fact_id": None}
        for doc in docs[:1]:
            finding.add_citation(doc.citation)

    if fetcher is not None:
        if finding.citations:
            doc = fetcher.fetch(finding.citations[0])
            if doc.status != STATUS_VERIFIED:
                finding.status = STATUS_NOT_VERIFIED
                eids = [backend.register_evidence(c, scope="abstract") for c in finding.citations]
                return {"status": finding.status, "evidence_ids": eids, "fact_id": None}
            finding.status = STATUS_VERIFIED

    fact_id = backend.write_finding(finding)
    # write_finding 已登记全部引用为 full_text 证据（写入 Evidence Register）
    return {
        "status": finding.status,
        "fact_id": fact_id,
    }


__all__ = ["ResearchBackend", "run_research_chain"]