"""上一版交付物清单（delivery baseline）：把「自上次发布以来只改了这些」变成可比对的事实。

第 27 片的发布证据能逐条回答「这份内容是哪张单带来的」，但答不了另一半天真的问题：
**这次到底改了多少**——因为「没被任何单提到」既可能是「没动过」，也可能是「动了没提单」，
两者在字节层面长得一样。要有区分，必须有一个**上一版的清单**当基准。

这一格刻意不做成「整仓文件清单的差集」：本仓实测过，自 v5.6.0 的锚定 tag 以来
`SOURCE_MANIFEST` 有 101 增 / 9 删 / 82 改，把它们全要求成有单覆盖，只能靠**补写一百多张
事后变更单**才能变绿——那是造证据，不是补证据。所以基线的**作用域 = 本次发布真正交出去的
带哈希交付物**（`release_manifest` 已经算得出的那一小集合），由同一个生产者落盘。

两条形状规矩：

- **易变字段由生产者声明，不靠自由 ignore 列表**。侧车带 `generated_at`，重新生成一次
  原始 sha256 就变了；若按原始字节比，「只是又跑了一遍」会被读成工程变更。
  所以比对用**语义摘要**（递归剔掉声明过的键再规范化求哈希）。
  反证也要常驻：**改一个真结论必须推动摘要**，否则「易变」二字就能把任何改动洗成没变。
- **基线缺失不折算成「什么都没改」**。读不到基线 ⇒ `baseline_coverage="absent"`，
  生产者不新增阻断，但**也绝不声称**「只改了这些」。
"""
from __future__ import annotations

import hashlib
import json
import posixpath
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASELINE_KIND = "aipd.delivery_baseline.v1"

#: 每次生成都必然变化的字段名。**只**允许按名字剔除，且必须是生产者自己写的那几个。
VOLATILE_FIELDS = frozenset({"generated_at", "accessed", "accessed_at", "generated_at_utc"})


def normalise(path: str) -> str:
    """交付物标识的规范形状：反斜杠转正斜杠再去掉冗余段。"""
    return posixpath.normpath(str(path).replace("\\", "/"))


def semantic_digest(path: Path) -> dict[str, Any]:
    """一个文件的「原始哈希 + 语义摘要」。

    JSON 文件：语义摘要 = 递归剔掉 `VOLATILE_FIELDS` 后规范化 dump 的 sha256；
    其他文件（STEP/DXF/Markdown 是文本或二进制，没有可声明的字段名）：语义摘要 = 原始哈希，
    即**不假装**能忽略什么。
    """
    raw = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    out: dict[str, Any] = {"sha256": raw, "semantic_sha256": raw, "volatile_dropped": []}
    try:
        loaded = json.loads(Path(path).read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, OSError):
        return out
    if not isinstance(loaded, dict):
        return out
    dropped = _strip_volatile(loaded)
    blob = json.dumps(loaded, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    out["semantic_sha256"] = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    out["volatile_dropped"] = sorted(dropped)
    return out


def _strip_volatile(node: Any, trail: str = "") -> list[str]:
    """原地剔掉易变键，返回被剔位置的清单（交出去，便于人核「到底省了什么」）。"""
    dropped: list[str] = []
    if isinstance(node, dict):
        for key in [k for k in node if k in VOLATILE_FIELDS]:
            dropped.append(f"{trail}/{key}")
            node.pop(key, None)
        for key, value in node.items():
            dropped.extend(_strip_volatile(value, f"{trail}/{key}"))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            dropped.extend(_strip_volatile(value, f"{trail}[{index}]"))
    return dropped


def artefact_index(artifacts: dict[str, str], root: Path | str) -> dict[str, dict[str, Any]]:
    """给每条交付物补上语义摘要；磁盘上读不到的记 `unreadable`，不折算成 0 哈希。"""
    base = Path(root)
    index: dict[str, dict[str, Any]] = {}
    for path, digest in sorted(artifacts.items()):
        key = normalise(path)
        target = base / key
        if not target.is_file():
            index[key] = {"sha256": digest, "semantic_sha256": "",
                          "volatile_dropped": [], "unreadable": True}
            continue
        index[key] = semantic_digest(target)
    return index


def write_baseline(path: Path | str, artifacts: dict[str, str], root: Path | str, *,
                   release: str = "", source_commit: str = "",
                   release_ready: bool | None = None,
                   acknowledgement: str = "",
                   now: datetime | None = None) -> dict[str, Any]:
    """把「这次交出去的东西」落成下一次的基线。

    `release_ready` / `acknowledgement` 只是留痕：一份**没通过就绪判定**的证据
    也可以被登记成基线（先落盘、后补单的流程确实存在），但调用方必须显式承认它没就绪，
    否则下一轮会把「没人放行过的一次运行」当成「上一版交付」来比对。
    """
    moment = now or datetime.now(timezone.utc)
    doc = {"kind": BASELINE_KIND,
           "written_at": moment.isoformat(),
           "release": release,
           "source_commit": source_commit,
           "release_ready": release_ready,
           "acknowledgement": acknowledgement,
           "artifacts": artefact_index(artifacts, root)}
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")
    return doc


def load_baseline_semantics(path: Path | str) -> dict[str, str]:
    """读回基线的 {交付物: 语义摘要}。文件不在 ⇒ 空表（调用方按「没有基线」处理）。"""
    target = Path(path)
    if not target.is_file():
        return {}
    doc = json.loads(target.read_text(encoding="utf-8"))
    if doc.get("kind") != BASELINE_KIND:
        raise ValueError(f"{path} 不是 {BASELINE_KIND}，拒绝当基线用")
    return {normalise(k): str(v.get("semantic_sha256") or "")
            for k, v in (doc.get("artifacts") or {}).items()}


def diff_since_baseline(current: dict[str, str], baseline: dict[str, str]) -> dict[str, list[str]]:
    """四条差集。`unchanged` = 语义摘要逐字相等 ⇒ 这一条**不需要**变更单。"""
    added = sorted(set(current) - set(baseline))
    removed = sorted(set(baseline) - set(current))
    modified = sorted(p for p in set(current) & set(baseline)
                      if current[p] != baseline[p])
    unchanged = sorted(set(current) & set(baseline))
    return {"added": added, "removed": removed, "modified": modified,
            "unchanged": [p for p in unchanged if p not in set(modified)]}
