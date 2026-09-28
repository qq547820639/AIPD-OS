"""执行证据必须能被失效传播走到（F-TRUTH-LINEAGE 第 70 片）。

登记原话是："不写 truth_lineage 边——工作项与上游 truth 之间还没有映射，
因此这一步产出的 evidence 今天不会被 aipd truth propagate 传播到"。
这一片把"映射"和"边"都补上，所以这些用例钉的是**传播真的能走到**，
而不是"多了一条边"：

1. 显式声明上游（`inputs["truth_refs"]`）⇒ 一次成功的 run 之后，边上真多出 1 条 `validated_by`；
2. 从那条上游记录跑 `aipd truth propagate` ⇒ 证据被标 stale 并生成返工任务
   （这才是登记里那句承诺的内容）；
3. 声明了但不存在的号 ⇒ 原样报出来，不静默丢（丢了就等于"声明过上游"这件事假绿）；
4. 只有 `idea_id` ⇒ 从"已提交的产品定义"解析上游（用的就是第 69 片接上的 `--commit` 产物）；
5. 什么上游都没有 ⇒ 0 条边 + 一句能看懂的 reason；
6. 重放不重复连边（`edges` 数的是新增行，不是调用次数）。
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, cast

from aipd_os.cli.main import main
from aipd_os.product_truth import ProductTruthStore
from aipd_os.product_truth.models import TruthRecord
from tests.test_supervisor_fact_writeback import _make_sup

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def _edges(db_path, upstream=None):
    with sqlite3.connect(str(db_path)) as c:
        c.row_factory = sqlite3.Row
        sql = ("SELECT upstream_id, downstream_id, relation FROM truth_lineage")
        rows = [dict(r) for r in c.execute(sql).fetchall()]
    if upstream:
        rows = [r for r in rows if r["upstream_id"] == upstream]
    return rows


def _add_fact(db_path, content):
    store = ProductTruthStore(str(db_path), tenant_id="default", project_id="P1")
    return store.add(TruthRecord(record_type="fact", content=content,
                                 trust_level="verified"))


def _run_doc_generate(tmp_path, monkeypatch, extra_inputs=None, project="P1"):
    import os
    os.makedirs(tmp_path / "out", exist_ok=True)
    monkeypatch.setenv("AIPD_OUTPUT_DIR", str(tmp_path / "out"))
    sup = _make_sup(tmp_path, project=project)
    inputs = {"title": "T", "sections": [{"heading": "H", "body": "b"}]}
    inputs.update(extra_inputs or {})
    wid = sup.add_work("S1_theory", "research", "t", "o",
                       capability_floor="doc.generate", inputs=inputs)
    results = sup.run_supervisor(steps=1)
    return sup, wid, results


def test_run_links_evidence_to_declared_truth(tmp_path, monkeypatch) -> None:
    db = tmp_path / "sup.db"
    rid = _add_fact(db, "支架最大载荷 50kg")
    _sup, _wid, results = _run_doc_generate(tmp_path, monkeypatch,
                                            {"truth_refs": [rid]})
    fb = results[0]["fact_writeback"]
    assert fb["record_id"], fb
    lineage = fb["lineage"]
    assert lineage["edges"] == 1, lineage
    assert lineage["relation"] == "validated_by", lineage
    assert lineage["upstream"] == [rid], lineage
    rows = _edges(db, upstream=rid)
    assert len(rows) == 1 and rows[0]["relation"] == "validated_by", rows
    assert rows[0]["downstream_id"] == fb["record_id"], rows


def test_propagate_from_that_fact_reaches_the_evidence(tmp_path, monkeypatch) -> None:
    """登记里那句"不会被传播走到"就是被这一条推翻的：改上游 ⇒ 证据 stale + 返工任务。"""
    db = tmp_path / "sup.db"
    rid = _add_fact(db, "支架最大载荷 50kg")
    _sup, _wid, results = _run_doc_generate(tmp_path, monkeypatch, {"truth_refs": [rid]})
    evidence_id = results[0]["fact_writeback"]["record_id"]
    store = ProductTruthStore(str(db), tenant_id="default", project_id="P1")
    assert store.get(evidence_id).status == "active", "前置：证据先是 active"

    rc = main(["truth", "propagate", "--db", str(db), "--project", "P1",
               "--upstream", rid, "--reason", "载荷口径改了", "--json"])
    # 有下游待返工 ⇒ 4（执行器不认 evidence 这一类，任务停在点名拒，不是失败三次）
    assert rc == 4, rc
    assert store.get(evidence_id).status == "stale", "证据必须被传播标 stale"
    with sqlite3.connect(str(db)) as c:
        c.row_factory = sqlite3.Row
        tasks = [dict(r) for r in c.execute(
            "SELECT task_id, truth_id, status FROM rework_tasks WHERE truth_id=?",
            (evidence_id,)).fetchall()]
    assert len(tasks) == 1 and tasks[0]["status"] == "pending", tasks


def test_unknown_ref_is_reported_and_not_dropped(tmp_path, monkeypatch) -> None:
    db = tmp_path / "sup.db"
    _sup, _wid, results = _run_doc_generate(
        tmp_path, monkeypatch, {"truth_refs": ["T-9999"]})
    fb = results[0]["fact_writeback"]
    assert fb["record_id"], "证据本身还是要写成（上游连不上是另一件事）"
    lineage = fb["lineage"]
    assert lineage["edges"] == 0, lineage
    assert lineage["unknown_refs"] == ["T-9999"], lineage
    assert _edges(db) == [], "不存在的号不许凭空造出一条边"


def test_idea_id_resolves_through_the_committed_definition(tmp_path) -> None:
    """只有 idea_id 的工作项：上游来自"已提交的产品定义"——第 69 片那条 CLI 的产物。"""
    from aipd_os.cli.main import main as cli_main
    from aipd_os.product_intelligence import ProductDefinitionGate
    from tests.test_product_definition_integrity import _chain, _snap
    from tests.test_product_intelligence_runtime_e2e import _env

    env = _env(tmp_path)
    _chain(env["db"], env["pi"], env["idea"])
    snap = _snap(env)
    gate = ProductDefinitionGate(env["db"], "default", "p1")
    did = gate.propose_owner_decision(actor="owner", snapshot_id=snap.snapshot_id)
    gate.resolve_owner_decision(did, "approve", "ok", actor="owner")
    assert cli_main(["product", "gate", "--db", str(env["db"].path),
                     "--project", "p1", "--commit", "--json"]) == 0
    # `get_commit` 回 `dict[str, Any] | None`（这个 idea 从没提交过才是 None）；这一条用例的
    # 前提就是上面那句 `product gate --commit` 退了 0，所以按已提交那一侧的形状读这一列。
    # 不用 assert 收窄——加断言会动运行时行为，前提已由那句 rc 断言承担。
    receipt = cast(dict[str, Any], gate.get_commit(snap.snapshot_id))
    committed = sorted(json.loads(receipt["committed_truth_refs_json"]))
    assert len(committed) == 2, receipt

    sup = env["sup"]
    wid = sup.add_work("S2_product_definition", "product", "t", "o",
                       capability_floor="doc.generate",
                       inputs={"title": "T", "sections": [{"heading": "H",
                                                           "body": "b"}],
                               "idea_id": env["idea"].idea_id})
    fb = sup._write_back_facts(
        wid, "doc.generate",
        {"record": __import__("types").SimpleNamespace(
            run_id="R-1", output_hash="h", evidence_references=[], status="succeeded")},
        {"gate": "pass"})
    assert fb["record_id"], fb
    assert sorted(fb["lineage"]["upstream"]) == committed, fb["lineage"]
    assert fb["lineage"]["edges"] == 2, fb["lineage"]
    assert fb["lineage"]["source"] == "inputs[idea_id]", fb["lineage"]


def test_no_upstream_says_why(tmp_path, monkeypatch) -> None:
    _sup, _wid, results = _run_doc_generate(tmp_path, monkeypatch)
    lineage = results[0]["fact_writeback"]["lineage"]
    assert lineage["edges"] == 0 and lineage["upstream"] == [], lineage
    assert "truth_refs" in lineage["reason"] and "idea_id" in lineage["reason"], lineage


def test_replay_adds_no_duplicate_edges(tmp_path, monkeypatch) -> None:
    """同一轮重跑：边不重复，而且读数要说"新增 0 条"而不是"又连了 1 条"。"""
    db = tmp_path / "sup.db"
    rid = _add_fact(db, "支架最大载荷 50kg")
    sup, wid, results = _run_doc_generate(tmp_path, monkeypatch, {"truth_refs": [rid]})
    first = results[0]["fact_writeback"]["lineage"]
    assert first["edges"] == 1, first
    from types import SimpleNamespace

    from aipd_os.product_truth import ProductTruthStore as S
    out = {"record": SimpleNamespace(run_id=results[0]["record"]["run_id"],
                                     output_hash=results[0]["record"]["output_hash"],
                                     evidence_references=[], status="succeeded")}
    again = sup._write_back_facts(wid, "doc.generate", out, {"gate": "pass"})
    assert again["created"] is False, again
    assert again["lineage"]["edges"] == 0, again["lineage"]
    assert again["lineage"]["total_for_this_evidence"] == 1, again["lineage"]
    assert len(_edges(db, upstream=rid)) == 1
    assert S(str(db), tenant_id="default", project_id="P1") is not None
