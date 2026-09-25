"""证据侧车的路径必须**每个产物一个**（F-EVID-03）。

第 22 片的端到端撞出来：`assy.step` 与 `assy.dxf` 的侧车都拼成 `assy.evidence.json`
——旧写法「拿产物路径换个后缀」把 `.step` / `.dxf` 换掉了，只剩干名。
于是「同一目录里先出总装 STEP 再出装配图」会把 STEP 的证据**静默顶掉**，
而 `aipd release manifest` 读到的是那张图的侧车。侧车是这一路唯一的机器可读凭据，
顶掉的后果不是报错而是**拿 A 的凭据给 B 盖章**；字段名恰好不重合时才发现（本次），
重合时（两份都是图纸派生）读到的就是一套自洽但属于别人的证据。

修法只有一条纪律：**侧车名的拼法收进一个函数**，四个写入点与所有读取点都走它。
本文件用字面量钉住拼法本身（不跟着助手函数一起错）。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from aipd_os.cad.evidence import sidecar_path, write_evidence_sidecar
from aipd_os.release_manifest import _evidence_path

cadquery = pytest.importorskip("cadquery", reason="CAD 内核为可选 extra")


class TestTheSpellingIsUniquePerArtifact:
    def test_the_suffix_is_kept_in_the_sidecar_name(self, tmp_path):
        assert sidecar_path(tmp_path / "assy.step") == tmp_path / "assy.step.evidence.json"
        assert sidecar_path(tmp_path / "assy.dxf") == tmp_path / "assy.dxf.evidence.json"
        assert sidecar_path(tmp_path / "assy.md") == tmp_path / "assy.md.evidence.json"

    def test_two_artifacts_with_the_same_stem_get_two_sidecars(self, tmp_path):
        step = sidecar_path(tmp_path / "assy.step")
        dxf = sidecar_path(tmp_path / "assy.dxf")
        assert step != dxf, "同干名的两个产物共用了侧车，后写的会顶掉前一份"

    def test_the_reader_uses_the_same_spelling_as_the_writer(self, tmp_path):
        assert _evidence_path(tmp_path / "bracket.dxf") == sidecar_path(
            tmp_path / "bracket.dxf")

    def test_a_name_without_a_suffix_still_gets_a_unique_sidecar(self, tmp_path):
        assert sidecar_path(tmp_path / "ASSY") == tmp_path / "ASSY.evidence.json"


class TestWritersDoNotClobberEachOther:
    @pytest.fixture()
    def two_products(self, tmp_path):
        """同干名的两份真产物：一份总装 STEP、一张装配图。"""
        import cadquery as cq

        from aipd_os.cad.assembly import export_assembly_step, generate_assembly_drawing

        src = tmp_path / "p.step"
        cq.exporters.export(cq.Workplane("XY").box(20, 8, 20), str(src))
        man = tmp_path / "assy.json"
        man.write_text(json.dumps({"parts": [
            {"name": "bracket", "step": src.name, "balloon": 1, "offset": [0, 0, 0]}]}),
            encoding="utf-8")
        step = tmp_path / "assy.step"
        export_assembly_step(step, manifest=str(man), part_name="ASSY-1")
        dxf = tmp_path / "assy.dxf"
        generate_assembly_drawing(dxf, manifest=str(man), part_name="ASSY-1",
                                  views=("FRONT",))
        return step, dxf

    def test_both_sidecars_survive_and_belong_to_their_own_product(self, two_products):
        step, dxf = two_products
        step_side = sidecar_path(step)
        dxf_side = sidecar_path(dxf)
        assert step_side.is_file() and dxf_side.is_file()
        assert json.loads(step_side.read_text("utf-8"))["document"] == "assembly_step"
        assert "assembly" in json.loads(dxf_side.read_text("utf-8"))

    def test_each_sidecar_hashes_its_own_product(self, two_products):
        step, dxf = two_products
        import hashlib

        ev = json.loads(sidecar_path(step).read_text("utf-8"))
        assert ev["document_sha256"] == hashlib.sha256(step.read_bytes()).hexdigest()
        assert ev["document_sha256"] != hashlib.sha256(dxf.read_bytes()).hexdigest()

    def test_the_release_manifest_reader_finds_the_step_evidence_after_the_drawing(
            self, tmp_path, two_products):
        """端到端那一趟的常驻版：出完图之后再读总装 STEP，仍要读到 STEP 的侧车。"""
        from aipd_os.release_manifest import _collect_assembly_step

        step, _dxf = two_products
        issues: list[dict] = []
        out = _collect_assembly_step(step, tmp_path, issues)
        assert "assembly_step_evidence_incomplete" not in {i["kind"] for i in issues}
        assert out["assembly_model"]["declared_part_count"] == 1


class TestBackwardsTrapIsClosed:
    def test_the_old_clobbering_spelling_is_not_left_anywhere_in_product_code(self):
        """留一处 `with_suffix('.evidence.json')` 就等于把这个坑原样留在那儿。"""
        import re
        import subprocess

        root = Path(__file__).resolve().parents[1]
        hits = subprocess.run(["grep", "-rn", r"with_suffix([\"']\.evidence\.json",
                               "src/"], cwd=str(root), capture_output=True, text=True)
        leftover = [ln for ln in hits.stdout.splitlines() if ln.strip()]
        assert not leftover, "侧车拼法没收敛到一个函数：\n" + "\n".join(leftover)
        assert re.search(r"def sidecar_path", (root / "src/aipd_os/cad/evidence.py")
                         .read_text(encoding="utf-8"))

    def test_write_evidence_sidecar_reports_the_path_it_actually_wrote(self, tmp_path):
        art = tmp_path / "x.step"
        art.write_text("x\n", encoding="utf-8")
        ev: dict = {"document": "unit"}
        got = write_evidence_sidecar(art, ev)
        assert got == sidecar_path(art) and got.is_file()
        assert ev["evidence_file"] == str(got)
