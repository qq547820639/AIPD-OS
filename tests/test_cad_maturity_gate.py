"""cad_maturity_gate 单元测试：统一 C0..C7 体系的行为。"""
from __future__ import annotations

import json
import runpy
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GATE = REPO / "scripts" / "cad_maturity_gate.py"
_NS = runpy.run_path(str(GATE))
LEVELS = _NS["LEVELS"]


def full_evidence() -> dict:
    ev = {}
    for keys in _NS["REQUIREMENTS"].values():
        for k in keys:
            ev[k] = True
    return ev


def run_gate(manifest: Path, target: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GATE), "--manifest", str(manifest), "--target", target],
        capture_output=True, text=True,
    )


def make_manifest(tmp_path: Path, runtime: str, evidence: dict) -> Path:
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps({"runtime": runtime, "evidence": evidence}), encoding="utf-8")
    return p


def test_faceted_brep_capped_at_C1(tmp_path):
    """faceted_brep 运行时即使证据齐全，成熟度也封顶在 C1。"""
    p = make_manifest(tmp_path, "faceted_brep", full_evidence())
    r = run_gate(p, "C7")
    out = json.loads(r.stdout)
    assert out["faceted_brep_capped"] is True
    assert out["runtime_ceiling"] == "C1"
    assert out["reached_level"] in LEVELS
    assert LEVELS.index(out["reached_level"]) <= LEVELS.index("C1")
    assert out["target_passed"] is False
    assert r.returncode != 0


def test_native_brep_reaches_expected_level(tmp_path):
    """native_brep 运行时证据齐全时可达到最高级 C7。"""
    p = make_manifest(tmp_path, "native_brep", full_evidence())
    r = run_gate(p, "C7")
    out = json.loads(r.stdout)
    assert out["reached_level"] == "C7"
    assert out["target_passed"] is True
    assert r.returncode == 0


def test_cad_L_target_rejected(tmp_path):
    """--target 必须为 C0..C7，遗留 CAD-L 目标应被拒绝。"""
    p = make_manifest(tmp_path, "native_brep", full_evidence())
    r = run_gate(p, "CAD-L3")
    assert r.returncode != 0
    assert "invalid choice" in r.stderr
