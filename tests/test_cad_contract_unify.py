"""Change Set 9 CAD 参数契约单源 + semantic geometry hash 测试（P0-15 + P0-14）。

覆盖：
- validate_param / validate_geometry_params 以 GOLDEN_PARAM_SPEC 为唯一来源；
- fillet_radius=0.0 / chamfer=0.0 契约合法（edit_parameter 接受 +
  geometry_validity_check valid）；
- 负数参数 → edit_parameter 与 geometry_validity_check 均拒绝；
- hole_diameter >= min(L,W) → 拒绝（共享交叉规则）；
- ContractBackend 完整参数集（含 fillet/chamfer/hole_count）可编辑/校验，
  与 CadQueryBackend 校验行为一致；
- export_step 记录同时含 sha256 与 semantic_geometry_hash；同参数两次导出
  两个 hash 各自稳定；改参 → 两者都变化。
"""
from __future__ import annotations

import pytest

from aipd_os.cad.backends import (
    GOLDEN_PARAM_SPEC,
    CadQueryBackend,
    ContractBackend,
    _default_golden_params,
    validate_geometry_params,
    validate_param,
)


# ---------------------------------------------------------------------------
# 1. validate_param / validate_geometry_params 单源
# ---------------------------------------------------------------------------
def test_validate_param_zero_allowed_for_fillet_chamfer():
    assert validate_param("fillet_radius", 0.0) is None
    assert validate_param("chamfer", 0.0) is None


def test_validate_param_rejects_negative_and_below_min():
    assert validate_param("length", -1.0) is not None
    assert validate_param("thickness", 1.5) is not None   # < min=2.0
    assert validate_param("hole_diameter", 0.5) is not None  # < min=1.0
    assert validate_param("hole_count", 0) is not None    # < min=1
    assert validate_param("not_a_param", 1.0) is not None


def test_validate_geometry_params_cross_rule():
    good = _default_golden_params()
    assert validate_geometry_params(good) == []
    bad = dict(good)
    bad["hole_diameter"] = 100.0  # >= min(100, 50) → 交叉规则拒绝
    errors = validate_geometry_params(bad)
    assert any("hole_diameter" in e for e in errors)


# ---------------------------------------------------------------------------
# 2. CadQueryBackend：fillet/chamfer=0 合法；负数与交叉规则拒绝
# ---------------------------------------------------------------------------
def test_cadquery_edit_accepts_zero_fillet_chamfer():
    b = CadQueryBackend()
    m = b.load_native_model(None)
    m1 = b.edit_parameter(m, "fillet_radius", 0.0)
    m2 = b.edit_parameter(m1, "chamfer", 0.0)
    assert m2["parameters"]["fillet_radius"] == 0.0
    assert m2["parameters"]["chamfer"] == 0.0
    check = b.geometry_validity_check(m2)
    assert check["valid"] is True


def test_cadquery_rejects_negative_and_cross_rule():
    b = CadQueryBackend()
    m = b.load_native_model(None)
    with pytest.raises(ValueError):
        b.edit_parameter(m, "thickness", -5.0)
    bad = dict(_default_golden_params())
    bad["hole_diameter"] = 100.0
    check = b.geometry_validity_check({"name": "bad", "parameters": bad})
    assert check["valid"] is False
    assert any("hole_diameter" in e for e in check["errors"])


# ---------------------------------------------------------------------------
# 3. ContractBackend：完整参数集可编辑/校验，与 CadQueryBackend 行为一致
# ---------------------------------------------------------------------------
def test_contract_full_param_set_editable_and_valid():
    b = ContractBackend()
    m = b.load_native_model(None)
    names = {p["name"] for p in b.list_parameters(m)}
    assert set(GOLDEN_PARAM_SPEC) <= names  # 完整参数集（含 fillet/chamfer/hole_count）
    m1 = b.edit_parameter(m, "fillet_radius", 0.0)
    m2 = b.edit_parameter(m1, "chamfer", 0.0)
    m3 = b.edit_parameter(m2, "hole_count", 3)
    check = b.geometry_validity_check(m3)
    assert check["valid"] is True
    # 共享校验：负数拒绝
    with pytest.raises(ValueError):
        b.edit_parameter(m, "thickness", -5.0)
    bad = dict(m["parameters"])
    bad["hole_diameter"] = 100.0
    assert b.geometry_validity_check({"name": "c", "parameters": bad})["valid"] is False


# ---------------------------------------------------------------------------
# 4. export_step 同时含 sha256 与 semantic_geometry_hash（P0-14，需真实内核）
# ---------------------------------------------------------------------------
cq = pytest.importorskip("cadquery")


def _default_model():
    return CadQueryBackend().load_native_model(None)


def test_export_step_records_both_hashes(tmp_path):
    b = CadQueryBackend()
    step = tmp_path / "m.step"
    rec = b.export_step(_default_model(), step)
    assert rec["sha256"]
    assert rec["semantic_geometry_hash"]
    assert rec["sha256"] != rec["semantic_geometry_hash"]


def test_semantic_hash_stable_for_same_params_and_changes(tmp_path):
    b = CadQueryBackend()
    m0 = _default_model()
    step0 = tmp_path / "m0.step"
    step0b = tmp_path / "m0b.step"
    r0 = b.export_step(m0, step0)
    r0b = b.export_step(m0, step0b)
    # 同参数两次导出：字节 hash 与语义 hash 各自稳定
    assert r0["sha256"] == r0b["sha256"]
    assert r0["semantic_geometry_hash"] == r0b["semantic_geometry_hash"]

    # 改参：两者都变化
    m1 = b.edit_parameter(m0, "length", 120.0)
    step1 = tmp_path / "m1.step"
    r1 = b.export_step(m1, step1)
    assert r1["sha256"] != r0["sha256"]
    assert r1["semantic_geometry_hash"] != r0["semantic_geometry_hash"]


def test_contract_export_step_has_no_semantic_hash(tmp_path):
    """契约后端（无真实几何测量）不伪造 semantic_geometry_hash。"""
    b = ContractBackend()
    model = b.load_native_model(None)
    rec = b.export_step(model, tmp_path / "c.step")
    assert "semantic_geometry_hash" not in rec
    assert rec["sha256"]
