"""`aipd truth rework` —— `run_rework` 的第一个产品调用点（F-REWORK 第 45 片）。

这里钉的不是"命令能跑"，而是**返工成功的凭据从哪来**：

- `unchanged`：重算哈希与记录一致**且磁盘文件重算后也一致** ⇒ 产物一个字节都不许动，
  但引擎必须真的 bump 版本、把 stale 关掉（否则"没做"与"做了且证明未变"在库里同形）；
- `rewrote` / `file_restored`：内容变了 / 文件被删或被手改 ⇒ 真的重写文件并更新记录；
- `gap`：重算有缺口 ⇒ **失败**，走引擎的有界退避与 max_attempts，绝不记成功；
- 执行器不认识的制品：必须在**烧 attempts 之前**拒掉（`attempts` 仍是 0）。
"""
from __future__ import annotations

import json

import pytest

from aipd_os.cli.main import main
from aipd_os.product_truth import LineageGraph, ProductTruthStore, TruthRecord
from aipd_os.state.db import AIPDStateDB

T = "default"
P = "REWORK-TEST"


def _hole(feature, drawing_feature, nominal=6.0, lo=5.95, hi=6.05, **extra):
    return {"feature": feature, "drawing_feature": drawing_feature,
            "nominal": nominal, "lower_limit": lo, "upper_limit": hi,
            "inspection_method": "CMM", **extra}


@pytest.fixture()
def env(tmp_path):
    db = tmp_path / "state.db"
    state = AIPDStateDB(db)
    state.ensure_default_tenant()
    state.init_project(T, P, "rework 测试", "evidence")
    return tmp_path, db


def _store(db):
    return ProductTruthStore(str(db), tenant_id=T, project_id=P)


def _seed(db, *metas):
    store = _store(db)
    return [store.add(TruthRecord(record_type="ctq", content=f"CTQ {m['feature']}",
                                  trust_level="verified", metadata=dict(m)),
                      tenant_id=T, project_id=P) for m in metas]


def _make_spec(tmp_path, db):
    """走真实生产路径：`aipd drawing spec` 落声明文件 + artifact_version 记录 + 边。"""
    out = tmp_path / "spec.json"
    rc = main(["drawing", "spec", "--db", str(db), "--project", P,
               "--out", str(out), "--json"])
    assert rc == 0, out
    return out


def _version_record(db):
    rows = _store(db).query(record_type="artifact_version", tenant_id=T, project_id=P)
    assert len(rows) == 1, [r.record_id for r in rows]
    return rows[0]


def _pending_task_ids(db):
    from aipd_os.product_truth.propagation import PropagationEngine

    engine = PropagationEngine(_store(db))
    return [t.to_dict() for t in engine.list_tasks(status="pending")]


def test_unchanged_declaration_rework_writes_no_artifact_bytes(env):
    """内容没变（改的是不进声明正文的字段）⇒ 产物不动，但返工真的收口、版本真的+1。"""
    tmp_path, db = env
    ctq = _seed(db, _hole("hole_Ø6", "TOP.hole_1"))[0]
    spec_path = _make_spec(tmp_path, db)
    before_bytes = spec_path.read_bytes()
    rec = _version_record(db)
    assert rec.version == 1

    store = _store(db)
    meta = dict(rec.metadata)
    meta["last_rework"] = {"outcome": "rewrote", "spec_sha256": meta["spec_sha256"]}
    # 制造一个"必须返工"的下游状态：把记录标 stale（propagate 的效果，见下一条用例）
    store.set_status(rec.record_id, "stale")
    from aipd_os.product_truth.propagation import PropagationEngine

    PropagationEngine(store).on_upstream_changed(ctq, reason="载荷口径改了")
    task = _pending_task_ids(db)[0]

    rc = main(["truth", "rework", "--db", str(db), "--project", P,
               "--task", task["task_id"], "--json"])
    assert rc == 0
    after = spec_path.read_bytes()
    assert after == before_bytes, "unchanged 结论不许动产物文件一个字节"
    rec2 = _version_record(db)
    assert rec2.version == 2, "引擎没真的 bump 版本 = 这次返工没落账"
    assert rec2.status == "active"
    assert rec2.metadata["last_rework"]["outcome"] == "unchanged"
    assert rec2.metadata["last_rework"]["file_written"] is False


