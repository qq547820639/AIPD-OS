"""P0-2 真实 CAD 黄金闭环测试（tests/test_cad_golden_loop.py）。

当真实 CadQuery/OpenCASCADE 内核可导入时运行（``pytest.importorskip``），否则
跳过。覆盖完整闭环：多参数 + 特征（孔/圆角/倒角）-> 改参 -> 重生成 -> STEP
导出 -> 可编辑原生源导出 -> 重载 -> 几何有效性 -> 产物哈希与工具版本 ->
修改前后差异 -> Product Truth 写回。

STEP 往返断言：实体数、面数、体积、包围盒、isValid。
无内核时跳过（importorskip 门控真实内核，不得把跳过当通过）。
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

cq = pytest.importorskip("cadquery")

from aipd_os.cad.backends import (  # noqa: E402
    GOLDEN_PARAM_SPEC,
    CadQueryBackend,
    _default_golden_params,
    _through_holes,
)
from aipd_os.cad.evidence import verify_artifact  # noqa: E402
from aipd_os.cad.writeback import propagate_cad_change  # noqa: E402

CQ_VERSION = getattr(cq, "__version__", "n/a")


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _default_model():
    return CadQueryBackend().load_native_model(None)


# ---------------------------------------------------------------------------
# 1. 真实内核可用性与版本
# ---------------------------------------------------------------------------

def test_real_kernel_available_and_version():
    b = CadQueryBackend()
    assert b.is_available() is True
    assert b.capability_status() == "full"
    assert b.maturity_ceiling() == "C2"
    assert b.tool_version() == CQ_VERSION


def test_parameter_spec_multifeature():
    """黄金模型含多参数 + 多特征（孔/圆角/倒角）。"""
    assert set(GOLDEN_PARAM_SPEC) == {
        "length", "width", "thickness", "hole_diameter",
        "hole_count", "fillet_radius", "chamfer",
    }
    m = _default_model()
    names = [p["name"] for p in CadQueryBackend().list_parameters(m)]
    assert set(names) == set(GOLDEN_PARAM_SPEC)


# ---------------------------------------------------------------------------
# 2. 建模 / 测量（真实内核）
# ---------------------------------------------------------------------------

def test_golden_model_build_and_measure():
    b = CadQueryBackend()
    regen = b.regenerate(_default_model())
    d = regen["derived"]
    assert d["is_valid"] is True
    assert d["solid_count"] == 1
    assert d["volume_mm3"] > 0
    assert d["face_count"] >= 6
    assert d["bbox"]["x"] == pytest.approx(100.0, abs=0.01)
    assert d["bbox"]["y"] == pytest.approx(50.0, abs=0.01)
    assert d["bbox"]["z"] == pytest.approx(10.0, abs=0.01)


# ---------------------------------------------------------------------------
# 3. STEP 导出 + 往返断言
# ---------------------------------------------------------------------------

def test_step_export_roundtrip(tmp_path):
    b = CadQueryBackend()
    model = _default_model()
    step = tmp_path / "golden.step"
    rec = b.export_step(model, step)
    assert step.is_file()
    assert rec["sha256"] == _sha(step)  # 记录哈希与磁盘一致
    assert rec["tool"] == "cadquery"
    assert rec["tool_version"] == CQ_VERSION
    assert "C2" in rec["maturity_evidence"]
    assert verify_artifact(rec) is True

    # STEP 往返：导入并断言实体/面/体积/包围盒/isValid
    loaded = cq.importers.importStep(str(step))
    s = loaded.val()
    assert s.isValid() is True
    assert len(loaded.solids().vals()) == 1
    m = b._measure(loaded)
    d = b.regenerate(model)["derived"]
    assert m["volume_mm3"] == pytest.approx(d["volume_mm3"], rel=1e-6)
    assert m["face_count"] == d["face_count"]
    for axis in ("x", "y", "z"):
        assert m["bbox"][axis] == pytest.approx(d["bbox"][axis], abs=0.01)


# ---------------------------------------------------------------------------
# 4. 可编辑原生源导出 + 独立执行 + 重载
# ---------------------------------------------------------------------------

def test_export_native_executable_and_reload(tmp_path):
    b = CadQueryBackend()
    model = _default_model()
    native = tmp_path / "golden_bracket.py"
    rec = b.export_native(model, native)
    assert native.is_file()
    assert rec["sha256"] == _sha(native)

    # 该源文件可被独立执行重生成模型
    r = subprocess.run([sys.executable, str(native)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "built True" in r.stdout

    # 通过 EXPORT_STEP 环境变量可同时写出 STEP
    step2 = tmp_path / "from_source.step"
    env = dict(os.environ)
    env["EXPORT_STEP"] = str(step2)
    r2 = subprocess.run([sys.executable, str(native)], env=env,
                        capture_output=True, text=True)
    assert r2.returncode == 0, r2.stderr
    assert step2.is_file() and step2.stat().st_size > 0

    # 重载：从原生源恢复可编辑参数（特征与参数一致，且不执行副作用代码）
    reloaded = b.load_native_model(native)
    assert reloaded["name"] == model["name"]
    assert reloaded["parameters"] == model["parameters"]
    assert reloaded["source_path"] == str(native)
    # 重载后可继续改参并重生成
    edited = b.edit_parameter(reloaded, "width", 60.0)
    d = b.regenerate(edited)["derived"]
    assert d["bbox"]["y"] == pytest.approx(60.0, abs=0.01)


# ---------------------------------------------------------------------------
# 4b. 声明参数必须被几何实现（孔数 / 孔径 / 孔位逐一对账）
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("n", [1, 2, 4, 7])
def test_declared_hole_pattern_is_realized_geometrically(n):
    """声明 n 个孔 ⇒ 实体上必须有 n 个等距、同半径的整圈通孔。

    只比数量不比位置的话，孔位累加那类缺陷看不出来（见
    :func:`test_hole_gate_fires_on_legacy_cumulative_center_loop`）。
    """
    b = CadQueryBackend()
    params = _default_golden_params()
    L = params["length"]
    check = b.geometry_validity_check(b.edit_parameter(_default_model(),
                                                       "hole_count", n))
    assert check["valid"] is True, check["errors"]
    assert check["checks"]["declared_features"] is True
    holes = check["checks"]["measurement"]["through_holes"]
    assert [h["center"][0] for h in holes] == pytest.approx(
        [-L / 2 + L * (i + 1) / (n + 1) for i in range(n)], abs=1e-6)
    assert all(h["center"][1] == pytest.approx(0.0, abs=1e-6) for h in holes)
    assert all(abs(h["radius"] - params["hole_diameter"] / 2) < 1e-6
               for h in holes)
    assert all(h["depth_mm"] == pytest.approx(params["thickness"], abs=1e-6)
               for h in holes)


def test_native_source_template_realizes_declared_holes(tmp_path):
    """渲染出的 .py 独立执行后，几何仍必须等于声明参数（模板路径同源校验）。

    ``geometry_validity_check`` 走的是 ``_build``，模板是另一份代码；
    两者不一致时发布的黄金工件就是错的，故必须独立量一次。
    """
    b = CadQueryBackend()
    native = tmp_path / "pattern.py"
    b.export_native(b.edit_parameter(_default_model(), "hole_count", 4), native)
    out = tmp_path / "pattern.step"
    env = dict(os.environ)
    env["EXPORT_STEP"] = str(out)
    r = subprocess.run([sys.executable, str(native)], env=env,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert out.is_file() and out.stat().st_size > 0
    holes = b._measure(cq.importers.importStep(str(out)))["through_holes"]
    params = _default_golden_params()
    n = 4
    assert [h["center"][0] for h in holes] == pytest.approx(
        [-params["length"] / 2 + params["length"] * (i + 1) / (n + 1)
         for i in range(n)], abs=1e-6)


def test_through_hole_measurement_ignores_partial_arc_faces():
    """量具负控：圆角的四分之一弧柱面不得被读成孔。

    半径由侧面积反解（r = A / 2·pi·h），部分圆弧会反解出偏小的 r，
    因此额外用「包围盒必须是 2r x 2r」把非整圈柱面排除。
    """
    corner_only = (cq.Workplane("XY").box(40, 20, 10)
                   .edges("|Z").fillet(3.0).solids().vals()[0])
    assert _through_holes(corner_only) == []

    drilled = (cq.Workplane("XY").box(40, 20, 10).faces(">Z").workplane()
               .pushPoints([(5.0, 0.0)]).hole(6.0).solids().vals()[0])
    holes = _through_holes(drilled)
    assert len(holes) == 1
    assert holes[0]["radius"] == pytest.approx(3.0, abs=1e-6)
    assert holes[0]["center"] == pytest.approx([5.0, 0.0], abs=1e-6)
    assert holes[0]["depth_mm"] == pytest.approx(10.0, abs=1e-6)


def test_hole_gate_fires_on_legacy_cumulative_center_loop():
    """反证（门的效力）：退回逐点 center() 写法时本门必须判红，且 n=1 仍为绿。

    ``Workplane.center()`` 相对**当前笔位**偏移而 ``hole()`` 不重置笔位，
    所以偏移会累加：实测 n=4 只钻出 3 个孔位 (-40, -30, 0)、其中两孔重合，
    n=1 时恰好正确。只断言 n=4 判红不足以证明门不是"永远红"，故两向都测。
    """
    def legacy_build(self, model):
        p = model["parameters"]
        L = float(p["length"])
        plate = cq.Workplane("XY").box(L, float(p["width"]),
                                       float(p["thickness"]))
        if float(p["fillet_radius"]) > 0:
            plate = plate.edges("|Z").fillet(float(p["fillet_radius"]))
        for i in range(max(1, int(p["hole_count"]))):
            cx = (L / (int(p["hole_count"]) + 1)) * (i + 1) - L / 2
            plate = plate.faces(">Z").workplane().center(cx, 0).hole(
                float(p["hole_diameter"]))
        return plate

    b = CadQueryBackend()
    original = CadQueryBackend._build
    CadQueryBackend._build = legacy_build
    try:
        bad = b.geometry_validity_check(
            b.edit_parameter(_default_model(), "hole_count", 4))
        ok_single = b.geometry_validity_check(
            b.edit_parameter(_default_model(), "hole_count", 1))
    finally:
        CadQueryBackend._build = original

    assert bad["valid"] is False
    assert bad["checks"]["declared_features"] is False
    assert any("through-hole" in e for e in bad["errors"]), bad["errors"]
    assert ok_single["valid"] is True, ok_single["errors"]


# ---------------------------------------------------------------------------
# 5. 修改前后差异 + 哈希稳定性
# ---------------------------------------------------------------------------

def test_edit_regenerate_differs_and_hashes_change(tmp_path):
    """正式 hash 契约（v5.8.1 Commit 13）：

    - artifact_byte_hash（sha256）：同参数两次导出 → 本环境稳定；改参数 →
      变化（字节完整性）；
    - semantic_geometry_hash：同参数两次导出 → 相同；改参数 → 变化
      （几何身份，跨环境契约）。
    """
    b = CadQueryBackend()
    m0 = _default_model()
    d0 = b.regenerate(m0)["derived"]
    step0 = tmp_path / "m0.step"
    native0 = tmp_path / "m0.py"
    r_step0 = b.export_step(m0, step0)
    h_step0 = r_step0["sha256"]
    h_native0 = b.export_native(m0, native0)["sha256"]

    # 未修改：STEP 与原生源哈希均稳定（本环境 byte reproducibility）
    step0b = tmp_path / "m0b.step"
    native0b = tmp_path / "m0b.py"
    r_step0b = b.export_step(m0, step0b)
    assert r_step0b["sha256"] == h_step0
    assert b.export_native(m0, native0b)["sha256"] == h_native0
    # 几何身份：同参同形 → semantic hash 相同
    assert r_step0b["semantic_geometry_hash"] == r_step0["semantic_geometry_hash"]

    # 修改参数 -> 体积/包围盒变化
    m1 = b.edit_parameter(m0, "length", 120.0)
    d1 = b.regenerate(m1)["derived"]
    assert d1["volume_mm3"] != d0["volume_mm3"]
    assert d1["bbox"]["x"] == pytest.approx(120.0, abs=0.01)

    # 修改后：STEP 与原生源哈希均变化（字节）；语义 hash 也变化（几何身份）
    step1 = tmp_path / "m1.step"
    native1 = tmp_path / "m1.py"
    r_step1 = b.export_step(m1, step1)
    h_step1 = r_step1["sha256"]
    h_native1 = b.export_native(m1, native1)["sha256"]
    assert h_step1 != h_step0
    assert h_native1 != h_native0
    assert r_step1["semantic_geometry_hash"] != r_step0["semantic_geometry_hash"]


# ---------------------------------------------------------------------------
# 6. 几何有效性（真实内核）
# ---------------------------------------------------------------------------

def test_geometry_validity_valid_and_kernel():
    b = CadQueryBackend()
    check = b.geometry_validity_check(_default_model())
    assert check["valid"] is True
    assert check["checks"]["kernel_build"] is True
    assert check["checks"]["measurement"]["is_valid"] is True


def test_geometry_validity_rejects_invalid_params():
    b = CadQueryBackend()
    bad = dict(_default_golden_params())
    bad["thickness"] = -5.0
    check = b.geometry_validity_check({"name": "bad", "parameters": bad})
    assert check["valid"] is False
    assert any("thickness" in e for e in check["errors"])


def test_edit_parameter_rejects_unknown_and_below_min(tmp_path):
    b = CadQueryBackend()
    m = _default_model()
    with pytest.raises(KeyError):
        b.edit_parameter(m, "not_a_param", 1.0)
    with pytest.raises(ValueError):
        b.edit_parameter(m, "thickness", 0.5)  # 低于 min=2.0


# ---------------------------------------------------------------------------
# 7. Product Truth 写回
# ---------------------------------------------------------------------------

def test_product_truth_writeback():
    manifest = {
        "model": {"revision": "R1", "parameters": {}},
        "spec": {"revision": "R1", "content_ref": "spec.md"},
        "bom": {"revision": "R1", "content_ref": "bom.csv"},
        "manual": {"revision": "R1", "content_ref": "manual.md"},
        "verification_plan": {"revision": "R1", "content_ref": "vp.md"},
    }
    out = propagate_cad_change(
        manifest, {"length": 120.0, "width": 60.0},
        tool_version=f"cadquery/{CQ_VERSION}")
    assert out["model"]["revision"] == "R2"
    assert out["model"]["parameters"]["length"] == 120.0
    assert out["model"]["last_change"]["tool_version"] == f"cadquery/{CQ_VERSION}"
    for key in ("spec", "bom", "manual", "verification_plan"):
        assert out[key]["revision"] == "R2"
        assert out[key]["regeneration_needed"] is True
        assert out[key]["cad_source_revision"] == "R2"
    # 原 manifest 不被改动
    assert manifest["model"]["revision"] == "R1"


# ---------------------------------------------------------------------------
# 8. 本地 B-Rep 适配器集成（真实内核通道）
# ---------------------------------------------------------------------------

def test_local_brep_adapter_executes_real_closure(tmp_path, monkeypatch):
    from aipd_os.tool_adapters.local_brep_adapter import LocalBrepAdapter

    monkeypatch.setenv("AIPD_OUTPUT_DIR", str(tmp_path))
    adapter = LocalBrepAdapter()
    out = adapter.execute({"parameters": {"length": 120.0}})
    assert out["backend"] == "cadquery"
    assert out["capability_status"] == "full"
    assert out["maturity_ceiling"] == "C2"
    assert out["tool_version"] == CQ_VERSION
    assert out["derived_geometry"]["is_valid"] is True
    assert out["derived_geometry"]["bbox"]["x"] == pytest.approx(120.0, abs=0.01)
    assert out["geometry_validity"]["valid"] is True
    assert out["artifacts"]["step"]["path"]
    assert Path(out["artifacts"]["step"]["path"]).is_file()
    assert Path(out["artifacts"]["native_source"]["path"]).is_file()
    # 适配器 discover 与 collect_artifacts 一致
    assert adapter.discover()["maturity_ceiling"] == "C2"
    assert adapter.collect_artifacts(out) == [
        out["artifacts"]["step"]["path"], out["artifacts"]["native_source"]["path"],
    ]
