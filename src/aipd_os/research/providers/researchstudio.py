"""ResearchStudio paper-search provider（v5.8.1 Commit 10）。

接入真实 ResearchStudio Academic Search 逻辑，作为 :class:`ResearchProvider`
实现，capability ``research.academic_search``。上层只知 capability 不知实现细节。

MIT attribution（§26）：
    本模块改编自 ResearchStudio（MIT License, Copyright (c) 2026 Happy，
    来源：/Volumes/Extra/新躯纪元/ResearchStudio-main.zip，GitHub 项目同名）。
    复用了其 paper-search 的确定性逻辑：
      - ``normalize_title``（normalized title 去重键）；
      - 多引擎聚合 + ``found_in`` 来源标注 + ``paper_id = source:source_id``；
      - OpenAlex externalIds 提取 DOI / arXiv ID 用于跨源去重。
    未复制 WorkBuddy-specific runtime / .env / 个人 API key / 无关 skill。
    完整 MIT License 文本见本仓库 ``NOTICE`` / 源项目 LICENSE。

§27 contract：provider 输出
  ``{provider, query, sources: [{title, authors, year, abstract, url, venue,
  citation_count, publication_date, source, doi, arxiv_id, found_in}]}``。

Search provider 默认不输出 supports —— relation candidate 由上层按
inconclusive + pending 处理（Commit 5 Search ≠ Assessment 已保证）。

§28 局部降级：多引擎并行调用，单引擎失败不影响其他；
  至少一个引擎成功 → succeeded + ``partial`` 标记 + successful_sources/
  failed_sources 记录；全部失败 → :class:`ResearchCapabilityUnavailable`
  （external_dependency，不伪造成功）。
"""
from __future__ import annotations

import abc
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable
from typing import Any

from aipd_os.idea.research_provider import (
    ResearchCapabilityUnavailable,
    ResearchProvider,
)

# 本模块改编自 ResearchStudio（MIT License, Copyright (c) 2026 Happy）
MIT_ATTRIBUTION = (
    "Adapted from ResearchStudio (MIT License, Copyright (c) 2026 Happy) — "
    "see https://github.com/research-studio/ResearchStudio"
)

# ---------------------------------------------------------------------------
# 去重/规范化（复用 ResearchStudio normalize_title；MIT）
# ---------------------------------------------------------------------------


def normalize_title(title: str) -> str:
    """normalized title（跨源去重键；ResearchStudio 逻辑）。"""
    return re.sub(r"\W+", " ", (title or "").lower()).strip()[:80]


def normalize_doi(doi: Any) -> str:
    """规范化 DOI（去 https://doi.org/ 前缀、去空白、小写）。"""
    return str(doi or "").strip().lower().replace("https://doi.org/", "")


def normalize_arxiv_id(arxiv_id: Any) -> str:
    """规范化 arXiv ID（去 URL 前缀/尾 .pdf、去空白、小写）。"""
    raw = str(arxiv_id or "").strip()
    if not raw:
        return ""
    if "arxiv.org" in raw:
        parsed = urllib.parse.urlparse(raw)
        path = re.sub(r"^/(?:abs|pdf|html)/", "", parsed.path or "")
        raw = path
    return raw.rstrip(".pdf").strip().lower()


# ---------------------------------------------------------------------------
# 引擎
# ---------------------------------------------------------------------------


class ResearchStudioEngine(abc.ABC):
    """一个学术检索引擎（真实实现标 integration；单元测试注入 fake）。"""

    name: str = "unnamed"

    @abc.abstractmethod
    def search(self, query: str, max_results: int = 20) -> list[dict[str, Any]]:
        """返回按 §27 source contract 归一化的 hit 列表（含 found_in）。"""


class _HttpEngine(ResearchStudioEngine):
    """基于 urllib 的引擎骨架（超时 + HTTPError 抛出，由 provider 局部降级）。"""

    timeout: int = 30

    def __init__(self, timeout: int = 30) -> None:
        self.timeout = timeout

    def _get_json(self, url: str, headers: dict[str, str] | None = None) -> Any:
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode("utf-8"))


