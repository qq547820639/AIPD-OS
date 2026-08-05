"""证据可信度评分测试（Task 2）。"""

from __future__ import annotations

import pytest

from aipd_os.research.credibility import (
    assumption_factor,
    score_evidence,
    separate_facts_from_assumptions,
    source_credibility,
    time_decay,
)


def test_source_credibility_mapping_and_unknown_default():
    assert source_credibility("peer_reviewed") == 0.9
    assert source_credibility("official_standard") == 0.95
    assert source_credibility("patent") == 0.85
    assert source_credibility("industry_report") == 0.7
    assert source_credibility("vendor_claim") == 0.5
    assert source_credibility("forum") == 0.3
    assert source_credibility("mystery_source") == 0.4  # 未知默认 0.4
    assert source_credibility("") == 0.4


def test_time_decay_floor():
    assert time_decay(0) == 1.0
    assert time_decay(30) == 1.0
    fresh = time_decay(100)
    assert 0.2 <= fresh < 1.0
    assert time_decay(10000) == 0.2  # 最低不低于 0.2


def test_assumption_factor():
    assert assumption_factor(True) == 1.0
    assert assumption_factor(False) == 0.6
    assert assumption_factor(None) == 0.8  # 未知


def test_score_evidence_high_medium_low():
    high = score_evidence("official_standard", 10, True)
    assert high["score"] >= 0.7
    assert high["credibility"] == "high"
    assert high["components"]["source_score"] == 0.95

    low = score_evidence("forum", 1000, False)
    assert low["score"] < 0.4
    assert low["credibility"] == "low"

    # 分数被钳制到 [0,1]
    assert 0.0 <= high["score"] <= 1.0


def test_score_evidence_missing_source_not_verifiable():
    # 诚实护栏：来源缺失时不虚构分数
    out = score_evidence("", 10, True)
    assert out == {"status": "not_verifiable"}
    out2 = score_evidence(None, 10, True)
    assert out2["status"] == "not_verifiable"
    assert "score" not in out2


def test_separate_facts_from_assumptions():
    evidence = [
        {"id": "a", "is_fact": True},
        {"id": "b", "is_fact": False},
        {"id": "c", "is_fact": True},
        {"id": "d", "is_fact": None},
    ]
    split = separate_facts_from_assumptions(evidence)
    assert [e["id"] for e in split["facts"]] == ["a", "c"]
    assert [e["id"] for e in split["assumptions"]] == ["b", "d"]

    empty = separate_facts_from_assumptions([])
    assert empty == {"facts": [], "assumptions": []}