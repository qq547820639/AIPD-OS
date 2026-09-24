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

第 15 片把**材料**、第 16 片把**工艺**接到同一条绑定上：它们与数量同一权威（BOM 行）、
同一个 `bom_item` 声明、同一处留空规矩，所以复用这里的夹具而不是另起一套对应关系。
两半各自独立判、各自点名（`TestProcessColumnComesFromTheBom` 里有一条专门钉「不许拿
工艺凑材料」）。供应商**不在**明细表里（判据与理由见 `TestSupplierIsNotOnTheDrawing`）。
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
    """按**产品口径**造库：状态库 state.db + 同目录的 bom.db，返回 (state.db, bom_id)。

    夹具故意走和命令行同一个换算（``bom_store_path``）：「BOM 放哪个文件」这条规矩
    一旦被改动，这里就跟着红——不会像上一片那样测试与命令行各认一个路径。

    每一项 ``(item, qty, unit[, material[, supplier]])``，或直接给一个 dict
    （``{"item":…, "quantity":…, "unit":…, "process":…}``）：第 16 片起字段多于三个，
    位置参数会读成 ``("BRACKET-01", 4.0, "pcs", None, None, "CNC")`` 那种没人能核的东西。
    材料/工艺留成可缺省，是为了让「BOM 行没填」这种真实数据形状能被画出来。
    """
    from aipd_os.bom.store import bom_store_path
    from aipd_os.state.db import AIPDStateDB

    state = tmp_path / "state.db"
    AIPDStateDB(state).ensure_default_tenant()
    store = BomStore(bom_store_path(state))
    header = store.create_bom(TENANT, PROJECT, "装配 BOM")
    for i, spec in enumerate(items, start=1):
        extra = dict(spec) if isinstance(spec, dict) else {
            "item": spec[0], "quantity": spec[1], "unit": spec[2],
            **({"material": spec[3]} if len(spec) > 3 else {}),
            **({"supplier": spec[4]} if len(spec) > 4 else {})}
        store.add_line(BomLine(line_id=f"L-{i}", bom_id=header.bom_id,
                               tenant_id=TENANT, project_id=PROJECT, **extra))
    return state, header.bom_id

def _lines(db, bom_id):
    from aipd_os.bom.store import bom_store_path

    return BomStore(bom_store_path(db)).list_lines(TENANT, PROJECT, bom_id)

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
        assert ev["parts_list"]["columns"] == ["ITEM", "PART", "QTY", "UNIT", "MATERIAL", "PROCESS"]
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

