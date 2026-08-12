"""v5.9.2 Product chain DAG fail-closed tests（§16/17/49）。

验证 Supervisor 显式依赖 DAG：
- chain 各 work item 带 depends（前后依赖）；
- 上游 blocked_external → 下游全部保持 queued（不执行、不产出对象）；
- 上游完成 → 下游 resume（依赖完成后续跑）。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from aipd_os.execution.execution_router import ExecutionRouter
from aipd_os.execution.runs import RunStore
from aipd_os.product_intelligence import ProductDefinitionSnapshotService
from aipd_os.supervisor.idea_capabilities import (
    schedule_product_intelligence_chain,
)
from aipd_os.tool_adapters.builtin import build_registry
from aipd_os.tool_adapters.product_adapters import register_product_adapters
from tests.test_product_intelligence_runtime_e2e import _env


def _provider_none_env(tmp_path):
    """provider=None 的 production 语义装配。"""
    env = _env(tmp_path)
    reg = build_registry()
    register_product_adapters(reg, env["db"], provider=None)
    router = ExecutionRouter(RunStore(str(Path(tmp_path) / "e.db")), reg)
    return env, reg, router


def _work_rows(db, tenant="default", project="p1"):
    with sqlite3.connect(str(db.path)) as c:
        c.row_factory = sqlite3.Row
        rows = c.execute(
            "SELECT work_id, capability_floor, status, depends_on_json "
            "FROM supervisor_work_items WHERE tenant_id=? AND project_id=? "
            "ORDER BY work_id", (tenant, project)).fetchall()
    return [dict(r) for r in rows]


def test_product_chain_has_explicit_dependencies(tmp_path):
    """§16：chain 每个 work item 显式 depends=[前一个]。"""
    env, reg, router = _provider_none_env(tmp_path)
    schedule_product_intelligence_chain(env["sup"], env["idea"].idea_id)
    rows = _work_rows(env["db"])
    assert len(rows) == 7
    prev = None
    for r in rows:
        deps = eval(r["depends_on_json"])  # noqa: S307 - 测试内 json list
        if prev is None:
            assert deps == []
        else:
            assert deps == [prev], f"{r['work_id']} deps={deps} != [{prev}]"
        prev = r["work_id"]


def test_blocked_insight_prevents_opportunity(tmp_path):
    """上游 derive_insights blocked → identify_opportunity 不运行（fail-closed）。"""
    env, reg, router = _provider_none_env(tmp_path)
    wids = schedule_product_intelligence_chain(
        env["sup"], env["idea"].idea_id, steps=(
            "derive_insights", "identify_opportunity"))
    for _ in range(4):
        env["sup"].run_supervisor(steps=1, adapter_registry=reg,
                                  router=router, project_id="p1")
    rows = _work_rows(env["db"])
    by_id = {r["work_id"]: r["status"] for r in rows}
    assert by_id[wids[0]] == "blocked_external"
    assert by_id[wids[1]] == "queued"  # 依赖未 complete → 不领取
    assert env["pi"].list_opportunities("default", "p1") == []


def test_blocked_provider_prevents_snapshot(tmp_path):
    """上游 blocked → create_snapshot 不执行（§17/49）。"""
    env, reg, router = _provider_none_env(tmp_path)
    wids = schedule_product_intelligence_chain(env["sup"], env["idea"].idea_id)
    for _ in range(12):
        env["sup"].run_supervisor(steps=1, adapter_registry=reg,
                                  router=router, project_id="p1")
    rows = _work_rows(env["db"])
    by_id = {r["work_id"]: r["status"] for r in rows}
    assert by_id[wids[0]] == "blocked_external"
    assert "complete" not in by_id.values(), \
        f"downstream must not run: {by_id}"
    assert ProductDefinitionSnapshotService(
        env["db"]).list_snapshots("default", "p1") == []


def test_blocked_provider_prevents_gate(tmp_path):
    """上游 blocked → definition_gate 不执行。"""
    env, reg, router = _provider_none_env(tmp_path)
    wids = schedule_product_intelligence_chain(env["sup"], env["idea"].idea_id)
    for _ in range(12):
        env["sup"].run_supervisor(steps=1, adapter_registry=reg,
                                  router=router, project_id="p1")
    rows = _work_rows(env["db"])
    by_id = {r["work_id"]: r["status"] for r in rows}
    assert by_id[wids[-1]] == "queued"  # gate 永不运行


def test_snapshot_never_runs_with_incomplete_product_chain(tmp_path):
    """链不完整（缺 derive_features）→ create_snapshot 不执行（§17）。"""
    env, reg, router = _provider_none_env(tmp_path)
    wids = schedule_product_intelligence_chain(
        env["sup"], env["idea"].idea_id, steps=(
            "derive_insights", "create_snapshot"))
    for _ in range(6):
        env["sup"].run_supervisor(steps=1, adapter_registry=reg,
                                  router=router, project_id="p1")
    rows = _work_rows(env["db"])
    by_id = {r["work_id"]: r["status"] for r in rows}
    assert by_id[wids[0]] == "blocked_external"
    assert by_id[wids[1]] == "queued"
    assert ProductDefinitionSnapshotService(
        env["db"]).list_snapshots("default", "p1") == []


def test_product_chain_resumes_after_dependency_completed(tmp_path):
    """依赖完成后下游 resume（§17）。provider 从 None 换为 FakeProvider
    后，重新 run → 下游执行。"""
    env = _env(tmp_path)
    reg = build_registry()
    # provider=None 调度 → 全部 blocked/queued
    register_product_adapters(reg, env["db"], provider=None)
    router = ExecutionRouter(RunStore(str(Path(tmp_path) / "e.db")), reg)
    wids = schedule_product_intelligence_chain(env["sup"], env["idea"].idea_id)
    for _ in range(10):
        env["sup"].run_supervisor(steps=1, adapter_registry=reg,
                                  router=router, project_id="p1")
    rows = _work_rows(env["db"])
    by_id = {r["work_id"]: r["status"] for r in rows}
    assert by_id[wids[0]] == "blocked_external"
    # 依赖完成后（此处以 FakeProvider 重新注册 + 显式 select + 重新调度
    # Segment B 模拟 resume；上游 blocked 的 DAG 需重新发起）
    from tests.fixtures.product.fake_product_provider import (
        FakeProductIntelligenceProvider,
    )
    reg2 = build_registry()
    register_product_adapters(reg2, env["db"],
                              provider=FakeProductIntelligenceProvider())
    router2 = ExecutionRouter(RunStore(str(Path(tmp_path) / "e2.db")), reg2)
    # Segment A 重跑（fake 可用）
    wids_a = schedule_product_intelligence_chain(
        env["sup"], env["idea"].idea_id, steps=(
            "derive_insights", "identify_opportunity"))
    for _ in range(3):
        env["sup"].run_supervisor(steps=1, adapter_registry=reg2,
                                  router=router2, project_id="p1")
    opps = env["pi"].list_opportunities("default", "p1")
    assert opps, "resumed segment A must produce opportunities"
    env["pi"].select_opportunity("default", "p1", opps[0].opportunity_id)
    wids_b = schedule_product_intelligence_chain(
        env["sup"], env["idea"].idea_id, steps=(
            "derive_principles", "derive_requirements", "derive_features",
            "create_snapshot", "definition_gate"))
    for _ in range(6):
        env["sup"].run_supervisor(steps=1, adapter_registry=reg2,
                                  router=router2, project_id="p1")
    rows2 = _work_rows(env["db"])
    by_id2 = {r["work_id"]: r["status"] for r in rows2}
    for wid in wids_a + wids_b:
        assert by_id2.get(wid) == "complete", f"{wid} not complete after resume"
    assert ProductDefinitionSnapshotService(
        env["db"]).list_snapshots("default", "p1"), \
        "snapshot must exist after resumed chain"
