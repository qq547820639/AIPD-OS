"""全文获取那一步的常驻用例（F-FULLTEXT-STEP，第 76 片）。

第 65 片登记的缺口是"库里有 `fetch_fulltext`，但没有任何连接器消费它"。
这一步补的就是那个消费者，所以用例钉的是**消费者行为**，不重复测库里那份实现：
选路规则、以及"拿不到就说拿不到"这两件事。全程不联网（getter 注入）。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts" / "research"
sys.path.insert(0, str(SCRIPTS))

import fetch_fulltexts as ff  # noqa: E402


def _getter(payload: bytes) -> ff.Getter:
    def _get(_url: str) -> bytes:
        return payload
    return _get


def test_arxiv_item_gets_the_official_pdf_url() -> None:
    target = ff.pick_target({"source": "arxiv", "arxiv_id": "2401.04398",
                             "title": "T"})
    assert target["url"] == "https://arxiv.org/pdf/2401.04398", target
    assert target["license"] == "arxiv", target


def test_openalex_uses_only_what_the_source_marked_open() -> None:
    oa = ff.pick_target({"source": "open_alex", "is_oa": True,
                         "oa_url": "https://example.org/a.pdf",
                         "oa_license": "cc-by", "title": "T"})
    assert oa["url"] == "https://example.org/a.pdf" and oa["license"] == "cc-by", oa
    closed = ff.pick_target({"source": "open_alex", "is_oa": False,
                             "url": "https://doi.org/10.1/x", "title": "T"})
    assert closed["url"] == "", closed
    assert "scrape" in closed["reason"], closed


def test_fetch_all_counts_by_access_and_keeps_abstract_only_items_out() -> None:
    items = [
        {"source": "arxiv", "arxiv_id": "2401.04398", "title": "拿到全文的那篇"},
        {"source": "arxiv", "arxiv_id": "2401.00001", "title": "付费墙那篇"},
        {"source": "crossref", "title": "没有开放副本"},
    ]

    def getter(url: str) -> bytes:
        if "04398" in url:
            return b"full body text here"
        return b"%PDF-1.5\xff\xfe\x00"     # 非法 UTF-8 字节：库里判"拿不到"，不当全文

    rep = ff.fetch_all(items, getter=getter)
    assert rep["full_texts"] == 1, rep
    # 三种"没拿到"是分开的两件事：非法字节 = restricted（真去取了），
    # 没有开放副本 = no_open_copy（根本没发起下载）。混成一个数就看不出哪一步该修。
    assert rep["restricted"] == 1, rep
    assert rep["access_counts"].get("no_open_copy") == 1, rep
    assert [r["access"] for r in rep["fetched"]] == ["open", "restricted"], rep
    assert rep["fetched"][0]["chars"] > 0 and rep["fetched"][1]["chars"] == 0, rep


def test_download_error_is_named_and_does_not_abort_the_step() -> None:
    def boom(_url: str) -> bytes:
        raise RuntimeError("connection reset")

    rep = ff.fetch_all([{"source": "arxiv", "arxiv_id": "1", "title": "T"}],
                       getter=boom)
    assert rep["access_counts"].get("error") == 1, rep
    assert "connection reset" in rep["skipped"][0]["reason"], rep
    assert rep["fetched"] == [], rep


def test_offline_mode_never_builds_a_downloader(monkeypatch, tmp_path: Path) -> None:
    """`--offline` 的兑现方式是**根本不构造下载器**，不是"下载失败后算拿不到"。

    第一版这条测的是"没拿到全文 + restricted 计数"——电池把 `offline` 判断摘掉后它仍然绿：
    真去下载 arXiv PDF 也会因为二进制字节被判 restricted，两种因果给出同一个读数。
    现在钉的是原因侧：`http_getter()` 一旦被调用就直接失败。
    """
    def _boom() -> ff.Getter:
        raise AssertionError("离线模式不该建下载器")

    monkeypatch.setattr(ff, "http_getter", _boom)
    src = tmp_path / "papers.json"
    src.write_text(json.dumps([{"source": "arxiv", "arxiv_id": "2401.04398",
                                "title": "T"}]), encoding="utf-8")
    out = tmp_path / "ft.json"
    assert ff.main(["--input", str(src), "--out", str(out), "--offline"]) == 0
    rep = json.loads(out.read_text(encoding="utf-8"))
    assert rep["offline"] is True and rep["full_texts"] == 0, rep


def test_offline_cli_run_still_reports_honestly(tmp_path: Path) -> None:
    src = tmp_path / "papers.json"
    src.write_text(json.dumps([{"source": "crossref", "title": "没有开放副本"}]),
                   encoding="utf-8")
    out = tmp_path / "ft.json"
    proc = subprocess.run([sys.executable, str(SCRIPTS / "fetch_fulltexts.py"),
                           "--input", str(src), "--out", str(out), "--offline"],
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr[-400:]
    rep = json.loads(out.read_text(encoding="utf-8"))
    assert rep["access_counts"].get("no_open_copy") == 1, rep
    assert "离线" in proc.stdout, proc.stdout
