"""剖切符号（cutting-plane line + 字母 + 剖面视图标题 A-A）。

F-DRAW-01 第 8 片。第 4 片已经把剖视**算对**了（真布尔切割、量出材料区、填真 HATCH），
但图纸上仍缺一样东西：**母视图上没有剖切符号，剖视图上没有 «A-A» 标题**。
车间拿到一张「SECTION_Y」而不是 «A-A»，无法在母视图上找到那一刀切在哪、往哪看——
这在交付图纸上是歧义缺陷，不只是好看问题。

判据为什么可以机器核（不是渲染主观判断）：剖切平面在母视图的投影必是一条
二维直线 ``a·u + b·v = offset``，其中 ``a = right·n̂``、``b = up·n̂``，
``n̂`` 是剖切面法向；母视图的定义就是视线方向与 ``n̂`` 垂直。于是

- 视线与 ``n̂`` 平行（即剖视图自己，或视线沿切割方向）⇒ 该视图**不该**有剖切符号；
- 剖切线在母视图里必须**严格落在**上面那条直线上（两端点都满足方程）；
- 保持侧方向 = ``(a, b)/√(a²+b²)``（沿它移动会让 ``p·n̂`` 变大，也就是 ``>= offset``
  那一侧），所以短划必须指向被保留的一侧；
- 符号长度必须**盖住**母视图在该方向上的轮廓跨度（从四角点算），并向两端各伸出余量。

夹具前提（实测，不是记忆）：100×20×10 板、4 个 Ø6 通孔；切 ``Y=0`` 保 ``y>=0`` 时
TOP 视图（视线 −Z、up +Y）的剖切线就是 ``v = 0`` 的一条横线，横跨 x∈[-50, 50]
（母视图轮廓宽 100）；FRONT 视图（视线 +Y）与切割方向共线 ⇒ 不该出现符号。
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest

cadquery = pytest.importorskip("cadquery", reason="cad 为可选 extra")
pytest.importorskip("ezdxf", reason="DXF 输出依赖 ezdxf")

import ezdxf  # noqa: E402

from aipd_os.cad.drawings2d import generate_drawing  # noqa: E402

L, W, T = 100.0, 20.0, 10.0
OVERHANG_MIN = 1.0     # 剖切线至少向轮廓两端各伸出这么多（图纸 mm），太短就等于没画


def _plate():
    return (cadquery.Workplane("XY").box(L, W, T).faces(">Z").workplane()
            .pushPoints([(-30.0, 0.0), (-10.0, 0.0), (10.0, 0.0), (30.0, 0.0)])
            .hole(6.0).solids().vals()[0])


def _gen(tmp_path, views=("TOP", "FRONT", "SECTION_Y"), sections=("Y=0",), name="sym"):
    out = Path(tmp_path) / f"{name}.dxf"
    ev = generate_drawing(_plate(), out, part_name="plate", revision="A",
                          views=tuple(v for v in views if not v.startswith("SECTION")),
                          sections=tuple(sections))
    return ev, out


def _view(ev, name):
    return next(v for v in ev["views"] if v["view"] == name)


def _ents(path, types=("LINE", "LWPOLYLINE"), layer="SECTION"):
    doc = ezdxf.readfile(str(path))
    return [e for e in doc.modelspace()
            if e.dxftype() in types and e.dxf.layer == layer]


def _texts(path, layer="SECTION"):
    doc = ezdxf.readfile(str(path))
    return [(t.dxf.text.strip(), (t.dxf.insert.x, t.dxf.insert.y))
            for t in doc.modelspace()
            if t.dxftype() == "TEXT" and t.dxf.layer == layer]


class TestSymbolOnTheParentView:
    def test_the_parent_view_gets_a_cutting_line_that_lies_on_the_cut_plane(self, tmp_path):
        ev, out = _gen(tmp_path)
        sym = _view(ev, "TOP")["section_symbols"]
        assert len(sym) == 1
        one = sym[0]
        assert one["letter"] == "A" and one["axis"] == "Y" and one["offset"] == 0.0
        # TOP 视图里 y=0 的剖切平面投影成 v=0 的水平线：两端点都必须严格在直线上
        assert one["from"][1] == pytest.approx(0.0, abs=1e-6)
        assert one["to"][1] == pytest.approx(0.0, abs=1e-6)
        assert one["from"][0] == pytest.approx(-one["to"][0], abs=1e-6)
        span = abs(one["to"][0] - one["from"][0])
        assert span >= L + 2 * OVERHANG_MIN, "剖切线必须盖住母视图轮廓并向两端伸出余量"
        assert _ents(out), "证据说画了，图上就得有真实体"

    def test_the_letters_and_ticks_are_on_the_kept_side(self, tmp_path):
        """字母与端部短划要指被保留的一侧（这里是 y>=0 ⇒ +v 方向）。"""
        ev, out = _gen(tmp_path)
        origin = _view(ev, "TOP")["origin"]          # 视图中心（放置坐标）
        labels = [t for t in _texts(out) if t[0] == "A"]
        assert len(labels) == 2, "两端各一个字母"
        assert all(pt[1] > origin[1] for _, pt in labels), labels
        kept = _view(ev, "TOP")["section_symbols"][0]["kept_side"]
        assert kept == pytest.approx([0.0, 1.0], abs=1e-6)

    def test_a_view_looking_along_the_cut_normal_gets_no_symbol(self, tmp_path):
        """FRONT 的视线就是 +Y（与剖切面法向平行）⇒ 它不是母视图，硬画就是错标。"""
        ev, out = _gen(tmp_path)
        assert _view(ev, "FRONT")["section_symbols"] == []

    def test_the_section_view_itself_has_no_symbol_but_a_title(self, tmp_path):
        ev, out = _gen(tmp_path)
        sec = _view(ev, "SECTION_Y")
        assert sec["section_symbols"] == []
        assert sec["label"] == "A-A"
        titles = [t for t in _texts(out, layer="TEXT") if t[0] == "A-A"]
        assert len(titles) == 1, "剖面标题 «A-A» 恰好一条"

    def test_end_ticks_are_perpendicular_to_the_cut_line(self, tmp_path):
        _, out = _gen(tmp_path)
        lines = [(math.atan2(e.dxf.end.y - e.dxf.start.y, e.dxf.end.x - e.dxf.start.x),
                  math.hypot(e.dxf.end.x - e.dxf.start.x, e.dxf.end.y - e.dxf.start.y))
                 for e in _ents(out)]
        long_ones = [a for a, ln in lines if ln > L]
        short_ones = [a for a, ln in lines if ln <= L]
        assert long_ones and short_ones, "既有剖切线也有端部短划"
        for a in short_ones:
            assert abs(abs(math.sin(a - long_ones[0])) - 1.0) < 1e-6, \
                "短划必须垂直于剖切线，否则看图人读不出投影方向"


class TestMultipleSections:
    def test_two_cuts_get_two_letters_and_two_titles(self, tmp_path):
        ev, out = _gen(tmp_path, views=("TOP", "FRONT", "SECTION_Y", "SECTION_Z"),
                       sections=("Y=0", "Z=2"), name="two")
        assert _view(ev, "SECTION_Y")["label"] == "A-A"
        assert _view(ev, "SECTION_Z")["label"] == "B-B"
        assert ev["section_letters"] == {"SECTION_Y": "A", "SECTION_Z": "B"}
        titles = sorted(t for t, _ in _texts(out, layer="TEXT") if t in ("A-A", "B-B"))
        assert titles == ["A-A", "B-B"]
        # Z=5 的母视图是 FRONT（视线 +Y 与 z 轴垂直）——它拿到 B，不是重复的 A
        front = _view(ev, "FRONT")["section_symbols"]
        assert [s["letter"] for s in front] == ["B"]
        top = [s["letter"] for s in _view(ev, "TOP")["section_symbols"]]
        assert top == ["A"]
        # 符号的位置由偏移决定：z=2 这一刀在 FRONT 里必须是 v=2 的水平线，
        # 而不是「过视图原点的那条」
        cut = front[0]
        assert cut["from"][1] == pytest.approx(2.0, abs=1e-6)
        assert cut["to"][1] == pytest.approx(2.0, abs=1e-6)
        assert cut["kept_side"] == pytest.approx([0.0, 1.0], abs=1e-6)


class TestNothingIsClaimedWithoutGeometry:
    def test_no_section_means_no_symbol_layer_at_all(self, tmp_path):
        ev, out = _gen(tmp_path, views=("TOP", "FRONT"), sections=(), name="none")
        assert all(v["section_symbols"] == [] for v in ev["views"])
        assert _ents(out) == []
        assert _texts(out) == []

    def test_evidence_records_the_line_endpoints_not_just_a_flag(self, tmp_path):
        """只报「画了符号」不可复核；端点与方向都进证据，读图时逐字对得上。"""
        ev, out = _gen(tmp_path, name="evid")
        one = _view(ev, "TOP")["section_symbols"][0]
        for key in ("letter", "axis", "offset", "from", "to", "kept_side", "ticks"):
            assert key in one, key
        assert one["ticks"] == 2
        lines = _ents(out)
        assert len(lines) == 3, "一条剖切线 + 两端短划，不多不少"
        longest = max(lines, key=lambda e: math.hypot(e.dxf.end.x - e.dxf.start.x,
                                                      e.dxf.end.y - e.dxf.start.y))
        drawn = math.hypot(longest.dxf.end.x - longest.dxf.start.x,
                           longest.dxf.end.y - longest.dxf.start.y)
        # 比例 1:1 ⇒ 图上的剖切线长度必须与证据里的端点距离逐毫米一致
        assert drawn == pytest.approx(abs(one["to"][0] - one["from"][0]), abs=1e-6)


class TestTheFileStillReopensClean:
    def test_section_layer_survives_the_recover_audit_without_errors(self, tmp_path):
        """引用不存在的 linetype/图层会让 DXF 在别的软件里被判损坏：审计必须 0 错 0 修。"""
        from ezdxf import recover

        _, out = _gen(tmp_path, views=("TOP", "FRONT", "SECTION_Y"),
                      sections=("Y=0",), name="audit")
        doc, auditor = recover.readfile(str(out))
        assert auditor.errors == [], [str(e) for e in auditor.errors]
        assert auditor.fixes == [], [str(f) for f in auditor.fixes]
        assert doc.layers.get("SECTION") is not None
        kinds = sorted({e.dxftype() for e in doc.modelspace()
                        if e.dxf.layer == "SECTION"})
        assert kinds == ["LINE", "TEXT"]
        lines = [e for e in doc.modelspace()
                 if e.dxf.layer == "SECTION" and e.dxftype() == "LINE"]
        longest = max(lines, key=lambda e: math.hypot(e.dxf.end.x - e.dxf.start.x,
                                                      e.dxf.end.y - e.dxf.start.y))
        assert longest.dxf.linetype in ("PHANTOM", "DASHED"), longest.dxf.linetype
        assert longest.dxf.linetype in {t.dxf.name for t in doc.linetypes}, \
            "剖切线用的线型必须在文档的线型表里，否则文件在别的软件里算损坏"


class TestDerivedViewsAreNotParents:
    def test_a_section_view_never_carries_another_sections_symbol(self, tmp_path):
        """剖视图自己不标别的剖的符号。

        这条不是多余的：剖视图的视线（例如 SECTION_Y 看向 +Y）与**另一刀**（Z=5）的法向
        并不平行，几何上确实能投出一条交线——所以「派生视图不当母视图」是显式规则，
        不是几何判据的副产品。少了它，图上会在剖视图里再画一条别刀的剖切线。
        """
        ev, _ = _gen(tmp_path, views=("TOP", "FRONT", "SECTION_Y", "SECTION_Z"),
                     sections=("Y=0", "Z=2"), name="no_chain")
        assert _view(ev, "SECTION_Y")["section_symbols"] == []
        assert _view(ev, "SECTION_Z")["section_symbols"] == []
        assert sum(len(v["section_symbols"]) for v in ev["views"]) == 2, \
            "两刀各自只有一个母视图带符号：TOP 拿 A、FRONT 拿 B"


class TestEmptySectionsGetNoLabel:
    def test_a_section_that_hits_no_material_is_not_lettered_or_symboled(self, tmp_path):
        """空剖视不该有 «B-B» 标题、也不该在母视图上留一条剖切线。

        真机发现的：切到空气的那一刀照样编号并把符号画到 FRONT 上，
        等于图纸声称「这里有一张 B-B 剖视」而它什么都没有。
        """
        ev, _ = _gen(tmp_path, views=("TOP", "FRONT", "SECTION_Y", "SECTION_Z"),
                     sections=("Y=0", "Z=999"), name="empty_cut")
        assert ev["section_letters"] == {"SECTION_Y": "A"}
        empty = _view(ev, "SECTION_Z")
        assert empty["label"] == "" and empty["section_symbols"] == []
        assert empty["cut_regions"] == 0 and empty["section_empty"] is True
        assert any("没切到任何材料" in m for m in empty["section_problems"])
        assert [s["letter"] for s in _view(ev, "FRONT")["section_symbols"]] == []
        assert [s["letter"] for s in _view(ev, "TOP")["section_symbols"]] == ["A"]


class TestEveryParentViewGetsTheSameLetter:
    def test_top_and_bottom_both_carry_A_for_the_same_cut(self, tmp_path):
        """同一刀有多个母视图时（TOP 与 BOTTOM 都看得见 XY 面），两边都要标同一个字母。

        只标第一个会漏：看图的人未必正在看 TOP。
        """
        ev, _ = _gen(tmp_path, views=("TOP", "BOTTOM", "SECTION_Y"),
                     sections=("Y=0",), name="two_parents")
        by_name = {v["view"]: v for v in ev["views"]}
        assert [s["letter"] for s in by_name["TOP"]["section_symbols"]] == ["A"]
        assert [s["letter"] for s in by_name["BOTTOM"]["section_symbols"]] == ["A"]
        assert by_name["TOP"]["section_symbols"][0]["from"] == \
               by_name["BOTTOM"]["section_symbols"][0]["from"]
