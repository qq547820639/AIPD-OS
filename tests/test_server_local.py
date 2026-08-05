"""StateService 本地模式：初始化/决策/检查点导出与摘要。"""
from __future__ import annotations

from aipd_os.state.server import StateService


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
