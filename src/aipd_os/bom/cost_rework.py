"""成本结论（`bom_cost`）的**返工执行器**（F-REWORK-COST 第 49 片）。

第 48 片把「BOM 版本 → 成本结论」的边接上之后，`aipd truth propagate` 才真的开始生成
`bom_cost` 的返工任务，而那些任务的处置仍是「在烧 attempts 之前逐条点名拒掉」。
本片补上执行器：**按记录里那份口径把这笔成本重算一遍**，并把这一条记录演进到新结果。

判据形状（与第 47 片同形，逐条都有出处）：

- **重算是显式一步，且由调用面注入**：`bom` 层不 import CLI 层，也不自己读 BOM 表；
  `recalc(meta)` 由 CLI 侧提供（它才知道怎么从 `args.db` 取当前 BOM 行、怎么装 `CostInputs`）。
- **执行器绝不走生产面的写版本路径**。引擎 `run_rework` 成功时是对**这一条**记录
  bump 版本、关 stale（`product_truth/propagation.py` 的 `bump_version(task.truth_id)`），
  所以这里用 `store.update` 演进它本身；「换输入另起一版 + 旧版标 superseded」是
  `cost calc --truth-lineage`（生产面）的规则，两边刻意不同。
  ⇒ CLI 侧的重算器**不带** `--truth-lineage`：带了就会在 BOM 真的动了时另起一对新版本，
  与「返工不新增版本记录」直接冲突。
- **签名一致而数值不一致 ⇒ 拒**（对应第 47 片的 `render_disagrees`）。
  成本核算是确定性的（同输入必同数），所以「签名没变但 total 变了」只能意味着
  计算器被改坏了或输入集合漏了项——不能拿它 bump 版本。
- **缺输入点名拒，不猜**：第 48 片写的记录里**没有**口径五项的值（只有哈希），
  那些记录重建不出同一次核算。拿 `--tooling 0 --margin 0` 猜一遍，会得到一条
  「按当前 BOM 重算过」的假结论，比不重算更坏。
- **成本不完整 ⇒ 不算收口**：`compute_bom_cost` 在缺供应商/单价时明写
  `cost_complete=False`（不拿 0 元假装），所以这种结果也不能把 stale 关掉。
"""
from __future__ import annotations

from typing import Any, Callable

from aipd_os.bom.cost_lineage import (
    ARTIFACT_COST,
    version_content,
)

__all__ = ["SUPPORTED_ARTIFACT", "rework_cost_artifact", "make_cost_rework_fn"]

SUPPORTED_ARTIFACT = ARTIFACT_COST

# 重建一次核算所需的输入。amortize_over 合法值就是 None（缺省=目标数量），
# 所以它只查「键在不在」，不查「值真不真」——否则 0.0 与 None 会被混成同一种缺。
REQUIRED_INPUTS = ("bom_id", "tooling_fee", "target_quantity", "nre",
                   "margin_pct", "input_signature")
REQUIRED_KEYS = ("amortize_over",)

# recalc 必须回报这些，缺一项就没法诚实判定收口
REQUIRED_RECALC = ("bom_id", "cost_signature", "total_cost", "cost_complete")

OUTCOMES_OK = ("unchanged", "recomputed")


def _fail(truth_id: str, outcome: str, **extra: Any) -> dict[str, Any]:
    return {"truth_id": truth_id, "ok": False, "outcome": outcome, **extra}


def _find_bom_record(store: Any, bom_id: str) -> str | None:
    """按 bom_id 找**当前有效**（active/stale）的 BOM 版本记录；找不到就 None，不猜最近一条。"""
    for rec in store.query(record_type="artifact_version"):
        meta = rec.metadata or {}
        if meta.get("artifact") != "bom" or str(meta.get("bom_id")) != bom_id:
            continue
        if str(rec.status) in ("active", "stale"):
            return str(rec.record_id)
    return None


