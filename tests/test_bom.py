"""BOM 域测试：模型校验 / 存储（乐观锁·防循环·审计）/ 成本核算诚实性 /
发布检查清单。"""
from __future__ import annotations

import pytest

from aipd_os.bom import (
    BomLine,
    BomStore,
    CostInputs,
    OptimisticLockError,
    compute_bom_cost,
    release_checklist,
    rollup,
)

TENANT = "default"
PID = "p1"


@pytest.fixture
def store(tmp_path) -> BomStore:
    return BomStore(str(tmp_path / "bom.db"))


# ------------------------------------------------------------- 模型校验
def test_model_validation():
    with pytest.raises(ValueError):
        BomLine(line_id="L1", bom_id="B1", item="", tenant_id=TENANT,
                project_id=PID)
    with pytest.raises(ValueError):
        BomLine(line_id="L1", bom_id="B1", item="a", quantity=0,
                tenant_id=TENANT, project_id=PID)
    with pytest.raises(ValueError):
        BomLine(line_id="L1", bom_id="B1", item="a", unit_cost=-1,
                tenant_id=TENANT, project_id=PID)
    with pytest.raises(ValueError):
        BomLine(line_id="L1", bom_id="B1", item="a", parent_item="a",
                tenant_id=TENANT, project_id=PID)
    with pytest.raises(ValueError):
        CostInputs(target_quantity=0)
    with pytest.raises(ValueError):
        CostInputs(margin_pct=-5)


# ------------------------------------------------------------- 存储 CRUD
def test_store_crud_optimistic_lock_and_audit(store):
    header = store.create_bom(TENANT, PID, "主 BOM")
    assert header.bom_id.startswith("BOM-")
    line = store.add_line(BomLine(
        line_id="", bom_id=header.bom_id, tenant_id=TENANT, project_id=PID,
        item="外壳", quantity=2, unit="pcs", supplier="Acme", unit_cost=12.5))
    assert line.line_id.startswith("LINE-")
    assert store.get_line(TENANT, PID, line.line_id) is not None

    updated = store.update_line(TENANT, PID, line.line_id, expected_version=1,
                                unit_cost=13.0, reason="报价更新")
    assert updated.unit_cost == 13.0 and updated.version_no == 2
    # 乐观锁：旧版本号冲突被拒
    with pytest.raises(OptimisticLockError):
        store.update_line(TENANT, PID, line.line_id, expected_version=1, unit_cost=9)
    # 审计可见
    changes = store.list_changes(TENANT, PID)
    assert any(ch["action"] == "update" and ch["object_id"] == line.line_id
               for ch in changes)
    store.remove_line(TENANT, PID, line.line_id)
    assert store.get_line(TENANT, PID, line.line_id) is None


def test_store_parent_cycle_prevented(store):
    header = store.create_bom(TENANT, PID, "主 BOM")
    a = store.add_line(BomLine(
        line_id="", bom_id=header.bom_id, tenant_id=TENANT, project_id=PID,
        item="A"))
    store.add_line(BomLine(
        line_id="", bom_id=header.bom_id, tenant_id=TENANT, project_id=PID,
        item="B", parent_item="A"))
    # 把 A 的父项改为 B → 环，必须拒绝
    with pytest.raises(ValueError, match="cycle"):
        store.update_line(TENANT, PID, a.line_id, expected_version=1,
                          parent_item="B")


# ------------------------------------------------------------- 成本核算
def test_cost_calculator_totals_and_honesty(store):
    header = store.create_bom(TENANT, PID, "主 BOM")
    for item, qty, cost, supplier in [
        ("外壳", 1, 10.0, "Acme"), ("电机", 2, 30.0, "MotorCo"),
        ("螺丝", 10, 0.1, None),  # 缺供应商 → 成本不完整
    ]:
        store.add_line(BomLine(
            line_id="", bom_id=header.bom_id, tenant_id=TENANT, project_id=PID,
            item=item, quantity=qty, supplier=supplier, unit_cost=cost))
    lines = store.list_lines(TENANT, PID, bom_id=header.bom_id)
    inputs = CostInputs(tooling_fee=50000, target_quantity=1000,
                        nre=20000, margin_pct=20)
    cost = compute_bom_cost(lines, inputs)
    # 材料小计 = 10 + 60 = 70（缺供应商行不按 0 元假装）
    assert cost.material_subtotal == 70.0
    assert cost.tooling_per_unit == 50.0
    assert cost.nre_per_unit == 20.0
    assert cost.unit_cost == 140.0
    assert cost.unit_price == 168.0  # +20% 毛利
    assert cost.total_cost == 140000.0
    assert cost.cost_complete is False
    assert any("螺丝" in m for m in cost.missing_cost_lines)


def test_cost_complete_when_all_quoted(store):
    header = store.create_bom(TENANT, PID, "主 BOM")
    store.add_line(BomLine(
        line_id="", bom_id=header.bom_id, tenant_id=TENANT, project_id=PID,
        item="外壳", supplier="Acme", unit_cost=10.0))
    lines = store.list_lines(TENANT, PID, bom_id=header.bom_id)
    cost = compute_bom_cost(lines, CostInputs())
    assert cost.cost_complete is True
    assert cost.missing_cost_lines == []


# ------------------------------------------------------------- 投影与发布检查
def test_rollup_and_release_checklist(store):
    header = store.create_bom(TENANT, PID, "主 BOM")
    store.add_line(BomLine(
        line_id="", bom_id=header.bom_id, tenant_id=TENANT, project_id=PID,
        item="外壳", supplier="Acme", unit_cost=10.0))
    store.add_line(BomLine(
        line_id="", bom_id=header.bom_id, tenant_id=TENANT, project_id=PID,
        item="子件", parent_item="外壳", supplier="Sub", unit_cost=2.0))
    r = rollup(store, TENANT, PID, bom_id=header.bom_id)
    assert r["line_count"] == 2
    assert r["root_items"] == ["外壳"]
    assert r["cost_complete"] is True
    assert r["orphan_parents"] == []

    checklist = release_checklist(store, TENANT, PID, bom_id=header.bom_id,
                                  cost_inputs=CostInputs())
    # 未 release → 不 ready
    assert checklist["checks"]["bom_released"] is False
    assert checklist["release_ready"] is False

    store.set_bom_status(TENANT, PID, header.bom_id, "released")
    checklist = release_checklist(store, TENANT, PID, bom_id=header.bom_id,
                                  cost_inputs=CostInputs())
    assert checklist["release_ready"] is True
    assert checklist["cost"]["cost_complete"] is True


def test_release_checklist_flags_orphans_and_missing_cost(store):
    header = store.create_bom(TENANT, PID, "主 BOM")
    store.add_line(BomLine(
        line_id="", bom_id=header.bom_id, tenant_id=TENANT, project_id=PID,
        item="外壳", supplier="Acme", unit_cost=10.0))
    store.add_line(BomLine(
        line_id="", bom_id=header.bom_id, tenant_id=TENANT, project_id=PID,
        item="子件", parent_item="不存在的父件"))
    store.set_bom_status(TENANT, PID, header.bom_id, "released")
    checklist = release_checklist(store, TENANT, PID, bom_id=header.bom_id,
                                  cost_inputs=CostInputs())
    assert checklist["checks"]["no_orphan_parents"] is False
    assert checklist["checks"]["cost_complete"] is False
    assert checklist["release_ready"] is False
