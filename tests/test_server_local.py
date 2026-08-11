"""StateService 本地模式：初始化/决策/检查点导出与摘要。"""
from __future__ import annotations

import json
import threading
from http.client import HTTPConnection

from aipd_os.state.server import StateService, _RpcHandler


def test_local_full_flow(tmp_path):
    svc = StateService(str(tmp_path / "state.db"), encryption_key="k", secret="s")

    summary = svc.init_project("default", "p1", "AIPD pilot", "build state service")
    assert summary["project"]["name"] == "AIPD pilot"

    did = svc.propose_decision("default", "p1", "transport", "use HTTP", ["HTTP", "MCP"])
    assert svc.project_summary("default", "p1")["project"]["status"] == "awaiting_owner_decision"

    svc.resolve_decision("default", "p1", did, "HTTP", "stdlib only")
    assert svc.project_summary("default", "p1")["project"]["status"] == "active"

    export = svc.export_checkpoint("default", "p1")
    assert export["project"]["project_id"] == "p1"
    assert [d["decision_id"] for d in export["decisions"]] == [did]
    assert export["decisions"][0]["choice"] == "HTTP"


def test_call_dispatch(tmp_path):
    svc = StateService(str(tmp_path / "state.db"))
    svc.init_project("default", "p1", "P1", "goal")
    out = svc.call("project_summary", tenant_id="default", project_id="p1")
    assert out["project"]["project_id"] == "p1"


def test_resume_and_backup(tmp_path):
    svc = StateService(str(tmp_path / "state.db"))
    svc.init_project("default", "p1", "P1", "goal")
    svc.save_checkpoint("default", "p1", {"note": "started"})
    r = svc.resume_summary("default", "p1")
    assert r["phase"] == "G0"
    path = svc.create_backup()
    assert path
    assert len(svc.list_backups()["backups"]) == 1


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


def test_http_transport_requires_auth(tmp_path):
    svc = StateService(str(tmp_path / "state.db"), secret="s")
    svc.init_project("default", "p1", "P1", "goal")
    httpd, port = _start_server(svc)
    try:
        # 1) 无令牌：必须 401
        status, body = _rpc(port, {"method": "project_summary",
                                   "params": {"tenant_id": "default", "project_id": "p1"}})
        assert status == 401, body
        # 2) 无效令牌：必须 401
        status, body = _rpc(port, {"user": "u1", "token": "garbage",
                                   "method": "project_summary",
                                   "params": {"tenant_id": "default", "project_id": "p1"}})
        assert status == 401, body
        # 3) 有效令牌：认证通过且注入 actor，需项目授权
        token = svc.auth_register("u1", "default", "alice", "pw", project_id="p1")
        status, body = _rpc(port, {"user": "u1", "token": token,
                                   "method": "project_summary",
                                   "params": {"tenant_id": "default", "project_id": "p1"}})
        assert status == 200, body
        assert body["result"]["project"]["project_id"] == "p1"
        # 4) 有效令牌但无项目授权：仍被拒绝（授权生效 → 403 Forbidden）
        status, body = _rpc(port, {"user": "u1", "token": token,
                                   "method": "project_summary",
                                   "params": {"tenant_id": "default", "project_id": "other"}})
        assert status == 403, body
        assert "has no access" in body["error"]
    finally:
        httpd.shutdown()
        httpd.server_close()
