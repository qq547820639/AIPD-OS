"""接口清单与契约证据（第 29 片）：分母必须重算，「被引用」不等于「被验证」。

这一格以前是 C6 普查里唯一的零实现项。真正的 ICD 要含「责任与变更授权」与「接口职责」，
那两段只能由对侧给 ⇒ 本仓单方产一份叫 ICD 的文件等于伪造签署。
这里做的是可自查的那一半：**接口清单 + 每条定义件的哈希 + 每条的取证用例 + 写明证不到什么**。

用例分两类，缺一类就是自说自话：
- **重算类**：清单里的条数必须由独立路径数出来（`PUBLIC_COMMANDS`、AST 里的 `def mcp_*`、
  目录实际文件），否则改名那天就漏项；
- **两向反证**：孤儿 schema 必须被抓到（must-fire），同一契约被真引用时必须**不**被抓
  （must-not-fire）；`verified_by` 的 AST 解析必须与 `pytest --collect-only` 的真读数对齐。
"""
from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from aipd_os import schema_binding as sb
from aipd_os.interface_contract import (
    CONTRACT_KIND,
    INSTRUMENT_FILES,
    PROVES,
    build,
    resolve_tests,
    schema_findings,
    schema_rows,
    verdict_of,
    verdict_rc,
    write,
)

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def doc() -> dict:
    return build(str(REPO))


class TestDenominatorsAreRecomputed:
    def test_cli_rows_are_exactly_the_public_command_surface(self, doc):
        sys.path.insert(0, str(REPO / "src"))
        from aipd_os.cli.command_contract import PUBLIC_COMMANDS

        rows = [r for r in doc["interfaces"] if r["kind"] == "cli_command"]
        assert {r["name"] for r in rows} == set(PUBLIC_COMMANDS), \
            "清单少一条或多一条，都说明它是抄来的而不是算出来的"
        assert len(rows) == doc["counts"]["by_kind"]["cli_command"]

    def test_mcp_rows_come_from_the_server_source_itself(self, doc):
        tree = ast.parse((REPO / "state_service" / "mcp_server.py").read_text(encoding="utf-8"))
        tools = {n.name[len("mcp_"):] for n in tree.body
                 if isinstance(n, ast.FunctionDef) and n.name.startswith("mcp_")}
        rows = {r["name"] for r in doc["interfaces"] if r["kind"] == "mcp_tool"}
        assert rows == tools and tools, "MCP 工具数必须是数出来的，不是写在文档里的"

    def test_schema_rows_are_the_files_actually_on_disk(self, doc):
        on_disk = {p.name for p in (REPO / "assets" / "schemas").glob("*.json")}
        rows = {r["name"] for r in doc["interfaces"] if r["kind"] == "json_schema"}
        assert rows == on_disk

    def test_every_row_declares_both_what_it_proves_and_what_it_does_not(self, doc):
        for row in doc["interfaces"]:
            assert row["proves"] and row["does_not_prove"], row["id"]
            assert row["proves"] != row["does_not_prove"], row["id"]
        assert set(doc["counts"]["by_kind"]) <= set(PROVES), \
            "新增一类接口却没写「这一类一般证不到什么」"

    def test_row_ids_are_unique(self, doc):
        ids = [r["id"] for r in doc["interfaces"]]
        assert len(ids) == len(set(ids)), "同一条接口被记两次 ⇒ 条数看着更多，覆盖却没变"


class TestDefinitionArtifacts:
    def test_every_defined_artifact_exists_and_its_hash_is_recorded(self, doc):
        recorded = doc["definition_digests"]
        for row in doc["interfaces"]:
            for rel in row["defines"]:
                path = REPO / rel
                assert path.is_file(), f"{row['id']} 指向不存在的定义件 {rel}"
                assert recorded[rel] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert doc["missing_defines"] == []

    def test_a_define_pointing_nowhere_is_a_blocking_finding(self, tmp_path, monkeypatch):
        """定义件不在盘上 ⇒ 进 missing_defines，且与 --strict 无关必拦。

        注入方式：换掉文件格式契约里的一条定义件，不动仓里的真文件。
        """
        import aipd_os.interface_contract as ic

        assert ic.schema_rows(tmp_path) == [], "空目录不该凭空长出 schema 行"
        broken = [dict(spec) for spec in ic.FILE_FORMAT_CONTRACTS]
        broken[0]["defines"] = ["src/aipd_os/definitely_not_here.py"]
        monkeypatch.setattr(ic, "FILE_FORMAT_CONTRACTS", broken)
        doc = ic.build(str(REPO))
        hits = [m for m in doc["missing_defines"] if "definitely_not_here" in m]
        assert hits, doc["missing_defines"]
        assert doc["verdict"] == "incomplete"
        assert ic.verdict_rc(doc, strict=False) == 4


