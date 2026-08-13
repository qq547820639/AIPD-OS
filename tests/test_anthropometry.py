"""人体工程学百分位数据测试（Task 2）。"""

from __future__ import annotations

import pytest

from aipd_os.cad.anthropometry import (
    available_families,
    get_dimension,
    list_dimensions,
    validate_dimension,
)


def test_available_families_includes_required():
    fams = available_families()
    assert "adult_male" in fams
    assert "adult_female" in fams
    assert "adult_combined" in fams


def test_get_dimension_known_values():
    assert get_dimension("adult_male", 50, "stature_mm") == 1750.0
    assert get_dimension("adult_female", 5, "stature_mm") == 1520.0
    assert get_dimension("adult_combined", 95, "shoulder_width_mm") == 500.0


def test_list_dimensions():
    dims = list_dimensions("adult_male")
    assert "stature_mm" in dims
    assert "shoulder_width_mm" in dims
    assert "hand_length_mm" in dims


def test_get_dimension_unknown_family_raises():
    # 诚实护栏：未知家庭不虚构
    with pytest.raises(ValueError):
        get_dimension("alien", 50, "stature_mm")


def test_get_dimension_unknown_percentile_raises():
    with pytest.raises(ValueError):
        get_dimension("adult_male", 99, "stature_mm")


def test_get_dimension_unknown_dimension_raises():
    with pytest.raises(ValueError):
        get_dimension("adult_male", 50, "wing_span_mm")


def test_validate_dimension_within_and_outside_tolerance():
    ok = validate_dimension("adult_male", 50, "stature_mm", 1752.0)
    assert ok["ok"] is True
    assert ok["expected"] == 1750.0
    assert ok["actual"] == 1752.0
    assert ok["within_tolerance"] is True

    bad = validate_dimension("adult_male", 50, "stature_mm", 1800.0)
    assert bad["ok"] is False
    assert bad["within_tolerance"] is False
