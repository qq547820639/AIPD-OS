"""F-SUPPLY-01 / F-BOM-01 / F-COST-01：询价 → 报价 → BOM → 成本这条链真的闭合。

接线前的实测事实（不是推测）：
- 报价文件解析是真的（`supply_chain/quotes.py`），但 `aipd industrialize --quote`
  解析完把结果放进一个**用完就丢的内存 QuoteRegistry** 打印出来就结束
  （`cli/commands_cad.py:55-74`）；
- 会写库的 `SupplyChainStore.persist_quote` **产品侧零调用点**（全仓唯一调用者是
  `tests/test_supply_chain.py:455`）；
- 全仓只有一处写 `bom_lines.unit_cost`：`cli/commands_manufacturing.py:101` 的
  `--unit-cost` 手填参数。也就是说 **报价的单价从来没有变成过 BOM 的成本**。
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from aipd_os.bom import BomLine, BomStore, CostInputs, compute_bom_cost
from aipd_os.bom.cost import CostCurrencyError
from aipd_os.cli._helpers import DEFAULT_TENANT
from aipd_os.cli.main import main
from aipd_os.state.db import AIPDStateDB
from aipd_os.supply_chain.apply import apply_quotes_to_bom
from aipd_os.supply_chain.quotes import QuoteRegistry, parse_quote_file

T = DEFAULT_TENANT


def _store(tmp_path) -> BomStore:
    store = BomStore(str(tmp_path / "bom.db"))
    store.create_bom(T, "P-1", "支架主 BOM")
    return store


def _line(store, **kw) -> BomLine:
    base = {"bom_id": store.get_bom(T, "P-1").bom_id, "tenant_id": T,
            "project_id": "P-1", "item": "支架", "quantity": 2.0,
            "unit": "pcs"}
    base.update(kw)
    line: BomLine = store.add_line(BomLine(line_id="", **base))
    return line


def _quotes(tmp_path, rows, *, reg=None) -> list:
    """写一份规范 CSV 并走真实解析 + 真实登记（含版本递增/状态）。

    ``reg`` 传入同一个注册表才能复现「同供应商同零件二次登记 → v1 superseded、v2
    official」的真实版本语义；每次新建注册表会让两次登记都停在 v1，测的是假链路。
    """
    path = tmp_path / "quotes.csv"
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["supplier", "part", "moq", "tooling_fee",
                         "unit_price", "lead_time_days"])
        for r in rows:
            writer.writerow(r)
    parsed = parse_quote_file(str(path))
    registry = reg if reg is not None else QuoteRegistry()
    for rec in parsed["records"]:
        registry.add_quote(supplier=rec["supplier"], part=rec["part"], data=rec,
                           source_file=str(path))
    return [q for versions in registry._quotes.values() for q in versions]


def _project(tmp_path) -> str:
    """一个真实状态库 + 一个项目（与 `aipd init` 同序：租户行必须先存在）。"""
    db_path = tmp_path / "state.db"
    db = AIPDStateDB(str(db_path))
    db.ensure_default_tenant(T)
    db.init_project(T, "P-1", "支架项目", "把支架做成可开模的量产件")
    return str(db_path)


def _quote_csv(tmp_path, unit_price="12.5", part="支架", supplier="亚明五金") -> str:
    quote_csv = tmp_path / "q.csv"
    quote_csv.write_text(
        "supplier,part,moq,tooling_fee,unit_price,lead_time_days\n"
        f"{supplier},{part},100,5000,{unit_price},15\n", encoding="utf-8")
    return str(quote_csv)


def _run(argv, capsys, *, expect: int = 0) -> dict:
    """跑一次真实 `aipd` 入口，断言退出码并把这条命令的 JSON 结果还给用例。

    先清空缓冲区：`--json` 每条命令打印一行，直接 loads 整段会在第二条上炸出
    "Extra data"，而那正是"命令有没有真的各输出一条"的信号。
    """
    capsys.readouterr()
    rc = main(argv)
    out = capsys.readouterr().out.strip()
    assert rc == expect, f"rc={rc}（期望 {expect}）：{out}"
    payload: dict = json.loads(out)
    return payload


class TestCostIntegrity:
    def test_mixed_currency_refuses_to_sum(self, tmp_path):
        """总价是钱，钱必须有单位：USD 与 CNY 相加得到的数没有任何含义。"""
        store = _store(tmp_path)
        _line(store, item="A", supplier="s1", unit_cost=10.0, currency="USD")
        _line(store, item="B", supplier="s2", unit_cost=20.0, currency="CNY")
        with pytest.raises(CostCurrencyError) as exc:
            compute_bom_cost(store.list_lines(T, "P-1"), CostInputs())
        msg = str(exc.value)
        assert "USD" in msg and "CNY" in msg

    def test_single_currency_is_reported_and_sums(self, tmp_path):
        store = _store(tmp_path)
        _line(store, supplier="s1", unit_cost=10.0, currency="CNY")
        cost = compute_bom_cost(store.list_lines(T, "P-1"), CostInputs())
        assert cost.currency == "CNY"
        assert cost.material_subtotal == 20.0        # 数量 2 × 10
        assert cost.cost_complete is True

    def test_obsolete_line_never_inflates_cost(self, tmp_path):
        """作废行仍在 BOM 里（可追溯），但不参与成本，也不该挡住成本完整性。"""
        store = _store(tmp_path)
        _line(store, item="支架", supplier="s1", unit_cost=10.0)
        without = compute_bom_cost(store.list_lines(T, "P-1"), CostInputs())

        store2 = BomStore(str(tmp_path / "bom.db"))
        _line(store2, item="旧支架", supplier="s9", unit_cost=999.0, status="obsolete")
        with_obsolete = compute_bom_cost(store2.list_lines(T, "P-1"), CostInputs())

        assert with_obsolete.material_subtotal == without.material_subtotal
        assert with_obsolete.obsolete_excluded == ["旧支架"]
        assert with_obsolete.cost_complete is True, "作废行不该让成本判成不完整"

    def test_missing_price_on_a_live_line_still_blocks_completeness(self, tmp_path):
        """反向对照：只排除 obsolete，不能顺手把「活行缺价」也放行。"""
        store = _store(tmp_path)
        _line(store, item="支架", supplier="s1", unit_cost=10.0)
        _line(store, item="螺丝", supplier=None, unit_cost=None)
        cost = compute_bom_cost(store.list_lines(T, "P-1"), CostInputs())
        assert cost.cost_complete is False
        assert any("螺丝" in m for m in cost.missing_cost_lines)


class TestQuoteAppliesToCost:
    def test_quote_unit_price_becomes_bom_unit_cost(self, tmp_path):
        store = _store(tmp_path)
        line = _line(store, item="支架", supplier=None, unit_cost=None)
        before = compute_bom_cost(store.list_lines(T, "P-1"), CostInputs())
        assert before.cost_complete is False

        report = apply_quotes_to_bom(store, T, "P-1", _quotes(tmp_path, [
            ["亚明五金", "支架", 100, 5000.0, 12.5, 15]]), currency="CNY")

        assert [u["item"] for u in report.updated] == ["支架"]
        assert report.unmatched == []
        after_line = store.get_line(T, "P-1", line.line_id)
        assert after_line.unit_cost == 12.5
        assert after_line.supplier == "亚明五金"
        assert after_line.status == "quoted"
        assert after_line.quote_ref == "quote.亚明五金.支架.v1"
        after = compute_bom_cost(store.list_lines(T, "P-1"), CostInputs())
        assert after.cost_complete is True
        assert after.material_subtotal == 25.0          # 2 × 12.5，精确对账

    def test_unmatched_part_is_reported_not_swallowed(self, tmp_path):
        store = _store(tmp_path)
        _line(store, item="支架")
        report = apply_quotes_to_bom(store, T, "P-1", _quotes(tmp_path, [
            ["别人家", "法兰", 10, 0.0, 3.0, 7]]), currency="CNY")
        assert report.updated == []
        assert [u["part"] for u in report.unmatched] == ["法兰"]

    def test_draft_quote_never_overwrites_a_price(self, tmp_path):
        """只有 official 报价能改钱——草稿覆盖已确认价格是不可接受的。"""
        store = _store(tmp_path)
        _line(store, item="支架", supplier="s1", unit_cost=10.0)
        quotes = _quotes(tmp_path, [["亚明五金", "支架", 100, 0.0, 99.0, 15]])
        for q in quotes:
            q.status = "draft"
        report = apply_quotes_to_bom(store, T, "P-1", quotes, currency="CNY")
        assert report.updated == []
        assert [d["reason"] for d in report.rejected] == ["not-official"]
        assert store.list_lines(T, "P-1")[0].unit_cost == 10.0

    def test_second_official_version_supersedes_the_first(self, tmp_path):
        store = _store(tmp_path)
        _line(store, item="支架", supplier="s1", unit_cost=10.0)
        reg = QuoteRegistry()
        apply_quotes_to_bom(store, T, "P-1",
                            _quotes(tmp_path, [["亚明五金", "支架", 100, 0.0, 11.0, 15]],
                                    reg=reg),
                            currency="CNY")
        assert store.list_lines(T, "P-1")[0].quote_ref.endswith("v1")
        second = _quotes(tmp_path, [["亚明五金", "支架", 120, 0.0, 9.5, 20]], reg=reg)
        report = apply_quotes_to_bom(store, T, "P-1", second, currency="CNY")
        assert [u["unit_cost"] for u in report.updated] == [9.5]
        assert store.list_lines(T, "P-1")[0].quote_ref.endswith("v2")
        # 旧版已被登记为 superseded，同一次应用里它必须被点名拒绝而不是悄悄覆盖
        assert [(r["reason"], r["quote_status"]) for r in report.rejected] == [
            ("not-official", "superseded")]

    def test_currency_conflict_is_refused_per_line(self, tmp_path):
        """报价文件没有币种列（实测表头就没有），所以币种必须由调用方显式声明且逐行核对。"""
        store = _store(tmp_path)
        _line(store, item="支架", currency="USD")
        report = apply_quotes_to_bom(store, T, "P-1", _quotes(tmp_path, [
            ["亚明五金", "支架", 100, 0.0, 12.5, 15]]), currency="CNY")
        assert report.updated == []
        assert [r["reason"] for r in report.rejected] == ["currency-conflict"]
        assert store.list_lines(T, "P-1")[0].unit_cost is None


class TestProductPath:
    """整条链走 `aipd` 真实入口（parser → registry → 分发 → 退出码）。

    参数一律由 `build_parser()` 产出，测试不自造 Namespace：此前 `bom show` 在产品
    路径上永远算不出成本（F-BOM-01），正是因为没有一条真实命令把成本口径带进去，
    而手搓的 args 副本恰好会把这个缺口抹平。
    """

    def test_release_checklist_is_satisfiable_end_to_end(self, tmp_path, capsys):
        """修 F-BOM-01：接线前这个清单在产品路径上永远 False——两处都是硬缺。"""
        db_path = _project(tmp_path)
        _run(["bom", "add", "--db", db_path, "--project", "P-1",
              "--part", "支架", "--quantity", "2", "--unit", "pcs",
              "--material", "Q235", "--json"], capsys)

        # 未报价：release 被清单挡住，且点名是成本不完整（口径与算不出来两问都成立）
        held = _run(["bom", "release", "--db", db_path, "--project", "P-1", "--json"],
                    capsys, expect=4)
        assert set(held["blocking_checks"]) == {"cost_complete", "cost_calculated"}

        applied = _run(["quote", "apply", "--db", db_path, "--project", "P-1",
                        "--file", _quote_csv(tmp_path), "--json"], capsys)
        assert [u["item"] for u in applied["updated"]] == ["支架"]
        assert applied["bom_remaining_unpriced"] == []

        show = ["bom", "show", "--db", db_path, "--project", "P-1",
                "--tooling", "5000", "--quantity", "1000", "--margin", "20", "--json"]
        payload = _run(show, capsys)
        checks = payload["checklist"]["checks"]
        assert checks["cost_complete"] is True
        assert checks["cost_calculated"] is True, "bom show 必须带成本口径去算（F-BOM-01）"
        assert checks["bom_released"] is False        # 还没发布
        assert payload["checklist"]["release_ready"] is False
        assert payload["cost_inputs"]["tooling_fee"] == 5000.0

        _run(["bom", "release", "--db", db_path, "--project", "P-1",
              "--tooling", "5000", "--quantity", "1000", "--margin", "20",
              "--reason", "首件确认", "--json"], capsys)
        done = _run(show, capsys)
        assert done["checklist"]["release_ready"] is True
        assert done["checklist"]["checks"]["bom_released"] is True
        assert done["bom"]["status"] == "released"

    def test_persisted_quote_fact_is_what_the_bom_points_at(self, tmp_path, capsys):
        """修「persist_quote 无产品调用点」：quote_ref 必须能解析回一条真实事实。"""
        db_path = _project(tmp_path)
        _run(["bom", "add", "--db", db_path, "--project", "P-1",
              "--part", "支架", "--json"], capsys)
        _run(["quote", "apply", "--db", db_path, "--project", "P-1",
              "--file", _quote_csv(tmp_path, "7.5"), "--json"], capsys)
        db = AIPDStateDB(db_path)
        facts = {f["key"]: f for f in db.list_facts(T, "P-1")
                 if str(f["key"]).startswith("quote.")}
        assert list(facts) == ["quote.亚明五金.支架.v1"]
        assert facts["quote.亚明五金.支架.v1"]["status"] == "V"
        store = BomStore(str(Path(db_path).parent / "bom.db"))
        assert store.list_lines(T, "P-1")[0].quote_ref in facts

    def test_industrialize_quote_declares_parse_only(self, tmp_path, capsys):
        """`industrialize --quote` 只解析：必须自陈未落库、未改价，并指向 quote apply。

        同一条报价在两条命令下都"看起来登记了"，而只有一条真的动了钱——不分清就是
        F-SUPPLY-01 的同一个误读换了一处发生。
        """
        db_path = _project(tmp_path)
        payload = _run(["industrialize", "--db", db_path,
                        "--quote", _quote_csv(tmp_path), "--json"], capsys)
        assert len(payload["official_quotes"]) == 1
        note = payload["quotes_note"] or ""
        assert "未写入 Product Truth" in note and "quote apply" in note
        db = AIPDStateDB(db_path)
        assert [f["key"] for f in db.list_facts(T, "P-1")
                if str(f["key"]).startswith("quote.")] == []

    def test_partial_quoting_is_visible_but_does_not_fake_release(self, tmp_path, capsys):
        """分批报价是正常工作流：quote apply 如实列出还缺谁，release 仍然必须被挡住。"""
        db_path = _project(tmp_path)
        _run(["bom", "add", "--db", db_path, "--project", "P-1",
              "--part", "支架", "--json"], capsys)
        _run(["bom", "add", "--db", db_path, "--project", "P-1",
              "--part", "螺丝", "--json"], capsys)
        applied = _run(["quote", "apply", "--db", db_path, "--project", "P-1",
                        "--file", _quote_csv(tmp_path), "--json"], capsys)
        assert applied["bom_remaining_unpriced"] == ["螺丝"]

        held = _run(["bom", "release", "--db", db_path, "--project", "P-1",
                     "--quantity", "1000", "--json"], capsys, expect=4)
        assert "cost_complete" in held["blocking_checks"]
        assert held["status"] == "HOLD"
        assert held["checklist"]["checks"]["bom_released"] is False
        show = _run(["bom", "show", "--db", db_path, "--project", "P-1", "--json"],
                    capsys)
        assert show["checklist"]["checks"]["cost_complete"] is False
        assert show["bom"]["status"] != "released"


class TestApplyIsReproducible:
    """`quote apply` 必须可重跑：崩溃后「再执行一次」就是修复动作，而不是第二次崩。

    修法前实测：同文件二次 `quote apply` 直接
    `UNIQUE constraint failed: facts.project_id, facts.tenant_id, facts.key, facts.version`
    （exit 1）——版本号来自**进程内**注册表（每次从 1 起），而事实是按项目**持久**的。
    bom.db 与 state.db 是两个文件，跨库没有原子性，所以可重跑性不是便利，
    是这条链唯一的收口手段。
    """

    def _setup(self, tmp_path, capsys) -> str:
        db_path = _project(tmp_path)
        capsys.readouterr()
        _run(["bom", "add", "--db", db_path, "--project", "P-1",
              "--part", "支架", "--quantity", "2", "--json"], capsys)
        return db_path

    @staticmethod
    def _quote_facts(db_path) -> dict:
        db = AIPDStateDB(db_path)
        return {f["key"]: f for f in db.list_facts(T, "P-1")
                if str(f["key"]).startswith("quote.")}

    def test_second_apply_of_the_same_file_is_a_no_op(self, tmp_path, capsys):
        db_path = self._setup(tmp_path, capsys)
        first = _run(["quote", "apply", "--db", db_path, "--project", "P-1",
                      "--file", _quote_csv(tmp_path), "--json"], capsys)
        assert [u["item"] for u in first["updated"]] == ["支架"]

        second = _run(["quote", "apply", "--db", db_path, "--project", "P-1",
                       "--file", _quote_csv(tmp_path), "--json"], capsys)
        assert second["updated"] == [], "同内容重放不得再改一次价"
        assert [u["item"] for u in second["unchanged"]] == ["支架"]
        assert second["persisted_facts"] == [], "同内容重放不得再登记一条事实"
        assert list(self._quote_facts(db_path)) == ["quote.亚明五金.支架.v1"]

    def test_new_price_continues_the_version_and_retires_the_old_fact(
            self, tmp_path, capsys):
        db_path = self._setup(tmp_path, capsys)
        _run(["quote", "apply", "--db", db_path, "--project", "P-1",
              "--file", _quote_csv(tmp_path, "12.5"), "--json"], capsys)
        _run(["quote", "apply", "--db", db_path, "--project", "P-1",
              "--file", _quote_csv(tmp_path, "11.0"), "--json"], capsys)

        facts = self._quote_facts(db_path)
        assert sorted(facts) == ["quote.亚明五金.支架.v1", "quote.亚明五金.支架.v2"]
        # 库里同时留两版时，只能有一版是"已证实的官方报价"
        assert {k: v["status"] for k, v in facts.items()} == {
            "quote.亚明五金.支架.v1": "R", "quote.亚明五金.支架.v2": "V"}
        store = BomStore(str(Path(db_path).parent / "bom.db"))
        assert store.list_lines(T, "P-1")[0].quote_ref == "quote.亚明五金.支架.v2"

    def test_reused_ref_always_resolves_to_a_persisted_fact(self, tmp_path, capsys):
        """复用既有事实时，BOM 指回的必须是库里真有的那条（不能指向没落库的版本号）。"""
        db_path = self._setup(tmp_path, capsys)
        csv = _quote_csv(tmp_path, "9.9")
        _run(["quote", "apply", "--db", db_path, "--project", "P-1",
              "--file", csv, "--json"], capsys)
        _run(["quote", "apply", "--db", db_path, "--project", "P-1",
              "--file", csv, "--json"], capsys)
        store = BomStore(str(Path(db_path).parent / "bom.db"))
        assert store.list_lines(T, "P-1")[0].quote_ref in self._quote_facts(db_path)
