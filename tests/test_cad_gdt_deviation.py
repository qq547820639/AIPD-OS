"""位置度偏差的**实测核对**：理论精确位置（需求侧）× 投影实测圆心（模型侧）。

F-DRAW-01 第 7 片。第 6 片把形位框接上了需求侧，但覆盖凭据只到「框画上去了 + 挂在实测特征上」，
能力行里明写着「**不**核形位偏差数值」——因为那时确实没有偏差可核：
判一条位置度成不成立，需要「理论精确位置」，而它既不在图纸几何里（图纸只有实测位置），
也不能从公差带反推（那是把要求当事实）。

这一片把理论精确位置作为**声明的一部分**接进来：``gdt`` 条目带 ``basic: [x, y]``
（与实测挂点同一套视图坐标、同一单位），于是

- 偏差 = ``2 × 距离(实测圆心, 理论位置)``（直径带 ⇒ 乘 2）；
- 偏差 > 带 ⇒ ``position_deviation_exceeded``（阻断，命令未收口 exit 4）；
- 偏差 == 带 ⇒ 判合格（边界值 inside，容差是浮点噪声级的 ``POSITION_DEV_TOL``）；
- 位置度没给 ``basic`` ⇒ ``position_basic_missing``（阻断），
  **不**拿实测圆心当理论位置、也**不**拿 (0,0) 当默认——那等于自己给自己出题再自己打勾；
- 非位置度的框（平面度等）偏差列为 ``None``，不假装有数值结论。

判据两侧来源独立（需求 vs 模型），所以这一半不是自证；这也是本片唯一诚实的卖点和唯一的边界：
只核**位置**偏差，形状/方向类（平面度、垂直度、轮廓度）需要整面采样，本仓内核还没做，
所以那些框的覆盖凭据仍是第 6 片的「画上去了 + 挂实测」。

夹具实测前提（写进用例，不是记忆）：100×20×10 板、4 个 Ø6 通孔在 ``y=0``、
``x = -30,-10,10,30`` ⇒ TOP 视图里 ``TOP.hole_1`` 的实测圆心是 ``(-30.0, 0.0)``。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

cadquery = pytest.importorskip("cadquery", reason="cad 为可选 extra")
pytest.importorskip("ezdxf", reason="DXF 输出依赖 ezdxf")

from aipd_os.cad.drawings2d import generate_drawing  # noqa: E402

L, W, T, HD = 100.0, 20.0, 10.0, 6.0
MEASURED = [-30.0, 0.0]


def _plate():
    return (cadquery.Workplane("XY").box(L, W, T).faces(">Z").workplane()
            .pushPoints([(x, 0.0) for x in (-30.0, -10.0, 10.0, 30.0)])
            .hole(HD).solids().vals()[0])


def _spec(zone=0.05, basic=None, characteristic="position", datums=("A",)):
    gdt = {"characteristic": characteristic, "zone": zone, "diametral": True}
    if basic is not None:
        gdt["basic"] = list(basic)
    if datums:
        gdt["datums"] = list(datums)
    return {"features": [{"feature": "TOP.hole_1", "gdt": [gdt], "ctq_ref": "c1"}],
            "datums": [{"id": "A", "feature": "TOP.hole_4"}]}


def _gen(tmp_path, spec, name="gdtdev"):
    out = Path(tmp_path) / f"{name}.dxf"
    ev = generate_drawing(_plate(), out, part_name="plate", revision="A",
                          views=("TOP",), spec=spec)
    frame = next(f for f in ev["gdt_frames"] if f["feature"] == "TOP.hole_1")
    return ev, frame


class TestDeviationIsMeasuredNotAssumed:
    def test_a_feature_on_its_basic_position_has_zero_deviation(self, tmp_path):
        ev, frame = _gen(tmp_path, _spec(basic=MEASURED))
        assert ev["gdt_issues"] == []
        assert frame["deviation_mm"] == pytest.approx(0.0, abs=1e-9)
        assert frame["within_zone"] is True and frame["verified"] == "deviation"

    def test_offset_beyond_half_the_diametral_zone_is_a_violation(self, tmp_path):
        """实测在 -30.0，理论位置给 -30.04 ⇒ 偏差 2×0.04=0.08 > 带 0.05 ⇒ 判不合格。"""
        ev, frame = _gen(tmp_path, _spec(basic=[-30.04, 0.0]))
        kinds = [i["kind"] for i in ev["gdt_issues"]]
        assert kinds == ["position_deviation_exceeded"]
        one = ev["gdt_issues"][0]
        assert one["feature"] == "TOP.hole_1" and one["zone"] == 0.05
        assert one["deviation_mm"] == pytest.approx(0.08, abs=1e-9)
        assert one["basic"] == [-30.04, 0.0]
        assert one["measured"] == pytest.approx(MEASURED)
        assert one["ctq_ref"] == "c1" and one["blocking"] is True
        assert frame["within_zone"] is False

    def test_deviation_exactly_equal_to_the_zone_is_inside(self, tmp_path):
        """0.025 的偏心 ⇒ 偏差正好 0.05，等于带 ⇒ 判合格（边界不判罚）。"""
        ev, frame = _gen(tmp_path, _spec(basic=[-30.025, 0.0]))
        assert ev["gdt_issues"] == []
        assert frame["deviation_mm"] == pytest.approx(0.05, abs=1e-9)
        assert frame["within_zone"] is True

    def test_y_component_counts_too(self, tmp_path):
        """只偏 y 也算：证明用的是二维距离而不是一维相减。"""
        ev, frame = _gen(tmp_path, _spec(basic=[-30.0, 0.04]))
        assert frame["deviation_mm"] == pytest.approx(0.08, abs=1e-9)
        assert [i["kind"] for i in ev["gdt_issues"]] == ["position_deviation_exceeded"]

    def test_position_without_basic_is_named_not_defaulted(self, tmp_path):
        """没有理论位置就没有结论：既不拿实测当理论，也不拿 (0,0) 当默认。"""
        ev, frame = _gen(tmp_path, _spec(basic=None))
        assert [i["kind"] for i in ev["gdt_issues"]] == ["position_basic_missing"]
        assert frame["deviation_mm"] is None and frame["within_zone"] is None
        assert frame["verified"] == "presence_only"

    def test_a_shape_control_claiming_no_deviation_stays_presence_only(self, tmp_path):
        """平面度不要求 basic，也拿不到偏差：诚实标 presence_only。"""
        ev, frame = _gen(tmp_path, _spec(zone=0.02, basic=None, characteristic="flatness",
                                         datums=()))
        assert ev["gdt_issues"] == []
        assert frame["deviation_mm"] is None and frame["within_zone"] is None
        assert frame["verified"] == "presence_only"

    def test_deviation_survives_the_dxf_round_trip_as_evidence(self, tmp_path):
        """偏差与结论进证据 JSON，读回仍在（下游 CAD/审计据此复核，不靠屏幕截图）。"""
        ev, _frame = _gen(tmp_path, _spec(basic=[-30.04, 0.0]), name="roundtrip")
        ev = json.loads(Path(ev["evidence_file"]).read_text("utf-8"))
        frame = next(f for f in ev["gdt_frames"] if f["feature"] == "TOP.hole_1")
        assert frame["basic"] == [-30.04, 0.0]
        assert frame["deviation_mm"] == pytest.approx(0.08, abs=1e-9)
        assert frame["within_zone"] is False


class TestCliHoldsOnDeviation:
    def _run(self, tmp_path, spec, name):
        from aipd_os.cli.main import main

        spec_file = Path(tmp_path) / f"{name}.json"
        spec_file.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        out = Path(tmp_path) / f"{name}.dxf"
        rc = main(["drawing", "generate", "--out", str(out), "--part", "plate",
                   "--views", "TOP", "--spec", str(spec_file)])
        return rc

    def test_an_out_of_zone_position_holds_the_command(self, tmp_path, capsys):
        rc = self._run(tmp_path, _spec(basic=[-30.04, 0.0]), "hold")
        assert rc == 4
        text = capsys.readouterr().out
        assert "形位未收口" in text and "position_deviation_exceeded" in text
        assert "0.08" in text and "0.05" in text

    def test_a_missing_basic_holds_the_command(self, tmp_path, capsys):
        rc = self._run(tmp_path, _spec(basic=None), "nobasic")
        assert rc == 4
        assert "position_basic_missing" in capsys.readouterr().out

    def test_within_zone_position_passes_and_reports_the_number(self, tmp_path, capsys):
        rc = self._run(tmp_path, _spec(basic=MEASURED), "ok")
        assert rc == 0
        text = capsys.readouterr().out
        assert "位置度" in text and "实测偏差" in text
        assert "未收口" not in text


class TestProducerCarriesBasic:
    def test_spec_from_ctq_passes_the_basic_location_through(self):
        from types import SimpleNamespace

        from aipd_os.cad.spec_from_truth import spec_from_ctq

        rec = SimpleNamespace(record_id="g1", metadata={
            "feature": "孔位置度", "drawing_feature": "TOP.hole_1",
            "gdt": [{"characteristic": "position", "zone": 0.05, "diametral": True,
                     "datums": ["A"], "basic": [-30.0, 0.0]}]})
        spec, gaps = spec_from_ctq([rec])
        assert gaps == []
        assert spec["features"][0]["gdt"][0]["basic"] == [-30.0, 0.0]


def _db(tmp_path):
    from aipd_os.state.db import AIPDStateDB

    path = tmp_path / "state.db"
    state = AIPDStateDB(path)
    state.ensure_default_tenant()
    state.init_project("default", "proj_dev", "deviation 测试", "evidence")
    return path


class TestManifestRefusesBadCoverage:
    """偏差超带的框**不能**再当覆盖凭据：那样等于用「画错了的要求」给自己盖章。"""

    def _manifest(self, tmp_path, db, spec, name):
        from aipd_os.cli.main import main
        from aipd_os.release_manifest import build_release_manifest

        spec_file = Path(tmp_path) / f"{name}.json"
        spec_file.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        dxf = Path(tmp_path) / f"{name}.dxf"
        assert main(["drawing", "generate", "--out", str(dxf), "--part", "plate",
                     "--views", "TOP", "--spec", str(spec_file)]) == 4
        out = Path(tmp_path) / f"{name}-evidence.json"
        payload = build_release_manifest(db_path=db, tenant_id="default",
                                         project_id="proj_dev", drawings=[dxf],
                                         out_path=out)
        return out, payload, json.loads(out.read_text("utf-8"))

    def _seed(self, db, spec_name):
        """走真正的生产者：记录 → spec，引用才是同一个 id（不在测试里手抄 ctq_ref）。"""
        from types import SimpleNamespace

        from aipd_os.cad.spec_from_truth import spec_from_ctq
        from aipd_os.product_truth.models import TruthRecord
        from aipd_os.product_truth.store import ProductTruthStore

        meta = {"feature": "孔位置度", "drawing_feature": "TOP.hole_1",
                "gdt": [_spec(basic=basic_for(spec_name))["features"][0]["gdt"][0]],
                "inspection_method": "CMM"}
        datum_meta = {"feature": "基准A面", "datum_id": "A",
                      "drawing_feature": "TOP.hole_4"}
        store = ProductTruthStore(str(db), tenant_id="default", project_id="proj_dev")
        rid = store.add(TruthRecord(record_type="ctq", content="CTQ 孔位置度",
                                    trust_level="verified", metadata=meta),
                        tenant_id="default", project_id="proj_dev")
        did = store.add(TruthRecord(record_type="ctq", content="CTQ 基准A面",
                                    trust_level="verified", metadata=datum_meta),
                        tenant_id="default", project_id="proj_dev")
        spec, gaps = spec_from_ctq([
            SimpleNamespace(record_id=rid, metadata=meta),
            SimpleNamespace(record_id=did, metadata=datum_meta)])
        assert gaps == [] and spec["features"], "前提：生产者真产出了声明"
        return rid, spec

    def test_an_out_of_zone_frame_is_not_counted_as_coverage(self, tmp_path):
        db = _db(tmp_path)
        rid, spec = self._seed(db, "bad")
        out, payload, doc = self._manifest(tmp_path, db, spec, "bad")
        assert [g["ctq_record_id"] for g in doc["gdt"]] == []
        kinds = [i["kind"] for i in payload["issues"]]
        assert "position_deviation_exceeded" in kinds
        assert payload["blocking"] is True
        assert any(rid in str(i.get("detail", "")) or rid in str(i.get("feature", ""))
                   or i["kind"] == "position_deviation_exceeded" for i in payload["issues"])

    def test_a_within_zone_frame_is_counted_and_says_it_measured_the_deviation(self,
                                                                              tmp_path):
        from aipd_os.cli.main import main

        db = _db(tmp_path)
        rid, spec = self._seed(db, "good")
        spec_file = Path(tmp_path) / "good.json"
        spec_file.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        dxf = Path(tmp_path) / "good.dxf"
        assert main(["drawing", "generate", "--out", str(dxf), "--part", "plate",
                     "--views", "TOP", "--spec", str(spec_file)]) == 0
        from aipd_os.release_manifest import build_release_manifest

        out = Path(tmp_path) / "good-evidence.json"
        build_release_manifest(db_path=db, tenant_id="default", project_id="proj_dev",
                               drawings=[dxf], out_path=out)
        doc = json.loads(out.read_text("utf-8"))
        hits = [g for g in doc["gdt"] if g["ctq_record_id"] == rid]
        assert len(hits) == 1 and hits[0]["covered_by"] == "feature_control_frame"
        assert hits[0]["verified"] == "deviation"


def basic_for(name):
    """夹具：bad = 偏心 0.04（偏差 0.08 > 带 0.05），good = 与实测同位。"""
    return [-30.04, 0.0] if name == "bad" else [-30.0, 0.0]
