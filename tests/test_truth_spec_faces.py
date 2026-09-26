"""`drawing_spec` 记录的**两个输入面**（F-DRIFT-5 第 57 片）。

第 56 片 §六 把一件事钉成了缺席断言：属主改了 CTQ 限值之后 `truth drift` / `truth sweep`
**看不见**——因为那一版的 `drawing_spec` 只比"声明文件还是不是当初那份"，而文件恰恰没动。
这一片把源面补上：按这条记录**自己声明的** `ctq_refs` 重跑一次 `spec_from_ctq`，
与同一个 `metadata.spec_sha256` 基线比。形状借 Argo CD 实读的那句
"compares the current, live state against the desired target state"——两侧都现算、基线只存一份，
所以第 43~56 片写下的存量记录**不需要迁移**。

钉三组，每组都有对面的不开火对照：
1. **两面各自独立开火**：改 CTQ 只红源面、手改文件只红文件面；
2. **不许过度开火**：作用域里新增一条与本记录无关的 CTQ ⇒ 这条记录仍然 `in_sync`
   （覆盖率是发布门禁 `gdt_covers_ctq` 那一格的事，不是漂移探测的事）；
3. **不可判不跨面折叠**：任一文件与基线不等就是漂移（哪怕另一面算不出）；
   没有一面有基线 ⇒ `no_record_signature`；有基线但算不出 ⇒ `undecidable`。
"""
from __future__ import annotations

import json

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
P = "SPEC-FACES"


@pytest.fixture()
def env(tmp_path):
    db = tmp_path / "state.db"
    state = AIPDStateDB(str(db))
    state.ensure_default_tenant(T)
    state.init_project(T, P, "两个输入面", "evidence")
    return tmp_path, db


def _store(db):
    return ProductTruthStore(str(db), tenant_id=T, project_id=P)


def _add_ctq(db, *, feature="hole_Ø8", drawing="TOP.hole_1", upper="8.05",
             by="潘工"):
    return main(["ctq", "add", "--db", str(db), "--project", P,
                 "--feature", feature, "--drawing-feature", drawing,
                 "--nominal", "8.0", "--lower", "7.95", "--upper", upper,
                 "--inspection", "CMM", "--by", by])


def _spec(db, tmp_path, capsys, name="spec.json"):
    out = tmp_path / name
    rc = main(["drawing", "spec", "--db", str(db), "--project", P,
               "--out", str(out), "--json"])
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert rc == 0, payload
    return out, payload


def _classify(db, record_id):
    resolver = build_resolvers(str(db), P, T)["drawing_spec"]
    verdict = classify_record(_store(db).get(record_id), resolver)
    return verdict, {f["face"]: f for f in verdict["faces"]}


def _declare(env, capsys):
    """种一条生产形状的声明：链头 `ctq add` → `drawing spec`，返回 (文件, 记录号, CTQ 记录)。"""
    tmp_path, db = env
    assert _add_ctq(db) == 0
    ctq = _store(db).query(record_type="ctq", tenant_id=T, project_id=P)[0]
    out, payload = _spec(db, tmp_path, capsys)
    return out, payload["lineage"]["record_id"], ctq


# ---------- 一、两面各自独立开火 ----------

def test_clean_declaration_is_in_sync_with_both_faces_present(env, capsys):
    """前提：一份刚生产的声明，两个面都得**有值且相等**（判据不许靠缺席蒙绿）。"""
    tmp_path, db = env
    _, rid, ctq = _declare(env, capsys)
    verdict, faces = _classify(db, rid)
    assert verdict["state"] == IN_SYNC, verdict
    assert set(faces) == {"file", "source"}, faces
    for face in ("file", "source"):
        assert faces[face]["current"] == faces[face]["stored"], faces[face]
        assert faces[face]["current"], faces[face]
    rec = _store(db).get(rid)
    assert [str(r) for r in rec.metadata["ctq_refs"]] == [str(ctq.record_id)]


def test_ctq_limit_change_is_discovered_by_drift_alone(env, capsys):
    """本片存在的理由：只改权威表里的限值，**不跑 propagate、不跑 rework**，drift 自己就发现。"""
    tmp_path, db = env
    out, rid, ctq = _declare(env, capsys)
    store = _store(db)
    meta = dict(ctq.metadata)
    meta["upper_limit"] = 8.10
    assert store.update(ctq.record_id, tenant_id=T, project_id=P, metadata=meta) is not None

    verdict, faces = _classify(db, rid)
    assert verdict["state"] == DRIFTED, verdict
    assert "source面" in verdict["reason"], verdict["reason"]
    assert faces["file"]["current"] == faces["file"]["stored"], \
        f"文件一个字节没动，文件面不许一起红：{faces}"

    rc = main(["truth", "drift", "--db", str(db), "--project", P, "--json"])
    assert rc == 4, rc


