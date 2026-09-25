"""壁厚第二条量法：**沿面法向**（`cad.dfm_dfa`，F-DFM-01 第 24 片）。

动因是一次实测，不是设想：一块 3mm 厚、绕 Y 转 45° 的板，
原来那条三轴网格射线量出来是 **1.00mm**。而代码里原先写的 caveat 是
「斜置薄壁会**测厚不测薄**」——这句关于误差方向的话**是错的**：
斜穿会让弦变长（t/cosθ），但在棱角附近擦过会让弦比真实壁厚还短。
一个会说谎的方向性偏差挂在 advisory 上，读报告的人恰好朝错误的方向放心。

第二条法向读数补的是**方向**：从面上一点沿 ±法向走第一段材料，
并用 `BRepClass3d_SolidClassifier` 逐条验「中点在材料内、出射点在材料外」才算数。
本机实测：斜板 3.000、平板 3.000、球 10.000、圆柱 10.000（直径）。

但它**不取代**三轴那条：它每面最多 12×12 个采样、还刻意只采参数域中间 60%
（躲棱边与角点——CATIA 的 Ray 模式正是在尖边处误差可超容差，故其默认用球），
所以它会漏掉三轴抓到的薄特征（金样品 bracket：三轴 2.00、法向 3.73）。

结论口径：**两法各量各的，`min_mm` 取较小者**，两个数都留在读数里。
阈值那两条壁厚规则是 advisory（不阻断就绪），宁可多提一次「找制造方看看」，
也不把墙说厚。聚合规则因此是「谁薄听谁的」，不是「谁新听谁的」。
"""
from __future__ import annotations

from pathlib import Path

import cadquery as cq
import pytest

from aipd_os.cad.dfm import _face_normal_thickness, measure_min_wall_thickness

_REPO = Path(__file__).resolve().parents[1]


def _solid(wp):
    return wp.solids().val().wrapped


def _plate(thickness: float, angle_deg: float = 0.0):
    wp = cq.Workplane("XY").box(40.0, thickness, 40.0)
    if angle_deg:
        wp = wp.rotate((0, 0, 0), (0, 1, 0), angle_deg)
    return _solid(wp)


class TestTheSecondReadingIsDirectionCorrect:
    def test_an_oblique_wall_reads_its_true_thickness_along_the_normal(self):
        got = measure_min_wall_thickness(_plate(3.0, 45.0), spacing_mm=0.5)
        assert got["normal_min_mm"] == pytest.approx(3.0, abs=1e-3), \
            "法向读数就该是垂直壁厚本身，不是斜弦"

    def test_the_axis_reading_of_that_same_wall_is_wrong_on_the_thin_side(self):
        """把「旧 caveat 说错方向」这件事钉住：斜板被三轴法读**薄**，不是读厚。"""
        got = measure_min_wall_thickness(_plate(3.0, 45.0), spacing_mm=0.5)
        assert got["axis_min_mm"] < got["normal_min_mm"], got
        assert got["axis_min_mm"] == pytest.approx(1.0, abs=0.05)

    def test_a_straight_wall_keeps_both_readings_agreeing(self):
        got = measure_min_wall_thickness(_plate(3.0), spacing_mm=0.5)
        assert got["axis_min_mm"] == got["normal_min_mm"] == pytest.approx(3.0, abs=1e-3)

    def test_curved_bodies_do_not_crash_at_poles_and_seams(self):
        sphere = measure_min_wall_thickness(_solid(cq.Workplane("XY").sphere(5.0)), 0.5)
        cylinder = measure_min_wall_thickness(_solid(cq.Workplane("XY").cylinder(20.0, 5.0)), 0.5)
        assert sphere["normal_min_mm"] == pytest.approx(10.0, abs=1e-2)
        assert cylinder["normal_min_mm"] == pytest.approx(10.0, abs=1e-2)
        for one in (sphere, cylinder):
            assert one["normal_measurement"]["samples_usable"] > 0

    def test_a_one_millimetre_spherical_skin_is_found_by_both(self):
        skin = _solid(cq.Workplane("XY").sphere(10.0)
                      .cut(cq.Workplane("XY").sphere(9.0)))
        got = measure_min_wall_thickness(skin, 0.5)
        assert got["min_mm"] == pytest.approx(1.0, abs=1e-2)
        assert got["normal_min_mm"] == pytest.approx(1.0, abs=1e-2)


