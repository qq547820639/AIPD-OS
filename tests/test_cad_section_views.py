"""剖视图（section view）：用本地内核真做布尔切割，剖面用**真 HATCH 实体**填剖面线。

F-DRAW-01 第 4 片。切片前的现状：出图只有六个外部正视图，孔内部被外壁挡住 ⇒
一张图看不出孔是不是通孔、壁厚多少。这一片补剖视。

选型（都做过实测）：
- **A（选定）** 用 cadquery/OCP 做半空间布尔切割，再沿用已有的射线遮挡投影，
  切出的材料面用 ezdxf 的 ``HATCH`` 实体（``paths.add_polyline_path`` +
  ``set_pattern_fill("ANSI31")``）填充；
- B 只在投影里挑「落在切割面上的边」：便宜，但拿不到闭合区域、算不出材料面积，
  也证明不了投影没把形状画歪；
- C FreeCAD/TechDraw 的剖视：本机未安装、未读源码，不作依据，
  且与本仓「本地纯 Python 内核」方向冲突。

本机实测（写进用例的前提，不是记忆）：100×20×10 板、4 个 Ø8 通孔，
用半空间盒切去 ``y<0`` 后，在 ``y=0`` 平面上恰好得到 **5 个材料面**，
面积 ``160,120,120,120,160``（合计 680 mm²），与手算 ``(16+12+12+12+16)×10`` 一致
（孔 Ø8 ⇒ 材料宽依次 16,12,12,12,16，板厚 10）。另有 5 个 ``y≈1.91`` 的孔壁面与 1 个 ``y=10`` 外壁面
法向也满足 ``|n·ŷ|=1`` ⇒ **只按法向筛面会把外壁当成剖面**，必须再加「面心到平面的距离」这一条。
"""
from __future__ import annotations

from pathlib import Path

import pytest

cadquery = pytest.importorskip("cadquery", reason="cad 为可选 extra")
pytest.importorskip("ezdxf", reason="DXF 写出依赖 ezdxf")

import ezdxf  # noqa: E402

from aipd_os.cad.drawings2d import generate_drawing, section_view  # noqa: E402

L, W, T, HD = 100.0, 20.0, 10.0, 8.0
HOLE_X = [-30.0, -10.0, 10.0, 30.0]
AREAS = [160.0, 120.0, 120.0, 120.0, 160.0]


def _plate():
    return (cadquery.Workplane("XY").box(L, W, T).faces(">Z").workplane()
            .pushPoints([(x, 0.0) for x in HOLE_X]).hole(HD).solids().vals()[0])


def _shoelace(poly):
    s = 0.0
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def _section(tmp_path, name="sec", axis="Y", offset=0.0, views=()):
    out = Path(tmp_path) / f"{name}.dxf"
    ev = generate_drawing(_plate(), out, part_name="plate", revision="A",
                          views=tuple(views), sections=[f"{axis}={offset}"])
    return ev, out


def _view(ev, name):
    return next(v for v in ev["views"] if v["view"] == name)


class TestCutIsRealGeometry:
    def test_section_finds_the_five_material_regions(self, tmp_path):
        view = section_view(_plate(), "SECTION_Y", "Y")
        assert view.name == "SECTION_Y"
        areas = sorted(round(_shoelace(r), 3) for r in view.cut_regions)
        assert areas == sorted(AREAS), "剖面材料区必须与 OCP 量到的面面积一致"
        assert sum(areas) == pytest.approx(680.0, abs=1e-6)

    def test_outer_wall_is_not_mistaken_for_the_cut_face(self, tmp_path):
        """法向也满足 |n·ŷ|=1 的后外壁（100×10）不得混进剖面——只筛法向就会中这个坑。"""
        view = section_view(_plate(), "SECTION_Y", "Y")
        assert all(len(r) >= 3 for r in view.cut_regions)
        assert not any(abs(_shoelace(r) - 1000.0) < 1.0 for r in view.cut_regions), \
            "把外壁（100×10）当剖面 ⇒ 材料面积凭空多出 1000mm²"

    def test_section_projection_matches_the_model_envelope(self, tmp_path):
        ev, _ = _section(tmp_path, name="bbox")
        v = _view(ev, "SECTION_Y")
        assert v["size_mm"] == [pytest.approx(100.0, abs=1e-6), pytest.approx(10.0, abs=1e-6)]
        assert v["section_of"] == {"axis": "Y", "offset": 0.0, "kept": "y>=0",
                                   "normal": [0.0, 1.0, 0.0]}
        assert v["cut_regions"] == 5 and v["material_area_mm2"] == pytest.approx(680.0)

    def test_cutting_outside_the_geometry_is_reported_not_hidden(self, tmp_path):
        """切平面落在实体外 ⇒ 0 个材料区要显式说出来，不能交一张空白剖视当成果。"""
        ev, _ = _section(tmp_path, name="empty", axis="Y", offset=80.0)
        v = _view(ev, "SECTION_Y")
        assert v["cut_regions"] == 0
        assert v["section_empty"] is True
        assert ev["section_issues"], "空剖视必须进问题清单"


