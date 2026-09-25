"""公差声明的生产者：CTQ（Product Truth）→ 图纸 `--spec`，并用实测值反查合格域。

F-DRAW-01 第 5 片。改前的真实缺口（已核实，不是推测）：`resolve_spec_tolerances`
只吃人手写的 JSON，`ctq_ref` 也要人逐条抄 ⇒ 门禁 `gdt_covers_ctq` 实际考的是
「人抄得对不对」。这一片让产品自己长出声明，并补上一条**不自证**的判据：
声明里的绝对上下限与**图纸投影实测值**对得上吗。

为什么「实测值 vs CTQ 合格域」这一半不是循环论证：上下限来自 CTQ（需求侧），
实测值来自 OCP 投影几何（制造/模型侧），两者独立；而「偏差 = 上限 − 标称」那一半
确实是由 CTQ 推出来的，所以本文件同时把「CTQ 缺 linkage/标称」这类情况一律判
未收口，绝不让生产者自己把空洞填平。

本机实测前提（写进用例，不是记忆）：夹具板 100×20×10、4 个 Ø6 通孔，
TOP 视图实测 `TOP.hole_1 = 6.0`、`TOP.overall_width = 100.0`。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from aipd_os.cad.evidence import sidecar_path
from aipd_os.cad.spec_from_truth import spec_from_ctq
from aipd_os.product_truth.models import TruthRecord
from aipd_os.product_truth.store import ProductTruthStore

cadquery = pytest.importorskip("cadquery", reason="cad 为可选 extra")
pytest.importorskip("ezdxf", reason="DXF 输出依赖 ezdxf")

from aipd_os.cad.drawings2d import generate_drawing  # noqa: E402

GATE = Path(__file__).resolve().parents[1] / "scripts" / "production_release_gate.py"
T = "default"
P = "proj_spec"


def _ctq(record_id, metadata, status="active"):
    return SimpleNamespace(record_id=record_id, metadata=dict(metadata), status=status)


def _hole_ctq(record_id="c1", drawing_feature="TOP.hole_1", *, feature="hole_Ø6",
              nominal=6.0, lower=5.95, upper=6.05, extra=None):
    meta = {"feature": feature, "drawing_feature": drawing_feature, "nominal": nominal,
            "lower_limit": lower, "upper_limit": upper, "inspection_method": "CMM"}
    if extra:
        meta.update(extra)
    return _ctq(record_id, meta)


class TestSpecGrowsFromCtq:
    def test_a_complete_ctq_becomes_a_traceable_declaration(self):
        spec, gaps = spec_from_ctq([_hole_ctq()])
        assert gaps == []
        assert len(spec["features"]) == 1
        entry = spec["features"][0]
        assert entry["feature"] == "TOP.hole_1"
        assert entry["tolerance"] == {"upper": 0.05, "lower": -0.05}
        assert entry["ctq_ref"] == "c1"
        assert entry["limits"] == {"min": 5.95, "max": 6.05, "nominal": 6.0}

    def test_asymmetric_limits_keep_both_signs(self):
        spec, gaps = spec_from_ctq([_hole_ctq(nominal=6.0, lower=5.9, upper=6.05)])
        assert gaps == []
        assert spec["features"][0]["tolerance"] == {"upper": 0.05, "lower": -0.1}

    def test_no_drawing_feature_is_a_gap_not_a_name_match(self):
        """特征名叫 hole_Ø6、图上也真有孔，也**不许**据此挂上去——猜错就是标错尺寸。"""
        meta = {"feature": "hole_Ø6", "nominal": 6.0, "lower_limit": 5.95,
                "upper_limit": 6.05}
        spec, gaps = spec_from_ctq([_ctq("c9", meta)])
        assert spec["features"] == []
        assert [g["kind"] for g in gaps] == ["ctq_missing_drawing_feature"]
        assert "TOP.hole" not in json.dumps(spec, ensure_ascii=False)

    def test_missing_nominal_is_not_filled_with_the_measured_value(self):
        spec, gaps = spec_from_ctq([_ctq("c2", {
            "feature": "hole_Ø6", "drawing_feature": "TOP.hole_1",
            "lower_limit": 5.95, "upper_limit": 6.05})])
        assert spec["features"] == []
        assert gaps[0]["kind"] == "ctq_missing_limit_value"
        assert "nominal" in gaps[0]["detail"]

    def test_string_limits_count_as_missing_not_coerced(self):
        """``"6.0"`` 这种脏值不折算成数：宁可点名缺什么，也不替调用方猜一个类型。"""
        spec, gaps = spec_from_ctq([_ctq("c3", {
            "feature": "hole_Ø6", "drawing_feature": "TOP.hole_1", "nominal": "6.0",
            "lower_limit": 5.95, "upper_limit": 6.05})])
        assert spec["features"] == []
        assert gaps[0]["kind"] == "ctq_missing_limit_value"

    def test_inverted_limits_are_named_not_swapped(self):
        spec, gaps = spec_from_ctq([_hole_ctq(lower=6.05, upper=5.95)])
        assert spec["features"] == []
        assert gaps[0]["kind"] == "ctq_limits_inverted"

    def test_two_ctqs_claiming_one_dimension_produce_neither(self):
        """取后者覆盖前者 = 悄悄丢掉一条要求；两条都不产出并点名才是可审计的。"""
        spec, gaps = spec_from_ctq([_hole_ctq("c1"), _hole_ctq("c2", feature="hole_Ø6b")])
        assert spec["features"] == []
        assert [g["kind"] for g in gaps] == ["ctq_duplicate_drawing_feature"]
        assert "c1" in gaps[0]["detail"]

    def test_empty_input_is_an_empty_spec_not_an_error(self):
        spec, gaps = spec_from_ctq([])
        assert spec == {"features": [], "generated_from": "product_truth.ctq"}
        assert gaps == []

    def test_global_tolerance_is_never_inferred(self):
        """总宽的 CTQ 若被推成 global_tolerance，会贴满每一条没单独声明的尺寸。"""
        spec, gaps = spec_from_ctq([
            _hole_ctq("c1"),
            _hole_ctq("c2", drawing_feature="TOP.overall_width", feature="板长",
                      nominal=100.0, lower=99.95, upper=100.05)])
        assert gaps == []
        assert "global_tolerance" not in spec
        assert len(spec["features"]) == 2


def _plate():
    return (cadquery.Workplane("XY").box(100.0, 20.0, 10.0).faces(">Z").workplane()
            .pushPoints([(-30.0, 0.0), (-10.0, 0.0), (10.0, 0.0), (30.0, 0.0)])
            .hole(6.0).solids().vals()[0])


def _generate(tmp_path, spec=None, name="spec"):
    out = Path(tmp_path) / f"{name}.dxf"
    ev = generate_drawing(_plate(), out, part_name="plate", revision="A",
                          views=("TOP",), spec=spec)
    return ev, out


class TestMeasuredGeometryAgainstTheCtqWindow:
    def _dims(self, ev):
        return {d["feature"]: d for d in
                next(v for v in ev["views"] if v["view"] == "TOP")["dimensions"]}

    def test_a_model_that_fits_the_window_raises_nothing(self, tmp_path):
        spec, gaps = spec_from_ctq([_hole_ctq()])
        assert gaps == []
        ev, _ = _generate(tmp_path, spec)
        assert ev["spec_limit_issues"] == []
        assert self._dims(ev)["TOP.hole_1"]["tolerance"] == {"upper": 0.05, "lower": -0.05}
        assert self._dims(ev)["TOP.hole_1"]["ctq_ref"] == "c1"

    def test_measured_outside_the_ctq_window_is_a_violation(self, tmp_path):
        """标称 6.5、合格域 6.45–6.55，实测 6.0 ⇒ 模型不满足这条 CTQ，必须点名。"""
        spec, gaps = spec_from_ctq([_hole_ctq(nominal=6.5, lower=6.45, upper=6.55)])
        assert gaps == []
        ev, _ = _generate(tmp_path, spec, name="violate")
        issues = ev["spec_limit_issues"]
        assert [i["kind"] for i in issues] == ["ctq_window_violation"]
        one = issues[0]
        assert one["feature"] == "TOP.hole_1" and one["measured"] == pytest.approx(6.0)
        assert one["min"] == 6.45 and one["max"] == 6.55 and one["ctq_ref"] == "c1"

    def test_a_value_exactly_on_the_boundary_is_inside(self, tmp_path):
        spec, _ = spec_from_ctq([_hole_ctq(nominal=6.0, lower=5.9, upper=6.0)])
        ev, _ = _generate(tmp_path, spec, name="boundary")
        assert ev["spec_limit_issues"] == []

    def test_no_limits_means_no_new_judgement(self, tmp_path):
        """手写 spec（没有 limits）行为不变：本片不悄悄给旧路径加判据。"""
        ev, _ = _generate(tmp_path, {"features": [
            {"feature": "TOP.hole_1", "tolerance": {"upper": 0.05, "lower": -0.05}}]},
            name="legacy")
        assert ev["spec_limit_issues"] == []


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "state.db"
    from aipd_os.state.db import AIPDStateDB

    state = AIPDStateDB(path)
    state.ensure_default_tenant()
    state.init_project(T, P, "spec from truth 测试", "evidence")
    return path


def _seed(db_path, *metas, record_type="ctq"):
    store = ProductTruthStore(str(db_path), tenant_id=T, project_id=P)
    ids = []
    for i, meta in enumerate(metas, start=1):
        ids.append(store.add(TruthRecord(record_type=record_type,
                                         content=f"CTQ {meta.get('feature', i)}",
                                         trust_level="verified", metadata=dict(meta)),
                             tenant_id=T, project_id=P))
    return ids


HOLE = {"feature": "hole_Ø6", "drawing_feature": "TOP.hole_1", "nominal": 6.0,
        "lower_limit": 5.95, "upper_limit": 6.05, "inspection_method": "CMM"}


class TestCliProducerAndGate:
    def test_spec_command_writes_a_declaration_the_drawing_can_consume(self, tmp_path, db):
        from aipd_os.cli.main import main

        rid = _seed(db, HOLE)[0]
        out = tmp_path / "spec.json"
        rc = main(["drawing", "spec", "--db", str(db), "--project", P,
                   "--out", str(out), "--json"])
        assert rc == 0
        spec = json.loads(out.read_text("utf-8"))
        assert spec["features"][0]["ctq_ref"] == rid
        assert spec["features"][0]["tolerance"] == {"upper": 0.05, "lower": -0.05}

    def test_a_gap_holds_the_command_and_writes_nothing(self, tmp_path, db, capsys):
        """半成品 spec 一旦落盘就是一份「看着能用、其实漏标」的声明 ⇒ 不写文件。"""
        from aipd_os.cli.main import main

        bad = {k: v for k, v in HOLE.items() if k != "drawing_feature"}
        _seed(db, bad)
        out = tmp_path / "never.json"
        rc = main(["drawing", "spec", "--db", str(db), "--project", P, "--out", str(out)])
        assert rc == 4
        assert not out.exists()
        assert "drawing_feature" in capsys.readouterr().out

    def test_inactive_records_are_not_declared(self, tmp_path, db):
        """已作废的 CTQ 不能继续往图纸上贴公差。"""
        from aipd_os.cli.main import main

        store = ProductTruthStore(str(db), tenant_id=T, project_id=P)
        rid = _seed(db, HOLE)[0]
        store.update(rid, tenant_id=T, project_id=P, status="superseded")
        out = tmp_path / "stale.json"
        assert main(["drawing", "spec", "--db", str(db), "--project", P,
                     "--out", str(out), "--json"]) == 0
        assert json.loads(out.read_text("utf-8"))["features"] == []

    def test_a_window_violation_holds_the_drawing_command(self, tmp_path, capsys):
        """声明写全了、但模型实测落在合格域外 ⇒ 出图命令拦下来，不是照出无误图纸。"""
        from aipd_os.cli.main import main

        spec = {"features": [{"feature": "TOP.hole_1",
                              "tolerance": {"upper": 0.05, "lower": -0.05},
                              "limits": {"min": 1000.0, "max": 1001.0},
                              "ctq_ref": "c1"}]}
        spec_file = tmp_path / "violate.json"
        spec_file.write_text(json.dumps(spec), encoding="utf-8")
        rc = main(["drawing", "generate", "--out", str(tmp_path / "v.dxf"),
                   "--part", "plate", "--views", "TOP", "--spec", str(spec_file)])
        assert rc == 4
        text = capsys.readouterr().out
        assert "合格域未收口" in text and "1000" in text and "CTQ c1" in text

    def test_the_whole_chain_needs_no_hand_written_spec_to_pass_the_gate(self, tmp_path, db):
        """产品自己出声明 ⇒ 门禁 gdt_covers_ctq 绿，且全程没人手写 ctq_ref。"""
        from aipd_os.cli.main import main
        from aipd_os.release_manifest import build_release_manifest

        rid = _seed(db, HOLE)[0]
        spec_file = tmp_path / "chain.json"
        assert main(["drawing", "spec", "--db", str(db), "--project", P,
                     "--out", str(spec_file)]) == 0
        _, dxf = _generate(tmp_path, json.loads(spec_file.read_text("utf-8")), name="chain")
        path = tmp_path / "release-evidence.json"
        build_release_manifest(db_path=db, tenant_id=T, project_id=P, drawings=[dxf],
                               out_path=path)
        doc = json.loads(path.read_text("utf-8"))
        assert [g["ctq_record_id"] for g in doc["gdt"]] == [rid], \
            "证据要写清「是对着哪条 CTQ 成立的」，只说「匹配上了」不可审计"
        proc = subprocess.run([sys.executable, str(GATE), "--manifest", str(path),
                               "--target", "C5"], capture_output=True, text=True)
        entry = next(c for c in json.loads(proc.stdout)["evidence_checks"]
                     if c["check"] == "gdt_covers_ctq")
        assert entry["passed"], entry["detail"]


FLATNESS = [{"characteristic": "flatness", "zone": 0.02}]


def _stripped(decls):
    """去掉生产者加的 ctq_ref 引用后比较声明本体。"""
    return [{k: v for k, v in d.items() if k != "ctq_ref"} for d in decls]


class TestGdtAndDatumsFromCtq:
    def test_a_gdt_only_ctq_declares_a_frame_without_inventing_a_size(self):
        spec, gaps = spec_from_ctq([_ctq("g1", {
            "feature": "面轮廓要求", "drawing_feature": "TOP.hole_1", "gdt": FLATNESS})])
        assert gaps == []
        entry = spec["features"][0]
        assert "tolerance" not in entry, "只声明形位的 CTQ 不该被塞进一个尺寸公差"
        assert _stripped(entry["gdt"]) == FLATNESS, "形位声明原样透传，另加一条引用"
        assert entry["gdt"][0]["ctq_ref"] == "g1"

    def test_size_and_gdt_can_come_from_one_record(self):
        spec, gaps = spec_from_ctq([_hole_ctq(extra={"gdt": FLATNESS})])
        assert gaps == []
        entry = spec["features"][0]
        assert entry["tolerance"] == {"upper": 0.05, "lower": -0.05}
        assert _stripped(entry["gdt"]) == FLATNESS
        assert entry["ctq_ref"] == "c1" and entry["gdt"][0]["ctq_ref"] == "c1"

    def test_a_datum_record_becomes_the_datum_scheme_without_needing_a_size(self):
        spec, gaps = spec_from_ctq([_ctq("d1", {
            "feature": "基准A面", "datum_id": "A", "drawing_feature": "TOP.hole_4"})])
        assert gaps == []
        assert spec["datums"] == [{"id": "A", "feature": "TOP.hole_4", "ctq_ref": "d1"}]
        assert spec["features"] == []

    def test_two_records_claiming_one_datum_letter_produce_neither(self):
        spec, gaps = spec_from_ctq([
            _ctq("d1", {"feature": "基准A", "datum_id": "A", "drawing_feature": "TOP.hole_1"}),
            _ctq("d2", {"feature": "基准A备份", "datum_id": "A",
                        "drawing_feature": "TOP.hole_2"})])
        assert spec.get("datums", []) == []
        assert [g["kind"] for g in gaps] == ["datum_id_conflict"]

    def test_a_record_declaring_neither_size_geometry_nor_datum_is_named(self):
        spec, gaps = spec_from_ctq([_ctq("e1", {"feature": "看一眼",
                                                "drawing_feature": "TOP.hole_1"})])
        assert spec["features"] == [] and spec.get("datums", []) == []
        assert [g["kind"] for g in gaps] == ["ctq_declares_nothing"]

    def test_generated_datums_resolve_for_a_position_frame(self):
        """基准来自需求侧记录，框才能解析基准字母——解析不到就该判未收口而不是画半截。"""
        spec, gaps = spec_from_ctq([
            _ctq("d1", {"feature": "基准A面", "datum_id": "A",
                        "drawing_feature": "TOP.hole_1"}),
            _ctq("g2", {"feature": "孔位置度", "drawing_feature": "TOP.hole_2",
                        "gdt": [{"characteristic": "position", "zone": 0.05,
                                 "diametral": True, "datums": ["A"]}]})])
        assert gaps == []
        assert "datums" in spec and len(spec["features"]) == 1

    def test_the_drawn_frame_records_which_ctq_it_answers(self, tmp_path):
        spec, gaps = spec_from_ctq([_ctq("g1", {
            "feature": "面轮廓要求", "drawing_feature": "TOP.hole_1", "gdt": FLATNESS})])
        assert gaps == []
        ev, _ = _generate(tmp_path, spec, name="frame")
        assert ev["gdt_issues"] == [] and ev["gdt_unmatched_features"] == []
        frames = [f for f in ev["gdt_frames"] if f["feature"] == "TOP.hole_1"]
        assert frames and frames[0]["ctq_ref"] == "g1", \
            "框要能回指它答的是哪条需求，否则门禁只能按名字猜"
        assert frames[0]["text"] == "⏥|0.02"

    def test_a_hand_written_frame_keeps_working_without_a_ref(self, tmp_path):
        ev, _ = _generate(tmp_path, {"features": [{"feature": "TOP.hole_1",
                                                   "gdt": FLATNESS}]}, name="noref")
        assert ev["gdt_frames"][0]["ctq_ref"] == ""

    def test_a_gdt_only_ctq_is_covered_by_the_frame_for_the_gate(self, tmp_path, db):
        """需求侧只声明形位（没有尺寸公差）时，画上去的框就是覆盖凭据。"""
        from aipd_os.cli.main import main
        from aipd_os.release_manifest import build_release_manifest

        rid = _seed(db, {"feature": "面轮廓要求", "drawing_feature": "TOP.hole_1",
                         "gdt": FLATNESS, "inspection_method": "平板+塞尺"})[0]
        spec_file = tmp_path / "gdt.json"
        assert main(["drawing", "spec", "--db", str(db), "--project", P,
                     "--out", str(spec_file)]) == 0
        _, dxf = _generate(tmp_path, json.loads(spec_file.read_text("utf-8")),
                           name="gdt_chain")
        path = tmp_path / "gdt-evidence.json"
        build_release_manifest(db_path=db, tenant_id=T, project_id=P, drawings=[dxf],
                               out_path=path)
        doc = json.loads(path.read_text("utf-8"))
        covered = [g for g in doc["gdt"] if g["ctq_record_id"] == rid]
        assert covered and covered[0]["covered_by"] == "feature_control_frame"
        proc = subprocess.run([sys.executable, str(GATE), "--manifest", str(path),
                               "--target", "C5"], capture_output=True, text=True)
        entry = next(c for c in json.loads(proc.stdout)["evidence_checks"]
                     if c["check"] == "gdt_covers_ctq")
        assert entry["passed"], entry["detail"]

    def test_a_gdt_only_ctq_with_no_frame_drawn_stays_uncovered(self, tmp_path, db):
        """另一极：声明了形位但图上没画框 ⇒ 不能算覆盖，门禁必须开火。"""
        from aipd_os.cli.main import main
        from aipd_os.release_manifest import build_release_manifest

        _seed(db, {"feature": "面轮廓要求", "drawing_feature": "TOP.hole_1",
                   "gdt": FLATNESS, "inspection_method": "平板+塞尺"})
        spec_file = tmp_path / "gdt2.json"
        assert main(["drawing", "spec", "--db", str(db), "--project", P,
                     "--out", str(spec_file)]) == 0
        _, dxf = _generate(tmp_path, name="no_frame")      # 不传 spec ⇒ 图上没有框
        path = tmp_path / "gdt2-evidence.json"
        build_release_manifest(db_path=db, tenant_id=T, project_id=P, drawings=[dxf],
                               out_path=path)
        doc = json.loads(path.read_text("utf-8"))
        assert doc["gdt"] == []
        proc = subprocess.run([sys.executable, str(GATE), "--manifest", str(path),
                               "--target", "C5"], capture_output=True, text=True)
        entry = next(c for c in json.loads(proc.stdout)["evidence_checks"]
                     if c["check"] == "gdt_covers_ctq")
        assert not entry["passed"], "只登记了要求、图上什么都没画，不能判已覆盖"


class TestDatumAndSizeOnOneRecord:
    def test_one_record_can_be_a_datum_and_a_size_requirement(self):
        """基准常常就是某个带公差的特征：同一条记录既登记字母又声明合格域时，两样都要出。"""
        spec, gaps = spec_from_ctq([_ctq("d2", {
            "feature": "基准A面（板宽）", "datum_id": "A",
            "drawing_feature": "TOP.overall_height",
            "nominal": 50.0, "lower_limit": 49.9, "upper_limit": 50.1})])
        assert gaps == []
        assert spec["datums"] == [{"id": "A", "feature": "TOP.overall_height",
                                   "ctq_ref": "d2"}]
        entry = spec["features"][0]
        assert entry["tolerance"] == {"upper": 0.1, "lower": -0.1}
        assert entry["ctq_ref"] == "d2"

    def test_a_pure_datum_ctq_is_covered_once_its_datum_role_is_used_by_a_frame(self,
                                                                                tmp_path):
        """基准字母被画上去的框引用时，它就已经上图了——但**引用它的框必须真存在**。"""
        spec, _ = spec_from_ctq([
            _ctq("d2", {"feature": "基准A面", "datum_id": "A",
                        "drawing_feature": "TOP.overall_height", "nominal": 50.0,
                        "lower_limit": 49.9, "upper_limit": 50.1}),
            _ctq("g3", {"feature": "孔位置度", "drawing_feature": "TOP.hole_2",
                        "gdt": [{"characteristic": "position", "zone": 0.05,
                                 "diametral": True, "datums": ["A"]}]}),
        ])
        ev, _ = _generate(tmp_path, spec, name="datum_used")
        frame = next(f for f in ev["gdt_frames"] if f["feature"] == "TOP.hole_2")
        assert frame["ctq_ref"] == "g3"
        assert [d["id"] for d in frame["datums"]] == ["A"]
        assert frame["datums"][0]["feature"] == "TOP.overall_height"


class TestOneRequirementCountsOnce:
    def test_a_record_covered_by_both_a_dimension_and_a_frame_counts_once(self,
                                                                         tmp_path, db):
        """同一条需求既标了尺寸公差又画了框 ⇒ 只算一条覆盖，且要说是按哪一半算的。

        重复计一条会让「覆盖了几条 CTQ」这种计数虚高——正是 `gdt_covers_ctq` 要防的反面。
        """
        from aipd_os.cli.main import main
        from aipd_os.release_manifest import build_release_manifest

        rid = _seed(db, {"feature": "孔（尺寸+位置度）", "drawing_feature": "TOP.hole_1",
                         "nominal": 6.0, "lower_limit": 5.95, "upper_limit": 6.05,
                         "gdt": FLATNESS, "inspection_method": "CMM"})[0]
        spec_file = tmp_path / "both.json"
        assert main(["drawing", "spec", "--db", str(db), "--project", P,
                     "--out", str(spec_file)]) == 0
        _, dxf = _generate(tmp_path, json.loads(spec_file.read_text("utf-8")), name="both")
        ev = json.loads(sidecar_path(dxf).read_text("utf-8"))
        assert ev["gdt_frames"], "前提：框真画上去了"
        path = tmp_path / "both-evidence.json"
        build_release_manifest(db_path=db, tenant_id=T, project_id=P, drawings=[dxf],
                               out_path=path)
        doc = json.loads(path.read_text("utf-8"))
        hits = [g for g in doc["gdt"] if g["ctq_record_id"] == rid]
        assert len(hits) == 1, f"一条需求被计了 {len(hits)} 次覆盖"
        assert hits[0]["covered_by"] == "dimension", \
            "尺寸与框同时成立时按尺寸记，框不重复计"
