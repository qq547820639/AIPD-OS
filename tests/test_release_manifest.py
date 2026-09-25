"""发布就绪证据文档的**生产者**：门禁的 `gdt_covers_ctq` 不再靠手写 JSON 满足（F-EVID-01）。

本轮实测前提（不是推测）：`scripts/production_release_gate.py:256-286` 的
`gdt_covers_ctq` / `ctq_has_inspection` 早就写成 fail-closed，但全仓 `ctq`/`gdt` 两个数组
只出现在测试夹具里（`tests/test_production_release_gate.py:44`、`tests/test_cli.py:336`），
`src/` 内**零生产点**——即 C5/C6 的证据只能手抄，抄的人说什么就是什么。
旧审计 `docs/audit/v5.4/phase5-cad-audit.md:30` 也记着"仅校验，无生成"。

本文件钉住生产者 `aipd_os.release_manifest` 的五条口径：

1. **数字一律现取**：BOM 行数取自 BomStore、图纸数取自实际 DXF 证据、版本取自各自权威
   （BOM 头版本 / 图纸 revision / 模型内容哈希）。三者不一致时**如实报不一致**，
   绝不为过门禁把三个字段填成同一个串（那正是 `drawing_cad_same_revision` 要抓的东西）。
2. **`gdt` 只从图纸侧长出**：只有"真的画上去了公差 + 声明里显式 `ctq_ref` 指到某条 CTQ +
   数值与该 CTQ 的上下限一致"三条同时成立，才产出一条 gdt。CTQ 侧永远产不出 gdt，
   所以"有 CTQ 没画"必然判未覆盖——这是防空真通过的关键。
3. **不猜映射**：`ctq_ref` 指向不存在的记录、CTQ 缺 `metadata.feature`、偏差与 CTQ 不符，
   一律点名并把命令判未收口（exit 4），不做按名字模糊匹配（那是 F-REG-01 的装饰性接线）。
4. **门禁是真判据**：正反两向都直接跑 `scripts/production_release_gate.py` 读
   `evidence_checks`，不在测试里复刻它的逻辑。
5. **材料覆盖只从图上那些行现算**（`TestMaterialIsCoveredByTheEvidence`）：绑上了但
   BOM 行没填材料 ⇒ 点名球标并阻断；压根没绑上的行不重复计入；出图时没接 BOM ⇒ 写成
   盲区而不是 0。C6（`references/production-cad-deliverables.md`）要「材料与工艺」，
   所以「哪几行还没有材料」必须是文档里读得出的一格。
6. **门对这份文档的数组形状真的开火**（`TestNumbersAreMeasured` 末两条）：生产者写出的
   `evidence.drawings[]` 是数组，门禁的 `file_openable` 与逐键哈希核对都必须逐条读到它——
   图没了要报、内容被换过要报。数组进不了判据时，「所有引用文件可打开」是句空话。
"""
from __future__ import annotations

import json
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

from aipd_os.bom.models import BomLine
from aipd_os.bom.store import BomStore
from aipd_os.product_truth.models import TruthRecord
from aipd_os.product_truth.store import ProductTruthStore
from aipd_os.release_manifest import build_release_manifest

cadquery = pytest.importorskip("cadquery", reason="cad 为可选 extra")
pytest.importorskip("ezdxf", reason="DXF 写出依赖 ezdxf")

from aipd_os.cad.drawings2d import generate_drawing  # noqa: E402

GATE = Path(__file__).resolve().parents[1] / "scripts" / "production_release_gate.py"
_GATE_REQ = runpy.run_path(str(GATE))["REQ"]
T = "default"
P = "proj_rm"


def _plate():
    return (cadquery.Workplane("XY").box(100.0, 20.0, 10.0)
            .faces(">Z").workplane()
            .pushPoints([(-30.0, 0.0), (-10.0, 0.0), (10.0, 0.0), (30.0, 0.0)])
            .hole(6.0).solids().vals()[0])


def _drawing(tmp_path, *, spec=None, name="bracket", details=()):
    out = Path(tmp_path) / f"{name}.dxf"
    generate_drawing(_plate(), out, part_name="bracket", revision="A",
                     views=("TOP",), spec=spec, details=tuple(details))
    return out


def _seed_ctq(db_path, feature="hole_Ø6", *, limits=(5.95, 6.05), inspection="CMM",
              record_type="ctq", with_feature=True):
    store = ProductTruthStore(str(db_path), tenant_id=T, project_id=P)
    meta: dict = {}
    if with_feature:
        meta["feature"] = feature
    if limits is not None:
        meta["lower_limit"], meta["upper_limit"] = limits[0], limits[1]
    if inspection:
        meta["inspection_method"] = inspection
    return store.add(TruthRecord(record_type=record_type, content=f"CTQ {feature}",
                                 trust_level="verified", metadata=meta),
                     tenant_id=T, project_id=P)


def _seed_bom(db_path, lines=3, revision="2.1"):
    store = BomStore(str(Path(db_path).parent / "bom.db"))
    header = store.create_bom(T, P, "bom-1", revision=revision)
    for i in range(lines):
        store.add_line(BomLine(line_id="", bom_id=header.bom_id, tenant_id=T, project_id=P,
                               item=f"P-{i}", quantity=1.0, unit="ea"))
    return store.get_bom(T, P, header.bom_id)


def _manifest(tmp_path, db_path, drawings, **kw):
    """把 manifest 写到产物旁边：门禁按 manifest 所在目录解析相对路径。"""
    out = tmp_path / "release-evidence.json"
    payload = build_release_manifest(db_path=db_path, tenant_id=T, project_id=P,
                                     drawings=drawings, out_path=out, **kw)
    return out, payload


