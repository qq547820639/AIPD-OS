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
    CadQueryBackend,
    GOLDEN_PARAM_SPEC,
    _default_golden_params,
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
# 5. 修改前后差异 + 哈希稳定性
# ---------------------------------------------------------------------------

def test_edit_regenerate_differs_and_hashes_change(tmp_path):
    b = CadQueryBackend()
    m0 = _default_model()
    d0 = b.regenerate(m0)["derived"]
    step0 = tmp_path / "m0.step"
    native0 = tmp_path / "m0.py"
    h_step0 = b.export_step(m0, step0)["sha256"]
    h_native0 = b.export_native(m0, native0)["sha256"]

    # 未修改：STEP 与原生源哈希均稳定
    step0b = tmp_path / "m0b.step"
    native0b = tmp_path / "m0b.py"
    assert b.export_step(m0, step0b)["sha256"] == h_step0
    assert b.export_native(m0, native0b)["sha256"] == h_native0

    # 修改参数 -> 体积/包围盒变化
    m1 = b.edit_parameter(m0, "length", 120.0)
    d1 = b.regenerate(m1)["derived"]
    assert d1["volume_mm3"] != d0["volume_mm3"]
    assert d1["bbox"]["x"] == pytest.approx(120.0, abs=0.01)

    # 修改后：STEP 与原生源哈希均变化
    step1 = tmp_path / "m1.step"
    native1 = tmp_path / "m1.py"
    h_step1 = b.export_step(m1, step1)["sha256"]
    h_native1 = b.export_native(m1, native1)["sha256"]
    assert h_step1 != h_step0
    assert h_native1 != h_native0


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