class TestVerifiedByMustResolve:
    def test_a_cited_test_file_must_exist_and_collect_something(self, doc):
        for row in doc["interfaces"]:
            for hit in row["verified_by_resolved"]:
                assert hit["tests"] > 0, row["id"]
                assert (REPO / hit["spec"].split("::")[0]).is_file(), row["id"]

    def test_an_empty_test_file_is_not_evidence(self, tmp_path):
        """文件在、但一个 test 都没有 ⇒ 不算取证。（尺子自己有项空注入的毛病就白搭。）"""
        (tmp_path / "tests").mkdir()
        blank = tmp_path / "tests" / "test_blank.py"
        blank.write_text("X = 1\n", encoding="utf-8")
        assert resolve_tests(tmp_path, "tests/test_blank.py") == (False, 0)

    def test_missing_or_renamed_test_lands_in_unverified_not_silently_passed(self, doc):
        assert resolve_tests(REPO, "tests/test_definitely_not_here.py") == (False, 0)
        ok, n = resolve_tests(REPO, "tests/test_delivery_baseline.py::NoSuchClass")
        assert not ok, "AST 解析若不看类名，改名后的测试会被当成还在"
        ok2, n2 = resolve_tests(REPO, "tests/test_delivery_baseline.py::TestSemanticDigest")
        assert ok2 and n2 >= 5

    def test_ast_resolution_agrees_with_pytest_collection(self, tmp_path):
        """AST 这套自制的解析必须与 pytest 自己的收集结果对齐（边界对象复核）。"""
        spec = "tests/test_delivery_baseline.py"
        proc = subprocess.run([sys.executable, "-m", "pytest", spec, "--collect-only", "-q"],
                              cwd=REPO, capture_output=True, text=True, timeout=300)
        collected = [ln for ln in proc.stdout.splitlines() if "::" in ln]
        assert collected, proc.stdout[-400:]
        ok, count = resolve_tests(REPO, spec)
        assert ok and count == len(collected), (count, len(collected))
        # must-not-fire 一侧：真实存在的一个用例名必须解析成功
        real = collected[0].split("::", 1)[1].replace("()", "")
        assert resolve_tests(REPO, f"{spec}::{real}")[0] is True
        assert resolve_tests(REPO, f"{spec}::{real}X")[0] is False


