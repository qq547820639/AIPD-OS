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


def test_pdf_is_not_reported_as_not_open_access() -> None:
    """第 77 片的核心更正：开放获取的 PDF **能下载**，只是这一层没有抽取器。

    第 76 片那版把它一路交给库的 UTF-8 判定，结果 `access=restricted`——
    那等于对读者说"这篇文章不是开放获取"，而事实是"我们缺一个 PDF 抽取器"。
    两件事必须有两个词。
    """
    items = [{"source": "open_alex", "is_oa": True, "title": "PDF 那篇",
              "oa_url": "https://repo.org/a.pdf", "oa_license": "cc-by"},
             {"source": "arxiv", "arxiv_id": "2401.04398", "title": "arXiv PDF"}]
    rep = ff.fetch_all(items, getter=lambda _u: b"%PDF-1.5\n%\x8f\n1 0 obj\n<<>>")
    assert rep["full_texts"] == 0, rep
    assert rep["needs_extractor"] == 2, rep
    assert rep["restricted"] == 0, rep
    kinds = {r["content_kind"] for r in rep["fetched"]}
    assert kinds == {"pdf"}, kinds
    # 装了 pypdf 之后这个假 PDF 的下场是"抽不出文本"，没装则是"没有抽取器"；
    # 两种都不许写成"来源不开放"，也不许写成"抽到了"。
    assert all(r["outcome"].startswith("pdf_") for r in rep["fetched"]), rep
    assert all(not r["outcome"].endswith("extracted_pdf") for r in rep["fetched"]), rep
    assert all(r["access"] == "open" for r in rep["fetched"]), rep
    assert all(r["sha256"] and r["bytes"] > 0 for r in rep["fetched"]), rep


def test_html_body_is_extracted_into_cacheable_text() -> None:
    """HTML 走 stdlib 抽取：拿到的是正文文本，``outcome=extracted_html``。"""
    LONG = ("<p>" + ("这一段用于把正文撑过全文下限，" * 200) + "</p>").encode("utf-8")
    html = ("<html><head><title>T</title><style>b{color:red}</style></head>"
            "<body><h1>协作机器人与老年康复</h1>"
            "<p>本文研究智能手环在居家场景下的应用。</p>"
            "<script>alert(1)</script></body></html>").encode("utf-8")
    rep = ff.fetch_all([{"source": "arxiv", "arxiv_id": "9999.00001",
                         "is_oa": True,
                         "oa_url": "https://arxiv.org/html/9999.00001",
                         "title": "T"}],
                       getter=lambda _u: html + b" " * 0 + LONG)
    assert rep["full_texts"] == 1, rep
    row = rep["fetched"][0]
    assert row["content_kind"] == "html", row
    assert row["outcome"] == "extracted_html", row
    text = ff.html_to_text(html)
    assert "协作机器人与老年康复" in text and "智能手环" in text, text
    assert "alert" not in text and "color:red" not in text, text
    assert row["sha256"] and row["chars"] > 0, row


def test_script_and_style_text_never_leaks_into_the_extracted_body() -> None:
    """抽取器不许把 <script>/<style> 里的字当正文（那是代码，不是文章内容）。"""
    raw = ("<html><body><p>REAL BODY TEXT</p>"
           "<script>var secretToken = 'abc'</script>"
           "<style>.hidden{display:none}</style></body></html>").encode("utf-8")
    text = ff.html_to_text(raw)
    assert "REAL BODY TEXT" in text, text
    assert "secretToken" not in text and "display:none" not in text, text


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
    # 离线模式现在给的是独立结果词，不再混进 restricted
    assert rep["access_counts"].get("offline_reachable") == 1, rep


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
    assert "缺抽取器" in proc.stdout, proc.stdout

def test_a_short_html_landing_page_is_not_reported_as_full_text() -> None:
    """arXiv 的 /abs 页也是合法 HTML：抽出来只有摘要长度时不许说"拿到全文"。"""
    landing = ("<html><body><h1>论文标题</h1><p>一小段摘要。</p>"
               "<a href=/pdf>PDF</a></body></html>").encode("utf-8")
    rep = ff.fetch_all([{"source": "arxiv", "arxiv_id": "9999.00002",
                         "is_oa": True, "oa_url": "https://arxiv.org/abs/9999.00002",
                         "title": "T"}], getter=lambda _u: landing)
    assert rep["full_texts"] == 0, rep
    assert rep["access_counts"].get("short_or_landing_page") == 1, rep
    assert "短于全文下限" in rep["skipped"][0]["reason"], rep


def test_whitespace_only_pdf_is_not_reported_as_extracted() -> None:
    """第 77 片实测的形状：大 PDF 只抽出空白字符时不许标 `extracted_pdf`。

    不 strip 的话，同一行读数里 `outcome=extracted_pdf` 与 `access=restricted`
    会互相打脸——库里按空文本判受限，标签却说抽到了。
    """
    fake = b"%PDF-1.7\n" + b"\x00" * 64
    text, outcome = ff.pdf_to_text(fake)
    assert text == "", text
    assert outcome == "pdf_without_text" or outcome.startswith("pdf_extract_failed:"), outcome
    rep = ff.fetch_all([{"source": "arxiv", "arxiv_id": "8888.00001",
                         "is_oa": True, "oa_url": "https://repo.org/blank.pdf",
                         "title": "只抽出空白的 PDF"}], getter=lambda _u: fake)
    assert rep["full_texts"] == 0, rep
    assert rep["access_counts"].get("open_needs_extractor") == 1, rep
    assert all(r["outcome"] != "extracted_pdf" for r in rep["fetched"]), rep


def test_pdf_that_yields_only_whitespace_hits_the_strip_guard(monkeypatch) -> None:
    """直接驱动 strip 那道闸：抽取器返回"只含空白"的页时必须算没抽到。

    上一条用例喂的是坏 PDF，走的是 `pdf_extract_failed` 分支，碰不到这道闸——
    电池臂 U1（把 strip 判空改成永不空）因此第一版存活。控制要打在它声称要防的那一行上。
    """
    import pypdf

    class _Page:
        def extract_text(self) -> str:
            return "   \n\t  "

    class _Reader:
        pages = [_Page()]

    monkeypatch.setattr(pypdf, "PdfReader", lambda *a, **k: _Reader())
    text, outcome = ff.pdf_to_text(b"%PDF-1.7 anything")
    assert text == "", text
    assert outcome == "pdf_without_text", outcome