def _coverage(doc, idx):
    """取第 ``idx`` 张**图**自己的 BOM 行事实覆盖读数（材料 + 工艺）。

    缺哪几个球标一律逐图读：多张装配图的球标都从 1 开始，聚合清单会分不清是谁家的 1 号。
    """
    return doc["evidence"]["drawings"][idx]["bom_line_coverage"]


def _gate_verdict(manifest_path, check, target="C5"):
    """真跑门禁，取某一条 evidence_check 的判定（不在此复刻判据）。"""
    proc = subprocess.run(
        [sys.executable, str(GATE), "--manifest", str(manifest_path), "--target", target],
        capture_output=True, text=True)
    out = json.loads(proc.stdout)
    entry = next(c for c in out["evidence_checks"] if c["check"] == check)
    return entry["passed"], entry["detail"]


def _gate_missing(manifest_path, target):
    """真跑门禁，取逐键失败清单（`missing` 里才有 `C6:drawings: sha256 mismatch`）。"""
    proc = subprocess.run(
        [sys.executable, str(GATE), "--manifest", str(manifest_path), "--target", target],
        capture_output=True, text=True)
    return json.loads(proc.stdout)["missing"]


def _spec_with(ref):
    return {"features": [{"feature": "TOP.hole_1", "ctq_ref": ref,
                          "tolerance": {"upper": 0.05, "lower": -0.05}}]}


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "state.db"
    from aipd_os.state.db import AIPDStateDB

    state = AIPDStateDB(path)
    state.ensure_default_tenant()
    state.init_project(T, P, "release manifest 测试", "evidence")
    return path


class TestNumbersAreMeasured:
    def test_counts_and_versions_come_from_the_real_stores(self, tmp_path, db):
        bom = _seed_bom(db)
        dxf = _drawing(tmp_path)
        path, payload = _manifest(tmp_path, db, [dxf], bom_id=bom.bom_id)
        doc = json.loads(path.read_text("utf-8"))
        assert doc["bom_line_count"] == 3
        assert doc["drawing_count"] == 1
        assert doc["bom_version"] == bom.revision == "2.1"
        assert doc["drawings_version"] == "A"          # 图纸标题栏里的修订，不是 CLI 抄的
        assert payload["producer"]["version_parity"]["consistent"] is False   # 2.1 vs A
        assert doc["approval_status"] == "unapproved", "生产者不得替属主把审批状态写成 approved"
        assert payload["producer"]["model_version"]["source"] == "not_given"

    def test_drawing_file_is_referenced_with_a_matching_sha256(self, tmp_path, db):
        dxf = _drawing(tmp_path, name="hashed")
        path, payload = _manifest(tmp_path, db, [dxf])
        doc = json.loads(path.read_text("utf-8"))
        ref = doc["evidence"]["drawings"][0]
        import hashlib
        assert ref["path"] == "hashed.dxf"           # 相对 manifest 目录
        assert ref["sha256"] == hashlib.sha256(dxf.read_bytes()).hexdigest()
        ok, detail = _gate_verdict(path, "file_openable")
        assert ok, detail

    def test_a_deleted_drawing_in_a_produced_doc_is_not_openable(self, tmp_path, db):
        """真产物 + 真门禁：图没了，`file_openable` 必须点名。

        这两条在 `resolve_paths` 之前**过不了**：`evidence.drawings` 是数组，
        旧的 `resolve_path` 只认单值，数组整条跳过 ⇒ 图纸全丢、全被换过，
        门照样读成「所有引用文件可打开」。修的是那道判据认的形状，不是用例的写法。
        """
        dxf = _drawing(tmp_path, name="gone")
        path, _payload = _manifest(tmp_path, db, [dxf])
        assert _gate_verdict(path, "file_openable")[0] is True
        dxf.unlink()
        ok, detail = _gate_verdict(path, "file_openable")
        assert ok is False, "图没了仍被读成「所有引用文件可打开」"
        assert "gone.dxf" in detail

    def test_a_tampered_drawing_in_a_produced_doc_is_a_hash_mismatch(self, tmp_path, db):
        """出图之后被人改过：哈希核对必须落在 `drawings` 这一项上（C6 要求它有）。

        门是逐级停的：`achieved` 停在没满足的那一级，上面各级的逐键判据就不跑了。
        所以这里把**与本题无关**的 C0..C5 各键填成占位真值，让门真走到 C6 那一格——
        `drawings` 保持生产者写进去的那个数组，一条都不改。
        """
        dxf = _drawing(tmp_path, name="tamper")
        path, _payload = _manifest(tmp_path, db, [dxf])
        doc = json.loads(path.read_text("utf-8"))
        for level_keys in _GATE_REQ.values():
            for k in level_keys:
                if k != "drawings":
                    doc["evidence"].setdefault(k, True)
        path.write_text(json.dumps(doc), encoding="utf-8")

        assert not [x for x in _gate_missing(path, "C6") if "drawings" in x]
        dxf.write_text(dxf.read_text("utf-8") + "\n; 出图之后被人改过\n", encoding="utf-8")
        hits = [x for x in _gate_missing(path, "C6") if "drawings" in x]
        assert hits and any("sha256 mismatch" in x for x in hits), hits

    def test_model_solid_count_is_read_from_the_step_not_assumed(self, tmp_path, db):
        """``--model`` 分支必须真跑：两个不相连实体要数出 2，而不是写死 1 或折算成 0。"""
        base = cadquery.Workplane("XY").box(10.0, 10.0, 10.0)
        other = (cadquery.Workplane("XY")
                 .transformed(offset=cadquery.Vector(40.0, 0.0, 0.0))
                 .box(5.0, 5.0, 5.0))
        step = tmp_path / "two.step"
        cadquery.exporters.export(base.union(other), str(step), exportType="STEP")

        path, payload = _manifest(tmp_path, db, [], model=step)
        doc = json.loads(path.read_text("utf-8"))
        assert doc["model_part_count"] == 2
        assert not [i for i in payload["issues"] if i["kind"] == "model_unreadable"]
        assert doc["model_version"] == payload["producer"]["model_version"]["value"]


