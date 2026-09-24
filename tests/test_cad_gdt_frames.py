"""GD&T 特征控制框（FCF）：只画声明过的框，框挂在**实测**特征位置上（F-DRAW-01 第 3 片）。

选型说明（都做过实测/检索）：ezdxf 有 DXF ``TOLERANCE`` 实体（``AcDbFcf``，
``content``/``insert``/``x_axis_vector``，实测存盘读回 1 个实体、audit 0 错），
但 ``Layout`` **没有** ``add_tolerance`` 工厂，而且 AutoCAD 那一套 ``content`` 转义码
（分隔符、直径码、几何特征符号）本轮**没找到权威来源**去核实（检索命中的是厂商博客与
培训文，不足以作为编码依据）。所以这一片不宣称「FCF 在 AutoCAD 里渲染成什么样」，
只做**可回读核验**的那一半：把框画成实体现（分隔框线 + 文字 + 引线），
并在证据里留下**结构化**的框内容，让下游 CAD 能据此重建语义实体。

这一片钉住的口径：

1. **框只来自声明**：没有 ``gdt`` 声明就一个框都不画（绝不"顺手加个位置度"）；
2. **框必须挂在实测位置**：``feature`` 指的是尺寸证据里的特征名（``TOP.hole_2``），
   框的引线终点取该特征**投影测量出来**的圆心，不是 spec 里写的坐标；
3. **基准必须可解析**：``datums: ["A"]`` 要在 ``spec.datums`` 里找得到且指向一个
   真实存在的特征，否则点名 ``datum_unresolved`` 并判未收口——不猜基准；
4. **声明了但图上没有的特征**同样点名（``gdt_unmatched_features``）。
"""
from __future__ import annotations

from pathlib import Path

import pytest

cadquery = pytest.importorskip("cadquery", reason="cad 为可选 extra")
pytest.importorskip("ezdxf", reason="DXF 写出依赖 ezdxf")

import ezdxf  # noqa: E402

from aipd_os.cad.drawings2d import generate_drawing  # noqa: E402

L, W, T, HD = 100.0, 20.0, 10.0, 6.0
HOLE_X = [-30.0, -10.0, 10.0, 30.0]
VIEW = "TOP"


def _plate():
    return (cadquery.Workplane("XY").box(L, W, T).faces(">Z").workplane()
            .pushPoints([(x, 0.0) for x in HOLE_X]).hole(HD).solids().vals()[0])


def _spec(gdt=None, datums="default", feature=f"{VIEW}.hole_2"):
    feats = []
    if gdt is not None:
        feats.append({"feature": feature, "gdt": gdt})
    spec = {"features": feats}
    if datums == "default":
        spec["datums"] = [{"id": "A", "feature": f"{VIEW}.hole_1"},
                          {"id": "B", "feature": f"{VIEW}.hole_4"}]
    elif datums is not None:
        spec["datums"] = datums
    return spec


POSITION = [{"characteristic": "position", "zone": 0.05, "diametral": True,
             "datums": ["A", "B"]}]


def _gen(tmp_path, spec=None, name="gdt"):
    out = Path(tmp_path) / f"{name}.dxf"
    ev = generate_drawing(_plate(), out, part_name="plate", revision="A",
                          views=(VIEW,), spec=spec)
    return ev, out


def _frames(ev, view=VIEW):
    return [f for f in ev["gdt_frames"] if f["view"] == view]


def _texts(path):
    doc = ezdxf.readfile(str(path))
    msp = doc.modelspace()
    return ([e.dxf.text for e in msp if e.dxftype() == "TEXT"],
            [e for e in msp if e.dxftype() == "LWPOLYLINE"],
            [e for e in msp if e.dxftype() == "LINE"])


class TestFramesComeFromDeclarations:
    def test_no_declaration_means_no_frames_anywhere(self, tmp_path):
        ev, out = _gen(tmp_path, name="nofcf")
        assert ev["gdt_frames"] == [] and ev["gdt_issue_kinds"] == []
        doc = ezdxf.readfile(str(out))
        assert not [e for e in doc.modelspace() if e.dxf.layer == "GDT"], \
            "没有声明就不该出现任何 FCF 实体（框线/文字/引线都算）"

    def test_a_declared_frame_lands_on_the_measured_feature(self, tmp_path):
        ev, out = _gen(tmp_path, _spec(POSITION), name="one")
        frames = _frames(ev)
        assert len(frames) == 1
        f = frames[0]
        assert f["characteristic"] == "position"
        assert f["zone"] == 0.05 and f["diametral"] is True
        assert f["datum_refs"] == ["A", "B"]
        # 引线终点 = TOP.hole_2 的实测圆心（-10.0, 0.0），不是 spec 里写的任何坐标
        assert f["attach"] == [-10.0, 0.0]
        assert f["text"] == "⌖|⌀0.05|A|B"

    def test_frame_geometry_is_readable_back_from_the_dxf(self, tmp_path):
        """每格一条 TEXT、每格一个闭合矩形、一条引线——都从存盘文件里读回来。"""
        _, out = _gen(tmp_path, _spec(POSITION), name="geom")
        texts, polys, lines = _texts(out)
        for compartment in ("⌖", "⌀0.05", "A", "B"):
            assert compartment in texts, texts
        assert "⌖|⌀0.05|A|B" not in texts, "整串是证据字段，不是画在图上的单条文字"
        gdt_polys = [pl for pl in polys if pl.dxf.layer == "GDT"]
        assert len(gdt_polys) == 4, "四格四个闭合矩形"
        assert any(pl.dxf.layer == "GDT" for pl in lines), "FCF 需要引线连到被测特征"


