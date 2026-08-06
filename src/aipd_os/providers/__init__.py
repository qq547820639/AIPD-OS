"""AIPD-OS Provider SDK（P2 平台化）。

提供正式的 Provider 抽象：能力声明（capability declaration）、运行时探测
（probe）、执行入口（run）与注册/发现（ProviderRegistry）。所有第三方 Provider
只需实现 :class:`~aipd_os.providers.sdk.Provider` 基类即可被统一注册与发现。
"""
from __future__ import annotations

from aipd_os.providers.sdk import (
    ProbeResult,
    Provider,
    ProviderRegistry,
    available,
    capability_schema,
    unavailable,
    validate_capabilities,
)

__all__ = [
    "Provider",
    "ProviderRegistry",
    "ProbeResult",
    "available",
    "unavailable",
    "capability_schema",
    "validate_capabilities",
]