class TestMaterialColumnComesFromTheBom:
    """第 15 片：材料**只认 BOM 行**——与数量同一权威、同一条 `bom_item` 声明、同一处留空。

    判据来源要说实话：本仓 `references/production-cad-deliverables.md:3` 把「材料与工艺」
    列为 C6 交付物，`references/deliverable-contracts.md:9` 把「规格/材料」写在**每一行 BOM**
    上；外部只读到 RoyMech 的条目清单（Item/Description/Quantity/Reference/Material，
    供货信息只算「其他必要信息」）。**ISO 7200 与 GB/T 10609.2 原文没有取到**
    （检索到的页面对本模型只返回 CSS 或文档分享站的转载），所以列集合按上面两条内部
    契约裁剪，不假装对照过标准表样。
    """

    def _gen(self, tmp_path, manifest, db, bom_id, **kw):
        out = tmp_path / "mat.dxf"
        return generate_assembly_drawing(out, manifest=str(manifest), part_name="ASSY-1",
                                         views=("TOP",), bom_lines=_lines(db, bom_id), **kw)

    def _texts(self, path):
        import ezdxf

        doc = ezdxf.readfile(str(path))
        return {e.dxf.text for e in doc.modelspace().query('TEXT[layer=="TABLECONTENT"]')}

    def test_the_material_of_a_bound_row_is_the_bom_line_material(self, tmp_path):
        manifest, _ = _manifest(tmp_path, [
            {"name": "支架", "balloon": 1, "bom_item": "BRACKET-01"},
            {"name": "压板", "balloon": 2, "step": "b", "bom_item": "PLATE-02"}])
        db, bom_id = _bom(tmp_path, [("BRACKET-01", 4.0, "pcs", "6061-T6"),
                                     ("PLATE-02", 2.0, "pcs", "SUS304")])
        rows, issues = bind_bom(_load(tmp_path, manifest), _lines(db, bom_id))
        assert issues == [], issues
        assert [(r["item"], r["material"]) for r in rows] == \
            [(1, "6061-T6"), (2, "SUS304")]

    def test_material_is_drawn_in_the_table_not_only_in_the_evidence(self, tmp_path):
        manifest, _ = _manifest(tmp_path, [
            {"name": "支架", "balloon": 1, "bom_item": "BRACKET-01"},
            {"name": "压板", "balloon": 2, "step": "b", "bom_item": "PLATE-02"}])
        db, bom_id = _bom(tmp_path, [("BRACKET-01", 4.0, "pcs", "6061-T6"),
                                     ("PLATE-02", 2.0, "pcs", "SUS304")])
        ev = self._gen(tmp_path, manifest, db, bom_id)
        assert ev["parts_list"]["columns"] == ["ITEM", "PART", "QTY", "UNIT", "MATERIAL", "PROCESS"]
        texts = self._texts(tmp_path / "mat.dxf")
        assert {"MATERIAL", "6061-T6", "SUS304"} <= texts, texts

    def test_a_bound_row_without_material_stays_blank_and_holds_no_guess(self, tmp_path):
        """绑上了但那一行没填材料 ⇒ 格子留空：写 "-" 或「未指定」都会被读成一个材料。"""
        manifest, _ = _manifest(tmp_path, [{"name": "支架", "balloon": 1,
                                            "bom_item": "BRACKET-01"}])
        db, bom_id = _bom(tmp_path, [("BRACKET-01", 4.0, "pcs", None)])
        ev = self._gen(tmp_path, manifest, db, bom_id)
        assert ev["parts_list"]["rows"][0]["material"] is None
        assert ev["assembly_issues"] == [], "材料缺失由 manifest 那条判据点名，不算绑定未收口"
        texts = self._texts(tmp_path / "mat.dxf")
        assert "MATERIAL" in texts
        assert "-" not in texts and "未指定" not in texts, texts
        assert "None" not in texts, texts       # str(None) 也是一种假装有值

    def test_the_material_column_is_there_even_when_no_row_has_one(self, tmp_path):
        """列集合跟着**接上的权威**走，不跟着「有没有值」走。

        用 `any(有值才加列)` 的写法，一张全缺材料的图会连列都不长，于是「哪些行没有材料」
        的答案从图纸上直接消失——而「全部没有」恰是最需要看得见的那一种。
        """
        manifest, _ = _manifest(tmp_path, [
            {"name": "支架", "balloon": 1, "bom_item": "BRACKET-01"},
            {"name": "压板", "balloon": 2, "step": "b", "bom_item": "PLATE-02"}])
        db, bom_id = _bom(tmp_path, [("BRACKET-01", 4.0, "pcs"),
                                     ("PLATE-02", 2.0, "pcs")])
        ev = self._gen(tmp_path, manifest, db, bom_id)
        assert "MATERIAL" in ev["parts_list"]["columns"]
        assert all(r["material"] is None for r in ev["parts_list"]["rows"])

    def test_an_unbound_row_has_no_material_either(self, tmp_path):
        """没绑上的行：数量、单位、材料一起留空——一个都不许从别处补。"""
        manifest, _ = _manifest(tmp_path, [
            {"name": "支架", "balloon": 1, "bom_item": "BRACKET-01"},
            {"name": "压板", "balloon": 2, "step": "b", "bom_item": "GHOST"}])
        db, bom_id = _bom(tmp_path, [("BRACKET-01", 4.0, "pcs", "6061-T6")])
        rows, _ = bind_bom(_load(tmp_path, manifest), _lines(db, bom_id))
        ghost = next(r for r in rows if r["item"] == 2)
        assert (ghost["qty"], ghost["unit"], ghost["material"]) == (None, None, None)

    def test_whitespace_only_material_counts_as_missing(self, tmp_path):
        """``"   "`` 不是材料：留空与「有个空格组成的材料」在图纸上看不出差别，必须归一到 None。"""
        manifest, _ = _manifest(tmp_path, [{"name": "支架", "balloon": 1,
                                            "bom_item": "BRACKET-01"}])
        db, bom_id = _bom(tmp_path, [("BRACKET-01", 4.0, "pcs", "   ")])
        rows, _ = bind_bom(_load(tmp_path, manifest), _lines(db, bom_id))
        assert rows[0]["material"] is None, "空白串当材料会盖住「这一行还没材料」这个事实"

    def test_the_title_block_material_is_not_a_fallback(self, tmp_path):
        """标题栏的 MATL 是作者另填的一格，不许拿它来补明细表里缺的行级材料。"""
        manifest, _ = _manifest(tmp_path, [{"name": "支架", "balloon": 1,
                                            "bom_item": "BRACKET-01"}])
        db, bom_id = _bom(tmp_path, [("BRACKET-01", 4.0, "pcs", None)])
        ev = self._gen(tmp_path, manifest, db, bom_id, material="ALU-7075")
        assert ev["parts_list"]["rows"][0]["material"] is None
        assert "ALU-7075" not in self._texts(tmp_path / "mat.dxf"), \
            "标题栏材料渗进明细表 = 一个来源两个含义"

    def test_material_never_comes_from_the_manifest(self, tmp_path):
        """与数量同一条边界规矩：清单里写了 material 也不许进到零件数据。"""
        a, _ = _parts(tmp_path)
        path = tmp_path / "withmat.json"
        path.write_text(json.dumps({"parts": [{"name": "支架", "step": str(a),
                                               "balloon": 1, "bom_item": "BRACKET-01",
                                               "material": "自己做主的材料"}]},
                                   ensure_ascii=False), encoding="utf-8")
        parts = _load(tmp_path, path)
        assert "material" not in parts[0], "第二个材料来源会在明细表里和 BOM 抢同一格"