class TestContractValidationCoverage:
    """契约**被谁校验**这一格：第 29 片按文件名字面量反查，看不见命名约定绑定。"""

    def _fake(self, tmp_path, *, dirs='("templates", "assets/templates")'):
        (tmp_path / "assets" / "schemas").mkdir(parents=True)
        scripts = tmp_path / "src" / "aipd_os" / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "schema_check.py").write_text(
            f"DATA_DIRS = {dirs}\n", encoding="utf-8")
        # build() 的 MCP 分母要求真文件在（读不到就该崩，不该静默给 0 条）
        state = tmp_path / "state_service"
        state.mkdir()
        (state / "mcp_server.py").write_text("def mcp_noop():\n    return None\n",
                                             encoding="utf-8")
        return tmp_path

    def test_convention_bound_schema_is_not_an_orphan(self, tmp_path):
        """按约定绑定的那张**不许**进「没有实例被按它校验过」。

        第 29 片的假阳性正是这条：`schema_check` 里从没出现过文件名
        `manual_chain_state.schema.json` 这个字面量，按名字反查必然读不到。
        """
        repo = self._fake(tmp_path)
        schemas = repo / "assets" / "schemas"
        (schemas / "bound_by_convention.schema.json").write_text(
            '{"type":"object"}', encoding="utf-8")
        (schemas / "never_exercised.schema.json").write_text(
            '{"type":"object"}', encoding="utf-8")
        (repo / "assets" / "templates").mkdir()
        (repo / "assets" / "templates" / "bound_by_convention.json").write_text(
            "{}", encoding="utf-8")
        rows = {r["name"]: r for r in schema_rows(repo)}
        assert rows["bound_by_convention.schema.json"]["validated_against"] == \
            ["assets/templates/bound_by_convention.json"]
        assert rows["never_exercised.schema.json"]["validated_against"] == []
        # 字面引用一栏仍然如实记着「没人提到过这个名字」——那是另一件事
        assert rows["bound_by_convention.schema.json"]["consumers"] == []
        found = schema_findings(list(rows.values()))
        assert found["without_instance"] == ["never_exercised.schema.json"]
        assert found["blind"] == []

    def test_a_read_validator_is_required_before_claiming_coverage(self, tmp_path):
        """抽不出约定（`schema_check.py` 不在）⇒ 报**盲区**。

        不许读成「有绑定」，也不许读成「没问题」。
        """
        repo = self._fake(tmp_path)
        (repo / "src" / "aipd_os" / "scripts" / "schema_check.py").unlink()
        (repo / "assets" / "schemas" / "x.schema.json").write_text('{"type":"object"}',
                                                                   encoding="utf-8")
        rows = {r["name"]: r for r in schema_rows(repo)}
        assert rows["x.schema.json"]["binding_readable"] is False
        assert rows["x.schema.json"]["validated_against"] == []
        found = schema_findings(list(rows.values()))
        assert found["blind"] == ["x.schema.json"]
        assert found["without_instance"] == [], "读不到时不臆断谁没校验"

    def test_a_validator_without_the_constant_is_still_blind(self, tmp_path):
        """校验器脚本在、但抽不出 `DATA_DIRS`（改名/挪走）⇒ 同样算盲区。

        补这条是因为上一格只测了「文件不在」那一支：`binding_dirs` 里那是两个不同的
        return，把「抽不到」折成「抽到空」时前一支用例不会红。
        """
        repo = self._fake(tmp_path)
        (repo / "src" / "aipd_os" / "scripts" / "schema_check.py").write_text(
            "X = 1\n", encoding="utf-8")
        (repo / "assets" / "schemas" / "y.schema.json").write_text('{"type":"object"}',
                                                                   encoding="utf-8")
        rows = {r["name"]: r for r in schema_rows(repo)}
        assert rows["y.schema.json"]["binding_readable"] is False
        found = schema_findings(list(rows.values()))
        assert found["blind"] == ["y.schema.json"] and found["without_instance"] == []

    def test_the_landing_axis_is_actually_wired_into_the_verdict(self, monkeypatch):
        """落点那一格不许只是文档里的一段字：它得能单独把判定压成 incomplete。"""
        import aipd_os.interface_contract as ic
        monkeypatch.setattr(ic.sb, "landing_sites", lambda repo: [
            {"artifact": "state/project_checkpoint.json", "gate": "scripts/x.py:1",
             "schema": "project_checkpoint.schema.json"}])
        doc = build(str(REPO))
        assert doc["landing_existence_only"] == \
            ["state/project_checkpoint.json ← scripts/x.py:1"]
        assert doc["counts"]["landing_existence_only"] == 1
        # 判定这一格交给下面的 TestEachAxisIsSolelyLoadBearing 逐轴钉：整体断 incomplete
        # 会被「别的轴本来就脏」掩盖（电池抓过一次这种假测）。

    def test_the_binding_dirs_come_from_the_validator_not_a_copy(self, tmp_path):
        """校验器改了约定 ⇒ 清单跟着变（抄一份常量就会在这里露馅）。"""
        repo = self._fake(tmp_path, dirs='("somewhere", "assets/templates")')
        schemas = repo / "assets" / "schemas"
        (schemas / "moved.schema.json").write_text('{"type":"object"}', encoding="utf-8")
        (repo / "somewhere").mkdir()
        (repo / "somewhere" / "moved.json").write_text("{}", encoding="utf-8")
        assert schema_rows(repo)[0]["validated_against"] == ["somewhere/moved.json"]

    def test_the_shipped_document_has_no_unexercised_contract(self, doc):
        """今天真读数：五份契约都有实例被按约定校验过。must-not-fire 的一侧。"""
        assert doc["contracts_without_instance"] == []
        assert doc["binding_blind"] == []
        for row in doc["interfaces"]:
            if row["kind"] == "json_schema":
                assert row["validated_against"], f"{row['name']} 的实例又没了？这行要改判"

    def test_fact_contract_is_now_actually_exercised(self, doc):
        """`fact.schema.json` 是第 29 片留下的那一格：从今天起有实例被按它校验。"""
        row = next(r for r in doc["interfaces"]
                   if r["name"] == "fact.schema.json")
        assert row["validated_against"] == ["assets/templates/fact.json"]