class TestGdtGrowsOnlyFromTheDrawing:
    def test_drawn_tolerance_linked_to_a_ctq_covers_it(self, tmp_path, db):
        """合规侧配对：画上了 + ref 指对 + 数值一致 + BOM 有行 ⇒ 门禁绿且零阻断。"""
        bom = _seed_bom(db, revision="A")     # 与图纸标题栏修订一致，走「全绿」那条路
        rec = _seed_ctq(db, "hole_Ø6", limits=(5.95, 6.05))
        dxf = _drawing(tmp_path, spec=_spec_with(rec), name="covered")
        path, payload = _manifest(tmp_path, db, [dxf], bom_id=bom.bom_id)
        doc = json.loads(path.read_text("utf-8"))
        assert [g["feature"] for g in doc["gdt"]] == ["hole_Ø6"]
        assert doc["ctq"][0]["feature"] == "hole_Ø6"
        assert payload["issues"] == [] and payload["ok"] is True
        assert payload["producer"]["version_parity"]["consistent"] is True
        passed, detail = _gate_verdict(path, "gdt_covers_ctq")
        assert passed, detail

    def test_ctq_without_a_drawn_tolerance_stays_uncovered(self, tmp_path, db):
        """必须开火的一侧：只登记 CTQ、图纸上没画公差 ⇒ 门禁判未覆盖，不得空真通过。"""
        _seed_ctq(db, "hole_Ø6")
        dxf = _drawing(tmp_path, name="bare")            # 无 spec ⇒ 无公差声明
        path, payload = _manifest(tmp_path, db, [dxf])
        doc = json.loads(path.read_text("utf-8"))
        assert doc["gdt"] == []
        passed, detail = _gate_verdict(path, "gdt_covers_ctq")
        assert not passed and "hole_Ø6" in detail

    def test_deviation_mismatch_between_drawing_and_ctq_is_named(self, tmp_path, db):
        """图纸写 ±0.05、CTQ 要求 ±0.5 ⇒ 不能算覆盖，且要点名是哪一处。"""
        rec = _seed_ctq(db, "hole_Ø6", limits=(5.5, 6.5))
        dxf = _drawing(tmp_path, spec=_spec_with(rec), name="dev_mismatch")
        path, payload = _manifest(tmp_path, db, [dxf])
        assert ("tolerance_mismatch", "TOP.hole_1", True) in {
            (i["kind"], i.get("feature"), i["blocking"]) for i in payload["issues"]}
        doc = json.loads(path.read_text("utf-8"))
        assert doc["gdt"] == []
        assert payload["blocking"] is True

    def test_a_detail_view_inheriting_the_tolerance_adds_no_second_coverage(
            self, tmp_path, db):
        """同一处测量在母视图与放大图上各印一次，只算**一条** gdt 覆盖。

        必须开火的一侧：`_collect_drawings` 若按「视图 × 尺寸」直计，画两张放大图就能
        把分子刷成 3 处，`gdt_covers_ctq` 的数从此与「真量了几处」脱钩——多印的标注
        不该换来多一条覆盖凭据。
        """
        bom = _seed_bom(db, revision="A")
        rec = _seed_ctq(db, "hole_Ø6", limits=(5.95, 6.05))
        dxf = _drawing(tmp_path, spec=_spec_with(rec), name="detail_cover",
                       details=("TOP@(-30,0)/12=2", "TOP@(30,0)/12=2"))
        evidence = json.loads(Path(dxf).with_suffix(".evidence.json").read_text("utf-8"))
        printed = [v["view"] for v in evidence["views"]
                   for d in v["dimensions"] if d.get("tolerance")]
        assert printed == ["TOP", "DETAIL_1"], "两处印刷是前提，没有它这条判据不打火"
        path, payload = _manifest(tmp_path, db, [dxf], bom_id=bom.bom_id)
        doc = json.loads(path.read_text("utf-8"))
        assert [g["covered_by"] for g in doc["gdt"]] == ["dimension"]
        assert payload["issues"] == [] and payload["ok"] is True
        passed, detail = _gate_verdict(path, "gdt_covers_ctq")
        assert passed, detail

    def test_dangling_ctq_ref_is_reported_not_guessed(self, tmp_path, db):
        _seed_ctq(db, "hole_Ø6")
        dxf = _drawing(tmp_path, spec=_spec_with("ctq-does-not-exist"), name="dangling")
        path, payload = _manifest(tmp_path, db, [dxf])
        kinds = {(i["kind"], i["detail"]) for i in payload["issues"]}
        assert any(k == "unknown_ctq_ref" for k, _ in kinds)
        assert payload["blocking"] is True
        doc = json.loads(path.read_text("utf-8"))
        assert doc["gdt"] == []

    def test_ctq_record_without_feature_is_named(self, tmp_path, db):
        """CTQ 没写 metadata.feature ⇒ 无法核对，必须点名而不是静默少一条 ctq。"""
        _seed_ctq(db, None, with_feature=False)
        dxf = _drawing(tmp_path, name="nofeature")
        path, payload = _manifest(tmp_path, db, [dxf])
        assert any(i["kind"] == "ctq_missing_feature" for i in payload["issues"])
        assert payload["blocking"] is True