class TestSupplierIsNotOnTheDrawing:
    """裁决：供应商**不进**零件图/装配图明细表，留在 BOM 与采购侧。

    理由写在这里而不只在审计文档里：明细表随图纸版本冻结，而供应商是商务事实
    （``references/deliverable-contracts.md:17`` 把它归到「供应链开发清单」，
    BOM 契约里它也只是「候选供应商」）。把供应商印到图上，等于让一张受控技术文件
    携带一个会变、且未取证就绪的采购承诺。所以这里连列都不长。
    """

    def test_a_bom_line_supplier_never_reaches_the_parts_list(self, tmp_path):
        import ezdxf

        manifest, _ = _manifest(tmp_path, [{"name": "支架", "balloon": 1,
                                            "bom_item": "BRACKET-01"}])
        db, bom_id = _bom(tmp_path, [("BRACKET-01", 4.0, "pcs", "6061-T6", "ACME-IND")])
        lines = _lines(db, bom_id)
        assert lines[0].supplier == "ACME-IND", "前提：BOM 那边真写了供应商"
        rows, _ = bind_bom(_load(tmp_path, manifest), lines)
        assert "supplier" not in rows[0], "明细表行里不许带 supplier 字段"

        out = tmp_path / "sup.dxf"
        ev = generate_assembly_drawing(out, manifest=str(manifest), part_name="ASSY-1",
                                       views=("TOP",), bom_lines=lines)
        assert "SUPPLIER" not in ev["parts_list"]["columns"]
        doc = ezdxf.readfile(str(out))
        texts = {e.dxf.text for e in doc.modelspace().query('TEXT[layer=="TABLECONTENT"]')}
        assert "ACME-IND" not in texts, texts

    def test_the_boundary_is_written_in_the_module_that_enforces_it(self):
        """这条规矩全靠「不实现」成立，所以必须留在代码旁边——否则下一个人会当成漏做。"""
        import aipd_os.cad.assembly as assembly_module

        assert "供应商" in (assembly_module.__doc__ or ""), \
            "模块 docstring 要写明供应商被排除及其理由"