class ArxivEngine(_HttpEngine):
    """arXiv API（匿名，export.arxiv.org；改编自 ResearchStudio search_arxiv.py）。"""

    name = "arxiv"
    api = "https://export.arxiv.org/api/query"
    ns = {"atom": "http://www.w3.org/2005/Atom"}

    def search(self, query: str, max_results: int = 20) -> list[dict[str, Any]]:
        import xml.etree.ElementTree as ET

        params = {"search_query": f"all:{query}", "sortBy": "relevance",
                  "sortOrder": "descending", "max_results": max_results}
        url = f"{self.api}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={
            "User-Agent": "aipd-os-researchstudio/1.0 (+https://arxiv.org/help/api)"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            body = r.read()
        root = ET.fromstring(body)

        def _text(entry: Any, tag: str) -> str:
            el = entry.find(tag, self.ns)
            return (el.text or "").strip() if el is not None else ""

        out: list[dict[str, Any]] = []
        for entry in root.findall("atom:entry", self.ns):
            title = _text(entry, "atom:title")
            abstract = _text(entry, "atom:summary")
            published = _text(entry, "atom:published")
            authors = [_text(a, "atom:name")
                       for a in entry.findall("atom:author", self.ns)]
            entry_id = _text(entry, "atom:id")
            arxiv_id = normalize_arxiv_id(entry_id.split("/")[-1])
            try:
                year = int(published[:4]) if published else None
            except ValueError:
                year = None
            out.append(self._hit(title=title, authors=authors, year=year,
                                 abstract=abstract, url=f"https://arxiv.org/abs/{arxiv_id}",
                                 venue="arXiv", citation_count=None,
                                 publication_date=published, source=self.name,
                                 doi="", arxiv_id=arxiv_id, identifier=arxiv_id))
        return out

    @staticmethod
    def _hit(**kw: Any) -> dict[str, Any]:
        kw["found_in"] = [ArxivEngine.name]
        return kw


class OpenAlexEngine(_HttpEngine):
    """OpenAlex API（polite pool；改编自 ResearchStudio search_openalex.py）。"""

    name = "openalex"
    api = "https://api.openalex.org/works"

    def search(self, query: str, max_results: int = 20) -> list[dict[str, Any]]:
        params = {"search": query, "per-page": max_results, "sort": "relevance_score:desc"}
        data = self._get_json(f"{self.api}?{urllib.parse.urlencode(params)}")
        out: list[dict[str, Any]] = []
        for work in data.get("results") or []:
            title = work.get("title") or ""
            abstract = self._reconstruct_abstract(work.get("abstract_inverted_index") or {})
            primary = work.get("primary_location") or {}
            source = primary.get("source") or {}
            venue = source.get("display_name") or ""
            authors = [a.get("author", {}).get("display_name", "")
                       for a in work.get("authorships", [])][:6]
            ids = work.get("ids") or {}
            arxiv_id = normalize_arxiv_id(ids.get("arxiv") or "")
            doi = normalize_doi(work.get("doi") or "")
            oa = work.get("best_oa_location") or {}
            out.append({
                "title": title,
                "authors": authors,
                "year": work.get("publication_year"),
                "abstract": abstract,
                "url": oa.get("pdf_url") or work.get("id", ""),
                "venue": venue,
                "citation_count": work.get("cited_by_count"),
                "publication_date": work.get("publication_date", ""),
                "source": self.name,
                "doi": doi,
                "arxiv_id": arxiv_id or None,
                "identifier": (work.get("id") or "").split("/")[-1],
                "found_in": [self.name],
            })
        return out

    @staticmethod
    def _reconstruct_abstract(inverted: dict[str, Any]) -> str:
        if not inverted:
            return ""
        words: list[tuple[int, str]] = []
        for word, positions in inverted.items():
            for pos in positions:
                words.append((pos, word))
        words.sort(key=lambda x: x[0])
        return " ".join(w for _, w in words)


class SemanticScholarEngine(_HttpEngine):
    """Semantic Scholar Graph API（externalIds 提供 DOI/arXiv；改编自 ResearchStudio）。"""

    name = "semanticscholar"
    api = "https://api.semanticscholar.org/graph/v1/paper/search"

    def search(self, query: str, max_results: int = 20) -> list[dict[str, Any]]:
        fields = ("title,authors,year,abstract,url,venue,citationCount,"
                  "publicationDate,externalIds,paperId")
        params = {"query": query, "limit": max_results, "fields": fields}
        data = self._get_json(f"{self.api}?{urllib.parse.urlencode(params)}")
        out: list[dict[str, Any]] = []
        for paper in data.get("data") or []:
            ext = paper.get("externalIds") or {}
            out.append({
                "title": paper.get("title") or "",
                "authors": [a.get("name", "") for a in paper.get("authors", [])],
                "year": paper.get("year"),
                "abstract": paper.get("abstract") or "",
                "url": paper.get("url") or "",
                "venue": paper.get("venue") or "",
                "citation_count": paper.get("citationCount"),
                "publication_date": paper.get("publicationDate") or "",
                "source": self.name,
                "doi": normalize_doi(ext.get("DOI") or ""),
                "arxiv_id": normalize_arxiv_id(ext.get("ArXiv") or ""),
                "identifier": paper.get("paperId") or "",
                "found_in": [self.name],
            })
        return out


