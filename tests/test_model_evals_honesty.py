"""P1-4 真实模型评测诚实性测试。

核心诚实断言：
- 无真实凭据时，模型行为报告显示 **0 个样本**（HOLD），绝不用 fixture 生成“满分”；
- fixture/contract 结果永远进入 ``fixture_behavior``，绝不进入真实模型通过率；
- 有凭据（mock 端点）时记录 provider / model version / token / 费用 / 延迟 / 重试 / trace。
"""

from __future__ import annotations

import os
from unittest import mock

import pytest

from aipd_os.evals.runner import (
    CALL_OK,
    STATUS_COMPLETED,
    STATUS_HOLD,
    ModelEvalConfig,
    ModelEvalJob,
    build_eval_report,
    estimate_cost,
    load_model_eval_config,
    model_behavior_block,
    run_model_eval,
)


# ---------------------------------------------------------------- 诚实门控：夹具
class _FixtureResult:
    """模拟一个 deterministic-fixture/contract-test 的通过结果。"""

    def __init__(self, passed: bool = True):
        self.passed = passed


def test_fixture_results_never_enter_model_behavior():
    """夹具结果只进 fixture_behavior，模型行为样本数必须为 0。"""
    fixture = [_FixtureResult(True) for _ in range(17)]
    report = build_eval_report([], status=STATUS_COMPLETED, fixture_results=fixture)
    mb = report["summary"]["model_behavior"]
    fb = report["summary"]["fixture_behavior"]
    # 模型行为：无真实调用 -> 0 样本。
    assert mb["total"] == 0
    assert mb["passed"] == 0
    assert report["samples"] == 0
    # 夹具 17/17 单独标注为 fixture，绝不当作真实通过率。
    assert fb["total"] == 17
    assert fb["passed"] == 17
    assert fb["fixture"] is True


def test_model_behavior_block_counts_only_real_calls():
    from aipd_os.evals.runner import ModelCall

    real_ok = ModelCall(provider="p", model_version="m", network_call=True, status=CALL_OK)
    real_err = ModelCall(provider="p", model_version="m", network_call=True, status="error")
    fixture = ModelCall(provider="f", model_version="m", network_call=False)
    block = model_behavior_block([real_ok, real_err, fixture])
    assert block["total"] == 2  # 只统计真实网络调用
    assert block["passed"] == 1


# ---------------------------------------------------------------- 无凭据 -> HOLD / 0 样本
def test_no_credentials_hold_reports_zero_samples():
    with mock.patch.dict(os.environ, {}, clear=True):
        report = run_model_eval(["sample A", "sample B"])

    assert report["status"] == STATUS_HOLD
    assert report["samples"] == 0  # 无真实调用 -> 0 样本，绝不用夹具凑数
    mb = report["summary"]["model_behavior"]
    assert mb["total"] == 0
    assert mb["passed"] == 0
    assert "no_credentials" in report["reason"]


def test_eval_job_hold_when_no_credentials():
    with mock.patch.dict(os.environ, {}, clear=True):
        job = ModelEvalJob()
        result = job.run(["sample"])
    assert result["status"] == STATUS_HOLD
    assert result["samples"] == 0


def test_load_config_configured_flag():
    with mock.patch.dict(os.environ, {}, clear=True):
        cfg = load_model_eval_config()
        assert cfg.configured is False
    with mock.patch.dict(
        os.environ,
        {"AIPD_MODEL_API_KEY": "k", "AIPD_MODEL_BASE_URL": "https://api.example"},
        clear=True,
    ):
        cfg2 = load_model_eval_config()
        assert cfg2.configured is True


# ---------------------------------------------------------------- 有凭据（mock 端点）
def _mock_client_with_usage(usage=None, fail_first=False):
    """构造一个可注入的 client：返回 text + usage；可选首次失败以测重试。"""
    calls = {"n": 0}

    def client(sample, cfg):
        calls["n"] += 1
        if fail_first and calls["n"] == 1:
            raise ConnectionError("first attempt failed")
        return {
            "text": f"response for {sample}",
            "usage": usage or {"prompt_tokens": 10, "completion_tokens": 20},
        }

    return client


@pytest.fixture
def cfg():
    return ModelEvalConfig(
        api_key="secret-key",
        base_url="https://api.example/v1",
        model_version="eval-model-v1",
    )


def test_with_credentials_records_full_metadata(cfg):
    client = _mock_client_with_usage({"prompt_tokens": 10, "completion_tokens": 20})
    report = run_model_eval(
        ["sample"],
        config=cfg,
        client=client,
        fixture_results=[_FixtureResult(True)],
    )
    assert report["status"] == STATUS_COMPLETED
    assert report["samples"] == 1
    call = report["calls"][0]
    assert call["provider"] == "api.example"
    assert call["model_version"] == "eval-model-v1"
    assert call["network_call"] is True
    assert call["token_count"] == 30
    assert call["prompt_token_count"] == 10
    assert call["completion_token_count"] == 20
    assert call["cost"] == estimate_cost(30)
    assert call["latency"] >= 0.0
    assert call["retry_count"] == 0
    assert call["status"] == CALL_OK
    assert "response for sample" in call["trace"]
    assert call["prompt_hash"]
    # 凭据保护：trace 中绝不含密钥
    assert "secret-key" not in call["trace"]
    assert "secret-key" not in str(report)
    # 模型行为通过率只含真实调用
    assert report["summary"]["model_behavior"]["total"] == 1
    assert report["summary"]["model_behavior"]["passed"] == 1
    # 夹具仍只在 fixture_behavior
    assert report["summary"]["fixture_behavior"]["total"] == 1


def test_retry_is_recorded(cfg):
    client = _mock_client_with_usage(fail_first=True)
    report = run_model_eval(["sample"], config=cfg, client=client)
    call = report["calls"][0]
    assert call["retry_count"] == 1
    assert call["status"] == CALL_OK


def test_budget_cap_stops_calls(cfg):
    client = _mock_client_with_usage({"prompt_tokens": 1000, "completion_tokens": 1000})
    # 每 1k token 单价 0.002 -> 每次 2000 token 成本 0.004；预算 0.003 应在第 1 次后超限
    cfg.rate_usd_per_1k = 0.002
    report = run_model_eval(["a", "b", "c"], config=cfg, client=client, budget_usd=0.003)
    assert report["samples"] == 1
    assert report["status"] == STATUS_HOLD
    assert "budget_exceeded" in report["reason"]


def test_max_calls_cap(cfg):
    client = _mock_client_with_usage()
    report = run_model_eval(["a", "b", "c"], config=cfg, client=client, max_calls=2)
    assert report["samples"] == 2
    assert len(report["calls"]) == 2


def test_credential_protection_never_leaks_key(cfg):
    client = _mock_client_with_usage(fail_first=True)
    report = run_model_eval(["x"], config=cfg, client=client)
    blob = str(report)
    assert "secret-key" not in blob
