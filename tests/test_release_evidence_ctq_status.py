"""CTQ 状态与发布证据分母（F-CTQ-STALE 第 44 片）。

原缺陷（实测）：`_collect_ctq` 用 `status="active"` 取分母，非 active 的记录**整条静默消失**——
两条 CTQ 标一条 stale，`doc["ctq"]` 只剩一条，issues 里一个字都没提它。
于是"把要求标成陈旧"会让 `gdt_covers_ctq` 的覆盖义务变小，本来放不了的行反而能过。

这里钉的是改判后的三件事：① 陈旧/过期/被阻断的 CTQ 必须点名且 blocking；
② 被新版本取代（superseded）可以不计入分母，但要点名且不阻断；
③ 干净库上这条新判据**不许开火**（反向对照，否则它只是一个永远抱怨的判据）。
"""
from __future__ import annotations

import json

import pytest

from aipd_os.product_truth import ProductTruthStore, TruthRecord
from aipd_os.release_manifest import _collect_ctq, build_release_manifest
from aipd_os.state.db import AIPDStateDB

T = "default"
P = "CTQ-STATUS"


def _store(db):
    return ProductTruthStore(str(db), tenant_id=T, project_id=P)


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "state.db"
    state = AIPDStateDB(path)
    state.ensure_default_tenant()
    state.init_project(T, P, "ctq status 测试", "evidence")
    return path


def _ctq(store, feature, **meta):
    base = {"feature": feature, "nominal": 6.0, "lower_limit": 5.95,
            "upper_limit": 6.05, "inspection_method": "CMM"}
    base.update(meta)
    return store.add(TruthRecord(record_type="ctq", content=f"CTQ {feature}",
                                 trust_level="verified", metadata=base),
                     tenant_id=T, project_id=P)


def _kinds(doc_or_issues):
    issues = doc_or_issues["issues"] if isinstance(doc_or_issues, dict) else doc_or_issues
    return [str(i.get("kind")) for i in issues]


def _issue(issues, kind):
    return [i for i in issues if str(i.get("kind")) == kind]


def test_stale_ctq_is_named_and_blocks(tmp_path, db):
    store = _store(db)
    active = _ctq(store, "hole_1")
    stale = _ctq(store, "hole_2")
    store.set_status(stale, "stale")

    doc = build_release_manifest(db_path=db, tenant_id=T, project_id=P,
                                 out_path=tmp_path / "e.json")
    assert [c["record_id"] for c in doc["ctq"]] == [active]
    hits = _issue(doc["issues"], "ctq_not_active")
    assert hits, f"stale 的 CTQ 没有被点名：{_kinds(doc)}"
    assert stale in str(hits[0]), "要点名到具体记录号，不能只说「有条目陈旧」"
    assert hits[0].get("blocking") is True
    assert doc["ok"] is False


def test_superseded_is_named_but_does_not_block(db):
    store = _store(db)
    _ctq(store, "hole_1")
    gone = _ctq(store, "hole_2")
    store.set_status(gone, "superseded")

    issues: list = []
    by_id = _collect_ctq(store, issues)
    assert list(by_id) == [k for k in by_id if k != gone]
    hits = _issue(issues, "ctq_superseded_not_required")
    assert hits and gone in str(hits[0])
    assert hits[0].get("blocking") is False
    assert not _issue(issues, "ctq_not_active"), "被取代的要求不该被当成没收口"


def test_every_non_active_status_is_accounted_for(db):
    """三种"没收口"的状态各自都要出现在点名里——一个都不许悄悄掉。"""
    store = _store(db)
    ids = {"stale": _ctq(store, "hole_1"),
           "expired": _ctq(store, "hole_2"),
           "blocked": _ctq(store, "hole_3")}
    for status, rid in ids.items():
        store.set_status(rid, status)

    issues: list = []
    assert _collect_ctq(store, issues) == {}
    hits = _issue(issues, "ctq_not_active")
    assert len(hits) == 3, f"每个状态各出一条点名，实际 {len(hits)} 条"
    text = " ".join(str(h) for h in hits)
    for status, rid in ids.items():
        assert rid in text and status in text
    assert all(h.get("blocking") is True for h in hits)
    assert "no_ctq" in _kinds(issues), "一条活的都没有时原来的兜底要还在"


def test_clean_database_does_not_fire_the_new_criterion(db):
    """反向对照：全是 active 时这条判据必须闭嘴，否则它只是永远抱怨。"""
    store = _store(db)
    a = _ctq(store, "hole_1")
    b = _ctq(store, "hole_2")
    issues: list = []
    by_id = _collect_ctq(store, issues)
    assert {a, b} == set(by_id)
    assert _kinds(issues) == [], issues
    assert not _issue(issues, "ctq_not_active")


def test_denominator_shrink_is_now_visible(tmp_path, db):
    """这条是"为什么算缺陷"的证据：分母少一条，同时必须看得见少的是哪条。"""
    store = _store(db)
    _ctq(store, "hole_1")
    second = _ctq(store, "hole_2")

    before: list = []
    assert len(_collect_ctq(store, before)) == 2 and before == []

    store.set_status(second, "stale")
    after: list = []
    assert len(_collect_ctq(store, after)) == 1, "覆盖分母仍只含 active"
    assert _issue(after, "ctq_not_active"), "但缩掉的那一条必须被点名"


def test_evidence_json_still_serialisable(tmp_path, db):
    """新增的 issue 不能把证据文档打成不可序列化（下游要落盘）。"""
    store = _store(db)
    rid = _ctq(store, "hole_1")
    store.set_status(rid, "stale")
    doc = build_release_manifest(db_path=db, tenant_id=T, project_id=P,
                                 out_path=tmp_path / "e.json")
    text = json.dumps(doc, ensure_ascii=False)
    assert "ctq_not_active" in text
