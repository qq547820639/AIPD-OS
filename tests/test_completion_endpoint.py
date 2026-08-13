"""EnvCompletionProvider 真实端点测试（Task 3, v5.2）。

验证：配置端点时真实调用 OpenAI 兼容 /chat/completions 并解析响应；
未配置端点/密钥时抛 ModelNotConfiguredError（诚实标记 external_dependency）。
"""

from __future__ import annotations

import os
from unittest import mock

import pytest

from aipd_os.evals_runner.completion import (
    EnvCompletionProvider,
    ModelNotConfiguredError,
)

MSGS = [
    {"role": "system", "content": "[eval case: route-decision] 你是 AIPD 监督者。"},
    {"role": "user", "content": "提示文本"},
]


def _resp(content: str):
    return mock.Mock(
        status_code=200,
        json=lambda: {"choices": [{"message": {"content": content}}]},
        text="",
    )


def test_model_not_configured_when_missing_env():
    with mock.patch.dict(os.environ, {}, clear=True):
        provider = EnvCompletionProvider()
        with pytest.raises(ModelNotConfiguredError):
            provider.complete(MSGS)


def test_model_version_defaults(tmp_path):
    with mock.patch.dict(os.environ, {}, clear=True):
        assert EnvCompletionProvider().model() == "gpt-4o-mini"


def test_model_version_from_env():
    with mock.patch.dict(
        os.environ, {"AIPD_EVAL_MODEL_VERSION": "custom-model"}, clear=True
    ):
        assert EnvCompletionProvider().model() == "custom-model"


def test_real_call_parses_response():
    with mock.patch.dict(
        os.environ,
        {
            "AIPD_EVAL_MODEL_ENDPOINT": "https://example.test/v1/chat/completions",
            "AIPD_EVAL_MODEL_KEY": "secret-key",
            "AIPD_EVAL_MODEL_VERSION": "x-model",
        },
        clear=True,
    ):
        provider = EnvCompletionProvider()
        with mock.patch("requests.post") as post:
            post.return_value = _resp("已读出工程事实，建立 CAD Contract。")
            out = provider.complete(MSGS)

    assert out == "已读出工程事实，建立 CAD Contract。"
    # 校验请求体与鉴权头
    request = post.call_args
    assert request.kwargs["json"]["model"] == "x-model"
    assert request.kwargs["json"]["messages"] == MSGS
    assert request.kwargs["headers"]["Authorization"] == "Bearer secret-key"


def test_non_200_raises_runtime_error():
    with mock.patch.dict(
        os.environ,
        {
            "AIPD_EVAL_MODEL_ENDPOINT": "https://example.test/v1/chat/completions",
            "AIPD_EVAL_MODEL_KEY": "k",
        },
        clear=True,
    ):
        provider = EnvCompletionProvider()
        with mock.patch("requests.post") as post:
            post.return_value = mock.Mock(status_code=429, text="rate limited")
            with pytest.raises(RuntimeError, match="429"):
                provider.complete(MSGS)


def test_malformed_response_raises_runtime_error():
    with mock.patch.dict(
        os.environ,
        {
            "AIPD_EVAL_MODEL_ENDPOINT": "https://example.test/v1/chat/completions",
            "AIPD_EVAL_MODEL_KEY": "k",
        },
        clear=True,
    ):
        provider = EnvCompletionProvider()
        with mock.patch("requests.post") as post:
            post.return_value = mock.Mock(status_code=200, json=lambda: {}, text="")
            with pytest.raises(RuntimeError, match="无法解析"):
                provider.complete(MSGS)


def test_runner_marks_external_when_unconfigured():
    """未配置真实端点时，EvalRunner 把 case 诚实标记为 external_dependency。"""
    from aipd_os.evals_runner.registry import load_cases
    from aipd_os.evals_runner.runner import EvalRunner

    cases = load_cases(_evals_path())
    with mock.patch.dict(os.environ, {}, clear=True):
        runner = EvalRunner(provider=EnvCompletionProvider(), version="5.3.0")
        result = runner.run_case(cases[0])
    assert result.passed is False
    assert "external" in result.failure_type


def _evals_path():
    repo_root = os.path.join(os.path.dirname(__file__), "..")
    p = os.path.join(repo_root, "evals", "evals.json")
    if os.path.exists(p):
        return p
    raise FileNotFoundError("未找到 evals/evals.json")
