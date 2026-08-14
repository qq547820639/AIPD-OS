"""BOM 域（v5.10 NPI：物料清单 + 成本核算）。

- :class:`BomStore`：BOM 头/行存储（tenant+project 作用域、乐观锁、原子 ID、
  审计、父链防循环）；
- :func:`compute_bom_cost`：确定性成本核算（缺数据不按 0 元假装）；
- :func:`rollup` / :func:`release_checklist`：所有者视图与发布检查清单。
"""
from __future__ import annotations

from .cost import CostInputs, CostResult, compute_bom_cost
from .models import (
    BOM_STATUSES,
    LINE_STATUSES,
    BomHeader,
    BomLine,
    now_iso,
)
from .projection import release_checklist, rollup
from .store import BomStore, OptimisticLockError

__all__ = [
    "BOM_STATUSES",
    "LINE_STATUSES",
    "BomHeader",
    "BomLine",
    "BomStore",
    "OptimisticLockError",
    "CostInputs",
    "CostResult",
    "compute_bom_cost",
    "rollup",
    "release_checklist",
    "now_iso",
]
