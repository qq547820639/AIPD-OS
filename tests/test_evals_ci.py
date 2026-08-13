"""CI 确定性评估子集：仅假实现，CI 可用 `pytest -m "not model_eval"` 运行。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from aipd_os.evals_runner.registry import load_cases  # noqa: E402
from aipd_os.evals_runner.runner import EvalRunner  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def test_deterministic_subset_runs_green(tmp_path):
    """确定性（假实现）子集：全部 case 通过。"""
    cases = load_cases(str(ROOT / "evals" / "evals.json"))
    runner = EvalRunner(workdir=str(tmp_path))
    results = runner.run(cases)
    assert all(r.passed for r in results)
    assert all(r.failure_type == [] or "external" in r.failure_type for r in results)


def test_cli_run_fake_produces_report(tmp_path):
    """通过 CLI（--provider fake）跑一次并产出版本化 JSON 报告。"""
    import subprocess
    import sys as _sys

    out = str(tmp_path / "out")
    r = subprocess.run(
        [_sys.executable, "-m", "aipd_os.evals_runner.cli", "run",
         "--evals", str(ROOT / "evals" / "evals.json"),
         "--provider", "fake", "--out", out, "--version", "5.0.0"],
        capture_output=True, text=True,
        env={"PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin:/usr/local/bin"},
    )
    assert r.returncode == 0, f"cli failed: {r.stdout}\n{r.stderr}"
    report_path = Path(out) / "eval_reports" / "5.0.0" / "report.json"
    assert report_path.exists()
    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert data["summary"]["passed"] == data["summary"]["total"]


@pytest.mark.model_eval
def test_model_gated_requires_endpoint(monkeypatch):
    """真实模型路径必须配置端点，否则抛错（不可伪造通过）。"""
    monkeypatch.delenv("AIPD_EVAL_MODEL_ENDPOINT", raising=False)
    from aipd_os.evals_runner.completion import EnvCompletionProvider, ModelNotConfiguredError
    with pytest.raises(ModelNotConfiguredError):
        EnvCompletionProvider().complete([{"role": "user", "content": "x"}])