class TestProcessColumnComesFromTheBom:
    """第 16 片：把 C6「材料与工艺」的另一半接上——工艺同样**只认 BOM 行**。

    `BomLine.process` 的语义边界写在 `bom/models.py`：它是「明细表那一格要的那道主工艺」，
    **不是工序路线**（成熟实现把多工序建成独立对象：Dynamics 365 BC 的 BOM 行只带
    Routing Link Code，ERPNext v15 用子表 BOM Operation）。所以这里一格一个字符串，
    不解析顺序、不估工时。
    """

    def _gen(self, tmp_path, manifest, db, bom_id, **kw):
        out = tmp_path / "proc.dxf"
        return generate_assembly_drawing(out, manifest=str(manifest), part_name="ASSY-1",
                                         views=("TOP",), bom_lines=_lines(db, bom_id), **kw)

    def _texts(self, path):
        import ezdxf

        doc = ezdxf.readfile(str(path))
        return {e.dxf.text for e in doc.modelspace().query('TEXT[layer=="TABLECONTENT"]')}

    def test_bound_row_carries_the_process_from_the_bom_line(self, tmp_path):
        manifest, _ = _manifest(tmp_path, [
            {"name": "支架", "balloon": 1, "bom_item": "BRACKET-01"},
            {"name": "压板", "balloon": 2, "step": "b", "bom_item": "PLATE-02"}])
        db, bom_id = _bom(tmp_path, [
            {"item": "BRACKET-01", "quantity": 4.0, "unit": "pcs", "process": "CNC 铣削"},
            {"item": "PLATE-02", "quantity": 2.0, "unit": "set", "process": "激光切割"}])
        rows, issues = bind_bom(_load(tmp_path, manifest), _lines(db, bom_id))
        assert issues == [], issues
        assert [(r["item"], r["process"]) for r in rows] == \
            [(1, "CNC 铣削"), (2, "激光切割")]

    def test_process_is_drawn_and_completes_the_bom_column_set(self, tmp_path):
        manifest, _ = _manifest(tmp_path, [{"name": "支架", "balloon": 1,
                                            "bom_item": "BRACKET-01"}])
        db, bom_id = _bom(tmp_path, [{"item": "BRACKET-01", "quantity": 4.0,
                                      "unit": "pcs", "process": "CNC 铣削"}])
        ev = self._gen(tmp_path, manifest, db, bom_id)
        assert ev["parts_list"]["columns"] == \
            ["ITEM", "PART", "QTY", "UNIT", "MATERIAL", "PROCESS"]
        assert "CNC 铣削" in self._texts(tmp_path / "proc.dxf")

    def test_a_row_without_process_is_blank_and_the_column_still_exists(self, tmp_path):
        manifest, _ = _manifest(tmp_path, [{"name": "支架", "balloon": 1,
                                            "bom_item": "BRACKET-01"}])
        db, bom_id = _bom(tmp_path, [{"item": "BRACKET-01", "quantity": 4.0,
                                      "unit": "pcs", "process": None}])
        ev = self._gen(tmp_path, manifest, db, bom_id)
        assert ev["parts_list"]["rows"][0]["process"] is None
        texts = self._texts(tmp_path / "proc.dxf")
        assert "PROCESS" in texts
        assert not {"-", "None", "未指定"} & texts, texts

    def test_whitespace_process_counts_as_missing(self, tmp_path):
        manifest, _ = _manifest(tmp_path, [{"name": "支架", "balloon": 1,
                                            "bom_item": "BRACKET-01"}])
        db, bom_id = _bom(tmp_path, [{"item": "BRACKET-01", "quantity": 4.0,
                                      "unit": "pcs", "process": "  \t "}])
        rows, _ = bind_bom(_load(tmp_path, manifest), _lines(db, bom_id))
        assert rows[0]["process"] is None

    def test_process_never_borrows_the_material_cell_and_the_other_way_round(self, tmp_path):
        """两个来源各填一半时**不许互相顶格子**：C6 那句「材料与工艺」是两件事。

        这一条盯的是最省事的错写法——「材料没填就拿工艺凑」（或反过来），
        那会让图纸上那一格看起来有值，而真正缺的事实被盖住。
        """
        manifest, _ = _manifest(tmp_path, [
            {"name": "支架", "balloon": 1, "bom_item": "BRACKET-01"},
            {"name": "压板", "balloon": 2, "step": "b", "bom_item": "PLATE-02"}])
        db, bom_id = _bom(tmp_path, [
            {"item": "BRACKET-01", "quantity": 4.0, "unit": "pcs",
             "material": None, "process": "CNC 铣削"},
            {"item": "PLATE-02", "quantity": 2.0, "unit": "set",
             "material": "SUS304", "process": None}])
        rows, _ = bind_bom(_load(tmp_path, manifest), _lines(db, bom_id))
        by_item = {r["item"]: r for r in rows}
        assert (by_item[1]["material"], by_item[1]["process"]) == (None, "CNC 铣削")
        assert (by_item[2]["material"], by_item[2]["process"]) == ("SUS304", None)

    def test_manifest_process_is_not_read_either(self, tmp_path):
        """与 quantity/material 同一条边界：清单里写工艺也不许进到零件数据。"""
        a, _ = _parts(tmp_path)
        path = tmp_path / "pm.json"
        path.write_text(json.dumps({"parts": [{"name": "支架", "step": str(a),
                                               "balloon": 1, "bom_item": "BRACKET-01",
                                               "process": "清单自己说的工艺"}]},
                                   ensure_ascii=False), encoding="utf-8")
        parts = _load(tmp_path, path)
        assert "process" not in parts[0]

    def test_the_cli_reports_which_half_is_still_missing(self, tmp_path, capsys):
        """命令行要说得出「材料齐了、工艺还差哪一行」——否则拍完材料就没人知道工艺是空的。"""
        from aipd_os.cli.main import main

        manifest, _ = _manifest(tmp_path, [
            {"name": "支架", "balloon": 1, "bom_item": "BRACKET-01"},
            {"name": "压板", "balloon": 2, "step": "b", "bom_item": "PLATE-02"}])
        db, bom_id = _bom(tmp_path, [
            {"item": "BRACKET-01", "quantity": 4.0, "unit": "pcs",
             "material": "6061-T6", "process": "CNC 铣削"},
            {"item": "PLATE-02", "quantity": 2.0, "unit": "set", "material": "SUS304"}])
        out = tmp_path / "cli-proc.dxf"
        rc = main(["drawing", "assembly", "--manifest", str(manifest), "--out", str(out),
                   "--part", "ASSY-1", "--views", "TOP", "--db", str(db),
                   "--bom", bom_id, "--tenant", TENANT, "--project", PROJECT])
        text = capsys.readouterr().out
        assert rc == 0, text
        assert "材料已填 2/2 行，没有缺行" in text, text
        assert "工艺已填 1/2 行，缺的球标 [2]" in text, text
        # 没做的事里不能再出现「工艺列还没做」——它已经做了，缺的是多工序路线
        assert "多工序工艺路线" in text and "工艺与表面处理列" not in text, text



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
        assert ev["parts_list"]["columns"] == ["ITEM", "PART", "QTY", "UNIT", "MATERIAL", "PROCESS"]
        assert "数量、单位、材料与工艺都来自 BOM" in text
        assert "不按零件名字猜" in text
        # 行内说的话要和真画出来的列一致，也不能再欠一句「材料还没取用」
        assert "MATERIAL" in text
        assert "材料列" not in text, "命令行还在说材料没接线"
        assert "工艺" in text, "「没做的事」里要留下还没做的那一半"

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


