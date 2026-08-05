"""决策策略测试。"""

from __future__ import annotations

from aipd_os.execution.decision_policy import build_decision_package, should_ask_decision


def test_rework_search_batching_not_decision():
    for cat in ("rework", "search", "batching", "ordinary", "iteration"):
        assert should_ask_decision({"category": cat}) is False


def test_direction_ambiguity_triggers():
    assert should_ask_decision({"category": "product_architecture_fork"}) is True


def test_irreversible_tooling_triggers():
    assert should_ask_decision({"category": "rework", "irreversible": True}) is True
    assert should_ask_decision({"category": "irreversible_investment"}) is True
    assert should_ask_decision({"category": "tooling_or_purchase"}) is True


def test_safety_regulatory_and_constraint_trigger():
    assert should_ask_decision({"category": "safety_or_regulatory"}) is True
    assert should_ask_decision({"category": "hard_constraint_conflict"}) is True
    assert should_ask_decision({"safety_impact": "high"}) is True
    assert should_ask_decision({"regulatory_impact": "critical"}) is True


def test_owner_required_triggers():
    assert should_ask_decision({"category": "rework", "owner_required": True}) is True


def test_build_decision_package():
    pkg = build_decision_package(
        {
            "work_id": "W1",
            "title": "开模",
            "category": "irreversible_investment",
            "capability_floor": "cad.text-to-cad",
        },
        recommendation="暂停不可逆投入",
        options=["暂停", "补充样件数据", "继续小批量试制"],
        impact={"cost": "high"},
    )
    assert pkg["recommendation"] == "暂停不可逆投入"
    assert 2 <= len(pkg["options"]) <= 4
    assert pkg["impact"]["cost"] == "high"
    assert pkg["decision"]["category"] == "irreversible_investment"
    assert "execute_after_approval" in pkg
    assert pkg["work_id"] == "W1"
