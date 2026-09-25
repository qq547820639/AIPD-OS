"""schema_check 真实校验的回归测试（schema 元校验 + 模板数据校验）。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from aipd_os import schema_binding as sb
from aipd_os.scripts.schema_check import validate_schemas

ROOT = Path(__file__).resolve().parents[1]


def _mk(tmp_path: Path, schema_name: str, schema: dict, data: dict) -> tuple[Path, Path]:
    sd = tmp_path / "assets" / "schemas"
    sd.mkdir(parents=True)
    td = tmp_path / "assets" / "templates"
    td.mkdir(parents=True)
    sp = sd / f"{schema_name}.schema.json"
    sp.write_text(json.dumps(schema), encoding="utf-8")
    dp = td / f"{schema_name}.json"
    dp.write_text(json.dumps(data), encoding="utf-8")
    return sd, dp


def test_schema_check_valid_data_passes(tmp_path):
    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    }
    sd, _ = _mk(tmp_path, "demo", schema, {"name": "ok"})
    assert validate_schemas(sd, tmp_path) == 0


def test_schema_check_invalid_data_fails(tmp_path):
    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    }
    sd, _ = _mk(tmp_path, "demo", schema, {"name": 123})
    assert validate_schemas(sd, tmp_path) == 1


def test_schema_check_invalid_schema_fails(tmp_path):
    # 非合法 JSON Schema：type 必须是合法值
    bad = {"$schema": "http://json-schema.org/draft-07/schema#", "type": "not-a-type"}
    sd, _ = _mk(tmp_path, "demo", bad, {})
    assert validate_schemas(sd, tmp_path) >= 1


# ---------------------------------------------------------------------------
# 第 30 片：三态报告、跨文件 $ref、以及按方言元校验
# ---------------------------------------------------------------------------

D2020 = "https://json-schema.org/draft/2020-12/schema"


def _mk_pair(tmp_path, *, with_instance: bool):
    sd = tmp_path / "assets" / "schemas"
    td = tmp_path / "assets" / "templates"
    sd.mkdir(parents=True)
    td.mkdir(parents=True)
    (sd / "inner.schema.json").write_text(json.dumps({
        "$schema": D2020, "type": "object", "required": ["key"],
        "properties": {"key": {"type": "string", "minLength": 1}}}), encoding="utf-8")
    (sd / "outer.schema.json").write_text(json.dumps({
        "$schema": D2020, "type": "object",
        "properties": {"items": {"type": "array",
                                 "items": {"$ref": "inner.schema.json"}}}}),
        encoding="utf-8")
    if with_instance:
        # inner 也是 schemas/ 里的一份契约 ⇒ 它自己得有实例，否则 UNBOUND 会先替它红一条
        (td / "inner.json").write_text(json.dumps({"key": "k"}), encoding="utf-8")
        (td / "outer.json").write_text(json.dumps({"items": [{"key": "k"}]}),
                                       encoding="utf-8")
    return sd


class TestUnboundIsANamedFinding:
    def test_a_contract_without_instance_no_longer_reports_green(self, tmp_path, capsys):
        """旧行为：`INFO …（跳过数据校验）` 然后 rc=0。今天必须计一条失败。"""
        sd = _mk_pair(tmp_path, with_instance=True)
        (tmp_path / "assets" / "templates" / "outer.json").unlink()
        assert validate_schemas(sd, tmp_path) >= 1
        out = capsys.readouterr().out
        assert "UNBOUND outer.schema.json" in out
        assert "INFO" not in out, "跳过就是 INFO 那条老路，不该还在"

    def test_the_compliant_side_stays_green(self, tmp_path):
        """配对反证：都有实例时必须 0 失败，否则上面那条红只是「多报」。"""
        assert validate_schemas(_mk_pair(tmp_path, with_instance=True), tmp_path) == 0

    def test_an_exemption_has_to_be_named(self, tmp_path, monkeypatch):
        """豁免必须是**具名**的：进了表才降级，且输出里看得见理由。"""
        import aipd_os.scripts.schema_check as sc
        sd = _mk_pair(tmp_path, with_instance=True)
        (tmp_path / "assets" / "templates" / "outer.json").unlink()
        monkeypatch.setitem(sc.UNBOUND_EXEMPT, "outer.schema.json", "只有对侧产这个文件")
        assert validate_schemas(sd, tmp_path) == 0

    def test_the_shipped_repo_has_no_unbound_contract_left(self, capsys):
        """真仓读数：五份契约今天都有实例被按约定校验过。"""
        assert validate_schemas(ROOT / "assets" / "schemas", ROOT) == 0
        out = capsys.readouterr().out
        assert "UNBOUND" not in out and "EXEMPT" not in out
        assert out.count("OK   assets/templates/") == 5, out


class TestCrossFileRefsAreResolved:
    def test_a_ref_violation_in_a_sibling_schema_is_caught(self, tmp_path, capsys):
        """裸 `jsonschema.validate` 解不开跨文件 `$ref`（实测抛 Unresolvable）。

        现在必须**跟着引用判形状**：`key` 为空串违 `inner` 的 minLength ⇒ 判 FAIL。
        """
        sd = _mk_pair(tmp_path, with_instance=True)
        (tmp_path / "assets" / "templates" / "outer.json").write_text(
            json.dumps({"items": [{"key": ""}]}), encoding="utf-8")
        assert validate_schemas(sd, tmp_path) >= 1
        out = capsys.readouterr().out
        assert "FAIL assets/templates/outer.json <- outer.schema.json" in out
        assert "['items', 0, 'key']" in out, "违的是兄弟契约里的 key.minLength，路径要指到位"

    def test_a_dangling_ref_reports_unreadable_not_valid(self, tmp_path, capsys):
        """引用指向不存在的文件 ⇒ `UNREADABLE`：不能说文档合法，也不能说它违规。"""
        sd = _mk_pair(tmp_path, with_instance=True)
        (sd / "dangling.schema.json").write_text(json.dumps({
            "$schema": D2020, "type": "object",
            "properties": {"x": {"$ref": "nowhere.schema.json"}}}), encoding="utf-8")
        (tmp_path / "assets" / "templates" / "dangling.json").write_text(
            json.dumps({"x": 1}), encoding="utf-8")
        assert validate_schemas(sd, tmp_path) >= 1
        assert "UNREADABLE" in capsys.readouterr().out

    def test_the_real_checkpoint_ref_is_followed(self, capsys):
        """`project_checkpoint` 的 `$defs.fact` 现在是外部引用；模板里带 `fact_id`
        才过 ⇒ 引用真的被解析了（不是被忽略）。"""
        assert validate_schemas(ROOT / "assets" / "schemas", ROOT) == 0
        assert "assets/templates/project_checkpoint.json <- project_checkpoint.schema.json" \
            in capsys.readouterr().out


class TestCheckpointContractSemantics:
    """`$defs.fact` 单源化之后，checkpoint 这张契约**本身**的两条应然。"""

    def _checkpoint(self, fact: dict) -> dict:
        raw = (ROOT / "assets" / "templates" / "project_checkpoint.json") \
            .read_text(encoding="utf-8")
        doc: dict = json.loads(raw)
        doc["facts"] = [fact]
        return doc

    def test_a_u_status_fact_is_legal_under_the_checkpoint_contract(self):
        """权威 `FACT_STATUSES` 含 U，产品在产 U ⇒ checkpoint 不许把 U 判非法。

        修之前内联副本的 enum 缺 U，这条正是红的样子。
        """
        r = sb.validate_document(str(ROOT), "project_checkpoint.schema.json",
                              self._checkpoint({"fact_id": "F-1", "key": "k",
                                                "value": 1, "status": "U"}))
        assert r["status"] == "valid", r["errors"]

    def test_the_checkpoint_still_demands_its_own_fact_id(self):
        """单源化不许丢掉 checkpoint 侧多出来的要求：裸 `$ref` 那一档就是丢在这里。"""
        r = sb.validate_document(str(ROOT), "project_checkpoint.schema.json",
                              self._checkpoint({"key": "k", "value": 1, "status": "U"}))
        assert r["status"] == "invalid"
        assert any("fact_id" in e for e in r["errors"]), r["errors"]

    def test_the_shape_is_declared_once(self):
        """同一个 fact 形状在盘上只许有一处声明（副本必然漂移）。"""
        sites = sb.shape_sites(ROOT, "fact")
        assert [s["at"] for s in sites] == ["(顶层)"], sites


class TestMetaValidationUsesTheDeclaredDialect:
    """五份契约都写 2020-12。拿 Draft7 去元校验会漏掉只有新方言看得出的问题。"""

    @pytest.mark.parametrize("body,keyword", [
        ({"type": "array", "prefixItems": 5}, "prefixItems"),
        ({"unevaluatedProperties": "x"}, "unevaluatedProperties"),
    ])
    def test_a_2020_12_only_defect_now_fires(self, tmp_path, body, keyword, capsys):
        schema = {"$schema": D2020, **body}
        sd, _ = _mk(tmp_path, "dialect", schema, {})
        assert validate_schemas(sd, tmp_path) >= 1, \
            f"{keyword} 在 Draft7 元校验里是未知关键字（实测放行），按方言必须红"
        assert "dialect.schema.json (schema)" in capsys.readouterr().out

    def test_both_drafts_agree_on_the_shipped_five(self):
        """这五份在两个方言下都合法 ⇒ 换方言今天 0 处翻红，但**两条判据不等价**。

        上面那条注入是「哪一类只有新方言抓得到」的必开火对照。
        """
        import jsonschema

        for path in sorted((ROOT / "assets" / "schemas").glob("*.schema.json")):
            doc = json.loads(path.read_text(encoding="utf-8"))
            jsonschema.validators.Draft7Validator.check_schema(doc)
            jsonschema.validators.Draft202012Validator.check_schema(doc)

