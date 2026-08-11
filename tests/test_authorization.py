"""Change Set 1 授权边界测试（P0-1 / P0-2 / P0-3）。

覆盖：
- 租户隔离：tenant A 用户不能读 tenant B 项目（get_project / list_facts）；
- 项目隔离：project A 用户不能读/写 project B（add_fact / add_evidence /
  add_risk / add_deliverable / object_put 全部拒绝）；
- grant_access 仅限租户管理员；普通成员被拒；
- create_backup / restore_backup 仅限租户管理员；
- 对象存储隔离：A 不能 object_get B 的对象；
- HTTP 公共引导：无 token 可调 auth_login / auth_register；无 token 调其他
  RPC 仍返回 401；
- audit / list_audit_events RPC 可调用（不再被实例属性遮蔽）；
- 注册用户（未指定 project）不自动获得任意项目访问；init_project(actor=...)
  后创建者可访问。
"""
from __future__ import annotations

import base64
import json
import threading
from http.client import HTTPConnection

import pytest

from aipd_os.state.auth import AuthError
from aipd_os.state.server import StateService, _RpcHandler


def _make_svc(tmp_path, **kwargs):
    return StateService(str(tmp_path / "state.db"), encryption_key="k",
                        secret="test-secret", **kwargs)


def _register(svc, user_id, username, tenant="default", project=None):
    """注册用户并返回令牌（project 显式时授予该项目访问权）。"""
    return svc.auth_register(user_id, tenant, username, "pw", project_id=project)


def _start_server(svc):
    import http.server

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _RpcHandler)
    _RpcHandler.service = svc
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd, port


def _rpc(port, payload):
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("POST", "/rpc", body=json.dumps(payload),
                 headers={"Content-Type": "application/json"})
    resp = conn.getresponse()
    body = json.loads(resp.read().decode("utf-8"))
    conn.close()
    return resp.status, body


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


# ---------------------------------------------------------------------------
# 1) 租户隔离：tenant A 用户不能读取 tenant B 项目
# ---------------------------------------------------------------------------
def test_tenant_isolation_get_project_and_list_facts(tmp_path):
    svc = _make_svc(tmp_path)
    svc.init_project("tenantA", "projA", "A", "goal-a")
    svc.init_project("tenantB", "projB", "B", "goal-b")
    token_a = _register(svc, "ua", "alice", tenant="tenantA")

    httpd, port = _start_server(svc)
    try:
        status, body = _rpc(port, {"user": "ua", "token": token_a,
                                   "method": "get_project",
                                   "params": {"tenant_id": "tenantB",
                                              "project_id": "projB"}})
        assert status == 403, body
        assert "error" in body and "result" not in body

        status, body = _rpc(port, {"user": "ua", "token": token_a,
                                   "method": "list_facts",
                                   "params": {"tenant_id": "tenantB",
                                              "project_id": "projB"}})
        assert status == 403, body
        assert "error" in body and "result" not in body
    finally:
        httpd.shutdown()
        httpd.server_close()


# ---------------------------------------------------------------------------
# 2) 项目隔离：project A 用户不能读/写 project B
# ---------------------------------------------------------------------------
def test_project_isolation_read_write(tmp_path):
    svc = _make_svc(tmp_path)
    svc.init_project("default", "pA", "A", "goal-a")
    svc.init_project("default", "pB", "B", "goal-b")
    token = _register(svc, "u1", "alice", project="pA")  # 仅 pA 成员

    httpd, port = _start_server(svc)
    try:
        # 读 pB → 拒绝
        status, body = _rpc(port, {"user": "u1", "token": token,
                                   "method": "get_project",
                                   "params": {"tenant_id": "default",
                                              "project_id": "pB"}})
        assert status == 403 and "error" in body and "result" not in body

        # 写 pB：add_fact / add_evidence / add_risk / add_deliverable 全部拒绝
        writes = [
            ("add_fact", {"tenant_id": "default", "project_id": "pB",
                          "key": "k", "value": 1, "status": "V"}),
            ("add_evidence", {"tenant_id": "default", "project_id": "pB",
                              "kind": "research", "title": "t"}),
            ("add_risk", {"tenant_id": "default", "project_id": "pB",
                          "title": "r"}),
            ("add_deliverable", {"tenant_id": "default", "project_id": "pB",
                                 "dtype": "doc"}),
        ]
        for method, params in writes:
            status, body = _rpc(port, {"user": "u1", "token": token,
                                       "method": method, "params": params})
            assert status == 403, (method, body)
            assert "error" in body and "result" not in body, method

        # object_put 到 pB → 拒绝
        status, body = _rpc(port, {"user": "u1", "token": token,
                                   "method": "object_put",
                                   "params": {"project_id": "pB", "key": "k",
                                              "data_b64": _b64(b"x")}})
        assert status == 403 and "result" not in body

        # 同项目写 pA → 成功
        status, body = _rpc(port, {"user": "u1", "token": token,
                                   "method": "add_fact",
                                   "params": {"tenant_id": "default",
                                              "project_id": "pA",
                                              "key": "k", "value": 1,
                                              "status": "V"}})
        assert status == 200 and body["result"], body
    finally:
        httpd.shutdown()
        httpd.server_close()


