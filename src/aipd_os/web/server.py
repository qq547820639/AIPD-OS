"""Owner Web Console HTTP 服务。

基于标准库 :mod:`http.server.ThreadingHTTPServer`，不引入任何第三方框架。
提供 HTML 页面（GET）与 JSON API（GET/POST ``/api/*``），二者共用
:class:`~aipd_os.web.views.WebConsole` 同一业务服务。

安全：JSON API 在序列化前会剥离 ``details`` 子字典（内部 ID / 内部代号），
默认不暴露内部标识。
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional, Tuple
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

    server: "OwnerHTTPServer"
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

    def _send_json(self, payload: Dict[str, Any], status: int = 200) -> None:
        safe = _strip_details(payload)
        body = json.dumps(safe, ensure_ascii=False, default=_json_default).encode("utf-8")
        self._send_bytes(body, status, "application/json; charset=utf-8")

    def _send_error_json(self, message: str, status: int = 400) -> None:
        self._send_json({"ok": False, "error": str(message)}, status)

    def _form(self) -> Dict[str, str]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else ""
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
        self._handle_api("POST", path)

    # ----------------------------------------------------------- JSON API
    def _handle_api(self, method: str, path: str) -> None:
        c = self.console
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

    def __init__(self, addr: Tuple[str, int], console: WebConsole) -> None:
        self.console = console
        super().__init__(addr, OwnerHandler)


def serve(console: WebConsole, host: str = "127.0.0.1",
          port: int = 8080, print_url: bool = True) -> None:
    """在前台运行服务（阻塞）。Ctrl+C 或 KeyboardInterrupt 时优雅退出。"""
    server = OwnerHTTPServer((host, port), console)
    if print_url:
        display = "localhost" if host in ("0.0.0.0", "::", "") else host
        print(f"Owner Web Console 已启动： http://{display}:{server.server_address[1]}/")
        print("按 Ctrl+C 停止。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def start_server(console: WebConsole, host: str = "127.0.0.1",
                 port: int = 0) -> OwnerHTTPServer:
    """创建一个已完成绑定并激活的服务器（供测试或后台线程使用）。

    注：:class:`ThreadingHTTPServer` 构造器即完成 ``server_bind`` 与
    ``server_activate``，故此处无需重复绑定。
    """
    return OwnerHTTPServer((host, port), console)


__all__ = ["OwnerHTTPServer", "OwnerHandler", "serve", "start_server"]