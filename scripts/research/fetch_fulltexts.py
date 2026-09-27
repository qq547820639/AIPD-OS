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
import sys
from collections import Counter
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
)

Getter = Callable[[str], bytes]

ARXIV_PDF = "https://arxiv.org/pdf/{arxiv_id}"


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
    """逐条取全文并给出**分 access 的计数**；任何一条失败都不中断整步。"""
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
        try:
            rec = fetch_fulltext(target["url"], source=str(item.get("source") or ""),
                                 cache=cache, getter=getter,
                                 license=target["license"],
                                 locator=str(item.get("doi") or item.get("url") or ""))
        except Exception as exc:  # noqa: BLE001 - 单源失败不能让整步死，但必须点名
            counts["error"] += 1
            skipped.append({"title": title, "reason": f"下载抛错：{type(exc).__name__}: {exc}"})
            continue
        counts[rec.access] += 1
        records.append({"title": title, "url": target["url"], "access": rec.access,
                        "text_type": rec.text_type, "sha256": rec.sha256,
                        "chars": len(rec.text), "license": rec.license,
                        "retrieved_at": rec.retrieved_at})
    return {"access_counts": dict(counts), "fetched": records, "skipped": skipped,
            "full_texts": sum(1 for r in records
                              if r["access"] == ACCESS_OPEN and r["chars"] > 0),
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
    print(f"全文获取：查 {rep['queried']} 条 → 拿到开放全文 {rep['full_texts']} 条，"
          f"受限 {rep['restricted']}、阻断 {rep['blocked']}、"
          f"无开放副本 {rep['access_counts'].get('no_open_copy', 0)}、"
          f"下载出错 {rep['access_counts'].get('error', 0)}"
          + ("（离线模式：不下载，只登记可取性）" if args.offline else ""))
    for s in rep["skipped"][:5]:
        print(f"  · 未取得：{s['title'][:40]} — {s['reason'][:70]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
