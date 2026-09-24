"""通用 LLM 客户端（OpenAI 兼容 ``/chat/completions``）。

这是全仓第一个**通用** LLM 客户端：此前 ``evals_runner/completion.py`` 的
``EnvCompletionProvider`` 仅服务模型评估（其 endpoint 语义绑定评估用例），
本模块提供与业务无关的 ``/chat/completions`` 调用能力，供 product
intelligence 与 idea decompose 的 LLM Provider 复用。

仅使用标准库（经 ``aipd_os.net.http`` 这一统一出口），不新增任何第三方运行时依赖。

诚实原则：endpoint 或 api_key 为空时，:meth:`LlmClient.complete` 抛
:class:`LlmNotConfiguredError`（诚实标记外部依赖），绝不伪造输出。
"""
from __future__ import annotations

from typing import Any

from aipd_os.net.http import HttpError
from aipd_os.net.http import request as http_request

# 模型名未显式配置时的合理默认（OpenAI 兼容的轻量模型名）。
DEFAULT_MODEL = "gpt-4o-mini"


class LlmNotConfiguredError(RuntimeError):
    """endpoint 或 api_key 为空时抛出（诚实外部依赖，绝不伪造输出）。"""


class LlmClient:
    """OpenAI 兼容 ``/chat/completions`` 客户端（出口在 ``aipd_os.net.http``）。"""

    def __init__(
        self,
        endpoint: str,
        api_key: str,
        model: str,
        timeout: float = 60.0,
        max_attempts: int = 1,
    ) -> None:
        self.endpoint = endpoint
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_attempts = max_attempts

    @property
    def configured(self) -> bool:
        """endpoint 与 api_key 均非空才视为已配置（诚实判定）。"""
        return bool(self.endpoint) and bool(self.api_key)

    def complete(self, messages: list[dict[str, Any]]) -> str:
        """调用 ``/chat/completions``，返回 ``choices[0].message.content``。

        :param messages: ``[{"role": ..., "content": ...}, ...]`` 消息列表
        :raises LlmNotConfiguredError: endpoint 或 api_key 为空
        :raises RuntimeError: 非 200 / 网络异常 / 响应无法解析

        endpoint 的 scheme 由 :mod:`aipd_os.net.http` 统一校验（只允许 http/https）。
        """
        if not self.endpoint or not self.api_key:
            raise LlmNotConfiguredError(
                "LLM endpoint 或 api_key 未配置，无法真实调用模型；"
                "应诚实标记为 external_dependency，不得伪造输出。")

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
        }
        try:
            # 计费的外部调用：默认不自动重试（本仓 EXTERNAL_SIDE_EFFECT 同一口径），
            # 需要时由调用方显式放宽 max_attempts。
            resp = http_request(
                self.endpoint, method="POST", json_body=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout, max_attempts=self.max_attempts)
        except HttpError as exc:
            raise RuntimeError(f"调用模型端点失败: {exc}") from exc

        if resp.status != 200:
            raise RuntimeError(f"模型端点返回 HTTP {resp.status}: {resp.text[:500]}")

        try:
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
        except ValueError as exc:
            raise RuntimeError(f"无法解析模型端点响应: {exc}") from exc
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"无法解析模型端点响应: {exc}") from exc
        if not isinstance(content, str):
            raise RuntimeError(
                "无法解析模型端点响应: choices[0].message.content 不是字符串")
        return content


__all__ = [
    "DEFAULT_MODEL",
    "LlmClient",
    "LlmNotConfiguredError",
]
