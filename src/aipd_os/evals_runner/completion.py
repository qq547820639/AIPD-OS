"""完成提供器：脚本化假模型或真实端点。

- :class:`CompletionProvider`：接口基类（``complete`` / ``model``）。
- :class:`RecordedCompletionProvider`：按 system 消息中的 case_id 返回脚本化文本并记录历史。
- :class:`EnvCompletionProvider`：从环境变量读取真实模型端点；未配置时抛
  :class:`ModelNotConfiguredError`（诚实标记外部依赖，而非假装生成）。
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

_CASE_TAG = re.compile(r"\[eval case:\s*([^\]]+)\]")


class ModelNotConfiguredError(RuntimeError):
    """真实模型未配置（缺端点或密钥）。评估器应把该 case 诚实标记为外部依赖。"""


class CompletionProvider:
    """完成提供器接口。"""

    def model(self) -> str:
        return "unknown"

    def complete(self, messages: List[Dict[str, Any]]) -> str:
        raise NotImplementedError


class RecordedCompletionProvider(CompletionProvider):
    """脚本化假模型：从 system 消息提取 case_id 返回预设文本，并记录历史。"""

    def __init__(self, script: Optional[Dict[str, str]] = None, model_version: str = "eval-fake-model") -> None:
        self._script: Dict[str, str] = dict(script or {})
        self._model_version = model_version
        self.history: List[Dict[str, Any]] = []

    def model(self) -> str:
        return self._model_version

    def complete(self, messages: List[Dict[str, Any]]) -> str:
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
    """真实模型提供器：从环境变量读取端点与密钥，未配置则诚实抛错。"""

    def __init__(
        self,
        endpoint_env: str = "AIPD_EVAL_MODEL_ENDPOINT",
        key_env: str = "AIPD_EVAL_MODEL_KEY",
        model_version_env: str = "AIPD_EVAL_MODEL_VERSION",
    ) -> None:
        self.endpoint_env = endpoint_env
        self.key_env = key_env
        self._model_version = os.environ.get(model_version_env, "env-model")

    def model(self) -> str:
        return self._model_version

    def complete(self, messages: List[Dict[str, Any]]) -> str:
        endpoint = os.environ.get(self.endpoint_env)
        key = os.environ.get(self.key_env)
        if not endpoint or not key:
            raise ModelNotConfiguredError(
                f"{self.endpoint_env}/{self.key_env} 未配置，无法调用真实模型"
            )
        # 具体端点 SDK 未接入，诚实拒绝假装调用。
        raise RuntimeError("EnvCompletionProvider: 未接入具体模型端点 SDK")


__all__ = [
    "CompletionProvider",
    "RecordedCompletionProvider",
    "EnvCompletionProvider",
    "ModelNotConfiguredError",
]