# ---------------------------------------------------------------------------
# 3) grant_access 仅限租户管理员
# ---------------------------------------------------------------------------
def test_grant_access_requires_tenant_admin(tmp_path):
    svc = _make_svc(tmp_path)
    svc.init_project("default", "p1", "P1", "goal")
    _register(svc, "u_member", "member", project="p1")
    _register(svc, "u_admin", "admin")
    _register(svc, "u_other", "other")
    # 内部调用（actor=None）授予 admin 租户通配 → 成为管理员
    svc.grant_access("u_admin", "default", None)

    # 普通成员 grant_access → AuthError
    with pytest.raises(AuthError):
        svc.grant_access("u_other", "default", "p1", actor="u_member")
    # 管理员 grant_access → 成功
    svc.grant_access("u_other", "default", "p1", actor="u_admin")
    svc.auth.require_project_access("u_other", "default", "p1")


# ---------------------------------------------------------------------------
# 4) 备份类操作仅限租户管理员
# ---------------------------------------------------------------------------
def test_backup_requires_tenant_admin(tmp_path):
    svc = _make_svc(tmp_path)
    svc.init_project("default", "p1", "P1", "goal")
    _register(svc, "u_member", "member", project="p1")
    _register(svc, "u_admin", "admin")
    svc.grant_access("u_admin", "default", None)

    with pytest.raises(AuthError):
        svc.create_backup(actor="u_member")
    with pytest.raises(AuthError):
        svc.list_backups(actor="u_member")
    with pytest.raises(AuthError):
        svc.retention_prune(actor="u_member")

    path = svc.create_backup(actor="u_admin")  # admin 成功
    assert path
    assert len(svc.list_backups(actor="u_admin")["backups"]) == 1

    # restore_backup：普通成员被拒（在触及备份目录前即拒绝）；admin 成功
    with pytest.raises(AuthError):
        svc.restore_backup(path, actor="u_member")
    restored = svc.restore_backup(path, target=str(tmp_path / "restored.db"),
                                  actor="u_admin")
    assert restored


# ---------------------------------------------------------------------------
# 5) 对象存储隔离：A 不能 object_get B 的对象
# ---------------------------------------------------------------------------
def test_object_store_isolation(tmp_path):
    svc = _make_svc(tmp_path)
    svc.init_project("default", "pA", "A", "goal-a")
    svc.init_project("default", "pB", "B", "goal-b")
    token_a = _register(svc, "ua", "alice", project="pA")
    # 内部放一个对象到 pB
    svc.object_put("pB", "secret.txt", _b64(b"secret"))

    httpd, port = _start_server(svc)
    try:
        # A 不能读 B 的对象
        status, body = _rpc(port, {"user": "ua", "token": token_a,
                                   "method": "object_get_b64",
                                   "params": {"project_id": "pB",
                                              "key": "secret.txt"}})
        assert status == 403 and "result" not in body

        # A 写自己的对象并读回 → 成功
        status, body = _rpc(port, {"user": "ua", "token": token_a,
                                   "method": "object_put",
                                   "params": {"project_id": "pA", "key": "mine.txt",
                                              "data_b64": _b64(b"hi")}})
        assert status == 200, body
        status, body = _rpc(port, {"user": "ua", "token": token_a,
                                   "method": "object_get_b64",
                                   "params": {"project_id": "pA",
                                              "key": "mine.txt"}})
        assert status == 200 and body["result"] == _b64(b"hi"), body
    finally:
        httpd.shutdown()
        httpd.server_close()


