"""P1-7 诚实评估报告测试。

核心断言：
- 夹具（deterministic-fixture/contract-test）结果绝不进入「模型行为通过率」。
- 夹具 17/17 绝不当作真实模型 17/17。
- 无凭据的真实模型 run 诚实标记 external/skipped，绝不用假实现替代。
- 报告区分 provider / provider_category / model / real_network_call / grader / trace。
- 评分使用结构化/状态/产物/DB/独立 judge 等维度，并记录 scoring_method。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


from aipd_os.evals_runner.completion import (  # noqa: E402
    PROVIDER_CATEGORY_DETERMINISTIC_FIXTURE,
    PROVIDER_CATEGORY_REAL_MODEL,
    RecordedCompletionProvider,
)
from aipd_os.evals_runner.registry import Case, load_cases  # noqa: E402
from aipd_os.evals_runner.runner import (  # noqa: E402
    EvalRunner,
    run_real_model_smoke,
)
from aipd_os.evals_runner.scoring import (  # noqa: E402
    GRADER_ARTIFACT,
    GRADER_DB_STATE,
    GRADER_JUDGE,
    GRADER_KEYWORD,
    GRADER_STATE,
    GRADER_STRUCTURED,
    evaluate_output,
)
from aipd_os.evals_runner.versioning import build_report  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _cases():
    return load_cases(str(ROOT / "evals" / "evals.json"))


def test_fixture_results_excluded_from_model_pass_rate(tmp_path):
    """夹具 17/17 只计入 fixture_behavior，绝不进入 model_behavior。"""
    runner = EvalRunner(workdir=str(tmp_path))
    results = runner.run(_cases())
    report = build_report(results, version="5.4.0")

    assert len(results) == 17
    assert all(r.provider_category == PROVIDER_CATEGORY_DETERMINISTIC_FIXTURE for r in results)
    assert all(r.passed for r in results)

    mb = report["summary"]["model_behavior"]
    fb = report["summary"]["fixture_behavior"]
    # 夹具结果完全不进入模型行为通过率。
    assert mb["total"] == 0
    assert mb["passed"] == 0
    # 夹具通过率单独、明确标注为 fixture。
    assert fb["total"] == 17
    assert fb["passed"] == 17
    assert fb["pass_rate"] == 1.0


def test_fixture_17_17_not_reported_as_real_model(tmp_path):
    """夹具 17/17 不得被描述为真实模型通过率。"""
    runner = EvalRunner(workdir=str(tmp_path))
    results = runner.run(_cases())
    report = build_report(results, version="5.4.0")

    # 模型行为通过率绝不为 17/17。
    mb = report["summary"]["model_behavior"]
    assert mb["total"] != 17
    assert mb["passed"] != 17
    # fixture 通过率字段名明确。
    assert "fixture_behavior" in report["summary"]
    assert report["summary"]["fixture_behavior"]["passed"] == 17


def test_report_distinguishes_provider_model_realcall_grader_trace(tmp_path):
    """报告区分 provider / provider_category / model / real_network_call / grader / trace。"""
    runner = EvalRunner(workdir=str(tmp_path))
    results = runner.run(_cases())
    report = build_report(results, version="5.4.0")
    r = report["results"][0]

    assert r["provider"] == "RecordedCompletionProvider"
    assert r["provider_category"] == PROVIDER_CATEGORY_DETERMINISTIC_FIXTURE
    assert r["endpoint_type"] == "scripted"
    assert r["model"] == "eval-fake-model"
    assert r["model_version"] == "eval-fake-model"
    assert r["real_network_call"] is False
    assert r["real_network_call"] is not True
    assert r["grader"]  # 非空，记录评分维度
    assert r["scoring_method"]  # 非空
    assert "keyword" in r["scoring_method"]
    assert "structured" in r["scoring_method"]
    assert r["trace"]  # 非空失败/评分轨迹
    assert r["prompt_hash"]
    assert r["token_count"] >= 0
    assert r["latency"] >= 0.0


def test_no_credential_real_model_run_marked_external(tmp_path):
    """无凭据时真实模型 run 标记 external/skipped，绝不用假实现替代。"""
    with mock.patch.dict(os.environ, {}, clear=True):
        results = run_real_model_smoke(_cases(), out_dir=str(tmp_path))

    assert len(results) == 17
    for r in results:
        assert r.provider_category == PROVIDER_CATEGORY_REAL_MODEL
        assert r.passed is False
        assert "external" in r.failure_type
        # trace 诚实说明未用假实现替代。
        assert "no fake substitution" in r.trace
        assert "external" in r.trace
    # 报告里这些是 real-model 类别，且全部 external。
    report = build_report(results, version="5.4.0")
    mb = report["summary"]["model_behavior"]
    assert mb["total"] == 17
    assert mb["external"] == 17
    assert mb["passed"] == 0
    assert mb["pass_rate"] == 0.0


def test_real_model_smoke_with_credentials_runs_real(tmp_path):
    """配置凭据后真实模型 run 真实调用并产出 real-model 结果。"""
    import re as _re

    from aipd_os.evals_runner.completion import PROVIDER_CATEGORY_REAL_MODEL as RM
    from aipd_os.evals_runner.runner import _DEFAULT_SCRIPT

    class SmokeProvider(RecordedCompletionProvider):
        def category(self):
            return RM

        def endpoint_type(self):
            return "openai-compatible-chat"

        def real_network_call(self):
            return True

        def model(self):
            return "real-smoke-model"

        def complete(self, messages):
            case_id = ""
            m = _re.search(r"\[eval case:\s*([^\]]+)\]",
                           messages[0].get("content", ""))
            if m:
                case_id = m.group(1).strip()
            return _DEFAULT_SCRIPT.get(case_id, "")

    cases = _cases()
    with mock.patch.dict(os.environ, {}, clear=True):
        results = run_real_model_smoke(cases, out_dir=str(tmp_path),
                                       provider=SmokeProvider())

    assert len(results) == 17
    all_real = all(r.provider_category == PROVIDER_CATEGORY_REAL_MODEL for r in results)
    assert all_real
    # 真实网络调用标记为 True。
    assert all(r.real_network_call is True for r in results)
    assert all(r.model == "real-smoke-model" for r in results)
    report = build_report(results, version="5.4.0")
    mb = report["summary"]["model_behavior"]
    assert mb["total"] == 17
    assert mb["passed"] == 17


def test_scoring_uses_structured_state_artifact_db_judge():
    """评分使用结构化/状态/产物/DB/独立 judge 维度并记录方法。"""
    case = Case(id="c1", prompt="p", must=["建立或恢复项目状态"], must_not=["伪造"],
                contracts=["no_fabricated_params"])
    output = "基于事实读取工程数据，建立或恢复项目状态。"
    ev = evaluate_output(
        case,
        output,
        state=[{"name": "project", "expected": "active", "actual": "active"}],
        artifacts=[{"name": "manual.pdf", "exists": True, "path": "/x/manual.pdf"}],
        db=[{"name": "run_records", "expected": 1, "actual": 1}],
        judge=lambda text: {"passed": True, "note": "independent rubric ok"},
    )
    assert ev["passed"] is True
    assert GRADER_KEYWORD in ev["graders"]
    assert GRADER_STRUCTURED in ev["graders"]
    assert GRADER_STATE in ev["graders"]
    assert GRADER_ARTIFACT in ev["graders"]
    assert GRADER_DB_STATE in ev["graders"]
    assert GRADER_JUDGE in ev["graders"]


def test_runner_records_scoring_method_with_state_artifact_db(tmp_path):
    """EvalRunner 配置状态/产物/DB 断言后，scoring_method 记录对应维度。"""
    case = Case(id="c1", prompt="p", must=["建立或恢复项目状态"], must_not=["伪造"],
                contracts=["no_fabricated_params"])
    runner = EvalRunner(
        workdir=str(tmp_path),
        script={"c1": "基于事实读取工程数据，建立或恢复项目状态。"},
        state=[{"name": "project", "expected": "active", "actual": "active"}],
        artifacts=[{"name": "manual.pdf", "exists": True, "path": "/x/manual.pdf"}],
        db=[{"name": "run_records", "expected": 1, "actual": 1}],
    )
    result = runner.run_case(case)
    assert result.passed is True
    assert GRADER_STATE in result.scoring_method
    assert GRADER_ARTIFACT in result.scoring_method
    assert GRADER_DB_STATE in result.scoring_method
    assert "state" in result.grader


def test_cli_provider_accepts_new_names():
    """CLI --provider 接受 deterministic-fixture / contract-test / real-model。"""
    from aipd_os.cli.main import build_parser

    parser = build_parser()
    for sub in parser._actions:
        if getattr(sub, "dest", None) == "provider":
            assert "deterministic-fixture" in sub.choices
            assert "contract-test" in sub.choices
            assert "real-model" in sub.choices
            assert "fake" in sub.choices  # 向后兼容


def test_golden_report_marks_fixture_and_side_effect(tmp_path):
    """黄金报告标注 provider_category 为夹具且验证真实副作用。"""
    from aipd_os.evals_runner.golden_projects import load_golden_project, run_golden_project

    project = load_golden_project(str(ROOT / "evals" / "golden_projects" / "simple_mechanical_tool"))
    report = run_golden_project(project, str(tmp_path / "golden_work"),
                                minimum_pages=3)
    assert report["provider_category"] == "deterministic-fixture"
    assert report["real_side_effect_verified"] is True
    assert "artifact" in report["scoring_method"]
    assert "db_state" in report["scoring_method"]
    assert any(c["name"].startswith("artifact:") for c in report["checks"])
    assert any(c["name"].startswith("db:") for c in report["checks"])
