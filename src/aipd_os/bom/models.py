"""BOM 域数据模型（v5.10 NPI：物料清单）。

- :class:`BomHeader`：BOM 头（名称/修订/状态，tenant+project 作用域）；
- :class:`BomLine`：BOM 行（层级 parent_item、数量/单位、材料、工艺、供应商、
  单位成本、关联图纸与报价引用；乐观锁 version_no）。

正式状态语义：
- BOM 状态：draft → released → superseded / archived；
- 行状态：planned → quoted → released → obsolete。

诚实原则：unit_cost/supplier/material/process 缺省 None（不伪造）；成本完整性由
``bom.projection.release_checklist`` 显式判定，绝不把缺数据算成 0 元。
材料与工艺**是否落到图纸**不在这里判，由 ``release manifest`` 逐图点名（见
``cad/assembly.bind_bom``）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

BOM_STATUSES = {"draft", "released", "superseded", "archived"}
LINE_STATUSES = {"planned", "quoted", "released", "obsolete"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class BomHeader:
    bom_id: str
    tenant_id: str = "default"
    project_id: str = "default"
    name: str = ""
    revision: str = "0.1"
    status: str = "draft"
    version_no: int = 1
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def __post_init__(self) -> None:
        if self.status not in BOM_STATUSES:
            raise ValueError(
                f"invalid bom status {self.status!r}; expected one of {sorted(BOM_STATUSES)}")
        if not self.bom_id:
            raise ValueError("bom_id is required")
        if not self.name:
            raise ValueError("bom name is required")

    def to_dict(self) -> dict[str, Any]:
        return {
            "bom_id": self.bom_id, "tenant_id": self.tenant_id,
            "project_id": self.project_id, "name": self.name,
            "revision": self.revision, "status": self.status,
            "version_no": self.version_no,
            "created_at": self.created_at, "updated_at": self.updated_at,
        }


def norm_item(value: Any) -> str:
    """BOM 行 ``item`` 的**标识归一**：去首尾空格 + 转小写后的全等。

    这不是模糊匹配：``BRACKET`` 归一后仍不等于 ``BRACKET-01``，包含关系不算命中
    （``supply_chain/impact`` 从一开始就是这条规矩，这里只是把它收成一处定义，
    免得图纸侧与影响传播侧各写一份然后各自漂）。
    """
    return str(value if value is not None else "").strip().lower()


@dataclass
class BomLine:
    """一行 BOM。``process`` 是**图纸明细表那一格要的那道主工艺/表面工艺**，不是工序路线：

    成熟实现把多工序建成独立对象（Dynamics 365 Business Central 的 BOM 行只带
    Routing Link Code、工序在 Routing 里；ERPNext v15 用 BOM 的子表 BOM Operation 存
    工位/工时/成本）。本仓不建那个对象，所以这里不承载顺序、工时或工序成本——
    要那些请先建路线表，别把多步塞进这一个字符串。
    """

    line_id: str
    bom_id: str
    tenant_id: str = "default"
    project_id: str = "default"
    item: str = ""
    parent_item: str | None = None
    description: str = ""
    quantity: float = 1.0
    unit: str = "pcs"
    material: str | None = None
    process: str | None = None
    supplier: str | None = None
    unit_cost: float | None = None
    currency: str = "CNY"
    source_deliverable: str | None = None
    quote_ref: str | None = None
    status: str = "planned"
    version_no: int = 1
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def __post_init__(self) -> None:
        if not self.item:
            raise ValueError("bom line item is required")
        if self.status not in LINE_STATUSES:
            raise ValueError(
                f"invalid line status {self.status!r}; expected one of {sorted(LINE_STATUSES)}")
        if self.quantity <= 0:
            raise ValueError(f"quantity must be > 0, got {self.quantity!r}")
        if self.unit_cost is not None and self.unit_cost < 0:
            raise ValueError(f"unit_cost must be >= 0, got {self.unit_cost!r}")
        if self.parent_item == self.item:
            raise ValueError(f"line cannot be its own parent: {self.item!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "line_id": self.line_id, "bom_id": self.bom_id,
            "tenant_id": self.tenant_id, "project_id": self.project_id,
            "item": self.item, "parent_item": self.parent_item,
            "description": self.description, "quantity": self.quantity,
            "unit": self.unit, "material": self.material,
            "process": self.process,
            "supplier": self.supplier, "unit_cost": self.unit_cost,
            "currency": self.currency,
            "source_deliverable": self.source_deliverable,
            "quote_ref": self.quote_ref, "status": self.status,
            "version_no": self.version_no,
            "created_at": self.created_at, "updated_at": self.updated_at,
        }


__all__ = ["BOM_STATUSES", "LINE_STATUSES", "BomHeader", "BomLine", "now_iso"]
