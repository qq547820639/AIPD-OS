"""Task 9：aipd 一键 CLI 与发布包构建器的测试。

直接调用 ``aipd_os.cli.main.main(argv)`` 验证 10 个子命令的关键行为。
所有用到的输出目录都落在 pytest 的 ``tmp_path`` 下，不污染仓库。
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from aipd_os import __version__ as _PKG_VERSION
from aipd_os.cli import main as cli_main
from aipd_os.cli.commands import cmd_doctor

ROOT = Path(__file__).resolve().parent.parent

FULL_CAD_EVIDENCE = {
    "design_intent", "coordinate_system", "overall_dimensions",
    "faceted_brep_mesh", "step_assemblies",
    "native_parametric_brep", "editable_feature_tree", "real_part_features", "step_parts",
    "assembly_constraints", "continuous_rom_clearance", "collision_reports",
    "cae_reports", "load_cases", "strength_stiffness_evidence", "fatigue_plan_or_evidence",
    "dfm_dfa", "tolerance_gdt",
    "drawings", "bom", "inspection_plan", "assembly_instructions", "release_manifest",
    "physical_evidence", "owner_release", "dvt_evidence", "pvt_control_plan",
}


def _init_project(tmp_path, name="外骨骼项目", goal="评估助力系统"):
    db = tmp_path / "state.db"
    rc = cli_main.main([
        "init-project", "--db", str(db), "--project-id", "p1",
        "--name", name, "--goal", goal,
    ])
    assert rc == 0
    return db


def test_init_project_creates_db_and_confirms(tmp_path, capsys):
    db = _init_project(tmp_path)
    out = capsys.readouterr().out
    assert db.exists()
    assert "项目已初始化" in out
    assert "p1" in out
    assert "外骨骼项目" in out


def test_project_summary_chinese_top_level(tmp_path, capsys):
    db = _init_project(tmp_path)
    capsys.readouterr()
    rc = cli_main.main(["project-summary", "--db", str(db)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "当前工作" in out
    assert "里程碑" in out
    # 顶层输出不应包含裸的内部代号（阶段 / 门禁代号）
    assert "S0" not in out
    assert "C4" not in out


def test_run_cad_chain_faceted_capped(tmp_path, capsys):
    manifest = tmp_path / "faceted.json"
    manifest.write_text(json.dumps({
        "runtime": "faceted_brep",
        "evidence": {k: True for k in FULL_CAD_EVIDENCE},
    }), encoding="utf-8")
    rc = cli_main.main(["run-cad-chain", "--manifest", str(manifest), "--target", "C2"])
    out = capsys.readouterr().out
    # faceted_brep 运行时封顶于 C1
    assert "达到 C1" in out
    assert "封顶于 C1" in out
    assert rc != 0  # 目标 C2 未达成


def test_submit_decision_resolves(tmp_path, capsys):
    from aipd_os.state.db import AIPDStateDB
    db = _init_project(tmp_path)
    store = AIPDStateDB(str(db))
    did = store.propose_decision("default", "p1", "单臂还是双臂", "推荐单臂", ["单臂", "双臂"])
    capsys.readouterr()
    rc = cli_main.main([
        "submit-decision", "--db", str(db), "--decision-id", did,
        "--choice", "单臂", "--comment", "性能优先",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    assert "已裁定" in out
    decs = store.list_decisions("default", "p1")
    assert decs[0]["status"] == "resolved"
    assert decs[0]["choice"] == "单臂"


def test_build_release_produces_artifacts(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("AIPD_RELEASE_SIGNING_KEY", "test-signing-key")
    out = tmp_path / "rel"
    rc = cli_main.main(["build-release", "--version", "5.0.0",
                        "--out", str(out), "--no-tests"])
    capsys.readouterr()
    assert rc == 0

    artifact = out / "aipd-os-5.0.0.zip"
    assert artifact.exists()
    assert artifact.stat().st_size > 0
    assert (out / "sha256_manifest.json").exists()
    # 发布清单被更新
    manifest_path = out / "RELEASE_MANIFEST.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["version"] == "5.0.0"
    assert manifest["sha256"]
    assert len(manifest["files"]) > 0
    # 清单被签名
    assert (out / "sha256_manifest.json.sig").exists()


def test_run_evals_fake_produces_report(tmp_path, capsys):
    out = tmp_path / "evals"
    rc = cli_main.main([
        "run-evals", "--evals", str(ROOT / "evals" / "evals.json"),
        "--provider", "fake", "--out", str(out),
    ])
    capsys.readouterr()
    assert rc == 0
    report = out / "eval_reports" / _PKG_VERSION / "report.json"
    assert report.exists()
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["summary"]["passed"] == data["summary"]["total"]

def test_run_until_decision_executes_and_summarizes(tmp_path, capsys, monkeypatch):
    import sys
    from pathlib import Path as _P

    monkeypatch.setenv("AIPD_OUTPUT_DIR", str(tmp_path))
    sys.path.insert(0, str(_P(__file__).resolve().parent.parent / "scripts"))
    from aipd_supervisor import Supervisor  # noqa: E402

    db = _init_project(tmp_path)
    sup = Supervisor(str(db))
    sup.add_work(
        "S1_theory", "research", "t", "o",
        capability_floor="doc.generate",
        inputs={"title": "T", "sections": [{"heading": "H", "body": "b"}]},
    )
    capsys.readouterr()
    rc = cli_main.main(["run", "--project", "p1", "--until-decision", "--db", str(db)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "项目 p1" in out
    assert "停止原因" in out
    assert "完成" in out


def test_run_missing_project_errors(tmp_path, capsys):
    db = _init_project(tmp_path)
    capsys.readouterr()
    rc = cli_main.main(["run", "--project", "nope", "--until-decision", "--db", str(db)])
    out = capsys.readouterr().err
    assert rc != 0
    assert "不存在" in out


# --------------------------------------------------------------------------
# v5.1 新增 16 个一键命令（Task 7）
# --------------------------------------------------------------------------
def test_init_json_returns_ok(tmp_path, capsys):
    db = tmp_path / "state.db"
    rc = cli_main.main([
        "init", "--db", str(db), "--project", "q1",
        "--name", "测试项目", "--goal", "验证初始化", "--json",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)  # 单个 JSON 对象
    assert data["ok"] is True
    assert data["command"] == "init"
    assert data["project_id"] == "q1"


def test_intake_creates_project_deterministic(tmp_path, capsys):
    db = tmp_path / "state.db"
    rc = cli_main.main([
        "intake", "--db", str(db), "--prompt", "做一款外骨骼助力系统",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    assert "已根据需求初始化项目" in out
    # 确定性：相同 prompt 得到相同 project_id
    from aipd_os.state.db import AIPDStateDB
    store = AIPDStateDB(str(db))
    projects = store.list_projects("default")
    assert len(projects) == 1
    assert projects[0]["goal"] == "做一款外骨骼助力系统"


def test_intake_json(tmp_path, capsys):
    db = tmp_path / "state.db"
    rc = cli_main.main([
        "intake", "--db", str(db), "--prompt", "做一款外骨骼", "--json",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)
    assert data["ok"] is True
    assert data["command"] == "intake"


def test_status_json_returns_json(tmp_path, capsys):
    db = _init_project(tmp_path)
    capsys.readouterr()
    rc = cli_main.main(["status", "--db", str(db), "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)
    assert data["ok"] is True
    assert data["command"] == "status"
    assert "project_summary" in data["summary"]


def test_status_project_arg(tmp_path, capsys):
    db = _init_project(tmp_path)
    capsys.readouterr()
    rc = cli_main.main(["status", "--db", str(db), "--project", "p1"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "当前工作" in out


def test_decide_resolves_decision(tmp_path, capsys):
    from aipd_os.state.db import AIPDStateDB
    db = _init_project(tmp_path)
    store = AIPDStateDB(str(db))
    did = store.propose_decision("default", "p1", "单臂还是双臂", "推荐单臂", ["单臂", "双臂"])
    capsys.readouterr()
    rc = cli_main.main([
        "decide", "--db", str(db), "--decision-id", did, "--choice", "单臂",
        "--comment", "性能优先", "--json",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)
    assert data["ok"] is True
    assert data["decision_id"] == did
    decs = store.list_decisions("default", "p1")
    assert decs[0]["status"] == "resolved"
    assert decs[0]["choice"] == "单臂"


def test_manual_plan_runs_on_temp_state(tmp_path, capsys):
    db = _init_project(tmp_path)
    state = tmp_path / "manual.json"
    capsys.readouterr()
    rc = cli_main.main([
        "manual", "plan", "--db", str(db), "--state", str(state),
        "--minimum-pages", "10", "--json",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)
    assert data["ok"] is True
    assert data["page_count"] >= 10
    assert state.exists()


def test_manual_generate_reports_external_pending(tmp_path, capsys):
    db = _init_project(tmp_path)
    state = tmp_path / "manual.json"
    out_dir = tmp_path / "out"
    # 先在无 json 模式跑 plan（内部会初始化状态）
    rc = cli_main.main([
        "manual", "plan", "--db", str(db), "--state", str(state), "--minimum-pages", "10",
    ])
    assert rc == 0
    capsys.readouterr()
    rc = cli_main.main([
        "manual", "generate", "--db", str(db), "--state", str(state),
        "--batch-id", "batch_1", "--prompt", "封面", "--output-dir", str(out_dir),
        "--json",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)
    assert data["ok"] is True
    # 图像后端不可用时应如实报告 external_pending，绝不伪造完成
    assert data["external_pending"], "图像后端不可用必须报告外部待办，不能假装生成"


def test_industrialize_no_data_no_fabricate(tmp_path, capsys):
    db = _init_project(tmp_path)
    capsys.readouterr()
    rc = cli_main.main(["industrialize", "--db", str(db), "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)
    assert data["ok"] is True
    # 未提供报价/实验室数据：不得虚构任何数值
    assert data["official_quotes"] == []
    assert data["quotes_note"], "应如实说明未收到报价数据"
    assert data["analysis"] is None


def test_industrialize_with_quote_and_lab(tmp_path, capsys):
    db = _init_project(tmp_path)
    quote = tmp_path / "quotes.csv"
    quote.write_text(
        "supplier,part,moq,tooling_fee,unit_price,lead_time_days\n"
        "A,电机,100,5000,120,30\n", encoding="utf-8")
    lab = tmp_path / "lab.csv"
    lab.write_text(
        "stage,test_item,sample_id,result,pass_fail,notes\n"
        "dvt,扭矩,S1,0.9,pass,ok\n", encoding="utf-8")
    capsys.readouterr()
    rc = cli_main.main([
        "industrialize", "--db", str(db), "--quote", str(quote),
        "--stage", "dvt", "--lab-data", str(lab), "--json",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)
    assert data["ok"] is True
    assert len(data["official_quotes"]) == 1
    assert data["official_quotes"][0]["unit_price"] == 120.0
    assert data["analysis"]["total"] == 1
    assert data["analysis"]["pass_flag"] is True


def test_validate_minimal_manifest(tmp_path, capsys):
    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps({
        "runtime": "native_brep",
        "design_intent": "已定义", "coordinate_system": "ISO", "overall_dimensions": "ok",
        "units": "mm", "owner_release": True, "approval_status": "approved",
        # fail-closed 证据项数据（缺失即失败，不得空真通过）
        "model_version": "1.0.0", "drawings_version": "1.0.0",
        "model_part_count": 1, "bom_line_count": 1, "drawing_count": 1,
        "ctq": [{"feature": "hole_a", "inspection_method": "CMM"}],
        "gdt": [{"feature": "hole_a"}],
        "timestamp": "2026-08-01T00:00:00Z",
    }), encoding="utf-8")
    rc = cli_main.main(["validate", "--manifest", str(manifest), "--target", "C0"])
    out = capsys.readouterr().out
    assert rc == 0
    assert '"passed": true' in out


def test_release_check_on_minimal_repo(tmp_path, capsys):
    manifest = tmp_path / "RELEASE_MANIFEST.json"
    manifest.write_text(json.dumps({
        "version": "5.1.0", "runtime": "native_brep",
        "design_intent": "已定义", "coordinate_system": "ISO", "overall_dimensions": "ok",
        "units": "mm", "owner_release": True, "approval_status": "approved",
        # fail-closed 证据项数据（缺失即失败，不得空真通过）
        "model_version": "1.0.0", "drawings_version": "1.0.0",
        "model_part_count": 1, "bom_line_count": 1, "drawing_count": 1,
        "ctq": [{"feature": "hole_a", "inspection_method": "CMM"}],
        "gdt": [{"feature": "hole_a"}],
        "timestamp": "2026-08-01T00:00:00Z",
    }), encoding="utf-8")
    rc = cli_main.main([
        "release", "check", "--target", "C0", "--repo", str(tmp_path), "--json",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)
    assert data["ok"] is True
    assert data["gate_passed"] is True


def test_release_check_missing_manifest_errors(tmp_path, capsys):
    rc = cli_main.main([
        "release", "check", "--target", "C0", "--repo", str(tmp_path), "--json",
    ])
    out = capsys.readouterr().out
    assert rc != 0
    data = json.loads(out)
    assert data["ok"] is False
    assert "error" in data


def test_audit_generates_three_deliverables(tmp_path, capsys):
    out = tmp_path / "audit"
    rc = cli_main.main(["audit", "--repo", str(ROOT), "--out", str(out), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert data["ok"] is True
    assert data["command"] == "audit"
    for name in ("repository_snapshot.json", "capability_matrix.json", "capability_matrix.md"):
        assert (out / name).exists(), f"缺少 {name}"
    assert data["total_capabilities"] > 0
    assert "by_classification" in data


def test_new_commands_registered():
    from aipd_os.cli.commands import PLANNED_COMMANDS
    for name in ["init", "intake", "resume", "status", "decide",
                 "manual plan", "manual generate", "cad preflight", "cad build",
                 "industrialize", "validate", "audit", "release check",
                 "test", "eval", "package"]:
        assert name in PLANNED_COMMANDS, f"{name} 未登记"


def test_existing_commands_still_registered():
    from aipd_os.cli.commands import PLANNED_COMMANDS
    for name in ["init-project", "restore-project", "run", "project-summary",
                 "submit-decision", "run-manual-chain", "run-cad-chain",
                 "run-tests", "run-evals", "build-release"]:
        assert name in PLANNED_COMMANDS, f"{name} 应保持向后兼容"


def test_doctor_reports_capability_guidance(capsys, monkeypatch):
    """doctor --json 对未实现/外部依赖能力给出可操作引导（R-7）。"""
    monkeypatch.delenv("AIPD_MODEL_API_KEY", raising=False)
    monkeypatch.delenv("AIPD_MODEL_BASE_URL", raising=False)
    args = SimpleNamespace(json=True)
    cmd_doctor(args)
    data = json.loads(capsys.readouterr().out)
    checks = {c["name"]: c for c in data["checks"]}
    # 外部依赖：产品智能转译 + 想法结构化给出可操作下一步
    pi = checks["capability.product_intelligence"]
    assert pi["status"] == "external_dependency"
    assert "AIPD_MODEL_API_KEY" in pi["detail"]
    assert "AIPD_MODEL_BASE_URL" in pi["detail"]
    # 未实现：研究五能力诚实标注「当前未实现（规划中）」
    ni = checks["capability.research_not_implemented"]
    assert ni["status"] == "not_implemented"
    assert "research.fulltext" in ni["detail"]
    assert "research.novelty_check" in ni["detail"]
    assert "research.asset_extract" in ni["detail"]


def test_doctor_unrelated_sensitive_env_not_hard_fail(capsys, monkeypatch):
    """回归：环境里存在与 AIPD 无关的敏感变量（如 CODEBUDDY_API_KEY）
    不得让 doctor 硬失败——只审查 AIPD_* 前缀变量。"""
    monkeypatch.setenv("CODEBUDDY_API_KEY", "unrelated-secret")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "unrelated-secret")
    monkeypatch.delenv("AIPD_MODEL_API_KEY", raising=False)
    monkeypatch.delenv("AIPD_MODEL_BASE_URL", raising=False)
    args = SimpleNamespace(json=True)
    rc = cmd_doctor(args)
    data = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert data["ok"] is True
    cred = {c["name"]: c for c in data["checks"]}["security.credentials"]
    assert cred["status"] in ("ok", "warn")


def test_doctor_unregistered_aipd_sensitive_env_warns_not_fails(capsys, monkeypatch):
    """AIPD_* 未登记敏感变量降级为 warn（可操作提示），不再是硬失败。"""
    monkeypatch.setenv("AIPD_SOMETHING_SECRET", "value")
    monkeypatch.delenv("AIPD_MODEL_API_KEY", raising=False)
    monkeypatch.delenv("AIPD_MODEL_BASE_URL", raising=False)
    args = SimpleNamespace(json=True)
    rc = cmd_doctor(args)
    data = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert data["ok"] is True
    cred = {c["name"]: c for c in data["checks"]}["security.credentials"]
    assert cred["status"] == "warn"


def test_industrialize_invalid_stage_rejected(tmp_path, capsys):
    """--stage 必须是 evt/dvt/pvt（缺省 validation），非法值报错退出。"""
    lab = tmp_path / "lab.csv"
    lab.write_text("stage,test_item,sample_id,result,pass_fail\n"
                   "pvt,drop,A-1,broken,fail\n", encoding="utf-8")
    rc = cli_main.main([
        "industrialize", "--db", str(tmp_path / "state.db"),
        "--lab-data", str(lab), "--stage", "dv", "--json",
    ])
    data = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert data.get("ok") is False


def test_bom_add_show_and_cost_calc(tmp_path, capsys):
    """v5.10 制造就绪：bom add / bom show / cost calc 端到端（确定性）。"""
    db_path = tmp_path / "state.db"
    from aipd_os.state.db import AIPDStateDB
    state = AIPDStateDB(str(db_path))
    state.ensure_default_tenant()
    state.init_project("default", "p1", "t", "g")

    rc = cli_main.main([
        "bom", "add", "--db", str(db_path), "--part", "外壳",
        "--supplier", "Acme", "--unit-cost", "10", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert rc == 0 and data["ok"] is True
    assert data["line"]["item"] == "外壳"

    rc = cli_main.main(["bom", "show", "--db", str(db_path), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert rc == 0 and data["rollup"]["line_count"] == 1
    assert data["checklist"]["checks"]["cost_complete"] is True

    rc = cli_main.main([
        "cost", "calc", "--db", str(db_path),
        "--tooling", "50000", "--quantity", "1000", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert rc == 0 and data["ok"] is True
    assert data["cost"]["unit_cost"] == 60.0  # 10 + 50000/1000
    assert data["fact_id"], "成本核算必须写回 Product Truth"
    facts = state.list_facts("default", "p1")
    assert any(f["key"] == "cost.total" and f["status"] == "C" for f in facts)
