"""人体工程学百分位数据表与查询。

提供确定性的人体尺寸百分位（5/50/95）数据表，用于 CAD 工效评估。
查询未知家庭/百分位/尺寸时抛出 ValueError，绝不虚构数值。
"""

from __future__ import annotations

from typing import Any, Dict, List

# 家庭成员 -> 尺寸 -> 百分位(mm)
# 数值为真实常见取值（如成年男性身高 1750mm）。
ANTHROPOMETRY_TABLE: Dict[str, Dict[str, Dict[int, float]]] = {
    "adult_male": {
        "stature_mm": {5: 1630.0, 50: 1750.0, 95: 1870.0},
        "shoulder_width_mm": {5: 420.0, 50: 470.0, 95: 520.0},
        "hip_width_mm": {5: 330.0, 50: 365.0, 95: 400.0},
        "arm_length_mm": {5: 700.0, 50: 750.0, 95: 800.0},
        "hand_length_mm": {5: 175.0, 50: 190.0, 95: 205.0},
    },
    "adult_female": {
        "stature_mm": {5: 1520.0, 50: 1620.0, 95: 1720.0},
        "shoulder_width_mm": {5: 360.0, 50: 400.0, 95: 440.0},
        "hip_width_mm": {5: 340.0, 50: 380.0, 95: 420.0},
        "arm_length_mm": {5: 620.0, 50: 670.0, 95: 720.0},
        "hand_length_mm": {5: 160.0, 50: 175.0, 95: 190.0},
    },
    "adult_combined": {
        "stature_mm": {5: 1540.0, 50: 1680.0, 95: 1840.0},
        "shoulder_width_mm": {5: 370.0, 50: 430.0, 95: 500.0},
        "hip_width_mm": {5: 330.0, 50: 370.0, 95: 415.0},
        "arm_length_mm": {5: 640.0, 50: 710.0, 95: 790.0},
        "hand_length_mm": {5: 165.0, 50: 182.0, 95: 200.0},
    },
    "child_5th_percentile": {
        "stature_mm": {5: 960.0, 50: 1050.0, 95: 1150.0},
        "shoulder_width_mm": {5: 240.0, 50: 270.0, 95: 300.0},
        "hip_width_mm": {5: 200.0, 50: 230.0, 95: 260.0},
        "arm_length_mm": {5: 380.0, 50: 420.0, 95: 470.0},
        "hand_length_mm": {5: 100.0, 50: 115.0, 95: 130.0},
    },
}


def available_families() -> List[str]:
    """返回所有可用家庭成员名。"""
    return sorted(ANTHROPOMETRY_TABLE.keys())


def list_dimensions(family: str) -> List[str]:
    """返回指定家庭成员的全部尺寸名；家庭不存在时抛 ValueError。"""
    if family not in ANTHROPOMETRY_TABLE:
        raise ValueError(f"unknown anthropometry family: {family!r}")
    return sorted(ANTHROPOMETRY_TABLE[family].keys())


def get_dimension(family: str, percentile: int, dimension: str) -> float:
    """按家庭/百分位/尺寸返回数值。

    家庭、百分位或尺寸不在表中时抛 ValueError，绝不虚构。
    """
    if family not in ANTHROPOMETRY_TABLE:
        raise ValueError(f"unknown anthropometry family: {family!r}")
    dims = ANTHROPOMETRY_TABLE[family]
    if dimension not in dims:
        raise ValueError(f"unknown dimension {dimension!r} for family {family!r}")
    if percentile not in dims[dimension]:
        raise ValueError(f"unknown percentile {percentile} for {family!r}/{dimension!r}")
    return dims[dimension][percentile]


def validate_dimension(
    family: str,
    percentile: int,
    dimension: str,
    value_mm: float,
    tolerance_mm: float = 5.0,
) -> Dict[str, Any]:
    """校验给定尺寸是否在公差范围内符合人体数据表。"""
    expected = get_dimension(family, percentile, dimension)
    within_tolerance = abs(value_mm - expected) <= tolerance_mm
    return {
        "ok": within_tolerance,
        "expected": expected,
        "actual": value_mm,
        "within_tolerance": within_tolerance,
    }


__all__ = [
    "ANTHROPOMETRY_TABLE",
    "available_families",
    "list_dimensions",
    "get_dimension",
    "validate_dimension",
]
