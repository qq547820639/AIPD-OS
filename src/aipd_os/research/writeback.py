"""研究结果回写：Product Truth（事实）与 Evidence Register（证据）。

基于 ``aipd_os.state.db.AIPDStateDB`` 的既有事实/证据/关联能力：
  - Product Truth  -> facts 表（``add_fact``）；
  - Evidence Register -> evidence 表（``add_evidence``）；
  - 证据支撑关系 -> fact_evidence（``link_evidence``）。

v5.7 语义收敛（Commit 7A）：**retrieval verified ≠ 命题 verified**。
仅当 finding 的检索状态为 ``verified``（已获取并解析）时才写事实，但写入的
认知状态保守为 ``E``（Reliable external evidence，外部来源最多 E），绝不自动
``V``（verified）。``not_verified`` 的 finding 只登记证据，不写事实；非事实
（``is_fact=False``）的研究结论也只登记证据，不固化为 Product Truth。
"""

from __future__ import annotations

from typing import Any

from .fetchers import DocumentFetcher
from .models import (
    STATUS_NOT_VERIFIED,
    STATUS_VERIFIED,
    Citation,
    ResearchFinding,
    default_epistemic_status,
)
from .retrieval import Retriever


class ResearchBackend:
    """研究链回写后端：把研究结果写入 Product Truth 与 Evidence Register。"""

    def __init__(self, db: Any, tenant_id: str = "default", project_id: str = "p1") -> None:
        self._db = db
        self._tenant = tenant_id
        self._project = project_id

    # ---------------------------------------------------------- Evidence Register
    def register_evidence(self, citation: Citation, scope: str = "abstract",
                          extra_meta: dict[str, Any] | None = None) -> str:
        """把一条引用写入 Evidence Register，返回 evidence_id。"""
        meta = citation.to_dict()
        meta["scope"] = scope  # abstract / full_text
        if extra_meta:
            meta.update(extra_meta)
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
    def write_finding(self, finding: ResearchFinding,
                      status: str | None = None) -> str | None:
        """把已获取的 finding 写入 Product Truth（facts），保守认知状态。

        - 仅 ``verified``（检索状态）才写事实；``not_verified`` 返回 None；
        - ``is_fact=False`` 的研究结论不固化为 Product Truth（仅登记证据）；
        - 事实认知状态默认 ``E``（Reliable external evidence），绝不自动 ``V``；
          显式传入 ``status`` 或 ``finding.epistemic_status`` 可覆盖。
        """
        if finding.status == STATUS_NOT_VERIFIED:
            return None
        if not finding.is_fact:
            # 非事实研究结论只登记证据，不写 Product Truth。
            self.write_evidence_only(finding)
            return None
        write_status = status or finding.epistemic_status or default_epistemic_status(finding)
        epistemic_meta = {
            "retrieval_status": finding.retrieval_status or finding.status,
            "epistemic_status": write_status,
            "epistemic_note": (
                "research finding: retrieval verified does NOT imply verified truth; "
                "external evidence is written as E at most unless explicitly confirmed"),
        }
        evidence_ids = [
            self.register_evidence(c, scope="full_text", extra_meta=epistemic_meta)
            for c in finding.citations
        ]
        fact_id = self._db.add_fact(
            self._tenant,
            self._project,
            key=finding.key,
            value=finding.value,
            status=write_status,
            confidence=finding.confidence,
            source=";".join(c.source for c in finding.citations) or "research",
        )
        for eid in evidence_ids:
            self._db.link_evidence(self._tenant, self._project, fact_id, eid, relation="supports")
        return fact_id

    def write_evidence_only(self, finding: ResearchFinding) -> list[str]:
        """仅登记证据（用于 not_verified / 摘要级发现 / 非事实结论），不写 Product Truth。"""
        return [self.register_evidence(c, scope="abstract") for c in finding.citations]


def run_research_chain(
    db: Any,
    tenant_id: str,
    project_id: str,
    finding: ResearchFinding,
    retriever: Retriever | None = None,
    fetcher: DocumentFetcher | None = None,
) -> dict[str, Any]:
    """（可选编排）检索 -> 取全文 -> 写出 Product Truth / Evidence Register。

    - 检索失败 / 无法获取全文时，finding 状态保持 not_verified；
    - 不产生确定性结论，不写事实；
    - 全文获取成功只表示**检索状态** verified；写事实的认知状态由
      :meth:`ResearchBackend.write_finding` 保守决定（默认 E，绝不自动 V）。
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
