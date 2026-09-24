"""装配图 + 序号球标 + 明细表（F-DRAW-01 第 12 片）。

单件图纸侧已经很厚（六视图 / 尺寸链 / 公差声明生产者 / 叠加 / GD&T / 剖视与剖切符号 /
局部放大）。缺的不是「再多一种画法」，而是**多零件**这一维：C6 生产图纸包要的是
一张能把装配讲清楚的图，而球标编号正是图纸与 BOM 之间唯一可能的共同语言。

本轮的三条硬规矩，都是可机器核的：

1. **零件逐个投影，不合成一次投影再猜归属。** 本机实测两个 20×20×8 盒子：单盒 24 条
   raw edge、合成 compound 48 条（``TopExp_Explorer(EDGE)``），``classify_view`` 投出
   8 条 vs 16 条折线 ⇒ 几何上能一次投完、条数也正好翻倍，但孔会被全局重编号、
   ``_bbox`` 会成包络、``_coincident`` 会把「A 遮住 B 的边」判成
   不存在。逐个投影让「这条线属于哪个零件」成为**已知**而不是推断结果。
2. **球标编号是作者声明的，不是从几何推出来的。** FreeCAD TechDraw 的
   ``DrawViewBalloon`` 同理：气泡内容是可写的 ``Text`` 属性、箭头落点是作者指的
   ``OriginX/OriginY``（``src/Mod/TechDraw/App/DrawViewBalloon.cpp:51-54,67``），
   上游没有按遍历顺序发号的机制。``balloon`` 必须在 manifest 里写、
   必须正整数且不重复，缺号/重号/写 0 直接判声明错误（rc=2），不做「按遍历顺序发号」。
3. **挂点必须量出来。** 球标引线终点取该零件在该视图里**已投影几何**的质心，
   断言它落在该零件的包络内、且不在别的零件包络内 —— 这就是「不是猜」的证明。

明细表用 ``ezdxf.addons.tablepainter.TablePainter``（本机实测：nrows/ncols +
``text_cell`` + ``render(msp)`` 产出 TEXT+LINE，层 TABLECONTENT/TABLEGRID）；
不用 DXF 原生 TABLE 实体，因为 **ezdxf 1.4.2 没有表实体的写作 API**
（``Modelspace.add_table`` 不存在、``ezdxf.entities`` 无 ``Table`` 类）。

明确**不在本轮**：球标 ↔ BOM 行交叉核对（``BomLine`` 今天没有件号/序号字段，只有自由
文本 ``item``；要核就得复用 ``supply_chain/impact`` 的 item 归一化全等规则并给明细表加
数量列 —— 数量权威在 BOM，不在 manifest），以及干涉/碰撞检查与爆炸图。
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pytest

cadquery = pytest.importorskip("cadquery", reason="cad 为可选 extra")
pytest.importorskip("ezdxf", reason="DXF 输出依赖 ezdxf")

import ezdxf  # noqa: E402

from aipd_os.cad.assembly import (  # noqa: E402
    build_assembly_view,
    load_assembly_parts,
    parse_assembly_manifest,
    render_assembly,
)
from aipd_os.cad.drawings2d import STANDARD_VIEWS, generate_drawing  # noqa: E402

BALLOON_RADIUS = 4.0        # 球标圆半径（图纸 mm，随视图比例缩放前）
BALLOON_COLUMN_GAP = 15.0   # 球标列相对包络右沿的外移


def _write_step(tmp_path: Path, name: str, shape) -> Path:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    cadquery.exporters.export(shape, str(path), exportType="STEP")
    return path


def _part_a(tmp_path) -> Path:
    """40×20×10 板，中心一个 Ø6 通孔 ⇒ 质心在原点。"""
    box = cadquery.Workplane("XY").box(40.0, 20.0, 10.0)
    shape = box.faces(">Z").workplane().hole(6.0).solids().vals()[0]
    return _write_step(tmp_path, "part_a.step", shape)


def _part_b(tmp_path) -> Path:
    """20×20×8 块，几何中心在 (0, 0, 4)。"""
    shape = cadquery.Workplane("XY").box(20.0, 20.0, 8.0).solids().vals()[0]
    return _write_step(tmp_path, "part_b.step", shape)


def _manifest(tmp_path, *, balloons=(1, 2), offsets=((0.0, 0.0, 0.0), (0.0, 45.0, 0.0)),
              names=("支架", "压板"), steps=None):
    a, b = _part_a(tmp_path), _part_b(tmp_path)
    files = list(steps or (a, b))
    parts = [{"name": n, "step": str(f), "balloon": bl, "offset": list(off)}
             for n, f, bl, off in zip(names, files, balloons, offsets)]
    path = tmp_path / "assembly.json"
    path.write_text(json.dumps({"parts": parts}, ensure_ascii=False), encoding="utf-8")
    return path, parts


def _gen(tmp_path, manifest=None, views=("TOP", "FRONT"), name="assy", **kw):
    out = tmp_path / f"{name}.dxf"
    if manifest is None:
        manifest, _ = _manifest(tmp_path)
    ev = generate_drawing(None, out, part_name="ASSY-1", revision="A",
                          views=tuple(views), assembly=str(manifest), **kw)
    return ev, out


def _view(ev, name):
    return next(v for v in ev["views"] if v["view"] == name)


def _ents(path, types, layer=None):
    doc = ezdxf.readfile(str(path))
    return [e for e in doc.modelspace()
            if e.dxftype() in types and (layer is None or e.dxf.layer == layer)]


def _texts(path, layer=None):
    doc = ezdxf.readfile(str(path))
    return [e.dxf.text.strip() for e in doc.modelspace()
            if e.dxftype() == "TEXT" and (layer is None or e.dxf.layer == layer)]


class TestProjectionIsPerPartAtUnitLevel:
    def test_unit_level_projection_keeps_two_envelopes_apart(self, tmp_path):
        """不经图纸直接验投影层：逐件投影后两件各有一套折线，且包络不重叠。"""
        specs = parse_assembly_manifest(_manifest(tmp_path)[0])
        parts = load_assembly_parts(specs)
        direction, up = STANDARD_VIEWS["TOP"]
        view = build_assembly_view(parts, "ASSY_TOP", direction, up)
        boxes = {p["part"]: p["bbox"] for p in view.assembly["parts"]}
        assert set(boxes) == {"支架", "压板"}
        assert boxes["支架"] == [pytest.approx(-20.0, abs=1e-6),
                                 pytest.approx(-10.0, abs=1e-6),
                                 pytest.approx(20.0, abs=1e-6),
                                 pytest.approx(10.0, abs=1e-6)]
        assert boxes["压板"][1] == pytest.approx(35.0, abs=1e-6)
        assert view.assembly["overlap_area_mm2"] == 0.0
        assert len(view.visible) == sum(p["visible_polylines"] + p["hidden_polylines"]
                                        for p in view.assembly["parts"])

    def test_render_assembly_is_the_only_balloon_producer(self, tmp_path):
        """球标层只可能由 render_assembly 画出来（前提：不画就没有任何东西）。"""
        import ezdxf as _ezdxf

        specs = parse_assembly_manifest(_manifest(tmp_path)[0])
        parts = load_assembly_parts(specs)
        direction, up = STANDARD_VIEWS["TOP"]
        view = build_assembly_view(parts, "ASSY_TOP", direction, up)
        doc = _ezdxf.new("R2010", setup=True)
        msp = doc.modelspace()
        assert [e for e in msp if e.dxf.layer == "BALLOON"] == []
        render_assembly(msp, view, 1.0)
        drawn = [e for e in msp if e.dxf.layer == "BALLOON"]
        assert len(drawn) == 3 * len(view.assembly["balloons"]), \
            "每个球标三样：引线 + 圆 + 编号"
        assert {e.dxftype() for e in drawn} == {"LINE", "CIRCLE", "TEXT"}


class TestManifestParsesAndRejects:
    def test_a_valid_manifest_parses(self, tmp_path):
        path, parts = _manifest(tmp_path)
        parsed = parse_assembly_manifest(path)
        assert [p["name"] for p in parsed] == ["支架", "压板"]
        assert [p["balloon"] for p in parsed] == [1, 2]
        assert parsed[0]["offset"] == [0.0, 0.0, 0.0]
        assert parsed[1]["offset"] == [0.0, 45.0, 0.0]
        # step 路径由 manifest 目录解析，绝对/相对都指向同一个文件
        assert Path(parsed[0]["step"]).is_file()

    def test_declaration_errors_raise_rather_than_being_guessed(self, tmp_path):
        bad = {
            "重号": {"parts": [{"name": "a", "step": "x.step", "balloon": 1},
                              {"name": "b", "step": "y.step", "balloon": 1}]},
            "零号球标": {"parts": [{"name": "a", "step": "x.step", "balloon": 0}]},
            "负号球标": {"parts": [{"name": "a", "step": "x.step", "balloon": -3}]},
            "球标缺失": {"parts": [{"name": "a", "step": "x.step"}]},
            "无名零件": {"parts": [{"name": "  ", "step": "x.step", "balloon": 1}]},
            "零件重名": {"parts": [{"name": "a", "step": "x.step", "balloon": 1},
                                 {"name": "a", "step": "y.step", "balloon": 2}]},
            "空清单": {"parts": []},
            "没有 parts 键": {},
            "偏移不是三个数": {"parts": [{"name": "a", "step": "x.step", "balloon": 1,
                                    "offset": [1.0, 2.0]}]},
        }
        for label, payload in bad.items():
            path = tmp_path / f"bad_{abs(hash(label))}.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            with pytest.raises(ValueError) as exc:
                parse_assembly_manifest(path)
            assert str(exc.value), label

    def test_missing_step_file_is_named_not_skipped(self, tmp_path):
        path = tmp_path / "missing.json"
        path.write_text(json.dumps({"parts": [{"name": "a", "step": "nope.step",
                                               "balloon": 1}]}, ensure_ascii=False),
                        encoding="utf-8")
        with pytest.raises(ValueError) as exc:
            parse_assembly_manifest(path)
        assert "nope.step" in str(exc.value)


class TestPartsAreProjectedIndividually:
    def test_each_part_contributes_geometry_and_keeps_its_own_identity(self, tmp_path):
        manifest, parts = _manifest(tmp_path)
        ev, _ = _gen(tmp_path, manifest)
        top = _view(ev, "ASSY_TOP")
        per_part = {p["part"]: p for p in top["assembly_parts"]}
        assert set(per_part) == {"支架", "压板"}
        assert all(per_part[n]["visible_polylines"] > 0 for n in per_part)
        # 合并后既不少于各自之和，也保留了归属标签（不是重新聚类猜出来的）
        owners = {seg["part"] for seg in top["segments"]}
        assert owners == {"支架", "压板"}

    def test_the_two_parts_do_not_share_envelopes_after_placement(self, tmp_path):
        manifest, _ = _manifest(tmp_path)     # 偏了 45mm 在 y 方向 ⇒ 投影后必然分开
        ev, _ = _gen(tmp_path, manifest)
        top = _view(ev, "ASSY_TOP")
        a, b = top["assembly_parts"]
        assert a["bbox"][3] < b["bbox"][1], (a["bbox"], b["bbox"])
        assert top["overlap_area_mm2"] == pytest.approx(0.0, abs=1e-9)

    def test_overlapping_parts_are_reported_as_a_warning_not_a_silent_zero(
            self, tmp_path):
        manifest, _ = _manifest(tmp_path, offsets=((0.0, 0.0, 0.0), (0.0, 5.0, 0.0)))
        ev, _ = _gen(tmp_path, manifest, name="overlap")
        top = _view(ev, "ASSY_TOP")
        assert top["overlap_area_mm2"] > 0.0
        assert any("重叠" in m for m in ev["assembly_warnings"]), ev["assembly_warnings"]
        assert ev["assembly_issues"] == [], "重叠是告警不是未收口：干涉判定本轮不做"


class TestBalloonsAnchorOnMeasuredGeometry:
    def test_anchor_is_the_parts_measured_centroid_and_lies_in_its_own_envelope(
            self, tmp_path):
        manifest, _ = _manifest(tmp_path)
        ev, _ = _gen(tmp_path, manifest)
        top = _view(ev, "ASSY_TOP")
        balloons = {b["part"]: b for b in top["balloons"]}
        for name, one in balloons.items():
            env = next(p for p in top["assembly_parts"] if p["part"] == name)["bbox"]
            ax, ay = one["anchor"]
            assert env[0] <= ax <= env[2] and env[1] <= ay <= env[3], (name, env, one)
            others = [p for p in top["assembly_parts"] if p["part"] != name]
            assert all(not (e["bbox"][0] <= ax <= e["bbox"][2]
                            and e["bbox"][1] <= ay <= e["bbox"][3])
                       for e in others), "挂点跑到别的零件包络里 = 归属是猜的"

    def test_balloon_numbers_come_from_the_manifest_and_the_column_is_ordered(
            self, tmp_path):
        manifest, _ = _manifest(tmp_path, balloons=(5, 9))
        ev, out = _gen(tmp_path, manifest, name="nums")
        top = _view(ev, "ASSY_TOP")
        assert [b["number"] for b in top["balloons"]] == [5, 9]
        right = max(p["bbox"][2] for p in top["assembly_parts"])
        assert all(b["x"] == pytest.approx(top["envelope"][2] + BALLOON_COLUMN_GAP,
                                           abs=1e-6) for b in top["balloons"])
        assert right <= top["envelope"][2] + 1e-9
        assert len({round(b["y"], 6) for b in top["balloons"]}) == 2, "两个球标不能重叠"
        circles = _ents(out, ("CIRCLE",), "BALLOON")
        assert len(circles) == 2
        assert [round(c.dxf.radius, 6) for c in circles] == [BALLOON_RADIUS, BALLOON_RADIUS]
        assert sorted(_texts(out, "BALLOON")) == ["5", "9"]

    def test_two_parts_collapsing_to_one_anchor_are_reported_as_ambiguity(
            self, tmp_path):
        """沿投影方向叠放的零件：正视图上两个球标会指向同一个点。

        这条不是设想出来的，是真跑 ``aipd drawing assembly --views FRONT,TOP`` 量到的——
        零件沿 Y 偏移，而 FRONT 的投影方向就是 Y，两件的投影质心都落在 (0, 0)。
        图能交付、几何也没错，但读图的人分不出哪个圈指哪件，所以必须**说话**：
        不改作者的视图顺序、不升格成未收口，只给告警。
        """
        manifest, _ = _manifest(tmp_path)
        ev, _ = _gen(tmp_path, manifest, views=("FRONT", "TOP"), name="collide")
        front = _view(ev, "ASSY_FRONT")
        anchors = [tuple(b["anchor"]) for b in front["balloons"]]
        assert len(set(anchors)) == 1, f"前提不成立，这一轮没造出撞点：{anchors}"
        assert any("同一个位置" in m for m in ev["assembly_warnings"]), \
            ev["assembly_warnings"]
        assert ev["assembly_issues"] == [], "标注歧义是告警，不是未收口"

    def test_leader_line_connects_the_balloon_to_its_measured_anchor(self, tmp_path):
        """引线位移必须等于「挂点 − 球标边缘」，且起点正落在某个球标圆上。

        判位移而不是判绝对坐标：图纸上视图摆在第几毫米是排版的事，这里要验的是
        「这条线确实从这个球标连到那个实测挂点」。绝对坐标由
        ``test_render_assembly_is_the_only_balloon_producer`` 在局部坐标下逐位钉住。
        """
        manifest, _ = _manifest(tmp_path)
        ev, out = _gen(tmp_path, manifest, name="leader")
        top = _view(ev, "ASSY_TOP")
        lines = _ents(out, ("LINE",), "BALLOON")
        circles = _ents(out, ("CIRCLE",), "BALLOON")
        assert len(lines) == 2 and len(circles) == 2
        for one in top["balloons"]:
            want = (one["anchor"][0] - one["leader_start"][0],
                    one["anchor"][1] - one["leader_start"][1])
            hit = [ln for ln in lines
                   if abs((ln.dxf.end.x - ln.dxf.start.x) - want[0]) < 1e-6
                   and abs((ln.dxf.end.y - ln.dxf.start.y) - want[1]) < 1e-6]
            assert hit, f"没有位移等于「{one['part']} 挂点 − 球标边缘」的引线"
            ln = hit[0]
            on_rim = [c for c in circles if abs(
                math.hypot(ln.dxf.start.x - c.dxf.center.x,
                           ln.dxf.start.y - c.dxf.center.y) - BALLOON_RADIUS) < 1e-6]
            assert len(on_rim) == 1, "引线起点必须正好落在某个球标圆周上"


class TestPartsList:
    def test_balloons_travel_with_their_view_instead_of_the_sheet_origin(self, tmp_path):
        """球标必须跟着视图的放置走——这条盯的是本轮真踩过的坑：

        ``render_assembly`` 自己再算一遍偏移（漏了视图中心 cx/cy）时，图线在视图里、
        球标却飞到图纸原点附近。位移类断言看不见这种错（两者一起偏），只有绝对坐标抓得到。
        """
        manifest, _ = _manifest(tmp_path)
        ev, out = _gen(tmp_path, manifest, name="place")
        top = _view(ev, "ASSY_TOP")
        cx, cy = top["origin"]
        env = top["envelope"]
        off = (cx - (env[2] - env[0]) / 2.0 - env[0],
               cy - (env[3] - env[1]) / 2.0 - env[1])
        circles = _ents(out, ("CIRCLE",), "BALLOON")
        for one in top["balloons"]:
            want = (one["x"] + off[0], one["y"] + off[1])
            # 证据里的 origin 只留 2 位小数，所以比到 0.011 而不是 1e-6
            assert any(abs(c.dxf.center.x - want[0]) < 0.011
                       and abs(c.dxf.center.y - want[1]) < 0.011 for c in circles), \
                f"球标 {one['number']} 没跟着 ASSY_TOP 放置：期望 {want}"

    def test_parts_list_lists_every_part_with_its_declared_number(self, tmp_path):
        manifest, parts = _manifest(tmp_path)
        ev, out = _gen(tmp_path, manifest, name="list")
        listed = ev["parts_list"]
        assert listed["columns"] == ["ITEM", "PART"]
        assert [[c["item"], c["part"]] for c in listed["rows"]] == \
               [[p["balloon"], p["name"]] for p in parts]
        assert listed["rendered_by"] == "ezdxf.addons.tablepainter"
        texts = _texts(out)
        assert "ITEM" in texts and "PART" in texts
        assert "支架" in texts and "压板" in texts
        # 明细表不许压到视图或标题栏：整块都在图框内
        box = listed["bbox"]
        assert box[0] >= 10.0 and box[2] <= 420.0 - 10.0
        assert box[1] >= 10.0 and box[3] <= 297.0 - 10.0

    def test_no_bom_given_means_no_quantity_claimed(self, tmp_path):
        manifest, _ = _manifest(tmp_path)
        ev, _ = _gen(tmp_path, manifest, name="noqty")
        assert ev["bom"] is None
        assert "QTY" not in ev["parts_list"]["columns"], "数量权威在 BOM，没有就别印一列空数"


class TestEnvelopeDimensionsAndFile:
    def test_assembly_envelope_comes_from_the_placed_geometry(self, tmp_path):
        # part A 占 x∈[-20,20] y∈[-10,10]；part B 占 x∈[-10,10] y∈[-10,10] 再偏 y+45
        manifest, _ = _manifest(tmp_path)
        ev, _ = _gen(tmp_path, manifest, name="env")
        top = _view(ev, "ASSY_TOP")
        assert top["envelope"] == [pytest.approx(-20.0, abs=1e-6),
                                   pytest.approx(-10.0, abs=1e-6),
                                   pytest.approx(20.0, abs=1e-6),
                                   pytest.approx(55.0, abs=1e-6)]
        dims = {d["feature"]: d for d in top["dimensions"]}
        assert dims["ASSY_TOP.envelope_width"]["value"] == pytest.approx(40.0, abs=1e-6)
        assert dims["ASSY_TOP.envelope_height"]["value"] == pytest.approx(65.0, abs=1e-6)
        assert dims["ASSY_TOP.envelope_width"]["kind"] == "envelope"

    def test_part_files_are_hashed_so_the_claim_binds_to_bytes(self, tmp_path):
        manifest, parts = _manifest(tmp_path)
        ev, _ = _gen(tmp_path, manifest, name="hash")
        for one, spec in zip(ev["assembly"]["parts"], parts):
            expect = hashlib.sha256(Path(spec["step"]).read_bytes()).hexdigest()
            assert one["step_sha256"] == expect

    def test_the_assembly_drawing_reopens_clean(self, tmp_path):
        from ezdxf import recover

        manifest, _ = _manifest(tmp_path)
        _, out = _gen(tmp_path, manifest, name="audit")
        doc, auditor = recover.readfile(str(out))
        assert auditor.errors == [], [str(e) for e in auditor.errors]
        assert auditor.fixes == [], [str(f) for f in auditor.fixes]
        for layer in ("BALLOON", "TABLECONTENT", "TABLEGRID", "OUTLINE"):
            assert doc.layers.get(layer) is not None, layer

    def test_a_part_with_no_solids_is_a_hold_not_an_empty_drawing(self, tmp_path):
        empty = tmp_path / "empty.step"
        cadquery.exporters.export(cadquery.Workplane("XY").rect(10, 10),
                                  str(empty), exportType="STEP")
        path = tmp_path / "empties.json"
        path.write_text(json.dumps({"parts": [{"name": "空", "step": str(empty),
                                               "balloon": 1}]}, ensure_ascii=False),
                        encoding="utf-8")
        ev, _ = _gen(tmp_path, path, name="empties")
        assert ev["assembly_issues"], "什么都没投出来必须点名"
        assert any("没有任何实体" in m for m in ev["assembly_issues"]), ev["assembly_issues"]
        # 明细表照列这个零件：没有几何不等于零件不存在（球标无处挂，但件号是作者给的）
        assert [r["part"] for r in ev["parts_list"]["rows"]] == ["空"]


class TestSinglePartAssemblyIsAllowed:
    def test_one_part_is_legal_and_gets_one_balloon(self, tmp_path):
        a = _part_a(tmp_path)
        path = tmp_path / "one.json"
        path.write_text(json.dumps({"parts": [{"name": "单件", "step": str(a),
                                               "balloon": 7}]}, ensure_ascii=False),
                        encoding="utf-8")
        ev, _ = _gen(tmp_path, path, name="one")
        top = _view(ev, "ASSY_TOP")
        assert [b["number"] for b in top["balloons"]] == [7]
        assert ev["assembly_issues"] == []


def test_generate_drawing_still_rejects_unknown_single_part_views(tmp_path):
    """装配分支不能顺手放宽既有判据：单件路径的未知视图仍然报错。"""
    manifest, _ = _manifest(tmp_path)
    with pytest.raises(ValueError):
        generate_drawing(None, tmp_path / "bad.dxf", part_name="ASSY",
                         views=("NOPE",), assembly=str(manifest))
    assert set(STANDARD_VIEWS) >= {"TOP", "FRONT", "RIGHT"}


def test_render_assembly_is_the_only_producer_of_the_balloon_layer(tmp_path):
    """前提断言：BALLOON 层上的东西只能来自 render_assembly，没有别的路径会画它。"""
    manifest, _ = _manifest(tmp_path)
    _, assy = _gen(tmp_path, manifest, name="x")     # 装配图：有球标
    single = tmp_path / "plain.dxf"
    ev = generate_drawing(cadquery.importers.importStep(str(_part_a(tmp_path))), single,
                          part_name="P", revision="A", views=("TOP",))
    assert ev.get("assembly") is None
    assert _ents(single, ("CIRCLE",), "BALLOON") == []
    assert _ents(assy, ("CIRCLE",), "BALLOON")


class TestCliAssemblySurface:
    """``aipd drawing assembly`` 必须真能从命令行走到图纸——registry 里的
    e2e 凭据只认这条，手写 Namespace 直接调函数不算。"""

    def _run(self, tmp_path, manifest, *extra, name="cli"):
        from aipd_os.cli.main import main

        out = tmp_path / f"{name}.dxf"
        rc = main(["drawing", "assembly", "--manifest", str(manifest),
                   "--out", str(out), "--part", "ASSY-1", *extra])
        evidence = None
        if out.with_suffix(".evidence.json").exists():
            evidence = json.loads(out.with_suffix(".evidence.json").read_text("utf-8"))
        return rc, evidence, out

    def test_cli_writes_the_assembly_drawing_and_its_evidence(self, tmp_path, capsys):
        manifest, _ = _manifest(tmp_path)
        rc, ev, out = self._run(tmp_path, manifest, "--views", "TOP,FRONT")
        assert rc == 0, capsys.readouterr().out
        assert out.is_file()
        top = _view(ev, "ASSY_TOP")
        assert [b["number"] for b in top["balloons"]] == [1, 2]
        assert ev["parts_list"]["columns"] == ["ITEM", "PART"]
        assert len(ev["parts_list"]["rows"]) == 2
        text = capsys.readouterr().out
        assert "明细表" in text and "球标 2 个" in text
        # 命令行必须把「没做的事」也说出口，不能只报成功
        assert "干涉" in text and "BOM" in text

    def test_duplicate_balloon_numbers_are_a_declaration_error_not_a_silent_fix(
            self, tmp_path):
        manifest, _ = _manifest(tmp_path, balloons=(3, 3))
        rc, _, out = self._run(tmp_path, manifest, name="dup")
        assert rc == 2
        assert not out.exists(), "声明错误不能留下一张半成品图纸"

    def test_missing_manifest_file_is_rc2_before_any_geometry_work(self, tmp_path):
        rc, _, out = self._run(tmp_path, tmp_path / "nope.json", name="missing")
        assert rc == 2
        assert not out.exists()

    def test_part_without_solids_holds_the_command_at_rc4(self, tmp_path):
        """未收口必须改变**退出码**，不然 CI 会把「少画了一个零件」当成功。"""
        empty = tmp_path / "empty.step"
        cadquery.exporters.export(cadquery.Workplane("XY").rect(10, 10),
                                  str(empty), exportType="STEP")
        path = tmp_path / "empties.json"
        path.write_text(json.dumps({"parts": [{"name": "空", "step": str(empty),
                                               "balloon": 1}]}, ensure_ascii=False),
                        encoding="utf-8")
        rc, ev, _ = self._run(tmp_path, path, name="hold")
        assert rc == 4, "有空零件仍返回 0 ⇒ hold 只写在 JSON 里，命令行看不见"
        assert any("没有任何实体" in m for m in ev["assembly_issues"])


def test_only_the_first_requested_view_gets_balloon_numbers(tmp_path):
    """球标只标一次是**声明**，不是巧合：证据要能分出「这里故意不编号」和「编号没出来」。

    少了 balloon_view 这根旗，非编号视图的 ``balloons == []`` 与「发号那步坏了」
    在证据里长得一模一样；少了这条断言，「每个视图都圈一遍编号」也只能靠别处的
    圆圈计数间接抓到。
    """
    manifest, _ = _manifest(tmp_path)
    ev, out = _gen(tmp_path, manifest, views=("TOP", "FRONT"), name="twoview")
    top, front = _view(ev, "ASSY_TOP"), _view(ev, "ASSY_FRONT")
    assert top["balloon_view"] is True and top["balloons"]
    assert front["balloon_view"] is False, "非编号视图必须明写，不能只留一个空表"
    assert front["balloons"] == []
    assert len(_ents(out, ("CIRCLE",), "BALLOON")) == 2, "两个视图不该各标一套号"
