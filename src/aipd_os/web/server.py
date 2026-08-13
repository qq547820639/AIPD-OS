"""Owner Web Console HTTP 服务。

基于标准库 :mod:`http.server.ThreadingHTTPServer`，不引入任何第三方框架。
提供 HTML 页面（GET）与 JSON API（GET/POST ``/api/*``），二者共用
:class:`~aipd_os.web.views.WebConsole` 同一业务服务。

安全：
- **默认 localhost dev console**（默认绑定 127.0.0.1）；绑定非 localhost 时
  必须配置 ``AIPD_WEB_TOKEN``，否则拒绝启动。
- 可选令牌认证：设置环境变量 ``AIPD_WEB_TOKEN`` 后，所有 ``/api/*`` 请求
  （GET/POST 均校验）须携带 ``Authorization: Bearer <token>``、
  ``X-AIPD-Token: <token>`` 或 ``?token=``，否则返回 401。
- JSON API 在序列化前会剥离 ``details`` 子字典（内部 ID / 内部代号），
  默认不暴露内部标识；POST 请求体上限 1MB（超限返回 413）。
"""
from __future__ import annotations

import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from .templates import RENDERERS
from .views import WebConsole

# 页面中心 → JSON API 业务数据函数
PAGE_KEYS = {
    "/onboarding": "onboarding",
    "/overview": "overview",
    "/decisions": "decisions",
    "/artifacts": "artifacts",
    "/run": "run",
    "/external-wait": "external-wait",
}

# POST 请求体大小上限（1MB）。
MAX_FORM_BYTES = 1024 * 1024

# 视为本机回环的 host（绑定这些地址时无需强制 token）。
_LOCALHOST_HOSTS = {"", "127.0.0.1", "localhost", "::1"}


def _is_localhost(host: str) -> bool:
    return host in _LOCALHOST_HOSTS


def _resolve_web_token(web_token: str | None) -> str:
    """令牌优先取显式参数，其次取环境变量 AIPD_WEB_TOKEN。"""
    if web_token is not None:
        return web_token
    return os.environ.get("AIPD_WEB_TOKEN", "")


def _strip_details(value: Any) -> Any:
    """递归移除 ``details`` 子字典，避免对外暴露内部 ID / 内部代号。"""
    if isinstance(value, dict):
        return {k: _strip_details(v) for k, v in value.items() if k != "details"}
    if isinstance(value, list):
        return [_strip_details(v) for v in value]
    return value


