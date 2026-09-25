"""孔周留肉（hole-to-edge land）与「孔还是外圆」这根正交判据（`cad.dfm_dfa`，F-DFM-01 第 25 片）。

为什么要这一量：钻孔时孔口那条窄肉翻边，是厂商页里没写、但加工方一眼会挑出来的缺陷。
本轮检索（HLH Rapid / Xometry / 3ERP 转述的 ISO 2768）**都没有机加件的孔边距规则**，
所以阈值不新造，走 `borrowed_out_of_scope`：借的是同页「最小壁厚」那个数
（金属 0.8mm、塑料 1.5mm），并在证据里写明「页内原述是给壁厚的」——外推由制造方核，
本仓不自证为标准（见 `tests/test_cad_dfm.py::TestRulebookCarriesItsSources`）。

写这一片时先量出一个旧错：**「整周回转即孔」不够**。Ø20 圆棒的侧面也满一周，
按旧口径它被报成一个 Ø20×深 20 的孔（孔数、深径比、留肉全跟着错）。
本机实测：圆棒 holes 0 / 外圆 1；垫片 Ø30+Ø8 holes 只有 Ø8。
补的判据与张角正交：从面上一点**径向外移 1µm** 问实体分类器，落进材料里才是孔。

所有数字都是本机实测，不是推算：单孔 Ø6@x=25 → 留肉 2.0；两孔孔心距 8 → 各 2.0（孔到孔）；
Ø6 盲孔@x=15 → 2.0；Ø10 沉孔 Ø14×3 → 两行各 2.0（就是沉孔底那圈环形韧带 (14−10)/2）；
金样品 bracket 2.0、bracket_v2 4.0。
"""
from __future__ import annotations

from pathlib import Path

import cadquery as cq
import pytest

from aipd_os.cad.dfm import (
    RULES,
    _cylinder_is_bore,
    _solid_classifiers,
    analyze,
    generate_dfm_report,
    geometry_facts,
    measure_hole_lands,
)

_REPO = Path(__file__).resolve().parents[1]


def _solid(wp):
    return wp.solids().val().wrapped


def _plate(length=60.0, width=30.0, thick=10.0, holes=(), diam=6.0, depth=None):
    """孔位由 `pushPoints` 一次给全：`center()` 是**累加**的（第 8 片踩过），
    逐孔 center 会把第二个孔搬到第一个孔的局部原点上去，两孔 Ø6 会并成一个异形孔。"""
    wp = cq.Workplane("XY").box(length, width, thick)
    if holes:
        wp = wp.faces(">Z").workplane().pushPoints(list(holes))
        wp = wp.hole(diam) if depth is None else wp.hole(diam, depth)
    return _solid(wp)


def _golden(name):
    return cq.importers.importStep(str(_REPO / "releases/golden-projects"
                                       / "B-cad-engineering-change" / name)).val().wrapped


def _rows(shape):
    return measure_hole_lands(shape)["holes"]