def test_recomputed_gap_is_drift_not_undecidable(env, capsys):
    """上游记录被改坏（标称值没了）⇒ 重算出的是**缺口**，不是"算不出"。

    缺口用一个确定性的 `ctq-gap:` 键参与比较，这样"这份声明按当前要求已经立不住"
    会以漂移的身份出现在清单里；把它折成不可判，drift 的退出码就从 4 掉回 0。
    """
    tmp_path, db = env
    _out, rid, ctq = _declare(env, capsys)
    store = _store(db)
    meta = dict(ctq.metadata)
    meta.pop("nominal")
    assert store.update(ctq.record_id, tenant_id=T, project_id=P, metadata=meta) is not None

    verdict, faces = _classify(db, rid)
    assert verdict["state"] == DRIFTED, verdict
    assert "source面" in verdict["reason"] and "缺口" in verdict["reason"], verdict["reason"]
    assert str(faces["source"]["current"]).startswith("ctq-gap"), faces["source"]

    rc = main(["truth", "drift", "--db", str(db), "--project", P, "--json"])
    assert rc == 4, rc


def test_hand_edited_declaration_fires_only_the_file_face(env, capsys):
    """第 51 片那半判据不许退化：手改产物文件仍然单独开火，且不被源面遮蔽。"""
    tmp_path, db = env
    out, rid, _ctq = _declare(env, capsys)
    payload = json.loads(out.read_text(encoding="utf-8"))
    payload["features"][0]["nominal"] = 9.99
    out.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True),
                   encoding="utf-8")

    verdict, faces = _classify(db, rid)
    assert verdict["state"] == DRIFTED, verdict
    assert "file面" in verdict["reason"], verdict["reason"]
    assert faces["source"]["current"] == faces["source"]["stored"], faces


def test_deactivated_upstream_ctq_is_drift_not_undecidable(env, capsys):
    """上游被停用：输入读得到、也算得出，只是算出来的东西说这份声明立不住 ⇒ 漂移。

    折进「不可判」等于把最响的警报调成哑——第 44 片怕的正是这个方向。
    """
    tmp_path, db = env
    _out, rid, ctq = _declare(env, capsys)
    assert _store(db).update(ctq.record_id, tenant_id=T, project_id=P,
                             status="stale") is not None

    verdict, faces = _classify(db, rid)
    assert verdict["state"] == DRIFTED, verdict
    assert "source面" in verdict["reason"] and "已不在 active 集合里" in verdict["reason"], \
        verdict["reason"]
    assert faces["file"]["current"] == faces["file"]["stored"], faces


# ---------- 二、不许过度开火 ----------

def test_unrelated_new_ctq_is_not_drift(env, capsys):
    """作用域里新增一条**别的尺寸**的 CTQ ⇒ 本记录仍然 `in_sync`。

    这条就是"源面按全作用域 CTQ 算"那个错做法的反面对照：源面只吃记录自己声明的
    `ctq_refs`，覆盖率归发布门禁（`gdt_covers_ctq`）管。
    """
    tmp_path, db = env
    _out, rid, _ctq = _declare(env, capsys)
    assert _add_ctq(db, feature="slot_Ø5", drawing="TOP.slot_1") == 0
    assert len(_store(db).query(record_type="ctq", tenant_id=T, project_id=P)) == 2

    verdict, faces = _classify(db, rid)
    assert verdict["state"] == IN_SYNC, \
        f"源面吃进了与本记录无关的 CTQ：{verdict}"
    assert faces["source"]["current"] == faces["source"]["stored"]


def test_rework_then_drift_is_green_again(env, capsys):
    """补上源面之后，链上三跳仍然收口：sweep 落刀 → rework 按新限值重写 → drift 转绿。"""
    tmp_path, db = env
    out, rid, ctq = _declare(env, capsys)
    store = _store(db)
    meta = dict(ctq.metadata)
    meta["upper_limit"] = 8.10
    store.update(ctq.record_id, tenant_id=T, project_id=P, metadata=meta)

    assert main(["truth", "sweep", "--db", str(db), "--project", P]) == 4
    assert str(store.get(rid).status) == "stale"
    assert main(["truth", "rework", "--db", str(db), "--project", P,
                 "--all-pending"]) == 0
    assert "8.1" in out.read_text(encoding="utf-8")

    verdict, _faces = _classify(db, rid)
    assert verdict["state"] == IN_SYNC, verdict
    assert main(["truth", "drift", "--db", str(db), "--project", P]) == 0


