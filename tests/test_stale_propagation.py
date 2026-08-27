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
