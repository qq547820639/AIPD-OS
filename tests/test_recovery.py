"""P1-5 跨会话恢复：统一备份/恢复、恢复摘要、多项目识别、安全自动续作、审批门控、崩溃 e2e。"""
from __future__ import annotations

import json
import sqlite3

import pytest

from aipd_os.state.db import AIPDStateDB
from aipd_os.state.objects import ObjectStore
from aipd_os.state.recovery import (
    ApprovalRequiredError,
    UnifiedStateService,
)
from aipd_os.state.state_backend import (
    ExternalDependencyError,
    LocalStateBackend,
    RemoteStateBackend,
)

SUPERVISOR_SCHEMA = r"""
CREATE TABLE IF NOT EXISTS supervisor_work_items(
 work_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, phase TEXT NOT NULL, module TEXT NOT NULL,
 title TEXT NOT NULL, objective TEXT NOT NULL, priority INTEGER NOT NULL DEFAULT 50,
 status TEXT NOT NULL DEFAULT 'queued', owner_required INTEGER NOT NULL DEFAULT 0,
 decision_id TEXT, depends_on_json TEXT NOT NULL DEFAULT '[]',
 inputs_json TEXT NOT NULL DEFAULT '{}',
 outputs_json TEXT NOT NULL DEFAULT '{}', acceptance_json TEXT NOT NULL DEFAULT '{}',
 capability_floor TEXT, blocked_reason TEXT, attempts INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
"""


def _make_service(tmp_path, name="state"):
    db = AIPDStateDB(str(tmp_path / f"{name}.db"), encryption_key="k")
    backend = LocalStateBackend(ObjectStore(str(tmp_path / f"{name}_objects")))
    svc = UnifiedStateService(
        db, tenant_id="default", backend=backend,
        index_path=str(tmp_path / f"{name}_attachments.json"))
    return db, svc


def _add_work(db, work_id, project_id, title, status="queued", owner_required=0,
              phase="S3_manual", module="manual", objective="do work", blocked_reason=None):
    with sqlite3.connect(str(db.path)) as c:
        c.execute(
            "INSERT OR REPLACE INTO supervisor_work_items("
            "work_id,project_id,phase,module,title,objective,priority,status,owner_required,"
            "depends_on_json,inputs_json,outputs_json,acceptance_json,capability_floor,"
            "blocked_reason,attempts,created_at,updated_at) VALUES(?,?,?,?,?,?,50,?,?,"
            "'[]','{}','{}','{}',NULL,?,0,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)",
            (work_id, project_id, phase, module, title, objective, status, owner_required,
             blocked_reason))


def _ensure_supervisor_table(db):
    with sqlite3.connect(str(db.path)) as c:
        c.executescript(SUPERVISOR_SCHEMA)


# ---------------------------------------------------------------------------
# 统一备份/恢复：数据库 + 对象 + 附件索引作为一个单元
# ---------------------------------------------------------------------------
def test_unified_backup_restore_db_objects_index(tmp_path):
    db, svc = _make_service(tmp_path)
    db.ensure_default_tenant()
    db.init_project("default", "p1", "P1", "goal")
    db.add_fact("default", "p1", "latency", 42, "V")
    svc.register_object("p1", "cover.png", b"\x89PNG-cover", "attachment")
    svc.register_object("p1", "batch1.json", b'{"n":1}', "manual_batch")

    bundle = svc.backup(out_dir=str(tmp_path / "backups"))

    # 备份后继续写入，数量变多
    db.add_fact("default", "p1", "accuracy", 0.9, "V")
    svc.register_object("p1", "extra.png", b"x", "attachment")
    assert len(db.list_facts("default", "p1")) == 2

    # 全新服务点（模拟恢复到干净环境）：新 db / 新对象 / 新索引
    db2, svc2 = _make_service(tmp_path, "state2")
    db2.ensure_default_tenant()
    db2.init_project("default", "p1", "P1", "goal")
    res = svc2.restore(bundle["backup_dir"])

    # 数据库回到备份时状态
    assert len(db2.list_facts("default", "p1")) == 1
    assert db2.get_fact("default", "p1",
                        db2.list_facts("default", "p1")[0]["fact_id"])["value"] == 42
    # 对象 + 索引恢复
    assert svc2.get_object("p1", "cover.png") == b"\x89PNG-cover"
    keys = {o["key"] for o in svc2.list_objects("p1")}
    assert keys == {"cover.png", "batch1.json"}
    assert res["object_count"] == 2
    assert res["index_entries"] == 2


