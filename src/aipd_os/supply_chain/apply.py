"""把已登记的官方报价落到 BOM 行上，从而让成本核算拿到真实单价。

链路上原本断在这里：报价文件解析是真的，但解析结果进了一个用完就丢的内存注册表；
`SupplyChainStore.persist_quote` 会写库却没有任何产品调用点；而全仓唯一写
`bom_lines.unit_cost` 的地方是 CLI 的 `--unit-cost` 手填参数。也就是说
「询价 → 报价 → 成本」这条商业主链从来没有闭合过（F-SUPPLY-01）。

口径（都写成用例钉住）：
- 只有 ``official`` 报价能改钱；``draft`` / ``superseded`` 一律拒绝并如实报告；
- 报价的 ``part`` 必须对上 BOM 行的 ``item``（去空格、大小写不敏感），
  对不上就是 ``unmatched`` —— **不静默跳过**，否则「报价已入账」会是假的；
- 报价文件表头没有币种列（实测 ``CANONICAL_CSV_HEADER``），所以币种必须由调用方
  显式声明并逐行核对：不一致 ⇒ 拒绝该行，而不是按某个默认汇率折算；
- 作废行（``obsolete``）不接受报价，与成本核算同一口径；
- 同一份报价重复应用不会把 ``version_no`` 一路推高（先看价格和引用是否已一致）；
- 版本号**以 Product Truth 为准**而不是以进程内注册表为准（``assign_quote_versions``）：
  报价事实按项目持久、注册表每次从 v1 起，两者不对齐时同文件重放就会撞
  ``facts`` 的 UNIQUE 约束。两个库（bom.db / state.db）之间没有跨库事务，
  「重放即修复」是这条链唯一的收口手段（F-SUPPLY-02）。
"""
from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from ..bom.models import BomLine
from ..bom.store import BomStore

QUOTE_FACT_PREFIX = "quote"
QUOTE_STATUS_VERIFIED = "V"
QUOTE_STATUS_RETIRED = "R"


def quote_fact_key(supplier: str, part: str, version: int) -> str:
    """与 ``SupplyChainStore.persist_quote`` 写入的 fact key 保持同一形状。"""
    return f"{QUOTE_FACT_PREFIX}.{supplier}.{part}.v{version}"


def _part_key(supplier: Any, part: Any) -> tuple[str, str]:
    return (str(supplier or "").strip().lower(), str(part or "").strip().lower())


def _signature(data: Any) -> str:
    """报价内容的规范签名：同一份内容重放必须落在同一个版本号上。"""
    return json.dumps(data, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), default=str)


@dataclass
class QuoteAssignment:
    """一条报价在「库里已有的事实」这套编号体系里应该占的那一版。"""

    quote: Any
    part: str
    version: int
    fact_key: str
    is_new: bool


def assign_quote_versions(existing_facts: Sequence[dict[str, Any]],
                          quotes: Sequence[Any]) -> list[QuoteAssignment]:
    """把进程内注册表的版本号对齐到已落库的报价事实（内容相同即复用，不重复登记）。

    ``existing_facts`` 是 ``SupplyChainStore.load_quotes()`` 的返回（value 已解码）。
    规则：① 内容签名命中库里某条事实 ⇒ 复用那一版（``is_new=False``）；② 否则取
    「库里同 (供应商, 零件) 的最大版本」与「本轮已分配版本」的较大者 +1。
    因此同一文件重放 N 次结果相同，改价则版本号只增不减、不撞号。
    """
    stored: dict[tuple[str, str], dict[str, int]] = {}
    highest: dict[tuple[str, str], int] = {}
    for fact in existing_facts:
        value = fact.get("value") or {}
        if not isinstance(value, dict):
            continue
        supplier, part = value.get("supplier"), value.get("part")
        try:
            version = int(value.get("version") or 0)
        except (TypeError, ValueError):
            continue
        key = _part_key(supplier, part)
        stored.setdefault(key, {}).setdefault(_signature(value.get("data")), version)
        highest[key] = max(highest.get(key, 0), version)

    assigned: dict[tuple[str, str], int] = {}
    result: list[QuoteAssignment] = []
    for quote in quotes:
        part = str(quote.data.get("part") or quote.part).strip()
        key = _part_key(quote.supplier, part)
        sig = _signature(quote.data)
        reused = stored.get(key, {}).get(sig)
        if reused is not None:
            result.append(QuoteAssignment(quote, part, reused,
                                          quote_fact_key(quote.supplier, part, reused),
                                          False))
            continue
        version = max(highest.get(key, 0), assigned.get(key, 0)) + 1
        assigned[key] = version
        stored.setdefault(key, {})[sig] = version
        result.append(QuoteAssignment(quote, part, version,
                                      quote_fact_key(quote.supplier, part, version),
                                      True))
    return result