class TestHoleVersusOuterCylinder:
    """`land` 与孔数的前提：先把「孔」和「整周的外圆」分开。"""

    def test_a_bare_rod_has_no_holes_but_one_outer_cylinder(self):
        facts = geometry_facts(_solid(cq.Workplane("XY").circle(10).extrude(20)))
        assert facts["holes"] == [], "圆棒侧面满一周，但它不是孔"
        assert facts["outer_cylinder_count"] == 1
        assert facts["bore_undecided_cylinder_count"] == 0

    def test_a_washer_reports_its_bore_not_its_outside_diameter(self):
        shape = _solid(cq.Workplane("XY").circle(15).extrude(5)
                       .faces(">Z").workplane().hole(8))
        facts = geometry_facts(shape)
        assert [h["diameter_mm"] for h in facts["holes"]] == [8.0]
        assert facts["outer_cylinder_count"] == 1

    def test_the_land_of_a_washer_is_the_annulus_width(self):
        """Ø8 孔在 Ø30 盘里 → 环宽 15−4=11mm。这个数只有「外圆不算孔」才对得上。"""
        shape = _solid(cq.Workplane("XY").circle(15).extrude(5)
                       .faces(">Z").workplane().hole(8))
        assert measure_hole_lands(shape)["min_land_mm"] == pytest.approx(11.0, abs=1e-6)

    def test_a_radial_hole_in_a_rod_is_a_hole_but_its_rim_is_not_a_circle(self):
        """孔口开在曲面上：口边是两个面的交线，不是圆 ⇒ 量不到，记盲区而不是 0。"""
        shape = _solid(cq.Workplane("XY").circle(10).extrude(20)
                       .cut(cq.Workplane("YZ").circle(2).extrude(40)
                            .translate(cq.Vector(-20, 0, 10))))
        facts = geometry_facts(shape)
        assert [h["diameter_mm"] for h in facts["holes"]] == [4.0], "Ø20 外圆不该再算孔"
        got = measure_hole_lands(shape)
        assert got["min_land_mm"] is None and got["measurable_count"] == 0
        assert got["holes"][0]["why"] == ["rim_circle_not_found"]

    def test_fillet_and_half_round_notch_are_neither_holes_nor_lands(self):
        """张角阈值不许放歪：R3 圆角是 1/4 周、半圆缺口是 1/2 周，都不该升成「孔」。

        缺口那条尤其要紧：它是**凹**面，孔/外圆那关它过得去，只挡在张角这一关。
        """
        filleted = _solid(cq.Workplane("XY").box(40, 20, 10).edges("|Z").fillet(3))
        assert geometry_facts(filleted)["holes"] == []
        assert measure_hole_lands(filleted)["holes"] == []
        notch = _solid(cq.Workplane("XY").box(40, 20, 10).faces(">Z").workplane()
                       .pushPoints([(20.0, 0.0)]).circle(6).cutThruAll())
        facts = geometry_facts(notch)
        assert facts["holes"] == [] and facts["outer_cylinder_count"] == 0
        assert facts["inside_radius_mm"] == pytest.approx(6.0, abs=1e-6), "缺口该落进内圆角那一档"
        assert measure_hole_lands(notch)["holes"] == []

    def test_the_bore_test_is_silent_when_there_is_no_solid_to_classify(self):
        """纯曲面输入：分类器建不出来 ⇒ 返回 None（不知道），不是 False（不是外圆）。"""
        from OCP.TopAbs import TopAbs_ShapeEnum
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopoDS import TopoDS

        shape = _solid(cq.Workplane("XY").circle(10).extrude(20)
                       .faces(">Z").workplane().hole(8))
        classifiers = _solid_classifiers(shape)
        assert classifiers, "夹具该有实体可分类"
        exp = TopExp_Explorer(shape, TopAbs_ShapeEnum.TopAbs_FACE)
        face = None
        while exp.More():
            candidate = TopoDS.Face_s(exp.Current())
            if _cylinder_is_bore(candidate, classifiers) is not None:
                face = candidate
                break
            exp.Next()
        assert face is not None, "夹具里一个可分类的圆柱面都没有，这条用例就成了空转"
        assert _cylinder_is_bore(face, []) is None, "没有实体可分类时不许猜成孔或外圆"