class TestBomLibraryResolution:
    """``--db`` 指的是**状态库**；BOM 永远在同目录的 ``bom.db`` 里（产品口径）。

    这一整类是我自己上一片埋的坑：`BomStore(path)` 会在 path 上建表，所以
    ``BomStore(args.db)`` 等于给权威状态库加 BOM 表——而 ``bom/store.py`` 的模块
    docstring 明写「BOM 使用独立库文件…避免给权威状态库加表（迁移冻结）」。
    真跑命令行复现了：state.db 的表数 42 → 46，多出 boms / bom_lines /
    bom_changes / bom_id_sequences，而命令本身还因为读不到 BOM 返回 rc=2。
    """

    def _tables(self, db: Path) -> set:
        import sqlite3

        con = sqlite3.connect(str(db))
        try:
            return {r[0] for r in con.execute(
                "select name from sqlite_master where type='table'")}
        finally:
            con.close()

    def _state_db(self, tmp_path: Path) -> Path:
        from aipd_os.state.db import AIPDStateDB

        db = tmp_path / "state.db"
        state = AIPDStateDB(str(db))
        state.ensure_default_tenant()
        state.init_project(TENANT, PROJECT, "装配验证项目", "看 BOM 会不会写进权威库")
        return db

    def test_reading_bom_never_adds_tables_to_the_state_db(self, tmp_path):
        manifest, _ = _manifest(tmp_path, [{"name": "支架", "balloon": 1,
                                           "bom_item": "BRACKET-01"}])
        db = self._state_db(tmp_path)
        # 真按产品口径把 BOM 放在同目录的 bom.db 里
        sibling = tmp_path / "bom.db"
        store = BomStore(sibling)
        header = store.create_bom(TENANT, PROJECT, "装配 BOM")
        store.add_line(BomLine(line_id="L-1", bom_id=header.bom_id, tenant_id=TENANT,
                               project_id=PROJECT, item="BRACKET-01",
                               quantity=7.0, unit="pcs"))
        before = self._tables(db)

        from aipd_os.cli.main import main

        out = tmp_path / "sibling.dxf"
        rc = main(["drawing", "assembly", "--manifest", str(manifest), "--out", str(out),
                   "--part", "ASSY-1", "--views", "TOP", "--db", str(db),
                   "--bom", header.bom_id, "--tenant", TENANT, "--project", PROJECT])
        assert rc == 0, f"BOM 在同目录 bom.db 里，命令却读不到：rc={rc}"
        assert self._tables(db) == before, (
            f"权威状态库被加了表：{sorted(self._tables(db) - before)}")
        evidence = json.loads(out.with_suffix(".evidence.json").read_text("utf-8"))
        assert [r["qty"] for r in evidence["parts_list"]["rows"]] == [7.0], \
            "数量必须来自同目录 bom.db 里那行"

    def test_missing_bom_library_is_rc2_and_creates_nothing(self, tmp_path):
        """只读消费方不许「顺手建一个空 BOM 库」——那会把「没接线」读成「接了但是空的」。"""
        manifest, _ = _manifest(tmp_path, [{"name": "支架", "balloon": 1,
                                            "bom_item": "BRACKET-01"}])
        db = self._state_db(tmp_path)
        from aipd_os.cli.main import main

        out = tmp_path / "none.dxf"
        rc = main(["drawing", "assembly", "--manifest", str(manifest), "--out", str(out),
                   "--part", "ASSY-1", "--views", "TOP", "--db", str(db),
                   "--bom", "BOM-001", "--tenant", TENANT, "--project", PROJECT])
        assert rc == 2
        assert not (tmp_path / "bom.db").exists(), "读不到就该报错，不该把库建出来"
        assert not out.exists()

    def test_wrong_state_db_path_is_refused_even_if_a_bom_sits_there(self, tmp_path):
        """状态库路径写错要当场拒绝，即使同目录真有一个能读的 bom.db。

        少了这条，「--db 拼错」会被 BOM 侧的存在性检查兜住而照常出图（N8 首轮就是这么
        幸存的）：数量来自一个和这个项目对不上的目录，图纸却看着完全正常。
        """
        manifest, _ = _manifest(tmp_path, [{"name": "支架", "balloon": 1,
                                            "bom_item": "BRACKET-01"}])
        db, bom_id = _bom(tmp_path, [("BRACKET-01", 7.0, "pcs")])
        assert (tmp_path / "bom.db").is_file()          # 前提：BOM 侧确实能读到

        from aipd_os.cli.main import main

        out = tmp_path / "wrong.dxf"
        rc = main(["drawing", "assembly", "--manifest", str(manifest), "--out", str(out),
                   "--part", "ASSY-1", "--views", "TOP",
                   "--db", str(tmp_path / "not-this-state.db"), "--bom", bom_id,
                   "--tenant", TENANT, "--project", PROJECT])
        assert rc == 2, f"--db 指错却出了图 ⇒ rc={rc}"
        assert not out.exists()
