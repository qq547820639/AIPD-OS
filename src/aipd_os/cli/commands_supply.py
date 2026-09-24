"""``aipd quote`` —— 把报价文件登记、落库，并应用到 BOM 上。

``quote apply`` 是这条商业主链此前缺失的那一段（F-SUPPLY-01）：报价解析早就有了，
但解析结果进了一个用完就丢的内存注册表，会写库的 ``persist_quote`` 没有产品调用点，
而 BOM 的 ``unit_cost`` 只能靠人手工填。现在一条命令走完：

    解析 → 登记（版本递增/旧版 superseded）→ 落 Product Truth（``quote.*`` 事实，status V）
    → 写进对应 BOM 行的 unit_cost/supplier/quote_ref/status → 成本核算即可闭合

版本号由 `assign_quote_versions` 对齐到库里已有的事实（F-SUPPLY-02）：注册表是进程内的，
同内容重放会复用既有那一版而不是再登记一条，所以本命令**可以重跑**；改价才产生新版本，
且旧版 ``V`` 事实随即转 ``R``（库里不允许两版同时是"作数的官方报价"）。

`ok` 只在**全部报价都对上了 BOM 行且没有币种冲突**时为 True：有一条对不上就返回 4，
不返回「看起来成功了但其实少算了一项」。分批报价（先只报一部分零件）是正常工作流，
所以 BOM 侧还缺哪些价由 ``bom_remaining_unpriced`` 显式列出、不改本次退出码——真正把
「缺价的 BOM」挡在门外的是 ``bom release``。
"""
from __future__ import annotations

from typing import Any

from aipd_os.cli._helpers import DEFAULT_TENANT, _emit


def cmd_quote(args: Any) -> int:
    """quote 命令分发（apply）。"""
    if args.quote_cmd != "apply":
        raise ValueError(f"unknown quote subcommand: {args.quote_cmd}")
    return _quote_apply(args)


def _quote_apply(args: Any) -> int:
    from aipd_os.bom import BomStore
    from aipd_os.bom.projection import rollup
    from aipd_os.state.db import AIPDStateDB
    from aipd_os.supply_chain.apply import (
        apply_quotes_to_bom,
        assign_quote_versions,
        retire_stale_officials,
    )
    from aipd_os.supply_chain.persistence import SupplyChainStore
    from aipd_os.supply_chain.quotes import QuoteRegistry, parse_quote_file

    from .commands_manufacturing import _bom_store_path, _resolve_project

    db = AIPDStateDB(args.db)
    pid = _resolve_project(db, getattr(args, "project", None))
    currency = str(getattr(args, "currency", None) or "CNY")

    parsed = parse_quote_file(args.file)
    registry = QuoteRegistry()
    for rec in parsed["records"]:
        registry.add_quote(supplier=rec["supplier"], part=rec["part"], data=rec,
                           source_file=str(parsed.get("source", "")))
    quotes = [q for versions in registry._quotes.values() for q in versions]

    # 版本号以库里的报价事实为准：注册表是进程内的、每次从 v1 起，直接登记会让
    # 同一份文件重放撞 facts 的 UNIQUE 约束（bom.db 与 state.db 无跨库原子性，
    # "重放即修复" 必须是可用的动作）。内容相同即复用既有那版，不重复登记。
    supply = SupplyChainStore(db, DEFAULT_TENANT)
    facts: list[str] = []
    reused: list[str] = []
    current: dict[tuple[str, str], int] = {}
    for assignment in assign_quote_versions(supply.load_quotes(pid), quotes):
        quote = assignment.quote
        quote.version = assignment.version
        quote.quote_id = f"{quote.supplier}-{assignment.part}-v{assignment.version}"
        key = (str(quote.supplier).strip().lower(), assignment.part.strip().lower())
        if assignment.is_new:
            facts.append(supply.persist_quote(
                pid, quote_id=quote.quote_id, supplier=quote.supplier,
                part=assignment.part, version=assignment.version,
                data=quote.data, status=quote.status))
        else:
            reused.append(assignment.fact_key)
        if quote.status == "official":
            current[key] = assignment.version
    retired = retire_stale_officials(supply, pid, current)

    store = BomStore(str(_bom_store_path(args.db)))
    report = apply_quotes_to_bom(store, DEFAULT_TENANT, pid, quotes,
                                 currency=currency)
    # 报价侧干净 ≠ BOM 侧已定价：分批报价是正常工作流，所以缺价不改变本次退出码，
    # 但必须显式列出来，否则「已按报价定价」会被读成整张 BOM 都有价了。
    remaining = rollup(store, DEFAULT_TENANT, pid)["missing_cost_items"]
    payload = {
        "command": "quote apply",
        "ok": report.clean,
        "status": "DONE" if report.clean else "HOLD",
        "project": pid,
        "source": str(parsed.get("source", "")),
        "currency": currency,
        "parsed": len(quotes),
        "persisted_facts": facts,
        "reused_facts": reused,
        "retired_facts": retired,
        "bom_remaining_unpriced": remaining,
        **report.to_dict(),
    }

    def prose():
        print(f"报价解析 {len(quotes)} 条（{payload['source']}），"
              f"新登记事实 {len(facts)} 条，复用已有事实 {len(reused)} 条，币种 {currency}")
        for u in report.updated:
            print(f"  已定价：{u['item']} → {u['unit_cost']} "
                  f"（{u['supplier']}，{u['quote_ref']}）")
        for u in report.unchanged:
            print(f"  已是该价：{u['item']}（{u['quote_ref']}）")
        for r in report.rejected:
            print(f"  未应用：{r.get('item', r.get('part'))} 原因 {r['reason']}")
        for m in report.unmatched:
            print(f"  无对应 BOM 行：{m['part']}（{m['supplier']}）")
        for k in retired:
            print(f"  旧版报价事实转 R（Retired）：{k}")
        if not report.clean:
            print("⇒ 报价未全部落到 BOM 上（不静默通过）")
        if remaining:
            print("  BOM 仍缺供应商/单价的行：" + "，".join(remaining) +
                  "（`bom release` 会因此拒绝发布）")

    _emit(args, payload, prose)
    return 0 if report.clean else 4


__all__ = ["cmd_quote"]
