#!/usr/bin/env python3
"""清单指纹：`SOURCE_MANIFEST.json` **内容**的规范摘要（去掉每次重生都会变的 `generated_at`）。

为什么不是整份文件的 sha256（这是本轮实测出来的，不是推的）：
`scripts/release_evidence.py` → `generate_source_manifest`
每次生成都把 `generated_at` 写成当前时间，
所以原始字节摘要在每轮收尾的「刷清单 → 跑全量 → 绑定」三步之间必然不同——拿它当判据就是给正常流程
判一条假红。规范摘要走的是**黑名单**（只剥 `VOLATILE_KEYS`），除 `generated_at` 之外的顶层键
（`name`/`version`/`source_commit`/`coverage`/`files`）**全部进摘要**，
于是「只换了时间戳」读成同一份清单，而「清单里某个文件的 sha256 变了」读成不同。

这份模块被两头消费：`tests/conftest.py` 在生成报告时算一次并写进报告，
`scripts/closeout_verifier.py` 在验签时按磁盘当前清单再算一次并比对。
两处必须同一把尺，所以只允许这一处定义；它的独立性由
`tests/test_report_manifest_fingerprint.py` 里那份**另写一遍**的独立算式来判（不共享盲区）。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

# 每次重生都必然不同的字段：不进摘要。只剥顶层（`files[]` 里没有时间戳，`_build_environment`
# 那种嵌套结构也不在 SOURCE_MANIFEST 里），剥得越宽越可能把真实内容差洗成"相同"。
VOLATILE_KEYS = ("generated_at",)


def canonical_document(doc: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in doc.items() if k not in VOLATILE_KEYS}


def find_floats(node: Any, path: str = "") -> list[str]:
    """清单里出现 float 的位置（含嵌套）。空列表＝这份文档的规范摘要是**有定义**的。"""
    hits: list[str] = []
    if isinstance(node, dict):
        for k, v in node.items():
            hits += find_floats(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            hits += find_floats(v, f"{path}[{i}]")
    elif isinstance(node, float):
        hits.append(path or "(顶层)")
    return hits


def fingerprint_of_document(doc: dict[str, Any]) -> str:
    """规范化排序后 sha256；键序与缩进不参与摘要（同一内容两种排版必须同一读数）。"""
    canon = canonical_document(doc)
    # 现读（2026-09-29）：`SOURCE_MANIFEST.json` 里 float 0 个，所以本函数今天不需要
    # RFC 8785 的数字序列化。但 `json.dumps` 是按 Python 的 `repr` 落浮点的——
    # 一旦有值变成 float，`1` 与 `1.0` 会得同一个语义、**不同**的摘要，跨解释器/跨生产者就漂；
    # NaN/Infinity 更会直接产出非法 JSON。与其静默算出一个不可比的数，不如当场拒绝。
    bad = find_floats(canon)
    if bad:
        raise ValueError(
            "清单里出现 float ⇒ 规范摘要未定义（本尺只做整数/字符串/布尔/None，"
            f"没接 RFC 8785 的数字序列化）：{', '.join(bad[:5])}"
            " ⇒ 要么把该值落成整数（例如秒改成 ISO 字符串），要么把本尺换成 RFC 8785 实现")
    text = json.dumps(canon, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fingerprint_from_file(path: Path) -> tuple[str, str]:
    """返回 (指纹, 错误说明)。读不出时指纹为空串——调用方据此判前提塌，不折算成违规。"""
    if not path.is_file():
        return "", f"清单文件不存在：{path}"
    if path.is_dir():
        return "", f"是目录不是文件：{path}"
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return "", f"读不出：{type(exc).__name__}: {exc}"
    if not isinstance(doc, dict):
        return "", f"顶层不是对象：{type(doc).__name__}"
    try:
        return fingerprint_of_document(doc), ""
    except ValueError as exc:
        # 前提塌（空指纹）而不是违规：调用方据此阻塞收尾，不许把"算不出"读成"内容不同"。
        return "", str(exc)


if __name__ == "__main__":
    import sys
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("SOURCE_MANIFEST.json")
    fp, err = fingerprint_from_file(target)
    print(fp if fp else f"前提不成立：{err}")
    sys.exit(0 if fp else 2)
