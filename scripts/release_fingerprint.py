#!/usr/bin/env python3
"""清单指纹：`SOURCE_MANIFEST.json` **内容**的规范摘要（去掉每次重生都会变的 `generated_at`）。

为什么不是整份文件的 sha256（这是本轮实测出来的，不是推的）：
`scripts/release_evidence.py:133` 每次生成都把 `generated_at` 写成当前时间，所以原始字节
摘要在每轮收尾的「刷清单 → 跑全量 → 绑定」三步之间必然不同——拿它当判据就是给正常流程
判一条假红。规范摘要只吃`version`/`source_commit`/`coverage`/`files`这些**内容**字段，
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


def fingerprint_of_document(doc: dict[str, Any]) -> str:
    """规范化排序后 sha256；键序与缩进不参与摘要（同一内容两种排版必须同一读数）。"""
    text = json.dumps(canonical_document(doc), sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"))
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
    return fingerprint_of_document(doc), ""


if __name__ == "__main__":
    import sys
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("SOURCE_MANIFEST.json")
    fp, err = fingerprint_from_file(target)
    print(fp if fp else f"前提不成立：{err}")
    sys.exit(0 if fp else 2)
