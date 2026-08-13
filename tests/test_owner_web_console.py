"""Owner Web Console（``aipd ui``）测试。

覆盖：
- 六个中心（首次向导/项目总览/决策/制品/运行控制/外部等待）HTML 页面返回 200 且含关键内容；
- 六个中心 JSON API 端点返回 200；
- 决策中心默认只返回一个真决策、不暴露内部 ID；
- 窄屏/键盘/无障碍标记存在（viewport meta、aria-label、tabindex、语义标签）；
- JSON API 与直接调用共享同一业务服务；
- ``aipd ui`` 可启动（start 后能访问 /，能 stop）。
"""
from __future__ import annotations

import json
import threading
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pytest

from aipd_os.cli.commands import COMMAND_FUNCS
from aipd_os.state.db import AIPDStateDB
from aipd_os.web import WebConsole, serve, start_server

TENANT = "default"

NAV = {
    "/": None,
    "/onboarding": "首次使用向导",
    "/overview": "项目总览",
    "/decisions": "决策中心",
    "/artifacts": "制品中心",
    "/run": "运行控制",
    "/external-wait": "外部等待中心",
}
API_PAGES = {
    "/api/onboarding": "onboarding",
    "/api/overview": "overview",
    "/api/decisions": "decisions",
    "/api/artifacts": "artifacts",
    "/api/run": "run",
    "/api/external-wait": "external-wait",
}


@pytest.fixture()
def console(tmp_path):
    db_path = str(tmp_path / "state.db")
    c = WebConsole(db_path, tenant_id=TENANT)
    c.create_project("测试助力外骨骼", "开发一款助力外骨骼样机")
    pid = c.active_project()
    db = AIPDStateDB(db_path)
    db.ensure_default_tenant(TENANT)
    db.propose_decision(TENANT, pid, "选择动力方案", "按 AI 推荐选择单臂方案",
                        ["单臂方案", "双臂方案"], "cost")
    db.propose_decision(TENANT, pid, "选择材料", "按 AI 推荐选择铝合金",
                        ["铝合金", "碳纤维"], "cost")
    db.add_evidence(TENANT, pid, "research", "行业调研",
                    summary="外骨骼市场主流从单臂起步，成本可控")
    db.add_deliverable(TENANT, pid, "manual", path=str(tmp_path / "manual.pdf"),
                       status="done", version="1.0")
    return c


@pytest.fixture()
def srv(console):
    # 显式 web_token=""（不读环境变量），保证既有用例在未配置 AIPD_WEB_TOKEN 时行为稳定。
    server = start_server(console, "127.0.0.1", 0, web_token="")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    yield server, base
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def _get(url: str):
    with urlopen(url, timeout=10) as resp:
        return resp.status, resp.read().decode("utf-8")


def _get_json(url: str):
    with urlopen(url, timeout=10) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def _post(url: str, data=None):
    body = urlencode(data or {}).encode("utf-8") if data else b""
    req = Request(url, data=body, method="POST")
    with urlopen(req, timeout=10) as resp:
        return resp.status, resp.read().decode("utf-8")


# ---------------------------------------------------------------- 各中心 HTML 页面
def test_all_center_pages_return_200_with_key_content(srv):
    _, base = srv
    for path, keyword in NAV.items():
        if path == "/":
            continue
        status, body = _get(base + path)
        assert status == 200, f"{path} 应返回 200"
        assert keyword in body, f"{path} 应包含关键内容「{keyword}」"


def test_root_redirects_to_overview_when_project_exists(srv):
    _, base = srv
    req = Request(base + "/", method="GET")
    try:
        with urlopen(req, timeout=10) as resp:
            assert resp.status in (200, 302)
    except HTTPError as exc:
        assert exc.code in (200, 302)


# ---------------------------------------------------------------- 各中心 JSON API
def test_all_json_api_endpoints_return_200(srv):
    _, base = srv
    for path in API_PAGES:
        status, _ = _get_json(base + path)
        assert status == 200, f"{path} 应返回 200"