class TestCliSurface:
    def test_cli_writes_the_manifest_next_to_the_artifacts(self, tmp_path, db):
        from aipd_os.cli.main import main

        bom = _seed_bom(db)
        rec = _seed_ctq(db, "hole_Ø6", limits=(5.95, 6.05))
        dxf = _drawing(tmp_path, spec=_spec_with(rec), name="cli")
        out = tmp_path / "rel.json"
        rc = main(["release", "manifest", "--db", str(db), "--project", P, "--bom",
                   bom.bom_id, "--drawing", str(dxf), "--out", str(out), "--json"])
        assert rc == 0
        doc = json.loads(out.read_text("utf-8"))
        assert doc["drawing_count"] == 1
        assert doc["runtime"] == "native_brep"
        assert [g["feature"] for g in doc["gdt"]] == ["hole_Ø6"]

    def test_cli_without_any_drawing_is_not_a_ready_release(self, tmp_path, db):
        """没图纸就没有 gdt，命令必须判未收口而不是产出一份"看起来齐了"的文档。"""
        from aipd_os.cli.main import main

        out = tmp_path / "rel2.json"
        rc = main(["release", "manifest", "--db", str(db), "--project", P,
                   "--out", str(out), "--json"])
        assert rc == 4
        payload = json.loads(out.read_text("utf-8"))
        assert payload["ok"] is False
        assert any(i["kind"] == "no_drawings" for i in payload["issues"])


class TestBomLibraryIsNotCreatedOnRead:
    """只读消费方不许把「没有 BOM 库」变成「有一个空 BOM 库」。

    ``BomStore(path)`` 会建库建表。改前 `_collect_bom` 直接构造它，于是跑一次发布证据
    就在 state.db 旁边留下一个空 bom.db，而报告说的是「BOM 里没有行」——
    「没接线」与「接了但是空的」在门禁里是两种处置，报告必须说清是哪一种。
    """

    def test_missing_bom_library_is_named_and_not_created(self, tmp_path, db):
        path, payload = _manifest(tmp_path, db, [])
        doc = json.loads(path.read_text("utf-8"))
        kinds = {i["kind"] for i in doc["issues"]}
        assert "bom_db_missing" in kinds, sorted(kinds)
        assert "no_bom_lines" not in kinds, "库都不在，不该报成「库里有但没有行」"
        assert not (tmp_path / "bom.db").exists(), "读不到就该报错，不该把库建出来"
        assert doc["blocking"], "缺 BOM 库必须是阻断项，否则门禁看不见它"


def _assy_drawing(tmp_path, bom_items=(("BRACKET-01", 4.0), ("PLATE-02", 2.0)),
                  parts=(("支架", "BRACKET-01"), ("压板", "PLATE-02")), name="assy",
                  revision="A", bind=True):
    """造一张**绑过 BOM** 的装配图（走真实入口，不手搓证据）。

    返回 (dxf 路径, 这张图绑的 bom_id)。bom_items 比 parts 多就是「BOM 有行图上没号」；
    每一项可写 ``(item, qty[, material[, process]])`` 或直接给 dict——`bind=False`
    则出图时不接 BOM。
    """
    import cadquery as cq

    from aipd_os.cad.assembly import generate_assembly_drawing

    store = BomStore(str(Path(tmp_path) / "bom.db"))
    header = store.create_bom(T, P, "装配 BOM", revision=revision)
    for spec in bom_items:
        fields = ({"item": spec[0], "quantity": spec[1], "unit": "pcs",
                   **({"material": spec[2]} if len(spec) > 2 else {}),
                   **({"process": spec[3]} if len(spec) > 3 else {})}
                  if not isinstance(spec, dict) else dict(spec))
        fields.setdefault("unit", "pcs")
        store.add_line(BomLine(line_id="", bom_id=header.bom_id, tenant_id=T,
                               project_id=P, **fields))
    steps = {}
    for i, letter in enumerate("ab"):
        box = cq.Workplane("XY").box(40.0, 20.0, 10.0 + i * 2).solids().vals()[0]
        path = Path(tmp_path) / f"{letter}.step"
        cq.exporters.export(box, str(path), exportType="STEP")
        steps[letter] = path
    entries = []
    for idx, (part, item) in enumerate(parts):
        entries.append({"name": part, "step": str(steps["a" if idx == 0 else "b"]),
                        "balloon": idx + 1, "offset": [0.0, 45.0 * idx, 0.0],
                        "bom_item": item})
    man = Path(tmp_path) / f"{name}.json"
    man.write_text(json.dumps({"parts": entries}, ensure_ascii=False), encoding="utf-8")
    out = Path(tmp_path) / f"{name}.dxf"
    generate_assembly_drawing(out, manifest=str(man), part_name=f"ASSY-{name}",
                              revision=revision, views=("TOP",),
                              bom_lines=store.list_lines(T, P, header.bom_id) if bind
                              else None)
    return out, header.bom_id


