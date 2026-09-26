"""报价批次 → BOM 版本 的血缘生产者（F-LINEAGE-QUOTE 第 50 片）。

第 48/49 片把「BOM 版本 → 成本结论」这一跳接上之后，链上还剩一个方向是断的：
**没有任何生产者往 `artifact=bom` 那条记录连入边**。核对过的事实（不是推测）：
`supply_chain/` 的三个写点全是 `db.add_fact(...)`
（`persistence.py:46,83,118`、`writeback.py:47,78`、`impact.py:108`），
一处 `add_edge`、一处 `ProductTruthStore` 都没有；而 `artifact=bom` 的唯一写点是
`bom/cost_lineage.py:128`（只有跑过 `cost calc --truth-lineage` 才存在）。

后果说清楚：`apply_quotes_to_bom` 会把官方报价的单价**就地写进 BOM 行**，
于是「当初那笔成本是按哪些单价算的」在库里悄悄变了，而已经登记过的那条成本结论
仍然是 `active` —— 读的人看到「下游已处理」，其实报价换过了。
这正是最初 F-SUPPLY-03 登记的那句「声明的影响传播 vs 只有 payload」的同一族。

判据形状沿用本仓已定的三条（出处见各轮取证文档，本轮不做新的外部检索）：
1. **按输入签名认身份**（第 46 片 Bazel action key 那一支）：同一份报价文件重放命中同一条记录；
2. **连不上下游时记录照写、边数 0、点名原因**（第 46 片对上游那一条的镜像）——
   报价完全可以先于任何一次 `cost calc` 发生，那时 `artifact=bom` 那条记录**根本还不存在**，
   这不是失败，但也不能静默；
3. **opt-in 旗子 + 明说的跳过 + 写不进去判未收口**（第 48 片 `cost calc` 那一支同形）。
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

__all__ = ["ARTIFACT_QUOTE", "quote_input_signature", "record_quote_lineage",
           "version_content"]

ARTIFACT_QUOTE = "quote_batch"


def _canonical_sha256(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False,
                   separators=(",", ":")).encode("utf-8")).hexdigest()


def quote_input_signature(*, currency: str,
                          applied: list[dict[str, Any]]) -> str:
    """签名吃**全部参与判定的报价事实**：谁、哪个件、第几版、什么状态、单价、币种。

    币种必须在内——`quote apply` 按币种逐行核对，跨币种的两条报价不是同一件事。
    **文件名刻意不在内**：这条边的用途是「价换了就把当初据以定价的那版 BOM 标 stale」，
    同一批价从另一个路径的文件的读进来不是又一次工程变更。
    第 46 片同形：DXF 自己的 sha256 与 `$TDCREATE` 都不进签名，只当观测。
    """
    return _canonical_sha256({
        "kind": ARTIFACT_QUOTE, "currency": currency,
        "applied": sorted(
            ({"quote_id": str(a.get("quote_id")), "supplier": str(a.get("supplier")),
              "part": str(a.get("part")), "version": a.get("version"),
              "status": str(a.get("status")), "unit_price": a.get("unit_price"),
              "currency": str(a.get("currency"))}
             for a in applied),
            key=lambda d: (d["quote_id"], d["part"]))})


def version_content(*, signature: str, detail: str) -> str:
    """版本记录正文只有一个写法：生产者与（将来的）返工执行器必须写同一形状。"""
    return f"{ARTIFACT_QUOTE} inputs={signature[:16]} {detail}"


def find_current_bom_record(store: Any, *, tenant_id: str | None = None,
                            project_id: str | None = None) -> str | None:
    """找本项目**当前有效**（active/stale）的 `artifact=bom` 版本记录；没有就 None。

    返回 None 是合法读数：报价可以先于任何一次 `cost calc --truth-lineage` 发生。
    """
    for rec in store.query(record_type="artifact_version",
                           tenant_id=tenant_id, project_id=project_id):
        meta = rec.metadata or {}
        if meta.get("artifact") == "bom" and str(rec.status) in ("active", "stale"):
            return str(rec.record_id)
    return None


def record_quote_lineage(store: Any, *, signature: str, source: str,
                         currency: str, applied: list[dict[str, Any]],
                         tenant_id: str | None = None,
                         project_id: str | None = None) -> dict[str, Any]:
    """写一条报价批次版本记录，并把 `quote → 当前 BOM 版本` 的边连上。"""
    from aipd_os.product_truth.lineage import LineageGraph
    from aipd_os.product_truth.models import SourceRef, TruthRecord

    if not applied:
        return {"written": False, "reason": "没有任何参与判定的报价，不登记血缘",
                "records": 0, "edges": 0,
                "quote_record_id": None, "bom_record_id": None}

    official = [a for a in applied if str(a.get("status")) == "official"]
    detail = (f"quotes={len(applied)} official={len(official)} "
              f"parts={len({str(a.get('part')) for a in official})}")
    content = version_content(signature=signature, detail=detail)
    existing = store.find_id_by_type_and_content(
        "artifact_version", content, tenant_id=tenant_id, project_id=project_id)
    if existing is not None:                       # 同一份报价重放 ⇒ 同一条，不另起
        record_id = str(existing)
        created = False
    else:
        record_id = str(store.add(
            TruthRecord(record_type="artifact_version", content=content,
                        source=SourceRef(file=source or "quote",
                                         note=f"input_signature={signature[:16]}"),
                        trust_level="high",
                        metadata={"artifact": ARTIFACT_QUOTE, "source": source,
                                  "currency": currency,
                                  "input_signature": signature,
                                  "quotes": len(applied),
                                  "official": len(official),
                                  "quote_ids": sorted(str(a.get("quote_id"))
                                                      for a in applied)}),
            tenant_id=tenant_id, project_id=project_id))
        created = True

    tenant = tenant_id or store.tenant_id
    project = project_id or store.project_id
    graph = LineageGraph(store, tenant_id=tenant, project_id=project)
    bom_record = find_current_bom_record(store, tenant_id=tenant, project_id=project)
    edges = 0
    reason = None
    if bom_record is not None:
        graph.add_edge(record_id, bom_record, "affects")
        edges = 1
    else:
        # 连不上不静默：记录照写，但要说清楚这次没有下游可标
        reason = ("项目里还没有 artifact=bom 的版本记录（要先跑一次 "
                  "aipd cost calc --truth-lineage），本次只登记报价批次、边数 0")
    return {"written": True, "reason": reason, "records": 1, "edges": edges,
            "quote_record_id": record_id, "created": created,
            "bom_record_id": bom_record, "input_signature": signature}
