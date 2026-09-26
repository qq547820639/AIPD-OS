"""「BOM 版本 → 成本结论」的血缘生产者（F-LINEAGE-COST 第 48 片）。

成本今天写回 `facts` 表的 `cost.total`（status C），但那行只留一句
`bom=<bom_id> qty=… tooling=…` 的**拼串**（`cli/commands_manufacturing.py` 里
`db.add_fact(... conditions=...)`）——事后既问不出「哪些行、哪一版 BOM 供了这个数」，
`truth propagate` 也打不到它：`bom/` 与 `supply_chain/` 里没有任何 `add_edge` 调用点。
这一片补的就是那条边，形状照第 46 片（`cad/dxf_lineage.py`）：

1. **身份按输入签名，不按结论数值**。成本记录的签名 = BOM 身份（bom_id/revision/version_no）
   + **参与行的集合**（每行的 line_id/item/quantity/unit_cost/currency/status/quote_ref/
   version_no）+ 口径五项（tooling/target_quantity/amortize_over/nre/margin）。
   只写数字或只写 `bom_id` 都不够：口径变而 BOM 不变时，旧结论会被当成仍然成立。
   BOM 版本记录自己的签名 = 前两项（不含口径）——**改价不改口径也必须有新 BOM 版本**，
   否则「报价回来把单价改了」这件事在血缘里是隐形的。
2. **同一作用域只留一版有效**：写新版时把同 artifact 的旧版标 `superseded`
   （第 44 片之后 `superseded` 在发布证据里是"可见但不算未收口"）。否则一张 BOM 改十次
   就有十条永久下游，传播会把十条都打成待返工。
3. **BOM 为空 / 没有行**时什么都不写：一份算了个空的结果没有版本可言
   （与该命令现有的「BOM 为空，先 aipd bom add」一致）。
4. **opt-in**：`cost calc` 的 `--db` 本来就是状态库（不加新语义），登记血缘要显式
   `--truth-lineage`；不给就**明说跳过**（不是静默），给了却写不进去则判未收口，
   `--json` 的 `ok` 与退码同向（第 43/46 片同一条纪律）。
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

__all__ = ["bom_input_signature", "cost_input_signature", "record_cost_lineage"]

ARTIFACT_BOM = "bom"
ARTIFACT_COST = "bom_cost"


def _canonical_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _line_facts(lines: list[Any]) -> list[dict[str, Any]]:
    """参与行的可枚举身份：按 line_id 排序，保证同一集合得到同一签名。"""
    out = []
    for line in sorted(lines, key=lambda ln: str(ln.line_id)):
        out.append({"line_id": str(line.line_id), "item": str(line.item),
                    "quantity": line.quantity, "unit_cost": line.unit_cost,
                    "currency": line.currency, "status": str(line.status),
                    "quote_ref": line.quote_ref, "version_no": line.version_no})
    return out


def bom_input_signature(*, bom_id: str, revision: str, version_no: Any,
                        lines: list[Any]) -> str:
    return _canonical_sha256({"kind": ARTIFACT_BOM, "bom_id": bom_id,
                             "revision": revision, "version_no": version_no,
                             "lines": _line_facts(lines)})


def cost_input_signature(*, bom_signature: str, tooling_fee: float,
                         target_quantity: int, amortize_over: int | None,
                         nre: float, margin_pct: float) -> str:
    return _canonical_sha256({"kind": ARTIFACT_COST, "bom_signature": bom_signature,
                             "tooling_fee": tooling_fee,
                             "target_quantity": target_quantity,
                             "amortize_over": amortize_over, "nre": nre,
                             "margin_pct": margin_pct})


def version_content(*, artifact: str, bom_id: str, signature: str,
                    detail: str) -> str:
    """版本记录正文只有一个写法：生产者与（将来的）返工执行器必须写同一形状。"""
    return f"{artifact} {bom_id} inputs={signature[:16]} {detail}"


def _find_current(store: Any, *, artifact: str, bom_id: str) -> str | None:
    """同 artifact + 同 bom_id 的**有效**（active/stale）记录号；没有就 None。"""
    for rec in store.query(record_type="artifact_version"):
        meta = rec.metadata or {}
        if meta.get("artifact") != artifact or str(meta.get("bom_id")) != bom_id:
            continue
        if str(rec.status) in ("active", "stale"):
            return str(rec.record_id)
    return None


def _add_or_reuse(store: Any, *, artifact: str, bom_id: str, signature: str,
                  detail: str, metadata: dict[str, Any],
                  tenant_id: str | None, project_id: str | None) -> dict[str, Any]:
    from aipd_os.product_truth.models import SourceRef, TruthRecord

    content = version_content(artifact=artifact, bom_id=bom_id,
                             signature=signature, detail=detail)
    existing = store.find_id_by_type_and_content(
        "artifact_version", content, tenant_id=tenant_id, project_id=project_id)
    if existing is not None:                       # 同输入 ⇒ 同一版，不另起
        return {"record_id": str(existing), "created": False}
    previous = _find_current(store, artifact=artifact, bom_id=bom_id)
    record_id = store.add(
        TruthRecord(record_type="artifact_version", content=content,
                    source=SourceRef(file=f"bom.db:{bom_id}",
                                     note=f"input_signature={signature[:16]}"),
                    trust_level="high", metadata=metadata),
        tenant_id=tenant_id, project_id=project_id)
    if previous is not None and previous != record_id:
        store.set_status(previous, "superseded", tenant_id=tenant_id,
                         project_id=project_id)
    return {"record_id": record_id, "created": True,
            "superseded_record_id": previous if previous != record_id else None}


def record_cost_lineage(store: Any, *, header: Any, lines: list[Any],
                        inputs: Any, cost: Any,
                        tenant_id: str | None = None,
                        project_id: str | None = None) -> dict[str, Any]:
    """写「BOM 版本 → 成本结论」两条记录与一条边，返回落库摘要。"""
    from aipd_os.product_truth.lineage import LineageGraph

    if header is None or not lines:
        return {"written": False, "reason": "BOM 为空或没有行，不登记血缘",
                "records": 0, "edges": 0}

    bom_sig = bom_input_signature(bom_id=header.bom_id,
                                 revision=str(header.revision),
                                 version_no=header.version_no, lines=lines)
    fact_keys = _line_facts(lines)
    bom_out = _add_or_reuse(
        store, artifact=ARTIFACT_BOM, bom_id=header.bom_id, signature=bom_sig,
        detail=f"lines={len(fact_keys)} rev={header.revision}",
        metadata={"artifact": ARTIFACT_BOM, "bom_id": header.bom_id,
                  "name": header.name, "revision": str(header.revision),
                  "bom_status": str(header.status),
                  "version_no": header.version_no,
                  "input_signature": bom_sig, "lines": fact_keys},
        tenant_id=tenant_id, project_id=project_id)
    cost_sig = cost_input_signature(bom_signature=bom_sig,
                                    tooling_fee=inputs.tooling_fee,
                                    target_quantity=inputs.target_quantity,
                                    amortize_over=inputs.amortize_over,
                                    nre=inputs.nre, margin_pct=inputs.margin_pct)
    total = (cost.to_dict() or {}).get("total_cost")
    cost_out = _add_or_reuse(
        store, artifact=ARTIFACT_COST, bom_id=header.bom_id, signature=cost_sig,
        detail=f"total={total}",
        metadata={"artifact": ARTIFACT_COST, "bom_id": header.bom_id,
                  "input_signature": cost_sig, "bom_signature": bom_sig,
                  "bom_record_id": bom_out["record_id"],
                  "total_cost": total,
                  "currency": (cost.to_dict() or {}).get("currency"),
                  "cost_complete": bool(getattr(cost, "cost_complete", False)),
                  "line_ids": [row["line_id"] for row in fact_keys],
                  # 口径五项的**值**也要落地：只有哈希的记录重建不出同一次核算，
                  # 返工执行器就只能拿默认值猜（第 47 片对缺输入的旧记录是点名拒，不是猜）。
                  "tooling_fee": inputs.tooling_fee,
                  "target_quantity": inputs.target_quantity,
                  "amortize_over": inputs.amortize_over,
                  "nre": inputs.nre, "margin_pct": inputs.margin_pct},
        tenant_id=tenant_id, project_id=project_id)

    graph = LineageGraph(store, tenant_id=tenant_id or store.tenant_id,
                         project_id=project_id or store.project_id)
    graph.add_edge(bom_out["record_id"], cost_out["record_id"], "affects")
    return {"written": True, "reason": None, "records": 2, "edges": 1,
            "bom": bom_out, "cost": cost_out,
            "bom_signature": bom_sig, "cost_signature": cost_sig}
