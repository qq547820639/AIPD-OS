"""ProductTruth LineageGraph ↔ Generic Lineage 兼容测试（v5.8.2 Commit 7）。

提示词 §16-17：State.LineageService 是 canonical cross-domain lineage engine；
ProductTruth.LineageGraph 逐步变成 compatibility facade（Phase 1：
dual-read / canonical-write），不建第三套 lineage。

验证：
- LineageGraph.add_edge（有 canonical_db）→ truth_lineage（兼容读）+ 
  dependencies（canonical 写，node_type=product_truth）双写；
- 旧 API（downstream_of/upstream_of/compute_affected/edges）行为不变；
- remove_edge → truth_lineage 删除 + canonical soft-retire（历史保留）；
- 无 canonical_db → 纯 truth_lineage（v5.7 行为）；
- 跨域统一图：product_truth 边与 claim/evidence 边在同一 LineageService 图。
"""
from __future__ import annotations

import pytest

from aipd_os.product_truth.lineage import CycleDetectedError, LineageGraph
from aipd_os.product_truth.store import ProductTruthStore
from aipd_os.state.db import AIPDStateDB
from aipd_os.state.lineage import LineageNodeRef, LineageService


@pytest.fixture
def store_and_db(tmp_path):
    path = str(tmp_path / "state.db")
    db = AIPDStateDB(path)  # canonical（dependencies 表，migration v1..v8）
    store = ProductTruthStore(path)  # 同一文件（truth_lineage 表）
    return store, db


def test_add_edge_dual_writes(store_and_db):
    """canonical-write：truth_lineage + dependencies 双写。"""
    store, db = store_and_db
    g = LineageGraph(store, canonical_db=db)
    g.add_edge("T-001", "T-002", relation="affects")

    # 兼容读：truth_lineage
    assert g.downstream_of("T-001") == ["T-002"]
    assert g.upstream_of("T-002") == ["T-001"]
    # canonical 写：dependencies（node_type=product_truth）
    edges = g.canonical_edges()
    assert len(edges) == 1
    e = edges[0]
    assert e["source"]["node_type"] == "product_truth"
    assert e["source"]["node_id"] == "T-001"
    assert e["target"]["node_id"] == "T-002"
    assert e["relation_type"] == "affects"
    assert e["provenance"]["source"] == "product_truth.lineage_graph"


def test_old_api_unchanged_without_canonical_db(tmp_path):
    """无 canonical_db：纯 truth_lineage（v5.7 行为）。"""
    store = ProductTruthStore(str(tmp_path / "pt.db"))
    g = LineageGraph(store)
    g.add_edge("T-001", "T-002", relation="affects")
    assert g.downstream_of("T-001") == ["T-002"]
    with pytest.raises(RuntimeError):
        g.canonical_edges()  # 无 canonical_db → 明确报错（不静默）


def test_remove_edge_retires_canonical(store_and_db):
    """remove_edge：truth_lineage 删除 + canonical soft-retire（历史保留）。"""
    store, db = store_and_db
    g = LineageGraph(store, canonical_db=db)
    g.add_edge("T-001", "T-002", relation="affects")
    g.remove_edge("T-001", "T-002")

    # truth_lineage 已删除
    assert g.downstream_of("T-001") == []
    # canonical 侧：active 边不可见，retired 边保留（include_retired）
    lineage = LineageService(db)
    edges = lineage.outgoing(
        LineageNodeRef("product_truth", "T-001", "default", "default"),
        include_retired=True)
    assert len(edges) == 1 and edges[0].retired
    # canonical 查询（默认 active）不可见
    assert g.canonical_edges() == []


def test_cycle_detection_keeps_both_stores_consistent(store_and_db):
    """canonical 环检测失败时两个 store 都不残留坏边。"""
    store, db = store_and_db
    g = LineageGraph(store, canonical_db=db)
    g.add_edge("T-001", "T-002")
    g.add_edge("T-002", "T-003")
    with pytest.raises(CycleDetectedError):
        g.add_edge("T-003", "T-001")  # 成环 → 拒绝
    assert g.downstream_of("T-003") == []  # truth_lineage 无残留
    assert g.canonical_edges()  # canonical 侧也无 T-003->T-001


def test_cross_domain_shared_graph(store_and_db):
    """product_truth 边与 claim/evidence 边在同一个 canonical 图。"""
    store, db = store_and_db
    g = LineageGraph(store, canonical_db=db)
    g.add_edge("T-001", "T-002", relation="satisfies")

    # claim → evidence 边（canonical LineageService）
    lineage = LineageService(db)
    lineage.add_edge(
        LineageNodeRef("claim", "CLM-001", "default", "default"),
        LineageNodeRef("evidence", "E-001", "default", "default"),
        "supported_by", provenance={"source": "test"})

    # 全图同一份（无第三套 lineage）
    all_edges = g.canonical_all_edges()
    types = {(e["source"]["node_type"], e["relation_type"])
             for e in all_edges}
    assert ("product_truth", "satisfies") in types
    assert ("claim", "supported_by") in types


def test_scope_enforced_on_canonical_write(store_and_db):
    """canonical 写同样 tenant/project scoped。"""
    store, db = store_and_db
    g = LineageGraph(store, canonical_db=db, tenant_id="t1", project_id="p1")
    g.add_edge("T-001", "T-002")
    # t1/p1 可见（实例 scope）
    edges = g.canonical_edges()
    assert len(edges) == 1
    # default/default 不可见（无跨 scope 泄漏）
    assert g.canonical_edges(tenant_id="default", project_id="default") == []


def test_propagation_still_works_through_facade(store_and_db):
    """compute_affected 经 facade 保持可用（propagation 兼容）。"""
    store, db = store_and_db
    g = LineageGraph(store, canonical_db=db)
    g.add_edge("T-001", "T-002")
    g.add_edge("T-002", "T-003")
    assert g.compute_affected("T-001") == ["T-002", "T-003"]
    assert g.edges()  # 旧 edges API 仍可用
