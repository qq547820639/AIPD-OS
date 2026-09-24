"""一维公差叠加（stack-up）：判断图纸上的尺寸链是否**自相矛盾**。

属于 capability ``cad.2d_drawings``；由 ``write_dxf`` 逐视图调用，结果写进图纸证据。

判据只有一条，且可手算复核：闭合链上各组成环的公差带之和，若超过封闭环（总体宽）自己
声明的公差带，那么「各段都合格」与「总宽也合格」在数学上不可能同时成立。

刻意**不做**的：不猜功能要求（仓库里没有「封闭间隙必须 ≤ X」这类外部限值，硬给就是编判据），
不做三维/角度叠加，不做统计相关的 Cpk 假设。缺任何一环声明就整体判
``insufficient_data`` 并点名——**绝不按 0 折算**，那正是这类计算最常见的假绿来源。

对照过的上游实现（读源码后否掉，只借公式形状）：GitHub ``tolerance-stackup-cli``
（MIT、1 star）对 tol 取 ``abs()`` ⇒ 不支持非对称偏差，也不计算封闭环（要人手写成一行）；
本仓的公差声明本来就允许非对称，所以判据自己实现，并用闭式手算值钉在
``tests/test_cad_stackup.py`` 里。
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

# 判定用容差：链条由投影测量得来，段值已经 round 到 3 位，这里只做浮点比较的收尾。
EPS = 1e-12


def band_of(tolerance: dict[str, Any] | None) -> float | None:
    """一条偏差声明的**公差带宽度** ``upper - lower``；没声明返回 None。

    ``{"upper": 0.0, "lower": 0.0}`` 是合法声明（不许偏），与「没声明」严格区分。
    """
    if not tolerance:
        return None
    upper = float(tolerance["upper"])
    lower = float(tolerance["lower"])
    if upper < lower:
        raise ValueError(f"tolerance 上下界颠倒：{tolerance!r}")
    return upper - lower


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 9)


def view_stackup(dims: Sequence[dict[str, Any]], view: str) -> dict[str, Any]:
    """按视图算链的叠加并给出判定。

    判定取值：``no_chain`` / ``insufficient_data`` / ``no_closing_tolerance`` /
    ``inconsistent`` / ``consistent``。前三种都意味着「这张图不能被判定」，
    不是通过。
    """
    chain = [d for d in dims if d.get("kind") == "chain"]
    report: dict[str, Any] = {
        "view": view,
        "segments": len(chain),
        "features": [str(d.get("feature")) for d in chain],
        "undeclared": [],
        "worst_case": None,
        "rss": None,
        "closing_feature": None,
        "closing_band": None,
        "verdict": "no_chain",
        "excess": None,
        "margin": None,
        "formula": "band=upper-lower; worst=Σband; rss=√(Σband²); "
                   "inconsistent when worst > closing band",
    }
    if not chain:
        return report

    bands: list[float] = []
    for d in chain:
        band = band_of(d.get("tolerance"))
        if band is None:
            report["undeclared"].append(str(d.get("feature")))
        else:
            bands.append(band)
    if report["undeclared"]:
        report["verdict"] = "insufficient_data"
        return report

    report["worst_case"] = _round(sum(bands))
    report["rss"] = _round(math.sqrt(sum(b * b for b in bands)))

    closing = next((d for d in dims if d.get("kind") == "overall_width"), None)
    if closing is None:
        report["verdict"] = "no_closing_tolerance"
        return report
    report["closing_feature"] = str(closing.get("feature"))
    closing_band = band_of(closing.get("tolerance"))
    report["closing_band"] = _round(closing_band)
    if closing_band is None:
        report["verdict"] = "no_closing_tolerance"
        return report

    worst = sum(bands)
    if worst > closing_band + EPS:
        report["verdict"] = "inconsistent"
        report["excess"] = _round(worst - closing_band)
    else:
        report["verdict"] = "consistent"
        report["margin"] = _round(closing_band - worst)
    return report