def rework_cost_artifact(store: Any, truth_id: str, *,
                         recalc: Callable[[dict[str, Any]], dict[str, Any]]
                         ) -> dict[str, Any]:
    """按记录里那份口径重算这笔成本；`recalc(meta)` 回当前输入下的核算结果。"""
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
                     reason="本执行器只认 bom_cost")
    missing = [k for k in REQUIRED_INPUTS if meta.get(k) in (None, "")]
    missing += [k for k in REQUIRED_KEYS if k not in meta]
    if missing:
        return _fail(truth_id, "missing_inputs", missing_inputs=missing,
                     reason="这些输入没记在版本里，重建不出同一次核算——"
                            "拿默认口径猜一遍会得到一条「按当前 BOM 重算过」的假结论")

    try:
        res = recalc(meta) or {}
    except Exception as exc:  # noqa: BLE001 - 重算失败不是「返工完成」
        return _fail(truth_id, "recalc_failed",
                     reason=f"{type(exc).__name__}: {exc}")
    if not isinstance(res, dict):
        return _fail(truth_id, "recalc_failed",
                     reason=f"重算器回的不是 dict：{type(res).__name__}")
    lack = [k for k in REQUIRED_RECALC if res.get(k) is None and k != "cost_complete"]
    if lack:
        return _fail(truth_id, "recalc_incomplete_result", missing_fields=lack,
                     reason="重算器没回这些字段，判定不了收口")

    if str(res["bom_id"]) != str(meta["bom_id"]):
        return _fail(truth_id, "bom_moved", recorded=str(meta["bom_id"]),
                     current=str(res["bom_id"]),
                     reason="这笔结论挂的 BOM 已经不是项目当前那份了——"
                            "拿别的 BOM 的行重算它，算出来的不是这笔账")

    if not bool(res["cost_complete"]):
        return _fail(truth_id, "cost_incomplete",
                     total_cost=res["total_cost"],
                     reason="当前 BOM 仍有行缺供应商/单价，核算不完整；"
                            "不完整的结果不能关掉 stale")

    new_sig = str(res["cost_signature"])
    same_sig = new_sig == str(meta["input_signature"])
    if same_sig and str(res["total_cost"]) != str(meta.get("total_cost")):
        return _fail(truth_id, "recalc_disagrees",
                     recorded=meta.get("total_cost"), current=res["total_cost"],
                     reason="输入签名没变而金额变了——确定性计算器不该给出这个读数，"
                            "不能拿它 bump 版本")

    if same_sig:
        store.update(truth_id, metadata={**meta, "last_rework": {
            "outcome": "unchanged", "total_cost": res["total_cost"],
            "input_signature": new_sig}})
        return {"truth_id": truth_id, "ok": True, "outcome": "unchanged",
                "bom_id": str(res["bom_id"]), "input_signature": new_sig,
                "total_cost": res["total_cost"], "edges": 0}

    upstream = _find_bom_record(store, str(meta["bom_id"]))
    content = version_content(artifact=ARTIFACT_COST, bom_id=str(meta["bom_id"]),
                              signature=new_sig, detail=f"total={res['total_cost']}")
    store.update(truth_id, content=content,
                 source=SourceRef(file=f"bom.db:{meta['bom_id']}",
                                  note=f"input_signature={new_sig[:16]}"),
                 metadata={**meta, "input_signature": new_sig,
                           "bom_signature": res.get("bom_signature",
                                                    meta.get("bom_signature")),
                           "total_cost": res["total_cost"],
                           "currency": res.get("currency", meta.get("currency")),
                           "bom_record_id": upstream or meta.get("bom_record_id"),
                           "last_rework": {"outcome": "recomputed",
                                           "input_signature": new_sig,
                                           "upstream_record_id": upstream}})
    edges = 0
    if upstream is not None:
        graph = LineageGraph(store)
        graph.add_edge(upstream, truth_id, "affects")
        edges = 1
    return {"truth_id": truth_id, "ok": True, "outcome": "recomputed",
            "bom_id": str(res["bom_id"]), "input_signature": new_sig,
            "total_cost": res["total_cost"],
            "upstream_record_id": upstream, "edges": edges}


def make_cost_rework_fn(store: Any,
                        recalc: Callable[[dict[str, Any]], dict[str, Any]]
                        ) -> Callable[[str], bool]:
    """给 `PropagationEngine.run_rework` 的 `rework_fn`（只认 True/False）。"""

    def rework_fn(truth_id: str) -> bool:
        return rework_cost_artifact(store, truth_id, recalc=recalc)["ok"] is True

    return rework_fn
