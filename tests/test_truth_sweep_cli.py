"""``aipd truth sweep``：把「发现漂移」接落到刀（F-SWEEP 第 54 片）。

第 51 片能发现、第 52 片把五类键都接到当前世界、第 53 片让返工收得了口，
中间断的那格是**触发**：漂移之后仍要人把 record id 抄进 `truth propagate --upstream`。
本片钉的是"抄"这一步能不能被机器取代，以及取代时不能出事的三条边界：

1. 只认边表交得出的上游；找不到就**点名不办**，绝不就近挑一条 active 记录当上游；
2. 落刀走与 `truth propagate` **同一个入口**（不另写一份传播逻辑）；
3. `--dry-run` 一个字都不写；真跑之后同一份世界再 sweep 应当无事可做（幂等）。
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from aipd_os.cli.main import main
from aipd_os.product_truth import ProductTruthStore
from aipd_os.product_truth.propagation import PropagationEngine
from aipd_os.product_truth.sweep import plan_sweep, sweep_reason
from aipd_os.state.db import AIPDStateDB

ROOT = Path(__file__).resolve().parents[1]
T = "default"
P = "TRUTH-SWEEP"


@pytest.fixture()
def env(tmp_path):
    db = tmp_path / "state.db"
    state = AIPDStateDB(db)
    state.ensure_default_tenant()
    state.init_project(T, P, "sweep 测试", "evidence")
    return tmp_path, db


def _store(db):
    return ProductTruthStore(str(db), tenant_id=T, project_id=P)


def _add_line(db, item, *, cost=12.5):
    assert main(["bom", "add", "--db", str(db), "--project", P, "--part", item,
                 "--quantity", "1", "--unit", "ea", "--material", "AL",
                 "--supplier", "ACME", "--unit-cost", str(cost),
                 "--currency", "CNY"]) == 0


def _calc(db, capsys):
    rc = main(["cost", "calc", "--db", str(db), "--project", P, "--tooling", "50000",
               "--quantity", "1000", "--nre", "1000", "--margin", "20",
               "--truth-lineage", "--json"])
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert rc == 0, payload
    return payload["lineage"]


def _sweep(db, capsys, *, dry=False):
    argv = ["truth", "sweep", "--db", str(db), "--project", P, "--json"]
    if dry:
        argv.append("--dry-run")
    rc = main(argv)
    return rc, json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def _snapshot(db):
    store = _store(db)
    return {r.record_id: (r.content, r.status, r.version,
                          json.dumps(r.metadata, sort_keys=True, ensure_ascii=False))
            for r in store.query(record_type="artifact_version",
                                 tenant_id=T, project_id=P)}


def _pending(db):
    return [t.to_dict() for t in PropagationEngine(_store(db)).list_tasks(
        status="pending")]


# ---------- 一、纯计划：不碰数据库 ----------

def test_plan_skips_records_that_are_not_active():
    up = plan_sweep([{"record_id": "T-1", "status": "stale", "artifact": "bom_cost",
                      "stored_signature": "a", "current_signature": "b"}],
                    lambda rid: ["T-0"])
    assert up == {"targets": [], "orphaned": [], "drifted_active": 0, "clean": True}


def test_plan_calls_one_upstream_even_when_two_records_share_it():
    """两条漂移记录共享上游 ⇒ 只调一次；重复调会把同一批任务反复 upsert。"""
    rows = [{"record_id": "T-2", "status": "active", "artifact": "bom_cost",
             "stored_signature": "a", "current_signature": "b"},
            {"record_id": "T-3", "status": "active", "artifact": "bom_cost",
             "stored_signature": "c", "current_signature": "d"}]
    plan = plan_sweep(rows, lambda rid: ["T-0"])
    assert len(plan["targets"]) == 1 and plan["drifted_active"] == 2
    assert [t["record_id"] for t in plan["targets"][0]["triggered_by"]] == ["T-2", "T-3"]


def test_plan_names_orphans_instead_guessing_an_upstream():
    plan = plan_sweep([{"record_id": "T-9", "status": "active", "artifact": "bom",
                        "stored_signature": "a", "current_signature": "b"}],
                      lambda rid: [])
    assert plan["targets"] == [] and len(plan["orphaned"]) == 1
    assert "不办" in plan["orphaned"][0]["reason"] or "猜" in plan["orphaned"][0]["reason"]
    assert plan["clean"] is False, "有一条没人管的记录，不能算无事可做"


def test_plan_ignores_self_loop_and_empty_ids():
    plan = plan_sweep([{"record_id": "T-1", "status": "active", "artifact": "bom",
                        "stored_signature": "a", "current_signature": "b"}],
                      lambda rid: ["T-1", "", None])
    assert plan["targets"] == [] and len(plan["orphaned"]) == 1


def test_reason_carries_both_keys():
    txt = sweep_reason("bom_cost", "abcdef1234567890", "9988776655443322")
    assert "abcdef123456" in txt and "998877665544" in txt
    assert "bom_cost" in txt


# ---------- 二、端到端：真库上发现并落刀 ----------

def test_sweep_dry_run_writes_nothing(env, capsys):
    """--dry-run 的「不写」要按整表快照判，不是按叙述判。"""
    tmp_path, db = env
    _add_line(db, "bracket")
    lin = _calc(db, capsys)
    _add_line(db, "cover", cost=3.2)          # 让 bom_cost 的键漂掉
    before = _snapshot(db)

    rc, p = _sweep(db, capsys, dry=True)
    assert rc == 4, p
    assert p["ok"] is False, p          # 退码与 ok 必须同向（dry-run 也算未收口）
    assert p["dry_run"] is True
    assert p["drifted_active"] >= 1, p
    ups = {t["upstream_id"] for t in p["targets"]}
    assert lin["bom"]["record_id"] in ups, p["targets"]
    assert _snapshot(db) == before, "dry-run 却写了记录"
    assert _pending(db) == [], "dry-run 不该建返工任务"


def test_sweep_marks_stale_and_creates_tasks_through_the_same_entry(env, capsys):
    tmp_path, db = env
    _add_line(db, "bracket")
    lin = _calc(db, capsys)
    cost_id = lin["cost"]["record_id"]
    bom_id = lin["bom"]["record_id"]
    _add_line(db, "cover", cost=3.2)

    rc, p = _sweep(db, capsys)
    assert rc == 4, p
    assert p["dry_run"] is False
    row = next(t for t in p["targets"] if t["upstream_id"] == bom_id)
    assert row["tasks"], "落刀没建出返工任务"
    assert cost_id in (row["newly_stale"] or []), row
    assert _store(db).get(cost_id).status == "stale"
    tasks = _pending(db)
    assert any(t["truth_id"] == cost_id for t in tasks), tasks
    assert all(sweep_reason_ok(t) for t in tasks), tasks


def sweep_reason_ok(task) -> bool:
    """任务说明里必须带着「当时按什么落的刀」：两个键都在。"""
    return "→" in str(task.get("reason")) or "truth sweep" in str(task.get("reason"))


def test_sweep_is_idempotent_after_it_landed(env, capsys, tmp_path):
    """落过刀之后再 sweep：**不再重复落刀**（attempts 一格不涨）。

    实测读数里退码仍是 4，但成因变了，这条要按成因判而不是按退码判：
    第一条 `bom` 版本记录本来就漂着，而它的"上游"是 BOM 表本身、不是库里的记录
    ⇒ 两轮都进 `orphaned`。真正的判据是 `targets` 由非空变空、任务配额没被再烧一次。
    """
    tmp_path, db = env
    _add_line(db, "bracket")
    _calc(db, capsys)
    _add_line(db, "cover", cost=3.2)
    rc, p = _sweep(db, capsys)
    assert rc == 4 and p["targets"], p
    tasks_first = [(t["task_id"], t["attempts"]) for t in _pending(db)]
    assert tasks_first, "第一轮就该建任务"

    rc2, p2 = _sweep(db, capsys)
    assert p2["targets"] == [], p2
    assert [(t["task_id"], t["attempts"]) for t in _pending(db)] == tasks_first, \
        "同一批任务被重复 sweep 再烧了一次配额"
    assert rc2 == 4 and p2["orphaned"], p2
    assert "orphaned" in json.dumps(p2, ensure_ascii=False)


def test_sweep_lands_once_for_a_full_quote_to_cost_chain(env, capsys, tmp_path):
    """整条链都在漂时：一轮 sweep 让 cost 侧被标 stale，且每个上游只挨一刀。

    第 50 片那条 quote→bom 边在这里才第一次被 sweep 用上：
    `bom` 记录漂了而且**有**上游（报价批次）⇒ 它进 targets，不再落在没人管那一栏。
    """
    tmp_path, db = env
    _add_line(db, "bracket")
    lin = _calc(db, capsys)
    csv = tmp_path / "q.csv"
    csv.write_text("supplier,part,moq,tooling_fee,unit_price,lead_time_days\n"
                   "ACME,bracket,100,5000,12.5,15\n", encoding="utf-8")
    assert main(["quote", "apply", "--db", str(db), "--project", P,
                 "--file", str(csv), "--currency", "CNY",
                 "--truth-lineage", "--json"]) == 0
    capsys.readouterr()
    _add_line(db, "cover", cost=3.2)

    rc, p = _sweep(db, capsys)
    assert rc == 4, p
    ups = [t["upstream_id"] for t in p["targets"]]
    assert len(ups) == len(set(ups)), f"同一上游被排进两次：{ups}"
    assert lin["bom"]["record_id"] in ups
    quote_rows = [r for r in _store(db).query(record_type="artifact_version",
                                              tenant_id=T, project_id=P)
                  if (r.metadata or {}).get("artifact") == "quote_batch"]
    assert quote_rows and quote_rows[0].record_id in ups, ups


def test_sweep_names_records_it_cannot_act_on(env, capsys):
    """漂移但边表里没有上游：点名不办，且不许顺手把别的记录标 stale。"""
    tmp_path, db = env
    _add_line(db, "bracket")
    _calc(db, capsys)
    store = _store(db)
    from aipd_os.product_truth.models import TruthRecord

    lonely = store.add(TruthRecord(
        record_type="artifact_version", content="bom lonely inputs=deadbeef",
        trust_level="high",
        metadata={"artifact": "bom", "bom_id": "GHOST-001", "revision": "1",
                  "version_no": 1, "input_signature": "0" * 64, "lines": []}),
        tenant_id=T, project_id=P)
    before = _snapshot(db)

    rc, p = _sweep(db, capsys, dry=True)
    assert rc == 4, p
    ids = {o["record_id"] for o in p["orphaned"]}
    assert lonely in ids, p["orphaned"]
    assert bom_id_not_in_targets(p, lonely)
    assert _snapshot(db) == before


def bom_id_not_in_targets(p, rid) -> bool:
    flat = [t["upstream_id"] for one in p["targets"] for t in [one]]
    return rid not in flat


def test_sweep_does_not_reimplement_propagation(env, capsys):
    """落刀必须走 `PropagationEngine.on_upstream_changed`，不是自己写一份标 stale。"""
    src = (ROOT / "src/aipd_os/cli/commands_truth.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "cmd_truth_sweep")
    calls = {f"{ast.unparse(c.func)}.{c.func.attr}" for c in ast.walk(fn)
             if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)}
    assert any(k.endswith(".on_upstream_changed") for k in calls), sorted(calls)
    # 反向对照：这条命令里不许出现「直接写状态」的调用
    assert not any(k.endswith(".set_status") for k in calls), sorted(calls)


def test_two_blades_on_one_record_create_two_tasks(env, capsys):
    """一条漂移记录挂着两个上游 ⇒ sweep 落两刀，引擎给同一 truth_id 建两条任务。

    这是本轮实测到的既有语义（`propagation.py:54-61` 对每个 affected 都建任务，
    建任务不排在"是否新标 stale"之后），不是 sweep 新造的。第 54 片的真库副本上
    就出现过 `RW-001` 与 `RW-003` 同指 `T-002`。这里把它钉成读数，同时说明：
    sweep 里没有"空刀"这一格 —— 每刀都会建任务，所以不需要那个恒为空的字段。
    """
    from aipd_os.product_truth.lineage import LineageGraph
    from aipd_os.product_truth.models import TruthRecord

    tmp_path, db = env
    _add_line(db, "bracket")
    lin = _calc(db, capsys)
    bom_id = lin["bom"]["record_id"]
    store = _store(db)
    graph = LineageGraph(store, tenant_id=T, project_id=P)
    fake = []
    for tag in ("上游甲", "上游乙"):
        rid = store.add(TruthRecord(record_type="artifact_version",
                                    content=f"quote_batch {tag} inputs=aaaa",
                                    trust_level="high",
                                    metadata={"artifact": "quote_batch"}),
                       tenant_id=T, project_id=P)
        graph.add_edge(rid, bom_id, "affects")
        fake.append(str(rid))
    _add_line(db, "cover", cost=3.2)          # 让 bom 那条漂

    rc, p = _sweep(db, capsys)
    assert rc == 4, p
    assert {t["upstream_id"] for t in p["targets"]} >= set(fake), p["targets"]
    per_truth: dict[str, int] = {}
    for one in p["targets"]:
        for t in one["tasks"]:
            per_truth[t["truth_id"]] = per_truth.get(t["truth_id"], 0) + 1
    assert per_truth.get(bom_id) == 2, (per_truth, p["targets"])


def test_sweep_missing_db_is_usage_error(env, tmp_path):
    assert main(["truth", "sweep", "--db", str(tmp_path / "nope.db"),
                 "--project", P]) == 2


def test_sweep_on_an_unscannable_world_is_not_reported_as_clean(env, capsys):
    """空库 ⇒ 不是「扫过了，什么都没漂」：判 2 并说明。"""
    tmp_path, db = env
    rc = main(["truth", "sweep", "--db", str(db), "--project", P])
    assert rc == 2, rc
    assert "没有可扫" in capsys.readouterr().out
