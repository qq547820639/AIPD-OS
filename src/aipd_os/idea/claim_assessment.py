"""ClaimAssessment：Claim 的证据评估（derived projection，v5.8.1 Commit 3）。

**不是新 Store** —— 纯函数式评估，输入 Claim + 该 claim 的 relations 列表，
输出确定性的评估结果（不建表、不写库）。

规则（v1，确定性）：
- **只考虑 ``review_status == "reviewed"`` 的 relation**；pending/rejected
  不参与评估（Commit 4 review semantics）；
- 无任何 reviewed relation → ``NOT_SEARCHED``（未完成检索/评审，即使有
  pending/rejected 也不算明确评估）；
- reviewed 关系按语义分类：
  - supporting>0 & contradicting==0 → ``SUPPORTED``（若支持全部为
    partially_supports → ``PARTIALLY_SUPPORTED``）
  - supporting>0 & contradicting>0 → ``MIXED``
  - supporting==0 & contradicting>0 → ``CONTRADICTED``
  - 只有 inconclusive / not_applicable → ``INSUFFICIENT``
- ``NOT_APPLICABLE`` 为显式可用状态（枚举保留；v1 规则不自动产出）。

诚实原则：不把「检索到来源」当作「支持」；不把 pending 当作已评审。
"""
from __future__ import annotations

from typing import Any

from .claims import Claim
from .evidence_relations import EvidenceRelation

# 版本化评估标识
CLAIM_ASSESSMENT_V1 = "claim_assessment_v1"

# 评估状态
ASSESSMENT_NOT_SEARCHED = "NOT_SEARCHED"
ASSESSMENT_INSUFFICIENT = "INSUFFICIENT"
ASSESSMENT_SUPPORTED = "SUPPORTED"
ASSESSMENT_PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
ASSESSMENT_MIXED = "MIXED"
ASSESSMENT_CONTRADICTED = "CONTRADICTED"
ASSESSMENT_NOT_APPLICABLE = "NOT_APPLICABLE"
ASSESSMENT_STATUSES = frozenset({
    ASSESSMENT_NOT_SEARCHED,
    ASSESSMENT_INSUFFICIENT,
    ASSESSMENT_SUPPORTED,
    ASSESSMENT_PARTIALLY_SUPPORTED,
    ASSESSMENT_MIXED,
    ASSESSMENT_CONTRADICTED,
    ASSESSMENT_NOT_APPLICABLE,
})

# 支持/反驳/中性关系类型分组
_SUPPORTING_TYPES = frozenset({"supports", "partially_supports"})
_CONTRADICTING_TYPES = frozenset({"contradicts"})
_INSUFFICIENT_TYPES = frozenset({"inconclusive", "not_applicable"})


def assess(claim: Claim, relations: list[EvidenceRelation]) -> dict[str, Any]:
    """评估一个 Claim 的证据状态（确定性，版本化）。

    ``relations`` 为该 claim 的**全部** relations（含 pending/rejected）；
    函数内部只取 reviewed 参与判定。

    返回：``{"status", "version", "reasons", "counts"}``。
    """
    reviewed = [r for r in relations if r.review_status == "reviewed"]
    pending = [r for r in relations if r.review_status == "pending"]
    rejected = [r for r in relations if r.review_status == "rejected"]

    supporting = [r for r in reviewed if r.relation_type in _SUPPORTING_TYPES]
    contradicting = [r for r in reviewed if r.relation_type in _CONTRADICTING_TYPES]
    insufficient = [r for r in reviewed if r.relation_type in _INSUFFICIENT_TYPES]

    reasons: list[str] = []
    if not reviewed:
        status = ASSESSMENT_NOT_SEARCHED
        reasons.append("no reviewed relation (not searched / not reviewed)")
    elif supporting and not contradicting:
        if all(r.relation_type == "partially_supports" for r in supporting):
            status = ASSESSMENT_PARTIALLY_SUPPORTED
        else:
            status = ASSESSMENT_SUPPORTED
        reasons.append(f"{len(supporting)} reviewed supporting relation(s)")
    elif supporting and contradicting:
        status = ASSESSMENT_MIXED
        reasons.append(
            f"{len(supporting)} supporting + {len(contradicting)} contradicting")
    elif contradicting:
        status = ASSESSMENT_CONTRADICTED
        reasons.append(f"{len(contradicting)} reviewed contradicting relation(s)")
    elif insufficient:
        status = ASSESSMENT_INSUFFICIENT
        reasons.append("reviewed relations all inconclusive/not_applicable")
    else:
        # 防御：reviewed 但关系类型不可识别（理论不可达）
        status = ASSESSMENT_NOT_SEARCHED
        reasons.append("reviewed relations with unrecognized types")

    return {
        "status": status,
        "version": CLAIM_ASSESSMENT_V1,
        "reasons": reasons,
        "counts": {
            "reviewed_supporting": len(
                [r for r in supporting if r.relation_type == "supports"]),
            "reviewed_partially_supporting": len(
                [r for r in supporting if r.relation_type == "partially_supports"]),
            "reviewed_contradicting": len(contradicting),
            "reviewed_inconclusive": len(
                [r for r in insufficient if r.relation_type == "inconclusive"]),
            "reviewed_not_applicable": len(
                [r for r in insufficient if r.relation_type == "not_applicable"]),
            "pending_relations": len(pending),
            "rejected_relations": len(rejected),
            "total_relations": len(relations),
        },
    }


__all__ = [
    "CLAIM_ASSESSMENT_V1",
    "ASSESSMENT_STATUSES",
    "ASSESSMENT_NOT_SEARCHED",
    "ASSESSMENT_INSUFFICIENT",
    "ASSESSMENT_SUPPORTED",
    "ASSESSMENT_PARTIALLY_SUPPORTED",
    "ASSESSMENT_MIXED",
    "ASSESSMENT_CONTRADICTED",
    "ASSESSMENT_NOT_APPLICABLE",
    "assess",
]