class TestInstrumentNotInItsOwnDenominator:
    def test_the_listing_module_and_its_own_test_are_not_consumers(self, doc):
        """本模块的文案与本用例的断言里都写着 `aipd_os.net.http`，两条都不许进分母。

        这条是被咬出来的：先在清单里出现「量具自己数成一个消费者」，
        再在补了断言之后发现**分母从 11 涨到 12**——写一条断言就把被测量加一。
        """
        names = [r["name"] for r in doc["interfaces"] if r["kind"] == "egress_consumer"]
        for rel in INSTRUMENT_FILES:
            assert rel not in names, f"{rel} 是量具自己，不是产品消费者"
        assert "src/aipd_os/net/http.py" not in names

    def test_the_instrument_registry_names_files_that_exist(self):
        """排除表会随改名腐化：表里每个路径必须真在盘上，且正好是「模块 + 它的用例」。"""
        root = Path(__file__).resolve().parents[1]
        for rel in INSTRUMENT_FILES:
            assert (root / rel).is_file(), f"排除表里的 {rel} 已经不在了，该删就删"
        assert INSTRUMENT_FILES[0] == "src/aipd_os/interface_contract.py"
        assert INSTRUMENT_FILES[1] == Path(__file__).relative_to(root).as_posix()

    def test_naming_a_contract_here_is_not_evidence_it_was_verified(self, doc):
        """第三个面：本用例文件点了 `manual_chain_state.schema.json` 这个名字，
        但那不许被当成「这张契约被某个消费方验过」。取证要么走真消费方的用例，
        要么就留在 `unverified` 里。"""
        assert "manual_chain_state.schema.json" in " ".join(doc["unverified"]), doc["unverified"]
        row = next(r for r in doc["interfaces"]
                   if r["name"] == "manual_chain_state.schema.json")
        specs = [v["spec"] for v in row["verified_by_resolved"]]
        assert "tests/test_interface_contract.py" not in specs
        # 而真消费方点了它，就必须算进去（否则这一栏会因为过度排除而假装没人验）
        cp = next(r for r in doc["interfaces"]
                  if r["name"] == "project_checkpoint.schema.json")
        assert [v["spec"] for v in cp["verified_by_resolved"]], cp["name"]

    def test_production_and_test_consumers_are_counted_apart(self, doc):
        """混在一个 kind 里数，「产品侧有几个消费者」这句话就读不出来。"""
        rows = [r for r in doc["interfaces"] if r["kind"] == "egress_consumer"]
        prod = [r for r in rows if r["layer"] == "production"]
        test = [r for r in rows if r["layer"] == "test"]
        assert len(prod) + len(test) == len(rows), "有行没被归层"
        assert len(prod) == 8 and len(test) == 3, \
            "今天的真读数：8 个产品模块 + 3 个用例；变了就改这行并注明为什么"
        assert all(r["name"].startswith("tests/") for r in test)
        assert all(not r["name"].startswith("tests/") for r in prod)