def test_changed_ctq_rewrites_declaration_and_recomputes_edges(env):
    """CTQ 数值改了 ⇒ 声明必须被重写、记录换哈希、血缘边跟着新的引用集合。"""
    tmp_path, db = env
    ctq = _seed(db, _hole("hole_Ø6", "TOP.hole_1"))[0]
    spec_path = _make_spec(tmp_path, db)
    old_sha = _version_record(db).metadata["spec_sha256"]

    store = _store(db)
    ctq_rec = store.get(ctq, tenant_id=T, project_id=P)
    meta = dict(ctq_rec.metadata)
    meta.update({"nominal": 7.0, "lower_limit": 6.9, "upper_limit": 7.1})
    store.update(ctq, tenant_id=T, project_id=P, metadata=meta)
    from aipd_os.product_truth.propagation import PropagationEngine

    PropagationEngine(store).on_upstream_changed(ctq, reason="孔径改到 7")
    task = _pending_task_ids(db)[0]

    rc = main(["truth", "rework", "--db", str(db), "--project", P,
               "--task", task["task_id"], "--json"])
    assert rc == 0
    rec = _version_record(db)
    assert rec.metadata["spec_sha256"] != old_sha
    assert rec.metadata["last_rework"]["outcome"] == "rewrote"
    on_disk = json.loads(spec_path.read_text("utf-8"))
    assert on_disk["features"][0]["tolerance"] == {"upper": 0.1, "lower": -0.1}
    assert rec.content.endswith(f"← CTQ {ctq}")
    edges = {(e["upstream_id"], e["downstream_id"])
             for e in LineageGraph(store).edges(tenant_id=T, project_id=P)}
    assert (ctq, rec.record_id) in edges


def test_deleted_artifact_is_restored_even_when_content_matches(env):
    """内容没变但文件不见了 ⇒ 仍要重写（BitBake 的"戳失配就重跑"，不是"记录说没变就跳过"）。"""
    tmp_path, db = env
    ctq = _seed(db, _hole("hole_Ø6", "TOP.hole_1"))[0]
    spec_path = _make_spec(tmp_path, db)
    from aipd_os.product_truth.propagation import PropagationEngine

    store = _store(db)
    PropagationEngine(store).on_upstream_changed(ctq, reason="外部改过上游")
    spec_path.unlink()
    task = _pending_task_ids(db)[0]

    assert main(["truth", "rework", "--db", str(db), "--project", P,
                 "--task", task["task_id"]]) == 0
    assert spec_path.is_file(), "文件缺失必须补回来"
    assert _version_record(db).metadata["last_rework"]["outcome"] == "file_restored"


def test_gap_in_recomputation_is_a_failure_not_a_success(env):
    """重算出缺口 ⇒ 失败：走退避、烧 attempts，退码 4；三条跑满即 blocked。

    缺口是**后来**造出来的：第二条 CTQ 抢同一个 `drawing_feature`（口径 4「不自相矛盾」
    会把两条都摘掉并点名）。传播必须打在**已连边的那条** CTQ 上——新来的那条没有边，
    拿它 propagate 只会得到"受影响 0 条"，那正是上一版用例写错的地方。
    """
    tmp_path, db = env
    first = _seed(db, _hole("hole_Ø6", "TOP.hole_1"))[0]
    spec_path = _make_spec(tmp_path, db)
    before = spec_path.read_bytes()
    _seed(db, _hole("hole_Ø8", "TOP.hole_1", nominal=8.0, lo=7.95, hi=8.05))
    from aipd_os.product_truth.propagation import PropagationEngine

    store = _store(db)
    PropagationEngine(store).on_upstream_changed(first, reason="第二条 CTQ 抢同一特征")
    task_id = _pending_task_ids(db)[0]["task_id"]

    for expect_attempts in (1, 2, 3):
        assert main(["truth", "rework", "--db", str(db), "--project", P,
                     "--task", task_id, "--json"]) == 4
        task = _pending_task_ids(db)
        if expect_attempts < 3:
            assert task and task[0]["attempts"] == expect_attempts, task
    assert not _pending_task_ids(db), "跑满上限后不该还挂在 pending"
    assert spec_path.read_bytes() == before, "失败不许把半成品写进产物"


