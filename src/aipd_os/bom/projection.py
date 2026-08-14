"""BOM 投影与发布检查清单（面向所有者与发布门禁）。

- :func:`rollup`：行数/供应商分布/成本完整性/孤儿父项；
- :func:`release_checklist`：开模可用物料清单与成本核算的确定性验收
  （发布前缺一项即不 ready，绝不空真通过）。
"""
from __future__ import annotations

from typing import Any

from .cost import CostInputs, CostResult, compute_bom_cost
from .store import BomStore


def rollup(store: BomStore, tenant_id: str, project_id: str,
           bom_id: str | None = None) -> dict[str, Any]:
    """BOM 汇总视图（行数、供应商分布、层级根、成本完整性）。"""
    lines = store.list_lines(tenant_id, project_id, bom_id=bom_id)
    items = {line.item for line in lines}
    suppliers: dict[str, int] = {}
    missing_cost = []
    orphans = []
    roots = []
    for line in lines:
        if line.supplier:
            suppliers[line.supplier] = suppliers.get(line.supplier, 0) + 1
        if line.unit_cost is None or not line.supplier:
            missing_cost.append(line.item)
        if line.parent_item and line.parent_item not in items:
            orphans.append(f"{line.item} -> parent {line.parent_item}")
        if not line.parent_item:
            roots.append(line.item)
    return {
        "bom_id": bom_id,
        "line_count": len(lines),
        "root_items": sorted(roots),
        "suppliers": suppliers,
        "missing_cost_items": sorted(set(missing_cost)),
        "orphan_parents": sorted(set(orphans)),
        "cost_complete": not missing_cost,
    }


def release_checklist(store: BomStore, tenant_id: str, project_id: str,
                      bom_id: str | None = None,
                      cost_inputs: CostInputs | None = None) -> dict[str, Any]:
    """开模可用物料清单与成本核算的发布检查清单（确定性）。

    检查项：
    - bom_released：BOM 头状态为 released；
    - lines_present：至少一行；
    - cost_complete：每行都有供应商与单位成本；
    - no_orphan_parents：父项引用都存在于本 BOM；
    - cost_calculated：成本核算已产出且不含缺失行。

    ``release_ready`` 仅在全部通过时为 True。
    """
    header = store.get_bom(tenant_id, project_id, bom_id)
    lines = store.list_lines(tenant_id, project_id, bom_id=bom_id)
    r = rollup(store, tenant_id, project_id, bom_id=bom_id)
    cost: CostResult | None = None
    if cost_inputs is not None:
        cost = compute_bom_cost(lines, cost_inputs)
    checks = {
        "bom_exists": header is not None,
        "bom_released": bool(header and header.status == "released"),
        "lines_present": bool(lines),
        "cost_complete": bool(lines) and r["cost_complete"],
        "no_orphan_parents": not r["orphan_parents"],
        "cost_calculated": bool(cost is not None and cost.cost_complete),
    }
    return {
        "bom_id": bom_id or (header.bom_id if header else None),
        "checks": checks,
        "rollup": r,
        "cost": cost.to_dict() if cost else None,
        "release_ready": all(checks.values()),
    }


__all__ = ["rollup", "release_checklist"]
