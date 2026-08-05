"""适配器注册表。"""

from __future__ import annotations

from typing import Dict, List, Optional

from aipd_os.execution.adapter import ToolAdapter


class AdapterRegistry:
    """按能力标识注册与查询适配器。"""

    def __init__(self) -> None:
        self._adapters: Dict[str, ToolAdapter] = {}

    def register(self, adapter: ToolAdapter) -> None:
        cid = adapter.capability_id()
        if cid in self._adapters:
            raise ValueError(f"capability already registered: {cid}")
        self._adapters[cid] = adapter

    def get(self, capability_id: str) -> Optional[ToolAdapter]:
        return self._adapters.get(capability_id)

    def all(self) -> List[ToolAdapter]:
        return list(self._adapters.values())

    def discover_all(self) -> List[dict]:
        return [a.discover() for a in self._adapters.values()]

    def __contains__(self, capability_id: str) -> bool:
        return capability_id in self._adapters


__all__ = ["AdapterRegistry"]