# ---------- 三、不可判不许跨面折叠 ----------

def test_missing_path_is_no_baseline_not_a_pass(env, capsys):
    """文件面连基线都没有 ⇒ 整条记 `no_record_signature`，不能因为源面合就宣布通过。"""
    tmp_path, db = env
    _out, rid, _ctq = _declare(env, capsys)
    store = _store(db)
    rec = store.get(rid)
    meta = dict(rec.metadata)
    meta.pop("path")
    assert store.update(rid, tenant_id=T, project_id=P, metadata=meta) is not None

    verdict, faces = _classify(db, rid)
    assert verdict["state"] == NO_SIGNATURE, verdict
    assert faces["file"]["stored"] is None and faces["file"]["current"] is None
    assert faces["source"]["current"] == faces["source"]["stored"]


def test_drifted_face_outranks_an_uncomputable_one(env, capsys):
    """一红一算不出 ⇒ 判 `drifted`（保守方向不许反过来），并把两边的话都留下。

    形状：源面被抽掉 `ctq_refs`（重算无从），文件面被人手改 ⇒ 只有后者能开火。
    """
    tmp_path, db = env
    out, rid, _ctq = _declare(env, capsys)
    store = _store(db)
    rec = store.get(rid)
    meta = dict(rec.metadata)
    meta.pop("ctq_refs")                            # 源面：算不出
    store.update(rid, tenant_id=T, project_id=P, metadata=meta)
    payload = json.loads(out.read_text(encoding="utf-8"))
    payload["features"][0]["nominal"] = 9.99        # 文件面：与基线不等
    out.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True),
                   encoding="utf-8")

    verdict, faces = _classify(db, rid)
    assert verdict["state"] == DRIFTED, verdict
    assert "file面" in verdict["reason"] and "ctq_refs" in verdict["reason"], \
        verdict["reason"]
    assert faces["file"]["current"] != faces["file"]["stored"]
    assert faces["source"]["current"] is None


def test_resolver_that_returns_no_face_is_undecidable():
    """恒真守卫：一把一个面都不交出来的尺子，绝不能读成"一致"。"""
    rec = type("R", (), {"record_id": "T-1", "metadata": {"artifact": "drawing_spec"},
                          "status": "active"})()
    out = classify_record(rec, lambda m: [])
    assert out["state"] == UNDECIDABLE and "不开火" in out["reason"], out


def test_faces_are_a_sequence_protocol_for_single_face_artifacts(env):
    """单面制品（bom/DXF/…）走同一个判据：一个 `input` 面，漂与不漂都不多出别的态。"""
    tmp_path, db = env
    store = _store(db)
    rec = type("R", (), {"record_id": "T-2", "status": "active",
                         "metadata": {"artifact": "bom", "input_signature": "abc"}})()
    resolvers = build_resolvers(str(db), P, T)
    bom = classify_record(rec, resolvers["bom"])
    assert bom["state"] == UNDECIDABLE, bom
    assert [f["face"] for f in bom["faces"]] == ["input"], bom["faces"]
    assert bom["faces"][0]["reason"] == "记录里没写 bom_id，认不出该重算哪张 BOM"
    assert "input面" in bom["reason"], bom["reason"]
    single = classify_record(rec, lambda m: [Face("input", "abc", "abc", None)])
    assert single["state"] == IN_SYNC and len(single["faces"]) == 1, single
    assert store.query(record_type="ctq", tenant_id=T, project_id=P) == []


def test_scan_buckets_still_partition_the_two_face_record(env, capsys):
    """分桶与 `should_be_stale` 的形状不变：多面记录进的是同四个桶，没有第五态。"""
    tmp_path, db = env
    _out, rid, ctq = _declare(env, capsys)
    store = _store(db)
    meta = dict(ctq.metadata)
    meta["upper_limit"] = 8.10
    store.update(ctq.record_id, tenant_id=T, project_id=P, metadata=meta)

    report = scan_drift(store, resolvers=build_resolvers(str(db), P, T),
                        tenant_id=T, project_id=P)
    assert set(report["counts"]) == {IN_SYNC, DRIFTED, UNDECIDABLE, NO_SIGNATURE}
    assert report["counts"][DRIFTED] == 1, report["counts"]
    assert [r["record_id"] for r in report["should_be_stale"]] == [rid]
