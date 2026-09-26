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
    Face,
    classify_record,
    scan_drift,
)
from aipd_os.state.db import AIPDStateDB

T = "default"
P = "TRUTH-DRIFT"


def _one(current, stored, reason=None):
    """单面制品的 resolver：把 (current, stored, reason) 抬成群面协议。"""
    return [Face("input", current, stored, reason)]


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
    same = classify_record(ok, lambda m: _one("abc", m.get("input_signature")))
    assert same["state"] == IN_SYNC
    diff = classify_record(ok, lambda m: _one("zzz", m.get("input_signature")))
    assert diff["state"] == DRIFTED and diff["status"] == "active"
    blind = classify_record(ok, lambda m: _one(None, m.get("input_signature"), "读不到 BOM 行"))
    assert blind["state"] == UNDECIDABLE
    assert "读不到 BOM 行" in blind["reason"]
    assert blind["faces"] == [{"face": "input", "current": None, "stored": "abc",
                               "reason": "读不到 BOM 行"}], blind["faces"]
    keyless = SimpleNamespace(record_id="T-2", metadata={"artifact": "bom"},
                              status="active")
    assert classify_record(keyless, lambda m: _one("abc", None))["state"] \
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
    out = classify_record(rec, lambda m: _one("abc", "abc"))
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
                        resolvers={"bom": lambda m: _one("zzz", "abc")})
    assert report["scanned"] == 0 and report["nothing_scanned"] is True


def test_should_be_stale_only_counts_active_drift():
    recs = [FakeRec("T-1", {"artifact": "bom", "input_signature": "abc"}, status="active"),
            FakeRec("T-2", {"artifact": "bom", "input_signature": "abc"}, status="stale")]
    report = scan_drift(FakeStore(recs),
                        resolvers={"bom": lambda m: _one("zzz", m["input_signature"])})
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
    """`drawing_spec` 那一类存的是 spec_sha256，不是 input_signature：换一种键名也要能吃。

    第 57 片改判的一格：这条夹具的 spec 是手写形状（只有 `tolerances`，不是
    `spec_from_ctq` 的产物），所以记录里 `ctq_refs` 是空的 ⇒ **源面没有从重算**。
    改判前它整条记 `in_sync`，改判后记 `undecidable`，而本片真正要钉的那半句
    ——「手改产物文件必须被发现」——不但没弱，反而更精确：漂移理由点名是 `file` 面。
    两面各自独立的正例（改 CTQ 只红源面）在 `tests/test_truth_spec_faces.py`。
    """
    from aipd_os.cad.spec_lineage import record_spec_lineage

    tmp_path, db = env
    spec = tmp_path / "spec.json"
    payload = {"tolerances": [{"ctq_ref": "CTQ-1", "nominal": 6.0}]}
    spec.write_text(json.dumps(payload), encoding="utf-8")
    store = ProductTruthStore(str(db), tenant_id=T, project_id=P)
    out = record_spec_lineage(store, payload, path=spec,
                              tenant_id=T, project_id=P)
    assert out["created"] is True and out["record_id"], out
    assert out["ctq_refs"] == [], out

    resolvers = build_resolvers(str(db), P)
    verdict = classify_record(store.get(out["record_id"]), resolvers["drawing_spec"])
    assert verdict["state"] == UNDECIDABLE, verdict
    assert {f["face"] for f in verdict["faces"]} == {"file", "source"}
    by_face = {f["face"]: f for f in verdict["faces"]}
    assert by_face["file"]["current"] == by_face["file"]["stored"], by_face["file"]
    assert by_face["source"]["current"] is None and "ctq_refs" in by_face["source"]["reason"]

    payload["tolerances"][0]["nominal"] = 6.05
    spec.write_text(json.dumps(payload), encoding="utf-8")
    verdict2 = classify_record(store.get(out["record_id"]), resolvers["drawing_spec"])
    assert verdict2["state"] == DRIFTED, verdict2
    assert "file面" in verdict2["reason"], verdict2["reason"]


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


