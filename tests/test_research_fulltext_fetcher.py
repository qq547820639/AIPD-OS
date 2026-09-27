"""OpenAlex 连接器的映射（F-FULLTEXT-STEP 第 76 片）。

连接器原先把 API 已经返回的 `open_access` / `best_oa_location` **整个丢掉**，
于是"全文获取"只能猜 URL。这里不联网：`request` 被换成返回假响应的桩，
钉的就是映射本身——带出哪些字段、没有开放副本时带出什么。
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts" / "research"
sys.path.insert(0, str(SCRIPTS))

import search_papers_by_open_alex as oa  # noqa: E402


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


def _run_works(monkeypatch, work: dict) -> list[dict]:
    calls = {"n": 0}

    def fake_request(session, method, url, **kwargs):
        calls["n"] += 1
        if calls["n"] > 1:
            return _Resp({"meta": {"count": 1}, "results": []})
        return _Resp({"meta": {"count": 1}, "results": [work]})

    monkeypatch.setattr(oa, "request", fake_request)
    monkeypatch.setattr(oa, "create_session", lambda *a, **k: object())
    papers = oa.search_papers_by_open_alex("康复机器人", 2020, 2026, max_results=1)
    assert calls["n"] >= 1
    return papers


def test_open_access_fields_are_carried_out_of_the_api(monkeypatch) -> None:
    papers = _run_works(monkeypatch, {
        "title": "T", "publication_year": 2024, "doi": "https://doi.org/10.1/x",
        "cited_by_count": 3, "publication_date": "2024-05-01",
        "open_access": {"is_oa": True, "oa_url": "https://zenodo.org/x.pdf",
                        "license": "cc-by"},
        "best_oa_location": {"pdf_url": "https://zenodo.org/x.pdf"},
    })
    assert len(papers) == 1, papers
    row = papers[0]
    assert row["is_oa"] is True, row
    assert row["oa_url"] == "https://zenodo.org/x.pdf", row
    assert row["oa_license"] == "cc-by", row


def test_closed_record_reports_closed(monkeypatch) -> None:
    papers = _run_works(monkeypatch, {
        "title": "T", "publication_year": 2024, "doi": "https://doi.org/10.2/y",
        "open_access": {"is_oa": False, "oa_url": None, "license": None},
    })
    row = papers[0]
    assert row["is_oa"] is False and row["oa_url"] == "", row
    assert row["oa_license"] == "", row


def test_best_oa_location_pdf_url_wins_over_the_landing_page(monkeypatch) -> None:
    """`open_access.oa_url` 常是落地页，`best_oa_location.pdf_url` 才是可解析正文。"""
    papers = _run_works(monkeypatch, {
        "title": "T", "doi": "https://doi.org/10.3/z",
        "open_access": {"is_oa": True, "oa_url": "https://journal.org/paper",
                        "license": "cc-by-nc"},
        "best_oa_location": {"pdf_url": "https://repo.org/paper.pdf",
                             "license": "cc-by"},
    })
    row = papers[0]
    assert row["oa_url"] == "https://repo.org/paper.pdf", row
    assert row["oa_license"] == "cc-by-nc", row      # 许可取 open_access 那份，不混着改


def test_no_open_access_block_still_maps_to_closed(monkeypatch) -> None:
    papers = _run_works(monkeypatch, {"title": "T", "doi": "https://doi.org/10.4/w"})
    row = papers[0]
    assert row["is_oa"] is False and row["oa_url"] == "", row