def _json_default(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


class OwnerHandler(BaseHTTPRequestHandler):
    """路由 HTML 页面与 JSON API 单一请求处理器。"""

    server: OwnerHTTPServer
    protocol_version = "HTTP/1.1"

    # ----------------------------------------------------------- 基础
    @property
    def console(self) -> WebConsole:
        return self.server.console

    def log_message(self, fmt, *args):  # noqa: A003 - 标准库签名
        super().log_message(fmt, *args)

    def _send_bytes(self, body: bytes, status: int = 200,
                    content_type: str = "text/html; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        safe = _strip_details(payload)
        body = json.dumps(safe, ensure_ascii=False, default=_json_default).encode("utf-8")
        self._send_bytes(body, status, "application/json; charset=utf-8")

    def _send_error_json(self, message: str, status: int = 400) -> None:
        self._send_json({"ok": False, "error": str(message)}, status)

    # ----------------------------------------------------------- 令牌认证
    def _token_authorized(self) -> bool:
        """未配置 AIPD_WEB_TOKEN 时放行；配置后校验 Bearer / X-AIPD-Token / ?token=。"""
        expected = self.server.web_token
        if not expected:
            return True
        auth = self.headers.get("Authorization", "")
        supplied = ""
        if auth.startswith("Bearer "):
            supplied = auth[len("Bearer "):].strip()
        if not supplied:
            supplied = self.headers.get("X-AIPD-Token", "")
        if not supplied:
            query = urlparse(self.path).query
            supplied = (parse_qs(query).get("token") or [""])[0] or ""
        return hmac.compare_digest(supplied, expected)

    def _form(self) -> dict[str, str]:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_FORM_BYTES:
            raise ValueError("request body too large (limit 1MB)")
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        if not raw.strip():
            return {}
        content_type = (self.headers.get("Content-Type") or "").lower()
        if "application/json" in content_type:
            # POST JSON 体此前被静默忽略（只解析 form-urlencoded）
            try:
                data = json.loads(raw)
            except ValueError as exc:
                raise ValueError(f"invalid JSON body: {exc}") from exc
            if not isinstance(data, dict):
                raise ValueError("JSON body 必须是对象")
            return {str(k): (v[0] if isinstance(v, list) and v else str(v))
                    for k, v in data.items()}
        return {k: v[0] if v else "" for k, v in parse_qs(raw).items()}

    # ----------------------------------------------------------- GET 路由
    def do_GET(self):  # noqa: N802 - 标准库回调
        path = urlparse(self.path).path
        if path == "/":
            self.send_response(302)
            target = "/onboarding" if not self.console.is_initialized() else "/overview"
            self.send_header("Location", target)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        if path.startswith("/api/"):
            self._handle_api("GET", path)
            return

        page = PAGE_KEYS.get(path)
        if page is None:
            self._send_error_json("未找到页面", 404)
            return
        try:
            html = RENDERERS[page](self.console)
        except Exception as exc:  # noqa: BLE001 - 业务异常如实返回
            self._send_error_json(str(exc), 500)
            return
        self._send_bytes(html.encode("utf-8"))

    # ----------------------------------------------------------- POST 路由
    def do_POST(self):  # noqa: N802 - 标准库回调
        path = urlparse(self.path).path
        if not path.startswith("/api/"):
            self._send_error_json("POST 仅支持 /api/* 端点", 404)
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_FORM_BYTES:
            self._send_error_json("request body too large (limit 1MB)", 413)
            return
        self._handle_api("POST", path)

    # ----------------------------------------------------------- JSON API
    def _handle_api(self, method: str, path: str) -> None:
        c = self.console
        if not self._token_authorized():
            return self._send_error_json(
                "unauthorized: missing or invalid AIPD_WEB_TOKEN", 401)
        try:
            if method == "GET":
                if path == "/api/onboarding":
                    return self._send_json(c.onboarding_center())
                if path == "/api/overview":
                    return self._send_json(c.overview())
                if path == "/api/decisions":
                    return self._send_json(c.decision_center())
                if path == "/api/artifacts":
                    return self._send_json(c.artifact_center())
                if path == "/api/run":
                    return self._send_json(c.run_control())
                if path == "/api/external-wait":
                    return self._send_json(c.external_wait_center())
                return self._send_error_json("未找到 API", 404)

            data = self._form()
            if path == "/api/onboarding/create":
                return self._send_json(c.create_project(
                    data.get("name", ""), data.get("goal", "")))
            if path == "/api/onboarding/import":
                return self._send_json(c.import_project_from_examples())
            if path == "/api/onboarding/fix":
                return self._send_json(c.fix_issue(data.get("name", "")))
            if path == "/api/decisions/approve":
                return self._send_json(c.approve_decision(data.get("ref", "")))
            if path == "/api/artifacts/approve":
                return self._send_json(c.approve_artifact(data.get("ref", "")))
            if path == "/api/artifacts/reject":
                return self._send_json(c.reject_artifact(
                    data.get("ref", ""), data.get("reason", "")))
            if path == "/api/artifacts/rework":
                return self._send_json(c.rework_artifact(
                    data.get("ref", ""), data.get("note", "")))
            if path == "/api/run/start":
                return self._send_json(c.start_run(data.get("intent", "")))
            if path == "/api/run/pause":
                return self._send_json(c.pause_run())
            if path == "/api/run/resume":
                return self._send_json(c.resume_run())
            if path == "/api/run/cancel":
                return self._send_json(c.cancel_run())
            if path == "/api/run/retry":
                return self._send_json(c.retry_run())
            return self._send_error_json("未找到 API", 404)
        except Exception as exc:  # noqa: BLE001 - 业务异常如实返回
            return self._send_error_json(str(exc), 400)


class OwnerHTTPServer(ThreadingHTTPServer):
    """把业务服务挂到服务器实例上，供请求处理器存取。"""

    daemon_threads = True

    def __init__(self, addr: tuple[str, int], console: WebConsole,
                 web_token: str = "") -> None:
        self.console = console
        self.web_token = web_token
        super().__init__(addr, OwnerHandler)


def serve(console: WebConsole, host: str = "127.0.0.1",
          port: int = 8080, print_url: bool = True,
          web_token: str | None = None) -> None:
    """在前台运行服务（阻塞）。Ctrl+C 或 KeyboardInterrupt 时优雅退出。

    绑定非 localhost 时必须配置 ``AIPD_WEB_TOKEN``（显式参数或环境变量），
    否则拒绝启动（fail-closed）。
    """
    token = _resolve_web_token(web_token)
    if not _is_localhost(host) and not token:
        raise RuntimeError(
            "non-localhost owner web console requires AIPD_WEB_TOKEN; "
            "set AIPD_WEB_TOKEN or bind to 127.0.0.1/localhost")
    server = OwnerHTTPServer((host, port), console, web_token=token)
    if print_url:
        display = "localhost" if host in ("0.0.0.0", "::", "") else host
        print(f"Owner Web Console 已启动： http://{display}:{server.server_address[1]}/")
        print("按 Ctrl+C 停止。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        # noqa: EMPTY_EXCEPT - Ctrl+C 优雅退出：交由 finally 关闭服务器
        pass
    finally:
        server.server_close()


def start_server(console: WebConsole, host: str = "127.0.0.1",
                 port: int = 0, web_token: str | None = None) -> OwnerHTTPServer:
    """创建一个已完成绑定并激活的服务器（供测试或后台线程使用）。

    注：:class:`ThreadingHTTPServer` 构造器即完成 ``server_bind`` 与
    ``server_activate``，故此处无需重复绑定。
    """
    token = _resolve_web_token(web_token)
    return OwnerHTTPServer((host, port), console, web_token=token)


__all__ = ["OwnerHTTPServer", "OwnerHandler", "serve", "start_server"]
