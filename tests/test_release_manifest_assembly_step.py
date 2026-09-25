"""总装 STEP 接进发布就绪证据（C6「总装/单件STEP」的总装那一半，F-EVID-02 第 22 片）。

契约给的理由：`references/production-cad-deliverables.md:4`——
「STEP 存在、网格闭合或快照好看均不能单独证明生产可用」。所以这一格不能只写
「有个 .step、哈希对得上」（那是门禁 `step_assemblies` 已经在做的事），必须把
**生产者回读核对过的那些事实**搬进来，而且**重算一遍**：侧车自己声明的数字互相对不上，
就是这份侧车在说假话，一律点名并阻断，不替它盖章。

三条口径：

1. **没交就不写这一格**：``--assembly-step`` 不给 ⇒ `step_assemblies` 与 `assembly_model`
   两个键都不出现（写一个空数组会让门把「没做」读成「做了但是空的」）。
2. **侧车的话要重算**：每件的两个体积数相减、每件的源实体数相加对上它报的 `solid_count`、
   侧车写的 `document_sha256` 对一眼眼前这份文件。第 20 片刻意**不留** `volume_match`
   那种写死的布尔，这里也就没法抄它——只能拿两个数自己减。
3. **图与模只在一对一时才配**：一张装配图对一份总装 STEP 才比球标集合；多张一律记
   `ambiguous_pairing` 不判（按名字猜配对是 F-REG-01 那条装饰性接线的老路）。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from aipd_os.cli import main as cli_main
from aipd_os.release_manifest import build_release_manifest

cadquery = pytest.importorskip("cadquery", reason="CAD 内核为可选 extra")
pytest.importorskip("ezdxf", reason="装配图侧车由 DXF 产出")

from aipd_os.bom.models import BomLine  # noqa: E402
from aipd_os.bom.store import BomStore, bom_store_path  # noqa: E402
from aipd_os.cad.assembly import export_assembly_step, generate_assembly_drawing  # noqa: E402
from aipd_os.product_truth.models import TruthRecord  # noqa: E402
from aipd_os.product_truth.store import ProductTruthStore  # noqa: E402

T = "default"
P = "proj_assy_step"
PARTS = [{"name": "支架", "step": "bracket.step", "balloon": 1, "offset": [0, 0, 0],
          "bom_item": "支架"},
         {"name": "压板", "step": "plate.step", "balloon": 2, "offset": [0, 25, 12],
          "bom_item": "压板"}]


def _db(tmp_path: Path) -> tuple[Path, str]:
    """状态库 + 一条 active CTQ + 同目录的 bom.db：让基线本身是「可就绪」的。

    返回 ``(state.db, 生成的 bom_id)``——``create_bom`` 的第三个参数是**名字**，
    id 是生成的（写成 ``bom-1`` 会让读的一方找不到那一版 BOM，报成「没有行」）。
    """
    from aipd_os.state.db import AIPDStateDB

    path = tmp_path / "state.db"
    state = AIPDStateDB(str(path))
    state.ensure_default_tenant()
    state.init_project(T, P, "总装 STEP 证据", "evidence")
    ProductTruthStore(str(path), tenant_id=T, project_id=P).add(
        TruthRecord(record_type="ctq", content="CTQ hole", trust_level="verified",
                    metadata={"feature": "hole", "lower_limit": 5.95, "upper_limit": 6.05,
                              "inspection_method": "CMM"}), tenant_id=T, project_id=P)
    store = BomStore(bom_store_path(path))
    header = store.create_bom(T, P, "bom-1", revision="A")
    for one in PARTS:
        store.add_line(BomLine(line_id="", bom_id=header.bom_id, tenant_id=T, project_id=P,
                               item=str(one["bom_item"]), quantity=1.0, unit="ea",
                               material="6061", process="CNC"))
    return path, header.bom_id


def _write_manifest(tmp_path: Path, name: str, parts) -> Path:
    out = tmp_path / f"{name}.json"
    out.write_text(json.dumps({"parts": parts}, ensure_ascii=False), encoding="utf-8")
    return out


def _part(tmp_path: Path, name: str, filename: str, box, shift: float) -> Path:
    src = tmp_path / filename
    wp = (cadquery.Workplane("XY").box(*box)
          .faces(">Z").workplane().pushPoints([(0.0, 0.0)]).hole(6.0))
    wp = wp.translate(cadquery.Vector(shift, 0, 0))
    cadquery.exporters.export(wp.val(), str(src))
    return src


@pytest.fixture()
def assy(tmp_path: Path):
    """一份真总装 STEP + 真侧车（走第 20 片的导出与写后回读），清单留在 assy.json。"""
    _part(tmp_path, "bracket", "bracket.step", (20, 8, 20), 0.0)
    _part(tmp_path, "plate", "plate.step", (15, 6, 12), 40.0)
    _write_manifest(tmp_path, "assy", PARTS)
    out = tmp_path / "assy.step"
    export_assembly_step(out, manifest=str(tmp_path / "assy.json"), part_name="ASSY-1")
    return out


def _sidecar(step: Path) -> Path:
    return step.with_suffix(".evidence.json")


def _rewrite(step: Path, **changes) -> None:
    """改侧车里的顶层字段（模拟一份自相矛盾的证据）。"""
    side = _sidecar(step)
    data = json.loads(side.read_text(encoding="utf-8"))
    data.update(changes)
    side.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _patch_part(step: Path, index: int, **changes) -> None:
    side = _sidecar(step)
    data = json.loads(side.read_text(encoding="utf-8"))
    data["parts"][index].update(changes)
    side.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _assy_drawing(tmp_path: Path, manifest_name: str, drawing_name: str) -> Path:
    dxf = tmp_path / f"{drawing_name}.dxf"
    generate_assembly_drawing(dxf, manifest=str(tmp_path / f"{manifest_name}.json"),
                              part_name="ASSY-1", views=("FRONT",))
    return dxf


def _manifest_for(tmp_path, step=None, drawings=()):
    """``aipd release manifest`` 把文档写在产物旁边，门禁按它所在目录解析相对路径。"""
    db, bom_id = _db(tmp_path)
    out = tmp_path / "release-evidence.json"
    payload = build_release_manifest(db_path=db, tenant_id=T, project_id=P,
                                     drawings=list(drawings), bom_id=bom_id,
                                     assembly_step=step, out_path=out)
    return out, payload


def _kinds(payload, prefix: str = ""):
    return {i["kind"] for i in payload["issues"]
            if i["blocking"] and i["kind"].startswith(prefix)}


class TestTheCellGrowsOnlyWhenGiven:
    def test_no_argument_writes_neither_key(self, tmp_path):
        _out, payload = _manifest_for(tmp_path)
        assert "step_assemblies" not in payload and "assembly_model" not in payload

    def test_a_missing_file_is_named_and_writes_nothing(self, tmp_path):
        _out, payload = _manifest_for(tmp_path, step=tmp_path / "nope.step")
        assert "assembly_step_missing" in _kinds(payload)
        assert payload["ok"] is False
        assert "step_assemblies" not in payload

    def test_a_step_without_a_sidecar_is_a_blocking_blind_spot(self, tmp_path):
        step = tmp_path / "bare.step"
        step.write_text("ISO-10303-21;\n", encoding="utf-8")
        _out, payload = _manifest_for(tmp_path, step=step)
        assert "assembly_step_evidence_missing" in _kinds(payload)
        # 引用照写（门禁那侧还要核它在不在），但事实一格不编
        assert payload["step_assemblies"][0]["path"].endswith("bare.step")
        assert "assembly_model" not in payload

    def test_a_sidecar_without_counts_is_named_not_folded_to_zero(self, tmp_path, assy):
        _rewrite(assy, parts=None, declared_part_count=None)
        _out, payload = _manifest_for(tmp_path, step=assy)
        assert "assembly_step_evidence_incomplete" in _kinds(payload)
        assert "assembly_model" not in payload


class TestFactsComeFromTheSidecar:
    def test_the_reference_is_ready_for_the_gate_file_key(self, tmp_path, assy):
        import hashlib

        _out, payload = _manifest_for(tmp_path, step=assy)
        ref = payload["step_assemblies"][0]
        assert ref["kind"] == "assembly"
        assert ref["sha256"] == hashlib.sha256(assy.read_bytes()).hexdigest()

    def test_each_part_carries_placement_and_both_volume_numbers(self, tmp_path, assy):
        _out, payload = _manifest_for(tmp_path, step=assy)
        model = payload["assembly_model"]
        assert [p["balloon"] for p in model["parts"]] == [1, 2]
        assert model["parts"][1]["placement"] == [0.0, 25.0, 12.0]
        for one in model["parts"]:
            assert one["read_back_volume_mm3"] == pytest.approx(one["volume_mm3"], abs=1e-6)

    def test_the_name_readability_boundary_is_carried_verbatim(self, tmp_path, assy):
        _out, payload = _manifest_for(tmp_path, step=assy)
        read = payload["assembly_model"]["name_readability"]
        assert read["readable"] is False
        assert "mojibake" in read["reason"] or "单字节" in read["reason"]

    def test_what_it_does_not_carry_is_not_emptied(self, tmp_path, assy):
        _out, payload = _manifest_for(tmp_path, step=assy)
        assert payload["assembly_model"]["not_covered"], "「没做的事」不能在这一格被抹平"

    def test_a_consistent_sidecar_adds_no_blocking_issue(self, tmp_path, assy):
        _out, payload = _manifest_for(tmp_path, step=assy)
        assert not _kinds(payload, "assembly"), payload["issues"]


class TestSelfDisagreementIsRefused:
    def test_a_sidecar_about_a_different_file_is_named(self, tmp_path, assy):
        assy.write_bytes(assy.read_bytes() + b"\n; changed after export\n")
        _out, payload = _manifest_for(tmp_path, step=assy)
        assert "assembly_step_hash_mismatch" in _kinds(payload)

    def test_a_sidecar_without_its_own_hash_is_the_same_kind_of_failure(self, tmp_path, assy):
        """字段缺失与字段不等是同一件事：没有可对的哈希，就不知道它说的是哪份文件。"""
        side = _sidecar(assy)
        data = json.loads(side.read_text(encoding="utf-8"))
        del data["document_sha256"]
        side.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        _out, payload = _manifest_for(tmp_path, step=assy)
        assert "assembly_step_hash_mismatch" in _kinds(payload)

    def test_a_part_with_no_read_back_solid_is_refused(self, tmp_path, assy):
        _patch_part(assy, 1, read_back_solid_count=0)
        _out, payload = _manifest_for(tmp_path, step=assy)
        assert "assembly_model_disagrees_with_itself" in _kinds(payload)

    def test_a_part_whose_two_volumes_disagree_is_refused(self, tmp_path, assy):
        _patch_part(assy, 0, read_back_volume_mm3=1234.5)
        _out, payload = _manifest_for(tmp_path, step=assy)
        assert "assembly_model_disagrees_with_itself" in _kinds(payload)
        detail = " ".join(i["detail"] for i in payload["issues"]
                          if i["kind"] == "assembly_model_disagrees_with_itself")
        assert "支架" in detail, "点名要点到是哪一件，不然读者还得自己去对表"

    def test_solid_count_not_equal_to_the_sum_of_parts_is_refused(self, tmp_path, assy):
        _rewrite(assy, solid_count=1)
        _out, payload = _manifest_for(tmp_path, step=assy)
        assert "assembly_model_solid_count_disagrees" in _kinds(payload)

    def test_declared_part_count_not_matching_the_rows_is_refused(self, tmp_path, assy):
        _rewrite(assy, declared_part_count=5)
        _out, payload = _manifest_for(tmp_path, step=assy)
        assert "assembly_model_count_disagrees" in _kinds(payload)

    def test_a_different_verification_method_is_not_accepted(self, tmp_path, assy):
        _rewrite(assy, verification="presence_only")
        _out, payload = _manifest_for(tmp_path, step=assy)
        assert "assembly_step_unverified" in _kinds(payload)


class TestDrawingCrossCheck:
    def test_matching_balloon_sets_are_recorded_as_compared(self, tmp_path, assy):
        dxf = _assy_drawing(tmp_path, "assy", "view")
        _out, payload = _manifest_for(tmp_path, step=assy, drawings=[dxf])
        check = payload["assembly_model"]["drawing_check"]
        assert check["status"] == "compared" and check["agree"] is True
        assert not _kinds(payload, "assembly_model")

    def test_a_balloon_only_on_the_drawing_blocks(self, tmp_path, assy):
        _write_manifest(tmp_path, "assy3", PARTS + [
            {"name": "螺钉", "step": "plate.step", "balloon": 3, "offset": [0, 0, 20]}])
        dxf = _assy_drawing(tmp_path, "assy3", "view3")
        _out, payload = _manifest_for(tmp_path, step=assy, drawings=[dxf])
        assert "assembly_model_drawing_disagree" in _kinds(payload)
        detail = "".join(i["detail"] for i in payload["issues"])
        assert "[3]" in detail, "图上多出来的那个号必须点名"

    def test_a_renamed_balloon_blocks(self, tmp_path, assy):
        _write_manifest(tmp_path, "assy_renamed", [
            dict(PARTS[0], name="支座"), dict(PARTS[1])])
        dxf = _assy_drawing(tmp_path, "assy_renamed", "viewr")
        _out, payload = _manifest_for(tmp_path, step=assy, drawings=[dxf])
        detail = "".join(i["detail"] for i in payload["issues"])
        assert "assembly_model_drawing_disagree" in _kinds(payload) and "支座" in detail

    def test_two_assembly_drawings_are_not_guessed_at(self, tmp_path, assy):
        d1 = _assy_drawing(tmp_path, "assy", "view_a")
        d2 = _assy_drawing(tmp_path, "assy", "view_b")
        _out, payload = _manifest_for(tmp_path, step=assy, drawings=[d1, d2])
        assert payload["assembly_model"]["drawing_check"]["status"] == "ambiguous_pairing"
        assert "assembly_model_drawing_disagree" not in _kinds(payload)

    def test_no_assembly_drawing_is_a_blind_spot_not_a_failure(self, tmp_path, assy):
        _out, payload = _manifest_for(tmp_path, step=assy)
        check = payload["assembly_model"]["drawing_check"]
        assert check["status"] == "no_assembly_drawing"
        assert not _kinds(payload, "assembly_model"), "没图是盲区，不该判成不成立"


class TestCliSurface:
    """CLI 面：基线得真能就绪（有图、有 BOM 行、有 CTQ），才谈得上「0 变 4」。

    夹具里踩过一次：``create_bom`` 第三个参数是**名字**，bom_id 是生成的，
    拿字面量 ``bom-1`` 去 ``--bom`` 会让读的一方找不到那一版 BOM，
    报成 ``no_bom_lines``——基线就永远不 ok，正反向断言全成空话。
    """

    def test_the_flag_lands_the_cell_and_adds_no_blocking_issue(self, tmp_path, assy):
        db, bom_id = _db(tmp_path)
        dxf = _assy_drawing(tmp_path, "assy", "view")
        base = cli_main.main(["release", "manifest", "--db", str(db), "--project", P,
                              "--bom", bom_id, "--drawing", str(dxf),
                              "--out", str(tmp_path / "e0.json")])
        assert base == 0, json.loads((tmp_path / "e0.json")
                                     .read_text(encoding="utf-8"))["issues"]
        out = tmp_path / "e1.json"
        rc = cli_main.main(["release", "manifest", "--db", str(db), "--project", P,
                            "--bom", bom_id, "--drawing", str(dxf),
                            "--assembly-step", str(assy), "--out", str(out)])
        assert rc == 0, "一份自洽的总装 STEP 不该让就绪结论变差"
        doc = json.loads(out.read_text(encoding="utf-8"))
        assert doc["step_assemblies"][0]["path"] == assy.name
        assert doc["assembly_model"]["declared_part_count"] == 2
        assert doc["assembly_model"]["drawing_check"]["status"] == "compared"

    def test_a_disagreeing_sidecar_turns_a_ready_pack_red(self, tmp_path, assy):
        db, bom_id = _db(tmp_path)
        dxf = _assy_drawing(tmp_path, "assy", "view")
        _patch_part(assy, 1, read_back_volume_mm3=9999.0)
        out = tmp_path / "e4.json"
        rc = cli_main.main(["release", "manifest", "--db", str(db), "--project", P,
                            "--bom", bom_id, "--drawing", str(dxf),
                            "--assembly-step", str(assy), "--out", str(out)])
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert "assembly_model_disagrees_with_itself" in _kinds(payload)
        assert payload["ok"] is False and rc == 4, \
            "侧车自相矛盾还判就绪，就是拿一个文件的存在冒充生产可用"