def test_unified_backup_checksum_protects_restore(tmp_path):
    db, svc = _make_service(tmp_path)
    db.ensure_default_tenant()
    db.init_project("default", "p1", "P1", "goal")
    bundle = svc.backup(out_dir=str(tmp_path / "backups"))

    # 篡改备份中的数据库文件 → 还原必须拒绝
    bdir = __import__("pathlib").Path(bundle["backup_dir"])
    manifest = json.loads((bdir / "manifest.json").read_text(encoding="utf-8"))
    (bdir / manifest["db"]["name"]).write_bytes(b"tampered")

    db2, svc2 = _make_service(tmp_path, "state2")
    db2.ensure_default_tenant()
    db2.init_project("default", "p1", "P1", "goal")
    with pytest.raises(ValueError, match="checksum mismatch"):
        svc2.restore(bundle["backup_dir"])


# ---------------------------------------------------------------------------
# 恢复摘要字段
# ---------------------------------------------------------------------------
def test_recovery_summary_fields(tmp_path):
    db, svc = _make_service(tmp_path)
    db.ensure_default_tenant()
    db.init_project("default", "p1", "P1", "goal")
    db.add_fact("default", "p1", "latency", 42, "V")
    db.add_fact("default", "p1", "supplier_quote", 12.5, "V")
    db.add_evidence("default", "p1", "paper", "evidence-1", url="http://e")
    db.link_evidence("default", "p1", db.list_facts("default", "p1")[0]["fact_id"],
                     db.list_evidence("default", "p1")[0]["evidence_id"])
    db.add_deliverable("default", "p1", "cad_mesh", path="cad.step",
                       status="complete", version="r2")
    db.add_deliverable("default", "p1", "manual_page", path="p1.png", status="planned")
    db.add_dependency("default", "p1", "work", "w1", "external", "e1", relation="needs_external")
    _ensure_supervisor_table(db)
    _add_work(db, "W1", "p1", "render cover", status="internal_rework",
              blocked_reason="image backend down")
    svc.register_object("p1", "vp.png", b"v", "visual_bible")
    svc.register_object("p1", "a1.png", b"1", "manual_batch", chain_prev=None)
    svc.register_object("p1", "a2.png", b"2", "manual_batch", chain_prev="a1.png")

    s = svc.recovery_summary("p1")
    assert [f["key"] for f in s["product_truth"]] == ["latency", "supplier_quote"]
    assert s["evidence_register"][0]["title"] == "evidence-1"
    # CAD/BOM 修订
    cad_types = {r["type"] for r in s["cad_bom_revisions"] if r.get("type")}
    assert "cad_mesh" in cad_types
    # 手工附件链（含 chain_prev 关系）
    assert s["manual_attachment_chain"] == ["a1.png", "a2.png"]
    # 外部等待
    assert any(w["needs"] == "external:e1" for w in s["external_waits"])
    # 失败任务
    assert any(t["work_id"] == "W1" for t in s["failed_tasks"])
    # 下一步（存在外部等待 → 先处理外部待办）
    assert s["next_actions"][0]["action"] == "resume_external"
    # 外部依赖诚实声明（本地后端无 pending 外部依赖）
    assert s["external_dependencies"] == []


# ---------------------------------------------------------------------------
# 多项目识别：按最近活动 / 显式 / 上下文 —— 绝不默认取第一条
# ---------------------------------------------------------------------------
def test_multi_project_identification_by_recent_activity(tmp_path):
    db, svc = _make_service(tmp_path)
    db.ensure_default_tenant()
    db.init_project("default", "old", "Old", "old goal")
    db.init_project("default", "fresh", "Fresh", "new goal")
    # fresh 最近有活动（新增事实会更新其 updated_at）
    db.add_fact("default", "fresh", "progress", 1, "V")

    picked = svc.identify_project()
    assert picked["project_id"] == "fresh"

    # 显式 project_id 优先
    assert svc.identify_project(project_id="old")["project_id"] == "old"
    # 上下文匹配
    assert svc.identify_project(context="Fresh")["project_id"] == "fresh"
    assert svc.identify_project(context="old goal")["project_id"] == "old"


