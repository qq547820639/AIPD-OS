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
