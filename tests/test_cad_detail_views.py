"""局部放大图（detail view）：把母视图上一个小区域裁出来、按倍数放大再画一张。

F-DRAW-01 第 9 片。图纸上 Ø6 孔标 ±0.02 这种紧公差，1:1 视图里字高 3.5mm 的偏差
根本读不出来——车间只能猜。局部放大是解决它的正规手段，所以这一片要的是
**同一处实测几何的放大版**，不是第二张图。

判据为什么可以机器核（不是「看着清楚」这种主观判断）：

- 圆裁剪是解析可判的：线段 ``a+t(b-a)`` 落在 ``|p-c|<=R`` 内的 t 区间由一元二次方程
  给出，所以「裁剩下什么」有闭式答案。夹具里 100×20×10 板、TOP 视图外沿 ``v=±10``，
  以 ``(-30,0)`` 为心 ``R=12`` 裁，交线必在 ``u=-30±√(144-100)`` ⇒ 被裁出的那条水平
  线段长度精确等于 ``2√44``。**这个数不来自任何参数表，只来自圆与直线的位置。**
- 放大图的尺寸**不许**自己量：裁剪窗宽 13.27、高 20 是「窗」的尺寸，把它当零件总体宽标
  上去就是凭空造出一条零件上不存在的尺寸（本模块一直守的「缺声明不折算成 0」同一条线）。
  所以放大图只**继承**母视图已量出的尺寸，且按测点是否落在圆内筛。
- 继承必须保住**特征名**：``TOP.hole_1`` 到了放大图还是 ``TOP.hole_1``（外加
  ``inherited_from``），因为整条 CTQ 溯源是按视图前缀名匹配的；重新按放大图量一遍会
  得到 ``DETAIL_1.hole_1``，声明好的公差就全落进 ``spec_unmatched_features`` 了。
- 「什么都没圈到」不能出一张空图：空放大图照样编号、照样在母视图上画圈，等于图纸声称
  这里有一张读得清的详图而它什么都没有——与第 8 片「空剖视不编号」同一条规矩。

已知边界（诚实记录，不当已具备）：放大图是母视图**已判定可见/隐藏**折线的二维裁剪，
不是像 FreeCAD TechDraw 那样用圆柱与实体求交后重新投影（``DrawViewDetail.cpp`` 的
``BRepPrimAPI_MakeCylinder`` + ``FCBRepAlgoAPI_Common``，还配了 ``m_fudge = 1.01``
的放大半径兜边界）。选二维裁剪的理由见
``docs/audit/CAD_DETAIL_VIEWS_F-DRAW-01_2026-09-24.md``。
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest

cadquery = pytest.importorskip("cadquery", reason="cad 为可选 extra")
pytest.importorskip("ezdxf", reason="DXF 输出依赖 ezdxf")

import ezdxf  # noqa: E402

from aipd_os.cad.drawings2d import (  # noqa: E402
    clip_polyline_to_circle,
    detect_circles,
    generate_drawing,
    parse_detail_spec,
)

L, W, T = 100.0, 20.0, 10.0
CROP_R = 12.0
EDGE_V = W / 2.0                                   # TOP 视图外沿 v=±10
HIT_HALF = math.sqrt(CROP_R ** 2 - EDGE_V ** 2)    # 交线到圆心的水平距离 = √44
CHORD = 2.0 * HIT_HALF                             # 被裁出的外沿长 = 2√44 ≈ 13.2665


def _plate():
    return (cadquery.Workplane("XY").box(L, W, T).faces(">Z").workplane()
            .pushPoints([(-30.0, 0.0), (-10.0, 0.0), (10.0, 0.0), (30.0, 0.0)])
            .hole(6.0).solids().vals()[0])


def _gen(tmp_path, details=("TOP@(-30,0)/12=2",), views=("TOP", "FRONT"),
         sections=(), scale=1.0, spec=None, name="detail"):
    out = Path(tmp_path) / f"{name}.dxf"
    ev = generate_drawing(_plate(), out, part_name="plate", revision="A",
                          views=tuple(views), sections=tuple(sections),
                          scale=scale, spec=spec, details=tuple(details))
    return ev, out


def _view(ev, name):
    return next(v for v in ev["views"] if v["view"] == name)


def _dims(view_ev):
    return {d["feature"]: d for d in view_ev["dimensions"]}


def _ents(path, types, layer=None):
    doc = ezdxf.readfile(str(path))
    return [e for e in doc.modelspace()
            if e.dxftype() in types and (layer is None or e.dxf.layer == layer)]


def _texts(path, layer="TEXT"):
    doc = ezdxf.readfile(str(path))
    return [(t.dxf.text.strip(), (t.dxf.insert.x, t.dxf.insert.y))
            for t in doc.modelspace()
            if t.dxftype() == "TEXT" and t.dxf.layer == layer]


def _length(entity) -> float:
    return math.hypot(entity.dxf.end.x - entity.dxf.start.x,
                      entity.dxf.end.y - entity.dxf.start.y)


class TestParsing:
    def test_the_documented_shape_parses(self):
        assert parse_detail_spec("TOP@(-30,0)/12=2") == ("TOP", (-30.0, 0.0), 12.0, 2.0)
        # 括号是写法糖，不是语义
        assert parse_detail_spec("TOP@-30,0/12=2") == ("TOP", (-30.0, 0.0), 12.0, 2.0)

    def test_bad_shapes_raise_instead_of_guessing(self):
        for bad in ("TOP", "TOP@(-30,0)", "TOP@(-30)/12=2", "TOP@(-30,x)/12=2",
                    "TOP@(-30,0)/12", "TOP@(-30,0)/y=2", "@(-30,0)/12=2",
                    "TOP@(0,0)/0=2", "TOP@(0,0)/-3=2", "TOP@(0,0)/12=x"):
            with pytest.raises(ValueError):
                parse_detail_spec(bad)

    def test_a_factor_of_one_is_not_a_magnification(self):
        """放大倍数 <=1 就不是局部放大：静默接受会出一张和母视图一样大的「放大图」。"""
        with pytest.raises(ValueError) as exc:
            parse_detail_spec("TOP@(-30,0)/12=1")
        assert "放大" in str(exc.value)


class TestCircularClip:
    def test_a_line_is_cut_where_the_circle_crosses_it(self):
        """v=10 那条外沿被 R=12 的圆裁出 √44 的半跨——闭式解，不是调容差调出来的。"""
        pieces = clip_polyline_to_circle([(-50.0, EDGE_V), (50.0, EDGE_V)],
                                         (-30.0, 0.0), CROP_R)
        assert len(pieces) == 1
        p0, p1 = pieces[0]
        assert p0 == pytest.approx((-30.0 - HIT_HALF, EDGE_V), abs=1e-9)
        assert p1 == pytest.approx((-30.0 + HIT_HALF, EDGE_V), abs=1e-9)
        assert math.hypot(p1[0] - p0[0], p1[1] - p0[1]) == pytest.approx(CHORD, abs=1e-9)

    def test_a_line_outside_the_circle_yields_nothing(self):
        assert clip_polyline_to_circle([(-50.0, 40.0), (50.0, 40.0)],
                                       (-30.0, 0.0), CROP_R) == []

    def test_the_kept_piece_spans_exactly_the_chord(self):
        pieces = clip_polyline_to_circle([(-50.0, 0.0), (50.0, 0.0)],
                                         (-30.0, 0.0), CROP_R)
        assert len(pieces) == 1
        assert pieces[0][0][0] == pytest.approx(-42.0, abs=1e-9)
        assert pieces[0][-1][0] == pytest.approx(-18.0, abs=1e-9)

    def test_a_closed_circle_fully_inside_stays_a_closed_circle(self):
        """整圆被裁后仍闭合，所以孔照样量得出 Ø6——放大图能标注全靠这一条。"""
        pts = [(3.0 * math.cos(2 * math.pi * i / 48), 3.0 * math.sin(2 * math.pi * i / 48))
               for i in range(49)]
        pieces = clip_polyline_to_circle(pts, (0.0, 0.0), 12.0)
        assert len(pieces) == 1
        assert pieces[0][0] == pytest.approx(pieces[0][-1], abs=1e-9)
        holes = detect_circles(pieces)
        assert len(holes) == 1 and holes[0]["diameter"] == pytest.approx(6.0, abs=0.05)

    def test_a_straddling_circle_is_not_claimed_as_a_hole(self):
        """被裁成开弧的圆**不许**继续当孔：那会给出一个量不出来的圆心与直径。

        孔心 (1,0) R1.5 落在裁剪圆（原点 R2）上：孔圆周到原点距离 0.5~2.5，
        一半在里一半在外 ⇒ 裁出来必是开弧。
        """
        pts = [(1.5 * math.cos(2 * math.pi * i / 48) + 1.0,
                1.5 * math.sin(2 * math.pi * i / 48)) for i in range(49)]
        pieces = clip_polyline_to_circle(pts, (0.0, 0.0), 2.0)
        assert pieces, "圆边确实切过了，不该一片不剩"
        assert detect_circles(pieces) == []


class TestTheDetailViewIsAMagnifiedCrop:
    def test_crop_keeps_only_geometry_inside_and_prints_it_at_the_magnification(
            self, tmp_path):
        ev, out = _gen(tmp_path)
        det = _view(ev, "DETAIL_1")
        # 上/下外沿各一段 + 左侧孔的整圆 = 3 处几何；母视图 TOP 每条轮廓线本就成对
        # 出现（顶面与底面轮廓从正上方看重合，分类器不去重），裁剪忠实照抄 ⇒ 6 段。
        # 「裁对没裁对」由下面的包围盒与图上线段长度判，不由这个条数判。
        assert det["visible_polylines"] == 6
        assert det["hidden_polylines"] == 0
        assert det["detail_of"] == {"parent": "TOP", "center": [-30.0, 0.0],
                                   "radius": 12.0, "factor": 2.0}
        assert det["drawn_scale"] == 2.0
        assert det["size_mm"] == [pytest.approx(CHORD * 2.0, abs=1e-3),
                                  pytest.approx(20.0 * 2.0, abs=1e-6)]
        # 图上真画出来的那段水平线，长度必须等于闭式解 ×放大倍数
        segs = [_length(e) for e in _ents(out, ("LINE",), "OUTLINE")]
        assert any(abs(s - CHORD * 2.0) < 1e-6 for s in segs), \
            f"放大 2 倍后图上应出现 {CHORD * 2:.4f}mm 的被裁外沿，实得 {segs}"

    def test_the_crop_window_is_never_reported_as_a_part_dimension(self, tmp_path):
        """裁剪窗 13.27×20 不是零件尺寸：出现 overall_width=13.266 就是凭空造尺寸。"""
        ev, _ = _gen(tmp_path)
        det = _view(ev, "DETAIL_1")
        kinds = {d["kind"] for d in det["dimensions"]}
        assert "overall_width" not in kinds and "overall_height" not in kinds
        values = {d["value"] for d in det["dimensions"]}
        assert not values & {round(CHORD, 3), 20.0, 13.266, 26.533, 24.0, 40.0}, values
        # 母视图自己的总体尺寸一条不少
        assert {"overall_width", "overall_height"} <= {
            d["kind"] for d in _view(ev, "TOP")["dimensions"]}

    def test_only_the_hole_inside_the_circle_is_inherited_and_keeps_its_name(
            self, tmp_path):
        ev, _ = _gen(tmp_path)
        det = _dims(_view(ev, "DETAIL_1"))
        assert set(det) == {"TOP.hole_1"}
        assert det["TOP.hole_1"]["value"] == pytest.approx(6.0, abs=0.05)
        assert det["TOP.hole_1"]["inherited_from"] == "TOP"
        # 母视图仍是 4 个孔（继承不改动母视图），且母视图的尺寸不带 inherited_from
        parent = _dims(_view(ev, "TOP"))
        assert {k for k in parent if ".hole_" in k} == {
            "TOP.hole_1", "TOP.hole_2", "TOP.hole_3", "TOP.hole_4"}
        assert "inherited_from" not in parent["TOP.hole_1"]

    def test_a_crop_wide_enough_inherits_the_inter_hole_chain_too(self, tmp_path):
        """半径 25 罩住 (-30,0) 与 (-10,0) 两个孔心：孔间距 chain_2 该进来；
        而以零件边缘为锚的 chain_1/chain_5 不该进来（那条 20mm 不是零件外沿）。"""
        ev, _ = _gen(tmp_path, details=("TOP@(-20,0)/25=2",), name="wide")
        det = _dims(_view(ev, "DETAIL_1"))
        assert {"TOP.hole_1", "TOP.hole_2", "TOP.chain_2"} <= set(det)
        assert not {"TOP.chain_1", "TOP.chain_5"} & set(det)
        assert det["TOP.chain_2"]["value"] == pytest.approx(20.0, abs=0.05)

    def test_traceability_survives_into_the_detail(self, tmp_path):
        spec = {"features": [{"feature": "TOP.hole_1",
                              "tolerance": {"upper": 0.02, "lower": -0.02},
                              "ctq_ref": "ctq-0001"}]}
        ev, _ = _gen(tmp_path, spec=spec, name="tr")
        det = _dims(_view(ev, "DETAIL_1"))["TOP.hole_1"]
        par = _dims(_view(ev, "TOP"))["TOP.hole_1"]
        assert det["tolerance"] == par["tolerance"] == {"upper": 0.02, "lower": -0.02}
        assert det["ctq_ref"] == "ctq-0001"
        assert ev["spec_unmatched_features"] == []
        # 母视图 + 放大图各贴一处：两处印刷、一条测量（发布证据不许数成两条覆盖）
        assert ev["tolerance_applied"] == 2

    def test_gdt_frames_stay_on_the_parent_because_names_resolve_there(self, tmp_path):
        """框按 ``TOP.hole_1`` 解析视图 ⇒ 只贴在 TOP 上，放大图不重复贴框。"""
        spec = {"features": [{"feature": "TOP.hole_1",
                              "gdt": [{"characteristic": "flatness", "zone": 0.05}]}]}
        ev, _ = _gen(tmp_path, spec=spec, name="gdt")
        assert len(ev["gdt_frames"]) == 1
        assert {f["view"] for f in ev["gdt_frames"]} == {"TOP"}


class TestWhatGoesOnTheSheet:
    def test_the_parent_carries_a_boundary_circle_at_the_declared_place(self, tmp_path):
        ev, out = _gen(tmp_path)
        top = _view(ev, "TOP")
        cx, cy = top["origin"]
        assert top["detail_markers"] == [{"number": 1, "of": "DETAIL_1",
                                          "center": [-30.0, 0.0], "radius": 12.0}]
        circles = sorted(_ents(out, ("CIRCLE",), "DETAIL"), key=lambda c: c.dxf.radius)
        assert [round(c.dxf.radius, 6) for c in circles] == [CROP_R, CROP_R * 2.0]
        # TOP 比例 1:1 且质心居中 ⇒ 视图局部 (u,v) 就落在 (cx+u, cy+v)；
        # 证据里的 origin 只留 2 位小数，所以这里比到 0.01 而不是 1e-6
        assert (circles[0].dxf.center.x, circles[0].dxf.center.y) == pytest.approx(
            (cx - 30.0, cy), abs=0.01)
        assert [t for t, _ in _texts(out, "DETAIL")] == ["1"]

    def test_the_detail_is_captioned_and_the_stale_ratio_label_is_gone(self, tmp_path):
        ev, out = _gen(tmp_path)
        captions = [t for t, _ in _texts(out, "TEXT")]
        assert "DETAIL 1  2:1" in captions, captions
        assert not [t for t in captions if t.startswith("DETAIL_1")], \
            "母视图那行 «NAME  1:1» 用的是全局比例，贴在放大图上就是错的"
        assert _view(ev, "DETAIL_1")["label"] == "DETAIL 1  2:1"

    def test_the_ratio_reflects_the_parent_scale_times_the_magnification(self, tmp_path):
        """--scale 0.5 的母视图放大 2 倍就是 1:1：报「2:1」会把看图人引到错尺寸。"""
        _, out = _gen(tmp_path, scale=0.5, name="half")
        assert "DETAIL 1  1:1" in [t for t, _ in _texts(out, "TEXT")]

    def test_two_details_number_1_and_2_without_touching_section_letters(
            self, tmp_path):
        ev, out = _gen(tmp_path, views=("TOP", "FRONT"), sections=("Y=0",),
                       details=("TOP@(-30,0)/12=2", "TOP@(30,0)/12=3"), name="two")
        assert ev["detail_numbers"] == {"DETAIL_1": 1, "DETAIL_2": 2}
        assert ev["section_letters"] == {"SECTION_Y": "A"}
        captions = [t for t, _ in _texts(out, "TEXT")]
        assert "A-A" in captions and "DETAIL 1  2:1" in captions
        assert "DETAIL 2  3:1" in captions
        assert len(_ents(out, ("CIRCLE",), "DETAIL")) == 4

    def test_a_detail_is_never_a_section_parent(self, tmp_path):
        """放大图是派生视图：在它上面再画一刀的剖切线，读图的人会以为那是另一处实体。"""
        ev, _ = _gen(tmp_path, views=("TOP", "FRONT"), sections=("Y=0",),
                     details=("TOP@(-20,0)/25=2",), name="derived")
        assert _view(ev, "DETAIL_1")["section_symbols"] == []
        assert [s["letter"] for s in _view(ev, "TOP")["section_symbols"]] == ["A"]


class TestNothingIsClaimedWithoutGeometry:
    def test_a_circle_that_catches_nothing_is_not_numbered_and_holds_the_sheet(
            self, tmp_path):
        ev, out = _gen(tmp_path, details=("TOP@(0,80)/5=2",), name="empty")
        det = _view(ev, "DETAIL_1")
        assert det["detail_empty"] is True
        assert det["label"] == ""
        assert ev["detail_numbers"] == {}
        assert any("没圈到" in m for m in ev["detail_issues"]), ev["detail_issues"]
        assert _ents(out, ("CIRCLE",), "DETAIL") == []
        assert [t for t, _ in _texts(out, "DETAIL")] == []

    def test_an_unknown_parent_is_a_declaration_error_not_a_silent_drop(self, tmp_path):
        with pytest.raises(ValueError) as exc:
            _gen(tmp_path, details=("BOTTOM@(-30,0)/12=2",), name="bad")
        assert "BOTTOM" in str(exc.value)

    def test_details_absent_means_the_drawing_is_unchanged(self, tmp_path):
        ev, out = _gen(tmp_path, details=(), name="none")
        assert [v["view"] for v in ev["views"]] == ["TOP", "FRONT"]
        assert ev["detail_numbers"] == {} and ev["detail_issues"] == []
        assert _ents(out, ("CIRCLE",), "DETAIL") == []


class TestTheFileStillReopensClean:
    def test_detail_layer_survives_the_recover_audit_without_errors(self, tmp_path):
        from ezdxf import recover

        _, out = _gen(tmp_path, name="audit")
        doc, auditor = recover.readfile(str(out))
        assert auditor.errors == [], [str(e) for e in auditor.errors]
        assert auditor.fixes == [], [str(f) for f in auditor.fixes]
        assert doc.layers.get("DETAIL") is not None
        kinds = sorted({e.dxftype() for e in doc.modelspace()
                        if e.dxf.layer == "DETAIL"})
        assert kinds == ["CIRCLE", "TEXT"]