class TestAggregationNeverHidesTheThinnerOne:
    def test_min_mm_is_the_smaller_of_the_two_not_the_newer(self):
        got = measure_min_wall_thickness(_plate(3.0, 45.0), spacing_mm=0.5)
        assert got["min_mm"] == min(got["axis_min_mm"], got["normal_min_mm"])

    def test_the_normal_reading_alone_would_have_claimed_a_thicker_bracket(self):
        """金样品上法向**漏掉**了薄特征：所以不能「谁新听谁的」。"""
        step = (_REPO / "releases" / "golden-projects"
                / "B-cad-engineering-change" / "bracket.step")
        got = measure_min_wall_thickness(cq.importers.importStep(str(step)).val().wrapped, 0.5)
        assert got["axis_min_mm"] < got["normal_min_mm"], \
            "这条是口径依据：法向会漏，所以 min 取两法较小者"
        assert got["min_mm"] == got["axis_min_mm"], "聚合得听较薄那一条，不是听新加的那条"

    def test_both_numbers_stay_in_the_reading_for_a_human_to_compare(self):
        got = measure_min_wall_thickness(_plate(3.0), spacing_mm=0.5)
        assert {"min_mm", "axis_min_mm", "normal_min_mm", "normal_measurement"} <= set(got)
        assert "三轴" in got["caveat"] and "法向" in got["caveat"]


class TestBlindSpotsStayBlind:
    def test_a_shape_with_no_solid_has_no_normal_reading_and_does_not_become_zero(self):
        """只给一张面（没有实体）：量不出来就是 None，不折成 0，也不许整个函数报错。"""
        from OCP.TopoDS import TopoDS

        planar = TopoDS.Face_s(cq.Workplane("XY")
                               .box(20.0, 20.0, 20.0).faces(">Z").val().wrapped)
        got = _face_normal_thickness(planar, 0.5)
        assert got["min_mm"] is None and got["faces_probed"] == 0

    def test_the_min_falls_back_to_the_axis_reading_when_normals_are_blind(self, monkeypatch):
        import aipd_os.cad.dfm as mod

        monkeypatch.setattr(mod, "_face_normal_thickness",
                            lambda shape, spacing, **kw: dict(
                                _BLIND, samples=1, samples_usable=0))
        got = mod.measure_min_wall_thickness(_plate(3.0), spacing_mm=0.5)
        assert got["normal_min_mm"] is None
        assert got["min_mm"] == pytest.approx(3.0, abs=1e-3)
        assert "没量出来" not in str(got["min_mm"])


_BLIND = {"min_mm": None, "faces_probed": 0, "sample_domain": "参数域中间 60%（躲棱边与角点）",
          "samples_degenerate_normal": 0}


class TestEverySolidInACompoundIsVisited:
    """法向那条按**实体**逐个走（三轴那条是对整个 shape 求交）：
    复合体里两块厚度不同，读数必须取到更薄的那块，而不是只看第一块。"""

    def test_a_two_solid_compound_reports_the_thinner_solid(self):
        thick = cq.Workplane("XY").box(10.0, 5.0, 10.0).val().wrapped
        thin = cq.Workplane("XY").box(10.0, 2.0, 10.0) \
            .translate(cq.Vector(0.0, 40.0, 0.0)).val().wrapped
        pair = cq.Compound.makeCompound([cq.Shape(thick), cq.Shape(thin)]).wrapped
        assert _face_normal_thickness(thick, 0.5)["min_mm"] == pytest.approx(5.0, abs=1e-3)
        assert _face_normal_thickness(pair, 0.5)["min_mm"] == pytest.approx(2.0, abs=1e-3)

    def test_solid_count_is_visible_in_the_reading(self):
        thick = cq.Workplane("XY").box(10.0, 5.0, 10.0).val().wrapped
        thin = cq.Workplane("XY").box(10.0, 2.0, 10.0) \
            .translate(cq.Vector(0.0, 40.0, 0.0)).val().wrapped
        pair = cq.Compound.makeCompound([cq.Shape(thick), cq.Shape(thin)]).wrapped
        one = _face_normal_thickness(thick, 0.5)
        both = _face_normal_thickness(pair, 0.5)
        assert both["faces_probed"] > one["faces_probed"], \
            "只走第一个实体的话，面数不会翻倍——这条就是它的反证"


