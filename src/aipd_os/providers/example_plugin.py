"""示例 Provider 插件。

演示如何实现 :class:`aipd_os.providers.sdk.Provider`：

- 声明一个 ``generic.echo`` 能力（确定性、无外部依赖）；
- 通过配置注入 ``prefix``；
- ``probe`` 恒为可用；
- ``run`` 返回确定性结果。

作为插件范例，其它真实 Provider（image / vision / cad / mail / research）
可参考本文件实现一致的接口与能力声明。
"""
from __future__ import annotations

from typing import Any, Dict, List

from aipd_os.providers.sdk import Provider, ProbeResult, available


class ExamplePlugin(Provider):
    """一个可注册进 ProviderRegistry 的示例插件。"""

    #: Provider 唯一名称
    name = "example.echo"

    def __init__(self, prefix: str = "") -> None:
        self._prefix = prefix

    def configure(self, config: Dict[str, Any]) -> None:
        """注入配置（示例：prefix）。"""
        if config.get("prefix"):
            self._prefix = str(config["prefix"])

    def capabilities(self) -> List[Dict[str, Any]]:
        return [{
            "id": "generic.echo",
            "name": "Echo 示例能力",
            "domain": "generic",
            "category": "execution",
            "evidence": {
                "entry_point": "aipd_os.providers.example_plugin.ExamplePlugin.run",
                "impl_file": "src/aipd_os/providers/example_plugin.py",
                "test_type": "unit",
            },
        }]

    def probe(self) -> ProbeResult:
        # 示例插件无需外部依赖，恒为可用
        return available()

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        message = context.get("message", "")
        echo = f"{self._prefix}{message}" if self._prefix else message
        return {"ok": True, "echo": echo, "provider": self.name}


__all__ = ["ExamplePlugin"]