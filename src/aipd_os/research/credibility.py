"""证据可信度评分。

对研究证据按来源可信度、时间衰减与事实/假设属性进行确定性评分，
并诚实区分事实与假设。当必要输入缺失时返回 not_verifiable，绝不虚构分数。
"""

from __future__ import annotations

from typing import Any

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


def score_evidence(source: str, days_old: float, is_fact: bool) -> dict[str, Any]:
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


def separate_facts_from_assumptions(evidence_list: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """按每条证据的 is_fact 标志拆分为 事实 / 假设 两组。"""
    facts = []
    assumptions = []
    for item in evidence_list or []:
        if bool(item.get("is_fact")):
            facts.append(item)
        else:
            assumptions.append(item)
    return {"facts": facts, "assumptions": assumptions}


# ------------------------------------------------------------------ 来源元数据
# 来源类型 -> 元数据（名称、性质、是否官方/一手）
SOURCE_METADATA: dict[str, dict[str, Any]] = {
    "peer_reviewed": {"label": "同行评审文献", "official": False, "first_hand": True},
    "official_standard": {"label": "官方标准", "official": True, "first_hand": True},
    "patent": {"label": "专利文献", "official": True, "first_hand": True},
    "industry_report": {"label": "行业报告", "official": False, "first_hand": False},
    "vendor_claim": {"label": "厂商宣称", "official": False, "first_hand": True},
    "forum": {"label": "社区讨论", "official": False, "first_hand": False},
    "unknown": {"label": "未知来源", "official": False, "first_hand": False},
}


def source_metadata(source: str) -> dict[str, Any]:
    """返回来源元数据；未知来源返回 unknown 元数据。"""
    return SOURCE_METADATA.get(source or "", SOURCE_METADATA["unknown"])


def timeliness(days_old: float) -> dict[str, Any]:
    """时效评级：新鲜 / 一般 / 陈旧。"""
    if days_old < 0:
        return {"freshness": "unknown"}
    if days_old <= 180:
        return {"freshness": "fresh", "fresh": True}
    if days_old <= 730:
        return {"freshness": "aging", "fresh": False}
    return {"freshness": "stale", "fresh": False}


def confidence_tag(confidence: float) -> str:
    """置信度离散化标签。"""
    if confidence >= 0.7:
        return "high"
    if confidence >= 0.4:
        return "medium"
    return "low"


# ------------------------------------------------------------------ 冲突解析
def resolve_conflicts(findings: list[dict[str, Any]]) -> dict[str, Any]:
    """解析同一 key 的多条证据冲突。

    不静默选择某一方：当存在事实性冲突时，返回 ``conflict=True`` 并列出冲突项，
    由调用方决定如何处理；仅在无冲突时标记 resolved。
    """
    if not findings:
        return {"conflict": False, "groups": [], "resolved": True}

    groups: dict[str, list[dict[str, Any]]] = {}
    for item in findings:
        key = item.get("key") or "unknown"
        groups.setdefault(key, []).append(item)

    conflicts = []
    for key, items in groups.items():
        values = {_norm_value(i.get("value")) for i in items if "value" in i}
        if len(values) > 1:
            conflicts.append({"key": key, "items": items, "distinct_values": sorted(values)})

    return {
        "conflict": len(conflicts) > 0,
        "groups": groups,
        "conflicts": conflicts,
        "resolved": len(conflicts) == 0,
    }


def _norm_value(value: Any) -> str:
    return str(value).strip().lower()


__all__ = [
    "SOURCE_CREDIBILITY",
    "SOURCE_METADATA",
    "source_credibility",
    "source_metadata",
    "time_decay",
    "timeliness",
    "confidence_tag",
    "assumption_factor",
    "score_evidence",
    "separate_facts_from_assumptions",
    "resolve_conflicts",
]
