"""「这个 actor 是不是人」的唯一一份词表（F-C6 第 32 片）。

放在叶子模块而不是某个域里，是因为有两处读者：ECO 变更单用它拒机器身份批
自己的单，`gates` 台账用它把已写进去的 `approved_by` 分成「人批 / 机器批 /
没人批」。词表只有一份，否则两边各抄一遍迟早漂。

三态而不是两态：`NULL`（从来没填过审批人）既不是「机器批了」也不是「人批了」，
把它折算成任何一态都是假读数。
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

UNATTRIBUTED = "unattributed"
NON_HUMAN = "non_human"
HUMAN = "human"

#: 机器身份。**空串也算**：漏填 actor 不许被读成「有人批了」。
#: `supply-chain` 是本仓供应链回写给自己盖的戳（`supply_chain/writeback.py`），
#: 它是一个子系统名，不是一个人。
NON_HUMAN_ACTORS = frozenset({
    "", "ai", "ai-internal", "agent", "assistant", "auto", "automation",
    "bot", "cli", "default", "n/a", "none", "null", "supply-chain",
    "system", "unknown",
})


def classify_actor(value: Any) -> str:
    """把一个 actor 值分成 UNATTRIBUTED / NON_HUMAN / HUMAN。

    `None` 与缺失（读不到该列）⇒ UNATTRIBUTED；纯空白 ⇒ NON_HUMAN（填了但等于没填）。
    """
    if value is None:
        return UNATTRIBUTED
    text = str(value).strip()
    if not text:
        return NON_HUMAN
    return NON_HUMAN if text.casefold() in NON_HUMAN_ACTORS else HUMAN


def is_human_actor(value: Any) -> bool:
    """只有「写了名字、而且那个名字不在机器身份表里」才算人。"""
    return classify_actor(value) == HUMAN


def summarize_actor_column(rows: Iterable[dict[str, Any]], *, column: str,
                           id_field: str) -> dict[str, Any]:
    """按某一 actor 列给一批行做三态计数（gates 的 `approved_by`、risks 的
    `owner`……共用同一份词表，但各自的投影留在各自模块里，这里只做通用计数）。

    `unassigned` 收的是「没有被读成真人」的那些行的 id —— 缺责任人与机器代签
    在「下一步要谁动」这个问题上是同一类，所以合在一列里给调用方看。
    """
    counts = {HUMAN: 0, NON_HUMAN: 0, UNATTRIBUTED: 0}
    unassigned: list[Any] = []
    total = 0
    for row in rows:
        total += 1
        kind = classify_actor(row.get(column)) if column in row else UNATTRIBUTED
        counts[kind] += 1
        if kind != HUMAN:
            unassigned.append(row.get(id_field))
    return {"column": column, "total": total, "counts": counts,
            "unassigned": [x for x in unassigned if x is not None]}
