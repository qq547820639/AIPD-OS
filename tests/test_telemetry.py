"""结构化日志 / trace / 指标 / 成本预算测试。

AIPD_ACK_SECRET: 本文件包含故意伪造的密钥样例（sk-...），仅用于断言脱敏，
非真实凭据；发布 secret 扫描据此视为已承认。
"""
from __future__ import annotations

import json
import logging

import pytest

from aipd_os.telemetry import (
    BudgetExceededError,
    BudgetState,
    CostBudget,
    Histogram,
    Metrics,
    Telemetry,
    TelemetryLogger,
    new_trace_id,
)
from aipd_os.telemetry.logging import JsonTraceFormatter, telemetry_enabled


def test_new_trace_id_unique_and_prefixed():
    a = new_trace_id()
    b = new_trace_id()
    assert a != b
    assert a.startswith("tr-")


def test_telemetry_enabled_default_off(monkeypatch):
    monkeypatch.delenv("AIPD_TELEMETRY_ENABLED", raising=False)
    assert telemetry_enabled() is False
    monkeypatch.setenv("AIPD_TELEMETRY_ENABLED", "1")
    assert TelemetryLogger()._emit is not None  # 引入确保可导入
    from aipd_os.telemetry.logging import telemetry_enabled as te
    assert te() is True


def test_json_trace_formatter_includes_trace_id_and_masks():
    formatter = JsonTraceFormatter()
    record = logging.LogRecord(
        name="t", level=logging.INFO, pathname=__file__, lineno=1,
        msg="run", args=(), exc_info=None)
    record.trace_id = "tr-abcdef"
    record.aipd_fields = {"api_key": "sk-verylongsecretvalue-xyz", "ok": True}
    out = json.loads(formatter.format(record))
    assert out["trace_id"] == "tr-abcdef"
    assert "verylongsecretvalue" not in out["api_key"]
    assert out["ok"] is True


def test_telemetry_logger_emits(capsys):
    tl = TelemetryLogger(name="test.tel", level="INFO")
    tl.info("hello", trace_id="tr-1", event_scope="unit")
    captured = capsys.readouterr()
    text = (captured.out + captured.err).strip()
    line = json.loads(text.splitlines()[-1])
    assert line["message"] == "hello"
    assert line["trace_id"] == "tr-1"
    assert line["event_scope"] == "unit"


def test_histogram_buckets():
    h = Histogram([1.0, 5.0])
    h.observe(0.5)
    h.observe(3.0)
    h.observe(10.0)
    snap = h.snapshot()
    assert snap["count"] == 3
    assert snap["sum"] == pytest.approx(13.5)
    assert snap["bucket_counts"] == [1, 1, 1]


def test_metrics_counter_and_histogram():
    m = Metrics()
    m.inc("tasks", 3)
    m.inc("tasks")
    assert m.count("tasks") == 4.0
    m.observe("latency_ms", 0.2)
    snap = m.snapshot()
    assert snap["counters"]["tasks"] == 4.0
    assert snap["histograms"]["latency_ms"]["count"] == 1


def test_cost_budget_warning():
    b = CostBudget(limit=100, warn_after=50, stop_on_exceed=False)
    assert b.track(60) == BudgetState.WARNING
    assert b.state() == BudgetState.WARNING


def test_cost_budget_exceed_disabled_stop():
    b = CostBudget(limit=100, stop_on_exceed=False)
    assert b.track(150) == BudgetState.EXCEEDED
    assert b.state() == BudgetState.EXCEEDED


def test_cost_budget_exceed_raises():
    b = CostBudget(limit=100, stop_on_exceed=True)
    with pytest.raises(BudgetExceededError):
        b.track(150)


def test_cost_budget_ok():
    b = CostBudget(limit=100, warn_after=50)
    assert b.track(10) == BudgetState.OK
    assert b.state() == BudgetState.OK
    assert b.snapshot()["spent"] == pytest.approx(10)


def test_telemetry_combined():
    t = Telemetry(budget_limit=100, budget_warn_after=50)
    t.metrics.inc("calls")
    t.budget.track(10)
    snap = t.snapshot()
    assert snap["metrics"]["counters"]["calls"] == 1
    assert snap["budget"]["state"] == BudgetState.OK