class TestAssemblyDrawingIsVisible:
    """C6 要的是「总装图 + 零件图」都在，而改前 manifest 只报 `drawing_count: 1`。

    更要紧的是：装配图证据里的 `assembly_issues`（球标↔BOM 没闭合）改前被整个忽略，
    一张漏了零件的装配图在发布证据里读起来是 `ok: true`。
    """

    def test_an_assembly_drawing_is_labelled_as_such(self, tmp_path, db):
        _seed_ctq(db)
        bom = _seed_bom(db)
        dxf, _ = _assy_drawing(tmp_path)
        path, payload = _manifest(tmp_path, db, [dxf], bom_id=bom.bom_id)
        doc = json.loads(path.read_text("utf-8"))
        kinds = [d.get("kind") for d in doc["evidence"]["drawings"]]
        assert kinds == ["assembly"], kinds
        assert doc["assembly_drawing_count"] == 1
        assert doc["part_drawing_count"] == 0

    def test_a_part_drawing_keeps_the_old_shape(self, tmp_path, db):
        """既有口径不许被顺手改掉：单件图仍是 kind=part、计数为 0 的装配侧。"""
        _seed_ctq(db)
        bom = _seed_bom(db, revision="A")
        dxf = _drawing(tmp_path)
        path, payload = _manifest(tmp_path, db, [dxf], bom_id=bom.bom_id)
        doc = json.loads(path.read_text("utf-8"))
        assert [d.get("kind") for d in doc["evidence"]["drawings"]] == ["part"]
        assert doc["assembly_drawing_count"] == 0
        assert doc["part_drawing_count"] == 1
        assert [i["kind"] for i in doc["issues"]] == []

    def test_a_leaked_bom_line_on_the_drawing_blocks_readiness(self, tmp_path, db):
        """BOM 有行而图上没号 ⇒ 这张装配图漏了零件，发布证据不能说齐。"""
        _seed_ctq(db)
        bom = _seed_bom(db)
        dxf, _ = _assy_drawing(tmp_path,
                               bom_items=(("BRACKET-01", 4.0), ("PLATE-02", 2.0),
                                          ("SCREW-77", 12.0)))
        path, payload = _manifest(tmp_path, db, [dxf], bom_id=bom.bom_id)
        doc = json.loads(path.read_text("utf-8"))
        hits = [i for i in doc["issues"] if i["kind"] == "assembly_unresolved"]
        assert hits, [i["kind"] for i in doc["issues"]]
        assert hits[0]["blocking"] is True
        assert doc["ok"] is False, "有待返工的装配图却 ok=true ⇒ 门禁这条判据是假的"
        assert "SCREW-77" in hits[0]["detail"] or "1" in hits[0]["detail"], hits[0]

    def test_an_assembly_bound_to_another_bom_is_named(self, tmp_path, db):
        """图上的数量来自 A 库，发布证据核的是 B 库 ⇒ 两边必须点名，不能各说各话。"""
        _seed_ctq(db)
        bom = _seed_bom(db)                       # 与图纸无关的另一张 BOM
        dxf, bound_to = _assy_drawing(tmp_path)
        assert bound_to != bom.bom_id
        path, payload = _manifest(tmp_path, db, [dxf], bom_id=bom.bom_id)
        doc = json.loads(path.read_text("utf-8"))
        kinds = [i["kind"] for i in doc["issues"]]
        assert "assembly_bom_mismatch" in kinds, kinds
        assert doc["ok"] is False

    def test_an_unbound_assembly_is_a_note_not_a_hold(self, tmp_path, db):
        """出图时没接 BOM 的装配图仍然成立（球标 + ITEM/PART），只是数量没核。

        告警不是未收口：本仓的口径是 blocking=False 不进 ok，但必须在文档里说清，
        否则「这张图的数量是哪来的」没人会被提醒去问。
        """
        import cadquery as cq

        from aipd_os.cad.assembly import generate_assembly_drawing

        _seed_ctq(db)
        bom = _seed_bom(db, revision="A")
        steps = {}
        for letter in "ab":
            box = cq.Workplane("XY").box(40.0, 20.0, 10.0).solids().vals()[0]
            path = tmp_path / f"{letter}.step"
            cq.exporters.export(box, str(path), exportType="STEP")
            steps[letter] = path
        man = tmp_path / "plain.json"
        man.write_text(json.dumps({"parts": [
            {"name": "支架", "step": str(steps["a"]), "balloon": 1, "offset": [0, 0, 0]},
            {"name": "压板", "step": str(steps["b"]), "balloon": 2,
             "offset": [0, 45, 0]}]}, ensure_ascii=False), encoding="utf-8")
        dxf = tmp_path / "plain.dxf"
        generate_assembly_drawing(dxf, manifest=str(man), part_name="ASSY-2",
                                  revision="A", views=("TOP",))
        path, payload = _manifest(tmp_path, db, [dxf], bom_id=bom.bom_id)
        doc = json.loads(path.read_text("utf-8"))
        kinds = [i["kind"] for i in doc["issues"]]
        assert "assembly_bom_unverified" in kinds, kinds
        assert all(not (i["kind"] == "assembly_bom_unverified" and i["blocking"])
                   for i in doc["issues"]), "没核数量不该把这张图判死"
        assert doc["ok"] is True


