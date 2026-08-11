"""v5.8.1 Commit 10：ResearchStudio paper-search provider 测试（不访问互联网）。

覆盖：
- MIT attribution 保留（文件头声明来源 + LICENSE notice）；
- 多引擎结果聚合（arxiv+openalex+semanticscholar → 合并去重）；
- DOI / arXiv ID / normalized title 去重；
- found_in 保留（同一论文被多引擎命中 → found_in 并集）；
- 部分引擎失败 → partial + successful_sources 保留；
- 全部引擎失败 → ResearchCapabilityUnavailable（external_dependency）；
- 输出字段符合 §27 contract；
- capability 注册 → ExecutionRouter 可路由；
- 真实 internet 引擎标 integration/external_capability，默认不访问外网。
"""
from __future__ import annotations

import pytest

from aipd_os.execution.execution_router import ExecutionRouter
from aipd_os.execution.registry import AdapterRegistry
from aipd_os.execution.runs import RunStore
from aipd_os.idea import (
    ResearchCapabilityUnavailable,
)
from aipd_os.research.providers.researchstudio import (
    MIT_ATTRIBUTION,
    ResearchStudioPaperSearchProvider,
    normalize_arxiv_id,
    normalize_doi,
    normalize_title,
    register_researchstudio,
)
from tests.fixtures.research.researchstudio_fixtures import (
    PAPER_ALPHA,
    EmptyEngine,
    FailingEngine,
    FakeArxivEngine,
    FakeOpenAlexEngine,
    FakeSemanticScholarEngine,
)

# §27 contract 必需字段
_CONTRACT_FIELDS = {
    "title", "authors", "year", "abstract", "url", "venue",
    "citation_count", "publication_date", "source", "doi", "arxiv_id", "found_in",
}


def _provider(*engines):
    return ResearchStudioPaperSearchProvider(engines=list(engines))


# ---------------------------------------------------------------------------
# 1) MIT attribution + normalize helpers
# ---------------------------------------------------------------------------
def test_mit_attribution_present():
    """改编自 MIT 项目必须保留 attribution/License notice。"""
    assert "MIT License" in MIT_ATTRIBUTION
    assert "Happy" in MIT_ATTRIBUTION
    import inspect
    src = inspect.getsource(__import__(
        "aipd_os.research.providers.researchstudio", fromlist=["x"]))
    assert "MIT License, Copyright (c) 2026 Happy" in src


def test_normalize_helpers():
    assert normalize_title("  AI  Feedback!  ") == "ai feedback"
    assert normalize_doi("https://doi.org/10.1000/Alpha") == "10.1000/alpha"
    assert normalize_arxiv_id("https://arxiv.org/abs/2304.00001v2") == "2304.00001v2"
    assert normalize_arxiv_id("2304.00001.pdf") == "2304.00001"


# ---------------------------------------------------------------------------
# 2) 多引擎聚合 + 去重
# ---------------------------------------------------------------------------
def test_multiple_engines_aggregated():
    """arxiv + openalex + semanticscholar 合并 → 去重后 2 篇（alpha/beta/unrelated）。"""
    p = _provider(FakeArxivEngine(), FakeOpenAlexEngine(),
                  FakeSemanticScholarEngine())
    out = p.execute({"query": "rehabilitation ai feedback"})
    assert out["provider"] == "researchstudio-paper-search"
    assert out["sources"]
    titles = {s["title"] for s in out["sources"]}
    # alpha 被 arxiv+openalex 双引擎命中 → 去重为 1；unrelated 来自 semanticscholar
    assert titles == {PAPER_ALPHA["title"], "Unrelated Survey on Sensor Networks"}
    assert len(out["sources"]) == 2
    assert out["partial"] is False


def test_dedupe_doi():
    """同一 DOI 两条记录 → 去重为 1。"""
    p = _provider(FakeOpenAlexEngine(), FakeOpenAlexEngine())
    out = p.execute({"query": "q"})
    assert len(out["sources"]) == 1
    assert out["sources"][0]["doi"] == "10.1000/alpha"


def test_dedupe_arxiv():
    """同一 arXiv ID 两条记录 → 去重为 1。"""
    p = _provider(FakeArxivEngine(), FakeArxivEngine())
    out = p.execute({"query": "rehabilitation"})
    assert len(out["sources"]) == 1
    assert out["sources"][0]["arxiv_id"] == PAPER_ALPHA["arxiv_id"]


def test_dedupe_normalized_title():
    """无 DOI/arXiv 时按 normalized(title+year) 去重。"""
    class T1:
        name = "t1"

        def search(self, query, max_results=20):
            return [{"title": "A  Strange Title!", "year": 2020, "doi": "",
                     "arxiv_id": "", "found_in": ["t1"], "authors": [], "abstract": "",
                     "url": "", "venue": "", "citation_count": None,
                     "publication_date": "", "source": "t1", "identifier": ""}]

    class T2:
        name = "t2"

        def search(self, query, max_results=20):
            return [{"title": "a strange title", "year": 2020, "doi": "",
                     "arxiv_id": "", "found_in": ["t2"], "authors": [], "abstract": "",
                     "url": "", "venue": "", "citation_count": None,
                     "publication_date": "", "source": "t2", "identifier": ""}]
    p = _provider(T1(), T2())
    out = p.execute({"query": "q"})
    assert len(out["sources"]) == 1
    assert set(out["sources"][0]["found_in"]) == {"t1", "t2"}