def retire_stale_officials(supply: Any, project_id: str,
                           current: dict[tuple[str, str], int]) -> list[str]:
    """把同 (供应商, 零件) 上不再是当前官方版的 ``V`` 事实改为 ``R``（Retired）。

    库里同时存在两版 ``V`` 等于宣布「有两份都作数的官方报价」，而 BOM 只指得回一版。
    ``current`` 里没出现的 (供应商, 零件) 一律不动（本次没碰过的报价不擅自改判）。
    返回被改判的 fact key 列表。
    """
    retired: list[str] = []
    for fact in supply.load_quotes(project_id):
        value = fact.get("value") or {}
        if not isinstance(value, dict) or fact.get("status") != QUOTE_STATUS_VERIFIED:
            continue
        key = _part_key(value.get("supplier"), value.get("part"))
        if key not in current:
            continue
        try:
            version = int(value.get("version") or 0)
        except (TypeError, ValueError):
            continue
        if version == current[key]:
            continue
        supply.db.update_fact(supply.tenant_id, project_id, fact["fact_id"],
                              expected_version=int(fact["version_no"]),
                              status=QUOTE_STATUS_RETIRED)
        retired.append(str(fact["key"]))
    return retired


@dataclass
class ApplyReport:
    """一次「报价 → BOM」的结果：动了哪些、为什么没动其余的。"""

    updated: list[dict[str, Any]] = field(default_factory=list)
    unchanged: list[dict[str, Any]] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    unmatched: list[dict[str, Any]] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.unmatched and not self.rejected

    def to_dict(self) -> dict[str, Any]:
        return {
            "updated": list(self.updated),
            "unchanged": list(self.unchanged),
            "rejected": list(self.rejected),
            "unmatched": list(self.unmatched),
            "clean": self.clean,
        }


def _live_lines_by_item(store: BomStore, tenant_id: str,
                        project_id: str) -> dict[str, list[BomLine]]:
    grouped: dict[str, list[BomLine]] = {}
    for line in store.list_lines(tenant_id, project_id):
        grouped.setdefault(line.item.strip().lower(), []).append(line)
    return grouped


def apply_quotes_to_bom(store: BomStore, tenant_id: str, project_id: str,
                        quotes: Sequence[Any], *, currency: str = "CNY",
                        bom_id: str | None = None) -> ApplyReport:
    """把官方报价的单价写进对应的 BOM 行，返回可对账的结果。"""
    report = ApplyReport()
    grouped = _live_lines_by_item(store, tenant_id, project_id)
    for quote in quotes:
        part = str(quote.data.get("part") or quote.part).strip()
        lines = grouped.get(part.lower(), [])
        if bom_id is not None:
            lines = [ln for ln in lines if ln.bom_id == bom_id]
        if not lines:
            report.unmatched.append({"part": part, "supplier": quote.supplier,
                                     "quote_id": quote.quote_id,
                                     "quote_status": quote.status,
                                     "reason": "no-bom-line"})
            continue
        if quote.status != "official":
            # 对得上行但状态不对：这才是真会被误用的那一类，必须逐行点名。
            for line in lines:
                report.rejected.append({
                    "item": line.item, "line_id": line.line_id,
                    "reason": "not-official", "quote_status": quote.status,
                    "quote_id": quote.quote_id,
                    "would_have_set": quote.data.get("unit_price")})
            continue
        for line in lines:
            ref = quote_fact_key(quote.supplier, part, quote.version)
            unit_price = float(quote.data["unit_price"])
            if line.status == "obsolete":
                report.rejected.append({"item": line.item, "line_id": line.line_id,
                                        "reason": "obsolete-line", "quote_id": quote.quote_id})
                continue
            if line.currency != currency:
                report.rejected.append({"item": line.item, "line_id": line.line_id,
                                        "reason": "currency-conflict",
                                        "line_currency": line.currency,
                                        "quote_currency": currency,
                                        "quote_id": quote.quote_id})
                continue
            if line.unit_cost == unit_price and line.quote_ref == ref:
                report.unchanged.append({"item": line.item, "line_id": line.line_id,
                                         "quote_ref": ref})
                continue
            updated = store.update_line(
                tenant_id, project_id, line.line_id,
                expected_version=line.version_no,
                unit_cost=unit_price, supplier=quote.supplier,
                quote_ref=ref, status="quoted",
                reason=f"apply quote {quote.quote_id}")
            report.updated.append({"item": updated.item,
                                   "line_id": updated.line_id,
                                   "unit_cost": updated.unit_cost,
                                   "supplier": updated.supplier,
                                   "quote_ref": ref})
    return report


__all__ = ["ApplyReport", "QuoteAssignment", "apply_quotes_to_bom",
           "assign_quote_versions", "quote_fact_key", "retire_stale_officials"]