# ---------------------------------------------------------------------------
# 6) HTTP 公共引导 + 未认证 401
# ---------------------------------------------------------------------------
def test_http_public_bootstrap_and_401(tmp_path):
    svc = _make_svc(tmp_path)
    svc.init_project("default", "p1", "P1", "goal")

    httpd, port = _start_server(svc)
    try:
        # 无 token 注册 → 成功（引导循环修复）
        status, body = _rpc(port, {"method": "auth_register",
                                   "params": {"user_id": "u1",
                                              "tenant_id": "default",
                                              "username": "alice",
                                              "password": "pw"}})
        assert status == 200, body
        token = body["result"]
        assert token

        # 无 token 登录 → 成功
        status, body = _rpc(port, {"method": "auth_login",
                                   "params": {"username": "alice",
                                              "password": "pw"}})
        assert status == 200 and body["result"], body

        # 无 token 调其他 RPC → 401
        status, body = _rpc(port, {"method": "project_summary",
                                   "params": {"tenant_id": "default",
                                              "project_id": "p1"}})
        assert status == 401, body
        # 带 token 但无项目授权 → 授权失败（403）
        status, body = _rpc(port, {"user": "u1", "token": token,
                                   "method": "project_summary",
                                   "params": {"tenant_id": "default",
                                              "project_id": "p1"}})
        assert status == 403, body
        assert "error" in body and "result" not in body
    finally:
        httpd.shutdown()
        httpd.server_close()


# ---------------------------------------------------------------------------
# 7) audit / list_audit_events RPC 可调用（不再被遮蔽）
# ---------------------------------------------------------------------------
def test_audit_rpc_not_shadowed(tmp_path):
    svc = _make_svc(tmp_path)
    svc.init_project("default", "p1", "P1", "goal")
    token_admin = _register(svc, "u_admin", "admin")
    svc.grant_access("u_admin", "default", None)  # 管理员

    httpd, port = _start_server(svc)
    try:
        # audit RPC 可调用且返回 records（P0-3 修复）
        status, body = _rpc(port, {"user": "u_admin", "token": token_admin,
                                   "method": "audit", "params": {}})
        assert status == 200, body
        assert "records" in body["result"]

        # 明确命名别名同样可调用
        status, body = _rpc(port, {"user": "u_admin", "token": token_admin,
                                   "method": "list_audit_events", "params": {}})
        assert status == 200 and "records" in body["result"], body

        # 非管理员访问 audit → 拒绝
        token_member = _register(svc, "u_member", "member", project="p1")
        status, body = _rpc(port, {"user": "u_member", "token": token_member,
                                   "method": "audit", "params": {}})
        assert status == 403 and "error" in body and "result" not in body
    finally:
        httpd.shutdown()
        httpd.server_close()


# ---------------------------------------------------------------------------
# 8) 注册不自动获得项目访问；init_project(actor=...) 创建者可访问
# ---------------------------------------------------------------------------
def test_register_no_implicit_access_and_init_project_grants_creator(tmp_path):
    svc = _make_svc(tmp_path)
    token = _register(svc, "u1", "alice")  # 未指定 project

    httpd, port = _start_server(svc)
    try:
        # 未指定 project 注册 → 不自动获得任意项目访问
        status, body = _rpc(port, {"user": "u1", "token": token,
                                   "method": "get_project",
                                   "params": {"tenant_id": "default",
                                              "project_id": "p1"}})
        assert status == 403 and "result" not in body
        # list_projects 对非管理员只返回自己有权访问的项目（这里应为空）
        status, body = _rpc(port, {"user": "u1", "token": token,
                                   "method": "list_projects",
                                   "params": {"tenant_id": "default"}})
        assert status == 200, body
        assert body["result"]["projects"] == []
    finally:
        httpd.shutdown()
        httpd.server_close()

    # init_project(actor=u1) 后创建者可访问新项目
    svc.init_project("default", "p2", "P2", "goal", actor="u1")
    svc.auth.require_project_access("u1", "default", "p2")
    pids = [p["project_id"] for p in svc.list_projects("default", actor="u1")["projects"]]
    assert pids == ["p2"]


# ---------------------------------------------------------------------------
# 9) list_projects：成员仅见自己项目，管理员可见全部
# ---------------------------------------------------------------------------
def test_list_projects_filtered_for_member_admin_sees_all(tmp_path):
    svc = _make_svc(tmp_path)
    svc.init_project("default", "pA", "A", "goal-a")
    svc.init_project("default", "pB", "B", "goal-b")
    token_member = _register(svc, "u_member", "member", project="pA")
    token_admin = _register(svc, "u_admin", "admin")
    svc.grant_access("u_admin", "default", None)

    httpd, port = _start_server(svc)
    try:
        status, body = _rpc(port, {"user": "u_member", "token": token_member,
                                   "method": "list_projects",
                                   "params": {"tenant_id": "default"}})
        assert status == 200, body
        assert [p["project_id"] for p in body["result"]["projects"]] == ["pA"]

        status, body = _rpc(port, {"user": "u_admin", "token": token_admin,
                                   "method": "list_projects",
                                   "params": {"tenant_id": "default"}})
        assert status == 200, body
        assert {p["project_id"] for p in body["result"]["projects"]} == {"pA", "pB"}
    finally:
        httpd.shutdown()
        httpd.server_close()