def test_scan_does_not_create_a_bom_store_when_the_sidecar_is_gone(env, capsys):
    """「一个字都不写」得读到**文件面**：同目录没有 bom.db 时判不可判，且不许建库。

    `BomStore.__init__` 会建库建表（`bom/store.py:87-89` 明写过这条约束），
    于是「没接线」会被一次只读扫描改成「接了但是空的」——
    记录面确实没动，但世界的形状动了。第 52 片在真库副本上撞出来的。
    """
    from aipd_os.cli.commands_manufacturing import _bom_store_path

    tmp_path, db = env
    _add_line(db, "bracket", cost=12.5)
    _calc(db, capsys)
    bom_db = _bom_store_path(str(db))
    assert bom_db.is_file()
    bom_db.unlink()

    rc, p = _drift(db, capsys)
    hits = [r for r in p["undecidable_items"]
            if r["artifact"] in ("bom", "bom_cost")]
    assert len(hits) == 2, p["undecidable_items"]
    assert all("没有 BOM 库文件" in r["reason"] for r in hits), hits
    assert p["counts"]["in_sync"] == 0, p["counts"]
    assert not bom_db.exists(), "只读扫描却建出了 BOM 库"


def test_generated_drawing_drift_is_discovered_on_a_real_record(tmp_path, capsys):
    """四类 resolver 里只有 `drawing_dxf` 那支此前没有真库端到端断言
    （第 51 片 §六 自记的缺口）。

    这条同时是第 46 片「签名要吃全出图输入」的一条独立回归：
    签名漏吃某一项时，这里会读成「没漂」，而第 46 片那批用例照样全绿——
    它们盯的是"另起新版"，这里盯的是"能不能被发现"。
    """
    from aipd_os.product_truth import ProductTruthStore, TruthRecord

    db = tmp_path / "state.db"
    state = AIPDStateDB(db)
    state.ensure_default_tenant()
    state.init_project(T, "DRIFT-DXF", "drift dxf 真库", "evidence")
    store = ProductTruthStore(str(db), tenant_id=T, project_id="DRIFT-DXF")
    # 窗口取自实测：golden 支架 TOP 视图四个孔拟合直径 8.0mm（第 46 片同一条）
    store.add(TruthRecord(record_type="ctq", content="CTQ hole_Ø8", trust_level="verified",
                          metadata={"feature": "hole_Ø8", "drawing_feature": "TOP.hole_1",
                                    "nominal": 8.0, "lower_limit": 7.95,
                                    "upper_limit": 8.05, "inspection_method": "CMM"}),
              tenant_id=T, project_id="DRIFT-DXF")
    spec = tmp_path / "spec.json"
    assert main(["drawing", "spec", "--db", str(db), "--project", "DRIFT-DXF",
                 "--out", str(spec), "--json"]) == 0
    dxf = tmp_path / "bracket.dxf"
    assert main(["drawing", "generate", "--out", str(dxf), "--part", "bracket",
                 "--views", "TOP", "--spec", str(spec), "--db", str(db),
                 "--project", "DRIFT-DXF", "--json"]) == 0
    rows = [r for r in store.query(record_type="artifact_version", tenant_id=T,
                                   project_id="DRIFT-DXF")
            if (r.metadata or {}).get("artifact") == "drawing_dxf"]
    assert len(rows) == 1, rows

    resolvers = build_resolvers(str(db), "DRIFT-DXF")
    resolver = resolvers["drawing_dxf"]
    first = classify_record(rows[0], resolver)
    assert first["state"] == IN_SYNC, first

    spec.write_text(spec.read_text(encoding="utf-8").replace("8.05", "8.06"),
                    encoding="utf-8")
    second = classify_record(store.get(rows[0].record_id), resolver)
    assert second["state"] == DRIFTED, second


def test_missing_db_is_usage_error_not_drift(env, tmp_path):
    rc = main(["truth", "drift", "--db", str(tmp_path / "nope.db"), "--project", P])
    assert rc == 2, rc