# ---------------------------------------------------------------------------
# 3) found_in 保留
# ---------------------------------------------------------------------------
def test_found_in_preserved():
    """alpha 被 arxiv+openalex 命中 → found_in=['arxiv','openalex']。"""
    p = _provider(FakeArxivEngine(), FakeOpenAlexEngine())
    out = p.execute({"query": "rehabilitation"})
    alpha = next(s for s in out["sources"] if s["doi"] == "10.1000/alpha")
    assert set(alpha["found_in"]) == {"arxiv", "openalex"}


# ---------------------------------------------------------------------------
# 4) 局部降级（partial provider failure）
# ---------------------------------------------------------------------------
def test_partial_provider_failure():
    """一引擎失败 → partial + successful_sources 保留 + failed_sources 记录。"""
    p = _provider(FakeArxivEngine(), FailingEngine())
    out = p.execute({"query": "rehabilitation"})
    assert out["partial"] is True
    assert out["successful_sources"] == ["arxiv"]
    assert out["failed_sources"] == [{"engine": "failing",
                                      "error": "fixture engine outage"}]
    assert len(out["sources"]) == 1  # arxiv 结果保留


def test_all_provider_failure():
    """全引擎失败 → external_dependency（不伪造成功）。"""
    p = _provider(FailingEngine(), FailingEngine())
    with pytest.raises(ResearchCapabilityUnavailable, match="ALL engines"):
        p.execute({"query": "rehabilitation"})


def test_empty_engines_do_not_fabricate():
    """引擎返回空结果 → 不伪造；若全空则 partial=False 且 sources=[]。"""
    p = _provider(EmptyEngine())
    out = p.execute({"query": "rehabilitation"})
    assert out["sources"] == []
    assert out["partial"] is False
    assert out["successful_sources"] == ["empty"]


# ---------------------------------------------------------------------------
# 5) §27 contract 字段齐全
# ---------------------------------------------------------------------------
def test_metadata_normalization():
    """每个 source 字段齐全符合 §27 contract。"""
    p = _provider(FakeArxivEngine(), FakeOpenAlexEngine())
    out = p.execute({"query": "rehabilitation"})
    for s in out["sources"]:
        assert set(s.keys()) >= _CONTRACT_FIELDS, f"missing fields in {s}"
        assert s["found_in"]  # found_in 非空


# ---------------------------------------------------------------------------
# 6) capability 注册 → ExecutionRouter 可路由
# ---------------------------------------------------------------------------
def test_registered_and_routable(tmp_path):
    """register_researchstudio → research.academic_search 可被 ExecutionRouter 路由。"""
    reg = AdapterRegistry()
    provider = register_researchstudio(reg, engines=[FakeArxivEngine()])
    assert isinstance(provider, ResearchStudioPaperSearchProvider)
    store = RunStore(str(tmp_path / "exec.db"))
    router = ExecutionRouter(store, reg)
    claim_id = "CLM-1"
    out = router.run(claim_id, "research.academic_search",
                     {"query": "rehabilitation"})
    assert out["record"].status == "succeeded"
    assert out["result"]["provider"] == "researchstudio-paper-search"
    assert out["result"]["sources"]
    # 未注册 capability → 不可路由
    reg2 = AdapterRegistry()
    router2 = ExecutionRouter(store, reg2)
    with pytest.raises(KeyError):
        router2.run(claim_id, "research.academic_search", {"query": "q"})


def test_provider_available_and_does_not_assess():
    """available=True；Search provider 不承担 assessment（诚实不可用）。"""
    p = _provider(FakeArxivEngine())
    assert p.available() is True
    assert p.capability_id == "research.academic_search"
    with pytest.raises(ResearchCapabilityUnavailable, match="assess_relation"):
        p.assess_relation({"claim_id": "CLM-1"})


# ---------------------------------------------------------------------------
# 7) 真实 internet 引擎（integration/external_capability；默认 CI 不访问外网）
# ---------------------------------------------------------------------------
def test_real_engines_available():
    """真实引擎可实例化（默认集合非空；不访问外网）。"""
    from aipd_os.research.providers.researchstudio import (
        ArxivEngine,
        OpenAlexEngine,
        SemanticScholarEngine,
        default_engines,
    )
    engines = default_engines()
    assert [e.name for e in engines] == ["arxiv", "openalex", "semanticscholar"]
    assert isinstance(engines[0], ArxivEngine)
    assert isinstance(engines[1], OpenAlexEngine)
    assert isinstance(engines[2], SemanticScholarEngine)


@pytest.mark.skipif(
    __import__("os").environ.get("AIPD_RESEARCHSTUDIO_INTEGRATION") != "1",
    reason="integration: requires internet (AIPD_RESEARCHSTUDIO_INTEGRATION=1)")
def test_real_arxiv_engine_integration():
    """真实 arXiv API（仅显式开启时运行；不伪造成功）。"""
    from aipd_os.research.providers.researchstudio import ArxivEngine
    hits = ArxivEngine(timeout=30).search("home-based rehabilitation AI", max_results=5)
    assert hits
    for h in hits:
        assert h["title"] and h["source"] == "arxiv" and h["found_in"] == ["arxiv"]