class TestTheLandIsMeasuredNotGuessed:
    def test_a_single_hole_reads_the_meat_left_to_the_nearest_edge(self):
        """Ø6@x=25 在 60 长的板上：板边在 x=30，孔壁外沿在 28 ⇒ 留肉 2.0，中心距 5.0。"""
        rows = _rows(_plate(60, 30, 10, [(25.0, 0.0)]))
        assert len(rows) == 1
        assert rows[0]["land_mm"] == pytest.approx(2.0, abs=1e-6)
        assert rows[0]["centerline_to_edge_mm"] == pytest.approx(5.0, abs=1e-6)
        assert rows[0]["diameter_mm"] == pytest.approx(6.0, abs=1e-6)

    def test_the_hole_to_neighbour_hole_ligament_counts_as_a_free_edge(self):
        """两孔孔心距 8、各 Ø6 ⇒ 中间只剩 2.0mm 的韧带，这就是孔边距最常被问的那个数。"""
        got = measure_hole_lands(_plate(80, 30, 10, [(-4.0, 0.0), (4.0, 0.0)]))
        assert [r["land_mm"] for r in got["holes"]] == pytest.approx([2.0, 2.0], abs=1e-6)
        assert got["min_land_mm"] == pytest.approx(2.0, abs=1e-6)
        assert got["measurable_count"] == got["hole_count"] == 2

    def test_the_nearest_edge_wins_even_when_it_is_the_other_pair_of_sides(self):
        """两孔相距 40、板 80×30：y 边给 15−3=12.0，x 边给 40−23=17.0 ⇒ 取 12.0。"""
        got = measure_hole_lands(_plate(80, 30, 10, [(-20.0, 0.0), (20.0, 0.0)]))
        assert got["min_land_mm"] == pytest.approx(12.0, abs=1e-6)

    def test_every_rim_of_one_bore_is_compared_not_just_the_first(self):
        """一个孔的两个口各自都给读数，交出去的是其中最薄的那个。

        Ø14 沉孔：一个口在顶面（最近的边在 8.0 外），另一个口在沉孔底的环形面上
        （那条边就是 Ø10 的圆，2.0）。若只取遍历碰到的第一个口，读数会因面序而变。
        """
        shape = _solid(cq.Workplane("XY").box(60, 30, 10).faces(">Z").workplane()
                       .pushPoints([(15.0, 0.0)]).cboreHole(10, 14, 3))
        rows = {r["diameter_mm"]: r for r in measure_hole_lands(shape)["holes"]}
        assert rows[14.0]["rim_count"] == 2
        assert sorted(one["land_mm"] for one in rows[14.0]["rim_readings"]) == \
            pytest.approx([2.0, 8.0], abs=1e-6)
        assert rows[14.0]["land_mm"] == pytest.approx(2.0, abs=1e-6)
        assert rows[14.0]["land_mm"] == min(one["land_mm"] for one in rows[14.0]["rim_readings"])

    def test_a_blind_hole_records_its_bottom_as_isolated_but_still_reads_the_top(self):
        """盲孔的底口那圈落在孔底圆面上、那个面除了自己没有别的边 ⇒ rim_isolated；
        顶口照样量得到（x=15 在 40 长板上：20−15−3=2.0）。"""
        rows = _rows(_plate(40, 30, 10, [(15.0, 0.0)], depth=6.0))
        assert rows[0]["land_mm"] == pytest.approx(2.0, abs=1e-6)
        assert rows[0]["why"] == ["rim_isolated"]
        assert rows[0]["rim_count"] == 2, "底口那圈在拓扑上也是圆柱边，它进 rim 列表但量不到边"

    def test_a_counterbore_reports_the_annular_web_under_it(self):
        """Ø10 通孔 + Ø14×3 沉孔：两行都量到 2.0 =（14−10)/2，就是沉孔底那圈环形韧带。"""
        shape = _solid(cq.Workplane("XY").box(60, 30, 10).faces(">Z").workplane()
                       .pushPoints([(15.0, 0.0)]).cboreHole(10, 14, 3))
        got = measure_hole_lands(shape)
        assert sorted(r["diameter_mm"] for r in got["holes"]) == [10.0, 14.0]
        assert [r["land_mm"] for r in got["holes"]] == pytest.approx([2.0, 2.0], abs=1e-6)
        assert [r["centerline_to_edge_mm"] for r in got["holes"]] == \
            pytest.approx([9.0, 7.0], abs=1e-6)
        assert got["min_land_mm"] == pytest.approx(2.0, abs=1e-6)

    def test_a_boss_wall_is_the_land_of_the_hole_running_through_it(self):
        """Ø6 孔穿过 Ø14 凸台 ⇒ 上口是凸台壁 7−3=4.0，下口是板边 10−3=7.0 ⇒ 交 4.0；
        而凸台外圆不该被当成第二个孔。"""
        shape = _solid(cq.Workplane("XY").box(40, 20, 6).faces(">Z").workplane()
                       .circle(7).extrude(6).faces(">Z").workplane()
                       .pushPoints([(0.0, 0.0)]).hole(6))
        facts = geometry_facts(shape)
        assert [h["diameter_mm"] for h in facts["holes"]] == [6.0]
        assert facts["outer_cylinder_count"] == 1
        rows = _rows(shape)
        assert sorted(one["land_mm"] for one in rows[0]["rim_readings"]) == \
            pytest.approx([4.0, 7.0], abs=1e-6)
        assert measure_hole_lands(shape)["min_land_mm"] == pytest.approx(4.0, abs=1e-6)

    def test_the_golden_parts_read_what_they_actually_are(self):
        """金样品：Ø8×10 三孔。v1 有两孔离边 2.0，v2 挪到 4.0 —— 一次改动把留肉翻倍。

        同一件上壁厚也给出 2.0 / 4.0（那圈韧带本来就是最薄的墙），所以这一量不是来
        *推翻*壁厚的，是来给「孔边距」一个有名字的读数；它真正补的是壁厚量不到的
        那一类（见 `test_the_land_catches_a_web_the_wall_reading_misses`）。
        """
        assert measure_hole_lands(_golden("bracket.step"))["min_land_mm"] == \
            pytest.approx(2.0, abs=1e-6)
        assert measure_hole_lands(_golden("bracket_v2.step"))["min_land_mm"] == \
            pytest.approx(4.0, abs=1e-6)

    def test_the_land_catches_a_web_the_wall_reading_misses(self):
        """沉孔底那圈环形韧带（(14−10)/2 = 2.0）：壁厚两法都量到 7.0，看不见它。

        这条就是「为什么有了壁厚还要有留肉」的实测答案，不是概念上的分工。
        """
        shape = _solid(cq.Workplane("XY").box(60, 30, 10).faces(">Z").workplane()
                       .pushPoints([(15.0, 0.0)]).cboreHole(10, 14, 3))
        report = analyze(shape, material="6061-T6")
        assert report["facts"]["min_wall_thickness_mm"] == pytest.approx(7.0, abs=0.05)
        assert report["facts"]["min_hole_land_mm"] == pytest.approx(2.0, abs=1e-6)
        fired = [f for f in report["findings"] if f["rule"] == "hole_land_metal"]
        assert fired and fired[0]["value"] == pytest.approx(2.0, abs=1e-6)
        assert fired[0]["verdict"] == "pass", \
            "借来的 0.8mm 线不会把 2.0 判红——这一量的价值是**看得见这个数**，不是多判一条红"

    def test_the_minimum_is_taken_across_rows_not_from_whichever_came_first(self):
        """一薄一厚两个孔：行序里第一条恰好是厚的那条（12.0），交出去的必须是最薄的 2.0。

        这条专治「聚合抄成 rows[0]」：断言里同时钉住行序，行序哪天变了这条会红，
        而不是悄悄退化成又一条靠运气的读数。
        """
        got = measure_hole_lands(_plate(60, 30, 10, [(25.0, 0.0), (-10.0, 0.0)]))
        assert [r["land_mm"] for r in got["holes"]] == pytest.approx([12.0, 2.0], abs=1e-6)
        assert got["min_land_mm"] == pytest.approx(2.0, abs=1e-6)
        assert got["holes"][0]["land_mm"] != got["min_land_mm"]

    def test_the_aggregate_is_recomputable_from_the_rows_and_never_a_made_up_zero(self):
        """`min_land_mm` 必须能由逐孔逐口的读数复算：写死、抄错、把「没量到」折成 0 都会红。"""
        for shape in (_plate(60, 30, 10, [(25.0, 0.0), (-10.0, 0.0)]),
                      _golden("bracket.step"), _golden("bracket_v2.step"),
                      _solid(cq.Workplane("XY").circle(10).extrude(20))):
            got = measure_hole_lands(shape)
            values = [r["land_mm"] for r in got["holes"] if r["land_mm"] is not None]
            assert got["min_land_mm"] == (min(values) if values else None), got
            assert got["measurable_count"] == len(values)
            assert got["hole_count"] == len(got["holes"])
            for row in got["holes"]:
                read = [one["land_mm"] for one in row["rim_readings"]
                        if one["land_mm"] is not None]
                assert row["land_mm"] == (min(read) if read else None), row
                assert len(row["rim_readings"]) == row["rim_count"]

    def test_the_land_is_a_different_number_from_the_wall_thickness(self):
        """两个量各钉各的：壁厚是「两壁之间」，留肉是「孔口到自由边」，不许互相顶。

        中心孔的 60×30×10 板：壁厚 10（板厚），留肉 12（孔口到 y 边）——
        反过来把孔推到 x=25，留肉变 2.0 而壁厚也是 2.0（那条韧带两头都薄）。
        """
        centered = analyze(_plate(60, 30, 10, [(0.0, 0.0)]), material="6061-T6")
        assert centered["facts"]["min_wall_thickness_mm"] == pytest.approx(10.0, abs=0.05)
        assert centered["facts"]["min_hole_land_mm"] == pytest.approx(12.0, abs=1e-6)
        edge = analyze(_plate(60, 30, 10, [(25.0, 0.0)]), material="6061-T6")
        assert edge["facts"]["min_hole_land_mm"] == pytest.approx(2.0, abs=1e-6)
        assert edge["facts"]["min_wall_thickness_mm"] == pytest.approx(2.0, abs=0.05)

    def test_the_method_string_says_what_the_number_is(self):
        got = measure_hole_lands(_plate(60, 30, 10, [(25.0, 0.0)]))
        assert "BRepExtrema" in got["method"] and got["holes"][0]["why"] == []


