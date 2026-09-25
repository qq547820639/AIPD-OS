"""装配级 STEP 的导出与**写后回读校验**（capability ``cad.local_native_brep``，
C6「总装/单件STEP」里此前明写没做的装配那一半）。

判据为什么长成这样（三条都是本机实测逼出来的，见
`docs/audit/CAD_ASSEMBLY_STEP_EXPORT_F-DRAW-01_2026-09-25.md` §二）：

1. **写完必须回读比对**，而且比的是**多重集**：回读实体的「中心 + 体积」与
   「源 STEP 自己量出的中心 + 声明偏移」逐件对上。少一件、多一件、摆错位置都算不等，
   一旦不等就**删掉刚写的文件并报错**——交出一份声称是 N 件、实际装不上的 STEP，
   比不出货更糟。
2. **件号与几何的对应只由 sidecar 承载，不宣称 STEP 里能读名字**：本机实测 OCCT 把
   非 ASCII 零件名写成 `PRODUCT('æ¯æ',…)`（UTF-8 字节被按单字节落盘），
   所以 `step_product_names_readable` 恒为 `False` 并带原因；这不是本仓的实现缺陷，
   但把它说成「名字已随 STEP 交付」就是假凭据。
3. **偏移只用 manifest 声明的**（与出图、爆炸视图同一个 `offset`），不再引入第二套位置事实。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from aipd_os.cad.assembly import export_assembly_step, read_back_solids


def _write_step(tmp_path: Path, name: str, box=(20, 8, 20), hole=None,
                center=(0.0, 0.0, 0.0)) -> Path:
    import cadquery as cq

    wp = cq.Workplane("XY").box(*box)
    if tuple(center) != (0.0, 0.0, 0.0):
        # Workplane.center() 只收 (x, y)；要把零件自身摆离原点用 translate()
        wp = wp.translate(cq.Vector(*center))
    if hole:
        wp = wp.faces(">Z").workplane().hole(hole)
    path = tmp_path / name
    cq.exporters.export(wp, str(path))
    return path


def _manifest(tmp_path: Path, parts: list[dict]) -> Path:
    payload = {"parts": parts}
    file = tmp_path / "assy.json"
    file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return file


def _two_part_manifest(tmp_path: Path, **kw) -> tuple[Path, list[dict]]:
    a = _write_step(tmp_path, "a.step", center=kw.get("a_center", (0, 0, 0)))
    b = _write_step(tmp_path, "b.step", box=(15, 6, 12), hole=None,
                    center=kw.get("b_center", (0, 0, 0)))
    parts = [{"name": "支架", "step": a.name, "balloon": 1, "offset": [0, 0, 0]},
             {"name": "压板", "step": b.name, "balloon": 2, "offset": [0, 25, 12]}]
    return _manifest(tmp_path, parts), parts


class TestExportIsFaithful:
    def test_file_written_with_every_declared_part(self, tmp_path):
        man, _ = _two_part_manifest(tmp_path)
        out = tmp_path / "assy.step"
        evidence = export_assembly_step(out, manifest=str(man), part_name="ASSY-1")
        assert out.is_file() and out.stat().st_size > 1000
        assert evidence["solid_count"] == 2
        assert [p["name"] for p in evidence["parts"]] == ["支架", "压板"]

    def test_each_part_sits_where_the_manifest_says(self, tmp_path):
        """中心 = 源 STEP 自己的中心 + 声明偏移；这是「摆放被真写进去」的唯一硬证据。"""
        man, _ = _two_part_manifest(tmp_path)
        out = tmp_path / "assy.step"
        export_assembly_step(out, manifest=str(man), part_name="ASSY-1")
        read = read_back_solids(out)
        assert len(read) == 2
        centers = sorted(tuple(round(v, 6) for v in s["center"]) for s in read)
        assert centers == [(0.0, 0.0, 0.0), (0.0, 25.0, 12.0)], centers

    def test_volumes_survive_the_round_trip_per_part(self, tmp_path):
        import cadquery as cq

        man, _ = _two_part_manifest(tmp_path)
        out = tmp_path / "assy.step"
        evidence = export_assembly_step(out, manifest=str(man), part_name="ASSY-1")
        sources = sorted(round(cq.importers.importStep(str(tmp_path / f"{f}.step"))
                               .val().Volume(), 6) for f in ("a", "b"))
        assert sorted(round(p["volume_mm3"], 6) for p in evidence["parts"]) == sources
        # 「体积对不对」在证据里是**每件两个可复算的数**（源件体积 / 回读体积），
        # 不是一个写死的 True。为什么不留聚合值：成功路径上偏差本来就是 0，
        # 硬编码 0 与量出来 0 长得一样（电池里那条 E16 活了下来），
        # 所以只留量出来的那两个数，也不再把源件体积抄第二遍当「期望值」。
        assert "volume_match" not in evidence and "max_volume_deviation_mm3" not in evidence
        assert evidence["verification"] == "read_back_matched_multiset"
        for one in evidence["parts"]:
            assert one["read_back_volume_mm3"] == pytest.approx(
                one["volume_mm3"], abs=1e-6)

    def test_off_center_source_geometry_still_lands_at_offset_plus_center(self, tmp_path):
        """源零件自身不在原点时，期望位置是「源中心 + 偏移」，不是偏移本身。"""
        man, _ = _two_part_manifest(tmp_path, a_center=(5, 0, 0))
        out = tmp_path / "assy.step"
        evidence = export_assembly_step(out, manifest=str(man), part_name="ASSY-1")
        bracket = [p for p in evidence["parts"] if p["name"] == "支架"][0]
        assert bracket["expected_center"] == pytest.approx((5.0, 0.0, 0.0), abs=1e-6)
        assert bracket["actual_center"] == pytest.approx((5.0, 0.0, 0.0), abs=1e-6)

    def test_multi_solid_part_is_counted_by_volume_not_by_solid_number(self, tmp_path):
        import cadquery as cq

        small = cq.Workplane("XY").box(4, 4, 4).translate(cq.Vector(30, 0, 0))
        two = cq.Workplane("XY").box(10, 10, 10).union(small)
        path = tmp_path / "two.step"
        cq.exporters.export(two.val(), str(path))
        _write_step(tmp_path, "one.step")
        man = _manifest(tmp_path, [
            {"name": "双实体件", "step": "two.step", "balloon": 1, "offset": [0, 0, 0]},
            {"name": "单实体件", "step": "one.step", "balloon": 2, "offset": [0, 40, 0]}])
        out = tmp_path / "multi.step"
        evidence = export_assembly_step(out, manifest=str(man), part_name="ASSY-2")
        # 回读会有 3 个 solid，但只有 2 个声明件：按**声明件**聚合体积与位置
        assert evidence["solid_count"] == 3 and evidence["declared_part_count"] == 2
        both = cq.importers.importStep(str(path)).solids().vals()
        twin = [p for p in evidence["parts"] if p["name"] == "双实体件"][0]
        assert twin["volume_mm3"] == pytest.approx(
            sum(s.Volume() for s in both), abs=1e-6)
        assert twin["source_solid_count"] == 2 and twin["read_back_solid_count"] == 2


class TestVerificationRefusesFalseClaims:
    def test_a_part_that_fails_to_import_is_refused_before_writing(self, tmp_path):
        broken = tmp_path / "broken.step"
        broken.write_text("这不是 STEP\n", encoding="utf-8")
        man = _manifest(tmp_path, [{"name": "坏件", "step": "broken.step", "balloon": 1,
                                   "offset": [0, 0, 0]}])
        out = tmp_path / "no.step"
        with pytest.raises(ValueError):
            export_assembly_step(out, manifest=str(man), part_name="ASSY-9")
        assert not out.exists(), "校验没过就不该留下一份声称是装配体的文件"

    def test_empty_solid_step_is_refused(self, tmp_path):
        """STEP 文件在、但读不出实体：拒绝，不产一份空装配。"""
        import cadquery as cq
        from OCP.TopoDS import TopoDS_Builder, TopoDS_Compound

        empty = TopoDS_Compound()
        TopoDS_Builder().MakeCompound(empty)
        path = tmp_path / "empty.step"
        cq.exporters.export(cq.Workplane(obj=empty), str(path))
        man = _manifest(tmp_path, [{"name": "空件", "step": "empty.step", "balloon": 1,
                                   "offset": [0, 0, 0]}])
        with pytest.raises(ValueError):
            export_assembly_step(tmp_path / "e.step", manifest=str(man), part_name="A")

    def test_a_dropped_solid_in_the_written_file_is_refused_and_the_file_deleted(
            self, tmp_path, monkeypatch):
        """写后校验的牙齿：注入「文件里少了一个实体」，必须报错**并且**删掉那份文件。

        故障注在内核之外（改的是回读结果），因为要验的是本仓这道校验，不是 OCCT 会不会掉件；
        校验被删掉时这条就没人红——第 19 片量到过一次「判据存在但没被验过」，这片先补上。
        """
        import aipd_os.cad.assembly as mod

        man, _ = _two_part_manifest(tmp_path)
        out = tmp_path / "drop.step"
        real = mod.read_back_solids
        monkeypatch.setattr(mod, "read_back_solids",
                            lambda path: real(path)[:1])
        with pytest.raises(ValueError, match="回读"):
            export_assembly_step(out, manifest=str(man), part_name="ASSY-1")
        assert not out.exists()

    def test_a_wrong_volume_in_the_written_file_is_caught(self, tmp_path, monkeypatch):
        """只比中心不比体积的话，这条就绿了：体积被换掉必须也被抓。"""
        import aipd_os.cad.assembly as mod

        man, _ = _two_part_manifest(tmp_path)
        out = tmp_path / "vol.step"
        real = mod.read_back_solids

        def shrunk(path):
            readings = real(path)
            readings[1]["volume_mm3"] *= 0.5
            return readings

        monkeypatch.setattr(mod, "read_back_solids", shrunk)
        with pytest.raises(ValueError, match="体积"):
            export_assembly_step(out, manifest=str(man), part_name="ASSY-1")

    def test_a_half_millimetre_placement_error_is_caught(self, tmp_path, monkeypatch):
        """容差是 1e-6，不是「差不多就行」：偏 0.2mm 就该拒。"""
        import aipd_os.cad.assembly as mod

        man, _ = _two_part_manifest(tmp_path)
        out = tmp_path / "off.step"
        real = mod.read_back_solids

        def shifted(path):
            readings = real(path)
            readings[1]["center"][1] += 0.2
            return readings

        monkeypatch.setattr(mod, "read_back_solids", shifted)
        with pytest.raises(ValueError, match="期望中心"):
            export_assembly_step(out, manifest=str(man), part_name="ASSY-1")

    def test_two_parts_in_the_same_place_are_reported_not_silently_merged(self, tmp_path):
        _write_step(tmp_path, "sa.step")
        _write_step(tmp_path, "sb.step", box=(6, 6, 6))
        man = _manifest(tmp_path, [{"name": "甲", "step": "sa.step", "balloon": 1,
                                    "offset": [0, 0, 0]},
                                   {"name": "乙", "step": "sb.step", "balloon": 2,
                                    "offset": [0, 0, 0]}])
        evidence = export_assembly_step(tmp_path / "same.step", manifest=str(man),
                                         part_name="ASSY-3")
        assert evidence["coincident_placements"], "两件同位要说出来，别让人以为是一件"


class TestEvidenceSidecar:
    def test_sidecar_next_to_the_step_with_both_hashes(self, tmp_path):
        man, _ = _two_part_manifest(tmp_path)
        out = tmp_path / "assy.step"
        evidence = export_assembly_step(out, manifest=str(man), part_name="ASSY-1")
        side = Path(evidence["evidence_file"])
        assert side == tmp_path / "assy.step.evidence.json" and side.is_file()
        disk = json.loads(side.read_text(encoding="utf-8"))
        assert disk["document"] == "assembly_step"
        assert disk["document_sha256"] == hashlib.sha256(out.read_bytes()).hexdigest()
        assert disk["manifest_sha256"] == hashlib.sha256(man.read_bytes()).hexdigest()
        assert disk["verification"] == "read_back_matched_multiset"

    def test_part_names_are_not_claimed_readable_in_the_step(self, tmp_path):
        """本机实测：OCCT 把中文件名写成 mojibake，所以这里只能是 False + 原因。"""
        man, _ = _two_part_manifest(tmp_path)
        evidence = export_assembly_step(tmp_path / "n.step", manifest=str(man),
                                        part_name="ASSY-1")
        assert evidence["step_product_names_readable"] is False
        assert "PRODUCT(" in evidence["step_product_names_reason"]

    def test_sidecar_says_what_the_assembly_step_does_not_carry(self, tmp_path):
        man, _ = _two_part_manifest(tmp_path)
        evidence = export_assembly_step(tmp_path / "nc.step", manifest=str(man),
                                        part_name="ASSY-1")
        assert evidence["not_covered"] == [
            "总装 STEP 里的装配约束/配合（本仓不建约束对象）",
            "零件名在 STEP 内的可读性（非 ASCII 被写坏，见 reason）",
            "颜色/材质属性（manifest 里没有材料字段，材料在 BOM 行上）",
            "子装配层级（manifest 是平表，没有父子件，产出一层装配）"]

    def test_sidecar_carries_the_part_identity_rows(self, tmp_path):
        man, _ = _two_part_manifest(tmp_path)
        evidence = export_assembly_step(tmp_path / "id.step", manifest=str(man),
                                        part_name="ASSY-1")
        first = evidence["parts"][0]
        assert first["balloon"] == 1 and first["source_step_sha256"]
        assert first["placement"] == [0.0, 0.0, 0.0]


class TestCliSurface:
    def test_cli_writes_the_assembly_step(self, tmp_path):
        from aipd_os.cli.main import main

        man, _ = _two_part_manifest(tmp_path)
        out = tmp_path / "cli.step"
        rc = main(["drawing", "assembly-step", "--manifest", str(man),
                   "--out", str(out), "--part", "ASSY-1"])
        assert rc == 0, rc
        assert out.is_file()

    def test_cli_missing_manifest_is_rc2(self, tmp_path):
        from aipd_os.cli.main import main

        rc = main(["drawing", "assembly-step", "--manifest", str(tmp_path / "nope.json"),
                   "--out", str(tmp_path / "x.step"), "--part", "ASSY-1"])
        assert rc == 2

    def test_cli_broken_part_step_is_rc2_not_a_hollow_file(self, tmp_path):
        from aipd_os.cli.main import main

        broken = tmp_path / "bad.step"
        broken.write_text("nope", encoding="utf-8")
        man = _manifest(tmp_path, [{"name": "坏件", "step": "bad.step", "balloon": 1,
                                   "offset": [0, 0, 0]}])
        out = tmp_path / "bad.step_out.step"
        rc = main(["drawing", "assembly-step", "--manifest", str(man),
                   "--out", str(out), "--part", "A"])
        assert rc == 2 and not out.exists()