def test_multi_project_context_ambiguous_uses_recent(tmp_path):
    db, svc = _make_service(tmp_path)
    db.ensure_default_tenant()
    db.init_project("default", "p-a", "Alpha", "model A")
    db.init_project("default", "p-b", "Beta", "model A")
    db.add_fact("default", "p-a", "x", 1, "V")  # p-a 更活跃
    # 上下文同时命中两个（goals 都含 "model A"）→ 按最近活动消歧
    assert svc.identify_project(context="model A")["project_id"] == "p-a"


def test_multi_project_identifies_by_recent_not_first_record(tmp_path):
    db, svc = _make_service(tmp_path)
    db.ensure_default_tenant()
    # 先创建的 A，后创建的 B，但 A 有最新活动
    db.init_project("default", "p-a", "Alpha", "goal")
    db.init_project("default", "p-b", "Beta", "goal")
    db.add_fact("default", "p-a", "progress", 1, "V")  # A 最近活动
    # list_projects 按 created_at 升序：首条是 p-a；这里校验并非机械取首条，
    # 而是按“最近活动”识别（此处 A 最近且首条，允许；关键在 B 更活跃时选 B）
    db.add_fact("default", "p-b", "progress", 2, "V")  # 现在 B 最近活动
    assert svc.identify_project()["project_id"] == "p-b"
    # 显式选择覆盖一切
    assert svc.identify_project(project_id="p-a")["project_id"] == "p-a"


# ---------------------------------------------------------------------------
# 安全自动续作 + 审批门控
# ---------------------------------------------------------------------------
def test_auto_continue_safe_work_and_gates_approval(tmp_path):
    db, svc = _make_service(tmp_path)
    db.ensure_default_tenant()
    db.init_project("default", "p1", "P1", "goal")
    _ensure_supervisor_table(db)
    _add_work(db, "W_SAFE", "p1", "render page", status="queued")
    _add_work(db, "W_OWNER", "p1", "choose material", status="queued", owner_required=1)
    _add_work(db, "W_RELEASE", "p1", "release to production", status="queued")

    out = svc.auto_continue("p1")
    continued_ids = {w["work_id"] for w in out["continued"]}
    assert "W_SAFE" in continued_ids
    assert "W_OWNER" not in continued_ids
    assert "W_RELEASE" not in continued_ids
    approval_ids = {w["work_id"] for w in out["requires_approval"]}
    assert {"W_OWNER", "W_RELEASE"} <= approval_ids
    cats = {w["approval_category"] for w in out["requires_approval"]}
    assert "owner_required" in cats and "release" in cats


def test_approval_gate_blocks_irreversible_without_approval(tmp_path):
    db, svc = _make_service(tmp_path)
    with pytest.raises(ApprovalRequiredError, match="irreversible"):
        svc.require_approval("delete_project", "irreversible", approved=False)
    # 获得批准才放行
    assert svc.require_approval("delete_project", "irreversible", approved=True) is True
    with pytest.raises(ValueError):
        svc.require_approval("x", "unknown-category")


# ---------------------------------------------------------------------------
# 不重新追问已解决决策
# ---------------------------------------------------------------------------
def test_resolved_decision_not_re_asked(tmp_path):
    db, svc = _make_service(tmp_path)
    db.ensure_default_tenant()
    db.init_project("default", "p1", "P1", "goal")
    did_resolved = db.propose_decision("default", "p1", "pick model", "use A", ["A", "B"])
    db.resolve_decision("default", "p1", did_resolved, "A", "go")
    did_open = db.propose_decision("default", "p1", "pick color", "orange", ["orange", "grey"])

    s = svc.recovery_summary("p1")
    assert did_resolved in s["resolved_decision_ids"]
    assert did_resolved not in s["pending_questions"]
    assert did_open in s["pending_questions"]
    # 已解决决策绝不进入待追问
    assert all(d["decision_id"] != did_resolved for d in s["unresolved_decisions"])