def default_engines(timeout: int = 30) -> list[ResearchStudioEngine]:
    """生产默认引擎集（真实 HTTP；integration）。"""
    return [ArxivEngine(timeout=timeout), OpenAlexEngine(timeout=timeout),
            SemanticScholarEngine(timeout=timeout)]


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class ResearchStudioPaperSearchProvider(ResearchProvider):
    """ResearchStudio Academic Search provider（capability research.academic_search）。

    多引擎聚合 + DOI/arXiv/normalized-title 去重 + found_in 来源标注 +
    局部降级（partial provider failure）。
    """

    name = "researchstudio-paper-search"
    capability_id = "research.academic_search"

    def __init__(self, engines: Iterable[ResearchStudioEngine] | None = None,
                 timeout: int = 30) -> None:
        self._engines = list(engines) if engines is not None \
            else default_engines(timeout=timeout)

    def available(self) -> bool:
        return True

    def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """执行 paper search（§27 contract + §28 partial 语义）。"""
        query = str(inputs.get("query") or inputs.get("topic") or "").strip()
        if not query:
            raise ValueError("researchstudio execute requires 'query' or 'topic'")
        successful: dict[str, list[dict[str, Any]]] = {}
        failed: list[dict[str, Any]] = []
        for engine in self._engines:
            try:
                hits = engine.search(query)
                successful[engine.name] = hits or []
            except Exception as exc:  # noqa: BLE001 - 单引擎失败局部降级
                failed.append({"engine": engine.name, "error": str(exc)})
        if not successful:
            raise ResearchCapabilityUnavailable(
                f"researchstudio paper search failed on ALL engines "
                f"({len(failed)} failed): {failed}; external_dependency, "
                "no fabricated results")
        sources = self._aggregate_and_dedupe(successful)
        return {
            "provider": self.name,
            "query": query,
            "sources": sources,
            "successful_sources": sorted(successful),
            "failed_sources": failed,
            "partial": bool(failed),
        }

    # ------------------------------------------------------------------ merge
    @staticmethod
    def _dedupe_keys(hit: dict[str, Any]) -> list[tuple]:
        """跨源去重候选键（任一命中即同一论文）：DOI → arXiv ID → title+year。"""
        keys: list[tuple] = []
        doi = normalize_doi(hit.get("doi"))
        if doi:
            keys.append(("doi", doi))
        arxiv_id = normalize_arxiv_id(hit.get("arxiv_id"))
        if arxiv_id:
            keys.append(("arxiv", arxiv_id))
        title_norm = normalize_title(hit.get("title") or "")
        year = hit.get("year")
        if title_norm and year is not None:
            keys.append(("title_year", f"{title_norm}|{year}"))
        return keys

    def _aggregate_and_dedupe(
            self, successful: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
        """按引擎优先级合并 + 去重；任一 identity 命中即同一论文，并集 found_in。"""
        seen: dict[tuple, dict[str, Any]] = {}
        order: list[tuple] = []
        for engine in self._engines:
            for hit in successful.get(engine.name, []):
                if not hit.get("title"):
                    continue
                keys = self._dedupe_keys(hit)
                if not keys:
                    continue
                # 命中任一已有 identity → 合并到已保留记录
                matched = next((seen[k] for k in keys if k in seen), None)
                if matched is not None:
                    for fi in hit.get("found_in") or []:
                        if fi not in matched.setdefault("found_in", []):
                            matched["found_in"].append(fi)
                    # 缺失字段回填（含 identity 字段：DOI/arXiv 由更完整来源补齐）
                    for f in ("abstract", "venue", "url", "citation_count",
                              "publication_date", "doi", "arxiv_id", "identifier"):
                        if not matched.get(f) and hit.get(f):
                            matched[f] = hit[f]
                    continue
                # 新记录：登记全部候选键
                for k in keys:
                    if k not in seen:
                        seen[k] = hit
                order.append(keys[0])
        return [seen[k] for k in order]


def register_researchstudio(registry: Any, **kwargs: Any) -> ResearchStudioPaperSearchProvider:
    """把 ResearchStudio provider 以 research.academic_search capability 注册进
    AdapterRegistry（可被 ExecutionRouter 路由；复用 ResearchToolAdapter 模式）。

    返回 provider 实例（便于调用方持有）。
    """
    from aipd_os.execution.research_integration import ResearchToolAdapter
    provider = ResearchStudioPaperSearchProvider(**kwargs)
    registry.register(ResearchToolAdapter(provider))
    return provider


__all__ = [
    "MIT_ATTRIBUTION",
    "normalize_title",
    "normalize_doi",
    "normalize_arxiv_id",
    "ResearchStudioEngine",
    "ArxivEngine",
    "OpenAlexEngine",
    "SemanticScholarEngine",
    "default_engines",
    "ResearchStudioPaperSearchProvider",
    "register_researchstudio",
]
