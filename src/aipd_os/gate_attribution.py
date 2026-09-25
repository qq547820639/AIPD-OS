"""`gates` 台账的读侧分类（F-C6 第 32 片）。

`gates.approved_by` 记的是「这一笔门禁判定是谁盖的戳」。migration v20 之前它是
`NOT NULL DEFAULT 'AI-internal'`，于是「没人批」和「AI 批了」在盘上是同一个值——
写坏的那半边已经由 v20 修掉（不写就落 NULL），但**历史行还在**：读侧必须能把
`'AI-internal'`、`'system'`、`''` 这些戳和人写的名字分开，否则这张表仍然只能
读出「每一条都有人批过」。

三态由 `aipd_os.actors` 的唯一词表决定：
- `unattributed` —— 列是 NULL，从来没填过审批人；
- `non_human` —— 填了，但填的是机器身份（含空白串与本仓供应链回写的戳）；
- `human` —— 填了一个不在机器身份表里的名字。

**这一格只能分到「写了个像人的名字」为止**：本仓没有身份源，`zhang` 是真人的
署名还是随手填的字符串，机器分不出来。所以这里给的是**归类**，不是**批准**——
`production_release_gate` 与 `quality_gate` 都只把它当读数报出来，不据此放行。
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from aipd_os.actors import HUMAN, NON_HUMAN, UNATTRIBUTED, classify_actor

APPROVED_BY_COLUMN = "approved_by"

#: 固定顺序，读数里三态都要出现（缺态写成 0 而不是不写，免得下游把「没有这个键」
#: 和「这一态是 0」混为一谈）。
CLASSIFICATIONS = (HUMAN, NON_HUMAN, UNATTRIBUTED)


def attribute_row(row: dict[str, Any]) -> str:
    """单行归类。读不到 `approved_by` 这个键与读到 `None` 同义 ⇒ unattributed。"""
    if APPROVED_BY_COLUMN not in row:
        return UNATTRIBUTED
    return classify_actor(row[APPROVED_BY_COLUMN])


def attribute_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """原样透传，每行多加一个 `approval_attribution`。"""
    out = []
    for row in rows:
        out.append({**row, "approval_attribution": attribute_row(row)})
    return out


def summarize(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """整张台账的归类计数 + 逐笔明细（明细只留判定要用的字段）。"""
    attributed = attribute_rows(rows)
    counts = {kind: 0 for kind in CLASSIFICATIONS}
    for row in attributed:
        counts[row["approval_attribution"]] += 1
    return {
        "total": len(attributed),
        "counts": counts,
        "rows": [{"gate_record_id": r.get("gate_record_id"),
                  "gate": r.get("gate"), "result": r.get("result"),
                  "approved_by": r.get(APPROVED_BY_COLUMN),
                  "attribution": r["approval_attribution"]} for r in attributed],
    }


def project_gates(db: Any, tenant_id: str, project_id: str) -> dict[str, Any]:
    """从权威库读一个项目的门禁台账并归类。

    表读不到时返回 `status=unreadable` 而不是「0 条、没人批」：读不到和没有是
    两回事，前者不能折算成后者的任何一态。
    """
    try:
        rows = db.list_gates(tenant_id, project_id)
    except Exception as exc:  # noqa: BLE001 - 表缺失/库不可读都归 unreadable
        return {"status": "unreadable", "why": f"{type(exc).__name__}: {exc}",
                "total": 0, "counts": {k: 0 for k in CLASSIFICATIONS}, "rows": []}
    out = summarize(rows)
    out["status"] = "ok"
    out["why"] = ""
    return out


__all__ = ["APPROVED_BY_COLUMN", "CLASSIFICATIONS", "attribute_row",
           "attribute_rows", "project_gates", "summarize"]