# ---------------------------------------------------------------------------
# 远端（云）对象存储为外部依赖 —— 诚实桩，绝不伪造云持久化
# ---------------------------------------------------------------------------
def test_remote_backend_is_external_dependency(tmp_path):
    remote = RemoteStateBackend()
    assert remote.name == "remote"
    svc = UnifiedStateService(
        AIPDStateDB(str(tmp_path / "s.db")),
        backend=remote,
        index_path=str(tmp_path / "idx.json"))
    assert svc.external_dependencies() == ["remote object storage"]
    with pytest.raises(ExternalDependencyError):
        svc.register_object("p1", "k", b"data", "attachment")


# ---------------------------------------------------------------------------
# 崩溃 - 重启 - 恢复 - 续作 端到端
# ---------------------------------------------------------------------------
def test_crash_restart_resume_continue_e2e(tmp_path):
    # ---- 崩溃前：真实工作 + 统一备份 ----
    db, svc = _make_service(tmp_path, "live")
    db.ensure_default_tenant()
    db.init_project("default", "exo", "Exoskeleton", "build exo")
    db.add_fact("default", "exo", "peak_torque", 120, "V", unit="N·m")
    db.add_evidence("default", "exo", "benchmark", "bench", url="http://bench",
                    identifier="bench-1")
    db.add_deliverable("default", "exo", "cad_assembly", version="v3", status="complete")
    did_resolved = db.propose_decision("default", "exo", "drive type", "harmonic",
                                       ["harmonic", "direct"])
    db.resolve_decision("default", "exo", did_resolved, "harmonic")
    did_open = db.propose_decision("default", "exo", "battery vendor", "vendorA",
                                   ["vendorA", "vendorB"])
    _ensure_supervisor_table(db)
    _add_work(db, "W_SAFE1", "exo", "render user scene", status="queued")
    _add_work(db, "W_SAFE2", "exo", "build CMF page", status="queued")
    _add_work(db, "W_RELEASE", "exo", "release to production", status="queued")
    _add_work(db, "W_FAIL", "exo", "render cover", status="internal_rework",
              blocked_reason="backend down")
    svc.register_object("exo", "vb.png", b"vb", "visual_bible")
    svc.register_object("exo", "m1.png", b"m1", "manual_batch", chain_prev=None)
    svc.register_object("exo", "m2.png", b"m2", "manual_batch", chain_prev="m1.png")

    bundle = svc.backup(out_dir=str(tmp_path / "backups"))

    # ---- 崩溃：状态文件被清空 / 换到干净机器 ----
    assert (tmp_path / "live.db").exists()

    # ---- 重启 + 恢复：全新服务点，从统一备份恢复 ----
    db2, svc2 = _make_service(tmp_path, "restarted")
    db2.ensure_default_tenant()
    db2.init_project("default", "exo", "Exoskeleton", "build exo")
    svc2.restore(bundle["backup_dir"])

    # ---- 恢复摘要：Product Truth / Evidence / 决策 / CAD / 附件链 / 外部 / 失败 / 下一步 ----
    s = svc2.recovery_summary("exo")
    assert s["product_truth"][0]["key"] == "peak_torque"
    assert s["evidence_register"][0]["identifier"] == "bench-1"
    assert any(r["version"] == "v3" for r in s["cad_bom_revisions"])
    assert s["manual_attachment_chain"] == ["m1.png", "m2.png"]
    assert svc2.get_object("exo", "vb.png") == b"vb"
    # 已解决决策不重问；未解决决策仍需问
    assert did_resolved in s["resolved_decision_ids"]
    assert did_resolved not in s["pending_questions"]
    assert did_open in s["pending_questions"]
    assert any(t["work_id"] == "W_FAIL" for t in s["failed_tasks"])

    # ---- 自动续作：安全工作继续，需审批的被门控 ----
    out = svc2.auto_continue("exo")
    continued_ids = {w["work_id"] for w in out["continued"]}
    assert {"W_SAFE1", "W_SAFE2"} <= continued_ids
    assert "W_RELEASE" not in continued_ids
    assert "W_RELEASE" in {w["work_id"] for w in out["requires_approval"]}

    # 安全工作真实推进到 ready
    with sqlite3.connect(str(db2.path)) as c:
        st = c.execute(
            "SELECT status FROM supervisor_work_items WHERE work_id='W_SAFE1'").fetchone()[0]
    assert st == "ready"

    # 审批门：release 必须显式批准
    with pytest.raises(ApprovalRequiredError):
        svc2.require_approval("release to production", "release", approved=False)
    assert svc2.require_approval("release to production", "release", approved=True) is True