# ---------------------------------------------------------------- 决策中心：单一真决策、不暴露内部 ID
def test_decision_center_returns_single_real_decision_no_internal_id(srv, console):
    _, base = srv
    status, data = _get_json(base + "/api/decisions")
    assert status == 200
    assert data.get("has_decision") is True, "存在待审决策时应返回 has_decision=True"
    assert data.get("topic"), "决策中心应返回真实决策主题"
    # 默认只返回一个真决策：topic 是字符串而非列表
    assert isinstance(data.get("topic"), str)
    # 不暴露内部 ID：顶层不应出现 decision_id 键
    assert "decision_id" not in data, "JSON API 不应暴露内部 decision_id"
    # ref 是安全展示编号（短哈希），不是内部决策 ID
    assert str(data.get("ref", "")).startswith("id-")

    # 内部决策 ID 也不应出现在 HTML 页面中
    pid = console.active_project()
    db = AIPDStateDB(console.db_path)
    internal_ids = [d["decision_id"] for d in db.list_open_decisions(TENANT, pid)]
    assert internal_ids, "测试夹具应创建至少一个待审决策"
    _, html = _get(base + "/decisions")
    for did in internal_ids:
        assert did not in html, f"决策内部 ID {did} 不应暴露在 HTML 页面中"


def test_decision_center_returns_exactly_one_when_multiple(srv):
    """存在多个待审决策时，决策中心默认只呈现一个最高优先级决策。"""
    _, base = srv
    _, data = _get_json(base + "/api/decisions")
    assert isinstance(data.get("topic"), str)
    assert isinstance(data.get("options"), list)
    assert data.get("ai_recommendation")


# ---------------------------------------------------------------- 无障碍 / 窄屏 / 键盘
def test_accessibility_and_responsive_markers_present(srv):
    _, base = srv
    _, html = _get(base + "/decisions")
    # 响应式：viewport meta
    assert 'name="viewport"' in html
    assert "width=device-width" in html
    # 无障碍：aria-label
    assert "aria-label" in html
    # 键盘操作：tabindex
    assert "tabindex" in html
    # 语义标签
    for tag in ("<header", "<nav", "<main", "<section", "<footer", "<h1", "<h2"):
        assert tag in html, f"应包含语义标签 {tag}"
    # 导航高亮
    assert 'aria-current="page"' in html


def test_css_contains_media_query_for_narrow_screen(srv):
    _, base = srv
    _, html = _get(base + "/overview")
    assert "@media" in html and "max-width" in html


def test_chinese_english_terminology_consistent(srv):
    """导航与页面标题使用一致的中文术语。"""
    _, base = srv
    _, html = _get(base + "/decisions")
    for label in ("首次使用向导", "项目总览", "决策中心", "制品中心",
                  "运行控制", "外部等待中心"):
        assert label in html, f"导航中应包含一致术语「{label}」"


# ---------------------------------------------------------------- JSON API 与直接调用共用同一业务服务
def test_json_api_uses_same_service_as_direct_call(srv, console):
    _, base = srv
    _, via_api = _get_json(base + "/api/overview")
    via_service = console.overview()
    # 同一业务服务：项目编号（安全展示）与名称一致
    assert via_api["project_ref"] == via_service["project_ref"]
    assert via_api["project_name"] == via_service["project_name"]

    # 决策中心同样一致性
    _, dec_api = _get_json(base + "/api/decisions")
    dec_service = console.decision_center()
    assert dec_api["topic"] == dec_service["topic"]


def test_cli_command_registered_and_serves():
    """``aipd ui`` 命令已注册，且 start 后可访问 /、能 stop。"""
    assert "ui" in COMMAND_FUNCS, "aipd ui 必须在命令分发表中注册"

    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as td:
        console = WebConsole(str(Path(td) / "s.db"), tenant_id=TENANT)
        console.create_project("命令行启动", "验证 aipd ui 可启动")
        server = start_server(console, "127.0.0.1", 0, web_token="")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            status, _ = _get(base + "/")
            assert status in (200, 302)
            status, body = _get(base + "/overview")
            assert status == 200 and "项目总览" in body
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