def test_unknown_artifact_is_refused_before_consuming_attempts(env):
    """执行器不认识的制品：不烧配额、不假装失败三次，但要逐条点名。

    宿主制品第 53 片换过一次：`artifact=bom` 已有执行器（再拿它当「不认识」的样本，
    读到的是 `missing_inputs` ⇒ 烧 attempts、打成 blocked），
    现在没有执行器的那一格是 `quote_batch`。
    """
    tmp_path, db = env
    store = _store(db)
    other = store.add(TruthRecord(
        record_type="artifact_version", content="报价批次 v1 sha256=deadbeef",
        trust_level="high",
        metadata={"artifact": "quote_batch", "path": str(tmp_path / "quote.json")}),
        tenant_id=T, project_id=P)
    from aipd_os.product_truth.propagation import PropagationEngine

    seed = _seed(db, _hole("hole_Ø6", "TOP.hole_1"))[0]
    PropagationEngine(store).on_upstream_changed(seed, reason="上游变了")
    # 直接给这条 BOM 记录建一个待办（模拟 propagate 覆盖到它的情形）
    engine = PropagationEngine(store)
    engine._create_rework(other, "手造待办：验证拒绝路径", 3)
    assert _pending_task_ids(db)

    rc = main(["truth", "rework", "--db", str(db), "--project", P,
               "--all-pending", "--json"])
    assert rc == 4
    tasks = _pending_task_ids(db)
    mine = [t for t in tasks if t["truth_id"] == other]
    assert mine and mine[0]["attempts"] == 0, "拒绝必须发生在烧 attempts 之前"


def test_refusals_are_visible_in_the_json_payload(env, capsys):
    """--json 里 refused 必须点名到 task_id 与制品类型，且 ok 与退码同向。"""
    tmp_path, db = env
    store = _store(db)
    other = store.add(TruthRecord(
        record_type="fact", content="某条 fact 记录",
        trust_level="high", metadata={"artifact": "quote_batch"}),
        tenant_id=T, project_id=P)
    from aipd_os.product_truth.propagation import PropagationEngine

    engine = PropagationEngine(store)
    engine._create_rework(other, "验证 json 面", 3)
    task_id = engine.list_tasks(status="pending")[0].to_dict()["task_id"]

    assert main(["truth", "rework", "--db", str(db), "--project", P,
                 "--task", task_id, "--json"]) == 4
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert [r["task_id"] for r in payload["refused"]] == [task_id]
    assert payload["refused"][0]["artifact_kind"] == "quote_batch"
    assert payload["results"] == []


def test_command_requires_a_task_selector(env):
    """既不给 --task 也不给 --all-pending ⇒ 2：不猜要跑哪一条。"""
    _tmp, db = env
    assert main(["truth", "rework", "--db", str(db), "--project", P]) == 2


def test_missing_database_is_not_reported_as_no_work(env, capsys):
    """库不存在 ⇒ 2，且不能把"读不到"说成"没有待办"。"""
    tmp_path, _db = env
    bogus = tmp_path / "nope.db"
    assert main(["truth", "rework", "--db", str(bogus), "--project", P,
                 "--all-pending"]) == 2
    assert "不存在" in capsys.readouterr().out
