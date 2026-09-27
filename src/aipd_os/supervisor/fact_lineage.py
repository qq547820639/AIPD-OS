r"""把一次执行的证据接进 `truth_lineage`（F-TRUTH-LINEAGE 第 70 片）。

`Supervisor._write_back_facts` 每成功跑一次就写一条 `record_type="evidence"` 的
`product_truth` 记录，但**从不连边**——所以那条证据永远走不到 `aipd truth propagate`
的下游里（登记原话："工作项与上游 truth 之间还没有映射"）。这一片把那层映射做出来。

上游怎么找（两条都要求身份**真实存在**，宁可报"连不上"也不猜）：

1. `inputs["truth_refs"]`（显式声明，走 `scripts/aipd_supervisor.py add-work --inputs-json`）：
   逐个回查 `product_truth` 记录，查不到的进 `unknown_refs` 并原样报出——
   静默丢掉一个错号等于让"声明过上游"这件事假绿。
2. `inputs["idea_id"]`（idea 与 product 那一族调度器今天就在写这个键）：
   经公开服务 `ProductDefinitionSnapshotService.list_snapshots` + `ProductDefinitionGate.get_commit`
   找出这个 idea 已提交的 truth 记录（`committed_truth_refs_json`）。
   走服务 API 而不是直读别人的表：域内表结构变了这里要红，而不是静默读空。
3. 两样都没有 ⇒ 0 条边 + `reason` 说清缺哪一样。

边的方向与名字：`add_edge(upstream=那条 truth 记录, downstream=本次证据, relation="validated_by")`——
`validated_by` 是 `state/lineage.py` 白名单里就有的关系（"这条证据在为什么背书"反过来即
"证据由该记录背书"），而 `LineageGraph.compute_affected` 不按 relation 过滤，
所以写进去就能被传播走到。
"""
from __future__ import annotations

import json
from typing import Any

RELATION = "validated_by"
UPSTREAM_KEYS = ("truth_refs", "truth_ids")


def resolve_upstream(store: Any, *, inputs: dict[str, Any],
                     state_db: Any = None, tenant_id: str = "default",
                     project_id: str = "default") -> dict[str, Any]:
    """⇒ ``{"upstream": [...], "unknown_refs": [...], "source": str, "reason": str}``。"""
    inputs = inputs or {}
    for key in UPSTREAM_KEYS:
        raw = inputs.get(key)
        if raw:
            refs = [str(x) for x in raw] if isinstance(raw, (list, tuple)) else [str(raw)]
            found: list[str] = []
            unknown: list[str] = []
            for rid in refs:
                try:
                    store.get(rid)
                    found.append(rid)
                except KeyError:
                    unknown.append(rid)
            reason = (f"显式声明 {len(refs)} 个，其中 {len(found)} 个在本作用域查得到"
                      + (f"；查不到的原样报出：{unknown}" if unknown else "")
                      ) if found else f"声明的 {len(refs)} 个在本作用域都查不到"
            return {"upstream": found, "unknown_refs": unknown,
                    "source": f"inputs[{key}]", "reason": reason}

    idea_id = str(inputs.get("idea_id") or "")
    if not idea_id:
        return {"upstream": [], "unknown_refs": [], "source": "",
                "reason": "工作项 inputs 里既没有 truth_refs/truth_ids，也没有 idea_id"}
    if state_db is None:
        return {"upstream": [], "unknown_refs": [], "source": "inputs[idea_id]",
                "reason": "legacy supervisor 库（未接 canonical 状态库），读不到产品定义快照"}
    from aipd_os.product_intelligence import ProductDefinitionGate, ProductDefinitionSnapshotService

    snaps = ProductDefinitionSnapshotService(state_db).list_snapshots(tenant_id, project_id)
    mine = [s for s in snaps if getattr(s, "idea_id", "") == idea_id]
    gate = ProductDefinitionGate(state_db, tenant_id, project_id)
    found_ids: list[str] = []
    for snap in mine:
        receipt = gate.get_commit(snap.snapshot_id) or {}
        # `get_commit` 回的是**表行**（列名 committed_truth_refs_json），不是 receipt 形状；
        # 按 receipt 的 "committed" 读会永远读到空——第一版就栽在这里，被第 70 片的
        # idea_id 用例抓出来（它让"解析不到"和"解析成 0"长得一模一样）。
        raw = receipt.get("committed_truth_refs_json")
        refs = receipt.get("committed")
        if isinstance(raw, str) and raw.strip():
            try:
                refs = json.loads(raw)
            except ValueError:
                refs = []
        for rid in refs or []:
            if rid not in found_ids:
                found_ids.append(str(rid))
    if found_ids:
        reason = f"idea {idea_id} 已提交的 {len(found_ids)} 条 truth 记录"
    else:
        reason = (f"idea {idea_id} 有 {len(mine)} 份快照但都还没 commit"
                  "（先跑 aipd product gate --commit）")
    return {"upstream": found_ids, "unknown_refs": [],
            "source": "inputs[idea_id]", "reason": reason}


def write_fact_lineage(store: Any, *, evidence_id: str, upstream: list[str],
                       tenant_id: str, project_id: str,
                       conn: Any = None) -> dict[str, Any]:
    """给每条上游连一条 ``validated_by`` 边；环与自环**报出来但不毁掉证据步**。

    `LineageGraph.add_edge` 是 `truth_lineage` 的唯一 SQL 入口（环检测在里面），
    所以这里不写任何 SQL。返回摘要进 `fact_writeback` 的结果字典，
    让"边写没写、为什么没写"在 CLI 与用例里都看得见。
    """
    from aipd_os.product_truth.lineage import CycleDetectedError, LineageGraph

    # `edges` 数的是**真新增的边**（前后各数一次），不是"调用了几次 add_edge"：
    # 同一轮重放时 `INSERT OR IGNORE` 不会报错，按调用次数报就会把"0 新增"说成"又连上两条"。
    def _count_rows() -> int:
        with store.connect() as c:
            return int(c.execute(
                "SELECT COUNT(*) FROM truth_lineage WHERE tenant_id=? AND project_id=?"
                " AND downstream_id=?", (tenant_id, project_id, evidence_id)).fetchone()[0])

    before = _count_rows()
    summary: dict[str, Any] = {"edges": 0, "skipped": [], "relation": RELATION}
    if not upstream:
        summary["reason"] = "没有上游记录可连"
        return summary
    graph = LineageGraph(store, tenant_id=tenant_id, project_id=project_id)
    for up in upstream:
        if up == evidence_id:
            summary["skipped"].append({"upstream": up, "why": "自环：上游就是这条证据自己"})
            continue
        try:
            graph.add_edge(up, evidence_id, RELATION, conn=conn)
            summary["attempted"] = summary.get("attempted", 0) + 1
        except CycleDetectedError as exc:
            summary["skipped"].append({"upstream": up, "why": f"环检测拒绝：{exc}"})
    summary["edges"] = _count_rows() - before
    summary["total_for_this_evidence"] = _count_rows()
    return summary


__all__ = ["RELATION", "UPSTREAM_KEYS", "resolve_upstream", "write_fact_lineage"]
