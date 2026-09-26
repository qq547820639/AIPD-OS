"""发布门的「文件真的在、哈希真的对」这一项，对**清单形状**到底到不到得了。

门里 `FILE_KEYS` 那一栏的自述是「值可能引用一个必须存在且哈希对得上的文件路径」。
但 `resolve_path` 只认字符串与 `{path, sha256}` 字典，而**模板里这些键本来就是数组**
（`assets/templates/production_cad_manifest.json`：`drawings: []`、`step_assemblies: []`、
`cae_reports: []`、`physical_evidence: []`），`aipd release manifest` 产出的
`evidence.drawings[]` 也是数组。数组进 `resolve_path` 得到 `(None, None)`，
两条使用点（`check_requirement` 的 (b) 与 `file_openable`）都 `continue` 掉 ⇒
一份图纸全丢了、全被改过的包照样读成「所有引用文件可打开」。

这一片先把它证伪（下面的用例在修之前必须红），再补上真开火的判据。
装配级 STEP 要接进发布证据（第 21 片的另一半），接的必须是**有牙的**那道核对。
"""
from __future__ import annotations

import hashlib
import json
import runpy
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GATE = REPO / "scripts" / "production_release_gate.py"
_NS = runpy.run_path(str(GATE))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_gate(manifest: Path, target: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GATE), "--manifest", str(manifest), "--target", target,
         "--max-evidence-age-hours", "8760"],
        capture_output=True, text=True)


def _base_evidence() -> dict:
    ev = {}
    for keys in _NS["REQ"].values():
        for k in keys:
            ev[k] = True
    return ev


def _pack(tmp_path: Path, **overrides) -> Path:
    m = {"runtime": "native_brep", "model_version": "1.0.0", "bom_version": "1.0.0",
         "drawings_version": "1.0.0", "model_part_count": 3, "bom_line_count": 3,
         "drawing_count": 3, "units": "mm", "datum_scheme": "DRF-A",
         "approval_status": "approved",
         # 记录号是生产者一定会写的两列（`ctq[].record_id` 见 release_manifest.py:86，
         # `gdt[].ctq_record_id` 见同文件 :257/:293），门禁按记录号核对覆盖。
         "ctq": [{"record_id": "T-001", "feature": "hole_a",
                  "inspection_method": "CMM"}],
         "gdt": [{"feature": "hole_a", "ctq_record_id": "T-001"}],
         "timestamp": "2026-08-01T00:00:00Z",
         "eco": {"coverage": "complete", "artifacts": 2, "covered": 2,
                 "uncovered": [], "unverified": [], "undetermined": []},
         "evidence": _base_evidence()}
    m.update(overrides)
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(m), encoding="utf-8")
    return p


def _get_check(out: dict, name: str) -> dict:
    return next(c for c in out["evidence_checks"] if c["check"] == name)


class TestFileKeysAcceptLists:
    """resolve_path 之于数组：这一组直接打在小函数上，不绕整道门。"""

    def test_a_list_of_paths_yields_every_entry(self):
        got = _NS["resolve_paths"](["a.step", {"path": "b.step", "sha256": "deadbeef"}])
        assert got == [("a.step", None), ("b.step", "deadbeef")]

    def test_a_single_value_still_works(self):
        assert _NS["resolve_paths"]({"path": "x.dxf", "sha256": "ab"}) == [("x.dxf", "ab")]
        assert _NS["resolve_paths"]("y.dxf") == [("y.dxf", None)]

    def test_non_file_values_yield_nothing(self):
        assert _NS["resolve_paths"](True) == []
        assert _NS["resolve_paths"](None) == []
        assert _NS["resolve_paths"]([]) == []
        # 空串/URL 不是路径（沿用旧判据，不扩权）
        assert _NS["resolve_paths"](["", "https://x/y"]) == []


