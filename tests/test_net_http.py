"""``aipd_os.net.http`` 的行为契约（真跑本地 HTTP 服务，不打外部网络）。

这些用例是「收敛 8 处 HTTP 出口」的前提：策略（只重试瞬态状态、尊重
``Retry-After``、scheme 白名单、超时必生效）必须在**发出请求之前**就成立。
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from aipd_os.net import http as H


class _Handler(BaseHTTPRequestHandler):
    """按路径编排响应；记录命中次数供断言使用。"""

    hits: dict[str, int] = {}
    last: dict[str, object] = {}

    def log_message(self, *args):        # 静音 stdio，避免污染 pytest 输出
        pass

    def _bump(self, key: str) -> int:
        _Handler.hits[key] = _Handler.hits.get(key, 0) + 1
        return _Handler.hits[key]

    def _send(self, status: int, body: bytes = b"",
              extra: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self):                    # noqa: N802 - BaseHTTPRequestHandler 约定
        n = self._bump(self.path)
        if self.path == "/ok":
            return self._send(200, json.dumps({"ok": True}).encode())
        if self.path == "/flaky":
            if n < 3:
                return self._send(429, b"", {"Retry-After": "0"})
            return self._send(200, json.dumps({"tries": n}).encode())
        if self.path == "/never":
            return self._send(503, b"down")
        if self.path == "/notfound":
            return self._send(404, b'{"error":"nope"}')
        if self.path == "/notjson":
            return self._send(200, b"<html>not json</html>")
        if self.path == "/big":
            return self._send(200, b"x" * 100)
        if self.path == "/slow":
            time.sleep(1.5)
            return self._send(200, b"{}")
        return self._send(418, b"")

    def do_POST(self):                   # noqa: N802
        self._bump(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        _Handler.last = {"body": raw,
                         "content_type": self.headers.get("Content-Type"),
                         "auth": self.headers.get("Authorization")}
        return self._send(200, json.dumps({"echoed": json.loads(raw or b"null")})
                          .encode())


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


def _hits(path: str) -> int:
    return _Handler.hits.get(path, 0)


def test_get_and_json_parse(base):
    assert H.request_json(f"{base}/ok") == {"ok": True}
    resp = H.request(f"{base}/ok")
    assert resp.status == 200 and resp.header("Content-Type") == "application/json"


def test_post_json_body_sets_content_type_and_sends_payload(base):
    out = H.request(f"{base}/echo", method="POST",
                    json_body={"a": "中文"}, headers={"Authorization": "Bearer x"})
    assert out.json()["echoed"] == {"a": "中文"}
    assert _Handler.last["content_type"] == "application/json"
    assert _Handler.last["auth"] == "Bearer x"


def test_retry_after_is_honored_then_succeeds(base):
    slept: list[float] = []
    out = H.request(f"{base}/flaky", max_attempts=4,
                    backoff_base=9.0, sleep=slept.append)
    assert out.status == 200 and out.json()["tries"] == 3
    assert _hits("/flaky") == 3
    # Retry-After: 0 ⇒ 用服务器给的 0，而不是本地 9/18 的指数退避
    assert slept == [0.0, 0.0]


def test_exponential_backoff_and_attempt_cap(base):
    slept: list[float] = []
    out = H.request(f"{base}/never", max_attempts=3, backoff_base=2.0,
                    sleep=slept.append)
    assert out.status == 503
    assert _hits("/never") == 3, "只重试瞬态状态，且到次数上限就返回"
    assert slept == [2.0, 4.0]


def test_non_retryable_status_returns_immediately(base):
    slept: list[float] = []
    out = H.request(f"{base}/notfound", max_attempts=5, sleep=slept.append)
    assert out.status == 404
    assert _hits("/notfound") == 1
    assert slept == []


def test_scheme_whitelist_blocks_before_socket(monkeypatch):
    def boom(*a, **kw):                   # 一旦真的要发请求就失败
        raise AssertionError("must not open a connection")

    monkeypatch.setattr(H.urllib.request, "urlopen", boom)
    for url in ("file:///etc/passwd", "ftp://example/x", "data:,x", ""):
        with pytest.raises(H.HttpError, match="unsupported URL scheme"):
            H.request(url)


def test_transport_error_surfaces_immediately_without_retry(monkeypatch):
    calls: list[int] = []

    def fail(*a, **kw):
        calls.append(1)
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(H.urllib.request, "urlopen", fail)
    with pytest.raises(H.HttpError, match="connection refused"):
        H.request("http://127.0.0.1:1/x", max_attempts=4)
    assert len(calls) == 1, "网络异常不重试（只有瞬态 HTTP 状态才重试）"


def test_timeout_is_applied(base):
    started = time.monotonic()
    with pytest.raises(H.HttpError):
        H.request(f"{base}/slow", timeout=0.3)
    assert time.monotonic() - started < 1.4, "timeout 参数没生效"


def test_request_json_raises_on_error_status_and_non_json(base):
    with pytest.raises(H.HttpError, match="HTTP 404"):
        H.request_json(f"{base}/notfound")
    with pytest.raises(H.HttpError, match="not JSON"):
        H.request_json(f"{base}/notjson")


@pytest.mark.parametrize("value,expected", [
    ("7", 7.0), ("0", 0.0), ("-5", 0.0), ("garbage", None), (None, None),
])
def test_retry_after_parsing(value, expected):
    got = H.retry_after_seconds(value)
    assert got == expected


def test_retry_after_http_date_is_relative_to_now():
    future = time.time() + 5.0
    header = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime(future))
    got = H.retry_after_seconds(header)
    assert got is not None and 3.0 <= got <= 6.5


class TestBodyCap:
    """响应体上限必须**响亮失败**，不能静默截断（F-NET-02）。

    截断只对下游造成两种后果：JSON 解析报「不是 JSON」（把尺寸问题伪装成格式问题），
    或者更糟——把半张 PNG 当完整图片写盘并记进证据。上限因此只能在读的一刻判定。
    """

    def test_over_cap_raises_rather_than_truncating(self, base):
        with pytest.raises(H.HttpError) as exc:
            H.request(base + "/big", max_bytes=64)
        assert "64" in str(exc.value), str(exc.value)

    def test_at_cap_is_not_truncated(self, base):
        """边界两个方向都要钉：正好等于上限是完整读取，不是溢出。"""
        resp = H.request(base + "/big", max_bytes=100)
        assert resp.content == b"x" * 100

    def test_one_byte_below_cap_still_raises(self, base):
        with pytest.raises(H.HttpError):
            H.request(base + "/big", max_bytes=99)

    def test_error_bodies_obey_the_same_cap(self, base):
        """404 的正文也不能绕过上限——它同样会被解码/展示。"""
        resp = H.request(base + "/notfound", max_bytes=64)
        assert resp.status == 404
        with pytest.raises(H.HttpError):
            H.request(base + "/notfound", max_bytes=5)

    def test_default_cap_is_resolved_at_call_time(self, base, monkeypatch):
        """默认上限走模块常量，且必须在**调用时**读取。

        若默认值绑在 def 行（``max_bytes=MAX_BODY_READ_BYTES``），调常量就无效——
        而调用方（图像下载等）从来不显式传参，只能靠这个常量。
        """
        monkeypatch.setattr(H, "MAX_BODY_READ_BYTES", 64)
        with pytest.raises(H.HttpError):
            H.request(base + "/big")
        monkeypatch.setattr(H, "MAX_BODY_READ_BYTES", 100)
        assert H.request(base + "/big").content == b"x" * 100
