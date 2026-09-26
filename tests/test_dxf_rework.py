"""图纸制品的返工执行器（F-REWORK-DXF 第 47 片）。

第 46 片把「声明 → 图纸」的边接上之后，`truth propagate` 才真的会生成 `drawing_dxf`
的返工任务；那一片的处置是「点名拒掉」，本片把执行器补上。钉住的是这五件事：

1. **什么都不变时一个字节都不动**（`unchanged`）：库里的 stale 真的收口、版本 bump，
   但产物哈希前后一致——「没人跑」与「跑过且证明未变」必须在库里分得开；
2. **声明变了就重画出图**（`rewrote`）：文件与记录一起演进到**新的输入签名**，
   且**不新增版本记录**（引擎是对这一条 bump 版本的，另起一版会把旧那条永远留在 stale）；
3. **重建不出同一次出图就失败**：缺输入（第 46 片之前写的记录没有 `model_*`）、
   上游声明文件读不到、模型源文件读不到、`render` 抛异常、`render` 回的哈希与磁盘不符
   ——一律 `ok=False` 交回引擎的有界退避，绝不记成"返工完成"；
4. **文件被删/被手改要补回来**（`file_restored`）；
5. 命令面：`truth rework` 现在认两种制品，其余（BOM/成本）仍在烧 attempts 之前点名拒掉。

失败类判据用注入的假 `render`（不碰 CAD 内核，秒级）；两条真跑的用例走真出图，
证明默认 `render` 接的确实是 `aipd drawing generate` 那条生产路径而不是另一份实现。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from aipd_os.cad.dxf_lineage import model_input_digest, record_dxf_lineage
from aipd_os.cad.dxf_rework import rework_dxf_artifact
from aipd_os.cli.main import main
from aipd_os.product_truth import LineageGraph, ProductTruthStore, TruthRecord
from aipd_os.product_truth.propagation import PropagationEngine
from aipd_os.state.db import AIPDStateDB

T = "default"
P = "DXF-REWORK"

HOLE = {"feature": "hole_Ø8", "drawing_feature": "TOP.hole_1", "nominal": 8.0,
        "lower_limit": 7.95, "upper_limit": 8.05, "inspection_method": "CMM"}


@pytest.fixture()
def env(tmp_path):
    db = tmp_path / "state.db"
    state = AIPDStateDB(db)
    state.ensure_default_tenant()
    state.init_project(T, P, "dxf rework 测试", "evidence")
    return tmp_path, db


def _store(db):
    return ProductTruthStore(str(db), tenant_id=T, project_id=P)


def _seed(db, meta_over=None):
    meta = dict(HOLE)
    meta.update(meta_over or {})
    return _store(db).add(TruthRecord(record_type="ctq", content="CTQ hole_Ø8",
                                      trust_level="verified", metadata=meta),
                          tenant_id=T, project_id=P)


def _spec(tmp_path, db, name="spec.json"):
    out = tmp_path / name
    assert main(["drawing", "spec", "--db", str(db), "--project", P,
                 "--out", str(out), "--json"]) == 0
    return out


def _generate(tmp_path, db, spec, capsys):
    dxf = tmp_path / "bracket.dxf"
    rc = main(["drawing", "generate", "--out", str(dxf), "--part", "bracket",
               "--views", "TOP", "--spec", str(spec), "--db", str(db),
               "--project", P, "--json"])
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert rc == 0, payload
    return dxf, payload


def _dxf_rows(db):
    return [r for r in _store(db).query(record_type="artifact_version",
                                        tenant_id=T, project_id=P)
            if (r.metadata or {}).get("artifact") == "drawing_dxf"]


def _pending_tasks(db, truth_id):
    return [t for t in PropagationEngine(_store(db)).list_tasks(status="pending")
            if t.truth_id == truth_id]


def _fake_record(tmp_path, db, *, drop=()):
    """不经 CAD 直接造一条图纸记录（失败类判据用它，秒级）。"""
    dxf = tmp_path / "fake.dxf"
    dxf.write_bytes(b"DXF-SECTION-0\n")
    store = _store(db)
    out = record_dxf_lineage(
        store, dxf_path=dxf, spec_path=None, part="bracket", revision="A",
        views=["TOP"], scale=1.0, sheet="A3", material="AL",
        sections=[], details=[],
        model=model_input_digest(step=None, native=None),
        dxf_sha256=hashlib.sha256(dxf.read_bytes()).hexdigest(),
        tenant_id=T, project_id=P)
    if drop:
        meta = dict(store.get(out["record_id"], tenant_id=T,
                              project_id=P).metadata)
        for key in drop:
            meta.pop(key, None)
        store.update(out["record_id"], tenant_id=T, project_id=P, metadata=meta)
    return out["record_id"], dxf


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------- 两条真跑的路径

def test_rework_with_nothing_changed_writes_not_a_byte(env, capsys):
    """签名一致 ⇒ `unchanged`：文件一个字节不动，但 stale 真的在库里收口。"""
    tmp_path, db = env
    ctq = _seed(db)
    spec = _spec(tmp_path, db)
    dxf, payload = _generate(tmp_path, db, spec, capsys)
    dxf_id = payload["lineage"]["record_id"]
    before, version_before = _sha(dxf), _store(db).get(dxf_id).version

    PropagationEngine(_store(db)).on_upstream_changed(ctq)
    assert _store(db).get(dxf_id).status == "stale"
    task_id = _pending_tasks(db, dxf_id)[0].task_id
    assert main(["truth", "rework", "--db", str(db), "--project", P,
                 "--task", task_id, "--json"]) == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["results"][0]["executor"]["outcome"] == "unchanged"
    assert out["results"][0]["executor"]["file_written"] is False
    assert _sha(dxf) == before, "unchanged 却动了产物文件"
    rec = _store(db).get(dxf_id)
    assert rec.status == "active" and rec.version > version_before
    assert rec.metadata["last_rework"]["outcome"] == "unchanged"


def test_rework_after_declaration_change_redraws_the_same_record(env, capsys):
    """声明变了 ⇒ 重跑出图并把**这一条**记录演进到新签名，不另起一版。

    改的是公差带（7.98–8.02）而不是名义值：图纸实测孔径是 8.0，把窗口挪到不含 8.0
    的位置会让重跑判 `ctq_window_violation` 退码 4——那正是本执行器**拒绝**当成成功的
    形状（见 test_render_refuses_an_unheld_drawing），不是这里要测的演进。
    """
    tmp_path, db = env
    ctq = _seed(db)
    spec = _spec(tmp_path, db)
    dxf, payload = _generate(tmp_path, db, spec, capsys)
    dxf_id = payload["lineage"]["record_id"]
    store = _store(db)
    old_sig = store.get(dxf_id).metadata["input_signature"]
    old_file = _sha(dxf)

    # 改 CTQ 并让声明文件按新 CTQ 重出（这一步是第 45 片执行器的活）
    rec = store.get(ctq)
    meta = dict(rec.metadata)
    meta.update({"lower_limit": 7.98, "upper_limit": 8.02})
    store.update(ctq, tenant_id=T, project_id=P, metadata=meta)
    assert main(["drawing", "spec", "--db", str(db), "--project", P,
                 "--out", str(spec), "--json"]) == 0
    new_spec = json.loads(
        capsys.readouterr().out.strip().splitlines()[-1]
    )["lineage"]["record_id"]
    PropagationEngine(store).on_upstream_changed(ctq)
    task_id = _pending_tasks(db, dxf_id)[0].task_id
    assert main(["truth", "rework", "--db", str(db), "--project", P,
                 "--task", task_id, "--json"]) == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    ex = out["results"][0]["executor"]
    assert ex["outcome"] == "rewrote", ex
    assert ex["file_written"] is True
    assert _sha(dxf) != old_file, "rewrote 却没重画文件"

    # 边必须改挂到**当前**那份声明记录上：声明改了就另有一条 spec 版本记录，
    # 还指着旧那条等于把这张图挂在一份已经不存在的公差上。
    spec_ids = {r.record_id for r in _store(db).query(record_type="artifact_version",
                                                      tenant_id=T, project_id=P)
                if (r.metadata or {}).get("artifact") == "drawing_spec"}
    assert len(spec_ids) == 2, "声明改了应当有两条版本记录，本前提不成立则这条断言是空的"
    assert ex["upstream_record_id"] == new_spec
    assert ex["edges"] == 1
    edges = {(e["upstream_id"], e["downstream_id"])
             for e in LineageGraph(store).edges(tenant_id=T, project_id=P)}
    assert (new_spec, dxf_id) in edges, "返工后图纸仍挂在旧声明记录上"

    rows = _dxf_rows(db)
    assert len(rows) == 1, "返工不许另起一版：引擎 bump 的是这一条记录"
    assert rows[0].status == "active"
    assert rows[0].metadata["input_signature"] != old_sig
    assert rows[0].metadata["input_signature"] == ex["input_signature"]
    assert ex["input_signature"][:16] in rows[0].content, \
        "正文里的签名必须跟着演进（生产面与返工面共用同一份拼装）"


# ---------------------------------------------------------------- 失败类判据

def test_missing_inputs_refuse_instead_of_guessing(env):
    """记录里缺模型来源 ⇒ 失败并点名，不许拿「默认黄金模型」猜一次重画。"""
    tmp_path, db = env
    rid, _dxf = _fake_record(tmp_path, db, drop=("model_digest", "material"))
    called = []
    out = rework_dxf_artifact(_store(db), rid,
                              render=lambda meta: called.append(1) or "x")
    assert out["ok"] is False and out["outcome"] == "missing_inputs"
    assert sorted(out["missing_inputs"]) == ["material", "model_digest"]
    assert called == [], "缺输入还去出图 = 把猜出来的图记成重算过"


def test_unreadable_declaration_file_is_not_read_as_no_upstream(env):
    """记录声明了上游声明文件、但文件读不到 ⇒ 失败，不能降级成「无上游」再画一遍。"""
    tmp_path, db = env
    rid, _dxf = _fake_record(tmp_path, db)
    store = _store(db)
    meta = dict(store.get(rid).metadata)
    meta["spec_path"] = str(tmp_path / "gone.json")
    store.update(rid, tenant_id=T, project_id=P, metadata=meta)
    out = rework_dxf_artifact(store, rid, render=lambda meta: "unused")
    assert out["ok"] is False and out["outcome"] == "missing_spec_file"


def test_missing_model_source_file_refuses(env):
    tmp_path, db = env
    rid, _dxf = _fake_record(tmp_path, db)
    store = _store(db)
    meta = dict(store.get(rid).metadata)
    meta.update({"model_kind": "step", "model_source": str(tmp_path / "gone.step")})
    store.update(rid, tenant_id=T, project_id=P, metadata=meta)
    out = rework_dxf_artifact(store, rid, render=lambda meta: "unused")
    assert out["ok"] is False and out["outcome"] == "model_unavailable"
    assert "读不到" in out["reason"]


def test_render_exception_is_not_a_success(env):
    """先让磁盘那份不是记录里的哈希（否则走 unchanged，压根不会去出图），再让 render 抛。"""
    tmp_path, db = env
    rid, dxf = _fake_record(tmp_path, db)
    store = _store(db)
    dxf.write_bytes(b"hacked\n")          # 撑开 file_lost，才到得了 render
    before = _sha(dxf)

    def boom(meta):
        raise RuntimeError("内核缺失")

    out = rework_dxf_artifact(store, rid, render=boom)
    assert out["ok"] is False and out["outcome"] == "render_failed"
    assert "内核缺失" in out["reason"]
    assert _sha(dxf) == before


def test_a_drawing_that_does_not_hold_is_not_a_successful_rework(env, capsys):
    """重跑出来判「合格域未收口」（退码 4）⇒ 返工不许记成成功、记录不许演进。

    这条是本片写用例时撞出来的：把 CTQ 窗口挪到不含实测 8.0 的位置，声明变了、图也画出来了，
    但图上那条尺寸不达要求。把这种结果记成"返工完成"并 bump 版本，等于让引擎替我们把
    一条未收口的事实洗成新版本。
    """
    tmp_path, db = env
    ctq = _seed(db)
    spec = _spec(tmp_path, db)
    dxf, payload = _generate(tmp_path, db, spec, capsys)
    dxf_id = payload["lineage"]["record_id"]
    store = _store(db)
    before = _sha(dxf)
    sig_before = store.get(dxf_id).metadata["input_signature"]

    rec = store.get(ctq)
    meta = dict(rec.metadata)
    meta.update({"nominal": 7.0, "lower_limit": 6.95, "upper_limit": 7.05})
    store.update(ctq, tenant_id=T, project_id=P, metadata=meta)
    assert main(["drawing", "spec", "--db", str(db), "--project", P,
                 "--out", str(spec), "--json"]) == 0
    PropagationEngine(store).on_upstream_changed(ctq)
    task_id = _pending_tasks(db, dxf_id)[0].task_id
    capsys.readouterr()
    assert main(["truth", "rework", "--db", str(db), "--project", P,
                 "--task", task_id, "--json"]) == 4
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    ex = out["results"][0]["executor"]
    assert ex["ok"] is False and ex["outcome"] == "render_failed"
    assert "退码 4" in ex["reason"] and "ctq_window_violation" in ex["reason"]
    assert _sha(dxf) == before, "未收口的重跑不许把磁盘那份覆盖掉"
    assert store.get(dxf_id).metadata["input_signature"] == sig_before
    assert store.get(dxf_id).status == "stale", "任务没收口，记录就该还是 stale"


def test_render_hash_disagreeing_with_disk_is_not_a_success(env):
    """执行器回的哈希与磁盘现状不一致 ⇒ 不能拿它 bump 版本（否则库里记的是没发生的事）。"""
    tmp_path, db = env
    rid, dxf = _fake_record(tmp_path, db)
    store = _store(db)
    sig = store.get(rid).metadata["input_signature"]
    dxf.write_bytes(b"someone edited the drawing by hand\n")
    out = rework_dxf_artifact(store, rid, render=lambda meta: "0" * 64)
    assert out["ok"] is False and out["outcome"] == "render_disagrees"
    assert store.get(rid).metadata["input_signature"] == sig, "失败不许演进记录"


def test_other_artifacts_are_not_this_executors_business(env):
    tmp_path, db = env
    store = _store(db)
    spec_rec = store.add(TruthRecord(record_type="artifact_version",
                                     content="spec", trust_level="high",
                                     metadata={"artifact": "drawing_spec"}),
                         tenant_id=T, project_id=P)
    out = rework_dxf_artifact(store, spec_rec, render=lambda meta: "x")
    assert out["ok"] is False and out["outcome"] == "unsupported_artifact"


def test_file_tampered_with_same_inputs_restores_it(env):
    """签名没变但磁盘上那份不是记录里的哈希 ⇒ 重跑补回， outcome=file_restored。"""
    tmp_path, db = env
    rid, dxf = _fake_record(tmp_path, db)
    store = _store(db)
    dxf.write_bytes(b"hacked\n")

    def render(meta):
        dxf.write_bytes(b"DXF-SECTION-0\n")   # 同输入 ⇒ 同一份字节
        return _sha(dxf)

    out = rework_dxf_artifact(store, rid, render=render)
    assert out["ok"] is True and out["outcome"] == "file_restored"
    assert out["file_written"] is True and out["edges"] == 0
    assert store.get(rid).metadata["dxf_sha256"] == _sha(dxf)


def test_rework_never_leaves_a_second_active_version_on_one_path(env, capsys):
    """命令面串起来：改两次声明、返工两次，图纸记录仍只有一条 active。"""
    tmp_path, db = env
    ctq = _seed(db)
    spec = _spec(tmp_path, db)
    _dxf, payload = _generate(tmp_path, db, spec, capsys)
    dxf_id = payload["lineage"]["record_id"]
    store = _store(db)

    for lower, upper in ((7.98, 8.02), (7.99, 8.01)):
        rec = store.get(ctq)
        meta = dict(rec.metadata)
        meta.update({"lower_limit": lower, "upper_limit": upper})
        store.update(ctq, tenant_id=T, project_id=P, metadata=meta)
        assert main(["drawing", "spec", "--db", str(db), "--project", P,
                     "--out", str(spec), "--json"]) == 0
        PropagationEngine(store).on_upstream_changed(ctq)
        task_id = _pending_tasks(db, dxf_id)[0].task_id
        assert main(["truth", "rework", "--db", str(db), "--project", P,
                     "--task", task_id, "--json"]) == 0
        capsys.readouterr()

    rows = _dxf_rows(db)
    active = [r for r in rows if r.status == "active"]
    assert len(active) == 1 and active[0].record_id == dxf_id
    assert active[0].metadata["last_rework"]["outcome"] == "rewrote"


# ---------------------------------------------------------------- 命令面极性

def test_rework_cli_now_supports_both_artifacts_and_still_refuses_bom(env, capsys):
    """`supported_artifact` 单值变 `supported_artifacts` 列表；BOM 仍在烧 attempts 前拒。"""
    tmp_path, db = env
    store = _store(db)
    bom = store.add(TruthRecord(record_type="artifact_version", content="bom row",
                                trust_level="high",
                                metadata={"artifact": "bom"}),
                   tenant_id=T, project_id=P)
    engine = PropagationEngine(store)
    engine._create_rework(bom, "验证命令面制品清单", 3)  # noqa: SLF001
    task_id = engine.list_tasks(status="pending")[0].to_dict()["task_id"]
    assert main(["truth", "rework", "--db", str(db), "--project", P,
                 "--task", task_id, "--json"]) == 4
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert sorted(out["supported_artifacts"]) == ["drawing_dxf", "drawing_spec"]
    assert out["refused"][0]["artifact_kind"] == "bom"
    assert store.get(bom).status == "active", "拒掉不是失败，不该把记录打成 blocked"
