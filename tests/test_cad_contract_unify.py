"""Change Set 9 CAD 参数契约单源 + semantic geometry hash 测试（P0-15 + P0-14）。

覆盖：
- validate_param / validate_geometry_params 以 GOLDEN_PARAM_SPEC 为唯一来源；
- fillet_radius=0.0 / chamfer=0.0 契约合法（edit_parameter 接受 +
  geometry_validity_check valid）；
- 负数参数 → edit_parameter 与 geometry_validity_check 均拒绝；
- hole_diameter >= min(L,W) → 拒绝（共享交叉规则）；
- ContractBackend 完整参数集（含 fillet/chamfer/hole_count）可编辑/校验，
  与 CadQueryBackend 校验行为一致；
- export_step 记录同时含 sha256 与 semantic_geometry_hash；同参数 →
  semantic_geometry_hash 稳定（几何身份）；改参 → 语义 hash 变化；
  字节 sha256 仅声明为「本环境」可复现，跨环境不保证（byte_reproducibility
  profile 见 backends.py 注释）；
- 纯 contract 测试（validate_param / ContractBackend / geometry_validity）在
  任何环境必须运行；仅真正需要真实内核的用例才 ``importorskip("cadquery")``
  （Commit 8B：importorskip 下沉到函数内，不再整模块跳过）。
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


def _require_cq():
    """真实 CAD 内核仅对需要它的用例生效（纯 contract 测试不受影响）。"""
    cq = pytest.importorskip("cadquery")
    return cq


# ---------------------------------------------------------------------------
# 1. validate_param / validate_geometry_params 单源（任何环境必须运行）
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
# 2. CadQueryBackend：fillet/chamfer=0 合法；负数与交叉规则拒绝（需真实内核）
# ---------------------------------------------------------------------------
def test_cadquery_edit_accepts_zero_fillet_chamfer():
    _require_cq()
    b = CadQueryBackend()
    m = b.load_native_model(None)
    m1 = b.edit_parameter(m, "fillet_radius", 0.0)
    m2 = b.edit_parameter(m1, "chamfer", 0.0)
    assert m2["parameters"]["fillet_radius"] == 0.0
    assert m2["parameters"]["chamfer"] == 0.0
    check = b.geometry_validity_check(m2)
    assert check["valid"] is True


def test_cadquery_rejects_negative_and_cross_rule():
    _require_cq()
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
# 3. ContractBackend：完整参数集可编辑/校验（任何环境必须运行，无需内核）
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
def _default_model():
    _require_cq()
    return CadQueryBackend().load_native_model(None)


def test_export_step_records_both_hashes(tmp_path):
    _require_cq()
    b = CadQueryBackend()
    step = tmp_path / "m.step"
    rec = b.export_step(_default_model(), step)
    assert rec["sha256"]
    assert rec["semantic_geometry_hash"]
    assert rec["sha256"] != rec["semantic_geometry_hash"]


def test_semantic_hash_stable_for_same_params_and_changes(tmp_path):
    """正式 hash 契约（Commit 8A + v5.8.1 Commit 13）：

    - ``semantic_geometry_hash`` = 几何身份：同参数两次导出 → 相同；
      改参数 → 变化（身份契约，跨环境保证）；
    - ``sha256``（artifact_byte_hash）= 磁盘字节完整性：同参数两次导出 →
      **本环境**稳定（STEP 头部时间戳已归一化）；跨环境不保证字节可复现
      （除非 ``byte_reproducibility_profile`` 固定同一 Python/CadQuery/
      OpenCASCADE/writer settings）；字节 hash 绝不与语义 hash 互换；
    - 保存后的文件 → ``verify_artifact(sha256)`` 成立；篡改 → 失败
      （tamper 检测见 test_artifact_byte_hash_tamper_detection）。
    """
    _require_cq()
    from aipd_os.cad.evidence import verify_artifact
    b = CadQueryBackend()
    m0 = _default_model()
    step0 = tmp_path / "m0.step"
    step0b = tmp_path / "m0b.step"
    r0 = b.export_step(m0, step0)
    r0b = b.export_step(m0, step0b)
    # 几何身份：同参同形 → 语义 hash 相同（这是身份契约，跨环境成立）
    assert r0["semantic_geometry_hash"] == r0b["semantic_geometry_hash"]
    # 字节 hash：本环境（同 kernel/version + 时间戳归一化）稳定；
    # 跨环境不保证 → 注释明确（byte_reproducibility_profile），不作为身份断言。
    assert r0["sha256"] == r0b["sha256"]

    # 改参：几何身份改变 → 语义 hash 变化（sha256 本环境也变化，但以语义为准）
    m1 = b.edit_parameter(m0, "length", 120.0)
    step1 = tmp_path / "m1.step"
    r1 = b.export_step(m1, step1)
    assert r1["semantic_geometry_hash"] != r0["semantic_geometry_hash"]

    # 保存后的 artifact → 字节 sha256 校验成立（artifact integrity）
    assert verify_artifact(r0) is True


def test_artifact_byte_hash_tamper_detection(tmp_path):
    """artifact_byte_hash 是完整性/篡改检测：保存后 verify 成立，篡改 → FAIL。"""
    _require_cq()
    from aipd_os.cad.evidence import verify_artifact
    b = CadQueryBackend()
    step = tmp_path / "m.step"
    rec = b.export_step(_default_model(), step)
    # 保存后的文件 → verify 成立
    assert verify_artifact(rec) is True
    # 篡改（修改文件内容）→ verify 失败（字节 hash 变化）
    with open(step, "a", encoding="utf-8") as fh:
        fh.write("\n; TAMPERED\n")
    assert verify_artifact(rec) is False


def test_contract_export_step_has_no_semantic_hash(tmp_path):
    """契约后端（无真实几何测量）不伪造 semantic_geometry_hash。"""
    b = ContractBackend()
    model = b.load_native_model(None)
    rec = b.export_step(model, tmp_path / "c.step")
    assert "semantic_geometry_hash" not in rec
    assert rec["sha256"]
