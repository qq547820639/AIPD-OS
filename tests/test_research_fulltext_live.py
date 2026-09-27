"""联网端到端（默认跳过）。`AIPD_RESEARCH_INTEGRATION=1` 才跑。

第 76 片我写过"沙箱无出网，所以在线验不了"——那是**错的**：本机出网正常，
第 77 片实测三条真实开放副本全部可下载。这条用例把那次实测固化下来：
只请求 arXiv 一个官方 PDF（不碰出版商站点），验的是
"下载 → 嗅出 PDF → 抽出正文 → 进缓存 → 计数为 open"整条链，
且只断言**下界**（字数、sha 非空），不断言具体文本，免得论文改版就红。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts" / "research"
sys.path.insert(0, str(SCRIPTS))

import fetch_fulltexts as ff  # noqa: E402

pytestmark = pytest.mark.skipif(
    os.environ.get("AIPD_RESEARCH_INTEGRATION") != "1",
    reason="integration: 需要出网（AIPD_RESEARCH_INTEGRATION=1 才跑）")


def test_one_arxiv_pdf_yields_cached_text() -> None:
    items = [{"source": "arxiv", "arxiv_id": "2401.04398",
              "title": "integration probe"}]
    rep = ff.fetch_all(items, getter=ff.http_getter("arxiv"))
    assert rep["access_counts"].get("error", 0) == 0, rep
    assert rep["full_texts"] == 1, rep
    row = rep["fetched"][0]
    assert row["content_kind"] == "pdf", row
    assert row["outcome"] == "extracted_pdf", row
    assert row["chars"] >= 20000, row          # 实测 80991
    assert len(row["sha256"]) == 64, row
    assert row["bytes"] > 100000, row


def test_one_pmc_article_yields_jats_text() -> None:
    """第二个域：Europe PMC 的 JATS XML。它不需要 PDF 抽取器就能拿到正文。"""
    items = [{"source": "open_alex", "pmcid": "PMC12900525",
              "title": "integration probe (PMC)"}]
    rep = ff.fetch_all(items, getter=ff.http_getter("europepmc"))
    assert rep["access_counts"].get("error", 0) == 0, rep
    assert rep["full_texts"] == 1, rep
    row = rep["fetched"][0]
    assert row["content_kind"] == "xml", row
    assert row["outcome"] == "extracted_xml", row
    assert row["chars"] >= 2000, row