class TestMaterialIsCoveredByTheEvidence:
    """第 15 片：C6 要「材料与工艺」，所以发布证据必须说得出**哪几行还没有材料**。

    材料取值与数量同一权威（BOM 行）、同一绑定结果，所以这里不新增一条对应关系，
    只加一条覆盖判据。三件事分开钉：绑上了但没材料 ⇒ 点名球标并阻断；压根没绑上 ⇒
    已由 `assembly_unresolved` 判住，不再算成「缺材料」（同一件事报两遍会淹掉真信号）；
    出图时没接 BOM ⇒ 那是**盲区**，只能明说看不见，不能折成「0 行有材料」。
    """

    def test_a_bound_row_without_material_holds_the_release(self, tmp_path, db):
        _seed_ctq(db)
        dxf, bom_id = _assy_drawing(tmp_path)          # 两行都没填材料
        path, _ = _manifest(tmp_path, db, [dxf], bom_id=bom_id)
        doc = json.loads(path.read_text("utf-8"))
        hits = [i for i in doc["issues"] if i["kind"] == "material_missing"]
        assert hits, [i["kind"] for i in doc["issues"]]
        assert hits[0]["blocking"] is True
        assert doc["ok"] is False, "图纸一行的材料都说不出来，C6 不算交齐"
        cov = _coverage(doc, 0)
        assert (cov["bound_rows"], cov["with_material"]) == (2, 0), cov
        assert cov["missing_material"] == [1, 2], cov
        assert doc["bom_line_coverage"]["missing_material_drawings"] == 1

    def test_full_material_coverage_raises_no_material_issue(self, tmp_path, db):
        """第 15 片这条原本断「无任何问题、ok=true」；第 16 片起工艺那半也要求齐，
        所以这里改判成**两半分开**：材料齐就不许再报材料，缺的工艺单独点名。"""
        _seed_ctq(db)
        dxf, bom_id = _assy_drawing(
            tmp_path, bom_items=(("BRACKET-01", 4.0, "6061-T6"),
                                 ("PLATE-02", 2.0, "SUS304")))
        path, _ = _manifest(tmp_path, db, [dxf], bom_id=bom_id)
        doc = json.loads(path.read_text("utf-8"))
        assert [i["kind"] for i in doc["issues"]] == ["process_missing"], doc["issues"]
        cov = _coverage(doc, 0)
        assert (cov["bound_rows"], cov["with_material"]) == (2, 2), cov
        assert cov["missing_material"] == [] and cov["missing_process"] == [1, 2], cov
        assert doc["bom_line_coverage"]["missing_material_drawings"] == 0

    def test_the_counted_rows_are_the_ones_the_drawing_did_draw(self, tmp_path, db):
        """只有一行没材料时，球标号必须逐个点名——「有 1 行缺」这种话没法返工。

        缺材料的那一行故意放在**第一位**：这样「拿位置当计数」（`with_material = 已数到第几行`）
        这种写法会算成 2 行有材料，而真逐行计数才是 1 行。反过来放只能杀掉另一半变异。
        """
        _seed_ctq(db)
        dxf, bom_id = _assy_drawing(
            tmp_path, bom_items=(("BRACKET-01", 4.0), ("PLATE-02", 2.0, "SUS304")))
        path, _ = _manifest(tmp_path, db, [dxf], bom_id=bom_id)
        doc = json.loads(path.read_text("utf-8"))
        hits = [i for i in doc["issues"] if i["kind"] == "material_missing"]
        assert hits and "球标 [1]" in hits[0]["detail"], hits
        cov = _coverage(doc, 0)
        assert cov["missing_material"] == [1], cov
        assert (cov["bound_rows"], cov["with_material"]) == (2, 1), cov

    def test_a_row_that_never_bound_is_not_double_counted_as_missing_material(
            self, tmp_path, db):
        """没绑上的行由 `assembly_unresolved` 判；这里既不算「有材料」也不算「缺材料」。"""
        _seed_ctq(db)
        dxf, bom_id = _assy_drawing(
            tmp_path, bom_items=(("BRACKET-01", 4.0, "6061-T6"), ("OTHER", 1.0)),
            parts=(("支架", "BRACKET-01"), ("压板", "GHOST")))
        path, _ = _manifest(tmp_path, db, [dxf], bom_id=bom_id)
        doc = json.loads(path.read_text("utf-8"))
        kinds = [i["kind"] for i in doc["issues"]]
        assert "assembly_unresolved" in kinds, kinds
        assert "material_missing" not in kinds, kinds
        cov = _coverage(doc, 0)
        assert (cov["bound_rows"], cov["with_material"], cov["unbound_rows"]) == \
            (1, 1, 1), cov

    def test_a_drawing_that_never_saw_a_bom_is_a_blind_spot_not_a_zero(self, tmp_path, db):
        """没接 BOM 的装配图：材料覆盖**无法判**，只能把盲区写出来。

        把盲区折成 `with_material: 0` 会让「去 BOM 补材料」变成看似正确的返工方向，
        而真正缺的是出图时那次接线。
        """
        _seed_ctq(db)
        dxf, bom_id = _assy_drawing(tmp_path, bind=False)
        path, _ = _manifest(tmp_path, db, [dxf], bom_id=bom_id)
        doc = json.loads(path.read_text("utf-8"))
        cov = _coverage(doc, 0)
        assert cov["drawings_without_bom"] == 1, cov
        assert cov["bound_rows"] == 0 and cov["missing_material"] == [], cov
        assert doc["bom_line_coverage"]["bound_rows"] == 0
        assert "material_missing" not in [i["kind"] for i in doc["issues"]]

    def test_two_assembly_drawings_keep_their_own_row_numbers(self, tmp_path, db):
        """两张装配图的球标都从 1 开始：缺材料的清单必须各自留在各自那张图里。"""
        _seed_ctq(db)
        first, bom_id = _assy_drawing(tmp_path, bom_items=(("BRACKET-01", 4.0),),
                                      parts=(("支架", "BRACKET-01"),), name="one")
        second, _ = _assy_drawing(tmp_path, bom_items=(("PLATE-02", 2.0, "SUS304"),),
                                  parts=(("压板", "PLATE-02"),), name="two")
        path, _ = _manifest(tmp_path, db, [first, second], bom_id=bom_id)
        doc = json.loads(path.read_text("utf-8"))
        assert [_coverage(doc, i)["missing_material"] for i in (0, 1)] == [[1], []]
        agg = doc["bom_line_coverage"]
        assert (agg["bound_rows"], agg["with_material"]) == (2, 1), agg
        assert agg["missing_material_drawings"] == 1

    def test_a_package_without_assembly_drawings_says_nothing_about_material(
            self, tmp_path, db):
        """单件图没有明细表，也就没有「行」可判——字段缺席，不是 0。"""
        _seed_ctq(db)
        bom = _seed_bom(db, revision="A")
        dxf = _drawing(tmp_path)
        path, _ = _manifest(tmp_path, db, [dxf], bom_id=bom.bom_id)
        doc = json.loads(path.read_text("utf-8"))
        assert "bom_line_coverage" not in doc, doc.get("bom_line_coverage")
        assert "bom_line_coverage" not in doc["evidence"]["drawings"][0]