class TestLandingSitesAxis:
    """另一条新轴：产物落点**只判存在**、有契约却没核形状。"""

    def test_the_probe_fires_on_an_existence_only_gate(self, tmp_path):
        repo = tmp_path
        (repo / "assets" / "schemas").mkdir(parents=True)
        (repo / "assets" / "schemas" / "thing.schema.json").write_text(
            '{"type":"object"}', encoding="utf-8")
        scripts = repo / "scripts"
        scripts.mkdir()
        (scripts / "gate.py").write_text(
            "ok = exists(root, 'state/thing.json')\n", encoding="utf-8")
        sites = sb.landing_sites(repo)
        assert sites == [{"artifact": "state/thing.json",
                          "gate": "scripts/gate.py:1",
                          "schema": "thing.schema.json"}]

    def test_the_shipped_repo_has_no_existence_only_landing_left(self, doc):
        """must-not-fire 的一侧：checkpoint 那个落点今天已经改成核形状了。

        这一格变空**不是**因为探针看不见——上面那条注入证明它认得这个形状；
        是因为 `scripts/outcome_acceptance.py` 里那句 `exists(root, 'state/…')`
        换成了形状判定，探针自然不再报它。
        """
        assert doc["landing_existence_only"] == []
        assert all(s["schema"] is None for s in doc["artifact_landing_sites"]), \
            "还有落点带着同名契约却只判存在"



class TestShapeAuthorityAxis:
    """同一形状两处声明时，真值是数据库那一套枚举，不是两份 schema 互比。"""

    def test_today_the_fact_shape_agrees_with_the_db_authority(self, doc):
        """must-not-fire 的一侧：副本已删，声明只剩一处且与权威一致。"""
        authority = doc["shape_authority"]
        assert authority["authority_readable"] is True
        assert authority["authority_source"] == "src/aipd_os/state/db.py:FACT_STATUSES"
        assert authority["divergent"] == []
        assert [s["schema"] for s in authority["sites"]] == ["fact.schema.json"]
        assert "U" in authority["authority"]

    def test_an_unreadable_authority_is_not_folded_into_agreement(self, tmp_path):
        """有文件、没常量 ⇒ `authority_readable=False`；差集留空是「不知道」。"""
        (tmp_path / "assets" / "schemas").mkdir(parents=True)
        (tmp_path / "assets" / "schemas" / "fact.schema.json").write_text(json.dumps(
            {"type": "object", "properties": {"status": {"enum": ["V", "S"]}}}),
            encoding="utf-8")
        db = tmp_path / "src" / "aipd_os" / "state"
        db.mkdir(parents=True)
        (db / "db.py").write_text("X = 1\n", encoding="utf-8")
        got = sb.shape_vs_authority(tmp_path)
        assert got["authority_readable"] is False
        assert [s["schema"] for s in got["sites"]] == ["fact.schema.json"]
        assert got["divergent"] == [] and got["authority"] is None
        values, source = sb.fact_status_authority(tmp_path)
        assert values is None and "没有 FACT_STATUSES" in source, \
            "常量不在时不许凭空有一套枚举"

    def test_an_unreadable_authority_makes_the_verdict_incomplete(self, monkeypatch):
        """读不到权威这一格进 `shape_blind`，判定只能是 incomplete。"""
        import aipd_os.interface_contract as ic
        monkeypatch.setattr(ic.sb, "shape_vs_authority", lambda repo, shape="fact": {
            "shape": shape, "authority": None, "authority_source": "读不到",
            "authority_readable": False,
            "sites": [{"schema": "fact.schema.json", "at": "(顶层)",
                       "status": "valid", "enum": ["V"]}],
            "divergent": [], "unreadable": []})
        doc = build(str(REPO))
        assert doc["counts"]["shape_authority_blind"] == 1
        assert doc["verdict"] == "incomplete"

    def test_a_copy_that_drifts_from_the_authority_is_named(self, monkeypatch):
        """副本缺 U 的原始样子必须被点名到**哪一份哪一处**（第 29 片留下的缺陷形状）。"""
        import aipd_os.interface_contract as ic
        monkeypatch.setattr(ic.sb, "shape_vs_authority", lambda repo, shape="fact": {
            "shape": shape, "authority": ["R", "S", "T", "U", "V"],
            "authority_source": "x", "authority_readable": True,
            "sites": [{"schema": "project_checkpoint.schema.json", "at": "$defs/fact",
                       "status": "valid", "enum": ["R", "S", "T", "V"],
                       "missing_vs_authority": ["U"], "extra_vs_authority": []}],
            "divergent": ["project_checkpoint.schema.json#$defs/fact"], "unreadable": []})
        doc = build(str(REPO))
        assert doc["counts"]["shape_divergent"] == 1
        assert doc["verdict"] == "incomplete"


