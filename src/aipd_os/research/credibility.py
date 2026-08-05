"""证据可信度评分。

对研究证据按来源可信度、时间衰减与事实/假设属性进行确定性评分，
并诚实区分事实与假设。当必要输入缺失时返回 not_verifiable，绝不虚构分数。
"""

from __future__ import annotations

from typing import Any, Dict, List

# 已知来源类型 -> 基础得分
SOURCE_CREDIBILITY = {
    "peer_reviewed": 0.9,
    "official_standard": 0.95,
    "patent": 0.85,
    "industry_report": 0.7,
    "vendor_claim": 0.5,
    "forum": 0.3,
    "unknown": 0.4,
}

# 事实/假设系数
FACT_FACTOR = 1.0
ASSUMPTION_FACTOR = 0.6
UNKNOWN_FACTOR = 0.8

# 时间衰减
FULL_CREDIBILITY_DAYS = 30.0
MIN_DECAY = 0.2


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def source_credibility(source: str) -> float:
    """将来源类型映射为基础得分；未知来源默认 0.4。"""
    if not source:
        return SOURCE_CREDIBILITY["unknown"]
    return SOURCE_CREDIBILITY.get(source, SOURCE_CREDIBILITY["unknown"])


def time_decay(days_old: float) -> float:
    """时间衰减：<=30 天为 1.0，之后线性衰减，最低不低于 0.2。"""
    if days_old <= FULL_CREDIBILITY_DAYS:
        return 1.0
    # 线性衰减：30 天 -> 1.0，衰减到 >=0.2 的最小值
    decayed = 1.0 - (days_old - FULL_CREDIBILITY_DAYS) / 365.0
    return max(MIN_DECAY, decayed)


def assumption_factor(is_fact: bool) -> float:
    """事实系数：事实 1.0，假设 0.6，未知 0.8。"""
    if is_fact is None:
        return UNKNOWN_FACTOR
    return FACT_FACTOR if bool(is_fact) else ASSUMPTION_FACTOR


def score_evidence(source: str, days_old: float, is_fact: bool) -> Dict[str, Any]:
    """对单条证据评分。

    当必要输入缺失（如未提供来源）时返回 {"status": "not_verifiable"}，
    而不虚构分数。
    """
    if not source:
        return {"status": "not_verifiable"}

    src = source_credibility(source)
    decay = time_decay(days_old)
    fact = assumption_factor(is_fact)
    score = _clamp01(src * decay * fact)

    if score >= 0.7:
        credibility = "high"
    elif score >= 0.4:
        credibility = "medium"
    else:
        credibility = "low"

    return {
        "score": round(score, 4),
        "credibility": credibility,
        "components": {
            "source_score": src,
            "time_factor": round(decay, 4),
            "assumption_factor": fact,
        },
    }


def separate_facts_from_assumptions(evidence_list: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """按每条证据的 is_fact 标志拆分为 事实 / 假设 两组。"""
    facts = []
    assumptions = []
    for item in evidence_list or []:
        if bool(item.get("is_fact")):
            facts.append(item)
        else:
            assumptions.append(item)
    return {"facts": facts, "assumptions": assumptions}


__all__ = [
    "SOURCE_CREDIBILITY",
    "source_credibility",
    "time_decay",
    "assumption_factor",
    "score_evidence",
    "separate_facts_from_assumptions",
]