# ---------------------------------------------------------------------------
# CS1-FIX：认证 actor 冒充向量（客户端 params 里的 actor 不得覆盖认证身份）
# ---------------------------------------------------------------------------
def test_http_cannot_impersonate_actor_in_params(tmp_path):
    """向量 1：带合法 token 的用户 A 在 params 塞 actor=B → 仍以 A 执行，B 的权限不可借用。"""
    svc = _make_svc(tmp_path)
    svc.init_project("default", "pA", "A", "goal-a")
    svc.init_project("default", "pB", "B", "goal-b")
    token_a = _register(svc, "ua", "alice", project="pA")
    _register(svc, "ub", "bob", project="pB")  # ub 有 pB 权限，但请求用 A 的 token

    httpd, port = _start_server(svc)
    try:
        # 若冒充生效将返回 pB 数据；修复后必须是 403（A 无 pB 权限）
        status, body = _rpc(port, {"user": "ua", "token": token_a,
                                   "method": "get_project",
                                   "params": {"tenant_id": "default",
                                              "project_id": "pB", "actor": "ub"}})
        assert status == 403, body
        assert "result" not in body
        # 反例：A 访问自己有权的 pA → 200（actor 被覆盖为 A 后仍有权限）
        status, body = _rpc(port, {"user": "ua", "token": token_a,
                                   "method": "get_project",
                                   "params": {"tenant_id": "default",
                                              "project_id": "pA", "actor": "ub"}})
        assert status == 200 and body["result"]["project_id"] == "pA", body
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_http_actor_none_cannot_escape_auth(tmp_path):
    """向量 2：params 塞 actor=None → 仍以认证用户执行（不得跳过授权）。"""
    svc = _make_svc(tmp_path)
    svc.init_project("default", "pA", "A", "goal-a")
    svc.init_project("default", "pB", "B", "goal-b")
    token_a = _register(svc, "ua", "alice", project="pA")

    httpd, port = _start_server(svc)
    try:
        status, body = _rpc(port, {"user": "ua", "token": token_a,
                                   "method": "get_project",
                                   "params": {"tenant_id": "default",
                                              "project_id": "pB", "actor": None}})
        assert status == 403 and "result" not in body, body
        status, body = _rpc(port, {"user": "ua", "token": token_a,
                                   "method": "get_project",
                                   "params": {"tenant_id": "default",
                                              "project_id": "pA", "actor": ""}})
        assert status == 200 and body["result"]["project_id"] == "pA", body
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_http_actor_override_admin_grant(tmp_path):
    """向量 3：admin token + params 塞非 admin actor → 仍以 admin 执行（覆盖而非借用）。"""
    svc = _make_svc(tmp_path)
    svc.init_project("default", "p1", "P1", "goal")
    _register(svc, "u_member", "member", project="p1")
    token_admin = _register(svc, "u_admin", "admin")
    _register(svc, "u_new", "newbie")
    svc.grant_access("u_admin", "default", None)  # u_admin 成为租户管理员

    httpd, port = _start_server(svc)
    try:
        # params 塞 actor=u_member（非 admin）→ 修复后仍以认证的 u_admin 执行 → 成功；
        # 若冒充生效（以 u_member 身份）→ 403。
        status, body = _rpc(port, {"user": "u_admin", "token": token_admin,
                                   "method": "grant_access",
                                   "params": {"user_id": "u_new", "tenant_id": "default",
                                              "project_id": "p1", "actor": "u_member"}})
        assert status == 200, body
        svc.auth.require_project_access("u_new", "default", "p1")
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_local_mode_explicit_actor_still_honored(tmp_path):
    """向量 4：本地模式直接调用仍尊重显式 actor（HTTP 注入不适用，行为不变）。"""
    svc = _make_svc(tmp_path)
    svc.init_project("default", "pA", "A", "goal-a")
    _register(svc, "ua", "alice", project="pA")
    # 本地 API 显式 actor 照常生效
    summary = svc.project_summary("default", "pA", actor="ua")
    assert summary["project"]["project_id"] == "pA"
    # 无 actor（内部/系统调用）跳过授权
    summary2 = svc.project_summary("default", "pA")
    assert summary2["project"]["project_id"] == "pA"
