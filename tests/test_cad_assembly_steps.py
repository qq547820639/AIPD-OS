"""装配步骤文档生产者（capability ``cad.assembly_instructions``，C6 的「装配/维护」那一半）。

判据的来路都写在模块 docstring 里，这里只钉住四件可数字化的事：

1. 步骤号与顺序**由作者声明**——本模块不按遍历顺序代发，也不补断档；
2. 步骤只指向 manifest 里**已声明**的球标——引用不存在的号直接拒，没被任何步骤
   装配的球标记未收口（文档照出，但话说清楚）；
3. 数量/材料/工艺只来自绑上的 BOM 行，绑不上留空，不写占位符；
4. 这份文档只承载装配步骤——工时、工序成本、扭矩、维护指引都不承载，
   而且证据里必须**明写**它没承载什么（否则读者把骨架当成完整作业指导书）。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from aipd_os.bom.models import BomLine
from aipd_os.cad.assembly_steps import (
    build_step_plan,
    generate_assembly_steps,
    parse_assembly_steps,
)
from aipd_os.release_manifest import build_release_manifest

TENANT = "t"
PROJECT = "p"


def _manifest(tmp_path: Path, parts: list[dict], steps: list[dict] | None = None,
              name: str = "assy.json") -> Path:
    """写一份装配 manifest：零件都要有真存在的 STEP 文件（本模块只查存在，不投影）。"""
    payload: dict = {"parts": []}
    for one in parts:
        raw = dict(one)
        if "step" not in raw:
            step = tmp_path / f"{raw['name']}.step"
            step.write_bytes(b"ISO-10303-21;HEADER;")
            raw["step"] = step.name
        elif not Path(raw["step"]).is_absolute():
            step = tmp_path / raw["step"]
            step.write_bytes(b"ISO-10303-21;HEADER;")
            raw["step"] = step.name
        payload["parts"].append(raw)
    if steps is not None:
        payload["assembly_steps"] = steps
    file = tmp_path / name
    file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return file


def _two_part_parts() -> list[dict]:
    return [{"name": "支架", "balloon": 1}, {"name": "压板", "balloon": 2}]


def _clean_steps() -> list[dict]:
    return [{"no": 1, "action": "支架贴合基面", "balloons": [1]},
            {"no": 2, "action": "压板压在支架上", "balloons": [1, 2]}]


class TestStepSequenceIsAuthorDeclared:
    def test_manifest_without_steps_is_refused(self, tmp_path):
        man = _manifest(tmp_path, _two_part_parts())
        with pytest.raises(ValueError) as exc:
            parse_assembly_steps(man)
        assert "assembly_steps" in str(exc.value)

    def test_empty_step_list_is_refused(self, tmp_path):
        """空列表≠「一份没有步骤的装配步骤文档」：后者不是交付物。"""
        man = _manifest(tmp_path, _two_part_parts(), steps=[])
        with pytest.raises(ValueError, match="一个步骤都没有"):
            parse_assembly_steps(man)

    def test_step_number_is_not_issued_in_traversal_order(self, tmp_path):
        man = _manifest(tmp_path, _two_part_parts(),
                        steps=[{"action": "装支架", "balloons": [1]}])
        with pytest.raises(ValueError) as exc:
            parse_assembly_steps(man)
        assert "步骤号" in str(exc.value), "缺编号要说清是作者没说，不是模块代发一个"

    def test_duplicate_step_numbers_refused(self, tmp_path):
        man = _manifest(tmp_path, _two_part_parts(),
                        steps=[{"no": 1, "action": "甲", "balloons": [1]},
                               {"no": 1, "action": "乙", "balloons": [2]}])
        with pytest.raises(ValueError, match="步骤号重复"):
            parse_assembly_steps(man)

    def test_step_number_must_be_a_positive_int(self, tmp_path):
        for bad in (0, -1, "1", 1.5, True):
            man = _manifest(tmp_path, _two_part_parts(),
                            steps=[{"no": bad, "action": "甲", "balloons": [1]}],
                            name=f"n{repr(bad)}.json")
            with pytest.raises(ValueError, match="正整数"):
                parse_assembly_steps(man)

    def test_gap_in_step_numbers_is_refused_not_silently_closed(self, tmp_path):
        """1、2、4 印出来就是让操作者以为第 3 步不存在——断档必须点名。"""
        man = _manifest(tmp_path, _two_part_parts(),
                        steps=[{"no": 1, "action": "甲", "balloons": [1]},
                               {"no": 2, "action": "乙", "balloons": [2]},
                               {"no": 4, "action": "丙", "balloons": [2]}])
        with pytest.raises(ValueError) as exc:
            parse_assembly_steps(man)
        assert "断档" in str(exc.value) and "3" in str(exc.value)

    def test_file_order_does_not_decide_reading_order(self, tmp_path):
        md = tmp_path / "steps.md"
        man = _manifest(tmp_path, _two_part_parts(),
                        steps=[{"no": 2, "action": "后一步", "balloons": [2]},
                               {"no": 1, "action": "先一步", "balloons": [1]}])
        generate_assembly_steps(md, manifest=str(man), part_name="ASSY-1")
        text = md.read_text(encoding="utf-8")
        assert text.index("## 步骤 1") < text.index("## 步骤 2")
        assert "先一步" in text.split("## 步骤 2")[0]

    def test_unknown_step_field_is_refused_not_dropped(self, tmp_path):
        """静默丢掉作者写的扭矩=文档少了一条他没说的信息还自称完整。"""
        man = _manifest(tmp_path, _two_part_parts(),
                        steps=[{"no": 1, "action": "拧紧", "balloons": [1],
                               "torque": "12 N·m"}])
        with pytest.raises(ValueError) as exc:
            parse_assembly_steps(man)
        assert "torque" in str(exc.value)


class TestStepsPointAtDeclaredBalloons:
    def test_step_must_cite_a_declared_balloon(self, tmp_path):
        man = _manifest(tmp_path, _two_part_parts(),
                        steps=[{"no": 1, "action": "装个不存在的东西", "balloons": [9]}])
        with pytest.raises(ValueError) as exc:
            parse_assembly_steps(man)
        assert "9" in str(exc.value) and "没声明" in str(exc.value)

    def test_step_without_balloons_refused(self, tmp_path):
        for raw in ({"no": 1, "action": "清洁配合面"},
                    {"no": 1, "action": "清洁配合面", "balloons": []}):
            man = _manifest(tmp_path, _two_part_parts(), steps=[raw],
                            name=f"b{len(raw)}.json")
            with pytest.raises(ValueError, match="球标"):
                parse_assembly_steps(man)

    def test_same_balloon_twice_in_one_step_refused(self, tmp_path):
        man = _manifest(tmp_path, _two_part_parts(),
                        steps=[{"no": 1, "action": "甲", "balloons": [1, 1]}])
        with pytest.raises(ValueError, match="重复"):
            parse_assembly_steps(man)

    def test_balloon_no_step_assembles_is_an_issue_not_a_crash(self, tmp_path):
        """文档照出，但「图上编了号、步骤里没人装它」必须留在证据里。"""
        man = _manifest(tmp_path, _two_part_parts(),
                        steps=[{"no": 1, "action": "只装支架", "balloons": [1]}])
        plan = build_step_plan(parse_manifest_parts(man), parse_assembly_steps(man), None)
        assert plan["balloon_coverage"]["unreferenced"] == [2]
        assert any("球标 2" in msg for msg in plan["issues"]), plan["issues"]

    def test_full_coverage_leaves_no_issue(self, tmp_path):
        man = _manifest(tmp_path, _two_part_parts(), steps=_clean_steps())
        plan = build_step_plan(parse_manifest_parts(man), parse_assembly_steps(man), None)
        assert plan["issues"] == []
        assert plan["balloon_coverage"] == {"declared": [1, 2], "referenced": [1, 2],
                                           "unreferenced": []}


def parse_manifest_parts(manifest: Path) -> list[dict]:
    from aipd_os.cad.assembly import parse_assembly_manifest

    return parse_assembly_manifest(manifest)


def _table(text: str) -> dict[str, list[str]]:
    """把明细表按球标号取出来：`{"1": ["1", "支架", "", "", "", ""]}`。

    断言写在**格子上**而不是写在「有没有某个字符」上——后者会被文档里
    解释自己边界的那几句话撞绿。
    """
    head = text.split("## 步骤")[0]
    rows: dict[str, list[str]] = {}
    for line in head.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells and cells[0] in ("1", "2"):
            rows[cells[0]] = cells
    return rows


class TestDocumentBody:
    def test_action_text_is_printed_verbatim(self, tmp_path):
        md = tmp_path / "s.md"
        man = _manifest(tmp_path, _two_part_parts(), steps=_clean_steps())
        generate_assembly_steps(md, manifest=str(man), part_name="ASSY-1")
        text = md.read_text(encoding="utf-8")
        assert "支架贴合基面" in text and "压板压在支架上" in text
        assert text.count("## 步骤") == 2

    def test_qty_and_material_come_from_the_bound_bom_row(self, tmp_path):
        man = _manifest(tmp_path, [{"name": "支架", "balloon": 1, "bom_item": "BRACKET-01"}],
                        steps=_clean_steps()[:1])
        lines = [BomLine(line_id="L-1", bom_id="B-1", tenant_id=TENANT, project_id=PROJECT,
                         item="BRACKET-01", quantity=4.0, unit="pcs",
                         material="6061-T6", process="阳极氧化")]
        md = tmp_path / "s.md"
        generate_assembly_steps(md, manifest=str(man), part_name="ASSY-1", bom_lines=lines)
        cells = _table(md.read_text(encoding="utf-8"))["1"]
        assert cells[2:] == ["4", "pcs", "6061-T6", "阳极氧化"], cells

    def test_without_bom_authority_the_table_has_no_value_columns(self, tmp_path):
        """没接权威就**不长出那几列**：空列会让读者以为「有这一格但没填」。"""
        man = _manifest(tmp_path, [{"name": "支架", "balloon": 1, "bom_item": "BRACKET-01"}],
                        steps=_clean_steps()[:1])
        md = tmp_path / "s.md"
        generate_assembly_steps(md, manifest=str(man), part_name="ASSY-1")
        assert _table(md.read_text(encoding="utf-8"))["1"] == ["1", "支架"]

    def test_declared_but_unbound_line_leaves_the_cells_empty(self, tmp_path):
        """列在（权威接了）但这一行没绑上 ⇒ 格子留空，不写占位符也不拿别的行冒充。"""
        man = _manifest(tmp_path, [{"name": "支架", "balloon": 1, "bom_item": "GHOST"}],
                        steps=_clean_steps()[:1])
        lines = [BomLine(line_id="L-9", bom_id="B-1", tenant_id=TENANT, project_id=PROJECT,
                         item="OTHER", quantity=2.0, unit="pcs")]
        md = tmp_path / "s.md"
        ev = generate_assembly_steps(md, manifest=str(man), part_name="ASSY-1",
                                     bom_lines=lines)
        cells = _table(md.read_text(encoding="utf-8"))["1"]
        assert cells[2:] == ["", "", "", ""], cells
        assert any("GHOST" in msg for msg in ev["assembly_step_issues"])

    def test_material_and_process_never_cover_for_each_other(self, tmp_path):
        """工艺有值、材料没值 ⇒ 材料那格仍留空。顶上去就把缺的那一半盖住了。

        （第 18 片变异电池 M8 注入「material 缺失时拿 process 顶」时本文件全绿，
        这条就是补上的那个样本——电池开火不了不等于判据不存在。）
        """
        man = _manifest(tmp_path, [{"name": "支架", "balloon": 1, "bom_item": "BR"}],
                        steps=_clean_steps()[:1])
        lines = [BomLine(line_id="L-1", bom_id="B-1", tenant_id=TENANT, project_id=PROJECT,
                         item="BR", quantity=2.0, unit="pcs",
                         material=None, process="阳极氧化")]
        md = tmp_path / "s.md"
        generate_assembly_steps(md, manifest=str(man), part_name="ASSY-1", bom_lines=lines)
        cells = _table(md.read_text(encoding="utf-8"))["1"]
        assert cells[2:] == ["2", "pcs", "", "阳极氧化"], cells

    def test_parts_table_carries_every_declared_balloon(self, tmp_path):
        md = tmp_path / "s.md"
        man = _manifest(tmp_path, _two_part_parts(), steps=_clean_steps())
        generate_assembly_steps(md, manifest=str(man), part_name="ASSY-1")
        rows = _table(md.read_text(encoding="utf-8"))
        assert sorted(rows) == ["1", "2"] and rows["2"][1] == "压板"


class TestEvidenceSidecar:
    def test_sidecar_carries_hash_and_coverage(self, tmp_path):
        md = tmp_path / "s.md"
        man = _manifest(tmp_path, _two_part_parts(), steps=_clean_steps())
        ev = generate_assembly_steps(md, manifest=str(man), part_name="ASSY-1")
        side = Path(ev["evidence_file"])
        assert side == tmp_path / "s.md.evidence.json" and side.is_file()
        disk = json.loads(side.read_text(encoding="utf-8"))
        assert disk["manifest_sha256"] == hashlib.sha256(man.read_bytes()).hexdigest()
        assert disk["document_sha256"] == hashlib.sha256(md.read_bytes()).hexdigest()
        assert disk["assembly_steps"]["balloon_coverage"]["unreferenced"] == []
        assert [s["no"] for s in disk["steps"]] == [1, 2]

    def test_evidence_names_what_the_document_does_not_carry(self, tmp_path):
        """证据必须自己说清边界：这份骨架不是作业指导书全文（工时/扭矩/维护都没有）。

        第 81 片翻掉的一项：清单里原本还有「PDF/图框版式」，而第 80 片已经把 PDF 与图框
        交付了——每份带 PDF 的产物都在自称没有 PDF。撤掉它，同时把 PDF 图框标题栏一直
        单独宣称的「检验点与点检项」并进来（同一个事实只留一处来源）。
        """
        md = tmp_path / "s.md"
        man = _manifest(tmp_path, _two_part_parts(), steps=_clean_steps())
        ev = generate_assembly_steps(md, manifest=str(man), part_name="ASSY-1")
        assert ev["not_covered"] == ["维护指引", "工时与工序成本", "扭矩或拧紧值",
                                     "检验点与点检项"]
        assert "PDF/图框版式" not in ev["not_covered"], ev["not_covered"]
        assert "PDF/图框版式" not in md.read_text(encoding="utf-8")

    def test_uncovered_balloon_shows_up_in_evidence_and_markdown(self, tmp_path):
        md = tmp_path / "s.md"
        man = _manifest(tmp_path, _two_part_parts(),
                        steps=[{"no": 1, "action": "只装支架", "balloons": [1]}])
        ev = generate_assembly_steps(md, manifest=str(man), part_name="ASSY-1")
        assert ev["assembly_step_issues"]
        assert "未收口" in md.read_text(encoding="utf-8")


class TestCliSurface:
    def test_cli_writes_the_document(self, tmp_path):
        from aipd_os.cli.main import main

        man = _manifest(tmp_path, _two_part_parts(), steps=_clean_steps())
        md = tmp_path / "cli.md"
        rc = main(["drawing", "assembly-steps", "--manifest", str(man),
                   "--out", str(md), "--part", "ASSY-1"])
        assert rc == 0, rc
        assert md.is_file() and "## 步骤 1" in md.read_text(encoding="utf-8")

    def test_cli_refuses_a_bad_declaration_with_rc2(self, tmp_path):
        from aipd_os.cli.main import main

        man = _manifest(tmp_path, _two_part_parts(),
                        steps=[{"no": 1, "action": "甲", "balloons": [7]}])
        rc = main(["drawing", "assembly-steps", "--manifest", str(man),
                   "--out", str(tmp_path / "x.md"), "--part", "ASSY-1"])
        assert rc == 2

    def test_cli_bom_wiring_needs_both_halves(self, tmp_path):
        from aipd_os.cli.main import main

        man = _manifest(tmp_path, _two_part_parts(), steps=_clean_steps())
        rc = main(["drawing", "assembly-steps", "--manifest", str(man),
                   "--out", str(tmp_path / "x.md"), "--part", "ASSY-1",
                   "--bom", "B-1"])
        assert rc == 2


class TestReleaseManifestSeesTheDocument:
    def _steps(self, tmp_path):
        man = _manifest(tmp_path, _two_part_parts(), steps=_clean_steps())
        md = tmp_path / "assy.md"
        generate_assembly_steps(md, manifest=str(man), part_name="ASSY-1")
        return md

    def _db(self, tmp_path):
        from aipd_os.product_truth.store import ProductTruthStore

        db = tmp_path / "state.db"
        ProductTruthStore(str(db), tenant_id=TENANT, project_id=PROJECT)  # 建库建表
        return db

    def _doc(self, tmp_path, steps, db):
        out = tmp_path / "release.json"
        build_release_manifest(db_path=db, tenant_id=TENANT, project_id=PROJECT,
                               steps_doc=steps, out_path=out)
        return json.loads(out.read_text(encoding="utf-8"))

    def test_key_present_with_matching_hash(self, tmp_path):
        md = self._steps(tmp_path)
        doc = self._doc(tmp_path, md, self._db(tmp_path))
        ref = doc["assembly_instructions"]
        assert ref["sha256"] == hashlib.sha256(md.read_bytes()).hexdigest()
        assert doc["assembly_steps"]["step_count"] == 2
        # 边界要一路带到发布证据里：读 release manifest 的人也得知道这份文档不含什么
        assert "维护指引" in doc["assembly_steps"]["not_covered"]
        assert doc["assembly_steps"]["evidence"]["sha256"]

    def test_uncovered_balloon_blocks_readiness(self, tmp_path):
        man = _manifest(tmp_path, _two_part_parts(),
                        steps=[{"no": 1, "action": "只装支架", "balloons": [1]}])
        md = tmp_path / "gap.md"
        generate_assembly_steps(md, manifest=str(man), part_name="ASSY-1")
        doc = self._doc(tmp_path, md, self._db(tmp_path))
        kinds = [i["kind"] for i in doc["issues"]]
        assert "steps_balloons_uncovered" in kinds, kinds
        one = [i for i in doc["issues"] if i["kind"] == "steps_balloons_uncovered"][0]
        assert one["blocking"] is True and "[2]" in one["detail"], one
        assert doc["assembly_steps"]["unreferenced"] == [2]
        assert doc["assembly_steps"]["step_count"] == 1
        assert doc["ok"] is False

    def test_missing_sidecar_is_blocking(self, tmp_path):
        md = self._steps(tmp_path)
        (tmp_path / "assy.md.evidence.json").unlink()
        doc = self._doc(tmp_path, md, self._db(tmp_path))
        kinds = [i["kind"] for i in doc["issues"]]
        assert "steps_evidence_missing" in kinds, kinds

    def test_no_steps_given_writes_no_key(self, tmp_path):
        """没交文档就不编一个 assembly_instructions 出来——缺席就让它缺席。"""
        doc = self._doc(tmp_path, None, self._db(tmp_path))
        assert "assembly_instructions" not in doc
        assert "assembly_steps" not in doc
