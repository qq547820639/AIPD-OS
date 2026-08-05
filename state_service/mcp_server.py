#!/usr/bin/env python3
"""AIPD 状态服务的 MCP 适配器（薄层）。

生产逻辑在 ``aipd_os.state``（StateService）。本文件仅做两层事：
  1) 把 MCP 工具语义映射到 StateService（默认租户）；
  2) 仅在已安装 ``mcp`` 时才注册 FastMCP 工具并运行 —— 未安装 mcp 时
     本模块仍可安全导入（不会因 import 失败而崩溃）。

跨对话持久化、认证、多租户、加密、备份、审计、健康检查等已由
``aipd_os.state`` 提供。运行前可用环境变量配置：
  AIPD_DB_DIR / AIPD_ENCRYPTION_KEY / AIPD_SECRET / AIPD_RETENTION_DAYS
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aipd_os.state.server import StateService  # noqa: E402

DEFAULT_TENANT = os.environ.get("AIPD_DEFAULT_TENANT", "default")
DB_PATH = os.environ.get("AIPD_DB_DIR", str(Path.home() / ".aipd-projects" / "state.db"))

_service = StateService(
    DB_PATH,
    encryption_key=os.environ.get("AIPD_ENCRYPTION_KEY", ""),
    secret=os.environ.get("AIPD_SECRET", "change-me-secret"),
    retention_days=int(os.environ.get("AIPD_RETENTION_DAYS", "90")),
)


# ---- 工具语义（与旧 server 一致，底层调用 StateService） ----
def init_project(project_id: str, name: str, goal: str) -> str:
    return json.dumps(_service.init_project(DEFAULT_TENANT, project_id, name, goal), ensure_ascii=False)


def project_summary(project_id: str) -> str:
    return json.dumps(_service.project_summary(DEFAULT_TENANT, project_id), ensure_ascii=False)


def add_fact(project_id: str, key: str, value_json: str, status: str,
             unit: str = "", source: str = "", confidence: float = 0.5) -> str:
    value = json.loads(value_json)
    return _service.add_fact(DEFAULT_TENANT, project_id, key, value, status,
                             unit=unit or None, source=source or None, confidence=confidence)


def propose_decision(project_id: str, topic: str, recommendation: str,
                     options_json: str, trigger: str = "") -> str:
    return _service.propose_decision(DEFAULT_TENANT, project_id, topic, recommendation,
                                     json.loads(options_json), trigger or None)


def resolve_decision(project_id: str, decision_id: str, choice: str, comment: str = "") -> str:
    return _service.resolve_decision(DEFAULT_TENANT, project_id, decision_id, choice, comment or None)


def export_checkpoint(project_id: str) -> str:
    return json.dumps(_service.export_checkpoint(DEFAULT_TENANT, project_id), ensure_ascii=False)


# ---- 仅在已安装 mcp 时注册 FastMCP 工具 ----
try:  # pragma: no cover - 取决于运行环境是否安装 mcp
    from mcp.server.fastmcp import FastMCP  # type: ignore

    mcp = FastMCP("aipd-state")

    @mcp.tool()
    def init_project(project_id: str, name: str, goal: str) -> str:  # noqa: F811
        return json.dumps(_service.init_project(DEFAULT_TENANT, project_id, name, goal), ensure_ascii=False)

    @mcp.tool()
    def project_summary(project_id: str) -> str:  # noqa: F811
        return json.dumps(_service.project_summary(DEFAULT_TENANT, project_id), ensure_ascii=False)

    @mcp.tool()
    def add_fact(project_id: str, key: str, value_json: str, status: str,  # noqa: F811
                 unit: str = "", source: str = "", confidence: float = 0.5) -> str:
        value = json.loads(value_json)
        return _service.add_fact(DEFAULT_TENANT, project_id, key, value, status,
                                 unit=unit or None, source=source or None, confidence=confidence)

    @mcp.tool()
    def propose_decision(project_id: str, topic: str, recommendation: str,  # noqa: F811
                         options_json: str, trigger: str = "") -> str:
        return _service.propose_decision(DEFAULT_TENANT, project_id, topic, recommendation,
                                         json.loads(options_json), trigger or None)

    @mcp.tool()
    def resolve_decision(project_id: str, decision_id: str, choice: str, comment: str = "") -> str:  # noqa: F811
        return _service.resolve_decision(DEFAULT_TENANT, project_id, decision_id, choice, comment or None)

    @mcp.tool()
    def export_checkpoint(project_id: str) -> str:  # noqa: F811
        return json.dumps(_service.export_checkpoint(DEFAULT_TENANT, project_id), ensure_ascii=False)

    _MCP_AVAILABLE = True
except Exception:  # pragma: no cover - mcp 未安装时的安全回退
    mcp = None
    _MCP_AVAILABLE = False


if __name__ == "__main__":
    if mcp is not None:
        mcp.run()
    else:
        raise SystemExit("mcp is not installed; cannot run the MCP transport. "
                         "Install `mcp` or use the built-in HTTP transport "
                         "(`python -m aipd_os.state.server --mode server`).")
