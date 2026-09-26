"""BOM 版本记录（`artifact=bom`）的**返工执行器**（F-REWORK-BOM 第 53 片）。

第 51/52 片的 §六 都留了同一格：`aipd truth rework` 今天只认三类制品，
`artifact=bom` 落在「不认识 ⇒ 在烧 attempts 之前逐条点名拒」。
第 52 片把漂移**发现**接上之后，这一格变得更刺眼：扫描能把 BOM 版本点成
「该 stale 却还 active」，可发现之后仍然没有执行器收得口。

判据形状沿用已定的三条（出处见各轮取证文档，本轮不做新的外部检索）：

- **就地演进这一条记录，绝不另起新版**：引擎 `run_rework` 成功时是对**同一条**
  `bump_version(task.truth_id)`（`product_truth/propagation.py:196-199`），
  而「换输入另起一版 + 旧版标 superseded」是生产面 `cost calc --truth-lineage` 的规则
  （`cost_lineage._add_or_reuse`）。两边刻意不同，CLI 侧的重算器因此不写任何事实。
- **正文与 metadata 由生产面那份投影给出**（`bom_version_fields`）：
  两边各写一遍映射时，「签名相同、正文不同」这种读数谁都不会红（第 52 片同格）。
- **缺输入点名拒、不猜**（第 47/49 片同形），且**签名没变而身份字段变了 ⇒ 拒**：
  `bom_input_signature` 本来吃 `bom_id/revision/version_no/行集合`，
  同签名却给出不同 revision 只能意味着签名漏吃了某一项——不能拿它 bump 版本。

与成本那一支的一个真实差别：**BOM 现在没有行 ⇒ 不算收口**。
一条版本记录描述的是「那张 BOM 的那些行」，当前一张空的 BOM 重建不出它，
拿 0 行去演进等于把「行被删光了」写进历史当成一次正常返工。
"""
from __future__ import annotations

from typing import Any, Callable

from aipd_os.bom.cost_lineage import ARTIFACT_BOM, version_content

__all__ = ["SUPPORTED_ARTIFACT", "rework_bom_artifact", "make_bom_rework_fn"]

SUPPORTED_ARTIFACT = ARTIFACT_BOM

# 认不出「该重算哪张 BOM」的四项：缺任何一项都不猜最近一张
REQUIRED_INPUTS = ("bom_id", "revision", "input_signature")
# version_no 的合法值可以是 0，所以只查键在不在（第 49 片 amortize_over 同形）
REQUIRED_KEYS = ("version_no",)
# recalc 必须回报这些，缺一项就没法诚实判定收口
REQUIRED_RECALC = ("bom_id", "bom_signature", "revision", "line_count")

OUTCOMES_OK = ("unchanged", "recomputed")


def _fail(truth_id: str, outcome: str, **extra: Any) -> dict[str, Any]:
    return {"truth_id": truth_id, "ok": False, "outcome": outcome, **extra}


