"""「报价批次 → BOM 版本」的血缘边（F-LINEAGE-QUOTE 第 50 片）。

改前事实（`docs/audit/QUOTE_BOM_LINEAGE_F-LINEAGE-QUOTE_2026-09-26.md` 记了取证）：
`supply_chain/` 的三个写点全是 `db.add_fact(...)`，一处 `add_edge` 都没有；
`artifact=bom` 的唯一写点是 `bom/cost_lineage.py`。
⇒ 报价把单价**就地写进 BOM 行**之后，已经登记过的那条成本结论仍是 `active`，
读的人看到「下游已处理」，其实价已经换过了。

本片钉：
1. `quote apply --truth-lineage` 写一条 `artifact=quote_batch` 版本记录 +
   `quote → 当前 BOM 版本` 的边；**传播真的能一路打到那笔成本**（第 4 条用例）；
2. 身份按输入签名：同文件重放命中同一条；只有单价/币种/版本变了才另起一版；
3. 项目里还没有 BOM 版本记录时：**记录照写、边数 0、点名原因**，不静默、也不算失败；
4. 没给旗子是**明说的跳过**；给了却写不进去判**未收口**（退码 4 且 `ok` 同向）。

第 52 片在这上面加钉一条：键的那几行**只能由库里的事实投影出来**
（`quote_applied_rows`，生产侧与漂移扫描侧共用同一份），于是
`truth drift` 看得见「当初那批报价已经被后来的报价转成 R」——
按报价文件的态算键时这一格永远看不出来（文件态是解析观测，不会自己变）。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from aipd_os.cli.commands_drift import build_resolvers
from aipd_os.cli.main import main
from aipd_os.product_truth import LineageGraph, ProductTruthStore
from aipd_os.product_truth.drift import IN_SYNC, UNDECIDABLE, classify_record
from aipd_os.product_truth.propagation import PropagationEngine
from aipd_os.state.db import AIPDStateDB
from aipd_os.supply_chain.quote_lineage import quote_input_signature

ROOT = Path(__file__).resolve().parents[1]
T = "default"
P = "QUOTE-LINEAGE"


def _sig(**over) -> str:
    # 这份 bag 的两个值本来就是两种形状（币种是 str、applied 是行列表），mypy 会把它们的
    # 公共父类型算成 `Sequence[Collection[str]]`，那个phantom 类型没有任何运行时值对得上；
    # 按 `quote_input_signature` 自己的入参形状（applied 就是 dict[str, Any] 的行列表）标出来。
    base: dict[str, Any] = {"currency": "CNY",
                            "applied": [{"quote_id": "亚明五金-支架-v1", "supplier": "亚明五金",
                                         "part": "支架", "version": 1, "status": "V",
                                         "unit_price": "12.5", "currency": "CNY"}]}
    base.update(over)
    return quote_input_signature(**base)


def _quote_csv(tmp_path, name, unit_price="12.5") -> str:
    p = tmp_path / name
    p.write_text("supplier,part,moq,tooling_fee,unit_price,lead_time_days\n"
                 f"亚明五金,支架,100,5000,{unit_price},15\n", encoding="utf-8")
    return str(p)


@pytest.fixture()
def env(tmp_path):
    db = tmp_path / "state.db"
    state = AIPDStateDB(db)
    state.ensure_default_tenant()
    state.init_project(T, P, "quote lineage 测试", "evidence")
    assert main(["bom", "add", "--db", str(db), "--project", P, "--part", "支架",
                 "--quantity", "1", "--unit", "ea", "--material", "AL",
                 "--supplier", "亚明五金", "--unit-cost", "30",
                 "--currency", "CNY"]) == 0
    return tmp_path, db


def _store(db):
    return ProductTruthStore(str(db), tenant_id=T, project_id=P)


def _edges(db):
    return {(e["upstream_id"], e["downstream_id"], e["relation"])
            for e in LineageGraph(_store(db)).edges(tenant_id=T, project_id=P)}


def _rows(db, artifact):
    return [r for r in _store(db).query(record_type="artifact_version",
                                        tenant_id=T, project_id=P)
            if (r.metadata or {}).get("artifact") == artifact]


def _apply(db, file, capsys, *, lineage=True, json_out=True):
    argv = ["quote", "apply", "--db", str(db), "--project", P, "--file", file,
            "--currency", "CNY"]
    if lineage:
        argv.append("--truth-lineage")
    if json_out:
        argv.append("--json")
    rc = main(argv)
    if not json_out:
        return rc, None
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    return rc, payload


def _cost_calc(db, capsys):
    rc = main(["cost", "calc", "--db", str(db), "--project", P, "--tooling", "50000",
               "--quantity", "1000", "--nre", "1000", "--margin", "20",
               "--truth-lineage", "--json"])
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert rc == 0, payload
    return payload


def _priced_bom(db, capsys, tmp_path):
    """先按报价定价、再登记一次成本，得到 (bom 版本记录, cost 版本记录)。"""
    rc, p = _apply(db, _quote_csv(tmp_path, "q1.csv"), capsys)
    assert rc == 0, p
    lin = _cost_calc(db, capsys)["lineage"]
    return lin["bom"]["record_id"], lin["cost"]["record_id"]


# ---------- 一、生产者与边 ----------

def test_apply_records_quote_batch_and_edges_to_current_bom(env, capsys):
    tmp_path, db = env
    bom_id, _ = _priced_bom(db, capsys, tmp_path)
    rc, p = _apply(db, _quote_csv(tmp_path, "q2.csv", "19.9"), capsys)
    assert rc == 0, p
    lin = p["lineage"]
    assert lin["written"] is True and lin["edges"] == 1
    assert lin["bom_record_id"] == bom_id
    assert (lin["quote_record_id"], bom_id, "affects") in _edges(db)
    assert p["ok"] is True


def test_replay_and_renamed_file_hit_one_quote_version(env, capsys):
    """重放同一份、以及**同一批价换个文件名**，都不许另起一版。

    文件名进不进签名是本轮实测决定的一项：进了就会把「重新下载了一份同样的报价」
    读成一次工程变更（第 46 片把 DXF 时间戳挡在签名外，同一个理由）。
    """
    tmp_path, db = env
    _priced_bom(db, capsys, tmp_path)
    first = _apply(db, _quote_csv(tmp_path, "same.csv"), capsys)[1]["lineage"]
    rc, again_p = _apply(db, _quote_csv(tmp_path, "same.csv"), capsys)
    assert rc == 0
    again = again_p["lineage"]
    assert again["created"] is False
    assert again["quote_record_id"] == first["quote_record_id"]

    rc, renamed_p = _apply(db, _quote_csv(tmp_path, "renamed_elsewhere.csv"),
                           capsys)
    assert rc == 0
    renamed = renamed_p["lineage"]
    assert renamed["created"] is False, "同一批价换了文件名不该另起一版"
    assert renamed["quote_record_id"] == first["quote_record_id"]
    assert len(_rows(db, "quote_batch")) == 1


def test_changed_price_starts_a_new_quote_version(env, capsys):
    tmp_path, db = env
    bom_id, _ = _priced_bom(db, capsys, tmp_path)
    a = _apply(db, _quote_csv(tmp_path, "p12.csv", "12.5"), capsys)[1]["lineage"]
    b = _apply(db, _quote_csv(tmp_path, "p19.csv", "19.9"), capsys)[1]["lineage"]
    assert a["quote_record_id"] != b["quote_record_id"]
    assert len(_rows(db, "quote_batch")) == 2
    # 两条都指向同一个「当初据以定价」的 BOM 版本记录
    assert a["bom_record_id"] == b["bom_record_id"] == bom_id


# ---------- 二、这一片的理由：传播真的打得到那笔成本 ----------

def test_propagating_a_quote_marks_bom_and_cost_stale(env, capsys):
    """标题那句的读数：改了报价 ⇒ 那笔成本结论不再是被认可的那一笔。"""
    tmp_path, db = env
    bom_id, cost_id = _priced_bom(db, capsys, tmp_path)
    qid = _apply(db, _quote_csv(tmp_path, "q9.csv", "19.9"),
                 capsys)[1]["lineage"]["quote_record_id"]

    report = PropagationEngine(_store(db)).on_upstream_changed(qid)
    assert {str(x) for x in report["affected"]} == {bom_id, cost_id}, report["affected"]
    assert {str(x) for x in report["stale"]} == {bom_id, cost_id}
    assert {t["truth_id"] for t in report["tasks"]} == {bom_id, cost_id}


# ---------- 三、跳过、未收口、以及「还没有 BOM 版本记录」 ----------

def test_no_flag_is_a_stated_skip_not_a_silent_one(env, capsys):
    tmp_path, db = env
    _priced_bom(db, capsys, tmp_path)
    before = len(_rows(db, "quote_batch"))
    rc, p = _apply(db, _quote_csv(tmp_path, "nosig.csv"), capsys, lineage=False)
    assert rc == 0, p
    assert p["lineage"] is None
    assert "不登记" in p["lineage_skipped"]
    assert len(_rows(db, "quote_batch")) == before, "没给旗子却写了记录"


def test_lineage_failure_holds_the_command_and_agrees_with_ok(env, capsys,
                                                              monkeypatch):
    tmp_path, db = env
    _priced_bom(db, capsys, tmp_path)
    import aipd_os.supply_chain.quote_lineage as ql

    monkeypatch.setattr(ql, "record_quote_lineage",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("写不进")))
    rc, p = _apply(db, _quote_csv(tmp_path, "boom.csv"), capsys)
    assert rc == 4, p
    assert p["ok"] is False
    assert "写不进" in p["lineage_error"]


def test_no_bom_version_record_yet_is_written_but_said_out_loud(env, capsys):
    """报价完全可以先于任何一次 cost calc 发生：记录照写、边数 0、原因点名。"""
    tmp_path, db = env
    rc, p = _apply(db, _quote_csv(tmp_path, "early.csv"), capsys)
    lin = p["lineage"]
    assert lin["written"] is True and lin["edges"] == 0
    assert lin["bom_record_id"] is None
    assert "还没有 artifact=bom" in lin["reason"]
    # 「没连上」不是失败：报价真落到行上了，命令仍按报价侧的干净度判定
    assert p["ok"] is True, p
    assert rc == 0, p
    assert len(_rows(db, "quote_batch")) == 1


# ---------- 四、签名要吃全声明的输入（撞键复现） ----------

def test_signature_covers_every_declared_input():
    """逐项改，签名必须两两不同；漏吃任何一项都会在这里露馅。"""
    variants = {
        "基线": {},
        "换币种": {"currency": "USD"},
        "只换某一行的币种": {"applied": [
            {"quote_id": "亚明五金-支架-v1", "supplier": "亚明五金", "part": "支架",
             "version": 1, "status": "V", "unit_price": "12.5",
             "currency": "USD"}]},
        "换单价": {"applied": [{"quote_id": "亚明五金-支架-v1",
                               "supplier": "亚明五金", "part": "支架",
                               "version": 1, "status": "V",
                               "unit_price": "19.9", "currency": "CNY"}]},
        "换状态": {"applied": [{"quote_id": "亚明五金-支架-v1",
                              "supplier": "亚明五金", "part": "支架",
                              "version": 1, "status": "P",
                              "unit_price": "12.5", "currency": "CNY"}]},
        "换版本": {"applied": [{"quote_id": "亚明五金-支架-v2",
                              "supplier": "亚明五金", "part": "支架",
                              "version": 2, "status": "V",
                              "unit_price": "12.5", "currency": "CNY"}]},
        "换供应商": {"applied": [{"quote_id": "德邦-支架-v1",
                               "supplier": "德邦", "part": "支架",
                               "version": 1, "status": "V",
                               "unit_price": "12.5", "currency": "CNY"}]},
        "多一条报价": {"applied": [
            {"quote_id": "亚明五金-支架-v1", "supplier": "亚明五金", "part": "支架",
             "version": 1, "status": "V", "unit_price": "12.5",
             "currency": "CNY"},
            {"quote_id": "亚明五金-底板-v1", "supplier": "亚明五金", "part": "底板",
             "version": 1, "status": "V", "unit_price": "7",
             "currency": "CNY"}]},
    }
    seen: dict[str, list[str]] = {}
    for label, over in variants.items():
        key = _sig(**over)
        seen.setdefault(key, []).append(label)
    assert len(seen) == len(variants), (
        "这些应当不同的报价给了同一个签名：" + str({k: v for k, v in seen.items()
                                                    if len(v) > 1}))


def test_no_quotes_at_all_writes_nothing(env):
    """空报价不配留一条「有效但没有来源」的记录。"""
    tmp_path, db = env
    from aipd_os.supply_chain.quote_lineage import record_quote_lineage

    out = record_quote_lineage(_store(db), signature=_sig(), source="",
                              currency="CNY", applied=[])
    assert out["written"] is False and out["records"] == 0 and out["edges"] == 0
    assert _rows(db, "quote_batch") == []


def test_lineage_producer_is_registered():
    """新生产者写 truth_lineage ⇒ 必须进 AST 两向棘轮的登记（漏登记当场红）。"""
    src = (ROOT / "tests/test_drawing_spec_lineage.py").read_text(encoding="utf-8")
    assert "src/aipd_os/supply_chain/quote_lineage.py" in src


# ---------- 六、漂移扫描：报价换过了要看得见（F-DRIFT-2 第 52 片） ----------

def _drift(db, capsys):
    rc = main(["truth", "drift", "--db", str(db), "--project", P, "--json"])
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    return rc, payload


def test_quote_key_is_recomputable_from_the_library_alone(env, capsys):
    """生产侧与扫描侧共用一份投影 ⇒ 刚登记完的报价批次，扫描必须读成「一致」。

    这条是防「两边各写一遍映射」那道闸：任何一侧单独改投影（状态字母、少读一列、
    币种算错、把 unit_price 换个数源），这里立刻从 in_sync 翻成 drifted。
    它同时也是第 52 片那个定论的落地证明：键**不靠报价文件**重算。
    """
    tmp_path, db = env
    _priced_bom(db, capsys, tmp_path)
    rec = _rows(db, "quote_batch")[0]
    verdict = classify_record(rec, build_resolvers(str(db), P)["quote_batch"])
    assert verdict["state"] == IN_SYNC, verdict


def test_a_later_quote_retiring_the_batch_is_discovered_by_the_scan(env, capsys):
    """本片的效力：后来的报价把这批转 R，`truth drift` 要能点名那条旧记录。

    第 50 片只有「再跑一次 quote apply 时才顺带传播」；按文件态算键的写法在这里
    永远读成「一致」——文件里的 `official` 不会自己变。
    """
    tmp_path, db = env
    _priced_bom(db, capsys, tmp_path)
    first = _rows(db, "quote_batch")[0].record_id
    rc, p = _apply(db, _quote_csv(tmp_path, "q2.csv", unit_price="19.9"), capsys)
    assert rc == 0, p
    rc, p = _drift(db, capsys)
    assert rc == 4, p
    assert first in {r["record_id"] for r in p["should_be_stale"]}, p["should_be_stale"]


def test_quote_record_on_the_old_file_status_basis_is_undecidable(env, capsys):
    """第 50 片那批按文件态算的键：不许换基准读成「漂了」，也不许读成「一致」。"""
    tmp_path, db = env
    _priced_bom(db, capsys, tmp_path)
    store = _store(db)
    rec = _rows(db, "quote_batch")[0]
    meta = dict(rec.metadata or {})
    meta.pop("rows_from", None)
    store.update(rec.record_id, metadata=meta)

    rc, p = _drift(db, capsys)
    hits = [r for r in p["undecidable_items"] if r["record_id"] == rec.record_id]
    assert hits and "第 50 片" in hits[0]["reason"], p["undecidable_items"]
    assert rec.record_id not in {r["record_id"] for r in p["should_be_stale"]}
    assert p["counts"][UNDECIDABLE] >= 1, p["counts"]


def test_quote_record_naming_vanished_facts_is_undecidable(env, capsys):
    """事实读不回来 ≠ 漂了：签名少几笔报价时只能报「不可判 + 点名是哪几条」。"""
    tmp_path, db = env
    _priced_bom(db, capsys, tmp_path)
    store = _store(db)
    rec = _rows(db, "quote_batch")[0]
    meta = dict(rec.metadata or {})
    meta["quote_ids"] = ["幽灵五金-支架-v9"]
    store.update(rec.record_id, metadata=meta)

    rc, p = _drift(db, capsys)
    hits = [r for r in p["undecidable_items"] if r["record_id"] == rec.record_id]
    assert hits and "已不在本项目里" in hits[0]["reason"], p["undecidable_items"]
    assert hits[0]["reason"].count("幽灵五金-支架-v9") == 1, hits[0]["reason"]


def test_a_quote_fact_that_will_not_read_back_holds_the_command(env, capsys,
                                                                monkeypatch):
    """登记时少读回一条事实 ⇒ 签名会少算，判未收口，不许写一条「少一笔」的记录。"""
    tmp_path, db = env
    _priced_bom(db, capsys, tmp_path)
    import aipd_os.supply_chain.quote_lineage as ql

    monkeypatch.setattr(ql, "quote_applied_rows", lambda *a, **k: [])
    rc, p = _apply(db, _quote_csv(tmp_path, "short.csv", unit_price="22"), capsys)
    assert rc == 4, p
    assert p["ok"] is False
    assert "读不回来" in p["lineage_error"], p
    assert len(_rows(db, "quote_batch")) == 1, "少算的那次不该留下新记录"

