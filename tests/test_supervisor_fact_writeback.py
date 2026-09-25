"""主管完成工作项后，事实/证据必须落到结构化表（F-FACT-WB 第 42 片）。

修的是这一步：`run_supervisor` 的成功分支里写着步骤标签 `update_facts_evidence`，
但**没有任何代码**把事实写回——`steps_log` 只是一串自述标签，读的人（和登记里的
`current_limitation`）据此以为"事实写回已做"。现在标签对应一次真实写回：
一条 `record_type="evidence"` 的 `product_truth` 记录，作用域跟着工作项，
信任分级由**独立质量门**推导，且同一 run 重放不重复建行。

极性说明：这些用例钉的是"写回了什么"，不是"没写回"。如果哪天把写回摘掉，
第 1/2/4/6 条会一起红；把 `high` 写成 `verified` 只有第 2/3 条红（它们是
门结果与上限的两面），所以两条都要留着。
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

from aipd_os.product_truth import ProductTruthStore
from aipd_os.product_truth.store import SCHEMA as TRUTH_SCHEMA

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from aipd_supervisor import Supervisor  # noqa: E402


def _db(tmp_path) -> Path:
    return tmp_path / "sup.db"


def _make_sup(tmp_path, project="P1", tenant="default"):
    db = _db(tmp_path)
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS projects("
        "project_id TEXT PRIMARY KEY, name TEXT, goal TEXT, gate TEXT DEFAULT 'G0',"
        " status TEXT DEFAULT 'active', version TEXT, owner_policy TEXT,"
        " created_at TEXT, updated_at TEXT)"
    )
    conn.execute(
        "INSERT INTO projects VALUES(?,'t','g','G0','active','0.1.0','{}','t','t')",
        (project,))
    conn.commit()
    conn.close()
    sup = Supervisor(str(db), tenant_id=tenant)
    sup.init_lifecycle()
    return sup


def _run_one(tmp_path, monkeypatch, project="P1"):
    """跑一个能离线完成的工作项（doc.generate），返回 (sup, wid, results)。"""
    monkeypatch.setenv("AIPD_OUTPUT_DIR", str(tmp_path))
    sup = _make_sup(tmp_path, project=project)
    wid = sup.add_work(
        "S1_theory", "research", "t", "o",
        capability_floor="doc.generate",
        inputs={"title": "T", "sections": [{"heading": "H", "body": "b"}]},
    )
    return sup, wid, sup.run_supervisor(steps=1)


def test_completion_writes_one_evidence_fact(tmp_path, monkeypatch):
    """金路径：跑完一步 ⇒ product_truth 里恰有一条 evidence，字段对得上执行记录。"""
    sup, wid, results = _run_one(tmp_path, monkeypatch)
    fb = results[0]["fact_writeback"]
    assert fb["created"] is True and fb["record_id"]

    store = ProductTruthStore(str(_db(tmp_path)), tenant_id="default",
                              project_id="P1")
    rows = store.query(record_type="evidence")
    assert len(rows) == 1, f"应恰写回一条，实际 {len(rows)} 条"
    rec = rows[0]
    assert rec.record_id == fb["record_id"]
    assert rec.metadata["work_id"] == wid
    assert rec.metadata["run_id"] == results[0]["record"]["run_id"]
    assert rec.metadata["output_hash"] == results[0]["record"]["output_hash"]
    # source.file 必须是执行留下的真实证据引用，不能是新造的字符串
    assert str(rec.source.file) in results[0]["record"]["evidence_references"]
    assert "update_facts_evidence" in results[0]["steps"]


def test_trust_level_follows_the_gate_not_a_constant(tmp_path, monkeypatch):
    """门 pass ⇒ high；门 review ⇒ low。同一夹具两向，缺一向就是硬编码。"""
    _sup, _wid, results = _run_one(tmp_path, monkeypatch)
    assert results[0]["quality_gate"]["gate"] == "pass"
    assert results[0]["fact_writeback"]["trust_level"] == "high"

    monkeypatch.setattr(
        Supervisor, "_quality_gate",
        lambda self, wid, record: {"gate": "review",
                                   "findings": ["missing output hash"]})
    sub = tmp_path / "review"
    sub.mkdir(parents=True, exist_ok=True)
    _sup2, _wid2, results2 = _run_one(sub, monkeypatch)
    assert results2[0]["quality_gate"]["gate"] == "review"
    assert results2[0]["fact_writeback"]["trust_level"] == "low"
    store2 = ProductTruthStore(str(_db(sub)), tenant_id="default",
                               project_id="P1")
    assert store2.query(record_type="evidence")[0].trust_level == "low"


def test_gate_pass_never_mints_verified(tmp_path, monkeypatch):
    """质量门只核"引用与哈希在不在"，那不是内容被外部核验 ⇒ 永不到 verified。"""
    _sup, _wid, results = _run_one(tmp_path, monkeypatch)
    trust = results[0]["fact_writeback"]["trust_level"]
    assert trust != "verified", "把自造门的结果读成 verified 是第 32/34 片那一族病"
    assert trust in {"high", "low"}


def test_same_run_is_written_once(tmp_path, monkeypatch):
    """幂等：同一 (类型, 内容, 作用域) 重放不新增行。

    这里用 SimpleNamespace 造 `out`，字段形状（run_id / output_hash /
    evidence_references）取自上一条用例真实跑出来的记录 dict——
    `_write_back_facts` 只读这三个字段，所以夹具与生产形状一致。
    """
    sup, wid, results = _run_one(tmp_path, monkeypatch)
    real = results[0]["record"]
    out = {"record": SimpleNamespace(run_id=real["run_id"],
                                     output_hash=real["output_hash"],
                                     evidence_references=list(
                                         real["evidence_references"])),
           "result": {}}
    gate = results[0]["quality_gate"]

    again = sup._write_back_facts(wid, "doc.generate", out, gate)
    assert again["created"] is False
    assert again["record_id"] == results[0]["fact_writeback"]["record_id"]

    store = ProductTruthStore(str(_db(tmp_path)), tenant_id="default",
                              project_id="P1")
    assert len(store.query(record_type="evidence")) == 1


def test_scoping_cannot_dedup_across_projects(tmp_path, monkeypatch):
    """去重键必须含作用域：另一项目查同一条内容应读不到，否则新项目永远写不进。"""
    _sup, _wid, results = _run_one(tmp_path, monkeypatch)
    store = ProductTruthStore(str(_db(tmp_path)), tenant_id="default",
                              project_id="P1")
    content = store.query(record_type="evidence")[0].content

    other = ProductTruthStore(str(_db(tmp_path)), tenant_id="default",
                              project_id="P2")
    assert other.query(record_type="evidence") == []
    assert other.find_id_by_type_and_content("evidence", content) is None


def test_writeback_failure_is_labelled_not_silently_claimed(tmp_path, monkeypatch):
    """写回失败时标签必须改判为 fact_writeback_failed——否则又是"没做却声称做过"。"""
    def boom(*_a, **_k):
        raise RuntimeError("夹具：写回炸掉")

    monkeypatch.setattr(ProductTruthStore, "add", boom)
    _sup, wid, results = _run_one(tmp_path, monkeypatch)
    fb = results[0]["fact_writeback"]
    assert fb["record_id"] is None and fb["created"] is False
    assert "夹具：写回炸掉" in fb["error"]
    steps = results[0]["steps"]
    assert "fact_writeback_failed" in steps
    assert "update_facts_evidence" not in steps
    # 失败不中断执行：工作项仍然 complete，且没有偷偷留下 evidence 行
    assert results[0]["action"] == "complete"
    store = ProductTruthStore(str(_db(tmp_path)), tenant_id="default",
                              project_id="P1")
    assert store.query(record_type="evidence") == []
    assert wid


def test_registry_wording_matches_the_schema_fact():
    """登记里那句「全库无独立 product_truth 表」早已不成立——本轮改判，并把
    文案与结构事实放进同一条断言：删掉错话不算证据，表真在才算。"""
    from aipd_os.registry_data import CAPABILITIES

    by_id = {str(r.get("id")): r for r in CAPABILITIES}
    limitation = str(by_id["supervisor.fact_writeback"].get(
        "current_limitation") or "")
    assert "无独立 product_truth" not in limitation, \
        f"登记还在说没有 truth 表：{limitation[:120]}"
    assert "CREATE TABLE IF NOT EXISTS product_truth" in TRUTH_SCHEMA, \
        "结构事实变了，本条断言的另一半要一起改判"