class TestTheReportShowsBothNumbers:
    def test_the_markdown_prints_axis_and_normal_readings_side_by_side(self, tmp_path):
        from aipd_os.cad.dfm import generate_dfm_report

        plate = cq.Workplane("XY").box(40.0, 3.0, 40.0).rotate((0, 0, 0), (0, 1, 0), 45.0)
        report = generate_dfm_report(tmp_path / "oblique.md",
                                     model=plate.solids().val(),
                                     part_name="RIB-1", material="6061-T6")
        text = (tmp_path / "oblique.md").read_text(encoding="utf-8")
        wall = report["facts"]["wall_measurement"]
        assert f"三轴 {wall['axis_min_mm']:g} mm" in text and \
            f"法向 {wall['normal_min_mm']:g} mm" in text
        assert "三轴" in wall["caveat"] and "会漏" in wall["caveat"]


class TestAVoidIsNotAWall:
    """分类器那两道验证不是为了好看：封闭空腔的**开口距离**会被裸第一命中读成壁厚。

    20 见方的块里挖一条 0.5mm 宽、四周全封闭的槽：从槽壁沿法向朝空腔里走，
    第一段「命中」就是对面槽壁，距离 0.5——那是**空的**，不是墙。
    中点必须在材料内、出射点必须在材料外，两段都验才收下这个数。
    """

    def _cavity_block(self):
        block = cq.Workplane("XY").box(20.0, 20.0, 20.0)
        slot = cq.Workplane("XY").box(10.0, 0.5, 10.0)
        return block.cut(slot).solids().val().wrapped

    def test_a_closed_cavity_is_not_reported_as_its_own_opening_width(self):
        """钉**具体那个数**，不是钉「> 1.0」：两道验证各自单独撤掉都会把它挪走。

        量到的 5.000 是「槽端到块边」那段实打实的肉（槽 x∈[-5,5]、块边 x=10），
        不是 0.5 的槽宽，也不是 9.75 的半板厚。
        """
        got = _face_normal_thickness(self._cavity_block(), 0.5)
        assert got["min_mm"] == pytest.approx(5.0, abs=1e-3), got

    def test_the_rejected_directions_are_not_counted_as_usable(self):
        got = _face_normal_thickness(self._cavity_block(), 0.5)
        assert got["samples_usable"] < got["samples"] * 2, \
            "两个方向都收下等于没验：可采样数不该被当成可用段数"


class TestTheNormalReadingDoesNotDependOnTheGrid:
    """三轴那条的读数随网格间距跳（同一块斜板 1.00 / 2.02 / 3.00），法向那条不跳。

    这条是这一片真正的卖点：**不随采样分辨率改口的读数**。
    """

    @pytest.mark.parametrize("spacing", [0.5, 1.0, 2.0, 5.0])
    def test_the_oblique_plate_reads_three_millimetres_at_every_spacing(self, spacing):
        got = measure_min_wall_thickness(_plate(3.0, 45.0), spacing_mm=spacing)
        assert got["normal_min_mm"] == pytest.approx(3.0, abs=1e-3)

    def test_the_axis_reading_moves_with_the_grid_while_the_normal_one_does_not(self):
        fine = measure_min_wall_thickness(_plate(3.0, 45.0), spacing_mm=0.5)
        coarse = measure_min_wall_thickness(_plate(3.0, 45.0), spacing_mm=1.0)
        assert fine["axis_min_mm"] != pytest.approx(coarse["axis_min_mm"], abs=1e-3), \
            "三轴读数本该随间距变化——这一条不成立就说明夹具退化成了轴对齐的板"
        assert fine["normal_min_mm"] == coarse["normal_min_mm"]


class TestWhyTheDegenerateNormalGuardIsThere:
    def test_occt_raises_instead_of_returning_a_unit_zero_normal(self):
        """`gp_Vec.Normalize()` 对零范数**抛异常**，不是给个 0。

        所以极点/奇异处必须先 `Magnitude()` 判一下再走：否则一面带奇异的模型会让整份
        DFM 报告当场崩，而不是少采一个点。本仓现有夹具没能造出零法向的曲面，
        因此这条打的是「危险确实存在」，不是「守卫被谁开过火」——
        电池里 W7（撤掉守卫）因此存活，如实记着。
        """
        from OCP.gp import gp_Vec

        with pytest.raises(Exception) as exc:
            gp_Vec(0.0, 0.0, 0.0).Normalize()
        assert "zero norm" in str(exc.value)