def rework_bom_artifact(store: Any, truth_id: str, *,
                        recalc: Callable[[dict[str, Any]], dict[str, Any]]
                        ) -> dict[str, Any]:
    """按当前 BOM 表把这条版本记录重算一遍；`recalc(meta)` 回当前世界的 BOM 投影。"""
    from aipd_os.bom.cost_lineage import bom_version_fields
    from aipd_os.product_truth.models import SourceRef

    try:
        rec = store.get(truth_id)
    except KeyError:
        return _fail(truth_id, "missing_record")
    meta = dict(rec.metadata or {})
    if meta.get("artifact") != SUPPORTED_ARTIFACT:
        return _fail(truth_id, "unsupported_artifact",
                     artifact=meta.get("artifact"),
                     reason="本执行器只认 bom")
    missing = [k for k in REQUIRED_INPUTS if meta.get(k) in (None, "")]
    missing += [k for k in REQUIRED_KEYS if k not in meta]
    if missing:
        return _fail(truth_id, "missing_inputs", missing_inputs=missing,
                     reason="这些输入没记在版本里，重建不出那一版 BOM——"
                            "拿当前最近一张猜一遍，得到的是「另一张 BOM 被登记成这一版的返工」")

    try:
        res = recalc(meta) or {}
    except Exception as exc:  # noqa: BLE001 - 重算失败不是「返工完成」
        return _fail(truth_id, "recalc_failed",
                     reason=f"{type(exc).__name__}: {exc}")
    if not isinstance(res, dict):
        return _fail(truth_id, "recalc_failed",
                     reason=f"重算器回的不是 dict：{type(res).__name__}")
    lack = [k for k in REQUIRED_RECALC
            if res.get(k) is None and k != "line_count"]
    if lack:
        return _fail(truth_id, "recalc_incomplete_result", missing_fields=lack,
                     reason="重算器没回这些字段，判定不了收口")

    if str(res["bom_id"]) != str(meta["bom_id"]):
        return _fail(truth_id, "bom_moved", recorded=str(meta["bom_id"]),
                     current=str(res["bom_id"]),
                     reason="这条记录挂的 BOM 已经不是项目当前那张了——"
                            "拿别的 BOM 的行演进它，写的不是这一版")

    if int(res.get("line_count") or 0) <= 0:
        return _fail(truth_id, "empty_bom", line_count=res.get("line_count"),
                     reason="当前 BOM 没有行，重建不出这一版的行集合；"
                            "空表不能把 stale 关掉")

    header = res.get("header")
    lines = res.get("lines")
    new_sig = str(res["bom_signature"])
    same_sig = new_sig == str(meta["input_signature"])
    if same_sig and (str(res["revision"]) != str(meta["revision"])
                     or str(res["version_no"]) != str(meta["version_no"])):
        return _fail(truth_id, "recalc_disagrees",
                     recorded=f"{meta['revision']}/{meta['version_no']}",
                     current=f"{res['revision']}/{res['version_no']}",
                     reason="输入签名没变而身份字段变了——签名漏吃了这一项，"
                            "不能拿它 bump 版本")

    if header is None or lines is None:
        # 演进要走生产面那份投影，recalc 没把 BOM 表交回来就写不出同形状的正文
        return _fail(truth_id, "recalc_incomplete_result",
                     missing_fields=[k for k in ("header", "lines")
                                     if res.get(k) is None],
                     reason="重算器没交出 BOM 表本体，投影函数用不了，"
                            "只能拒——自己拼一份正文就是第二份映射")

    fields = bom_version_fields(header, lines, signature=new_sig)
    if same_sig:
        store.update(truth_id, metadata={**meta, "last_rework": {
            "outcome": "unchanged", "input_signature": new_sig,
            "line_count": res["line_count"]}})
        return {"truth_id": truth_id, "ok": True, "outcome": "unchanged",
                "bom_id": str(res["bom_id"]), "input_signature": new_sig,
                "line_count": res["line_count"], "edges": 0}

    content = version_content(artifact=ARTIFACT_BOM, bom_id=str(meta["bom_id"]),
                              signature=new_sig, detail=fields["detail"])
    store.update(truth_id, content=content,
                 source=SourceRef(file=f"bom.db:{meta['bom_id']}",
                                  note=f"input_signature={new_sig[:16]}"),
                 metadata={**fields["metadata"],
                           "last_rework": {"outcome": "recomputed",
                                           "input_signature": new_sig,
                                           "recorded_signature":
                                               str(meta["input_signature"])}})
    return {"truth_id": truth_id, "ok": True, "outcome": "recomputed",
            "bom_id": str(res["bom_id"]), "input_signature": new_sig,
            "recorded_signature": str(meta["input_signature"]),
            "previous_revision": str(meta["revision"]),
            "revision": str(res["revision"]),
            "line_count": res["line_count"], "edges": 0}


def make_bom_rework_fn(store: Any,
                       recalc: Callable[[dict[str, Any]], dict[str, Any]]
                       ) -> Callable[[str], bool]:
    """给 `PropagationEngine.run_rework` 的 `rework_fn`（只认 True/False）。"""

    def rework_fn(truth_id: str) -> bool:
        return rework_bom_artifact(store, truth_id, recalc=recalc)["ok"] is True

    return rework_fn
