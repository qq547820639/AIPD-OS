"""v5.10 验证 / Issue / 就绪度 这 8 条命令的真实 CLI 面（F-CLI-01 的补账）。

接线前的实测：`build_parser()` 的 choices 里没有 `validation` / `issue` / `readiness`，
`aipd validation import` 直接 `invalid choice` —— 但 `COMMAND_FUNCS`、`command_contract`
的 PUBLIC 表、SKILL.md 的逐条声明三处都写着它们。三份内部副本互相对表，
所以谁也没发现这条命令在产品面上不存在。

这里一律走 `main(argv)`：既验证解析器接上了，也验证参数形状与函数真的对得上
（`args.stage.upper()`、`args.id`、`--plan-id`→`args.plan_id` 这类细节只有真跑才暴露）。
"""
from __future__ import annotations

import json
from pathlib import Path

from aipd_os.cli._helpers import DEFAULT_TENANT
from aipd_os.cli.main import main
from aipd_os.state.db import AIPDStateDB

T = DEFAULT_TENANT


def _project(tmp_path) -> str:
    db_path = Path(tmp_path) / "state.db"
    db = AIPDStateDB(str(db_path))
    db.ensure_default_tenant(T)
    db.init_project(T, "P-1", "支架项目", "把支架做成可开模的量产件")
    return str(db_path)


def _run(argv, capsys, *, expect: int = 0) -> dict:
    capsys.readouterr()
    rc = main(argv)
    out = capsys.readouterr().out.strip()
    assert rc == expect, f"rc={rc}（期望 {expect}）：{out}"
    payload: dict = json.loads(out) if out.startswith("{") else {}
    return payload


def _deliverable_status(db_path: str, deliverable_id: str) -> str:
    db = AIPDStateDB(db_path)
    row = next(d for d in db.list_deliverables(T, "P-1")
               if d["deliverable_id"] == deliverable_id)
    return str(row["status"])


def _lab(tmp_path, verdict: str) -> str:
    lab = Path(tmp_path) / "lab.csv"
    lab.write_text(
        "stage,test_item,sample_id,result,pass_fail,notes\n"
        f"dvt,支架,S1,0.4,{verdict},拉力不足\n", encoding="utf-8")
    return str(lab)


class TestValidationSurface:
    def test_plan_list_show_roundtrip(self, tmp_path, capsys):
        db_path = _project(tmp_path)
        made = _run(["validation", "plan", "--db", db_path, "--project", "P-1",
                     "--stage", "dvt", "--title", "DVT 结构验证",
                     "--objective", "验证支架拉力", "--json"], capsys)
        plan_id = made["plan"]["plan_id"]
        assert plan_id

        listed = _run(["validation", "list", "--db", db_path, "--project", "P-1",
                       "--what", "plans", "--json"], capsys)
        assert [p["plan_id"] for p in listed["items"]] == [plan_id]

        shown = _run(["validation", "show", "--db", db_path, "--project", "P-1",
                      "--what", "plan", "--id", plan_id, "--json"], capsys)
        assert shown["item"]["title"] == "DVT 结构验证"

    def test_show_missing_id_exits_nonzero(self, tmp_path, capsys):
        db_path = _project(tmp_path)
        out = _run(["validation", "show", "--db", db_path, "--project", "P-1",
                    "--what", "plan", "--id", "VP-NOPE", "--json"], capsys,
                   expect=1)
        assert out["ok"] is False

    def test_import_passing_data_is_clean(self, tmp_path, capsys):
        db_path = _project(tmp_path)
        out = _run(["validation", "import", "--db", db_path, "--project", "P-1",
                    "--stage", "dvt", "--file", _lab(tmp_path, "pass"), "--json"],
                   capsys)
        assert out["result"]["records_imported"] == 1
        assert out["result"]["failing_items"] == []
        assert out["impact"] is None

    def test_import_failure_creates_issue_and_propagates_impact(self, tmp_path, capsys):
        """Issue 与影响传播必须来自同一次导入（此前传播无处触发）。"""
        from aipd_os.bom import BomLine, BomStore

        db_path = _project(tmp_path)
        db = AIPDStateDB(db_path)
        deliv = db.add_deliverable(T, "P-1", "drawing", status="draft")
        store = BomStore(str(Path(db_path).parent / "bom.db"))
        store.create_bom(T, "P-1", "支架主 BOM")
        store.add_line(BomLine(line_id="", bom_id=store.get_bom(T, "P-1").bom_id,
                               tenant_id=T, project_id="P-1", item="支架",
                               quantity=1.0, unit="pcs", source_deliverable=deliv))

        out = _run(["validation", "import", "--db", db_path, "--project", "P-1",
                    "--stage", "dvt", "--file", _lab(tmp_path, "fail"), "--json"],
                   capsys)
        assert out["result"]["failing_items"] == ["支架"]
        assert out["result"]["issues_created"] == 1
        assert out["impact"]["stale_deliverables"] == [deliv]
        assert out["impact"]["clean"] is True
        # 报告说了不算：制品状态必须真的在库里（变异对照 M1 就是从这里抓出来的）
        assert _deliverable_status(db_path, deliv) == "stale"

        listed = _run(["issue", "list", "--db", db_path, "--project", "P-1", "--json"],
                      capsys)
        assert len(listed["items"]) == 1
        issue_id = listed["items"][0]["issue_id"]

        shown = _run(["issue", "show", "--db", db_path, "--project", "P-1",
                      "--id", issue_id, "--json"], capsys)
        assert shown["issue"]["title"].startswith("Validation failure: 支架")

        resolved = _run(["issue", "resolve", "--db", db_path, "--project", "P-1",
                         "--id", issue_id, "--disposition", "FIX",
                         "--root-cause", "壁厚不足", "--revalidation", "--json"],
                        capsys)
        assert resolved["issue"]["status"] == "RESOLVED"
        assert resolved["issue"]["disposition"] == "FIX"

        # 阻塞项已解决后，阻塞过滤应当查不到；就绪度仍必须是 FAIL——
        # 处置 Issue 不等于复验通过（结果表里那条 FAIL 还在），这是正确语义而非缺陷。
        blocking = _run(["issue", "list", "--db", db_path, "--project", "P-1",
                         "--blocking", "--json"], capsys)
        assert blocking["items"] == []
        ready = _run(["readiness", "check", "--db", db_path, "--project", "P-1",
                      "--json"], capsys, expect=1)
        assert ready["report"]["overall_status"] == "FAIL"
        assert any("FAIL" in b for b in ready["report"]["blockers"])
        dims = {d["dimension"]: d["status"] for d in ready["report"]["dimensions"]}
        assert dims["issues"] == "PASS" and dims["validation"] == "FAIL"