class TestHatchIsARealEntity:
    def test_cut_regions_become_closed_ansi31_hatches(self, tmp_path):
        ev, out = _section(tmp_path, name="hatch")
        doc = ezdxf.readfile(str(out))
        hatches = [e for e in doc.modelspace() if e.dxftype() == "HATCH"]
        assert len(hatches) == 5, "每个材料区一条 HATCH，不多不少"
        for h in hatches:
            assert h.dxf.pattern_name == "ANSI31"
            assert len(h.paths) == 1
            path = h.paths[0]
            assert len(path.vertices) >= 4
        assert ev["entity_counts"].get("HATCH") == 5

    def test_hatch_boundary_area_equals_the_measured_region_area(self, tmp_path):
        """填进去的多边形与内核量到的面必须同面积——投影/缩放走偏一眼看得见。"""
        _, out = _section(tmp_path, name="hatch_area")
        doc = ezdxf.readfile(str(out))
        areas = sorted(round(_shoelace([(v[0], v[1]) for v in h.paths[0].vertices]), 3)
                       for h in doc.modelspace() if h.dxftype() == "HATCH")
        assert areas == sorted(AREAS)


class TestChainLoopGuard:
    """接不上环的多边形**不能**静默填进去：宁可不填并说出来。"""

    def test_a_gap_in_the_segments_is_reported_as_not_closed(self):
        from aipd_os.cad.drawings2d import _chain_loop

        loop, closed = _chain_loop([[(0.0, 0.0), (10.0, 0.0)], [(11.0, 0.0), (11.0, 10.0)]])
        assert closed is False, "有缺口还判闭合 ⇒ 后面会拿一个自交多边形去填充"
        assert len(loop) == 2, "接不上时要如实返回已经接到的部分，不编造整圈"

    def test_uncloseable_boundary_skips_fill_and_says_so(self, tmp_path, monkeypatch):
        """把边界投影换成「接不成环」，验证：不填 HATCH、面积 0、问题清单说清是断环而不是没切到。"""
        import ezdxf as _ezdxf

        from aipd_os.cad import drawings2d

        monkeypatch.setattr(drawings2d, "_projected_wire",
                            lambda wire, project: ([(0.0, 0.0), (10.0, 0.0)], False))
        out = Path(tmp_path) / "broken.dxf"
        ev = generate_drawing(_plate(), out, part_name="plate", revision="A",
                              views=(), sections=["Y=0"])
        v = _view(ev, "SECTION_Y")
        assert v["cut_regions"] == 0 and v["section_empty"] is True
        assert v["material_area_mm2"] == 0
        doc = _ezdxf.readfile(str(out))
        assert [e for e in doc.modelspace() if e.dxftype() == "HATCH"] == []
        text = " ".join(ev["section_issues"])
        assert "接不成闭合环" in text, text
        assert "没切到任何材料" not in text, "切到了材料却报『没切到』是把原因说反"


class TestCliSurface:
    def test_bad_section_spec_is_a_usage_error(self, tmp_path):
        from aipd_os.cli.main import main

        rc = main(["drawing", "generate", "--out", str(tmp_path / "x.dxf"),
                   "--part", "plate", "--views", "TOP", "--section", "Q=0"])
        assert rc == 2
        assert not (tmp_path / "x.dxf").exists()

    def test_sections_combine_with_ordinary_views(self, tmp_path):
        from aipd_os.cli.main import main

        out = tmp_path / "both.dxf"
        rc = main(["drawing", "generate", "--out", str(out), "--part", "plate",
                   "--views", "TOP", "--section", "Y=0", "--json"])
        assert rc == 0
        ev = __import__("json").loads(out.with_suffix(".evidence.json").read_text("utf-8"))
        assert [v["view"] for v in ev["views"]] == ["TOP", "SECTION_Y"]
        assert _view(ev, "TOP").get("section_of") is None

    def test_empty_section_holds_the_command(self, tmp_path, capsys):
        """切到空气的剖平面不能算出图成功：要明说原因并返回 4，交一张空剖视不是成果。"""
        from aipd_os.cli.main import main

        rc = main(["drawing", "generate", "--out", str(tmp_path / "e.dxf"),
                   "--part", "plate", "--views", "TOP", "--section", "Y=10000"])
        assert rc == 4
        text = capsys.readouterr().out
        assert "没切到任何材料" in text and "未收口" in text

    def test_cut_material_area_is_reported_per_view(self, tmp_path, capsys):
        """剖视图要说人话：切在哪、保留哪一侧、量到几个材料区多大面积。"""
        from aipd_os.cli.main import main

        rc = main(["drawing", "generate", "--out", str(tmp_path / "ok.dxf"),
                   "--part", "plate", "--views", "TOP", "--section", "Y=0"])
        assert rc == 0
        text = capsys.readouterr().out
        assert "SECTION_Y" in text and "材料区" in text and "剖面线" in text
        assert "未收口" not in text
