"""漂移清单 → 该对哪个上游落刀（F-SWEEP 第 54 片，纯计划、可测）。

第 51 片让库自己**发现**「上游已变、下游还 active」，第 52 片把五类制品的键都接到
「按当前世界重算」上，第 53 片让 `truth rework` 收得了四类制品的返工任务。
中间还差一格，而且是最容易出事的一格：**发现之后仍要人把 record id 抄进
`truth propagate --upstream`**。

形状取自本轮开过的两页官方文档（出处写进取证文档）：
- OpenTofu《cli/commands/plan》："The `plan` command alone does not actually carry out
  the proposed changes"，检测与执行分面；它另给一条 `-out=FILE` 的中间工件。
- dbt《node-selection/methods》：`state:modified` 这套选择器同时喂 `dbt ls`（列）与
  `dbt run`（执行）——同一份"哪些变了"的判断，两种消费方式。

本仓**借语义、不落工件**：`truth drift` 已经是那步"只读的检测"，所以 sweep 不需要
plan 文件；相反，plan 文件会引入"工件比现实更旧"这个新洞（OpenTofu 自己要用
"apply 时重新生成计划并要求确认"来兜底，我们没那个预算）。改成**同一次进程内**
现算现用：拿刚算出的键差决定调用谁，落刀时把两个键一起打出来当审计。

三条判据（都有主人，见 `tests/test_truth_sweep_cli.py`）：
1. **只认边表交得出的上游**。漂移记录的"上游"可能是磁盘上的一个文件
   （图纸声明那种），库里没有对应记录 ⇒ 不知道标谁，就**点名不办**，
   绝不"就近挑一条 active 记录"当上游——那等于把不相干的东西标成过期。
2. **一次调用覆盖一片下游**：`compute_affected` 是从上游往下算闭包的，
   两条漂移记录共享同一上游时只调一次；调多次会让同一批任务被反复 upsert，
   读数里"本次新置 stale"会变成空列表（第 31 片明说过那一栏空不等于没影响）。
3. **不新增传播逻辑**：落刀一律走 `PropagationEngine.on_upstream_changed`，
   与 `aipd truth propagate` 同一个入口 ⇒ 两条命令不可能对同一件事给出不同的世界。
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

__all__ = ["plan_sweep", "sweep_reason"]


def sweep_reason(artifact: Any, stored: Any, current: Any) -> str:
    """写进每条返工任务的变更说明：带着两个键，事后能问出"当时按什么落的刀"。"""
    return (f"truth sweep 发现 {artifact or '未标注制品'} 的输入键已变："
            f"{str(stored)[:12]} → {str(current)[:12]}")


def plan_sweep(drifted: Iterable[dict[str, Any]],
               upstreams: Callable[[str], Iterable[str]]
               ) -> dict[str, Any]:
    """把「漂移且还 active」的记录切成 targets / orphaned 两栏。

    `drifted` 是 `scan_drift` 的 `buckets["drifted"]`（每条含 record_id / artifact /
    status / stored_signature / current_signature）；`upstream(record_id)` 由调用面
    提供（本仓是 `LineageGraph.upstream_of`）——本模块不认识数据库，好测。

    只有 `status == "active"` 的才进计划：已经 stale 的那批早就该在任务队列里，
    再落一刀只会把 attempts 白烧掉（第 45 片那条有界返工的纪律）。
    """
    targets: dict[str, dict[str, Any]] = {}
    orphaned: list[dict[str, Any]] = []
    considered = 0
    for rec in drifted:
        if str(rec.get("status")) != "active":
            continue
        rid = str(rec.get("record_id") or "")
        if not rid:
            continue
        considered += 1
        # 先看原值再转字符串：`str(None)` 是 "None"，既非空也不等于自己，
        # 会被当成一个真上游 ⇒ 凭空多一次落刀。
        ups = sorted({str(u) for u in upstreams(rid) if u and str(u) != rid})
        if not ups:
            orphaned.append({
                "record_id": rid, "artifact": rec.get("artifact"),
                "stored_signature": rec.get("stored_signature"),
                "current_signature": rec.get("current_signature"),
                "reason": "边表里读不到这条记录的上游（它的上游是磁盘文件而不是库里的"
                          "记录，或这条边还没人写）——标谁是人的判断，不猜"})
            continue
        for up in ups:
            row = targets.setdefault(up, {"upstream_id": up, "reason": sweep_reason(
                rec.get("artifact"), rec.get("stored_signature"),
                rec.get("current_signature")), "triggered_by": []})
            row["triggered_by"].append({
                "record_id": rid, "artifact": rec.get("artifact"),
                "stored_signature": rec.get("stored_signature"),
                "current_signature": rec.get("current_signature")})
    ordered = sorted(targets.values(), key=lambda t: t["upstream_id"])
    for row in ordered:
        row["triggered_by"] = sorted(row["triggered_by"],
                                     key=lambda r: str(r["record_id"]))
    return {"targets": ordered, "orphaned": orphaned,
            "drifted_active": considered,
            "clean": considered == 0 and not orphaned}
