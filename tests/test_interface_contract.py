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

from aipd_os.interface_contract import (
    CONTRACT_KIND,
    PROVES,
    build,
    resolve_tests,
    schema_rows,
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


class TestOrphanSchemasAreFindings:
    def test_an_unreferenced_schema_is_reported_not_passed(self, tmp_path):
        schemas = tmp_path / "assets" / "schemas"
        schemas.mkdir(parents=True)
        (schemas / "orphan.schema.json").write_text('{"type":"object"}', encoding="utf-8")
        (schemas / "used.schema.json").write_text('{"type":"object"}', encoding="utf-8")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "user.py").write_text(
            'x = "assets/schemas/used.schema.json"\n', encoding="utf-8")
        rows = {r["name"]: r for r in schema_rows(tmp_path)}
        assert rows["orphan.schema.json"]["consumers"] == []
        assert "src/user.py" in rows["used.schema.json"]["consumers"], \
            "反查若不认得真引用，孤儿清单就是一张假清单"

    def test_the_shipped_document_names_its_own_orphans(self, doc):
        """今天这份真清单读数不许悄悄变好或变坏：孤儿 schema 一栏是**登记过的事实**。"""
        assert doc["declared_but_unconsumed"], "三个 schema 的引用被加进来了？那这行要改判"
        # must-not-fire 一侧：真被引用的那张不许一起躺进孤儿清单，
        # 否则「反查消费者」这条判据坏掉时，孤儿清单会整栏膨胀而没人看得出。
        assert "cad_contract.schema.json" not in doc["declared_but_unconsumed"]
        assert "fact.schema.json" not in doc["declared_but_unconsumed"]
        for name in doc["declared_but_unconsumed"]:
            assert any(r["kind"] == "json_schema" and r["name"] == name
                       and not r.get("consumers") for r in doc["interfaces"])
        assert doc["verdict"] == "incomplete"


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
