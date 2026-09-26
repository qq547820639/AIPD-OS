"""图纸声明 → DXF 制品的血缘生产者（F-LINEAGE-DXF 第 46 片）。

第 43 片接上「CTQ → 图纸声明」、第 45 片给声明接上返工执行器之后，链路的**第三跳**
仍然断着：改了 CTQ，`aipd truth propagate` 只能把那份声明标 stale，
而按旧声明画出来的那张 DXF 不受任何影响——读的人看到"下游已处理"就等于把图纸放过了。
这一片把这条边补上：`aipd drawing generate --db …` 成功出图后写一条
`artifact_version`（`metadata.artifact=drawing_dxf`）记录，并连
`声明记录 → 图纸记录` 的 `affects` 边。

两条刻意的取舍：

1. **制品身份按输入签名，不按 DXF 输出字节。** 实测同一输入连跑两次出图：两份文件
   13170 行里只有 2 行不同，差的是 `$TDCREATE` / `$TDUPDATE` 那几个儒略日时间戳——
   按字节哈希会让"同样输入重跑一次"每次都另起一版，那是把时间戳当成工程变更。
   签名取输入（声明内容哈希 + part/revision/views/scale/sheet），
   与第 45 片借来的 dbt「比内容签名而不是比字节」、BitBake「比任务输入校验和」同形。
   DXF 自己的 sha256 仍然记进 metadata，作为**观测**而不是键。
2. **同一产物路径只留一版有效**：写入新版时把该路径上更早的那条标 `superseded`
   （第 44 片之后 `superseded` 在发布证据里是"可见但不算未收口"），
   否则一张图改十次就留下十条永久的下游，传播会把十条都打成待返工。

上游查不到（手写的 spec、或当时 `drawing spec` 没给 `--db`）时**记录照写、边数为 0**，
并把原因写进返回值——"没有上游可连"与"上游没参与"是两件事，不许混。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from aipd_os.cad.spec_lineage import spec_digest

__all__ = ["dxf_input_signature", "find_artifact_record", "record_dxf_lineage"]


def _canonical_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def dxf_input_signature(*, spec_sha256: str | None, part: str, revision: str,
                        views: list[str], scale: float, sheet: str) -> str:
    return _canonical_sha256({"kind": "drawing_dxf", "spec_sha256": spec_sha256,
                              "part": part, "revision": revision,
                              "views": list(views), "scale": scale,
                              "sheet": sheet})


def spec_file_digest(path: Path) -> str | None:
    """声明文件的**内容**哈希；读不出或不是 JSON ⇒ None（不可核，不是"没声明"）。"""
    try:
        return spec_digest(json.loads(Path(path).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return None


def find_artifact_record(store: Any, *, artifact: str, path: Path,
                         tenant_id: str | None = None,
                         project_id: str | None = None) -> str | None:
    """按 (制品类型, 产物路径) 找记录号；读不到就 None，不猜最近的一条。"""
    for rec in store.query(record_type="artifact_version",
                           tenant_id=tenant_id, project_id=project_id):
        meta = rec.metadata or {}
        if meta.get("artifact") == artifact and str(meta.get("path")) == str(path):
            return str(rec.record_id)
    return None


def record_dxf_lineage(store: Any, *, dxf_path: Path, spec_path: Path | None,
                       part: str, revision: str, views: list[str],
                       scale: float, sheet: str, relation: str = "affects",
                       dxf_sha256: str | None = None,
                       tenant_id: str | None = None,
                       project_id: str | None = None) -> dict[str, Any]:
    """写图纸制品的版本记录并连上游边，返回落库摘要（含边数为 0 的原因）。"""
    from aipd_os.product_truth.lineage import LineageGraph
    from aipd_os.product_truth.models import SourceRef, TruthRecord

    dxf = Path(dxf_path)
    spec_sha = spec_file_digest(spec_path) if spec_path else None
    signature = dxf_input_signature(spec_sha256=spec_sha, part=part,
                                    revision=revision, views=views,
                                    scale=scale, sheet=sheet)
    spec_tag = (spec_sha[:16] if spec_sha else "未知")
    content = (f"drawing dxf {dxf.name} inputs={signature[:16]} ← spec {spec_tag}")

    upstream = None
    upstream_reason = "未给 --spec：这张图没有可追的公差声明"
    if spec_path is not None:
        upstream = find_artifact_record(store, artifact="drawing_spec",
                                        path=Path(spec_path),
                                        tenant_id=tenant_id, project_id=project_id)
        if upstream is None:
            upstream_reason = ("按路径找不到声明的版本记录："
                               "当时 aipd drawing spec 没带 --db，或声明是手写的")

    metadata = {"artifact": "drawing_dxf", "path": str(dxf),
                "input_signature": signature, "spec_path": str(spec_path or ""),
                "spec_sha256": spec_sha, "spec_record_id": upstream,
                "part": part, "revision": revision, "views": list(views),
                "scale": scale, "sheet": sheet, "dxf_sha256": dxf_sha256}

    existing = store.find_id_by_type_and_content(
        "artifact_version", content, tenant_id=tenant_id, project_id=project_id)
    created = existing is None
    if created:
        previous = find_artifact_record(store, artifact="drawing_dxf", path=dxf,
                                        tenant_id=tenant_id, project_id=project_id)
        record_id = store.add(
            TruthRecord(record_type="artifact_version", content=content,
                        source=SourceRef(file=str(dxf),
                                         note=f"input_signature={signature[:16]}"),
                        trust_level="high", metadata=metadata),
            tenant_id=tenant_id, project_id=project_id)
        if previous is not None and previous != record_id:
            store.set_status(previous, "superseded",
                             tenant_id=tenant_id, project_id=project_id)
    else:
        record_id = str(existing)

    edges = 0
    if upstream is not None:
        graph = LineageGraph(store, tenant_id=tenant_id or store.tenant_id,
                             project_id=project_id or store.project_id)
        graph.add_edge(upstream, record_id, relation)
        edges = 1
    return {"record_id": record_id, "created": created,
            "upstream_record_id": upstream, "edges": edges,
            "upstream_reason": None if upstream else upstream_reason,
            "input_signature": signature, "spec_sha256": spec_sha,
            "dxf_sha256": dxf_sha256}