class TestProcessIsReportedApartFromMaterial:
    """C6 那句是「材料与工艺」，所以覆盖也得分两半报——合在一起就看不出还差哪一半。

    工艺值同样只来自绑上的那一行 ``BomLine.process``；两半各自独立判、各自点名，
    **不许互相顶**（材料空着却拿工艺填上，图纸那一格看起来有值而真正缺的事实被盖住）。
    """

    def test_a_bound_row_without_process_holds_the_release(self, tmp_path, db):
        _seed_ctq(db)
        dxf, bom_id = _assy_drawing(
            tmp_path, bom_items=(("BRACKET-01", 4.0, "6061-T6", "CNC 铣削"),
                                 ("PLATE-02", 2.0, "SUS304")))
        path, _ = _manifest(tmp_path, db, [dxf], bom_id=bom_id)
        doc = json.loads(path.read_text("utf-8"))
        kinds = [i["kind"] for i in doc["issues"]]
        assert "process_missing" in kinds, kinds
        assert "material_missing" not in kinds, kinds
        hits = [i for i in doc["issues"] if i["kind"] == "process_missing"]
        assert hits[0]["blocking"] is True and "球标 [2]" in hits[0]["detail"], hits
        cov = _coverage(doc, 0)
        assert (cov["bound_rows"], cov["with_material"], cov["with_process"]) == \
            (2, 2, 1), cov
        assert cov["missing_process"] == [2] and cov["missing_material"] == [], cov
        assert doc["ok"] is False

    def test_the_two_halves_are_named_separately(self, tmp_path, db):
        """一行缺材料、另一行缺工艺 ⇒ 两条问题各点各的球标，不合成一条「信息不全」。"""
        _seed_ctq(db)
        dxf, bom_id = _assy_drawing(
            tmp_path, bom_items=(("BRACKET-01", 4.0, None, "CNC 铣削"),
                                 ("PLATE-02", 2.0, "SUS304")))
        path, _ = _manifest(tmp_path, db, [dxf], bom_id=bom_id)
        doc = json.loads(path.read_text("utf-8"))
        by_kind = {i["kind"]: i["detail"] for i in doc["issues"]}
        assert set(by_kind) == {"material_missing", "process_missing"}, by_kind
        assert "球标 [1]" in by_kind["material_missing"]
        assert "球标 [2]" in by_kind["process_missing"]
        cov = _coverage(doc, 0)
        assert (cov["missing_material"], cov["missing_process"]) == ([1], [2]), cov

    def test_full_coverage_of_both_halves_leaves_no_issue(self, tmp_path, db):
        _seed_ctq(db)
        dxf, bom_id = _assy_drawing(
            tmp_path, bom_items=(("BRACKET-01", 4.0, "6061-T6", "CNC 铣削"),
                                 ("PLATE-02", 2.0, "SUS304", "激光切割")))
        path, _ = _manifest(tmp_path, db, [dxf], bom_id=bom_id)
        doc = json.loads(path.read_text("utf-8"))
        assert [i["kind"] for i in doc["issues"]] == []
        agg = doc["bom_line_coverage"]
        assert (agg["bound_rows"], agg["with_material"], agg["with_process"]) == \
            (2, 2, 2), agg
        assert doc["ok"] is True

    def test_a_row_that_never_bound_is_not_counted_against_process(self, tmp_path, db):
        _seed_ctq(db)
        dxf, bom_id = _assy_drawing(
            tmp_path, bom_items=(("BRACKET-01", 4.0, "6061-T6", "CNC 铣削"),
                                 ("OTHER", 1.0)),
            parts=(("支架", "BRACKET-01"), ("压板", "GHOST")))
        path, _ = _manifest(tmp_path, db, [dxf], bom_id=bom_id)
        doc = json.loads(path.read_text("utf-8"))
        kinds = [i["kind"] for i in doc["issues"]]
        assert "assembly_unresolved" in kinds and "process_missing" not in kinds, kinds
        cov = _coverage(doc, 0)
        assert (cov["bound_rows"], cov["with_process"], cov["unbound_rows"]) == \
            (1, 1, 1), cov

    def test_the_blind_spot_covers_both_halves(self, tmp_path, db):
        """没接 BOM 的图：材料与工艺**都无法判**，同一格盲区说一次，不折成两个 0。"""
        _seed_ctq(db)
        dxf, bom_id = _assy_drawing(tmp_path, bind=False)
        path, _ = _manifest(tmp_path, db, [dxf], bom_id=bom_id)
        doc = json.loads(path.read_text("utf-8"))
        cov = _coverage(doc, 0)
        assert cov["drawings_without_bom"] == 1
        assert (cov["missing_material"], cov["missing_process"]) == ([], []), cov
        assert "process_missing" not in [i["kind"] for i in doc["issues"]]


    def test_the_process_count_is_per_row_not_positional(self, tmp_path, db):
        """混合样本故意「缺的那行在前、有的那行在后」：拿位置当计数的写法在这里算错。

        上一轮 M10 就是这么幸存的（见 CAD_ASSEMBLY_MATERIAL 审计 §六），所以这一片
        材料与工艺各配一条这种排列的用例。
        """
        _seed_ctq(db)
        dxf, bom_id = _assy_drawing(
            tmp_path, bom_items=(("BRACKET-01", 4.0, "6061-T6"),
                                 ("PLATE-02", 2.0, "SUS304", "激光切割")))
        path, _ = _manifest(tmp_path, db, [dxf], bom_id=bom_id)
        doc = json.loads(path.read_text("utf-8"))
        cov = _coverage(doc, 0)
        assert (cov["bound_rows"], cov["with_material"], cov["with_process"]) == \
            (2, 2, 1), cov
        assert cov["missing_process"] == [1] and cov["missing_material"] == [], cov

    def test_a_process_value_never_lands_in_the_material_cell(self, tmp_path, db):
        """取值不互顶：整张图只有工艺时，材料那一半照样得判缺。"""
        _seed_ctq(db)
        dxf, bom_id = _assy_drawing(
            tmp_path, bom_items=(("BRACKET-01", 4.0, None, "CNC 铣削"),
                                 ("PLATE-02", 2.0, None, "激光切割")))
        path, _ = _manifest(tmp_path, db, [dxf], bom_id=bom_id)
        doc = json.loads(path.read_text("utf-8"))
        kinds = [i["kind"] for i in doc["issues"]]
        assert kinds == ["material_missing"], kinds
        cov = _coverage(doc, 0)
        assert (cov["with_material"], cov["with_process"]) == (0, 2), cov


