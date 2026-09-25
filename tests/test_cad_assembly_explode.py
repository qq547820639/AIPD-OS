"""装配图爆炸视图（F-DRAW-01 第 17 片，把 C6 的「爆炸图」从 absent 升到 producer）。

**位移一律由作者声明**，本模块不算拆卸方向。这不是偷懒，是判据决定的：文献里自动
爆炸/拆卸方向的作法（《智能装配规划中的拆卸方向计算》，JCAD）是「对装配约束做离散球面
算法」+「为一件零件找到一条**无碰撞路径**后才定全局拆卸方向」，它要两样本仓没有的前提：

1. 装配约束/配合数据 —— `cad.assembly_constraints` 能力行的 implementation_file 与
   unit_test 两栏皆空（C6 普查已登记），本仓根本没有约束；
2. 干涉/碰撞检查 —— `cad/assembly.py` 的模块 docstring 明写只报**包络投影重叠**面积，
   不做实体求交。

缺这两样还要自动摆，等于画一张「没证过的拆卸顺序」而图纸看着完整——与本仓
「编号/对应关系都由声明、不外推」的既有纪律正好相反。所以这里吃文献的结构
（每一步 = 零件 + 方向 + 距离），来源换成 manifest 里的 ``explode``。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from aipd_os.cad.evidence import sidecar_path

cadquery = pytest.importorskip("cadquery", reason="cad 为可选 extra")
pytest.importorskip("ezdxf", reason="DXF 输出依赖 ezdxf")

from aipd_os.bom.models import BomLine  # noqa: E402
from aipd_os.bom.store import BomStore  # noqa: E402
from aipd_os.cad.assembly import (  # noqa: E402
    build_assembly_view,
    generate_assembly_drawing,
    load_assembly_parts,
    parse_assembly_manifest,
)
from aipd_os.cad.drawings2d import STANDARD_VIEWS, view_basis  # noqa: E402

TENANT = "default"
PROJECT = "explode-proj"


def _write_step(tmp_path: Path, name: str, shape) -> Path:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    cadquery.exporters.export(shape, str(path), exportType="STEP")
    return path


def _boxes(tmp_path):
    """两个同尺寸盒子，各自一份 STEP。相对摆法由 manifest 的 ``offset`` 声明。"""
    def box():
        return cadquery.Workplane("XY").box(40.0, 20.0, 10.0).solids().vals()[0]

    return _write_step(tmp_path, "a.step", box()), _write_step(tmp_path, "b.step", box())


def _manifest(tmp_path, entries, name="explode.json"):
    a, b = _boxes(tmp_path)
    steps = {"a": a, "b": b}
    parts = []
    for one in entries:
        spec = {"name": one["name"], "balloon": one["balloon"],
                "step": str(steps[one.get("step", "a")]),
                "offset": one.get("offset", [0.0, 0.0, 0.0])}
        if "explode" in one:
            spec["explode"] = one["explode"]
        if "bom_item" in one:
            spec["bom_item"] = one["bom_item"]
        parts.append(spec)
    path = tmp_path / name
    path.write_text(json.dumps({"parts": parts}, ensure_ascii=False), encoding="utf-8")
    return path


def _load(tmp_path, manifest_path):
    return load_assembly_parts(parse_assembly_manifest(str(manifest_path)))


def _top():
    return ("ASSY_TOP",) + STANDARD_VIEWS["TOP"]


class TestExplodeIsDeclaredNotComputed:
    def test_explode_vector_is_parsed_when_declared(self, tmp_path):
        man = _manifest(tmp_path, [{"name": "支架", "balloon": 1,
                                    "explode": [0.0, 0.0, 60.0]}])
        parts = _load(tmp_path, man)
        assert parts[0]["explode"] == [0.0, 0.0, 60.0]

    def test_absent_explode_is_none_not_zero(self, tmp_path):
        """没声明就是 None；折成 [0,0,0] 会让「这一件没参与爆炸」与「就在原位」同形。"""
        man = _manifest(tmp_path, [{"name": "支架", "balloon": 1}])
        assert _load(tmp_path, man)[0]["explode"] is None

    @pytest.mark.parametrize("bad", [[0.0, 0.0], [0.0, 0.0, 0.0, 1.0],
                                     [0.0, "x", 0.0], "up", {"z": 60}])
    def test_malformed_explode_is_rejected(self, tmp_path, bad):
        path = tmp_path / "bad.json"
        path.write_text(json.dumps({"parts": [{"name": "支架", "step": str(_boxes(tmp_path)[0]),
                                               "balloon": 1, "explode": bad}]},
                                   ensure_ascii=False), encoding="utf-8")
        with pytest.raises(ValueError, match="explode"):
            parse_assembly_manifest(str(path))

    def test_exploding_a_part_without_a_declared_vector_is_refused(self, tmp_path):
        """要爆炸却有人没声明位移 ⇒ 拒，不画一张「只有部分零件被摆开」的半成品爆炸图。"""
        man = _manifest(tmp_path, [{"name": "支架", "balloon": 1, "explode": [0, 0, 60]},
                                   {"name": "压板", "balloon": 2, "step": "b"}])
        with pytest.raises(ValueError, match="爆炸"):
            generate_assembly_drawing(tmp_path / "x.dxf", manifest=str(man),
                                      part_name="ASSY-1", views=("TOP",), explode=True)
        assert not (tmp_path / "x.dxf").exists(), "拒了就不该留下图纸"

    def test_no_explode_keeps_the_twelve_slice_shape(self, tmp_path):
        man = _manifest(tmp_path, [{"name": "支架", "balloon": 1}])
        ev = generate_assembly_drawing(tmp_path / "plain.dxf", manifest=str(man),
                                       part_name="ASSY-1", views=("TOP",))
        assert ev["views"][0]["exploded"] is False
        assert ev["views"][0]["connectors"] == []


class TestExplodedGeometryIsVerifiable:
    def _parts(self, tmp_path, explode_a, explode_b=None):
        entries = [{"name": "支架", "balloon": 1, "explode": explode_a}]
        if explode_b is not None:
            entries.append({"name": "压板", "balloon": 2, "step": "b", "explode": explode_b})
        man = _manifest(tmp_path, entries)
        return _load(tmp_path, man)

    def _front(self, parts, explode=False):
        return build_assembly_view(parts, "ASSY_FRONT", *STANDARD_VIEWS["FRONT"],
                                   explode=explode)

    def test_exploded_position_is_the_declared_shift_projected(self, tmp_path):
        """爆炸位 = 装配位 + 声明位移在**这个视图**上的投影——逐位对得上才可复核。"""
        parts = self._parts(tmp_path, [60.0, 0.0, 0.0])
        flat = build_assembly_view(_load_parts_no_explode(parts), *_top())
        blown = build_assembly_view(parts, *_top(), explode=True)
        basis = view_basis(*STANDARD_VIEWS["TOP"])
        dx = parts[0]["explode"][0] * basis["right"][0] + \
            parts[0]["explode"][1] * basis["right"][1] + \
            parts[0]["explode"][2] * basis["right"][2]
        dy = parts[0]["explode"][0] * basis["up"][0] + \
            parts[0]["explode"][1] * basis["up"][1] + \
            parts[0]["explode"][2] * basis["up"][2]
        a0 = flat.assembly["parts"][0]["centroid"]
        a1 = blown.assembly["parts"][0]["centroid"]
        assert a1[0] - a0[0] == pytest.approx(dx, abs=1e-6)
        assert a1[1] - a0[1] == pytest.approx(dy, abs=1e-6)

    def test_one_connector_per_part_between_assembled_and_exploded(self, tmp_path):
        parts = self._parts(tmp_path, [60.0, 0.0, 0.0], [-60.0, 0.0, 0.0])
        blown = build_assembly_view(parts, *_top(), explode=True)
        cons = blown.assembly["connectors"]
        assert len(cons) == len(parts), cons
        for con, one in zip(cons, blown.assembly["parts"]):
            assert con["from"] == one["assembled_centroid"]
            assert con["to"] == one["centroid"], "连线两头一个是装配位一个是爆炸位"

    def test_envelope_projection_overlap_shrinks_after_exploding(self, tmp_path):
        """爆炸图的正面价值：原本沿投影方向叠着、看不出前后的两件，摆开以后包络不再互压。

        这条不是「画得好不好看」，是**重叠面积这个数真的变小**——它才是读图分不出归属的
        那个原因（第 12 片的挂点告警就是它）。
        """
        # 两件沿 Z 部分叠着（offset [0,0,5] 与爆炸位移都由作者声明），
        # FRONT 视图里 Z 在投影面内 => 摆开以后包络不再互压。
        man = _manifest(tmp_path, [{"name": "支架", "balloon": 1, "explode": [0, 0, 0.0]},
                                   {"name": "压板", "balloon": 2, "step": "b",
                                    "offset": [0, 0, 5], "explode": [0, 0, 40]}])
        parts = _load(tmp_path, man)
        assembled = self._front(_load_parts_no_explode(parts))
        blown = self._front(parts, explode=True)
        assert assembled.assembly["overlap_area_mm2"] > 0.0
        assert blown.assembly["overlap_area_mm2"] < assembled.assembly["overlap_area_mm2"]

    def test_exploding_along_the_view_axis_warns_that_nothing_separates(self, tmp_path):
        """位移与视线平行时在图上看不出分离——图没错（爆炸真做了），但读者拿不到信息。"""
        man = _manifest(tmp_path, [{"name": "支架", "balloon": 1, "explode": [0, 0, 60]}])
        view = build_assembly_view(_load(tmp_path, man), "ASSY_TOP",
                                   *STANDARD_VIEWS["TOP"], explode=True)
        assert any("看不出分离" in w for w in view.assembly["warnings"]), \
            view.assembly["warnings"]
        assert view.assembly["exploded"] is True

    def test_envelope_covers_every_exploded_part(self, tmp_path):
        parts = self._parts(tmp_path, [60.0, 0.0, 0.0], [-60.0, 0.0, 0.0])
        blown = build_assembly_view(parts, *_top(), explode=True)
        env = blown.assembly["envelope"]
        for one in blown.assembly["parts"]:
            assert env[0] <= one["bbox"][0] and one["bbox"][2] <= env[2], (env, one)
            assert env[1] <= one["bbox"][1] and one["bbox"][3] <= env[3], (env, one)


def _load_parts_no_explode(parts):
    """同一批零件，但把声明的爆炸位移摘掉（当作装配位对照）。"""
    return [{**p, "explode": None} for p in parts]


class TestBalloonsStayOnTheExplodedPosition:
    def test_anchor_is_the_exploded_centroid_not_the_assembled_one(self, tmp_path):
        man = _manifest(tmp_path, [{"name": "支架", "balloon": 1, "explode": [0, 60, 0]}])
        parts = _load(tmp_path, man)
        view = build_assembly_view(parts, "ASSY_TOP", *STANDARD_VIEWS["TOP"],
                                   explode=True)
        bal = view.assembly["balloons"][0]
        assert bal["anchor"] == view.assembly["parts"][0]["centroid"], \
            "球标指着零件现在在的地方，不是它爆炸前的地方"
        assert bal["anchor"] != view.assembly["parts"][0]["assembled_centroid"]

    def test_numbers_stay_author_declared(self, tmp_path):
        """爆炸**不重排编号**：摆开之后按位置重发号就等于图纸在说一个作者没说过的顺序。"""
        man = _manifest(tmp_path, [{"name": "支架", "balloon": 7, "explode": [60, 0, 0]},
                                   {"name": "压板", "balloon": 3, "step": "b",
                                    "explode": [-60, 0, 0]}])
        parts = _load(tmp_path, man)
        view = build_assembly_view(parts, "ASSY_TOP", *STANDARD_VIEWS["TOP"],
                                   explode=True)
        assert [b["number"] for b in view.assembly["balloons"]] == [3, 7]


class TestDrawingAndEvidence:
    def test_exploded_drawing_carries_an_explode_layer_with_one_line_per_part(self, tmp_path):
        import ezdxf

        man = _manifest(tmp_path, [{"name": "支架", "balloon": 1, "explode": [60, 0, 0]},
                                   {"name": "压板", "balloon": 2, "step": "b",
                                    "explode": [-60, 0, 0]}])
        out = tmp_path / "blown.dxf"
        ev = generate_assembly_drawing(out, manifest=str(man), part_name="ASSY-1",
                                       views=("TOP",), explode=True)
        assert ev["views"][0]["exploded"] is True
        assert len(ev["views"][0]["connectors"]) == 2
        doc = ezdxf.readfile(str(out))
        lines = [e for e in doc.modelspace().query('LINE[layer=="EXPLODE"]')]
        assert len(lines) == 2, len(lines)

    def test_evidence_records_both_positions_per_part(self, tmp_path):
        man = _manifest(tmp_path, [{"name": "支架", "balloon": 1, "explode": [60, 0, 0]}])
        ev = generate_assembly_drawing(tmp_path / "e.dxf", manifest=str(man),
                                       part_name="ASSY-1", views=("TOP",), explode=True)
        one = ev["views"][0]["assembly_parts"][0]
        assert one["explode"] == [60.0, 0.0, 0.0]
        assert one["assembled_centroid"] != one["centroid"]

    def test_bom_binding_is_unaffected_by_exploding(self, tmp_path):
        store = BomStore(tmp_path / "bom.db")
        header = store.create_bom(TENANT, PROJECT, "爆炸 BOM")
        store.add_line(BomLine(line_id="L-1", bom_id=header.bom_id, tenant_id=TENANT,
                               project_id=PROJECT, item="BRACKET-01", quantity=4.0,
                               unit="pcs", material="6061-T6"))
        man = _manifest(tmp_path, [{"name": "支架", "balloon": 1, "explode": [60, 0, 0],
                                    "bom_item": "BRACKET-01"}])
        ev = generate_assembly_drawing(tmp_path / "b.dxf", manifest=str(man),
                                       part_name="ASSY-1", views=("TOP",), explode=True,
                                       bom_lines=store.list_lines(TENANT, PROJECT,
                                                                  header.bom_id))
        assert ev["parts_list"]["columns"] == \
            ["ITEM", "PART", "QTY", "UNIT", "MATERIAL", "PROCESS"]
        assert ev["parts_list"]["rows"][0]["qty"] == 4.0
        assert ev["assembly_issues"] == []


class TestCliSurface:
    def _run(self, tmp_path, manifest, extra, name="cli"):
        from aipd_os.cli.main import main

        out = tmp_path / f"{name}.dxf"
        rc = main(["drawing", "assembly", "--manifest", str(manifest), "--out", str(out),
                   "--part", "ASSY-1", "--views", "TOP", *extra])
        ev = None
        if sidecar_path(out).exists():
            ev = json.loads(sidecar_path(out).read_text("utf-8"))
        return rc, ev, out

    def test_explode_flag_switches_the_view(self, tmp_path, capsys):
        man = _manifest(tmp_path, [{"name": "支架", "balloon": 1, "explode": [60, 0, 0]}])
        rc, ev, _ = self._run(tmp_path, man, ["--explode"], name="on")
        assert rc == 0, capsys.readouterr().out
        assert ev["views"][0]["exploded"] is True
        assert "爆炸视图" in capsys.readouterr().out

    def test_without_the_flag_the_declared_explode_is_ignored(self, tmp_path):
        man = _manifest(tmp_path, [{"name": "支架", "balloon": 1, "explode": [60, 0, 0]}])
        rc, ev, _ = self._run(tmp_path, man, [], name="off")
        assert rc == 0
        assert ev["views"][0]["exploded"] is False

    def test_missing_declaration_holds_the_command_at_rc2(self, tmp_path, capsys):
        man = _manifest(tmp_path, [{"name": "支架", "balloon": 1, "explode": [60, 0, 0]},
                                   {"name": "压板", "balloon": 2, "step": "b"}])
        rc, ev, out = self._run(tmp_path, man, ["--explode"], name="half")
        text = capsys.readouterr().out
        assert rc == 2, text
        assert not out.exists(), "拒了不能留半成品图纸"
        # 必须认得出是**出图前那道整体校验**拒的：只报「零件 X 没声明 explode」是投影时
        # 才发现的，那时图纸已经建到一半。两道检查都留着，但断言得能分辨是哪一道。
        assert "爆炸视图要求每个零件都声明" in text, text
        assert "压板" in text, text

    def test_other_views_still_reject_derived_views(self, tmp_path):
        """未知视图照样拒（爆炸不改变这条）。"""
        man = _manifest(tmp_path, [{"name": "支架", "balloon": 1, "explode": [60, 0, 0]}])
        with pytest.raises(ValueError, match="视图"):
            generate_assembly_drawing(tmp_path / "s.dxf", manifest=str(man),
                                      part_name="ASSY-1", views=("NOPE",), explode=True)
