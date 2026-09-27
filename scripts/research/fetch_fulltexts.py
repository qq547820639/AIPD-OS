#!/usr/bin/env python3
"""全文获取：把检索结果真正接到 `src/aipd_os/research/fulltext.py`（第 76 片）。

第 65 片登记的缺口原话是"库里有一个**完全没被任何连接器消费**的 `fetch_fulltext`"。
这一步就是那个消费者：**不重新实现下载与分类**，只做连接器侧的两件事实——
"这一条记录有没有合法的开放副本"与"该用哪个 URL 去取"。

选路规则（每个来源只用自己已经返回的字段，不去猜付费墙）：

- `arxiv`：arXiv 一律有官方 PDF 直链，按 `arxiv_id` 推导，许可记 `arxiv`；
- `open_alex`：只用 `is_oa` + `oa_url`（OpenAlex 的 `best_oa_location.pdf_url` 优先），
  许可用 OpenAlex 给的 `license`；没有 `is_oa` 就当受限，**不退回 publisher 页面去 scrape**；
- 其他来源（crossref / semantic_scholar / openreview / dblp）：只有当记录里已经带
  `oa_url` 时才取；否则 `restricted` 并写明原因。

诚实契约（由库里那份实现保证，这里只补一条连接器侧的）：
拿不到就是拿不到——`restricted`/`blocked` 的记录**文本为空**，摘要仍在 `abstract` 字段里，
"全文缺失"不会伪装成"全文已获取"，也不会因为缺全文就让整步失败。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from _http_runtime import create_session, request  # noqa: E402

sys.path.insert(0, str(HERE.parent.parent / "src"))

from aipd_os.research.fulltext import (  # noqa: E402
    ACCESS_BLOCKED,
    ACCESS_OPEN,
    ACCESS_RESTRICTED,
    FullTextCache,
    fetch_fulltext,
    sha256_of,
    utc_now_iso,
)

Getter = Callable[[str], bytes]

ARXIV_PDF = "https://arxiv.org/pdf/{arxiv_id}"

KIND_PDF = "pdf"
KIND_HTML = "html"
KIND_TEXT = "text"
KIND_UNKNOWN_BINARY = "unknown_binary"

# 抽不出长度下限就分不清"全文"与"摘要落地页"：arXiv 的 /abs 页也是合法 HTML。
# 没有这道闸，抓到一页摘要就会被报成"拿到全文"——本仓对『把没做到的说成做到』零容忍。
MIN_FULL_TEXT_CHARS = 2000


def sniff_bytes(raw: bytes) -> str:
    """先看字节再决定能不能变成正文。

    第 77 片补的这一步是因为第 76 片留了一个**误标**：开放获取的 PDF 是真能下载的，
    但库里那份实现只保证 UTF-8 文本，二进制会被判成 `restricted`——
    于是"来源不允许我拿"和"我拿到了但没抽取器"在读数里长成同一个词。
    """
    if raw[:5] == b"%PDF-":
        return KIND_PDF
    head = raw[:512].lstrip().lower()
    if head.startswith(b"<") and (b"<html" in head or b"<!doctype" in head or b"<body" in head):
        return KIND_HTML
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return KIND_UNKNOWN_BINARY
    return KIND_TEXT if text.strip() else KIND_UNKNOWN_BINARY


class _TextExtractor(HTMLParser):
    """stdlib 的 HTML -> 纯文本：丢掉 script/style，块级标签换行，不猜语义。"""

    _SKIP = {"script", "style", "noscript", "svg", "head"}
    _BLOCK = {"p", "br", "div", "section", "article", "h1", "h2", "h3", "h4",
              "li", "tr", "table", "figure", "figcaption", "blockquote"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip_depth and data.strip():
            self.parts.append(data)


def html_to_text(raw: bytes) -> str:
    parser = _TextExtractor()
    parser.feed(raw.decode("utf-8", errors="replace"))
    text = "".join(parser.parts)
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def pdf_to_text(raw: bytes) -> tuple[str, str]:
    """PDF -> 文本。pypdf 是**可选**依赖：没装就说"没装"，不假装拿到正文。

    第 77 片实测：三条真实开放副本（arXiv PDF、出版商 OA PDF）**全是 PDF**，
    所以没有这一步，"全文获取"这个名字就是虚的。
    """
    try:
        import io

        from pypdf import PdfReader
    except ImportError:
        return "", "pdf_extractor_unavailable"
    try:
        reader = PdfReader(io.BytesIO(raw))
        pages = [(page.extract_text() or "") for page in reader.pages]
    except Exception as exc:  # noqa: BLE001 - 损坏 PDF 不是崩溃理由，但要留下原因
        return "", f"pdf_extract_failed:{type(exc).__name__}"
    text = "\n".join(ln for ln in (pg.strip() for pg in pages) if ln)
    # 只有空白也算"没抽到"：第 77 片实测有一条 3.6 MB 的 OA PDF 就返回了这个，
    # 不 strip 就会被标成 extracted_pdf，而库里随后按空文本判 restricted ⇒ 两个字段互相打脸。
    if not text.strip():
        return "", "pdf_without_text"
    return text, "extracted_pdf"


def extract_text(raw: bytes, kind: str) -> tuple[str, str]:
    """⇒ (可拿去缓存的文本, 结论词)。结论词解释**为什么没文本**。"""
    if kind == KIND_PDF:
        return "", "needs_pdf_extractor"
    if kind == KIND_HTML:
        text = html_to_text(raw)
        return (text, "extracted_html") if text.strip() else ("", "html_without_text")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return "", "undecodable_bytes"
    return (text, "extracted_text") if text.strip() else ("", "empty_payload")


def pick_target(item: dict[str, Any]) -> dict[str, Any]:
    """这条记录该不该去取全文、取哪个 URL。返回 ``{url, license, reason}``（url 空 = 不取）。"""
    source = str(item.get("source") or "")
    arxiv_id = item.get("arxiv_id") or ""
    if source == "arxiv" and arxiv_id:
        return {"url": ARXIV_PDF.format(arxiv_id=str(arxiv_id).strip()),
                "license": "arxiv", "reason": "arXiv 官方 PDF 直链"}
    if bool(item.get("is_oa")) and str(item.get("oa_url") or "").strip():
        return {"url": str(item["oa_url"]).strip(),
                "license": str(item.get("oa_license") or "") or None,
                "reason": "来源自带开放副本"}
    if str(item.get("oa_url") or "").strip():
        return {"url": str(item["oa_url"]).strip(),
                "license": str(item.get("oa_license") or "") or None,
                "reason": "来源自带开放副本（无 is_oa 标记）"}
    return {"url": "", "license": None,
            "reason": f"{source or '未知来源'} 没返回开放副本，不去 scrape 出版商页面"}


def http_getter(source: str = "fulltext") -> Getter:
    """真下载器：走连接器同一套超时/重试约定，返回**原始字节**（文本判定交给库）。"""
    session = create_session("AIPD-FullText/1.0")

    def _get(url: str) -> bytes:
        response = request(session, "GET", url, source=source)
        return response.content

    return _get


def fetch_all(items: list[dict[str, Any]], *, cache: FullTextCache | None = None,
              getter: Getter | None = None) -> dict[str, Any]:
    """逐条取全文并给出**分结果计数**；任何一条失败都不中断整步。

    结果词把两件以前混在一起的事分开：
    `restricted`/`blocked` = **不让拿**（版权与 robots 边界）；
    `open_needs_extractor` = **拿到了但这一层没有抽取器**（PDF 二进制），
    两者混成一个词就会把"我们缺一个 PDF 抽取器"读成"这些文章不是开放获取"。
    """
    cache = cache if cache is not None else FullTextCache()
    records: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for item in items:
        target = pick_target(item)
        title = str(item.get("title") or "")[:120]
        if not target["url"]:
            counts["no_open_copy"] += 1
            skipped.append({"title": title, "reason": target["reason"]})
            continue
        url = target["url"]
        source = str(item.get("source") or "")
        locator = str(item.get("doi") or item.get("url") or "")
        if getter is None:      # 离线：只登记可取性，不下载也不伪造
            counts["offline_reachable"] += 1
            records.append({"title": title, "url": url, "access": "unfetched_offline",
                            "content_kind": "", "outcome": "offline", "chars": 0,
                            "sha256": "", "license": target["license"] or ""})
            continue
        try:
            raw = getter(url)
        except Exception as exc:  # noqa: BLE001 - 单源失败不能拖垮整步，但必须点名
            counts["error"] += 1
            skipped.append({"title": title,
                            "reason": f"下载抛错：{type(exc).__name__}: {exc}"})
            continue
        kind = sniff_bytes(raw)
        if kind == KIND_PDF:
            text, outcome = pdf_to_text(raw)
            if not text:
                counts["open_needs_extractor"] += 1
                records.append({"title": title, "url": url, "access": ACCESS_OPEN,
                                "content_kind": kind, "outcome": outcome,
                                "chars": 0, "sha256": sha256_of(raw),
                                "bytes": len(raw), "license": target["license"] or "",
                                "retrieved_at": utc_now_iso()})
                continue
        else:
            text, outcome = extract_text(raw, kind)
        if text and len(text) < MIN_FULL_TEXT_CHARS:
            # 太短：只可能是摘要页/落地页，不当全文缓存，也不报"拿到正文"
            counts["short_or_landing_page"] += 1
            skipped.append({"title": title,
                            "reason": f"只抽到 {len(text)} 字，短于全文下限 "
                                      f"{MIN_FULL_TEXT_CHARS}（落地页或摘要页）"})
            continue
        if not text:
            counts["undecodable"] += 1
            skipped.append({"title": title, "reason": f"取到字节但抽不出文本：{outcome}"})
            continue
        try:
            rec = fetch_fulltext(url, source=source, cache=cache,
                                 getter=(lambda _u, _b=text.encode("utf-8"): _b),
                                 license=target["license"], locator=locator)
        except Exception as exc:  # noqa: BLE001
            counts["error"] += 1
            skipped.append({"title": title,
                            "reason": f"入库抛错：{type(exc).__name__}: {exc}"})
            continue
        counts[rec.access] += 1
        records.append({"title": title, "url": url, "access": rec.access,
                        "content_kind": kind, "outcome": outcome,
                        "chars": len(rec.text), "sha256": rec.sha256,
                        "bytes": len(raw), "license": rec.license,
                        "retrieved_at": rec.retrieved_at})
    return {"access_counts": dict(counts), "fetched": records, "skipped": skipped,
            "full_texts": counts[ACCESS_OPEN],
            "needs_extractor": counts["open_needs_extractor"],
            "restricted": counts[ACCESS_RESTRICTED], "blocked": counts[ACCESS_BLOCKED]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", required=True, help="检索结果 JSON（list 或 {\"papers\": [...]}）")
    ap.add_argument("--out", default="", help="把读数写成 JSON")
    ap.add_argument("--cache-dir", default="", help="全文缓存目录（默认内存缓存）")
    ap.add_argument("--offline", action="store_true",
                    help="不联网：开放副本也按「无下载器」处理（诚实标记，不伪造全文）")
    args = ap.parse_args(argv)
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    items = payload.get("papers") if isinstance(payload, dict) else payload
    if not isinstance(items, list) or not items:
        print(f"输入里没有可迭代的论文列表：{type(items).__name__}")
        return 2
    cache = FullTextCache(Path(args.cache_dir)) if args.cache_dir else FullTextCache()
    getter = None if args.offline else http_getter()
    rep = fetch_all(list(items), cache=cache, getter=getter)
    rep["offline"] = bool(args.offline)
    rep["queried"] = len(items)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(rep, ensure_ascii=False, indent=1),
                                  encoding="utf-8")
    print(f"全文获取：查 {rep['queried']} 条 → 拿到可缓存文本 {rep['full_texts']} 条，"
          f"开放但是 PDF（缺抽取器）{rep['needs_extractor']}、"
          f"受限 {rep['restricted']}、阻断 {rep['blocked']}、"
          f"无开放副本 {rep['access_counts'].get('no_open_copy', 0)}、"
          f"下载出错 {rep['access_counts'].get('error', 0)}"
          + ("（离线模式：不下载，只登记可取性）" if args.offline else ""))
    for s in rep["skipped"][:5]:
        print(f"  · 未取得：{s['title'][:40]} — {s['reason'][:70]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
