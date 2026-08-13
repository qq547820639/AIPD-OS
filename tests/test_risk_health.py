"""风险健康视图测试：确定性、无副作用、无需真实数据库。"""
from __future__ import annotations

from aipd_os.experience.risk_health import compute_risk_health, traffic_light_status


def _risk(impact, status="open", title=None):
    return {"title": title or f"risk-{impact}", "impact": impact, "status": status}


# ---------------------------------------------------------------- 红/黄/绿
def test_red_when_critical_open_risk():
    out = compute_risk_health([_risk("critical")], [])
    assert out["traffic_light"] == "red"
    assert out["top_risk_title"] == "risk-critical"


def test_red_when_high_open_risk():
    assert traffic_light_status([_risk("high")], []) == "red"


def test_red_when_blocked_external():
    out = compute_risk_health([], [], project_status="blocked_external")
    assert out["traffic_light"] == "red"


def test_yellow_when_medium_open_risk():
    assert compute_risk_health([_risk("medium")], [])["traffic_light"] == "yellow"


def test_yellow_when_external_waiting():
    wait = [{"source_type": "supplier", "source_id": "s1",
             "target_type": "quote", "target_id": "q1"}]
    assert compute_risk_health([], wait)["traffic_light"] == "yellow"


def test_green_when_nothing():
    out = compute_risk_health([], [])
    assert out["traffic_light"] == "green"
    assert out["summary"]
    assert out["reason"]
    assert out["top_risk_title"] is None


def test_closed_high_risk_does_not_trigger_red():
    assert compute_risk_health([_risk("high", status="closed")], [])["traffic_light"] == "green"


# ---------------------------------------------------------------- 确定性
def test_deterministic_same_input_same_output():
    risks = [_risk("low"), _risk("high"), _risk("medium")]
    wait = [{"source_type": "lab", "source_id": "L1",
             "target_type": "test", "target_id": "t1"}]
    a = compute_risk_health(risks, wait, "active")
    b = compute_risk_health(risks, wait, "active")
    assert a == b


def test_red_overrides_yellow():
    # 既有 medium 又有 high -> 红灯优先
    out = compute_risk_health([_risk("medium"), _risk("high")], [])
    assert out["traffic_light"] == "red"