class TestDatumsMustResolve:
    def test_unknown_datum_letter_is_named_and_holds(self, tmp_path):
        gdt = [{"characteristic": "perpendicularity", "zone": 0.1,
                "diametral": False, "datums": ["Z"]}]
        ev, _ = _gen(tmp_path, _spec(gdt), name="baddatum")
        kinds = ev["gdt_issue_kinds"]
        assert "datum_unresolved" in kinds
        assert [i["datum"] for i in ev["gdt_issues"] if i["kind"] == "datum_unresolved"] == ["Z"]
        assert ev["gdt_frames"] == [], "基准解析不了就不画半截框"

    def test_datum_pointing_at_a_missing_feature_is_named(self, tmp_path):
        spec = _spec(POSITION, datums=[{"id": "A", "feature": "TOP.hole_99"},
                                       {"id": "B", "feature": f"{VIEW}.hole_4"}])
        ev, _ = _gen(tmp_path, spec, name="badfeature")
        assert "datum_feature_missing" in ev["gdt_issue_kinds"]
        assert ev["gdt_frames"] == []

    def test_declared_frame_on_an_absent_feature_is_reported(self, tmp_path):
        ev, _ = _gen(tmp_path, _spec(POSITION, feature=f"{VIEW}.hole_9"), name="ghost")
        assert ev["gdt_unmatched_features"] == [f"{VIEW}.hole_9"]
        assert ev["gdt_frames"] == []


class TestNoInvention:
    def test_unsupported_characteristic_is_rejected_not_silently_drawn(self, tmp_path):
        gdt = [{"characteristic": "concentricity", "zone": 0.05,
                "diametral": True, "datums": ["A"]}]
        ev, _ = _gen(tmp_path, _spec(gdt), name="unsupported")
        assert "characteristic_unsupported" in ev["gdt_issue_kinds"]
        assert ev["gdt_frames"] == []

    def test_zone_must_be_declared_positive(self, tmp_path):
        gdt = [{"characteristic": "position", "zone": 0.0, "diametral": True,
                "datums": ["A"]}]
        ev, _ = _gen(tmp_path, _spec(gdt), name="zerozone")
        assert "zone_not_positive" in ev["gdt_issue_kinds"]
        assert ev["gdt_frames"] == []

    def test_position_without_datums_is_incomplete_not_silently_accepted(self, tmp_path):
        gdt = [{"characteristic": "position", "zone": 0.05, "diametral": True,
                "datums": []}]
        ev, _ = _gen(tmp_path, _spec(gdt), name="nodatum")
        assert "datum_required" in ev["gdt_issue_kinds"]
        assert ev["gdt_frames"] == []

    def test_form_tolerance_needs_no_datum_and_still_draws(self, tmp_path):
        gdt = [{"characteristic": "flatness", "zone": 0.02, "diametral": False,
                "datums": []}]
        ev, _ = _gen(tmp_path, _spec(gdt), name="form")
        frames = _frames(ev)
        assert len(frames) == 1
        assert frames[0]["text"] == "⏥|0.02"
        assert ev["gdt_issue_kinds"] == []


class TestCliHolds:
    def test_gdt_issue_holds_the_command(self, tmp_path, capsys):
        import argparse
        import json

        from aipd_os.cli.commands_drawing import cmd_drawing

        spec_file = tmp_path / "fcf.json"
        spec_file.write_text(json.dumps(_spec([
            {"characteristic": "position", "zone": 0.05, "diametral": True,
             "datums": ["Q"]}]), ensure_ascii=False), encoding="utf-8")
        out = tmp_path / "cli.dxf"
        rc = cmd_drawing(argparse.Namespace(
            out=str(out), part="plate", revision="A", views=VIEW, scale=1.0,
            material="-", sheet="A3", json=False, step=None, native=None,
            spec=str(spec_file)))
        assert rc == 4
        printed = capsys.readouterr().out
        assert "GD&T" in printed and "基准 Q" in printed
