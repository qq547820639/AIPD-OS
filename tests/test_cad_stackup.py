"""公差叠加（stack-up）：链各段的偏差合成后，**图纸自相矛盾吗**（F-DRAW-01 第 2 片）。

先说清这一片**不**做什么：不猜功能要求、不算「能不能装得上」。仓库里没有「封闭尺寸
必须 ≤ X」这类外部要求，硬给一个限值就是编造判据。这一片只做一件有确定答案的事：

一条闭合链上，若各组成环的公差带之和已经超过封闭环（总体宽）自己声明的公差带，
那么「五段都合格且总宽也合格」在数学上不可能同时成立 ⇒ 这张图自相矛盾，必须报出来。

口径（全部写成用例，可手算复核）：
- 每段公差带 ``band = upper - lower``（非负；``0/0`` 是**声明**，不等于没声明）；
- 最坏值 ``worst_case = Σ band_i``；统计值 ``rss = √(Σ band_i²)``；
- 只要**任何一环缺声明**就整体判 ``insufficient_data`` 并点名缺哪几环——绝不按 0 折算；
- 封闭环没声明公差时判 ``no_closing_tolerance``，不假设「总体宽 = 精确值」。

对照过的上游实现：GitHub 上的 ``tolerance-stackup-cli``（MIT、1 star）读源码后确认
它对 tol 取 ``abs()`` ⇒ **不支持非对称偏差**，也不计算封闭环（要人手写成一行）。
本仓的声明本来就允许非对称（``{"upper": 0.1, "lower": -0.02}``），所以只借它的
公式形状，判据自己实现并用闭式手算值钉住。
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest

cadquery = pytest.importorskip("cadquery", reason="cad 为可选 extra")
pytest.importorskip("ezdxf", reason="DXF 写出依赖 ezdxf")

from aipd_os.cad.drawings2d import generate_drawing  # noqa: E402
from aipd_os.cad.stackup import band_of, view_stackup  # noqa: E402

L, W, T, HD = 100.0, 20.0, 10.0, 6.0
HOLE_X = [-30.0, -10.0, 10.0, 30.0]
VIEW = "TOP"
CHAIN = [f"{VIEW}.chain_{i}" for i in range(1, 6)]


def _plate(hole_x=HOLE_X):
    return (cadquery.Workplane("XY").box(L, W, T).faces(">Z").workplane()
            .pushPoints([(x, 0.0) for x in hole_x]).hole(HD).solids().vals()[0])


def _spec(pairs, overall=None):
    """pairs: {特征名: (upper, lower)}；overall 给封闭环声明。"""
    feats = [{"feature": k, "tolerance": {"upper": v[0], "lower": v[1]}}
             for k, v in pairs.items()]
    if overall is not None:
        feats.append({"feature": f"{VIEW}.overall_width",
                      "tolerance": {"upper": overall[0], "lower": overall[1]}})
    return {"features": feats}


def _gen(tmp_path, spec=None, hole_x=HOLE_X, name="stack"):
    out = Path(tmp_path) / f"{name}.dxf"
    ev = generate_drawing(_plate(hole_x), out, part_name="plate", revision="A",
                          views=(VIEW,), spec=spec)
    dims = next(v for v in ev["views"] if v["view"] == VIEW)["dimensions"]
    return ev, dims


def _chain(dims):
    return [d for d in dims if d["kind"] == "chain"]


class TestHandCheckableArithmetic:
    def test_band_is_upper_minus_lower_and_zero_is_a_declaration(self):
        assert band_of({"upper": 0.05, "lower": -0.05}) == pytest.approx(0.1)
        assert band_of({"upper": 0.10, "lower": -0.02}) == pytest.approx(0.12)
        assert band_of({"upper": 0.0, "lower": 0.0}) == 0.0     # 声明为「不许偏」
        assert band_of(None) is None                            # 没声明 ≠ 0

    def test_worst_case_above_the_closing_band_is_a_contradiction(self, tmp_path):
        spec = _spec({c: (0.05, -0.05) for c in CHAIN}, overall=(0.2, -0.2))
        _, dims = _gen(tmp_path, spec)
        r = view_stackup(dims, VIEW)
        assert r["worst_case"] == pytest.approx(0.5)        # 5 段 × 0.1
        assert r["closing_band"] == pytest.approx(0.4)
        assert r["verdict"] == "inconsistent"
        assert r["excess"] == pytest.approx(0.1)

    def test_wide_enough_closing_band_is_consistent(self, tmp_path):
        spec = _spec({c: (0.05, -0.05) for c in CHAIN}, overall=(0.5, -0.5))
        _, dims = _gen(tmp_path, spec)
        r = view_stackup(dims, VIEW)
        assert r["verdict"] == "consistent"
        assert r["worst_case"] == pytest.approx(0.5)
        assert r["margin"] == pytest.approx(0.5)            # 1.0 - 0.5

    def test_rss_is_the_root_sum_of_squares_and_smaller(self, tmp_path):
        spec = _spec({c: (0.05, -0.05) for c in CHAIN}, overall=(0.5, -0.5))
        _, dims = _gen(tmp_path, spec)
        r = view_stackup(dims, VIEW)
        assert r["rss"] == pytest.approx(math.sqrt(5 * 0.1 ** 2))
        assert r["rss"] < r["worst_case"]

    def test_asymmetric_bands_use_upper_minus_lower(self, tmp_path):
        spec = _spec({c: (0.10, -0.02) for c in CHAIN}, overall=(0.5, -0.5))
        _, dims = _gen(tmp_path, spec)
        r = view_stackup(dims, VIEW)
        assert r["worst_case"] == pytest.approx(5 * 0.12)
        assert r["rss"] == pytest.approx(math.sqrt(5 * 0.12 ** 2))


class TestFailClosedSemantics:
    def test_one_undeclared_link_kills_the_arithmetic_and_is_named(self, tmp_path):
        declared = {c: (0.05, -0.05) for c in CHAIN if c != f"{VIEW}.chain_3"}
        spec = _spec(declared, overall=(0.2, -0.2))
        _, dims = _gen(tmp_path, spec)
        r = view_stackup(dims, VIEW)
        assert r["verdict"] == "insufficient_data"
        assert r["undeclared"] == [f"{VIEW}.chain_3"]
        assert r["worst_case"] is None, "缺声明时不得按 0 折算出一个数"

    def test_missing_closing_tolerance_is_not_treated_as_exact(self, tmp_path):
        spec = _spec({c: (0.05, -0.05) for c in CHAIN})     # 只给各段，不给总体宽
        _, dims = _gen(tmp_path, spec)
        r = view_stackup(dims, VIEW)
        assert r["verdict"] == "no_closing_tolerance"
        assert r["worst_case"] == pytest.approx(0.5), "各段合成仍要算得出，只是没有对照物"

    def test_view_without_a_chain_says_so_instead_of_erroring(self, tmp_path):
        _, dims = _gen(tmp_path, name="nochaintol")
        front_only = [d for d in dims if d["kind"] == "overall_width"]
        r = view_stackup(front_only, VIEW)
        assert r["verdict"] == "no_chain"


class TestCliHoldsOnContradiction:
    """矛盾必须把命令判住：只打印不判红，等于把工程缺陷降级成日志。"""

    @staticmethod
    def _ns(out, spec_path):
        import argparse

        return argparse.Namespace(out=str(out), part="bracket", revision="A",
                                  views=VIEW, scale=1.0, material="-", sheet="A3",
                                  json=False, step=None, native=None, spec=str(spec_path))

    def _run(self, tmp_path, pairs, overall, name):
        import json

        from aipd_os.cli.commands_drawing import cmd_drawing

        spec_file = Path(tmp_path) / f"{name}.json"
        spec_file.write_text(json.dumps(_spec(pairs, overall), ensure_ascii=False),
                             encoding="utf-8")
        out = Path(tmp_path) / f"{name}.dxf"
        return cmd_drawing(self._ns(out, spec_file)), out

    def test_contradictory_declarations_hold_the_command(self, tmp_path, capsys):
        rc, _ = self._run(tmp_path, {c: (0.05, -0.05) for c in CHAIN}, (0.2, -0.2), "hold")
        assert rc == 4
        printed = capsys.readouterr().out
        assert "图纸自相矛盾" in printed and "未收口" in printed

    def test_consistent_declarations_pass(self, tmp_path, capsys):
        rc, _ = self._run(tmp_path, {c: (0.05, -0.05) for c in CHAIN}, (0.5, -0.5), "pass")
        assert rc == 0
        assert "一致" in capsys.readouterr().out


class TestEvidenceIntegration:
    def test_generate_drawing_carries_the_stackup_per_view(self, tmp_path):
        spec = _spec({c: (0.05, -0.05) for c in CHAIN}, overall=(0.2, -0.2))
        ev, dims = _gen(tmp_path, spec, name="evid")
        check = ev["stackup_check"][VIEW]
        assert check["verdict"] == "inconsistent"
        assert check["segments"] == len(_chain(dims)) == 5
        assert ev["stackup_inconsistent"] is True

    def test_the_stackup_reads_the_measured_chain_not_the_declaration(self, tmp_path):
        """孔位挪动 ⇒ 段数与段值变，叠加结果必须跟着量出来的链走。"""
        spec = {"features": [{"feature": f"{VIEW}.chain_{i}",
                              "tolerance": {"upper": 0.05, "lower": -0.05}}
                             for i in (1, 2)],
                "global_tolerance": {"upper": 0.3, "lower": -0.3}}
        ev, dims = _gen(tmp_path, spec, hole_x=[-40.0, 0.0, 40.0], name="moved")
        chain = _chain(dims)
        assert [c["value"] for c in chain] == [10.0, 40.0, 40.0, 10.0]
        check = ev["stackup_check"][VIEW]
        assert check["segments"] == 4
        # 4 段各 ±0.05，其中只有 2 段用了细公差，其余按全局 ±0.3
        assert check["worst_case"] == pytest.approx(2 * 0.1 + 2 * 0.6)
