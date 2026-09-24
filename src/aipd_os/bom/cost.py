"""BOM 成本核算（确定性纯计算，v5.10 NPI：Cost）。

- 行成本 = 数量 × 单位成本（unit_cost 缺失的行计入 missing，绝不按 0 元假装）；
- 模具费 / NRE 按摊销数量摊入单件；
- 毛利按比例加价，输出单件与总价；
- ``cost_complete`` 显式判定：全部行都有 supplier 与 unit_cost 才为 True。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import BomLine

#: 作废行不参与成本：它留在 BOM 里可追溯，但钱不按它算。
OBSOLETE_STATUS = "obsolete"


class CostCurrencyError(ValueError):
    """一个 BOM 里出现多种币种 ⇒ 求和得到的「总价」没有含义，拒绝出数。"""


@dataclass
class CostInputs:
    """成本核算输入（全部确定性）。"""

    tooling_fee: float = 0.0
    target_quantity: int = 1000
    amortize_over: int | None = None  # None → 用 target_quantity
    nre: float = 0.0
    margin_pct: float = 0.0

    def __post_init__(self) -> None:
        if self.tooling_fee < 0 or self.nre < 0:
            raise ValueError("tooling_fee / nre must be >= 0")
        if self.target_quantity <= 0:
            raise ValueError("target_quantity must be > 0")
        if self.amortize_over is not None and self.amortize_over <= 0:
            raise ValueError("amortize_over must be > 0")
        if self.margin_pct < 0:
            raise ValueError("margin_pct must be >= 0")

    def amortize_quantity(self) -> int:
        return self.amortize_over or self.target_quantity


@dataclass
class CostResult:
    """成本核算结果（可 JSON 序列化）。"""

    material_subtotal: float
    tooling_fee: float
    tooling_per_unit: float
    nre: float
    nre_per_unit: float
    unit_cost: float
    unit_price: float
    total_cost: float
    total_price: float
    line_count: int
    missing_cost_lines: list[str] = field(default_factory=list)
    cost_complete: bool = False
    currency: str | None = None
    obsolete_excluded: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "material_subtotal": round(self.material_subtotal, 4),
            "currency": self.currency,
            "obsolete_excluded": list(self.obsolete_excluded),
            "tooling_fee": round(self.tooling_fee, 4),
            "tooling_per_unit": round(self.tooling_per_unit, 6),
            "nre": round(self.nre, 4),
            "nre_per_unit": round(self.nre_per_unit, 6),
            "unit_cost": round(self.unit_cost, 4),
            "unit_price": round(self.unit_price, 4),
            "total_cost": round(self.total_cost, 4),
            "total_price": round(self.total_price, 4),
            "line_count": self.line_count,
            "missing_cost_lines": list(self.missing_cost_lines),
            "cost_complete": self.cost_complete,
        }


def compute_bom_cost(lines: list[BomLine], inputs: CostInputs) -> CostResult:
    """确定性 BOM 成本核算（纯函数，无 IO）。

    诚实原则：supplier 或 unit_cost 缺失的行计入 missing_cost_lines 且
    cost_complete=False——不把缺数据当 0 元。
    """
    material_subtotal = 0.0
    missing: list[str] = []
    obsolete: list[str] = []
    priced: dict[str, None] = {}
    for line in lines:
        if line.status == OBSOLETE_STATUS:
            obsolete.append(line.item)
            continue
        if line.unit_cost is None or not line.supplier:
            missing.append(f"{line.item}(line {line.line_id})")
            continue
        priced[line.currency] = None
        material_subtotal += line.quantity * line.unit_cost

    if len(priced) > 1:
        raise CostCurrencyError(
            f"BOM 含多种币种 {sorted(priced)}，不能相加为一个 unit_cost；"
            "请拆 BOM 或先统一币种后再核算")

    amortize = inputs.amortize_quantity()
    tooling_per_unit = inputs.tooling_fee / amortize
    nre_per_unit = inputs.nre / amortize
    unit_cost = material_subtotal + tooling_per_unit + nre_per_unit
    unit_price = unit_cost * (1.0 + inputs.margin_pct / 100.0)
    return CostResult(
        material_subtotal=material_subtotal,
        currency=next(iter(priced)) if priced else None,
        obsolete_excluded=obsolete,
        tooling_fee=inputs.tooling_fee,
        tooling_per_unit=tooling_per_unit,
        nre=inputs.nre,
        nre_per_unit=nre_per_unit,
        unit_cost=unit_cost,
        unit_price=unit_price,
        total_cost=unit_cost * inputs.target_quantity,
        total_price=unit_price * inputs.target_quantity,
        line_count=len(lines),
        missing_cost_lines=missing,
        cost_complete=not missing,
    )


__all__ = ["CostInputs", "CostResult", "compute_bom_cost"]
