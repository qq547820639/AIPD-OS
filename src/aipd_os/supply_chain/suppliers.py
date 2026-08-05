"""供应商档案与资质校验。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class SupplierProfile:
    """供应商档案：id、名称、资质等级与证书清单。"""

    supplier_id: str
    name: str
    qualification: str = "unqualified"
    certificates: List[str] = field(default_factory=list)


class SupplierRegistry:
    """按 supplier_id 登记与查询供应商档案。"""

    def __init__(self) -> None:
        self._suppliers: Dict[str, SupplierProfile] = {}

    def add(self, profile: SupplierProfile) -> SupplierProfile:
        self._suppliers[profile.supplier_id] = profile
        return profile

    def get(self, supplier_id: str) -> Optional[SupplierProfile]:
        return self._suppliers.get(supplier_id)

    def qualify(self, supplier_id: str, required_cert: str) -> bool:
        """仅当供应商档案中真实存在 required_cert 证书时才判定可合格。

        证书缺失或供应商不存在都返回 False —— 不虚构资质。
        """
        profile = self._suppliers.get(supplier_id)
        if profile is None:
            return False
        if required_cert in (profile.certificates or []):
            profile.qualification = "qualified"
            return True
        return False


__all__ = ["SupplierProfile", "SupplierRegistry"]
