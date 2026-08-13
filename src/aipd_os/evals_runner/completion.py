"""完成提供器：脚本化假模型或真实端点。

- :class:`CompletionProvider`：接口基类（``complete`` / ``model``）。
- :class:`RecordedCompletionProvider`：按 system 消息中的 case_id 返回脚本化文本并记录历史。
- :class:`EnvCompletionProvider`：从环境变量读取真实模型端点（OpenAI 兼容），
  真实调用 HTTP API 并返回文本；未配置端点/密钥时抛
  :class:`ModelNotConfiguredError`（诚实标记外部依赖，而非假装生成）。
"""

from __future__ import annotations

import os
import re
from typing import Any

_CASE_TAG = re.compile(r"\[eval case:\s*([^\]]+)\]")

# 请求体默认模型名（可被 AIPD_EVAL_MODEL_VERSION 覆盖）。
_DEFAULT_MODEL = "gpt-4o-mini"

# ---------------------------------------------------------------------------
# Provider 类别（诚实报告的核心：把夹具与真实模型严格区分）
# ---------------------------------------------------------------------------
# 确定性脚本化夹具：contract-test。其「通过」绝不代表真实模型行为。
PROVIDER_CATEGORY_DETERMINISTIC_FIXTURE = "deterministic-fixture"
# 真实模型端点：真实网络调用，纳入「模型行为通过率」。
PROVIDER_CATEGORY_REAL_MODEL = "real-model"
# 纯契约：由实际应用代码驱动（无模型、无夹具）。
PROVIDER_CATEGORY_PURE_CONTRACT = "pure-contract"

PROVIDER_CATEGORIES = (
    PROVIDER_CATEGORY_DETERMINISTIC_FIXTURE,
    PROVIDER_CATEGORY_REAL_MODEL,
    PROVIDER_CATEGORY_PURE_CONTRACT,
)

# 各类别的展示标签（报告中明确标注，绝不让夹具被误读为真实模型）。
CATEGORY_LABELS = {
    PROVIDER_CATEGORY_DETERMINISTIC_FIXTURE: "deterministic-fixture (contract-test)",
    PROVIDER_CATEGORY_REAL_MODEL: "real-model",
    PROVIDER_CATEGORY_PURE_CONTRACT: "pure-contract (code-driven)",
}


class ModelNotConfiguredError(RuntimeError):
    """真实模型未配置（缺端点或密钥）。评估器应把该 case 诚实标记为外部依赖。"""


class CompletionProvider:
    """完成提供器接口。"""

    def model(self) -> str:
        return "unknown"

    def category(self) -> str:
        """返回 provider 类别（deterministic-fixture / real-model / pure-contract）。"""
        return PROVIDER_CATEGORY_PURE_CONTRACT

    def endpoint_type(self) -> str:
        return ""

    def real_network_call(self) -> bool:
        return False

    def complete(self, messages: list[dict[str, Any]]) -> str:
        raise NotImplementedError


class RecordedCompletionProvider(CompletionProvider):
    """脚本化假模型：从 system 消息提取 case_id 返回预设文本，并记录历史。"""

    def __init__(self, script: dict[str, str] | None = None, model_version: str = "eval-fake-model") -> None:
        self._script: dict[str, str] = dict(script or {})
        self._model_version = model_version
        self.history: list[dict[str, Any]] = []

    def model(self) -> str:
        return self._model_version

    def category(self) -> str:
        return PROVIDER_CATEGORY_DETERMINISTIC_FIXTURE

    def endpoint_type(self) -> str:
        return "scripted"

    def real_network_call(self) -> bool:
        return False

    def complete(self, messages: list[dict[str, Any]]) -> str:
        case_id = ""
        for m in messages:
            if m.get("role") == "system":
                mt = _CASE_TAG.search(m.get("content", ""))
                if mt:
                    case_id = mt.group(1).strip()
                    break
        text = self._script.get(case_id, "")
        self.history.append({"case_id": case_id, "messages": messages, "output": text})
        return text


class EnvCompletionProvider(CompletionProvider):
    """真实模型提供器：从环境变量读取 OpenAI 兼容端点并真实调用。

    未配置端点/密钥时抛 :class:`ModelNotConfiguredError`（外部依赖，绝不伪造）。

    环境变量：
    - ``AIPD_EVAL_MODEL_ENDPOINT``：OpenAI 兼容 ``/chat/completions`` 端点 URL。
    - ``AIPD_EVAL_MODEL_KEY``：Bearer API 密钥。
    - ``AIPD_EVAL_MODEL_VERSION``：模型名（可选，默认 ``gpt-4o-mini``）。
    """

    def __init__(
        self,
        endpoint_env: str = "AIPD_EVAL_MODEL_ENDPOINT",
        key_env: str = "AIPD_EVAL_MODEL_KEY",
        model_version_env: str = "AIPD_EVAL_MODEL_VERSION",
        timeout: float = 60.0,
    ) -> None:
        self.endpoint_env = endpoint_env
        self.key_env = key_env
        self.model_version_env = model_version_env
        self.timeout = timeout
        self._model_version = os.environ.get(model_version_env, "") or _DEFAULT_MODEL
        self._endpoint = os.environ.get(endpoint_env, "")
        self._key = os.environ.get(key_env, "")

    def model(self) -> str:
        return self._model_version

    def category(self) -> str:
        return PROVIDER_CATEGORY_REAL_MODEL

    def endpoint_type(self) -> str:
        return "openai-compatible-chat"

    def real_network_call(self) -> bool:
        return True

    def complete(self, messages: list[dict[str, Any]]) -> str:
        if not self._endpoint or not self._key:
            raise ModelNotConfiguredError(
                f"{self.endpoint_env}/{self.key_env} 未配置，无法真实调用模型；"
                "用例应诚实标记为 external_dependency，不得伪造输出。"
            )
        try:
            import requests  # 延迟导入：仅真实端点路径需要
        except ImportError as exc:  # pragma: no cover - 依赖缺失时诚实报外部依赖
            raise ModelNotConfiguredError(
                "缺少 requests 依赖，无法真实调用模型端点"
            ) from exc

        payload: dict[str, Any] = {
            "model": self._model_version,
            "messages": messages,
            "temperature": 0.2,
        }
        headers = {
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
        }
        try:
            resp = requests.post(
                self._endpoint,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"调用模型端点失败: {exc}") from exc
        if resp.status_code != 200:
            raise RuntimeError(
                f"模型端点返回 HTTP {resp.status_code}: {resp.text[:500]}"
            )
        try:
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"无法解析模型端点响应: {exc}") from exc


__all__ = [
    "CompletionProvider",
    "RecordedCompletionProvider",
    "EnvCompletionProvider",
    "ModelNotConfiguredError",
    "PROVIDER_CATEGORY_DETERMINISTIC_FIXTURE",
    "PROVIDER_CATEGORY_REAL_MODEL",
    "PROVIDER_CATEGORY_PURE_CONTRACT",
    "PROVIDER_CATEGORIES",
    "CATEGORY_LABELS",
]
