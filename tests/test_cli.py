"""Task 9：aipd 一键 CLI 与发布包构建器的测试。

直接调用 ``aipd_os.cli.main.main(argv)`` 验证 10 个子命令的关键行为。
所有用到的输出目录都落在 pytest 的 ``tmp_path`` 下，不污染仓库。
"""
from __future__ import annotations

import json
from pathlib import Path

from aipd_os.cli import main as cli_main

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
    report = out / "eval_reports" / "5.0.0" / "report.json"
    assert report.exists()
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["summary"]["passed"] == data["summary"]["total"]