class TestTheBorrowedThresholdJudgesThreeWays:
    def _thin_land(self):
        """留肉 0.5mm 的件：Ø6 孔，孔心离板边 3.5。"""
        return _plate(60, 30, 10, [(26.5, 0.0)])

    def test_metal_line_flags_half_a_millimetre_of_land(self):
        report = analyze(self._thin_land(), material="6061-T6")
        hit = [f for f in report["findings"] if f["rule"] == "hole_land_metal"]
        assert hit and hit[0]["verdict"] == "flag"
        assert hit[0]["value"] == pytest.approx(0.5, abs=1e-6)
        assert hit[0]["limit"] == 0.8 and hit[0]["severity"] == "advisory"
        assert hit[0]["basis"] == "borrowed_out_of_scope"

    def test_the_same_part_passes_on_the_metal_line_and_fails_on_the_plastic_one(self):
        """1.0mm：按金属线（0.8）合格、按塑料线（1.5）是问题——两档不许互相顶。"""
        shape = _plate(60, 30, 10, [(26.0, 0.0)])
        metal = {f["rule"]: f["verdict"] for f in analyze(shape, material="6061-T6")["findings"]}
        plastic = {f["rule"]: f["verdict"]
                   for f in analyze(shape, material="ABS")["findings"]}
        assert metal["hole_land_metal"] == "pass"
        assert "hole_land_plastic" not in metal, "材料是金属，塑料那条不该参与判定"
        assert plastic["hole_land_plastic"] == "flag"
        assert "hole_land_metal" not in plastic

    def test_the_fact_line_always_reports_and_never_invents_a_limit(self):
        report = analyze(_plate(60, 30, 10, [(25.0, 0.0)]), material="6061-T6")
        hit = [f for f in report["findings"] if f["rule"] == "hole_land_reported"]
        assert hit and hit[0]["verdict"] == "info" and hit[0]["limit"] is None
        assert hit[0]["source"]["url"] == "" and hit[0]["basis"] == "own_measure"

    def test_unknown_material_blinds_the_land_rules_but_keeps_the_fact(self):
        report = analyze(self._thin_land(), material=None)
        by = {b["rule"]: b["reason"] for b in report["blind"]}
        assert by["hole_land_metal"] == "material_class_unknown"
        assert by["hole_land_plastic"] == "material_class_unknown"
        assert any(f["rule"] == "hole_land_reported" for f in report["findings"])

    def test_a_part_with_no_bore_blinds_the_whole_land_family(self):
        report = analyze(_plate(60, 30, 10), material="6061-T6")
        by = {b["rule"]: b["reason"] for b in report["blind"]}
        assert by["hole_land_reported"] == "no_full_cylindrical_hole"
        assert "hole_land_reported" not in {f["rule"] for f in report["findings"]}

    def test_an_unmeasurable_bore_blinds_rather_than_reading_as_plenty_of_meat(self):
        """有孔但一圈都量不到边（孔口开在曲面上）⇒ `hole_land_unmeasurable`，不是 pass。"""
        shape = _solid(cq.Workplane("XY").circle(10).extrude(20)
                       .cut(cq.Workplane("YZ").circle(2).extrude(40)
                            .translate(cq.Vector(-20, 0, 10))))
        report = analyze(shape, material="6061-T6")
        by = {b["rule"]: b["reason"] for b in report["blind"]}
        assert by["hole_land_metal"] == "hole_land_unmeasurable"
        assert report["facts"]["min_hole_land_mm"] is None

    def test_a_rule_never_appears_in_both_findings_and_blind(self):
        for shape in (_plate(60, 30, 10, [(25.0, 0.0)]), _plate(60, 30, 10),
                      _solid(cq.Workplane("XY").circle(10).extrude(20))):
            for material in ("6061-T6", "ABS", None):
                report = analyze(shape, material=material)
                judged = {f["rule"] for f in report["findings"]}
                assert judged.isdisjoint({b["rule"] for b in report["blind"]})


