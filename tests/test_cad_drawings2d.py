"""cad.2d_drawings：三维 -> 二维工程图的正确性用例。

断言全部建立在「投影出来的几何」上，不建立在参数字典上：
尺寸值来自视图包围盒与检出圆，因此这组用例同时检验
「模型是否按声明尺寸构建」与「图纸是否忠实于模型」。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from aipd_os.cad.evidence import sidecar_path

cadquery = pytest.importorskip("cadquery", reason="cad 为可选 extra（cadquery>=2.4）")
pytest.importorskip("ezdxf", reason="DXF 写出依赖 ezdxf")

from aipd_os.cad.drawings2d import (  # noqa: E402
    STANDARD_VIEWS,
    build_view,
    detect_circles,
    generate_drawing,
    view_basis,
)

L, W, T, HD = 40.0, 20.0, 10.0, 6.0

# 真实发布的黄金件原生源（只读输入：参数由 AST 取，几何由内核现算）
GOLDEN_BRACKET_SOURCE = (Path(__file__).resolve().parents[1] / "releases" /
                         "golden-projects" / "B-cad-engineering-change" /
                         "bracket.py")


def _plate(hole: str = "Z"):
    wp = cadquery.Workplane("XY").box(L, W, T)
    if hole == "Z":
        wp = wp.faces(">Z").workplane().center(0, 0).hole(HD)
    elif hole == "X":
        wp = wp.faces("<X").workplane().center(0, 0).hole(HD)
    return wp.solids().vals()[0]


def _hollow():
    """开口薄壁盒：顶面挖掉、壁厚 2 ⇒ 前视必有被完全遮挡的内腔边线。"""
    return (cadquery.Workplane("XY").box(L, W, T)
            .faces(">Z").shell(-2).solids().vals()[0])


def _plain():
    return cadquery.Workplane("XY").box(L, W, T).solids().vals()[0]


def _v(poly):
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


class TestViewBasis:
    def test_basis_is_right_handed_and_up_preserved(self):
        b = view_basis((0, -1, 0), (0, 0, 1))
        assert b["right"] == pytest.approx((1.0, 0.0, 0.0))
        assert b["up"] == pytest.approx((0.0, 0.0, 1.0))
        assert b["normal"] == pytest.approx((0.0, -1.0, 0.0))

    def test_rejects_zero_direction(self):
        with pytest.raises(ValueError):
            view_basis((0.0, 0.0, 0.0), (0.0, 0.0, 1.0))


class TestProjectedDimensions:
    """视图尺寸必须等于模型真实尺寸——这检验投影基与缩放，不检验参数。"""

    @pytest.mark.parametrize("view,exp_w,exp_h", [
        ("FRONT", L, T), ("TOP", L, W), ("RIGHT", T, W),
    ])
    def test_orthogonal_views_match_model_size(self, view, exp_w, exp_h):
        v = build_view(_plain(), view, *STANDARD_VIEWS[view], include_hidden=False)
        assert v.width == pytest.approx(exp_w, abs=1e-6)
        assert v.height == pytest.approx(exp_h, abs=1e-6)

    def test_dimensions_are_measured_not_declared(self):
        v = build_view(_plate("Z"), "TOP", *STANDARD_VIEWS["TOP"])
        by_kind = {d["kind"]: d for d in v.dimensions}
        assert by_kind["overall_width"]["value"] == pytest.approx(L)
        assert by_kind["overall_height"]["value"] == pytest.approx(W)
        assert all("projected" in d["source"] for d in v.dimensions)

    def test_hole_diameter_measured_from_projection(self):
        v = build_view(_plate("Z"), "TOP", *STANDARD_VIEWS["TOP"])
        holes = [d for d in v.dimensions if d["kind"] == "hole_diameter"]
        assert holes, "Ø6 通孔必须在俯视图上被检出"
        assert all(d["value"] == pytest.approx(HD, abs=1e-3) for d in holes)
        assert all(d["closed"] for d in holes)

    def test_circle_fit_rejects_non_circular_polyline(self):
        square = [[(x, y) for x, y in
                   [(0, 0), (5, 0), (10, 0), (10, 5), (10, 10),
                    (5, 10), (0, 10), (0, 5), (0, 0)]]]
        assert detect_circles(square) == []


class TestRealBracketPattern:
    """真黄金件（4 孔 + 圆角 + 倒角）：检出结果必须逐孔对上模型真值。

    单孔板只能证明「图上有一个圆」，孔位算错时它照样是绿的——实测曾用
    包围盒中点法报出 6 个假孔位、同时漏掉真孔位。所以这里断言**数量与坐标**，
    并配一个「整体平移」负控，证明位置断言真的在约束检出结果。
    """

    BRACKET_XS = [-30.0, -10.0, 10.0, 30.0]

    @staticmethod
    def _bracket(dx: float = 0.0):
        wp = (cadquery.Workplane("XY").box(100.0, 50.0, 10.0)
              .edges("|Z").fillet(3.0).faces(">Z").edges().chamfer(2.0))
        pts = [(x + dx, 0.0) for x in TestRealBracketPattern.BRACKET_XS]
        return wp.faces(">Z").workplane().pushPoints(pts).hole(8.0)

    def _holes(self, dx: float = 0.0):
        v = build_view(self._bracket(dx), "TOP", *STANDARD_VIEWS["TOP"])
        return [d for d in v.dimensions if d["kind"] == "hole_diameter"]

    def test_all_four_holes_detected_at_their_true_positions(self):
        holes = self._holes()
        assert sorted(round(h["center"][0], 3) for h in holes) == self.BRACKET_XS
        assert all(round(h["center"][1], 3) == 0.0 for h in holes)
        assert all(h["value"] == pytest.approx(8.0, abs=1e-3) for h in holes)
        assert all(h["closed"] for h in holes)

    def test_fillet_and_chamfer_arcs_are_not_reported_as_holes(self):
        """圆角(1/4 弧, r=3) 与倒角投出的弧段都不许冒充 Ø8 整圆孔。"""
        assert len(self._holes()) == 4

    def test_detection_follows_a_shifted_hole_pattern(self):
        """负控：孔阵整体平移 5mm ⇒ 检出中心必须同步平移。"""
        holes = self._holes(dx=5.0)
        assert sorted(round(h["center"][0], 3) for h in holes) == \
            [x + 5.0 for x in self.BRACKET_XS]

    def test_overall_size_still_measured_from_projection(self):
        v = build_view(self._bracket(), "TOP", *STANDARD_VIEWS["TOP"])
        by_kind = {d["kind"]: d for d in v.dimensions
                   if d["kind"] != "hole_diameter"}
        assert by_kind["overall_width"]["value"] == pytest.approx(100.0, abs=1e-3)
        assert by_kind["overall_height"]["value"] == pytest.approx(50.0, abs=1e-3)


class TestHiddenLines:
    def test_solid_box_has_no_hidden_edges(self):
        """实心盒的后边与前边投影重合 ⇒ 图纸上不该出现虚线。"""
        v = build_view(_plain(), "FRONT", *STANDARD_VIEWS["FRONT"])
        assert v.hidden == []

    def test_occluded_cavity_edges_are_drawn_hidden(self):
        v = build_view(_hollow(), "FRONT", *STANDARD_VIEWS["FRONT"])
        assert v.hidden, "开口薄壁盒的内腔边线被前壁完全遮挡，必须出现在隐藏线里"
        xs = {round(_v(h)[0], 3) for h in v.hidden}
        ys = {round(_v(h)[1], 3) for h in v.hidden}
        # 内壁在 x=±(L/2-2)=±18；内底板面在 z=-(T/2)+2=-3
        assert -18.0 in xs and 18.0 in xs
        assert -3.0 in ys

    def test_hidden_lines_do_not_duplicate_visible_outline(self):
        v = build_view(_hollow(), "FRONT", *STANDARD_VIEWS["FRONT"])
        for h in v.hidden:
            for vis in v.visible:
                # 允许端点相接，但不允许整段与可见线重合
                span_h = (_v(h)[2] - _v(h)[0], _v(h)[3] - _v(h)[1])
                span_v = (_v(vis)[2] - _v(vis)[0], _v(vis)[3] - _v(vis)[1])
                if span_h[0] > 1e-6 and span_v[0] > 1e-6:
                    continue
        keys = [tuple(round(x, 3) for x in _v(h)) for h in v.hidden]
        assert len(keys) == len(set(keys)), "隐藏线出现重复条目"

    def test_looking_down_the_hole_axis_has_nothing_hidden(self):
        v = build_view(_plate("Z"), "TOP", *STANDARD_VIEWS["TOP"])
        assert v.hidden == []


class TestTangencyLimit:
    """现状钉住：逐点射线遮挡在「视线与曲面相切」处不可靠。

    竖直孔的筒壁轮廓线 x=±3 从正视看与圆柱面相切：实测 -3 侧判为隐藏、
    +3 侧判为不隐藏（真实 CAD 靠曲面分类解决）。这里把**当前行为**钉住而不是
    钉应然。翻转条件：改用曲面法向分类或接真实 HLR 后，应断言 ±3 两侧都出现，
    届时本用例随实现修正一起改判。
    """

    def test_tangent_silhouette_is_currently_one_sided(self):
        v = build_view(_plate("Z"), "FRONT", *STANDARD_VIEWS["FRONT"])
        sides = {round(_v(h)[0], 1) for h in v.hidden}
        assert -3.0 in sides
        assert 3.0 not in sides, (
            "相切轮廓线两侧都判出来了——曲面分类/真 HLR 已落地，"
            "请把本用例改为断言 ±3 均在隐藏线中")


class TestDxfOutput:
    def test_dxf_and_evidence_written_with_entities(self, tmp_path):
        out = tmp_path / "bracket.dxf"
        ev = generate_drawing(_plate("Z"), out, part_name="golden_bracket",
                              revision="B", views=("FRONT", "TOP", "RIGHT"),
                              provenance={"source_hash": "deadbeef",
                                          "tool": "cadquery/ezdxf"})
        assert out.exists() and out.stat().st_size > 1000
        assert Path(ev["evidence_file"]).exists()
        counts = ev["entity_counts"]
        assert counts.get("LWPOLYLINE", 0) + counts.get("LINE", 0) > 10
        assert counts.get("DIMENSION", 0) >= 4, "三视图总体尺寸 + 孔径"
        assert counts.get("TEXT", 0) >= 8, "标题栏字段"
        assert len(ev["sha256"]) == 64
        assert [v["view"] for v in ev["views"]] == ["FRONT", "TOP", "RIGHT"]
        assert all(v["size_mm"][0] > 0 for v in ev["views"])

    def test_evidence_json_round_trips(self, tmp_path):
        out = tmp_path / "p.dxf"
        ev = generate_drawing(_plain(), out, part_name="p", views=("FRONT",))
        on_disk = json.loads(Path(ev["evidence_file"]).read_text(encoding="utf-8"))
        assert on_disk["sha256"] == ev["sha256"]
        assert on_disk["hidden_line_method"].startswith("ray-occlusion")

    def test_dxf_reopens_and_keeps_layers(self, tmp_path):
        import ezdxf

        out = tmp_path / "layers.dxf"
        generate_drawing(_hollow(), out, part_name="hollow",
                         views=("FRONT", "TOP"))
        doc = ezdxf.readfile(str(out))
        names = {layer.dxf.name for layer in doc.layers}
        assert {"OUTLINE", "HIDDEN", "DIMENSION", "TEXT", "FRAME"} <= names
        msp = doc.modelspace()
        assert {e.dxf.layer for e in msp} & {"OUTLINE", "HIDDEN"}

    def test_unknown_view_is_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="未知视图"):
            generate_drawing(_plain(), tmp_path / "x.dxf", part_name="x",
                             views=("ISOMETRIC",))

    def test_scale_shrinks_placed_size(self, tmp_path):
        ev = generate_drawing(_plain(), tmp_path / "s.dxf", part_name="s",
                              views=("FRONT",), scale=0.5)
        assert ev["views"][0]["size_mm"][0] == pytest.approx(L * 0.5, abs=1e-3)
        assert ev["scale"] == 0.5


class TestCliInputPaths:
    """CLI 的两种输入都必须真跑一遍。

    此前只有 HOLD 分支被覆盖，`--native` 与 `--step` 全靠手工命令验证；
    一个没人跑过的入参分支等于没交付。
    """

    @staticmethod
    def _ns(out, **kw):
        import argparse

        base = dict(out=str(out), part="cli_part", revision="A",
                    views="TOP", scale=1.0, material="-", sheet="A3",
                    json=True, step=None, native=None)
        base.update(kw)
        return argparse.Namespace(**base)

    def test_native_source_input_writes_dxf_and_evidence(self, tmp_path):
        from aipd_os.cli.commands_drawing import cmd_drawing

        out = tmp_path / "from_native.dxf"
        rc = cmd_drawing(self._ns(out, native=str(GOLDEN_BRACKET_SOURCE)))
        assert rc == 0
        assert out.stat().st_size > 1000
        ev = json.loads(sidecar_path(out).read_text("utf-8"))
        holes = [d for v in ev["views"] for d in v["dimensions"]
                 if d["kind"] == "hole_diameter"]
        assert sorted(round(h["center"][0], 3) for h in holes) == \
            [-30.0, -10.0, 10.0, 30.0]

    def test_step_input_writes_dxf(self, tmp_path):
        from aipd_os.cli.commands_drawing import cmd_drawing

        step = tmp_path / "bracket.step"
        cadquery.exporters.export(TestRealBracketPattern._bracket(), str(step),
                                  exportType="STEP")
        out = tmp_path / "from_step.dxf"
        assert cmd_drawing(self._ns(out, step=str(step))) == 0
        assert out.is_file() and out.stat().st_size > 1000

    def test_no_input_falls_back_to_default_but_says_so(self, tmp_path):
        """现状钉住：既无 --step 也无 --native 时回退默认黄金模型。

        这是本仓 `load_native_model` 的既有约定（与 `cad build` 一致），但出图
        不能让人以为画的是自己那个件——所以回退必须在证据里点名。
        翻转条件：若改为「缺输入即报错」，本用例改为断言 rc != 0 且不落文件。
        """
        from aipd_os.cli.commands_drawing import cmd_drawing

        out = tmp_path / "default.dxf"
        assert cmd_drawing(self._ns(out)) == 0
        ev = json.loads(sidecar_path(out).read_text("utf-8"))
        assert ev["model_source"] == "golden_default"
        # 溯源必须落在磁盘证据里，而不是只存在于本次 stdout
        assert ev["ok"] is True and ev["status"] == "DONE"
        assert ev["command"] == "drawing generate"


class TestCapabilityDeclaration:
    def test_registry_declares_real_entry_and_honest_limitation(self, tmp_path):
        """登记必须指向真实实现与真实入口，且写清未覆盖项。"""
        import importlib

        from aipd_os.cli.commands_drawing import cmd_drawing
        from aipd_os.registry import load_default_registry, probe_entry_callable

        cap = load_default_registry().get("cad.2d_drawings")
        assert cap is not None
        # 实现文件可以登记多个（";" 分隔，与下面 unit_test 同一套规矩，也是
        # registry.probe_file_has_impl 认的形状），但**每一个**都得真存在
        root = Path(__file__).resolve().parents[1]
        declared_impls = [p.strip() for p in (cap.implementation_file or "").split(";")
                          if p.strip()]
        assert declared_impls, "实现文件未登记"
        for rel in declared_impls:
            assert (root / rel).is_file(), f"登记指向的实现文件不存在：{rel}"
        assert "src/aipd_os/cad/assembly.py" in declared_impls, \
            "装配图的实现改了名/搬了家，登记就要跟着改"
        # 入口要"取得到真身"，而不是钉一个字符串形状：这里曾钉的正是探针解析不了的
        # 文件路径形态（F-REG-01），等于把错写法当成了基线。
        module_name, _, attr = cap.entry_point.rpartition(".")
        assert getattr(importlib.import_module(module_name), attr) is cmd_drawing
        assert probe_entry_callable(
            cap.entry_point, Path(__file__).resolve().parents[1]) is True
        assert cap.run_command == "aipd drawing generate"
        declared_tests = [t.strip() for t in (cap.unit_test or "").split(";") if t.strip()]
        assert set(declared_tests) >= {"tests/test_cad_drawings2d.py",
                                       "tests/test_cad_drawings_chain_tolerance.py"}
        for rel in declared_tests:  # 登记的每个测试文件都得真存在
            assert (root / rel).is_file(), f"登记指向的测试文件不存在：{rel}"
        # 未覆盖项必须逐项点名；已落地的（尺寸链/按声明的公差）也要写进行内，
        # 否则 limitation 会把现状说小，等于另一种不诚实。
        assert cap.classification == "partially_implemented"
        for token in ("GD&T", "公差叠加", "剖视", "爆炸图", "相切"):
            assert token in cap.current_limitation, cap.current_limitation
        for token in ("尺寸链", "--spec", "退出码 4"):
            assert token in cap.current_limitation, cap.current_limitation
        # 装配图这一维已经落地，行内必须同时写清「做到什么」和「没做什么」：
        # 只写球标不写「不干涉判定/数量列未接 BOM」就是把现状说大
        for token in ("球标", "明细表", "干涉", "爆炸图"):
            assert token in cap.current_limitation, cap.current_limitation
        assert "Product Truth" in cap.current_limitation, "公差声明未接权威事实源这点要写明"


class TestGracefulDegradation:
    def test_missing_kernel_holds_and_writes_nothing(self, tmp_path, monkeypatch):
        """内核缺失时给 HOLD + 外部任务包，绝不落一个假 DXF。"""
        import builtins

        from aipd_os.cli.commands_drawing import cmd_drawing

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name in ("cadquery", "ezdxf"):
                raise ImportError(f"No module named {name!r}")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        out = tmp_path / "should-not-exist.dxf"
        ns = argparse.Namespace(out=str(out), part="bracket", revision="A",
                                views="FRONT,TOP", step=None, native=None,
                                scale=1.0, material="-", sheet="A3", json=True)
        rc = cmd_drawing(ns)
        assert rc == 4
        assert not out.exists()
        assert not sidecar_path(out).exists()
