"""Capability Registry 导出表防回归测试（v5.9.2 Q-1）。

验证 ``registry.py`` 的 ``__all__`` 已修正（此前误写为 ``_all__``，导致
``from aipd_os.registry import *`` 与打包/文档工具看不到导出符号）。
"""
from __future__ import annotations

import aipd_os.registry as registry_mod


def test_registry_all_is_non_empty():
    """registry.__all__ 必须非空（typo 回归防护）。"""
    assert registry_mod.__all__, "registry.__all__ 不应为空"


def test_registry_all_exports_capability_registry():
    """registry.__all__ 必须包含核心导出符号 CapabilityRegistry。"""
    assert "CapabilityRegistry" in registry_mod.__all__


def test_registry_all_symbols_resolve():
    """registry.__all__ 中每个符号都应真实存在于模块命名空间。"""
    for name in registry_mod.__all__:
        assert hasattr(registry_mod, name), f"__all__ 中的 {name} 不可解析"