class TestTheReportSaysWhatItDidAndDidNotDo:
    def _text(self, tmp_path, shape, material="6061-T6"):
        generate_dfm_report(tmp_path / "dfm.md", model=shape, part_name="P-1",
                            revision="A", material=material)
        return (tmp_path / "dfm.md").read_text(encoding="utf-8")

    def test_the_report_prints_the_land_line_with_hole_and_outer_counts(self, tmp_path):
        text = self._text(tmp_path, _plate(60, 30, 10, [(25.0, 0.0)]))
        assert "整孔 1 个" in text and "整周外圆（不计入孔）0 个" in text
        line = next(row for row in text.splitlines() if "留肉" in row)
        assert "2 mm" in line and "1/1 个整孔" in line

    def test_a_borrowed_threshold_shows_the_feature_the_page_stated_it_for(self, tmp_path):
        text = self._text(tmp_path, _plate(60, 30, 10, [(26.5, 0.0)]))
        assert "页内原述是给「金属最小壁厚」的" in text
        assert "借来的数" in text
        assert "vendor_capability" not in text, "机器码不该直接印给读者"

    def test_an_unmeasurable_lands_as_a_blind_line_not_a_zero(self, tmp_path):
        """孔口开在曲面上的那件（圆棒 + 径向孔）：留肉那一行必须写「没量出来」，不是 0。"""
        shape = _solid(cq.Workplane("XY").circle(10).extrude(20)
                       .cut(cq.Workplane("YZ").circle(2).extrude(40)
                            .translate(cq.Vector(-20, 0, 10))))
        text = self._text(tmp_path, shape)
        assert "孔周最小留肉" in text and "没量出来（1 个整孔一个都找不到可量的边）" in text
        assert "- 孔周最小留肉：0" not in text
        assert "整周外圆（不计入孔）1 个" in text


