"""图纸声明的**返工执行器**（F-REWORK 第 45 片）。

`PropagationEngine.run_rework` 一直带着一句诚实拒绝：不给 `rework_fn` 就判 `blocked`，
"绝不伪造成功"。此前它在 `src/` 里是 0 调用点——不是漏接，而是本仓确实没有执行器，
而一条永远只能输出 `blocked` 的命令比没有命令更容易被读成"返工跑过了"。
这一片补上那个执行器，判据形状借两条成熟实现（都是本轮实读的文档，不是凭记忆）：

- dbt 的 `state:modified`：**拿当前节点签名与上一份 manifest 比**才判"变了"，
  纯 cosmetic 字段（tags/meta）的变化刻意不算变更；
- BitBake：`STAMPS_DIR` 里存在**输入校验和匹配的戳文件**才算上次产物仍有效，
  否则重跑；上游签名变 ⇒ 下游任务哈希连锁变 ⇒ 整条依赖链重算。

于是这里分三种结论，而且**只有这三种**：

1. `unchanged` —— 按当前 active CTQ 重算出的声明与记录里的 `spec_sha256` 相同，
   **且磁盘上那份文件重算后哈希也仍相同** ⇒ 什么都不写（产物文件一个字节都不动），
   只在记录上留一条"返工跑过、证明未变"的结论；
2. `rewrote` / `file_restored` —— 内容确实变了（`rewrote`），或内容没变但文件被删/被手改
   （`file_restored`，对应 BitBake 的"戳失配就重跑"）⇒ 用同一个 renderer 重写文件，
   更新记录的 content/metadata/source，并给新的 CTQ 引用集合补边；
3. `gap` / `unsupported_artifact` / `missing_path` —— 重算出缺口（补齐 CTQ 之前这份声明
   本来就不该存在）、记录不是本执行器认识的制品、或没写产物路径 ⇒ **返回失败**，
   交回引擎的有界退避与 max_attempts（不许把它记成"返工完成"）。

`unsupported_artifact` 这一支必须在**消费 attempts 之前**由调用面先问一次
（见 `artifact_kind`）：拿一次注定失败的尝试去烧配额，等于让引擎替我们把
"这格还没接执行器"伪装成"返工失败了三次"。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from aipd_os.cad.spec_lineage import SUPPORTED_ARTIFACT, render_spec_text, spec_content, spec_digest

__all__ = ["SUPPORTED_ARTIFACT", "artifact_kind", "rework_artifact",
           "make_rework_fn"]

OUTCOMES_OK = ("unchanged", "rewrote", "file_restored")


def artifact_kind(store: Any, truth_id: str) -> str | None:
    """这条 truth 记录是哪类制品；读不到就返回 None，不猜。"""
    try:
        rec = store.get(truth_id)
    except KeyError:
        return None
    return str((rec.metadata or {}).get("artifact") or "") or None


def _file_digest(path: Path) -> str | None:
    """按**内容**比文件还是那一份：解析后走同一个 canonical 哈希，
    所以缩进/键序这类排版差异不会被当成"改动"（dbt 对 cosmetic 字段的取舍同理）。"""
    try:
        return spec_digest(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return None


def rework_artifact(store: Any, truth_id: str) -> dict[str, Any]:
    """执行一次返工并给出结论；`ok` 为真时引擎才会 bump 版本、关闭 stale。"""
    from aipd_os.cad.spec_from_truth import spec_from_ctq
    from aipd_os.product_truth.lineage import LineageGraph
    from aipd_os.product_truth.models import SourceRef

    try:
        rec = store.get(truth_id)
    except KeyError as exc:
        return {"truth_id": truth_id, "ok": False, "outcome": "missing_record",
                "reason": str(exc)}

    meta = dict(rec.metadata or {})
    kind = meta.get("artifact")
    if kind != SUPPORTED_ARTIFACT:
        return {"truth_id": truth_id, "ok": False, "outcome": "unsupported_artifact",
                "reason": f"本执行器只认 artifact={SUPPORTED_ARTIFACT}，实际是 {kind!r}"}

    path = Path(str(meta.get("path") or ""))
    if not str(path):
        return {"truth_id": truth_id, "ok": False, "outcome": "missing_path",
                "reason": "记录里没有产物路径，重算出来的声明无处可写"}

    records = store.query(record_type="ctq", status="active")
    spec, gaps = spec_from_ctq(records)
    if gaps:
        return {"truth_id": truth_id, "ok": False, "outcome": "gap",
                "reason": f"重算出 {len(gaps)} 条缺口，补齐之前这份声明本就不该存在",
                "gap_kinds": [str(g.get("kind")) for g in gaps]}

    content, digest, refs = spec_content(spec, path)
    recorded = str(meta.get("spec_sha256") or "")
    on_disk = _file_digest(path)
    content_changed = digest != recorded
    file_lost = on_disk != digest          # 文件没写、读不出、或内容已不是这一份

    if not content_changed and not file_lost:
        outcome, wrote = "unchanged", False
    else:
        outcome = "rewrote" if content_changed else "file_restored"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_spec_text(spec), encoding="utf-8")
        wrote = True

    store.update(truth_id, content=content,
                 source=SourceRef(file=str(path), note=f"spec_sha256={digest}"),
                 metadata={**meta, "spec_sha256": digest, "ctq_refs": refs,
                           "last_rework": {"outcome": outcome,
                                           "artifact_sha256_before": recorded,
                                           "artifact_sha256_after": digest,
                                           "disk_matched_before": not file_lost,
                                           "file_written": wrote}})
    graph = LineageGraph(store)
    for ctq_id in refs:
        graph.add_edge(ctq_id, truth_id, "affects")

    return {"truth_id": truth_id, "ok": True, "outcome": outcome,
            "path": str(path), "spec_sha256": digest, "ctq_refs": refs,
            "file_written": wrote, "edges": len(refs)}


def make_rework_fn(store: Any) -> Callable[[str], bool]:
    """给 `PropagationEngine.run_rework` 的 `rework_fn`：只回布尔，细节由调用面另取。"""
    def rework_fn(truth_id: str) -> bool:
        return rework_artifact(store, truth_id)["ok"] is True

    return rework_fn