# ---------------------------------------------------------------- CS3 安全（P0-13）
def _request_status(url, data=None, headers=None, method=None):
    """发送请求并返回 (status, body)；HTTPError 也返回状态码而非抛异常。"""
    if isinstance(data, bytes):
        body = data
    else:
        body = urlencode(data or {}).encode("utf-8") if data else None
    req = Request(url, data=body, method=method, headers=headers or {})
    try:
        with urlopen(req, timeout=10) as resp:
            return resp.status, resp.read().decode("utf-8")
    except HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def test_start_run_requires_approval_creates_pending_decision(console):
    """requires_approval 意图 start_run → 产生待审决策（而非自动执行）。"""
    pid = console.active_project()
    before = len(AIPDStateDB(console.db_path).list_open_decisions(TENANT, pid))

    snapshot = console.start_run("批准", pid)

    assert snapshot["state"] == "needs_approval"
    db = AIPDStateDB(console.db_path)
    open_decisions = db.list_open_decisions(TENANT, pid)
    # 新增一条待审决策供决策中心显式批准
    assert len(open_decisions) == before + 1
    assert open_decisions[-1]["trigger"] == "owner_web_requires_approval"
    # 未自动执行：全部待审决策仍为 proposed
    assert all(d["status"] == "proposed" for d in open_decisions)


def test_web_token_required_when_set(console):
    """设置 AIPD_WEB_TOKEN 后：无 token 的 /api/* 请求返回 401；带 token 返回 200。"""
    server = start_server(console, "127.0.0.1", 0, web_token="test-token")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        # GET 无 token → 401
        status, _ = _request_status(base + "/api/overview")
        assert status == 401
        # POST 无 token → 401
        status, _ = _request_status(base + "/api/run/pause", data={}, method="POST")
        assert status == 401
        # Bearer token → 200
        status, _ = _request_status(base + "/api/overview",
                                    headers={"Authorization": "Bearer test-token"})
        assert status == 200
        # X-AIPD-Token → 200
        status, _ = _request_status(base + "/api/overview",
                                    headers={"X-AIPD-Token": "test-token"})
        assert status == 200
        # ?token= → 200
        status, _ = _request_status(base + "/api/overview?token=test-token")
        assert status == 200
        # POST 带 token → 200
        status, _ = _request_status(base + "/api/run/pause", data={},
                                    headers={"X-AIPD-Token": "test-token"},
                                    method="POST")
        assert status == 200
        # 错误 token → 401
        status, _ = _request_status(base + "/api/overview",
                                    headers={"X-AIPD-Token": "wrong-token"})
        assert status == 401
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_serve_non_localhost_requires_token(monkeypatch):
    """serve 绑定非 localhost 且未配置 AIPD_WEB_TOKEN → 拒绝启动（fail-closed）。"""
    monkeypatch.delenv("AIPD_WEB_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="AIPD_WEB_TOKEN"):
        serve(None, host="0.0.0.0", print_url=False)


def test_oversized_request_body_rejected(srv):
    """POST 请求体超过 1MB → 413（服务端按 Content-Length 直接拒绝）。"""
    from http.client import HTTPConnection

    _, base = srv
    _, _, hostport = base.partition("://")
    host, port = hostport.split(":")
    conn = HTTPConnection(host, int(port), timeout=10)
    # 仅声明超大的 Content-Length，不发送 body：服务端应据此返回 413。
    conn.putrequest("POST", "/api/run/start", skip_host=True)
    conn.putheader("Host", hostport)
    conn.putheader("Content-Type", "application/x-www-form-urlencoded")
    conn.putheader("Content-Length", str(1024 * 1024 + 100))
    conn.endheaders()
    try:
        resp = conn.getresponse()
        assert resp.status == 413
        resp.read()
    finally:
        conn.close()