class TestTheRuleTableStaysHonest:
    def test_lands_are_the_only_new_measure_and_it_is_plumbed_once(self):
        report = analyze(_plate(60, 30, 10, [(25.0, 0.0)]), material="6061-T6")
        assert set(report["facts"]) >= {"min_hole_land_mm", "hole_land_measurement",
                                        "outer_cylinder_count",
                                        "bore_undecided_cylinder_count"}

    def test_the_land_rules_are_the_only_borrowed_ones_and_both_borrow_from_walls(self):
        borrowed = {r["id"]: r["source"]["stated_for"] for r in RULES
                    if r["basis"] == "borrowed_out_of_scope"}
        assert borrowed == {"hole_land_metal": "wall_thickness_metal",
                            "hole_land_plastic": "wall_thickness_plastic"}

    def test_the_land_rows_recount_to_the_reported_minimum(self):
        """报告里那句「量到 x/y 个」必须与逐行读数同源于一次测量。"""
        got = measure_hole_lands(_plate(60, 30, 10, [(25.0, 0.0), (22.0, 9.0)]))
        assert got["hole_count"] == len(got["holes"]) == 2
        assert got["measurable_count"] == sum(1 for r in got["holes"]
                                              if r["land_mm"] is not None)
        assert got["min_land_mm"] == min(r["land_mm"] for r in got["holes"]
                                         if r["land_mm"] is not None)
