"""内置核心工具适配器注册。

注册 10 个内置核心适配器（research / document / imggen / layout / cad /
local_brep / faceted / mail_rfq / supplier / evt_dvt_pvt）进
:class:`AdapterRegistry`。注意：product.*、idea.*、researchstudio 等适配器
不在此注册，由 runtime bootstrap（``aipd_os.runtime._register_external_providers``）
按配置动态装配——此处不是「全部适配器」。
"""

from __future__ import annotations

from aipd_os.execution.adapter import ToolAdapter
from aipd_os.execution.registry import AdapterRegistry
from aipd_os.tool_adapters.cad_adapter import CadAdapter
from aipd_os.tool_adapters.document_adapter import DocumentGenAdapter
from aipd_os.tool_adapters.evt_dvt_pvt_adapter import ValidationDataAdapter
from aipd_os.tool_adapters.faceted_adapter import FacetedAdapter
from aipd_os.tool_adapters.imggen_adapter import ImageGenAdapter
from aipd_os.tool_adapters.layout_adapter import LayoutAdapter
from aipd_os.tool_adapters.local_brep_adapter import LocalBrepAdapter
from aipd_os.tool_adapters.mail_rfq_adapter import MailRfqAdapter
from aipd_os.tool_adapters.research_adapter import ResearchAdapter
from aipd_os.tool_adapters.supplier_adapter import SupplierAdapter


def builtin_adapters() -> list[ToolAdapter]:
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
