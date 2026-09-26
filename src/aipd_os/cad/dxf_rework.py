"""图纸制品（DXF）的**返工执行器**（F-REWORK-DXF 第 47 片）。

第 46 片把「声明 → 图纸」的边接上之后，`aipd truth propagate` 才真的会生成
`drawing_dxf` 的返工任务；而第 45 片的执行器只认 `drawing_spec`，所以那些任务今天的
正确处置是「在烧 attempts 之前逐条点名拒掉」。本片把执行器补上，让"图纸要重画"
这件事真的能被执行一次并收口。

判据形状：

- **视图是派生物，重算是显式一步**（本轮实读 FreeCAD TechDraw 文档：视图靠 `Source`
  挂在实体上，模型变了要 `doc.recompute()` 才更新）。所以这里不"顺手改文件"，
  而是按记录里那份**输入集合**重跑一次出图；出图本身由调用面注入的 `render` 完成
  （`cad` 层不 import CLI 层，也不假装自己能投影）。
- **要不要重跑按输入签名判**，不按产物字节（沿用 Bazel action key 的取舍，第 46 片实读）：
  当前输入算出的签名与记录里的相同 ⇒ `unchanged`，产物一个字节都不动。
- **三条失败比一条假成功值钱**：记录不是本执行器认识的制品、缺输入、声明/模型源文件读不到，
  一律 `ok=False` 交回引擎的有界退避。特别是**缺输入**这一支：第 46 片之前写的记录里
  没有 `model_*` / `material` / `sections` / `details`，那些记录**重建不出同一次出图**，
  执行器必须点名拒掉，而不是拿「默认黄金模型 + 空剖切」猜一遍——猜出来的图会被
  记成"按当前声明重算过"。

三态与第 45 片同形：`unchanged`（签名一致且磁盘产物仍是那份）、
`rewrote`（签名变了 ⇒ 重跑出图并把这条记录演进到新的输入集合）、
`file_restored`（签名没变但文件被删/被手改 ⇒ 只把文件补回来）。

**返工不新增版本记录**：引擎 `run_rework` 成功时是对**这一条**记录 bump 版本、关 stale，
所以执行器更新它本身（与第 45 片对声明做的事一致）。「换输入 ⇒ 另起一版、旧版标
superseded」是**生产面**（`aipd drawing generate`）的规则，两边刻意不同，各自钉着。
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Callable

from aipd_os.cad.dxf_lineage import (
    dxf_input_signature,
    dxf_version_content,
    model_input_digest,
    spec_file_digest,
)

__all__ = ["SUPPORTED_ARTIFACT", "rework_dxf_artifact", "make_dxf_rework_fn"]

SUPPORTED_ARTIFACT = "drawing_dxf"

# 重建一次出图所需的全部输入。缺任何一项都无法诚实重算。
REQUIRED_INPUTS = ("path", "part", "revision", "views", "scale", "sheet",
                   "material", "sections", "details", "model_kind",
                   "model_source", "model_digest", "input_signature")

OUTCOMES_OK = ("unchanged", "rewrote", "file_restored")


def _file_sha256(path: Any) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def _fail(truth_id: str, outcome: str, **extra: Any) -> dict[str, Any]:
    return {"truth_id": truth_id, "ok": False, "outcome": outcome, **extra}


def _current_model(meta: dict[str, Any]) -> tuple[str | None, str | None]:
    """按记录里那份模型来源重算摘要；返回 (digest, 错误)。"""
    kind = str(meta.get("model_kind") or "")
    source = str(meta.get("model_source") or "")
    if kind == "golden_default":
        return model_input_digest(step=None, native=None)["digest"], None
    if kind not in ("step", "native"):
        return None, f"不认识的模型来源类型：{kind!r}"
    if not source or not Path(source).is_file():
        return None, f"模型源文件读不到：{source or '（记录里没写路径）'}"
    kwargs = {"step": source} if kind == "step" else {"native": source}
    return model_input_digest(**kwargs)["digest"], None


def _find_spec_record(store: Any, path: str, spec_sha: str | None) -> str | None:
    """按 (声明路径, 当前声明哈希) 找上游记录；找不到就 None，不猜最近的一条。"""
    if not path:
        return None
    for rec in store.query(record_type="artifact_version"):
        meta = rec.metadata or {}
        if meta.get("artifact") != "drawing_spec" or str(meta.get("path")) != path:
            continue
        if spec_sha is None or str(meta.get("spec_sha256")) == spec_sha:
            return str(rec.record_id)
    return None


def rework_dxf_artifact(store: Any, truth_id: str, *,
                        render: Callable[[dict[str, Any]], str]) -> dict[str, Any]:
    """按当前输入重算一次图纸；`render(meta)` 负责真出图并回产物 sha256。"""
    from aipd_os.product_truth.lineage import LineageGraph
    from aipd_os.product_truth.models import SourceRef

    try:
        rec = store.get(truth_id)
    except KeyError:
        return _fail(truth_id, "missing_record")
    meta = dict(rec.metadata or {})
    if meta.get("artifact") != SUPPORTED_ARTIFACT:
        return _fail(truth_id, "unsupported_artifact",
                     artifact=meta.get("artifact"),
                     reason="本执行器只认 drawing_dxf")
    missing = [k for k in REQUIRED_INPUTS if meta.get(k) in (None, "")]
    if missing:
        return _fail(truth_id, "missing_inputs", missing_inputs=missing,
                     reason="这些输入没记在版本里，重建不出同一次出图——"
                            "拿默认值猜一遍会被记成「按当前声明重算过」")

    path = Path(str(meta["path"]))
    spec_path = str(meta.get("spec_path") or "")
    spec_sha: str | None = None
    if spec_path:
        spec_sha = spec_file_digest(Path(spec_path))
        if spec_sha is None:
            return _fail(truth_id, "missing_spec_file", spec_path=spec_path,
                         reason="记录声明了上游声明文件，但它读不到/不是合法 JSON")
    model_sha, model_err = _current_model(meta)
    if model_err:
        return _fail(truth_id, "model_unavailable", reason=model_err)

    signature = dxf_input_signature(
        spec_sha256=spec_sha,
        model={"kind": str(meta["model_kind"]),
               "source": str(meta["model_source"]), "digest": str(model_sha)},
        part=str(meta["part"]), revision=str(meta["revision"]),
        views=[str(v) for v in meta["views"]], scale=float(meta["scale"]),
        sheet=str(meta["sheet"]), material=str(meta["material"]),
        sections=[str(s) for s in meta["sections"]],
        details=[str(d) for d in meta["details"]])

    sig_changed = signature != str(meta["input_signature"])
    on_disk = _file_sha256(path)
    if not sig_changed and on_disk == str(meta.get("dxf_sha256")):
        store.update(truth_id, metadata={**meta, "model_digest": str(model_sha),
                                         "spec_sha256": spec_sha,
                                         "last_rework": {
                                             "outcome": "unchanged",
                                             "input_signature": signature}})
        return {"truth_id": truth_id, "ok": True, "outcome": "unchanged",
                "path": str(path), "input_signature": signature,
                "spec_sha256": spec_sha, "dxf_sha256": on_disk,
                "edges": 0, "file_written": False}

    outcome = "rewrote" if sig_changed else "file_restored"
    try:
        written = render(meta)
    except Exception as exc:  # 出图失败不是"返工完成"
        return _fail(truth_id, "render_failed",
                     reason=f"{type(exc).__name__}: {exc}")
    rendered_sha = str(written or "")
    disk_sha = _file_sha256(path)
    if not disk_sha:
        return _fail(truth_id, "render_failed",
                     reason=f"{outcome} 之后磁盘上读不到产物：{path}")
    if rendered_sha and disk_sha != rendered_sha:
        return _fail(truth_id, "render_disagrees",
                     expected=rendered_sha, on_disk=disk_sha,
                     reason="执行器回到的哈希与磁盘现状不一致——不能拿它 bump 版本")

    upstream = _find_spec_record(store, spec_path, spec_sha)
    content = dxf_version_content(dxf_name=path.name, signature=signature,
                                  spec_sha256=spec_sha)
    store.update(truth_id, content=content,
                 source=SourceRef(file=str(path),
                                  note=f"input_signature={signature[:16]}"),
                 metadata={**meta, "input_signature": signature,
                           "spec_path": spec_path, "spec_sha256": spec_sha,
                           "spec_record_id": upstream,
                           "model_digest": str(model_sha),
                           "dxf_sha256": disk_sha,
                           "last_rework": {"outcome": outcome,
                                           "input_signature": signature,
                                           "upstream_record_id": upstream}})
    if upstream is not None:
        graph = LineageGraph(store)
        graph.add_edge(upstream, truth_id, "affects")
    return {"truth_id": truth_id, "ok": True, "outcome": outcome,
            "path": str(path), "input_signature": signature,
            "spec_sha256": spec_sha, "dxf_sha256": disk_sha,
            "upstream_record_id": upstream, "file_written": True,
            "edges": 1 if upstream is not None else 0}


def make_dxf_rework_fn(store: Any, render: Callable[[dict[str, Any]], str]
                       ) -> Callable[[str], bool]:
    """给 `PropagationEngine.run_rework` 的 `rework_fn`（只认 True/False）。"""

    def rework_fn(truth_id: str) -> bool:
        return rework_dxf_artifact(store, truth_id, render=render)["ok"] is True

    return rework_fn
