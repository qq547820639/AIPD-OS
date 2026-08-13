"""评估运行器与评分逻辑测试。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from aipd_os import __version__ as _PKG_VERSION  # noqa: E402
from aipd_os.evals_runner.completion import (  # noqa: E402
    EnvCompletionProvider,
    ModelNotConfiguredError,
    RecordedCompletionProvider,
)
from aipd_os.evals_runner.registry import Case, load_cases  # noqa: E402
from aipd_os.evals_runner.runner import EvalRunner  # noqa: E402
from aipd_os.evals_runner.scoring import score_response  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def test_score_response_must_and_must_not():
    res = score_response("已建立或恢复项目状态，开始整理和研究，不先发长问卷。",
                         must=["建立或恢复项目状态", "开始整理和研究", "不先发长问卷"],
                         must_not=["是否继续", "请填写完整需求表"])
    assert res["passed"] is True
    assert res["score"] == 1.0
    assert res["missing_must"] == []
    assert res["violated_must_not"] == []


def test_score_response_missing_and_violated():
    res = score_response("请填写完整需求表。",
                         must=["建立或恢复项目状态", "开始整理和研究"],
                         must_not=["请填写完整需求表"])
    assert res["passed"] is False
    assert res["missing_must"] == ["建立或恢复项目状态", "开始整理和研究"]
    assert res["violated_must_not"] == ["请填写完整需求表"]
    assert res["score"] == 0.0


def test_recorded_provider_returns_scripted_by_case():
    prov = RecordedCompletionProvider({"c1": "hello c1", "c2": "hello c2"})
    out = prov.complete([{"role": "system", "content": "[eval case: c1]"},
                         {"role": "user", "content": "x"}])
    assert out == "hello c1"
    assert prov.history[0]["case_id"] == "c1"


def test_fake_provider_case_passes(tmp_path):
    case = Case(id="autonomous-intake", prompt="p",
                must=["建立或恢复项目状态", "开始整理和研究", "不先发长问卷"],
                must_not=["是否继续", "请填写完整需求表"],
                contracts=["no_long_questionnaire"])
    runner = EvalRunner(workdir=str(tmp_path))
    result = runner.run_case(case)
    assert result.passed is True
    assert result.score == 1.0
    assert result.tool_trajectory[0]["tool"] == "supervisor"
    assert result.failure_type == []


def test_run_over_evals_json_produces_report(tmp_path):
    cases = load_cases(str(ROOT / "evals" / "evals.json"))
    runner = EvalRunner(workdir=str(tmp_path))
    results = runner.run(cases, out_dir=str(tmp_path))
    assert len(results) == len(cases)
    assert all(r.passed for r in results)
    report = (Path(tmp_path) / "eval_reports" / _PKG_VERSION / "report.json")
    assert report.exists()


@pytest.mark.model_eval
def test_env_provider_raises_when_unconfigured(monkeypatch):
    monkeypatch.delenv("AIPD_EVAL_MODEL_ENDPOINT", raising=False)
    monkeypatch.delenv("AIPD_EVAL_MODEL_KEY", raising=False)
    prov = EnvCompletionProvider()
    with pytest.raises(ModelNotConfiguredError):
        prov.complete([{"role": "user", "content": "hi"}])


def test_estimate_tokens_unified_across_runner_and_adapters():
    """回归：evals_runner 与 tool_adapters 必须共用同一 token 估算口径。"""
    from aipd_os.evals_runner.runner import _estimate_tokens
    from aipd_os.llm.tokens import estimate_tokens
    from aipd_os.tool_adapters._common import token_meta

    for text in ("", "hello world", "中文文本估算", "x" * 500):
        assert _estimate_tokens(text) == estimate_tokens(text)
    meta = token_meta("hello world " * 10)
    assert meta["tokens_in"] == estimate_tokens("hello world " * 10)
    assert meta["tokens_in"] > 0
    assert meta["tokens_out"] == 0  # 输入侧文本计入 tokens_in
