"""Product Truth：结构化事实模型、失效传播与有界自动返工测试。"""
from __future__ import annotations

import pytest

from aipd_os.product_truth.lineage import CycleDetectedError, LineageGraph
from aipd_os.product_truth.models import TruthRecord
from aipd_os.product_truth.propagation import PropagationEngine, ReworkExhaustedError
from aipd_os.product_truth.store import ProductTruthStore


@pytest.fixture
def store(tmp_path):
    return ProductTruthStore(str(tmp_path / "product_truth.db"))


@pytest.fixture
def lineage(store):
    return LineageGraph(store)


def _mk(store, rtype, content, trust="unverified", expires_at=None, **kw):
    rec = TruthRecord(record_type=rtype, content=content, trust_level=trust,
                      expires_at=expires_at, source=kw.pop("source", None),
                      effective_at=kw.pop("effective_at", None))
    return store.add(rec)


# ----------------------------------------------------------- A. CRUD + 过期
def test_truth_crud_and_expiry(store):
    rid = _mk(store, "fact", "max load 50kg", trust="medium")
    rec = store.get(rid)
    assert rec.record_type == "fact"
    assert rec.content == "max load 50kg"
    assert rec.trust_level == "medium"
    assert rec.version == 1
    assert rec.status == "active"

    assert store.find_id_by_type_and_content("fact", "max load 50kg") == rid
    assert store.find_id_by_type_and_content("fact", "nope") is None

    store.update(rid, content="max load 60kg", trust_level="high")
    assert store.get(rid).content == "max load 60kg"
    assert store.get(rid).trust_level == "high"

    q = store.query(record_type="fact")
    assert [r.record_id for r in q] == [rid]

    store.delete(rid)
    with pytest.raises(KeyError):
        store.get(rid)


def test_expiry_detection(store):
    expired = _mk(store, "assumption", "old assumption",
                  expires_at="2000-01-01T00:00:00+00:00")
    valid = _mk(store, "assumption", "fresh assumption",
                expires_at="2099-01-01T00:00:00+00:00")
    never = _mk(store, "assumption", "no expiry")
    assert store.is_expired(expired) is True
    assert store.is_expired(valid) is False
    assert store.is_expired(never) is False
    assert {r.record_id for r in store.list_expired()} == {expired}


def test_expiry_detection_mixed_naive_aware_timestamps(store):
    """回归：naive 与 aware 时间戳混用不得抛 TypeError（按 UTC 归一化比较）。"""
    naive_past = _mk(store, "assumption", "naive old",
                     expires_at="2000-01-01T00:00:00")  # naive 视为 UTC
    aware_past = _mk(store, "assumption", "aware old",
                     expires_at="2000-01-01T00:00:00+00:00")
    assert store.is_expired(naive_past) is True
    assert store.is_expired(aware_past) is True
    naive_future = _mk(store, "assumption", "naive new",
                       expires_at="2099-01-01T00:00:00")
    assert store.is_expired(naive_future) is False


def test_trust_assessment_with_missing_evidence(store):
    # 无证据支撑 → low
    bare = _mk(store, "requirement", "speed > 100m/s")
    assert store.assess_trust(bare).trust_level == "low"
    assert store.assess_trust(bare).reasons  # 有缺证据原因

    # evidence 类型本身 → high（来源可信度，NOT verified——有内容 ≠ 命题为真）
    ev = _mk(store, "evidence", "bench result", trust="verified")
    assert store.assess_trust(ev).trust_level == "high"
    assert store.assess_trust(ev).trust_level != "verified"

    # 显式 Owner/工程确认标记 → verified（唯一自动 verified 路径）
    rec = TruthRecord(record_type="fact", content="confirmed claim",
                      trust_level="unverified",
                      metadata={"confirm_by_owner": True})
    cid = store.add(rec)
    assert store.assess_trust(cid).trust_level == "verified"

    # 有过期 → unverified
    store.update(bare, expires_at="2000-01-01T00:00:00+00:00")
    assert store.assess_trust(bare).trust_level == "unverified"


# ----------------------------------------------------------- B. 血缘与受影响
def test_lineage_downstream_and_affected(lineage, store):
    a = _mk(store, "fact", "fact A")
    b = _mk(store, "requirement", "req B")
    c = _mk(store, "ctq", "ctq C")
    lineage.add_edge(a, b)
    lineage.add_edge(b, c)
    assert lineage.downstream_of(a) == [b]
    assert lineage.upstream_of(c) == [b]
    # A 影响 B 和 C
    affected = lineage.compute_affected(a)
    assert set(affected) == {b, c}
    # 排序：最上游优先（B 在 C 前）
    assert affected == [b, c]


