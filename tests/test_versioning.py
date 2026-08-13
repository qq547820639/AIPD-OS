"""评估数据版本化与回归门禁测试。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from aipd_os.evals_runner.runner import EvalResult  # noqa: E402
from aipd_os.evals_runner.versioning import (  # noqa: E402
    build_report,
    load_baseline,
    save_eval_report,
    should_block_release,
)


def _report(results):
    return build_report(results, version="5.0.0")


def test_save_and_load_baseline(tmp_path):
    r = _report([EvalResult(case_id="c1", prompt="p", model_version="m", score=1.0, passed=True, failure_type=[])])  # noqa: E501
    path = save_eval_report(r, str(tmp_path), version="5.0.0")
    assert Path(path).exists()
    base = load_baseline(str(tmp_path), "5.0.0")
    assert base["results"][0]["case_id"] == "c1"


def test_should_block_release_blocks_on_drop(tmp_path):
    baseline = _report([EvalResult(case_id="c1", prompt="p", model_version="m", score=0.9, passed=True, failure_type=[])])  # noqa: E501
    latest = _report([EvalResult(case_id="c1", prompt="p", model_version="m", score=0.5, passed=False, failure_type=["missing"])])  # noqa: E501
    gate = should_block_release(latest, baseline, threshold=0.1)
    assert gate["blocked"] is True
    assert gate["drop"] >= 0.1
    assert "c1" in gate["drops"]


def test_should_block_release_passes_without_drop(tmp_path):
    baseline = _report([EvalResult(case_id="c1", prompt="p", model_version="m", score=0.8, passed=True, failure_type=[])])  # noqa: E501
    latest = _report([EvalResult(case_id="c1", prompt="p", model_version="m", score=0.8, passed=True, failure_type=[])])  # noqa: E501
    gate = should_block_release(latest, baseline, threshold=0.1)
    assert gate["blocked"] is False
    assert gate["drop"] == 0.0
