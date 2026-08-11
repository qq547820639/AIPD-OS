"""ResearchStudio provider 确定性夹具（v5.8.1 Commit 10；不访问互联网）。

Fake engines 模拟多引擎返回：同一论文可被不同引擎以不同 identity 命中
（DOI / arXiv / normalized title），用于验证聚合去重与 found_in 并集。

EPISTEMIC_NOTE: fixture 数据仅用于测试系统行为，不代表真实研究结论。
"""
from __future__ import annotations

from typing import Any

from aipd_os.research.providers.researchstudio import (
    ResearchStudioEngine,
    normalize_arxiv_id,
    normalize_doi,
)

PAPER_ALPHA = {
    "title": "Home-Based Rehabilitation with AI Feedback: A Randomized Trial",
    "authors": ["A. Author", "B. Researcher"],
    "year": 2023,
    "abstract": "Abstract for alpha paper (fixture, non-medical).",
    "url": "https://example.invalid/alpha",
    "venue": "J. Rehab",
    "citation_count": 42,
    "publication_date": "2023-04-01",
    "doi": "10.1000/alpha",
    "arxiv_id": "2304.00001",
}
PAPER_BETA = {
    "title": "Pose Estimation for Remote Rehabilitation Monitoring",
    "authors": ["C. Clinician"],
    "year": 2022,
    "abstract": "Abstract for beta paper (fixture).",
    "url": "https://example.invalid/beta",
    "venue": "J. HCI",
    "citation_count": 10,
    "publication_date": "2022-11-15",
    "doi": "10.1000/beta",
    "arxiv_id": None,
}


class FakeArxivEngine(ResearchStudioEngine):
    """模拟 arXiv：只提供 arXiv ID（无 DOI）。"""

    name = "arxiv"

    def search(self, query: str, max_results: int = 20) -> list[dict[str, Any]]:
        if "beta" in query.lower():
            return [{"title": PAPER_BETA["title"], "authors": PAPER_BETA["authors"],
                     "year": PAPER_BETA["year"], "abstract": PAPER_BETA["abstract"],
                     "url": "https://arxiv.org/abs/2211.00002",
                     "venue": "arXiv", "citation_count": None,
                     "publication_date": "2022-11-15", "source": self.name,
                     "doi": "", "arxiv_id": "2211.00002",
                     "identifier": "2211.00002", "found_in": [self.name]}]
        return [{"title": PAPER_ALPHA["title"], "authors": PAPER_ALPHA["authors"],
                 "year": PAPER_ALPHA["year"], "abstract": PAPER_ALPHA["abstract"],
                 "url": f"https://arxiv.org/abs/{PAPER_ALPHA['arxiv_id']}",
                 "venue": "arXiv", "citation_count": None,
                 "publication_date": PAPER_ALPHA["publication_date"],
                 "source": self.name, "doi": "", "arxiv_id": PAPER_ALPHA["arxiv_id"],
                 "identifier": PAPER_ALPHA["arxiv_id"], "found_in": [self.name]}]


class FakeOpenAlexEngine(ResearchStudioEngine):
    """模拟 OpenAlex：提供 DOI + externalIds（arXiv）。"""

    name = "openalex"

    def search(self, query: str, max_results: int = 20) -> list[dict[str, Any]]:
        # 与 FakeArxivEngine 命中同一篇 alpha 论文（但带 DOI）
        return [{
            "title": PAPER_ALPHA["title"],
            "authors": PAPER_ALPHA["authors"],
            "year": PAPER_ALPHA["year"],
            "abstract": PAPER_ALPHA["abstract"],
            "url": "https://example.invalid/alpha-openalex",
            "venue": PAPER_ALPHA["venue"],
            "citation_count": PAPER_ALPHA["citation_count"],
            "publication_date": PAPER_ALPHA["publication_date"],
            "source": self.name,
            "doi": normalize_doi(PAPER_ALPHA["doi"]),
            "arxiv_id": normalize_arxiv_id(PAPER_ALPHA["arxiv_id"]),
            "identifier": "W123456",
            "found_in": [self.name],
        }]


class FakeSemanticScholarEngine(ResearchStudioEngine):
    """模拟 Semantic Scholar：返回无关论文（测试多引擎合并）。"""

    name = "semanticscholar"

    def search(self, query: str, max_results: int = 20) -> list[dict[str, Any]]:
        return [{
            "title": "Unrelated Survey on Sensor Networks",
            "authors": ["D. Reviewer"],
            "year": 2021,
            "abstract": "Unrelated (fixture).",
            "url": "https://example.invalid/unrelated",
            "venue": "Sensors",
            "citation_count": 7,
            "publication_date": "2021-01-01",
            "source": self.name,
            "doi": "10.1000/unrelated",
            "arxiv_id": None,
            "identifier": "SS123",
            "found_in": [self.name],
        }]


class FailingEngine(ResearchStudioEngine):
    """总是失败的引擎（测试局部降级）。"""

    name = "failing"

    def search(self, query: str, max_results: int = 20) -> list[dict[str, Any]]:
        raise RuntimeError("fixture engine outage")


class EmptyEngine(ResearchStudioEngine):
    """总是返回空结果（测试空引擎不贡献）。"""

    name = "empty"

    def search(self, query: str, max_results: int = 20) -> list[dict[str, Any]]:
        return []


__all__ = [
    "PAPER_ALPHA",
    "PAPER_BETA",
    "FakeArxivEngine",
    "FakeOpenAlexEngine",
    "FakeSemanticScholarEngine",
    "FailingEngine",
    "EmptyEngine",
]
