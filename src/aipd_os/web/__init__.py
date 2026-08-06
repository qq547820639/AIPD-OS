"""Owner Web Console。

本地可运行的 Owner Web Console（``aipd ui``）：基于标准库 ``http.server``，
提供 HTML 页面 + JSON API，二者共用 :class:`~aipd_os.web.views.WebConsole`
同一业务服务（项目总览 / 决策 / 制品 / 运行控制 / 外部等待 / 首次使用向导）。
"""
from __future__ import annotations

from .server import OwnerHTTPServer, OwnerHandler, serve, start_server
from .views import RunController, WebConsole, safe_ref

__all__ = ["WebConsole", "RunController", "safe_ref",
           "OwnerHTTPServer", "OwnerHandler", "serve", "start_server"]