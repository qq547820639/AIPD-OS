"""production_release_gate 单元测试：achieved 修复、多维门检查与新增 evidence_checks。"""
from __future__ import annotations

import json
import runpy
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GATE = REPO / "scripts" / "production_release_gate.py"
_NS = runpy.run_path(str(GATE))


def full_evidence() -> dict:
    ev = {}
    for keys in _NS["REQ"].values():
        for k in keys:
            ev[k] = True
    return ev


def run_gate(manifest: Path, target: str, max_age: float = 8760.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GATE), "--manifest", str(manifest), "--target", target,
         "--max-evidence-age-hours", str(max_age)],
        capture_output=True, text=True,
    )


def write_complete_manifest(tmp_path, **overrides) -> Path:
    m = {
        "runtime": "native_brep",
        "model_version": "1.0.0",
        "bom_version": "1.0.0",
        "drawings_version": "1.0.0",
        "model_part_count": 3,
        "bom_line_count": 3,
        "drawing_count": 3,
        "units": "mm",
        "datum_scheme": "DRF-A",
        "approval_status": "approved",
        "evidence": full_evidence(),
    }
    m.update(overrides)
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(m), encoding="utf-8")
    return p


def get_check(out, name: str) -> dict:
    return next(c for c in out["evidence_checks"] if c["check"] == name)


def test_c0_missing_achieved_none(tmp_path):
    """回归：C0 任一要求缺失时 achieved 必须为 None 且 passed=False。"""
    ev = full_evidence()
    del ev["design_intent"]
    p = write_complete_manifest(tmp_path, evidence=ev)
    r = run_gate(p, "C7")
    out = json.loads(r.stdout)
    assert out["achieved"] is None
    assert out["passed"] is False
    assert out["achieved_reached"] is False
    assert r.returncode == 2


def test_complete_manifest_passes(tmp_path):
    """完整清单达到目标级时通过。"""
    p = write_complete_manifest(tmp_path)
    r = run_gate(p, "C7")
    out = json.loads(r.stdout)
    assert out["achieved"] == "C7"
    assert out["passed"] is True
    assert r.returncode == 0
    assert "evidence_checks" in out
    assert all(c["passed"] for c in out["evidence_checks"])


def test_missing_file_requirement_fails(tmp_path):
    """文件路径要求指向不存在的文件时失败。"""
    p = write_complete_manifest(tmp_path, drawings="missing_drawings.pdf")
    r = run_gate(p, "C7")
    out = json.loads(r.stdout)
    assert out["passed"] is False
    assert r.returncode == 2
    assert any("drawings" in x and "file not found" in x for x in out["missing"])


def test_stale_evidence_fails(tmp_path):
    """证据时间戳超过最大时效时失败。"""
    p = write_complete_manifest(tmp_path, timestamp="2020-01-01T00:00:00Z")
    r = run_gate(p, "C7", max_age=1)
    out = json.loads(r.stdout)
    assert out["passed"] is False
    assert r.returncode == 2
    assert any("stale" in f for f in out["failures"])
    assert get_check(out, "evidence_not_expired")["passed"] is False


def test_gdt_not_covering_ctq_fails(tmp_path):
    """gdt 未覆盖某个 ctq feature 时证据门失败。"""
    p = write_complete_manifest(
        tmp_path,
        ctq=[{"feature": "hole_a", "inspection_method": "CMM"}],
        gdt=[{"feature": "slot_b"}],
    )
    r = run_gate(p, "C2")
    out = json.loads(r.stdout)
    assert out["passed"] is False
    assert r.returncode == 2
    assert get_check(out, "gdt_covers_ctq")["passed"] is False


def test_ctq_missing_inspection_fails(tmp_path):
    """ctq 条目缺少 inspection_method / test_method 时证据门失败。"""
    p = write_complete_manifest(tmp_path, ctq=[{"feature": "hole_a"}])
    r = run_gate(p, "C2")
    out = json.loads(r.stdout)
    assert out["passed"] is False
    assert r.returncode == 2
    assert get_check(out, "ctq_has_inspection")["passed"] is False


def test_drawing_model_version_mismatch_fails(tmp_path):
    """drawings_version != model_version 时证据门失败。"""
    p = write_complete_manifest(tmp_path, drawings_version="2.0.0")
    r = run_gate(p, "C2")
    out = json.loads(r.stdout)
    assert out["passed"] is False
    assert r.returncode == 2
    assert get_check(out, "drawing_cad_same_revision")["passed"] is False


def test_consistent_c2_manifest_passes(tmp_path):
    """完全一致的 C2 清单通过，且所有 evidence_checks 通过。"""
    p = write_complete_manifest(tmp_path)
    r = run_gate(p, "C2")
    out = json.loads(r.stdout)
    assert out["passed"] is True
    assert out["achieved"] == "C7"
    assert r.returncode == 0
    assert all(c["passed"] for c in out["evidence_checks"])
