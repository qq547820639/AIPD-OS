"""EnvCompletionProvider 真实端点测试（Task 3, v5.2；F-NET-01 收敛后重写）。

验证：配置端点时真实调用 OpenAI 兼容 /chat/completions 并解析响应；
未配置端点/密钥时抛 ModelNotConfiguredError（诚实标记 external_dependency）。

真跑本地 HTTP 服务而不是 patch 依赖库：收敛到 ``aipd_os.net.http`` 后，
打桩 ``requests.post`` 会变成「桩错对象」——测试全绿而真实出口从未被验证，
甚至会把请求放到真网络上去。
"""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
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

ANSWER = "已读出工程事实，建立 CAD Contract。"

# 清掉开发者机器上的代理设置：这些用例只许打本机端口，不许出网
_NO_PROXY = {
    "HTTP_PROXY": "", "http_proxy": "",
    "HTTPS_PROXY": "", "https_proxy": "",
    "no_proxy": "*",
}


class _Handler(BaseHTTPRequestHandler):
    """按路径编排响应，并记录线上真实收到的请求体与鉴权头。"""

    hits: dict[str, int] = {}
    last: dict[str, object] = {}

    def log_message(self, *args):        # 静音 stdio，避免污染 pytest 输出
        pass

    def _bump(self) -> int:
        _Handler.hits[self.path] = _Handler.hits.get(self.path, 0) + 1
        return _Handler.hits[self.path]

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_POST(self):                   # noqa: N802 - BaseHTTPRequestHandler 约定
        self._bump()
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        _Handler.last = {
            "body": json.loads(raw or b"null"),
            "auth": self.headers.get("Authorization"),
            "content_type": self.headers.get("Content-Type"),
        }
        if self.path == "/rate":
            return self._send(429, b"rate limited", "text/plain")
        if self.path == "/junk":
            return self._send(200, b"{}", "application/json")
        content = json.dumps({"choices": [{"message": {"content": ANSWER}}]}).encode()
        return self._send(200, content, "application/json")


@pytest.fixture(scope="module")
def base():
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()
    srv.server_close()


@pytest.fixture(autouse=True)
def _reset():
    _Handler.hits = {}
    _Handler.last = {}


def _env(base: str, path: str, key: str = "secret-key") -> dict[str, str]:
    return {
        "AIPD_EVAL_MODEL_ENDPOINT": base + path,
        "AIPD_EVAL_MODEL_KEY": key,
        "AIPD_EVAL_MODEL_VERSION": "x-model",
        **_NO_PROXY,
    }


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


def test_real_call_parses_response(base):
    with mock.patch.dict(os.environ, _env(base, "/chat/completions"), clear=True):
        provider = EnvCompletionProvider()
        out = provider.complete(MSGS)

    assert out == ANSWER
    # 校验真实上线的请求体与鉴权头（不是打桩参数的自证）
    assert _Handler.last["auth"] == "Bearer secret-key"
    assert _Handler.last["content_type"] == "application/json"
    body = _Handler.last["body"]
    assert body["model"] == "x-model"
    assert body["messages"] == MSGS


def test_non_200_raises_runtime_error(base):
    with mock.patch.dict(os.environ, _env(base, "/rate", key="k"), clear=True):
        provider = EnvCompletionProvider()
        with pytest.raises(RuntimeError, match="429"):
            provider.complete(MSGS)
    # 付费端点不自动重试：一次命中即诚实上抛，避免重复计费
    assert _Handler.hits["/rate"] == 1


def test_malformed_response_raises_runtime_error(base):
    with mock.patch.dict(os.environ, _env(base, "/junk", key="k"), clear=True):
        provider = EnvCompletionProvider()
        with pytest.raises(RuntimeError, match="无法解析"):
            provider.complete(MSGS)


def test_unreachable_endpoint_raises_runtime_error_not_silence(base):
    """端点连不上（传输层异常）必须是 RuntimeError，不能伪装成空输出。"""
    with mock.patch.dict(
        os.environ, _env("http://127.0.0.1:1", "/chat/completions", key="k"),
        clear=True,
    ):
        provider = EnvCompletionProvider(timeout=2.0)
        with pytest.raises(RuntimeError, match="调用模型端点失败"):
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
