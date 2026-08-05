"""内置适配器注册。

将全部具体适配器注册进 :class:`AdapterRegistry`。
"""

from __future__ import annotations

from typing import List

from aipd_os.execution.adapter import ToolAdapter
from aipd_os.execution.registry import AdapterRegistry

from aipd_os.tool_adapters.research_adapter import ResearchAdapter
from aipd_os.tool_adapters.document_adapter import DocumentGenAdapter
from aipd_os.tool_adapters.imggen_adapter import ImageGenAdapter
from aipd_os.tool_adapters.layout_adapter import LayoutAdapter
from aipd_os.tool_adapters.cad_adapter import CadAdapter
from aipd_os.tool_adapters.local_brep_adapter import LocalBrepAdapter
from aipd_os.tool_adapters.faceted_adapter import FacetedAdapter
from aipd_os.tool_adapters.mail_rfq_adapter import MailRfqAdapter
from aipd_os.tool_adapters.supplier_adapter import SupplierAdapter
from aipd_os.tool_adapters.evt_dvt_pvt_adapter import ValidationDataAdapter


def builtin_adapters() -> List[ToolAdapter]:
    """返回全部内置适配器实例列表。"""
    return [
        ResearchAdapter(),
        DocumentGenAdapter(),
        ImageGenAdapter(),
        LayoutAdapter(),
        CadAdapter(),
        LocalBrepAdapter(),
        FacetedAdapter(),
        MailRfqAdapter(),
        SupplierAdapter(),
        ValidationDataAdapter(),
    ]


def build_registry() -> AdapterRegistry:
    """构建并返回注册了全部内置适配器的注册表。"""
    registry = AdapterRegistry()
    for adapter in builtin_adapters():
        registry.register(adapter)
    return registry


__all__ = ["builtin_adapters", "build_registry"]
