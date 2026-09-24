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


# ------------------------------------------------- 工艺列（F-DRAW-01 第 16 片）
# 「材料与工艺」里的另一半。C6 交付物清单要它（references/production-cad-deliverables.md:3），
# BOM 契约把它写在**每一行**上（references/deliverable-contracts.md:9）。
# 注意它**不是**工序路线：Dynamics 365 Business Central 的 BOM 行只带 Routing Link Code、
# 工序在另一张 Routing 里；ERPNext v15 用 BOM 的子表 BOM Operation 存工位/工时/成本。
# 本仓只建「图纸明细表那一格要的那道主工艺」，多工序、工序成本与工时明确不建模。
def _all_text_fields(**over):
    """一行填得满的 BOM 行：用来核「每个字段真的落库也真的读回来」。"""
    base = dict(item="支架", parent_item=None, description="左支架", quantity=4.0,
                unit="pcs", material="6061-T6", supplier="ACME-IND", unit_cost=12.5,
                currency="CNY", source_deliverable="D-1", quote_ref="Q-9",
                status="planned")
    base.update(over)
    return base


def test_process_round_trips_and_is_in_the_dict(store):
    header = store.create_bom(TENANT, PID, "主 BOM")
    line = store.add_line(BomLine(line_id="", bom_id=header.bom_id, tenant_id=TENANT,
                                  project_id=PID, **_all_text_fields(
                                      process="CNC 铣削 + 阳极氧化")))
    assert line.process == "CNC 铣削 + 阳极氧化"
    assert store.get_line(TENANT, PID, line.line_id).process == "CNC 铣削 + 阳极氧化"
    assert line.to_dict()["process"] == "CNC 铣削 + 阳极氧化"


def test_process_is_optional_and_stays_none_when_not_filled(store):
    """没填工艺就是没填：读回来是 None，不是空串——明细表要拿它判「这一行还缺」。"""
    header = store.create_bom(TENANT, PID, "主 BOM")
    line = store.add_line(BomLine(line_id="", bom_id=header.bom_id, tenant_id=TENANT,
                                  project_id=PID, item="螺丝", quantity=12))
    again = store.get_line(TENANT, PID, line.line_id)
    assert again.process is None, f"缺工艺被折成 {again.process!r}"


def test_a_fully_populated_line_round_trips_every_field(store):
    """每个字段都得真写进去再真读回来——漏在 INSERT 列表里的字段只有这条能抓。

    第 16 片的真实风险不是「没加工艺」，而是「模型加了字段、建表语句加了、
    INSERT 的列名/占位符没跟着加」——那种错只有逐字段比对才看得见。
    """
    import dataclasses

    header = store.create_bom(TENANT, PID, "主 BOM")
    made = store.add_line(BomLine(line_id="", bom_id=header.bom_id, tenant_id=TENANT,
                                  project_id=PID, **_all_text_fields(process="喷砂")))
    back = store.get_line(TENANT, PID, made.line_id)
    mine = {f.name: getattr(made, f.name) for f in dataclasses.fields(BomLine)}
    theirs = {f.name: getattr(back, f.name) for f in dataclasses.fields(BomLine)}
    assert mine == theirs, {k: (mine[k], theirs[k]) for k in mine if mine[k] != theirs[k]}


def test_bom_line_fields_and_table_columns_agree(store):
    """模型字段集合 == 表列集合：两边各自漂的时候（加了列没加字段/反过）当场红。"""
    import dataclasses
    import sqlite3

    con = sqlite3.connect(str(store.path))
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(bom_lines)")}
    finally:
        con.close()
    fields = {f.name for f in dataclasses.fields(BomLine)}
    assert fields == cols, ("只在模型里: " + str(sorted(fields - cols))
                            + " / 只在表里: " + str(sorted(cols - fields)))


def test_update_line_can_edit_process(store):
    header = store.create_bom(TENANT, PID, "主 BOM")
    line = store.add_line(BomLine(line_id="", bom_id=header.bom_id, tenant_id=TENANT,
                                  project_id=PID, item="支架", process="激光切割"))
    upd = store.update_line(TENANT, PID, line.line_id, line.version_no,
                            reason="改工艺", process="CNC 铣削")
    assert upd.process == "CNC 铣削"
    assert store.get_line(TENANT, PID, line.line_id).process == "CNC 铣削"


def test_old_bom_library_gets_the_process_column_and_keeps_its_rows(tmp_path):
    """旧 bom.db（没有 process 列）打开就补齐，旧行读出来工艺是 None 而不是崩。

    CREATE TABLE IF NOT EXISTS 不会给已存在的表加列——沿用 ProductTruthStore
    的 _ensure_columns 先例（bom.db 归 BomStore 自有，不动迁移冻结的状态库）。
    """
    import sqlite3

    path = tmp_path / "old-bom.db"
    con = sqlite3.connect(str(path))
    con.executescript("""
    CREATE TABLE bom_lines(
      line_id TEXT NOT NULL, bom_id TEXT NOT NULL,
      tenant_id TEXT NOT NULL DEFAULT 'default',
      project_id TEXT NOT NULL DEFAULT 'default',
      item TEXT NOT NULL, parent_item TEXT, description TEXT NOT NULL DEFAULT '',
      quantity REAL NOT NULL DEFAULT 1.0, unit TEXT NOT NULL DEFAULT 'pcs',
      material TEXT, supplier TEXT, unit_cost REAL, currency TEXT NOT NULL DEFAULT 'CNY',
      source_deliverable TEXT, quote_ref TEXT, status TEXT NOT NULL DEFAULT 'planned',
      version_no INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL, PRIMARY KEY (line_id, tenant_id, project_id));
    """)
    con.execute("INSERT INTO bom_lines(line_id,bom_id,tenant_id,project_id,item,"
                "quantity,created_at,"
                "updated_at) VALUES('L-1','BOM-1',?,?, '老支架',3.0,"
                "'2024-01-01T00:00:00+00:00','2024-01-01T00:00:00+00:00')",
                (TENANT, PID))
    con.commit()
    con.close()

    s = BomStore(path)                      # 实例化即补列
    cols = {r[1] for r in sqlite3.connect(str(path)).execute(
        "PRAGMA table_info(bom_lines)").fetchall()}
    assert "process" in cols, sorted(cols)
    old = s.list_lines(TENANT, PID)[0]
    assert old.item == "老支架" and old.quantity == 3.0, old
    assert old.process is None, "旧行没填工艺 ⇒ None，不是空串（空串会被当成有值）"


def test_bom_add_cli_records_process(tmp_path, capsys):
    """产品路径上真能填：命令行不给 --process，字段就只是测试夹具里的东西。"""
    import json

    from aipd_os.cli.main import main
    from aipd_os.state.db import AIPDStateDB

    db = tmp_path / "state.db"
    state = AIPDStateDB(str(db))
    state.ensure_default_tenant()
    state.init_project(TENANT, PID, "工艺验证", "bom add 能不能填工艺")
    rc = main(["bom", "add", "--db", str(db), "--project", PID, "--part", "支架",
               "--material", "6061-T6", "--process", "CNC 铣削", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0, out
    assert out["line"]["process"] == "CNC 铣削", out["line"]
    from aipd_os.bom.store import bom_store_path

    got = BomStore(bom_store_path(db)).list_lines(TENANT, PID)
    assert [(one.material, one.process) for one in got] == [("6061-T6", "CNC 铣削")]