AXES = ["unverified", "missing_defines", "without_instance", "binding_blind",
        "existence_only", "shape_divergent", "shape_blind"]


class TestEachAxisIsSolelyLoadBearing:
    """七个轴**各自单独**都得能压住判定。

    只测整体（「今天这份文档是 incomplete」）时，任何一格从 `or` 串里删掉都照样红，
    因为别的格子本来就脏——第 30 片的电池正是这样放过两条注入的，故拆成逐轴。
    """

    @pytest.mark.parametrize("axis", AXES)
    def test_one_dirty_axis_alone_decides_incomplete(self, axis):
        kwargs = {a: [] for a in AXES}
        kwargs[axis] = ["某一条"]
        assert verdict_of(**kwargs) == "incomplete", f"{axis} 这一格没接进判定"

    def test_all_clean_is_the_only_complete_reading(self):
        assert verdict_of(**{a: [] for a in AXES}) == "complete"


class TestVerdictAndExitCodes:
    def test_three_state_exit_does_not_fold_cannot_tell_into_pass(self):
        complete = {"verdict": "complete", "missing_defines": []}
        incomplete = {"verdict": "incomplete", "missing_defines": []}
        broken = {"verdict": "incomplete", "missing_defines": ["json_schema:x → gone"]}
        assert verdict_rc(complete, strict=False) == 0
        assert verdict_rc(incomplete, strict=False) == 0, "默认不拦，但发现已写进文档"
        assert verdict_rc(incomplete, strict=True) == 4, "开 --strict 就得拦"
        assert verdict_rc(broken, strict=False) == 4, "定义件不在盘上 ⇒ 与 strict 无关，必拦"


class TestCliSurface:
    def test_command_writes_document_and_sidecar_with_matching_hash(self, tmp_path, capsys):
        from aipd_os.cli.main import main

        out = tmp_path / "interfaces.json"
        rc = main(["interfaces", "--repo", str(REPO), "--out", str(out)])
        capsys.readouterr()
        assert rc == 0
        sidecar = Path(str(out) + ".evidence.json")      # 侧车拼法 = 产物全名 + .evidence.json
        assert out.is_file() and sidecar.is_file()
        doc = json.loads(out.read_text(encoding="utf-8"))
        side = json.loads(sidecar.read_text(encoding="utf-8"))
        assert doc["kind"] == CONTRACT_KIND
        assert side["document_sha256"] == hashlib.sha256(out.read_bytes()).hexdigest()
        assert side["verdict"] == doc["verdict"] == "incomplete"

    def test_strict_flag_flips_the_exit_code_on_the_same_document(self, tmp_path, capsys):
        from aipd_os.cli.main import main

        out = tmp_path / "i.json"
        loose = main(["interfaces", "--repo", str(REPO), "--out", str(out)])
        capsys.readouterr()
        strict = main(["interfaces", "--repo", str(REPO), "--out", str(out), "--strict"])
        capsys.readouterr()
        assert loose == 0 and strict == 4

    def test_the_document_refuses_the_icd_label(self, doc):
        """这份东西**不叫** ICD，理由必须随文档走：只留一个标题，改名只需要一行字。"""
        assert "不叫 ICD" in doc["title"] or "不是 ICD" in doc["title"]
        assert "伪造签署" in doc["not_icd_because"]

    def test_write_uses_the_single_sidecar_spelling(self, tmp_path):
        from aipd_os.cad.evidence import sidecar_path

        target = tmp_path / "assy.step"
        doc = build(str(REPO))
        write(doc, target)
        assert sidecar_path(target) == tmp_path / "assy.step.evidence.json"
        assert (tmp_path / "assy.step.evidence.json").is_file()
