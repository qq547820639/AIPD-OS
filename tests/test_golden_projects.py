"""黄金端到端项目测试：每个夹具运行并产出报告。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from aipd_os.evals_runner import golden_projects  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "evals" / "golden_projects"


def _run(name, tmp_path, minimum_pages=None):
    report = golden_projects.run_golden_dir(
        str(GOLDEN / name), str(tmp_path / name), minimum_pages=minimum_pages
    )
    return report


def test_exoskeleton_ten_page_manual(tmp_path):
    """外骨骼黄金项目：>=10 页手册端到端完成 + 批次连续性 + 无伪造外部证据。"""
    report = _run("exoskeleton", tmp_path, minimum_pages=10)
    assert report["passed"] is True
    assert report["manual_pages"] >= 10
    assert report["batch_continuity_ok"] is True
    assert report["external_status"] == "blocked_external"
    assert report["external_task_packages"]
    assert report["pdf"] and Path(report["pdf"]).exists()
    assert report["zip"] and Path(report["zip"]).exists()


def test_consumer_electronics(tmp_path):
    report = _run("consumer_electronics", tmp_path)
    assert report["passed"] is True
    assert report["manual_pages"] >= 6
    assert report["batch_continuity_ok"] is True


def test_simple_mechanical_tool(tmp_path):
    report = _run("simple_mechanical_tool", tmp_path)
    assert report["passed"] is True
    assert report["manual_pages"] >= 4


def test_all_golden_projects_run(tmp_path):
    for name in ["exoskeleton", "consumer_electronics", "simple_mechanical_tool"]:
        report = _run(name, tmp_path)
        assert report["passed"] is True, f"{name} failed: {report['checks']}"


def test_report_contains_run_metadata(tmp_path):
    """黄金报告应包含：耗时、产物 SHA-256、工具轨迹与诚实成本/token。"""
    report = _run("exoskeleton", tmp_path, minimum_pages=10)

    # 耗时：可观测的墙钟时间
    assert "elapsed_seconds" in report
    assert report["elapsed_seconds"] >= 0

    # 产物哈希：PNG/PDF/ZIP 均须有 SHA-256
    hashes = report["artifact_hashes"]
    assert hashes["manual.pdf"]
    assert hashes["manual.zip"]
    assert len(hashes) >= report["manual_pages"] + 2  # 每页 PNG + pdf + zip
    assert all(len(h) == 64 for h in hashes.values())

    # 工具轨迹：真实执行记录被记录
    traj = report["tool_trajectory"]
    assert traj
    tools = {t["tool"] for t in traj}
    assert "manual.render_page" in tools
    assert "manual.visual_audit" in tools
    assert "manual.imggen.eval-fake" in tools
    assert "manual.compose_pdf" in tools
    assert "manual.compose_zip" in tools

    # 诚实成本/token：离线确定性运行，token/成本为 0/na 并附说明
    usage = report["model_usage"]
    assert usage["tokens_in"] == 0
    assert usage["tokens_out"] == 0
    assert usage["cost"] == 0
    assert "offline-deterministic" in usage["note"]
    assert report["provider"] == "offline-deterministic"