def test_diamond_affects_each_once(lineage, store):
    a = _mk(store, "fact", "root")
    x = _mk(store, "requirement", "x")
    y = _mk(store, "requirement", "y")
    z = _mk(store, "ctq", "z")
    lineage.add_edge(a, x)
    lineage.add_edge(a, y)
    lineage.add_edge(x, z)
    lineage.add_edge(y, z)
    affected = lineage.compute_affected(a)
    assert len(affected) == len(set(affected)) == 3
    assert set(affected) == {x, y, z}


def test_cycle_detection_blocks_infinite_recursion(lineage, store):
    a = _mk(store, "fact", "a")
    b = _mk(store, "fact", "b")
    lineage.add_edge(a, b)
    # 尝试制造环 b -> a：应拒绝并抛异常
    with pytest.raises(CycleDetectedError):
        lineage.add_edge(b, a)
    # 图保持无环，compute_affected 不无限递归
    affected = lineage.compute_affected(a)
    assert set(affected) == {b}
    assert lineage.has_cycle_from(a) is False


# ------------------------------------------------- C. 失效传播 + 有界返工
def test_upstream_change_marks_downstream_stale(store, lineage):
    eng = PropagationEngine(store, lineage)
    a = _mk(store, "fact", "fact A")
    b = _mk(store, "requirement", "req B")
    lineage.add_edge(a, b)
    res = eng.on_upstream_changed(a)
    assert set(res["affected"]) == {b}
    assert res["stale"] == [b]
    assert store.get(b).status == "stale"
    assert len(res["tasks"]) == 1
    assert res["explanation"]["what_changed"]
    assert "approval_needed" in res["explanation"]


def test_bounded_rework_stops_and_blocks(store, lineage):
    eng = PropagationEngine(store, lineage)
    a = _mk(store, "fact", "fact A")
    b = _mk(store, "requirement", "req B")
    lineage.add_edge(a, b)
    res = eng.on_upstream_changed(a, max_attempts=2)
    task_id = res["tasks"][0]["task_id"]

    # 返工函数始终失败
    def _failing(_rid):
        return False

    r1 = eng.run_rework(task_id, rework_fn=_failing)
    assert r1["status"] == "pending"          # 退避重试
    assert r1["backoff_seconds"] >= 1
    r2 = eng.run_rework(task_id, rework_fn=_failing)
    assert r2["status"] == "blocked"          # 达到上限 → blocked

    # 达到上限后再尝试 → 抛 ReworkExhaustedError，不无限重试
    with pytest.raises(ReworkExhaustedError):
        eng.run_rework(task_id, rework_fn=_failing)
    assert store.get(b).status == "blocked"
    assert eng.get_task(task_id).attempts == 2


def test_rework_success_bumps_version_and_closes_stale(store, lineage):
    eng = PropagationEngine(store, lineage)
    a = _mk(store, "fact", "fact A")
    b = _mk(store, "requirement", "req B")
    lineage.add_edge(a, b)
    res = eng.on_upstream_changed(a)
    task_id = res["tasks"][0]["task_id"]
    assert store.get(b).status == "stale"

    def _ok(_rid):
        return True

    r = eng.run_rework(task_id, rework_fn=_ok)
    assert r["reworked"] is True
    assert r["new_version"] == 2
    assert store.get(b).status == "active"    # 关闭 stale
    assert eng.get_task(task_id).status == "succeeded"


def test_owner_readable_change_explanation(store, lineage):
    eng = PropagationEngine(store, lineage)
    a = _mk(store, "fact", "elastic modulus changed")
    b = _mk(store, "artifact_version", "CAD v1")
    lineage.add_edge(a, b)
    res = eng.on_upstream_changed(a)
    exp = res["explanation"]
    assert "elastic modulus changed" in exp["what_changed"]
    assert b in exp["why_affected"]
    assert "bounded rework" in exp["fix_plan"]
    assert "approval" in exp["approval_needed"]
    # pending_approval 汇总也可读
    pending = eng.pending_approval()
    assert pending and pending[0]["explanation"]["what_changed"]
