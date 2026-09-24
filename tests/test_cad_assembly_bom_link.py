"""球标 ↔ BOM 行交叉核对（F-DRAW-01 第 13 片，第 12 片明确欠下的那一半）。

第 12 片出的装配图只有 ITEM/PART 两列，并在行内写明「数量权威在 BOM，本轮未接线」。
本片把那条接线做成**可机器核的对应关系**，同时守住一条本仓已经定了的规矩：

**对应关系由作者声明，不按名字自动映射。** 全仓从 `drawing spec`（CTQ↔图纸特征）
到 GD&T 框解析都是这个形状，理由是一样的：名字相似不等于同一个东西，自动映射会
让图纸声称一个作者从没说过的对应。所以 manifest 里必须显式写 ``bom_item``，
只写零件名而没写 ``bom_item`` 的零件**不会**因为 BOM 里恰好有同名行就算对上。

数量与单位的权威在 BOM 行上：manifest 里就算写了数量也不算数（用例专门钉这一条）。
两头都要闭合：图纸上有号但 BOM 找不到 ⇒ 未收口；BOM 有行但图上没号 ⇒ 也是未收口
（一张漏了零件的装配图比一张丑的装配图危险得多）。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

cadquery = pytest.importorskip("cadquery", reason="cad 为可选 extra")
pytest.importorskip("ezdxf", reason="DXF 输出依赖 ezdxf")

from aipd_os.bom.models import BomLine  # noqa: E402
from aipd_os.bom.store import BomStore  # noqa: E402
from aipd_os.cad.assembly import (  # noqa: E402
    bind_bom,
    generate_assembly_drawing,
    load_assembly_parts,
    parse_assembly_manifest,
)

TENANT = "default"
PROJECT = "assy-proj"

def _write_step(tmp_path: Path, name: str, shape) -> Path:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    cadquery.exporters.export(shape, str(path), exportType="STEP")
    return path

def _parts(tmp_path) -> tuple[Path, Path]:
    box_a = cadquery.Workplane("XY").box(40.0, 20.0, 10.0)
    solid_a = box_a.faces(">Z").workplane().hole(6.0).solids().vals()[0]
    a = _write_step(tmp_path, "a.step", solid_a)
    b = _write_step(tmp_path, "b.step",
                    cadquery.Workplane("XY").box(20.0, 20.0, 8.0).solids().vals()[0])
    return a, b

def _manifest(tmp_path, entries):
    """entries: [{name, balloon, step, offset?, bom_item?}]，写盘并返回路径与 specs。"""
    a, b = _parts(tmp_path)
    steps = {"a": a, "b": b}
    parts = []
    for one in entries:
        spec = {"name": one["name"], "balloon": one["balloon"],
                "step": str(steps[one.get("step", "a")]),
                "offset": one.get("offset", [0.0, 0.0, 0.0])}
        if "bom_item" in one:
            spec["bom_item"] = one["bom_item"]
        if "quantity" in one:
            spec["quantity"] = one["quantity"]      # 故意允许写：用来证明它不算数
        parts.append(spec)
    path = tmp_path / "assembly.json"
    path.write_text(json.dumps({"parts": parts}, ensure_ascii=False), encoding="utf-8")
    return path, parts

def _bom(tmp_path, items):
    """建一张 BOM：items = [(item, quantity, unit)]，返回 (db 路径, bom_id)。"""
    db = tmp_path / "state.db"
    store = BomStore(db)
    header = store.create_bom(TENANT, PROJECT, "装配 BOM")
    for i, (item, qty, unit) in enumerate(items, start=1):
        store.add_line(BomLine(line_id=f"L-{i}", bom_id=header.bom_id,
                               tenant_id=TENANT, project_id=PROJECT,
                               item=item, quantity=qty, unit=unit))
    return db, header.bom_id

def _lines(db, bom_id):
    return BomStore(db).list_lines(TENANT, PROJECT, bom_id)

def _load(tmp_path, manifest_path):
    return load_assembly_parts(parse_assembly_manifest(str(manifest_path)))

class TestBindingIsDeclaredNotInferred:
    def test_declared_bom_item_binds_and_quantity_comes_from_the_bom(self, tmp_path):
        manifest, _ = _manifest(tmp_path, [
            {"name": "支架", "balloon": 1, "bom_item": "BRACKET-01", "quantity": 99},
            {"name": "压板", "balloon": 2, "step": "b", "bom_item": "PLATE-02"},
        ])
        db, bom_id = _bom(tmp_path, [("BRACKET-01", 4.0, "pcs"), ("PLATE-02", 2.0, "pcs")])
        rows, issues = bind_bom(_load(tmp_path, manifest), _lines(db, bom_id))
        assert issues == [], issues
        assert [(r["item"], r["qty"], r["unit"]) for r in rows] == \
            [(1, 4.0, "pcs"), (2, 2.0, "pcs")], \
            "数量必须来自 BOM 行；manifest 里那个 99 是诱饵"

    def test_same_name_without_a_declared_bom_item_is_not_a_match(self, tmp_path):
        """这条是「不许按名字自动映射」的反证：零件名与 BOM 行完全相同也不许对上。"""
        manifest, _ = _manifest(tmp_path, [{"name": "支架", "balloon": 1}])
        db, bom_id = _bom(tmp_path, [("支架", 1.0, "pcs")])
        rows, issues = bind_bom(_load(tmp_path, manifest), _lines(db, bom_id))
        unbound = [r for r in rows if r["bom_line_id"] is None]
        assert [r["part"] for r in unbound] == ["支架"], "没声明却对上 = 图纸在编对应关系"
        assert any("未声明 bom_item" in m for m in issues), issues

    def test_matching_is_the_same_normalisation_the_bom_impact_path_uses(self, tmp_path):
        """大小写/首尾空格是**标识归一**，不是模糊匹配：与 supply_chain/impact 同一规则。"""
        manifest, _ = _manifest(tmp_path, [
            {"name": "支架", "balloon": 1, "bom_item": "  bracket-01 "}])
        db, bom_id = _bom(tmp_path, [("BRACKET-01", 3.0, "pcs")])
        rows, issues = bind_bom(_load(tmp_path, manifest), _lines(db, bom_id))
        assert issues == [], issues
        assert rows[0]["qty"] == 3.0

    def test_a_partial_prefix_of_a_bom_item_is_not_a_match(self, tmp_path):
        """归一是 strip+lower，不是「包含就算」——否则 BRACKET 会同时绑上 BRACKET-01/02。"""
        manifest, _ = _manifest(tmp_path, [{"name": "支架", "balloon": 1,
                                            "bom_item": "BRACKET"}])
        db, bom_id = _bom(tmp_path, [("BRACKET-01", 1.0, "pcs"),
                                     ("BRACKET-02", 1.0, "pcs")])
        rows, issues = bind_bom(_load(tmp_path, manifest), _lines(db, bom_id))
        assert rows[0]["bom_line_id"] is None
        assert any("找不到" in m for m in issues), issues

class TestBothSidesMustClose:
    def test_declared_item_missing_from_the_bom_is_an_issue_not_a_blank_cell(self, tmp_path):
        manifest, _ = _manifest(tmp_path, [{"name": "支架", "balloon": 1,
                                            "bom_item": "NOPE-9"}])
        db, bom_id = _bom(tmp_path, [("BRACKET-01", 1.0, "pcs")])
        rows, issues = bind_bom(_load(tmp_path, manifest), _lines(db, bom_id))
        assert any("NOPE-9" in m for m in issues), issues
        assert rows[0]["qty"] is None, "找不到就留空，不拿 0 或别的行冒充"

    def test_two_bom_lines_with_the_same_item_is_ambiguity_not_first_wins(self, tmp_path):
        manifest, _ = _manifest(tmp_path, [{"name": "支架", "balloon": 1,
                                            "bom_item": "BRACKET-01"}])
        db, bom_id = _bom(tmp_path, [("BRACKET-01", 1.0, "pcs"),
                                     ("BRACKET-01", 5.0, "set")])
        rows, issues = bind_bom(_load(tmp_path, manifest), _lines(db, bom_id))
        assert any("歧义" in m for m in issues), issues
        assert rows[0]["bom_line_id"] is None, "歧义时随便取一行就是猜数量"

    def test_bom_lines_the_drawing_never_points_at_are_listed(self, tmp_path):
        """漏了零件的装配图比丑的装配图危险：BOM 有行而图上没号 ⇒ 未收口，并点名是谁。"""
        manifest, _ = _manifest(tmp_path, [{"name": "支架", "balloon": 1,
                                            "bom_item": "BRACKET-01"}])
        db, bom_id = _bom(tmp_path, [("BRACKET-01", 1.0, "pcs"),
                                     ("SCREW-77", 12.0, "pcs")])
        rows, issues = bind_bom(_load(tmp_path, manifest), _lines(db, bom_id))
        missing = [m for m in issues if "SCREW-77" in m]
        assert missing, issues
        assert "图上没有球标" in missing[0]

    def test_a_fully_closed_binding_reports_no_issues(self, tmp_path):
        manifest, _ = _manifest(tmp_path, [
            {"name": "支架", "balloon": 1, "bom_item": "BRACKET-01"},
            {"name": "压板", "balloon": 2, "step": "b", "bom_item": "PLATE-02"}])
        db, bom_id = _bom(tmp_path, [("BRACKET-01", 4.0, "pcs"),
                                     ("PLATE-02", 2.0, "pcs")])
        _, issues = bind_bom(_load(tmp_path, manifest), _lines(db, bom_id))
        assert issues == []

class TestDrawingCarriesTheBoundQuantities:
    def _gen(self, tmp_path, manifest, db, bom_id, name="bound"):
        out = tmp_path / f"{name}.dxf"
        ev = generate_assembly_drawing(out, manifest=str(manifest), part_name="ASSY-1",
                                       views=("TOP",), bom_lines=_lines(db, bom_id))
        return ev, out

    def test_columns_grow_only_when_a_bom_is_bound(self, tmp_path):
        manifest, _ = _manifest(tmp_path, [
            {"name": "支架", "balloon": 1, "bom_item": "BRACKET-01"},
            {"name": "压板", "balloon": 2, "step": "b", "bom_item": "PLATE-02"}])
        db, bom_id = _bom(tmp_path, [("BRACKET-01", 4.0, "pcs"),
                                     ("PLATE-02", 2.0, "pcs")])
        ev, _ = self._gen(tmp_path, manifest, db, bom_id)
        assert ev["parts_list"]["columns"] == ["ITEM", "PART", "QTY", "UNIT"]
        assert [r["qty"] for r in ev["parts_list"]["rows"]] == [4.0, 2.0]
        assert ev["bom"]["bom_id"] == bom_id
        assert ev["assembly_issues"] == []

    def test_without_a_bom_the_table_keeps_the_old_two_columns(self, tmp_path):
        """第 12 片的形状不许被顺手改掉：没接 BOM 就只有 ITEM/PART，且一个数量都不印。"""
        manifest, _ = _manifest(tmp_path, [{"name": "支架", "balloon": 1}])
        out = tmp_path / "plain.dxf"
        ev = generate_assembly_drawing(out, manifest=str(manifest), part_name="ASSY-1",
                                       views=("TOP",))
        assert ev["parts_list"]["columns"] == ["ITEM", "PART"]
        assert all("qty" not in r for r in ev["parts_list"]["rows"])
        assert ev["bom"] is None

    def test_unbound_part_is_printed_with_an_empty_qty_not_a_zero(self, tmp_path):
        """留空是「没核到」，写 0 是「数量为 0」——图纸上这两个含义差一个量级。"""
        manifest, _ = _manifest(tmp_path, [
            {"name": "支架", "balloon": 1, "bom_item": "BRACKET-01"},
            {"name": "压板", "balloon": 2, "step": "b", "bom_item": "GHOST"}])
        db, bom_id = _bom(tmp_path, [("BRACKET-01", 4.0, "pcs")])
        ev, _ = self._gen(tmp_path, manifest, db, bom_id, name="half")
        rows = {r["item"]: r for r in ev["parts_list"]["rows"]}
        assert rows[2]["qty"] is None
        assert any("GHOST" in m for m in ev["assembly_issues"])

class TestCliSurface:
    def _run(self, tmp_path, manifest, extra, name="cli"):
        from aipd_os.cli.main import main

        out = tmp_path / f"{name}.dxf"
        argv = ["drawing", "assembly", "--manifest", str(manifest),
                "--out", str(out), "--part", "ASSY-1", "--views", "TOP", *extra]
        rc = main(argv)
        ev = None
        if out.with_suffix(".evidence.json").exists():
            ev = json.loads(out.with_suffix(".evidence.json").read_text("utf-8"))
        return rc, ev, out

    def test_bom_and_db_come_as_a_pair_otherwise_rc2(self, tmp_path):
        manifest, _ = _manifest(tmp_path, [{"name": "支架", "balloon": 1}])
        db, _ = _bom(tmp_path, [("BRACKET-01", 1.0, "pcs")])
        rc, _, out = self._run(tmp_path, manifest, ["--bom", "BOM-1"], name="onlybom")
        assert rc == 2, "只给 --bom 不给 --db 就是半条接线"
        rc2, _, _ = self._run(tmp_path, manifest, ["--db", str(db)], name="onlydb")
        assert rc2 == 2, "只给 --db 不给 --bom 同样是半条接线"
        assert not out.exists()

    def test_closed_binding_is_rc0_and_prints_quantities(self, tmp_path, capsys):
        manifest, _ = _manifest(tmp_path, [
            {"name": "支架", "balloon": 1, "bom_item": "BRACKET-01"},
            {"name": "压板", "balloon": 2, "step": "b", "bom_item": "PLATE-02"}])
        db, bom_id = _bom(tmp_path, [("BRACKET-01", 4.0, "pcs"),
                                     ("PLATE-02", 2.0, "pcs")])
        rc, ev, _ = self._run(tmp_path, manifest,
                              ["--db", str(db), "--bom", bom_id,
                               "--tenant", TENANT, "--project", PROJECT])
        text = capsys.readouterr().out
        assert rc == 0, text
        assert ev["parts_list"]["columns"] == ["ITEM", "PART", "QTY", "UNIT"]
        assert "数量与单位来自 BOM" in text
        assert "不按零件名字猜" in text

    def test_a_leaked_bom_line_holds_the_command_at_rc4(self, tmp_path):
        """BOM 多一个零件 = 图上少一个球标，这种图能画但会漏装，必须判住。"""
        manifest, _ = _manifest(tmp_path, [{"name": "支架", "balloon": 1,
                                           "bom_item": "BRACKET-01"}])
        db, bom_id = _bom(tmp_path, [("BRACKET-01", 1.0, "pcs"),
                                     ("SCREW-77", 12.0, "pcs")])
        rc, ev, _ = self._run(tmp_path, manifest,
                              ["--db", str(db), "--bom", bom_id,
                               "--tenant", TENANT, "--project", PROJECT])
        assert rc == 4, ev
        assert any("SCREW-77" in m for m in ev["assembly_issues"])

    def test_a_bom_id_that_does_not_exist_is_rc2_not_an_empty_binding(self, tmp_path):
        """编号写错要当场说「这张 BOM 不存在」，不能报成「每行都找不到」。

        真跑命令行时 ``--bom BOM-999`` 被当成空 BOM：每个球标各报一条「在 BOM 里找不到」，
        听起来像内容对不上，而实际是**根本没读到那张表**——两者处置完全不同。
        """
        manifest, _ = _manifest(tmp_path, [{"name": "支架", "balloon": 1,
                                           "bom_item": "BRACKET-01"}])
        db, _ = _bom(tmp_path, [("BRACKET-01", 4.0, "pcs")])
        rc, ev, out = self._run(tmp_path, manifest,
                                ["--db", str(db), "--bom", "BOM-999",
                                 "--tenant", TENANT, "--project", PROJECT],
                                name="wrongid")
        assert rc == 2, f"读不到那张表却继续画 ⇒ rc={rc}"
        assert not out.exists()

    def test_missing_db_file_is_rc2_not_a_silent_no_bom_run(self, tmp_path):
        """库路径写错要停在 rc=2，而且**不许把库建出来**。

        ``BomStore(path)`` 会 mkdir + 建表，所以「先构造再判断」等于在开发者机器上
        凭空造一个数据库；`is_file` 检查必须在构造之前。
        """
        manifest, _ = _manifest(tmp_path, [{"name": "支架", "balloon": 1,
                                           "bom_item": "BRACKET-01"}])
        ghost = tmp_path / "ghost.db"
        rc, _, out = self._run(tmp_path, manifest,
                               ["--db", str(ghost), "--bom", "BOM-1"],
                               name="ghostdb")
        assert rc == 2
        assert not out.exists(), "读不到权威表就当没接 BOM，会画出一张声称完整的图"
        assert not ghost.exists(), "命令行不许在写错的路径上凭空建一个数据库"

class TestAuthorityBoundaryAtParseTime:
    """两条变异电池抓出来的缺口：规矩要钉在**边界**上，不是钉在使用点上。

    N2「数量改从 manifest 取」原本杀不掉——因为解析器根本不把 ``quantity`` 读进零件数据，
    那个变异是等价变异（no-op）。这说明真正的守卫在解析边界，于是把这条不显形的
    规矩直接写成断言。N12「bom_item 写空串被放过」则是实打实的漏测。
    """

    def test_manifest_quantity_never_reaches_the_part_record(self, tmp_path):
        manifest, _ = _manifest(tmp_path, [{"name": "支架", "balloon": 1,
                                            "quantity": 99}])
        parts = _load(tmp_path, manifest)
        assert "quantity" not in parts[0], \
            "manifest 里写了数量就不许进到零件数据；进了，明细表就可能有第二个数量来源"
        assert parts[0]["bom_item"] is None, "没声明就没有对应关系，不拿名字补"

    def test_blank_bom_item_is_a_declaration_error_not_a_no_match(self, tmp_path):
        """``"bom_item": ""`` 是写坏了的声明，不是「这一行没对上」——必须当场拒绝。"""
        a, _ = _parts(tmp_path)
        path = tmp_path / "blank.json"
        path.write_text(json.dumps({"parts": [{"name": "支架", "step": str(a),
                                               "balloon": 1, "bom_item": "   "}]},
                                   ensure_ascii=False), encoding="utf-8")
        with pytest.raises(ValueError, match="bom_item"):
            parse_assembly_manifest(str(path))

    def test_non_string_bom_item_is_rejected_too(self, tmp_path):
        a, _ = _parts(tmp_path)
        path = tmp_path / "num.json"
        path.write_text(json.dumps({"parts": [{"name": "支架", "step": str(a),
                                               "balloon": 1, "bom_item": 7}]},
                                   ensure_ascii=False), encoding="utf-8")
        with pytest.raises(ValueError, match="bom_item"):
            parse_assembly_manifest(str(path))


def test_bound_quantities_are_actually_drawn_not_only_in_the_evidence(tmp_path):
    """证据里有数量不等于图纸上看得见数量：TEXT 实体必须真的落在表格里。

    少了这条，「columns 长出来了、rows 带着 qty，但一格都没画」这种错只会绿。
    """
    import ezdxf

    manifest, _ = _manifest(tmp_path, [
        {"name": "支架", "balloon": 1, "bom_item": "BRACKET-01"},
        {"name": "压板", "balloon": 2, "step": "b", "bom_item": "PLATE-02"}])
    db, bom_id = _bom(tmp_path, [("BRACKET-01", 4.0, "pcs"), ("PLATE-02", 2.0, "set")])
    out = tmp_path / "drawn.dxf"
    generate_assembly_drawing(out, manifest=str(manifest), part_name="ASSY-1",
                              views=("TOP",), bom_lines=_lines(db, bom_id))
    doc = ezdxf.readfile(str(out))
    texts = {e.dxf.text for e in doc.modelspace().query('TEXT[layer=="TABLECONTENT"]')}
    assert {"ITEM", "PART", "QTY", "UNIT"} <= texts, texts
    # 逐格点名：4/2 是数量、pcs/set 是单位——「4」「2」也可能出现在别处，
    # 所以只在 TABLECONTENT 这一层里核，且核到的是**两行各自**的数量与单位
    assert {"4", "2", "pcs", "set"} <= texts, texts
