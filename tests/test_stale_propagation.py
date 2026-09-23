"""P2-M6: Stale Propagation tests。

验证 BOM/Requirement/CAD change → downstream stale → Readiness HOLD。
"""
from __future__ import annotations

import pytest

from aipd_os.state.db import AIPDStateDB
from aipd_os.state.stale_propagation import (
    BOM_MATERIAL_FIELDS,
    REQUIREMENT_MATERIAL_FIELDS,
    StalePropagationService,
)


@pytest.fixture
def db(tmp_path):
    db = AIPDStateDB(str(tmp_path / "test.db"))
    db.ensure_default_tenant("default")
    return db


class TestMaterialFieldDetection:
    """material field 变化检测。"""

    def test_no_change(self, db):
        svc = StalePropagationService(db)
        result = svc._material_changed(
            BOM_MATERIAL_FIELDS,
            {"quantity": 10, "description": "old"},
            {"quantity": 10, "description": "new"},
        )
        assert len(result) == 0

    def test_material_change(self, db):
        svc = StalePropagationService(db)
        result = svc._material_changed(
            BOM_MATERIAL_FIELDS,
            {"quantity": 10, "description": "old"},
            {"quantity": 20, "description": "new"},
        )
        assert "quantity" in result
        assert "description" not in result

    def test_requirement_material_change(self, db):
        svc = StalePropagationService(db)
        result = svc._material_changed(
            REQUIREMENT_MATERIAL_FIELDS,
            {"title": "old", "priority": "high"},
            {"title": "new", "priority": "high"},
        )
        assert "title" in result
        assert "priority" not in result


class TestBOMPropagation:
    """BOM change → Cost stale。"""

    def test_bom_material_change_propagates(self, db):
        svc = StalePropagationService(db)
        result = svc.propagate_bom_change(
            "default", "P-1", "bom-1",
            {"quantity": 10},
            {"quantity": 20},
        )
        assert result["propagated"] is True
        assert "quantity" in result["material_fields"]

    def test_bom_non_material_no_propagation(self, db):
        svc = StalePropagationService(db)
        result = svc.propagate_bom_change(
            "default", "P-1", "bom-1",
            {"description": "old"},
            {"description": "new"},
        )
        assert result["propagated"] is False


class TestRequirementPropagation:
    """Requirement change → Validation stale。"""

    def test_requirement_material_change_propagates(self, db):
        svc = StalePropagationService(db)
        result = svc.propagate_requirement_change(
            "default", "P-1", "req-1",
            {"title": "old"},
            {"title": "new"},
        )
        assert result["propagated"] is True
        assert "title" in result["material_fields"]


class TestIssuePropagation:
    """Issue opened → Readiness HOLD。"""

    def test_issue_opened_propagates(self, db):
        svc = StalePropagationService(db)
        result = svc.propagate_issue_opened("default", "P-1", "ISS-1")
        assert result["propagated"] is True
        assert result["readiness_impact"] == "HOLD"


class TestStaleIsNotFail:
    """stale = historically valid but no longer current (not FAIL)。"""

    def test_stale_preserves_original_result(self, db):
        """stale result 保留原始 PASS，不变成 FAIL。"""
        from aipd_os.validation.models import RESULT_PASS
        from aipd_os.validation.service import ValidationService
        v_svc = ValidationService(db)
        plan = v_svc.create_plan("default", "P-1", "EVT", "Test Plan")
        test = v_svc.create_test("default", "P-1", plan.plan_id, "Test", "EVT",
                                  required=True)
        run = v_svc.create_run("default", "P-1", test.test_id)
        v_svc.record_result("default", "P-1", run.run_id, test.test_id, RESULT_PASS)
        # Mark stale
        v_svc.mark_stale_by_artifact_change(
            "default", "P-1", "old-artifact-v1", "new-artifact-v2")
        # Result should still be PASS but stale=True
        results = v_svc.list_results("default", "P-1")
        assert len(results) == 1
        assert results[0].result_status == RESULT_PASS  # NOT changed to FAIL


class TestPropagationWithRealDependencies:
    """依赖非空时，传播必须真的落到 canonical 表。

    此前的用例一律跑在「零依赖」图上，affected 恒为空，因此
    ``_mark_downstream_stale`` 的写库分支从未被执行过——cost_snapshot 分支
    就往 ``changes`` 表写了它没有的列（entity_type/entity_id/change_type/
    change_data），一有真实依赖即 OperationalError。
    """

    def test_bom_change_writes_cost_snapshot_stale_to_changes(self, db):
        db.init_project("default", "P-9", "p9", "goal")
        db.add_dependency("default", "P-9", "bom", "BOM-1",
                          "cost_snapshot", "COST-1")
        db.add_dependency("default", "P-9", "bom", "BOM-1",
                          "cost_snapshot", "COST-2")
        svc = StalePropagationService(db)

        result = svc.propagate_bom_change(
            "default", "P-9", "BOM-1", {"quantity": 1}, {"quantity": 2})

        assert result["propagated"] is True
        assert {a["target_id"] for a in result["affected"]} == {"COST-1", "COST-2"}
        with db.connect() as c:
            rows = c.execute(
                "SELECT object_type, object_id, action, reason FROM changes "
                "WHERE tenant_id=? AND project_id=? AND object_type='cost_snapshot'",
                ("default", "P-9")).fetchall()
        assert {r["object_id"] for r in rows} == {"COST-1", "COST-2"}
        assert all(r["action"] == "stale" for r in rows)
        assert all("quantity" in (r["reason"] or "") for r in rows)

    def test_cad_change_marks_linked_validation_result_stale(self, db):
        from aipd_os.validation.models import RESULT_PASS
        from aipd_os.validation.service import ValidationService

        db.init_project("default", "P-9", "p9", "goal")
        v_svc = ValidationService(db)
        plan = v_svc.create_plan("default", "P-9", "EVT", "Plan")
        test = v_svc.create_test("default", "P-9", plan.plan_id, "T", "EVT",
                                 required=True)
        run = v_svc.create_run("default", "P-9", test.test_id)
        v_svc.record_result("default", "P-9", run.run_id, test.test_id, RESULT_PASS)
        result_id = v_svc.list_results("default", "P-9")[0].result_id
        db.add_dependency("default", "P-9", "cad_artifact", "CAD-1",
                          "validation_result", result_id)

        svc = StalePropagationService(db)
        out = svc.propagate_cad_change(
            "default", "P-9", "CAD-1", {"revision": "A"}, {"revision": "B"})

        assert {a["target_id"] for a in out["affected"]} == {result_id}
        stale = [r for r in v_svc.list_results("default", "P-9")
                 if r.result_id == result_id][0]
        assert bool(stale.stale) is True
        assert "CAD material change" in (stale.stale_reason or "")
        # stale ≠ FAIL：原结论必须保留
        assert stale.result_status == RESULT_PASS

    def test_propagation_is_skipped_when_no_dependency(self, db):
        """零依赖仍是合法路径：propagated 为真但 affected 为空，且不报错。"""
        db.init_project("default", "P-9", "p9", "goal")
        svc = StalePropagationService(db)
        out = svc.propagate_bom_change(
            "default", "P-9", "BOM-X", {"quantity": 1}, {"quantity": 9})
        assert out["propagated"] is True
        assert out["affected"] == []