class TestExplodedViewIsJudged:
    """爆炸视图的第三条判据：摆开了就得说清谁从哪儿来（证据里要有连接线）。

    生产者不会产出不一致的证据，但 sidecar 可能是**手改的或旧版本留下的**——
    门禁吃的是证据文件，所以这条必须能红（变异电池里它就是靠改 sidecar 验的）。
    """

    def _exploded(self, tmp_path, name="blown"):
        import cadquery as cq

        from aipd_os.cad.assembly import generate_assembly_drawing

        steps = {}
        for letter in "ab":
            box = cq.Workplane("XY").box(40.0, 20.0, 10.0).solids().vals()[0]
            steps[letter] = tmp_path / f"{letter}.step"
            cq.exporters.export(box, str(steps[letter]), exportType="STEP")
        man = tmp_path / f"{name}.json"
        man.write_text(json.dumps({"parts": [
            {"name": "支架", "step": str(steps["a"]), "balloon": 1,
             "offset": [0, 0, 0], "explode": [60, 0, 0], "bom_item": "BRACKET-01"},
            {"name": "压板", "step": str(steps["b"]), "balloon": 2,
             "offset": [0, 0, 5], "explode": [-60, 0, 0], "bom_item": "PLATE-02"}]},
            ensure_ascii=False), encoding="utf-8")
        out = tmp_path / f"{name}.dxf"
        bom = tmp_path / "bom.db"
        store = BomStore(str(bom))
        header = store.create_bom(T, P, "爆炸 BOM", revision="A")
        for item in ("BRACKET-01", "PLATE-02"):
            store.add_line(BomLine(line_id="", bom_id=header.bom_id, tenant_id=T,
                                   project_id=P, item=item, quantity=2.0, unit="pcs",
                                   material="6061-T6", process="CNC 铣削"))
        generate_assembly_drawing(out, manifest=str(man), part_name=f"ASSY-{name}",
                                  revision="A", views=("TOP",), explode=True,
                                  bom_lines=store.list_lines(T, P, header.bom_id))
        return out, header.bom_id

    def test_a_consistent_exploded_drawing_raises_nothing(self, tmp_path, db):
        _seed_ctq(db)
        dxf, bom_id = self._exploded(tmp_path)
        path, _ = _manifest(tmp_path, db, [dxf], bom_id=bom_id)
        doc = json.loads(path.read_text("utf-8"))
        assert [i["kind"] for i in doc["issues"]] == [], doc["issues"]
        assert doc["ok"] is True

    def test_connectors_stripped_from_the_evidence_is_a_hold(self, tmp_path, db):
        """手改/旧 sidecar 会留下「说了爆炸却没有连线」的证据——这条判据就是为它建的。"""
        _seed_ctq(db)
        dxf, bom_id = self._exploded(tmp_path, name="stripped")
        sidecar = dxf.with_suffix(".evidence.json")
        ev = json.loads(sidecar.read_text("utf-8"))
        assert ev["views"][0]["connectors"], "前提：真出的图每条连接都在"
        ev["views"][0]["connectors"] = []
        sidecar.write_text(json.dumps(ev, ensure_ascii=False), encoding="utf-8")
        path, _ = _manifest(tmp_path, db, [dxf], bom_id=bom_id)
        doc = json.loads(path.read_text("utf-8"))
        hits = [i for i in doc["issues"] if i["kind"] == "explode_unconnected"]
        assert hits and hits[0]["blocking"] is True, doc["issues"]
        # 视图名要真在文案里：证据里那个键叫 view 而不是 name，取错键只会印出 None，
        # 读的人就不知道是一张图上的哪个视图没连线。
        assert "ASSY_TOP" in hits[0]["detail"], hits[0]["detail"]
        assert doc["ok"] is False

    def test_a_view_that_is_not_exploded_is_not_judged(self, tmp_path, db):
        """没爆炸就不该被爆炸判据管：没有 connectors 这一项缺席才是正常形状。"""
        _seed_ctq(db)
        dxf, bom_id = _assy_drawing(tmp_path, name="flat")
        path, _ = _manifest(tmp_path, db, [dxf], bom_id=bom_id)
        doc = json.loads(path.read_text("utf-8"))
        kinds = [i["kind"] for i in doc["issues"]]
        assert "explode_unconnected" not in kinds, kinds
        assert doc["evidence"]["drawings"][0]["kind"] == "assembly"
