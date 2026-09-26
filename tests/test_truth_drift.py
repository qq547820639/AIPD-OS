"""`aipd truth drift`：让库自己发现「上游已变、下游还 active」（F-DRIFT 第 51 片）。

第 48/49/50 三轮的 §七 都留了同一句：传播的触发靠人给 `--upstream`。
这一片补的是**发现**那一半：不靠人记得去 propagate，库里能自己算出
「这条记录登记时的输入，和现在世界的输入，已经不是同一份」。

钉四组：
1. 分类器四态各自开火，且**「不可判」不折进「没漂」也不折进「漂了」**；
2. 没接探测器的制品类型要显式落进「不可判」并说明原因 —— 静默跳过会把覆盖率读成 100%；
3. 真库端到端：`cost calc` 之后什么都不动 ⇒ 一致；**只改报价**（不跑 propagate、不跑 rework）
   ⇒ 命令自己就把 BOM 版本与成本结论两条都点出来，且它们还挂着 active；
4. 空库/无可扫记录 ⇒ **不是通过**（`clean=False`、退码 4），别把"没东西可判"读成"全都一致"。
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from aipd_os.cli.commands_drift import build_resolvers
from aipd_os.cli.main import main
from aipd_os.product_truth import ProductTruthStore
from aipd_os.product_truth.drift import (
    DRIFTED,
    IN_SYNC,
    NO_SIGNATURE,
    UNDECIDABLE,
    classify_record,
    scan_drift,
)
from aipd_os.state.db import AIPDStateDB

T = "default"
P = "TRUTH-DRIFT"


class FakeRec:
    def __init__(self, record_id, metadata, status="active"):
        self.record_id = record_id
        self.metadata = metadata
        self.status = status


# ---------- 一、分类器四态 ----------

def test_classifier_four_states():
    ok = SimpleNamespace(record_id="T-1", metadata={"artifact": "bom",
                                                    "input_signature": "abc"},
                         status="active")
    same = classify_record(ok, lambda m: ("abc", m.get("input_signature"), None))
    assert same["state"] == IN_SYNC
    diff = classify_record(ok, lambda m: ("zzz", m.get("input_signature"), None))
    assert diff["state"] == DRIFTED and diff["status"] == "active"
    blind = classify_record(ok, lambda m: (None, m.get("input_signature"), "读不到 BOM 行"))
    assert blind["state"] == UNDECIDABLE and blind["reason"] == "读不到 BOM 行"
    keyless = SimpleNamespace(record_id="T-2", metadata={"artifact": "bom"},
                              status="active")
    assert classify_record(keyless, lambda m: ("abc", None, None))["state"] \
        == NO_SIGNATURE


def test_classifier_does_not_leak_resolver_exception():
    """重算器抛异常是「不可判」，不是崩溃、也不是"没漂"。"""
    rec = FakeRec("T-1", {"artifact": "bom", "input_signature": "abc"})

    def boom(meta):
        raise RuntimeError("声明文件被删了")

    out = classify_record(rec, boom)
    assert out["state"] == UNDECIDABLE
    assert "RuntimeError" in out["reason"] and "声明文件被删了" in out["reason"]


def test_record_without_artifact_is_undecidable_not_skipped():
    rec = FakeRec("T-9", {"input_signature": "abc"})
    out = classify_record(rec, lambda m: ("abc", "abc", None))
    assert out["state"] == UNDECIDABLE and out["artifact"] is None


class FakeStore:
    def __init__(self, records):
        self._records = records

    def query(self, record_type=None, tenant_id=None, project_id=None):
        return list(self._records)


def test_uncovered_artifact_lands_in_undecidable_with_reason():
    """没有 resolver 的类型不能静默跳过——那会把"覆盖率"读成 100%。"""
    recs = [FakeRec("T-1", {"artifact": "quote_batch", "input_signature": "abc"})]
    report = scan_drift(FakeStore(recs), resolvers={})
    assert report["counts"][UNDECIDABLE] == 1
    assert "还没接漂移探测器" in report["buckets"][UNDECIDABLE][0]["reason"]


def test_superseded_records_are_not_scanned():
    """已作废的记录不是"现状"，不该拿它算漂移。"""
    recs = [FakeRec("T-1", {"artifact": "bom", "input_signature": "abc"},
                    status="superseded")]
    report = scan_drift(FakeStore(recs),
                        resolvers={"bom": lambda m: ("zzz", "abc", None)})
    assert report["scanned"] == 0 and report["nothing_scanned"] is True


def test_should_be_stale_only_counts_active_drift():
    recs = [FakeRec("T-1", {"artifact": "bom", "input_signature": "abc"}, status="active"),
            FakeRec("T-2", {"artifact": "bom", "input_signature": "abc"}, status="stale")]
    report = scan_drift(FakeStore(recs),
                        resolvers={"bom": lambda m: ("zzz", m["input_signature"], None)})
    assert report["counts"][DRIFTED] == 2
    assert [r["record_id"] for r in report["should_be_stale"]] == ["T-1"]


def test_nothing_scanned_is_not_green():
    """空库读成"全部一致"是最安静的假绿：0 条必须不 clean。"""
    report = scan_drift(FakeStore([]), resolvers={})
    assert report["clean"] is False and report["nothing_scanned"] is True


# ---------- 二、真库端到端：发现不需要人记得 propagate ----------

@pytest.fixture()
def env(tmp_path):
    db = tmp_path / "state.db"
    state = AIPDStateDB(db)
    state.ensure_default_tenant()
    state.init_project(T, P, "drift 测试", "evidence")
    return tmp_path, db


def _add_line(db, item, *, cost, supplier="ACME"):
    assert main(["bom", "add", "--db", str(db), "--project", P, "--part", item,
                 "--quantity", "1", "--unit", "ea", "--material", "AL",
                 "--supplier", supplier, "--unit-cost", str(cost),
                 "--currency", "CNY"]) == 0


def _calc(db, capsys):
    rc = main(["cost", "calc", "--db", str(db), "--project", P, "--tooling", "50000",
               "--quantity", "1000", "--nre", "1000", "--margin", "20",
               "--truth-lineage", "--json"])
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert rc == 0, payload
    return payload


def _drift(db, capsys):
    rc = main(["truth", "drift", "--db", str(db), "--project", P, "--json"])
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    return rc, payload


def test_fresh_world_reports_in_sync(env, capsys):
    tmp_path, db = env
    _add_line(db, "bracket", cost=12.5)
    _calc(db, capsys)
    rc, p = _drift(db, capsys)
    assert rc == 0, p
    assert p["ok"] is True
    # bom 与 bom_cost 两条都在、都一致；quote_batch 这一类没接探测器 ⇒ 本例里没有该记录
    assert p["counts"][IN_SYNC] == 2, p["counts"]
    assert p["counts"][DRIFTED] == 0 and p["should_be_stale"] == []


def test_changing_the_bom_is_discovered_without_any_propagate(env, capsys):
    """本片的理由：只改 BOM，**不跑 propagate、不跑 rework**，命令自己就发现两条都漂了。"""
    tmp_path, db = env
    _add_line(db, "bracket", cost=12.5)
    lin = _calc(db, capsys)["lineage"]
    _add_line(db, "cover", cost=3.2)          # 只动权威表，不碰血缘状态
    rc, p = _drift(db, capsys)
    assert rc == 4, p
    assert p["ok"] is False
    assert p["counts"][DRIFTED] == 2, p["counts"]
    assert {r["record_id"] for r in p["should_be_stale"]} == \
        {lin["bom"]["record_id"], lin["cost"]["record_id"]}
    assert all(r["status"] == "active" for r in p["should_be_stale"])


def test_legacy_cost_record_is_undecidable_not_in_sync(env, capsys):
    """第 48 片那批没存口径值的记录：不许被读成"一致"，也不许读成"漂了"。"""
    tmp_path, db = env
    _add_line(db, "bracket", cost=12.5)
    cost_id = _calc(db, capsys)["lineage"]["cost"]["record_id"]
    store = ProductTruthStore(str(db), tenant_id=T, project_id=P)
    meta = dict(store.get(cost_id).metadata or {})
    for k in ("tooling_fee", "target_quantity", "amortize_over", "nre", "margin_pct"):
        meta.pop(k, None)
    store.update(cost_id, metadata=meta)

    rc, p = _drift(db, capsys)
    assert p["counts"][UNDECIDABLE] >= 1, p["counts"]
    hit = [r for r in p["undecidable_items"] if r["record_id"] == cost_id]
    assert hit and "口径五项" in hit[0]["reason"]
    assert cost_id not in {r["record_id"] for r in p["should_be_stale"]}


def test_spec_record_drifts_when_the_file_on_disk_changes(env, capsys, tmp_path):
    """`drawing_spec` 那一类存的是 spec_sha256，不是 input_signature：换一种键名也要能吃。"""
    from aipd_os.cad.spec_lineage import record_spec_lineage

    tmp_path, db = env
    spec = tmp_path / "spec.json"
    payload = {"tolerances": [{"ctq_ref": "CTQ-1", "nominal": 6.0}]}
    spec.write_text(json.dumps(payload), encoding="utf-8")
    store = ProductTruthStore(str(db), tenant_id=T, project_id=P)
    out = record_spec_lineage(store, payload, path=spec,
                              tenant_id=T, project_id=P)
    assert out["created"] is True and out["record_id"], out

    resolvers = build_resolvers(str(db), P)
    verdict = classify_record(store.get(out["record_id"]), resolvers["drawing_spec"])
    assert verdict["state"] == IN_SYNC, verdict

    payload["tolerances"][0]["nominal"] = 6.05
    spec.write_text(json.dumps(payload), encoding="utf-8")
    verdict2 = classify_record(store.get(out["record_id"]), resolvers["drawing_spec"])
    assert verdict2["state"] == DRIFTED, verdict2


def test_drift_is_read_only_even_when_it_finds_drift(env, capsys):
    """「本命令一个字都不写」是叙述还是事实：跑出漂移之后，整表必须逐字段没动。"""
    tmp_path, db = env
    _add_line(db, "bracket", cost=12.5)
    _calc(db, capsys)
    _add_line(db, "cover", cost=3.2)          # 制造漂移
    store = ProductTruthStore(str(db), tenant_id=T, project_id=P)

    def snapshot():
        return {r.record_id: (r.content, r.status, r.version,
                              json.dumps(r.metadata, sort_keys=True, ensure_ascii=False))
                for r in store.query(record_type="artifact_version",
                                     tenant_id=T, project_id=P)}

    before = snapshot()
    rc, p = _drift(db, capsys)
    assert rc == 4 and p["counts"][DRIFTED] == 2, p
    assert snapshot() == before, "只读扫描却改了记录（content/status/version/metadata 任一）"


def test_missing_db_is_usage_error_not_drift(env, tmp_path):
    rc = main(["truth", "drift", "--db", str(tmp_path / "nope.db"), "--project", P])
    assert rc == 2, rc
