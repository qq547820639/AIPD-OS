"""「BOM 版本 → 成本结论」的血缘边（F-LINEAGE-COST 第 48 片）。

改前事实（`docs/audit/BOM_COST_LINEAGE_F-LINEAGE-COST_2026-09-26.md` 记了取证）：
成本只写进 `facts` 表的 `cost.total`，`conditions` 是一句 `bom=BOM-001 qty=…` 的拼串；
`bom/` 与 `supply_chain/` 里没有任何 `add_edge` 调用点 —— 所以「改了 BOM，那笔成本还是不是
它算出来的」在库里问不出来，`truth propagate` 也打不到成本结论。

本片钉四件事：
1. `cost calc --truth-lineage` 写两条 `artifact_version`（`bom` / `bom_cost`）+ 一条
   `bom → cost` 的 `affects` 边，**传播真的能一路打到成本**；
2. 身份按**输入签名**：BOM 行集合变 ⇒ BOM 版本变；只有口径变 ⇒ 只有成本版本变；
   同输入重跑命中同一条（不因为时间戳/浮点排版另起一版）；
3. 同一 BOM 只留一版有效（旧版标 `superseded`），否则一次改 BOM 会把历史成本全打成待返工；
4. 没给 `--truth-lineage` 是**明说的跳过**；给了却写不进去则判未收口，`ok` 与退码同向。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from aipd_os.bom.cost_lineage import bom_input_signature, cost_input_signature, record_cost_lineage
from aipd_os.cli.main import main
from aipd_os.product_truth import LineageGraph, ProductTruthStore
from aipd_os.product_truth.propagation import PropagationEngine
from aipd_os.state.db import AIPDStateDB

ROOT = Path(__file__).resolve().parents[1]
T = "default"
P = "COST-LINEAGE"


@pytest.fixture()
def env(tmp_path):
    db = tmp_path / "state.db"
    state = AIPDStateDB(db)
    state.ensure_default_tenant()
    state.init_project(T, P, "cost lineage 测试", "evidence")
    return tmp_path, db


def _store(db):
    return ProductTruthStore(str(db), tenant_id=T, project_id=P)


def _rows(db, artifact):
    return [r for r in _store(db).query(record_type="artifact_version",
                                        tenant_id=T, project_id=P)
            if (r.metadata or {}).get("artifact") == artifact]


def _edges(db):
    return {(e["upstream_id"], e["downstream_id"], e["relation"])
            for e in LineageGraph(_store(db)).edges(tenant_id=T, project_id=P)}


def _add_line(db, item, *, cost, qty=1.0, supplier="ACME"):
    assert main(["bom", "add", "--db", str(db), "--part", item,
                 "--quantity", str(qty), "--unit", "ea", "--material", "AL",
                 "--supplier", supplier, "--unit-cost", str(cost),
                 "--currency", "CNY"]) == 0


def _calc(db, *, lineage=True, margin=0.0, capsys=None):
    argv = ["cost", "calc", "--db", str(db), "--project", P, "--tooling", "50000",
            "--quantity", "1000", "--nre", "1000", "--margin", str(margin), "--json"]
    if lineage:
        argv.append("--truth-lineage")
    rc = main(argv)
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    return rc, payload


def test_cost_conclusion_is_reachable_from_the_bom(env, capsys):
    """本片的理由：改 BOM ⇒ `truth propagate` 能把那笔成本结论打成 stale 并生成返工任务。"""
    tmp_path, db = env
    _add_line(db, "bracket", cost=12.5)
    rc, payload = _calc(db, capsys=capsys)
    assert rc == 0, payload
    lin = payload["lineage"]
    assert lin["written"] is True and lin["edges"] == 1
    bom_id = lin["bom"]["record_id"]
    cost_id = lin["cost"]["record_id"]
    assert (bom_id, cost_id, "affects") in _edges(db)
    assert payload.get("ok", True) is True

    report = PropagationEngine(_store(db)).on_upstream_changed(bom_id)
    assert cost_id in report["affected"], f"成本仍打不到：affected={report['affected']}"
    assert {t["truth_id"] for t in report["tasks"]} == {cost_id}


def test_same_inputs_hit_one_cost_version(env, capsys):
    """同 BOM 同口径重跑 ⇒ 命中同一条成本记录（`created=False`），不另起一版。"""
    tmp_path, db = env
    _add_line(db, "bracket", cost=12.5)
    _p1 = _calc(db, capsys=capsys)[1]
    rc2, p2 = _calc(db, capsys=capsys)
    assert rc2 == 0
    assert p2["lineage"]["bom"]["created"] is False
    assert p2["lineage"]["cost"]["created"] is False
    assert p2["lineage"]["cost"]["record_id"] == _p1["lineage"]["cost"]["record_id"]
    assert len(_rows(db, "bom")) == 1 and len(_rows(db, "bom_cost")) == 1


def test_only_the_caliber_changed_supersedes_the_cost_not_the_bom(env, capsys):
    """只改口径（毛利率）⇒ BOM 版本不动、成本另起一版且旧版标 superseded。

    这是把「签名要吃口径」钉成断言的那一条：只记 bom_id 的实现会在这里露馅。
    """
    tmp_path, db = env
    _add_line(db, "bracket", cost=12.5)
    first = _calc(db, capsys=capsys)[1]["lineage"]
    rc, second = _calc(db, margin=20.0, capsys=capsys)
    assert rc == 0, second
    lin = second["lineage"]
    assert lin["bom"]["record_id"] == first["bom"]["record_id"]
    assert lin["bom"]["created"] is False
    assert lin["cost"]["created"] is True
    assert lin["cost"]["record_id"] != first["cost"]["record_id"]
    assert lin["cost"]["superseded_record_id"] == first["cost"]["record_id"]
    rows = {r.record_id: r.status for r in _rows(db, "bom_cost")}
    assert rows[first["cost"]["record_id"]] == "superseded"
    assert rows[lin["cost"]["record_id"]] == "active"
    assert len([rid for rid, st in rows.items() if st in ("active", "stale")]) == 1


def test_new_line_starts_a_new_bom_version_and_repoints_the_edge(env, capsys):
    """加一行 BOM ⇒ BOM 版本另起一版，新成本挂到**新** BOM 记录上，边不许悬空。"""
    tmp_path, db = env
    _add_line(db, "bracket", cost=12.5)
    first = _calc(db, capsys=capsys)[1]["lineage"]
    _add_line(db, "washer", cost=0.5)
    rc, second = _calc(db, capsys=capsys)
    assert rc == 0, second
    lin = second["lineage"]
    assert lin["bom"]["created"] is True
    assert lin["bom"]["record_id"] != first["bom"]["record_id"]
    assert (lin["bom"]["record_id"], lin["cost"]["record_id"], "affects") in _edges(db)
    # 签名里带的是**参与行集合**：两行与一行的签名必须不同
    assert lin["bom_signature"] != first["bom_signature"]
    assert len(lin["bom"]["record_id"]) > 0


def test_no_flag_is_a_stated_skip_not_a_silent_one(env, capsys):
    tmp_path, db = env
    _add_line(db, "bracket", cost=12.5)
    rc, payload = _calc(db, lineage=False, capsys=capsys)
    assert rc == 0
    assert payload["lineage"] is None
    assert "未给 --truth-lineage" in payload["lineage_skipped"]
    assert _rows(db, "bom") == [] and _rows(db, "bom_cost") == []
    # 终端面（不带 --json 才会有散文输出）也必须把跳过说出来
    capsys.readouterr()
    assert main(["cost", "calc", "--db", str(db), "--project", P,
                 "--tooling", "50000", "--quantity", "1000"]) == 0
    assert "未给 --truth-lineage" in capsys.readouterr().out


def test_empty_bom_writes_no_lineage(env, capsys):
    """没有行就没有版本可言：与那句「BOM 为空，先 aipd bom add」保持一致。"""
    _tmp, db = env
    rc, payload = _calc(db, capsys=capsys)
    assert rc == 0
    lin = payload["lineage"]
    assert lin["written"] is False and lin["records"] == 0
    assert "BOM 为空" in lin["reason"]
    assert _rows(db, "bom") == []


def test_lineage_failure_holds_the_command_and_agrees_with_ok(env, capsys, monkeypatch):
    import aipd_os.bom.cost_lineage as cl

    _tmp, db = env
    _add_line(db, "bracket", cost=12.5)
    monkeypatch.setattr(cl, "record_cost_lineage",
                        lambda *a, **k: (_ for _ in ()).throw(
                            RuntimeError("夹具：库锁住")))
    rc, payload = _calc(db, capsys=capsys)
    assert rc == 4, payload
    assert payload["lineage"] is None and "RuntimeError" in payload["lineage_error"]
    assert payload["ok"] is False, "机器面与终端面不许各说一套"


def test_signature_covers_every_declared_input():
    """输入键的适用域：BOM 行集合与口径五项各自单独变都要翻签名，全同必须稳定。"""
    base_bom = {"bom_id": "BOM-1", "revision": "A", "version_no": 3, "lines": []}
    same = bom_input_signature(**base_bom)
    assert bom_input_signature(**base_bom) == same

    class _Line:
        def __init__(self, line_id, unit_cost):
            self.line_id, self.item = line_id, "p"
            self.quantity, self.unit_cost = 1.0, unit_cost
            self.currency, self.status = "CNY", "quoted"
            self.quote_ref, self.version_no = "Q1", 1

    changed = dict(base_bom)
    changed["lines"] = [_Line("LINE-001", 12.5)]
    assert bom_input_signature(**changed) != same
    moved = dict(base_bom)
    moved["lines"] = [_Line("LINE-002", 12.5)]
    assert bom_input_signature(**moved) != bom_input_signature(**changed), \
        "行身份不能只看数量——换一行同价的东西必须是另一版"
    revision = dict(base_bom)
    revision["revision"] = "B"
    assert bom_input_signature(**revision) != same

    cost_base = {"bom_signature": same, "tooling_fee": 1.0, "target_quantity": 2,
                 "amortize_over": None, "nre": 3.0, "margin_pct": 4.0}
    stable = cost_input_signature(**cost_base)
    assert cost_input_signature(**cost_base) == stable
    for field, value in (("tooling_fee", 1.5), ("target_quantity", 20),
                         ("amortize_over", 500), ("nre", 3.5), ("margin_pct", 0.0),
                         ("bom_signature", "other")):
        assert cost_input_signature(**{**cost_base, field: value}) != stable, field


def test_producer_is_registered_and_wired():
    """生产者集合由棘轮钉；接线本身也要钉（定义了函数而命令不调用就是死代码）。"""
    import ast

    producers = (ROOT / "tests" / "test_drawing_spec_lineage.py").read_text(
        encoding="utf-8")
    assert "bom/cost_lineage.py" in producers or "bom.cost_lineage" in producers
    tree = ast.parse((ROOT / "src" / "aipd_os" / "cli"
                      / "commands_manufacturing.py").read_text(encoding="utf-8"))
    calls = {n.func.id for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "record_cost_lineage" in calls


def test_producer_refuses_to_write_when_upstream_id_missing(env, capsys):
    """直接调生产者时缺 header/行 ⇒ 不写任何记录（不是"写了个空版本"）。"""
    _tmp, db = env
    out = record_cost_lineage(_store(db), header=None, lines=[], inputs=None, cost=None)
    assert out["written"] is False and out["records"] == 0
    assert _rows(db, "bom") == []