class TestOpenableFiresOnLists:
    def test_a_missing_file_inside_a_list_is_reported(self, tmp_path):
        p = _pack(tmp_path, drawings=[{"path": "gone.dxf", "sha256": "aa"}])
        out = json.loads(run_gate(p, "C6").stdout)
        check = _get_check(out, "file_openable")
        assert check["passed"] is False
        assert "gone.dxf" in check["detail"]

    def test_a_second_list_entry_is_not_skipped(self, tmp_path):
        """只核第一条等于没核：第二条丢了必须也报。"""
        (tmp_path / "one.dxf").write_text("one\n", encoding="utf-8")
        p = _pack(tmp_path, drawings=[{"path": "one.dxf", "sha256": _sha(tmp_path / "one.dxf")},
                                      {"path": "two.dxf", "sha256": "aa"}])
        out = json.loads(run_gate(p, "C6").stdout)
        check = _get_check(out, "file_openable")
        assert check["passed"] is False and "two.dxf" in check["detail"]

    def test_every_entry_present_passes(self, tmp_path):
        names = ("one.dxf", "two.dxf")
        for n in names:
            (tmp_path / n).write_text(n + "\n", encoding="utf-8")
        p = _pack(tmp_path, drawings=[{"path": n, "sha256": _sha(tmp_path / n)}
                                      for n in names])
        out = json.loads(run_gate(p, "C6").stdout)
        assert _get_check(out, "file_openable")["passed"] is True


class TestHashMatchesFiresOnLists:
    def test_an_entry_whose_content_changed_is_a_mismatch(self, tmp_path):
        dxf = tmp_path / "bracket.dxf"
        dxf.write_text("原始几何\n", encoding="utf-8")
        good = _sha(dxf)
        dxf.write_text("被换过的几何\n", encoding="utf-8")
        p = _pack(tmp_path, drawings=[{"path": dxf.name, "sha256": good}])
        out = json.loads(run_gate(p, "C6").stdout)
        errs = [x for x in out["missing"] if "drawings" in x]
        assert errs and any("sha256 mismatch" in x for x in errs), out["missing"]

    def test_a_stale_sidecar_hash_is_not_reused_as_the_expected_one(self, tmp_path):
        """哈希必须来自清单里写的那个值，不是现场算——现场算等于永不失配。"""
        dxf = tmp_path / "assy.step"
        dxf.write_text("step\n", encoding="utf-8")
        p = _pack(tmp_path, step_assemblies=[{"path": dxf.name, "sha256": "0" * 64}])
        out = json.loads(run_gate(p, "C6").stdout)
        assert any("step_assemblies" in x and "sha256 mismatch" in x for x in out["missing"]), \
            out["missing"]

    def test_a_path_that_is_not_in_the_manifest_cannot_be_proved(self, tmp_path):
        """没写 sha256 的条目只核存在，不假装核过哈希。"""
        dxf = tmp_path / "part.step"
        dxf.write_text("step\n", encoding="utf-8")
        p = _pack(tmp_path, step_parts=[dxf.name])
        out = json.loads(run_gate(p, "C6").stdout)
        assert not any("step_parts" in x for x in out["missing"]), out["missing"]
        assert _get_check(out, "file_openable")["passed"] is True


class TestGateStillRejectsWhatItRejectedBefore:
    """收紧不能把原来对的东西判错：字符串形状与布尔形状的旧行为原样保留。"""

    def test_a_string_value_still_reports_missing_file(self, tmp_path):
        p = _pack(tmp_path, drawings="missing_drawings.pdf")
        out = json.loads(run_gate(p, "C6").stdout)
        assert any("drawings" in x and "file not found" in x for x in out["missing"])

    def test_a_boolean_evidence_is_not_read_as_a_path(self, tmp_path):
        p = _pack(tmp_path)
        out = json.loads(run_gate(p, "C7").stdout)
        assert out["passed"] is True
        assert _get_check(out, "file_openable")["passed"] is True
