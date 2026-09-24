"""验证失败 → BOM 行 → 关联制品 的影响传播（把「已声明」变成「已接线」）。

登记表的 ``industrialize.physical_writeback`` 一直写着「测试结果 → 事实主表更新 →
BOM/CAD 影响传播」且 ``current_limitation=None``（自称完整实现），但实测：那条传播的
唯一调用点 ``tool_adapters/evt_dvt_pvt_adapter.py:76`` 把 ``input["facts"]`` /
``input["bom"]``（调用方自带、实际不传）喂给 ``propagate_impact``，而该适配器 id 在
``src`` + ``scripts`` + ``tests`` 里除自身外零引用；产品侧唯一排产 capability 的
``supervisor/idea_capabilities.py`` 只排 ``idea.*`` / ``product.*`` ⇒ 这条能力在软件上
不可达（F-SUPPLY-03）。

本模块把传播挂在**已经可达且已经持久化**的路径上（``aipd industrialize --lab-data``、
``aipd validation import``），并复用仓内既有语义而不是新造一套 stale 存储：

- 匹配只认归一化后的全等（``strip`` + 小写），**不做子串猜**——「支架」不得带出「支架座」；
- 受影响行 → 其 ``source_deliverable`` 指向的制品按 CAS 置 ``stale``，与
  ``experience/instructions._mark_stale`` 同一纪律：``released`` / ``archived`` 不悄悄改写；
- 关联不到制品的行如实进 ``unresolved_lines``（不凭空造制品、也不算传播成功）；
- 结论写进事实主表 ``impact.<项>``（status ``P`` = 待返工）——「事实主表更新」这句话
  由此可核验；
- **可重放**：同一失败项重跑只刷新那一条事实，不再标第二次（与 F-SUPPLY-02 同一教训：
  崩溃后「再执行一次」必须就是修复动作）。
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from ..bom.store import BomStore

IMPACT_FACT_PREFIX = "impact"
IMPACT_FACT_STATUS = "P"              # Pending：待返工（STATUS_SEMANTICS 的正式语义）
PROTECTED_DELIVERABLE_STATUSES = frozenset({"released", "archived"})
STALE_STATUS = "stale"


def _norm(value: Any) -> str:
    return str(value if value is not None else "").strip().lower()


@dataclass
class ImpactReport:
    """一次影响传播的结果：动了谁、谁没法动、结论记在哪。

    ``stale_deliverables`` 只列**本次真正改判**的制品；本来就已是 stale 的记在
    ``already_stale_deliverables``。把两者混成一个字段，重放就会谎报"我又标了一次"
    （与 F-SUPPLY-01 的 ``updated`` / ``unchanged`` 同一分工）。
    """

    failing_items: list[str] = field(default_factory=list)
    affected_lines: list[dict[str, Any]] = field(default_factory=list)
    stale_deliverables: list[str] = field(default_factory=list)
    already_stale_deliverables: list[str] = field(default_factory=list)
    unresolved_lines: list[str] = field(default_factory=list)
    fact_keys: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        """没有受影响行，或每个受影响行都落到了制品上（含本就无需再标）。"""
        return not self.unresolved_lines

    def to_dict(self) -> dict[str, Any]:
        return {
            "failing_items": list(self.failing_items),
            "affected_lines": list(self.affected_lines),
            "stale_deliverables": list(self.stale_deliverables),
            "already_stale_deliverables": list(self.already_stale_deliverables),
            "unresolved_lines": list(self.unresolved_lines),
            "fact_keys": list(self.fact_keys),
            "clean": self.clean,
        }


def _failing_items(failing: Iterable[Any]) -> list[str]:
    """接受字符串或 ``{"test_item": ...}`` 两种形态（阶段分析的产出就是后者）。"""
    out: list[str] = []
    seen: set[str] = set()
    for entry in failing or []:
        if isinstance(entry, dict):
            name = entry.get("test_item") or entry.get("item") or entry.get("name")
        else:
            name = entry
        text = str(name or "").strip()
        if text and _norm(text) not in seen:
            seen.add(_norm(text))
            out.append(text)
    return out


def _lines_by_item(store: BomStore, tenant_id: str, project_id: str,
                   wanted: Sequence[str]) -> dict[str, list[Any]]:
    targets = {_norm(w) for w in wanted}
    grouped: dict[str, list[Any]] = {}
    for line in store.list_lines(tenant_id, project_id):
        key = _norm(line.item)
        if key in targets:
            grouped.setdefault(key, []).append(line)
    return grouped


def _record_fact(db: Any, tenant_id: str, project_id: str, item: str,
                 value: dict[str, Any]) -> str:
    """写结论事实：有则刷新（CAS），无则新建。重放不产生第二条。"""
    key = f"{IMPACT_FACT_PREFIX}.{item.strip()}"
    existing = next((f for f in db.list_facts(tenant_id, project_id)
                     if str(f.get("key")) == key), None)
    if existing is None:
        db.add_fact(tenant_id, project_id, key, value, IMPACT_FACT_STATUS,
                    source="lab-impact", version="1",
                    conditions=f"failing_item={item}")
    else:
        db.update_fact(tenant_id, project_id, existing["fact_id"],
                       expected_version=int(existing["version_no"]), value=value)
    return key


def propagate_lab_impact(db: Any, store: BomStore, tenant_id: str, project_id: str,
                         failing: Iterable[Any], *, source: str = "") -> ImpactReport:
    """把验证失败项传播到 BOM 行与其关联制品，并把结论写进事实主表。"""
    items = _failing_items(failing)
    report = ImpactReport(failing_items=items)
    if not items:
        return report

    grouped = _lines_by_item(store, tenant_id, project_id, items)
    deliverables = {str(d["deliverable_id"]): d
                    for d in db.list_deliverables(tenant_id, project_id)}

    for item in items:
        lines = grouped.get(_norm(item), [])
        if not lines:
            continue
        stale_here: list[str] = []
        already_here: list[str] = []
        unresolved_here: list[str] = []
        affected_here: list[dict[str, Any]] = []
        for line in lines:
            ref = str(line.source_deliverable or "").strip()
            entry = {"item": line.item.strip(), "line_id": line.line_id,
                     "bom_id": line.bom_id, "line_status": line.status,
                     "deliverable": ref or None}
            if not ref:
                unresolved_here.append(line.line_id)
            elif ref not in deliverables:
                unresolved_here.append(line.line_id)
                entry["deliverable_missing"] = True
            elif deliverables[ref]["status"] == STALE_STATUS:
                already_here.append(ref)            # 本就过期：不重复标记、也不谎报改判
            elif deliverables[ref]["status"] in PROTECTED_DELIVERABLE_STATUSES:
                entry["skipped_protected"] = deliverables[ref]["status"]
            else:
                db.update_deliverable(tenant_id, project_id, ref,
                                      expected_version=int(
                                          deliverables[ref]["version_no"]),
                                      status=STALE_STATUS)
                deliverables[ref]["status"] = STALE_STATUS
                stale_here.append(ref)
            affected_here.append(entry)

        report.affected_lines.extend(affected_here)
        report.unresolved_lines.extend(unresolved_here)
        for did in stale_here + already_here:
            bucket = (report.stale_deliverables if did in stale_here
                      else report.already_stale_deliverables)
            if did not in bucket:
                bucket.append(did)
        report.fact_keys.append(_record_fact(db, tenant_id, project_id, item, {
            "failing_item": item,
            "source": source,
            "affected_line_ids": [a["line_id"] for a in affected_here],
            "stale_deliverables": sorted(set(stale_here)),
            "already_stale_deliverables": sorted(set(already_here)),
            "unresolved_line_ids": unresolved_here,
        }))
    return report


__all__ = ["IMPACT_FACT_PREFIX", "ImpactReport", "propagate_lab_impact"]
