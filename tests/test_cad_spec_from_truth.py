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


def _generate(tmp_path, spec, name="spec"):
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
