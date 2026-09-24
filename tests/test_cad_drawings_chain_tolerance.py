"""尺寸链与公差：链从「投影几何量出来的孔心」推，公差只允许来自声明（F-DRAW-01 第 1 片）。

出图此前的尺寸只有总体宽/高 + 孔径，没有尺寸链，也没有公差 ⇒ 图纸不可用于加工验收。
这一片的口径全部写成用例：

1. 链的各段来自孔心的实测投影位置，且「左沿→h1→…→hn→右沿」各段之和必须等于总体宽
   ——这是链条闭合的硬不变量，几何或测量一旦不一致就会断；
2. 公差**只来自 spec 声明**：没有 spec 时整张图不得出现任何公差（绝不"顺手给个 0.1"），
   spec 里写了但图上没有的特征要如实报出来，不得静默丢弃；
3. 写进 DXF 的每个 DIMENSION，其定义点距离除以比例必须等于登记的名义值——
   防止"文字写 40、几何是 39"这种图纸上最危险的分裂。

特征名一律带视图前缀（``TOP.hole_2``）：同一份模型里 FRONT 的 ``overall_width`` 是 100、
RIGHT 的 ``overall_width`` 是 10，不带前缀的声明会把公差贴到错误的尺寸上。

读数一律用 ezdxf 重新读回文件来取（本机 1.4.2 实测：线性尺寸 ``dimtype=32`` 用
``defpoint2/defpoint3``，直径尺寸 ``dimtype=35`` 用 ``defpoint/defpoint4``，
``dimtol/dimtp/dimtm`` 存盘后原样读回），不靠内存对象。
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest

cadquery = pytest.importorskip("cadquery", reason="cad 为可选 extra（cadquery>=2.4）")
pytest.importorskip("ezdxf", reason="DXF 写出依赖 ezdxf")

import ezdxf  # noqa: E402

from aipd_os.cad.drawings2d import STANDARD_VIEWS, build_view, generate_drawing  # noqa: E402

L, W, T, HD = 100.0, 20.0, 10.0, 6.0
HOLE_X = [-30.0, -10.0, 10.0, 30.0]
VIEW = "TOP"  # 竖直孔只有在俯视才投影成整圆，链的孔位来源必须是这个视图


def _plate(centers=None, length=L, *, hole_x=HOLE_X):
    pts = centers if centers is not None else [(x, 0.0) for x in hole_x]
    wp = cadquery.Workplane("XY").box(length, W, T)
    return wp.faces(">Z").workplane().pushPoints(pts).hole(HD).solids().vals()[0]


def _gen(tmp_path, *, spec=None, name="chain", centers=None, hole_x=HOLE_X, length=L):
    out = Path(tmp_path) / f"{name}.dxf"
    ev = generate_drawing(_plate(centers=centers, hole_x=hole_x, length=length), out,
                          part_name="plate", revision="A", views=(VIEW,),
                          spec=spec)
    return ev, out


def _dims(ev, view=VIEW):
    return next(v for v in ev["views"] if v["view"] == view)["dimensions"]


def _by_kind(ev, kind, view=VIEW):
    return [d for d in _dims(ev, view) if d["kind"] == kind]


def _read_dims(path):
    doc = ezdxf.readfile(str(path))
    return [e for e in doc.modelspace() if e.dxftype() == "DIMENSION"]


def _nominal_from_geometry(dim, scale=1.0):
    """从 DXF 定义点反算这条尺寸真正量到的长度（线性/直径两种几何）。"""
    if dim.dxf.dimtype == 35:
        p1, p2 = dim.dxf.defpoint, dim.dxf.defpoint4
    else:
        p1, p2 = dim.dxf.defpoint2, dim.dxf.defpoint3
    assert p1 is not None and p2 is not None, "定义点缺失，无法核验文字与几何是否一致"
    return math.hypot(p2.x - p1.x, p2.y - p1.y) / scale


def _text_value(dim):
    txt = dim.dxf.text
    if txt == "<>":
        return None
    numeric = txt.replace("%%c", "").strip()
    try:
        return float(numeric)
    except ValueError:  # pragma: no cover - 只有非数值文字才会走到这里
        return None


def _deviations(dim):
    """读回「偏差」本身。

    DXF 的 ``dimtm`` 存的是下偏差的相反数（ezdxf 渲染时对 dimtm 取负再打符号），
    所以断言必须换算回来，不能拿 ``dimtm`` 直接和声明比。
    """
    ov = dim.override()
    return {"upper": ov.get("dimtp"), "lower": -ov.get("dimtm")}


def _rendered_text(dim):
    """取 DIMENSION 渲染块里真正打在图纸上的文字（含公差堆叠）。"""
    doc = dim.doc
    name = dim.dxf.get("geometry")
    if not name or name not in doc.blocks:
        return ""
    return " ".join(t.dxf.text for t in doc.blocks.get(name) if t.dxftype() == "MTEXT")


class TestDimensionChain:
    def test_chain_is_measured_and_closes_against_overall(self, tmp_path):
        ev = _gen(tmp_path)[0]
        chain = _by_kind(ev, "chain")
        overall = _by_kind(ev, "overall_width")[0]
        assert [c["value"] for c in chain] == [20.0, 20.0, 20.0, 20.0, 20.0]
        assert overall["value"] == 100.0
        check = ev["dimension_chain_check"][VIEW]
        assert check["segments"] == 5
        assert check["delta"] == pytest.approx(0.0, abs=1e-9)

    def test_chain_follows_the_geometry_not_the_declaration(self, tmp_path):
        """把孔位挪开，链必须跟着变——证明值是从投影里量出来的。"""
        ev = _gen(tmp_path, name="moved", hole_x=[-40.0, 0.0, 40.0])[0]
        assert [c["value"] for c in _by_kind(ev, "chain")] == [10.0, 40.0, 40.0, 10.0]
        assert sum(c["value"] for c in _by_kind(ev, "chain")) == \
            _by_kind(ev, "overall_width")[0]["value"]

    def test_features_are_named_by_measured_order_not_detection_order(self, tmp_path):
        """孔的编号与链段必须按实测 x 递增，而不是内核检出/打孔顺序。

        本机实测（grid 图样）内核的检出顺序是 ``[(-10,-5),(30,-5),(-30,5),(10,5)]``，
        与 x 递增顺序不同，所以这条用例真的能区分两者；若哪天检出顺序恰好变成
        x 递增，下面那条前提断言会先红，提醒换图样而不是让守卫静默失效。
        """
        grid = [(-30.0, 5.0), (30.0, -5.0), (-10.0, -5.0), (10.0, 5.0)]
        detection_order = [tuple(c["center"]) for c in build_view(
            _plate(centers=grid), VIEW, *STANDARD_VIEWS[VIEW]).circles]
        measured_order = [(-30.0, 5.0), (-10.0, -5.0), (10.0, 5.0), (30.0, -5.0)]
        assert detection_order != measured_order, "前提已失效：两种顺序已不可区分"

        ev = _gen(tmp_path, name="names", centers=grid)[0]
        holes = _by_kind(ev, "hole_diameter")
        assert [h["feature"] for h in holes] == [f"{VIEW}.hole_{i}" for i in range(1, 5)]
        assert [tuple(h["center"]) for h in holes] == measured_order
        assert [c["feature"] for c in _by_kind(ev, "chain")] == \
            [f"{VIEW}.chain_{i}" for i in range(1, 6)]
        assert [c["value"] for c in _by_kind(ev, "chain")] == [20.0] * 5

    def test_no_chain_when_holes_share_one_axis_position(self, tmp_path):
        """两个孔同 x ⇒ 链里会出现零长段，这种链不成立，宁可不给。"""
        ev = _gen(tmp_path, name="same_x", centers=[(-30.0, 5.0), (-30.0, -5.0)])[0]
        assert _by_kind(ev, "chain") == []
        assert "TOP" in ev["dimension_chain_check"]
        assert ev["dimension_chain_check"][VIEW]["segments"] == 0

    def test_view_geometry_carries_the_same_chain(self):
        view = build_view(_plate(), VIEW, (0, 0, 1), (0, 1, 0))
        chain = [d for d in view.dimensions if d["kind"] == "chain"]
        assert len(chain) == 5, "build_view 自己就该产出链，不只是写 DXF 时才拼"


class TestToleranceProvenance:
    def test_no_spec_means_no_tolerances_anywhere(self, tmp_path):
        ev, out = _gen(tmp_path, name="nospec")
        assert _dims(ev), "图上没有尺寸，这条用例在空转"
        for dim in _read_dims(out):
            ov = dim.override()
            assert ov.get("dimtol") in (0, None), "无声明却写了公差 ⇒ 这是编造"
        assert ev["tolerance_applied"] == 0

    def test_tolerance_lands_only_on_the_declared_feature(self, tmp_path):
        spec = {"features": [{"feature": f"{VIEW}.hole_2",
                              "tolerance": {"upper": 0.05, "lower": -0.05}}]}
        ev, out = _gen(tmp_path, spec=spec, name="onefeat")
        holes = _by_kind(ev, "hole_diameter")
        assert holes[1]["tolerance"] == {"upper": 0.05, "lower": -0.05}
        assert all(h["tolerance"] is None for i, h in enumerate(holes) if i != 1)
        assert ev["tolerance_applied"] == 1
        assert ev["spec_unmatched_features"] == []

        dims = _read_dims(out)
        flagged = [d for d in dims if d.override().get("dimtol")]
        assert len(flagged) == 1
        assert _deviations(flagged[0]) == {"upper": pytest.approx(0.05),
                                          "lower": pytest.approx(-0.05)}

    def test_declaration_beats_global_and_global_covers_the_rest(self, tmp_path):
        spec = {"global_tolerance": {"upper": 0.2, "lower": -0.2},
                "features": [{"feature": f"{VIEW}.hole_2",
                              "tolerance": {"upper": 0.05, "lower": -0.05}}]}
        ev, out = _gen(tmp_path, spec=spec, name="mixed")
        holes = _by_kind(ev, "hole_diameter")
        assert holes[1]["tolerance"] == {"upper": 0.05, "lower": -0.05}
        assert holes[0]["tolerance"] == {"upper": 0.2, "lower": -0.2}
        assert ev["tolerance_applied"] == len(_dims(ev))

        for dim in _read_dims(out):
            ov = dim.override()
            assert ov.get("dimtol") == 1, "有全局声明却没落到某条尺寸上"
        assert [d.override().get("dimtp") for d in _read_dims(out)].count(0.05) == 1

    def test_global_tolerance_covers_every_dimension(self, tmp_path):
        spec = {"global_tolerance": {"upper": 0.2, "lower": -0.2}}
        ev, out = _gen(tmp_path, spec=spec, name="global")
        dims = _read_dims(out)
        assert dims, "图上没有尺寸，这条用例在空转"
        assert ev["tolerance_applied"] == len(_dims(ev))
        for dim in dims:
            assert dim.override().get("dimtol") == 1
            assert _deviations(dim) == {"upper": pytest.approx(0.2),
                                        "lower": pytest.approx(-0.2)}

    def test_declared_but_absent_feature_is_reported(self, tmp_path):
        """spec 写了图上没有的特征 ⇒ 必须点名，不能安静地少标一个公差。"""
        spec = {"features": [{"feature": f"{VIEW}.hole_9",
                              "tolerance": {"upper": 0.05, "lower": -0.05}}]}
        ev, out = _gen(tmp_path, spec=spec, name="ghost")
        assert ev["spec_unmatched_features"] == [f"{VIEW}.hole_9"]
        assert ev["tolerance_applied"] == 0
        for dim in _read_dims(out):
            assert dim.override().get("dimtol") in (0, None)


class TestDxfSelfConsistency:
    def test_every_dimension_matches_its_own_geometry(self, tmp_path):
        """文字与几何不得分裂：从 DXF 定义点反算的距离必须等于登记的名义值。"""
        spec = {"features": [{"feature": f"{VIEW}.overall_width",
                              "tolerance": {"upper": 0.1, "lower": -0.1}}]}
        ev, out = _gen(tmp_path, spec=spec, name="consistency")
        nominal = [d["value"] for d in _dims(ev)]
        dims = _read_dims(out)
        assert len(dims) == len(nominal)
        for dim in dims:
            measured = _nominal_from_geometry(dim, ev["scale"])
            assert any(abs(measured - n) < 1e-6 for n in nominal), (
                f"DXF 里有一处尺寸几何长度 {measured} 对不上任何登记名义值 {sorted(nominal)}")
            text_value = _text_value(dim)
            if text_value is not None:
                assert any(abs(text_value - n) < 1e-6 for n in nominal), dim.dxf.text

    def test_diameter_dims_stay_diameters_after_the_chain_was_added(self, tmp_path):
        ev, out = _gen(tmp_path, name="diam")
        holes = _by_kind(ev, "hole_diameter")
        assert len(holes) == 4
        assert all(abs(h["value"] - HD) < 1e-6 for h in holes)
        dia = [d for d in _read_dims(out) if d.dxf.dimtype == 35]
        assert len(dia) == 4
        for d in dia:
            assert d.dxf.text.startswith("%%c")
            assert abs(_nominal_from_geometry(d, ev["scale"]) - HD) < 1e-6

    def test_chain_segments_are_horizontal_linear_dims(self, tmp_path):
        """链必须是可测量的线性尺寸（不是文字），且逐段首尾相接。"""
        ev, out = _gen(tmp_path, name="linear")
        chain = _by_kind(ev, "chain")
        assert [d.dxf.dimtype for d in _read_dims(out)
                if d.dxf.dimtype == 32].count(32) >= len(chain)
        xs = [c["from_x"] for c in chain] + [chain[-1]["to_x"]]
        assert xs == pytest.approx([-50.0, -30.0, -10.0, 10.0, 30.0, 50.0], abs=1e-9)
        for lo, hi, seg in zip(xs, xs[1:], chain):
            assert seg["value"] == pytest.approx(hi - lo, abs=1e-9)


class TestRenderedToleranceText:
    """公差最终是「打在图纸上给人看」的，所以必须读渲染块文字，而不是只读属性。

    本机实测：把声明的下偏差原样塞进 ``dimtm`` 会得到 ``+0.05^ +0.05`` 这种双向正
    的假公差；正确写法是 ``dimtm = -lower``，四种偏差形状渲染后都与声明一致。
    """

    @pytest.mark.parametrize("upper,lower,tokens", [
        (0.05, -0.05, ["±0.05"]),
        (0.10, -0.02, ["+0.10", "-0.02"]),
        (0.05, 0.01, ["+0.05", "+0.01"]),
        (0.025, -0.025, ["±0.025"]),
    ])
    def test_rendered_text_says_what_was_declared(self, tmp_path, upper, lower, tokens):
        feature = f"{VIEW}.overall_width"
        spec = {"features": [{"feature": feature,
                              "tolerance": {"upper": upper, "lower": lower}}]}
        _, out = _gen(tmp_path, spec=spec, name=f"rend_{abs(upper)}_{abs(lower)}")
        flagged = [d for d in _read_dims(out) if d.override().get("dimtol")]
        assert len(flagged) == 1
        text = _rendered_text(flagged[0])
        assert text, "渲染块里没有文字，公差等于没画出来"
        for token in tokens:
            assert token in text, f"声明 {upper}/{lower} 却渲染成 {text!r}"
        if upper == -lower:  # 对称公差应打成 ±，不该是两行堆叠
            assert "\\S" not in text, text

    def test_tolerance_shown_in_full_not_truncated(self, tmp_path):
        """三位小数不得被默认的 2 位截成 0.03。"""
        spec = {"features": [{"feature": f"{VIEW}.overall_width",
                              "tolerance": {"upper": 0.005, "lower": -0.005}}]}
        _, out = _gen(tmp_path, spec=spec, name="decimals")
        dim = [d for d in _read_dims(out) if d.override().get("dimtol")][0]
        assert dim.override().get("dimtdec") >= 3
        assert "0.005" in _rendered_text(dim)

    def test_malformed_declaration_is_rejected_not_guessed(self, tmp_path):
        spec = {"features": [{"feature": f"{VIEW}.hole_1", "tolerance": {"upper": 0.05}}]}
        with pytest.raises(ValueError, match="lower"):
            _gen(tmp_path, spec=spec, name="bad")


class TestCliSpecSurface:
    """``--spec`` 必须真的能从命令行走到图纸，并且未匹配声明要把命令判住。"""

    @staticmethod
    def _ns(out, **kw):
        import argparse

        base = dict(out=str(out), part="cli_plate", revision="A", views=VIEW,
                    scale=1.0, material="-", sheet="A3", json=True,
                    step=None, native=None, spec=None)
        base.update(kw)
        return argparse.Namespace(**base)

    def _write_spec(self, tmp_path, spec):
        import json

        path = Path(tmp_path) / "tolerances.json"
        path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        return path

    def _run(self, tmp_path, spec_obj, name, json_mode=True):
        import json as _json

        from aipd_os.cli.commands_drawing import cmd_drawing

        out = Path(tmp_path) / f"{name}.dxf"
        args = self._ns(out)
        args.json = json_mode
        if spec_obj is not None:
            args.spec = str(self._write_spec(tmp_path, spec_obj))
        rc = cmd_drawing(args)
        evidence = None
        if out.with_suffix(".evidence.json").exists():
            evidence = _json.loads(out.with_suffix(".evidence.json").read_text("utf-8"))
        return rc, evidence, out

    def test_declared_tolerance_reaches_the_drawing_via_cli(self, tmp_path, capsys):
        spec = {"features": [{"feature": f"{VIEW}.hole_1",
                              "tolerance": {"upper": 0.02, "lower": -0.02}}]}
        rc, ev, out = self._run(tmp_path, spec, "cli_ok")
        assert rc == 0
        assert ev["tolerance_applied"] == 1
        assert ev["spec_unmatched_features"] == []
        assert [d for d in _read_dims(out) if d.override().get("dimtol")]

    def test_unmatched_declaration_holds_the_command(self, tmp_path, capsys):
        spec = {"features": [{"feature": "TOP.hole_99",
                              "tolerance": {"upper": 0.02, "lower": -0.02}}]}
        rc, ev, _ = self._run(tmp_path, spec, "cli_ghost", json_mode=False)
        assert rc == 4, "声明落空却返回 0 ⇒ 少标公差没人知道"
        assert ev["spec_unmatched_features"] == ["TOP.hole_99"]
        assert "未收口" in capsys.readouterr().out

    def test_missing_spec_file_is_usage_error_and_writes_nothing(self, tmp_path):
        rc, ev, out = self._run(tmp_path, None, "cli_missing")
        assert rc == 0 and ev["tolerance_applied"] == 0, "不传 --spec 也必须能出图"

        from aipd_os.cli.commands_drawing import cmd_drawing

        out2 = Path(tmp_path) / "cli_nospec.dxf"
        assert cmd_drawing(self._ns(out2, spec=str(Path(tmp_path) / "nope.json"))) == 2
        assert not out2.exists() and not out2.with_suffix(".evidence.json").exists()

    def test_invalid_declaration_is_reported_without_a_drawing(self, tmp_path):
        spec = {"features": [{"feature": f"{VIEW}.hole_1", "tolerance": {"upper": 0.02}}]}
        rc, _, out = self._run(tmp_path, spec, "cli_bad")
        assert rc == 2
        assert not out.exists()


