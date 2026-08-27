"""P2-M7: Readiness Snapshot persistence tests。

验证 readiness evaluation 自动持久化快照到 readiness_snapshots 表。
"""
from __future__ import annotations

import pytest

from aipd_os.state.db import AIPDStateDB
from aipd_os.validation.issues import IssueService
from aipd_os.validation.models import RESULT_PASS
from aipd_os.validation.readiness import ReadinessService
from aipd_os.validation.readiness_snapshot_repo import (
    READINESS_RULESET_VERSION,
    ReadinessSnapshotRepository,
    compute_input_fingerprint,
)
from aipd_os.validation.service import ValidationService


@pytest.fixture
def db(tmp_path):
    from aipd_os.state import migrations as mig
    path = str(tmp_path / "test.db")
    mig.migrate(path)
    return AIPDStateDB(path)


class TestSnapshotRepository:
    """ReadinessSnapshotRepository 基本操作。"""

    def test_create_and_get(self, db):
        with db.connect() as conn:
            repo = ReadinessSnapshotRepository(conn)
            repo.create(
                "snap-1", "T-A", "P-1", "PASS",
                [{"dim": "validation", "status": "PASS"}],
                [], [], [], [], [],
                "fingerprint-abc",
            )
            conn.commit()
            snap = repo.get("snap-1", "T-A", "P-1")
            assert snap is not None
            assert snap["overall_status"] == "PASS"
            assert snap["ruleset_version"] == READINESS_RULESET_VERSION
            assert snap["input_fingerprint"] == "fingerprint-abc"

    def test_latest_returns_most_recent(self, db):
        with db.connect() as conn:
            repo = ReadinessSnapshotRepository(conn)
            repo.create("snap-1", "T-A", "P-1", "HOLD", [], [], [], [], [], [],
                         "fp-1")
            repo.create("snap-2", "T-A", "P-1", "PASS", [], [], [], [], [], [],
                         "fp-2")
            conn.commit()
            latest = repo.latest("T-A", "P-1")
            assert latest["snapshot_id"] == "snap-2"

    def test_superseded_excluded_from_latest(self, db):
        with db.connect() as conn:
            repo = ReadinessSnapshotRepository(conn)
            repo.create("snap-1", "T-A", "P-1", "PASS", [], [], [], [], [], [],
                         "fp-1")
            conn.commit()
            repo.mark_superseded("T-A", "P-1")
            conn.commit()
            assert repo.latest("T-A", "P-1") is None

    def test_list_snapshots(self, db):
        with db.connect() as conn:
            repo = ReadinessSnapshotRepository(conn)
            for i in range(5):
                repo.create(f"snap-{i}", "T-A", "P-1", "HOLD", [], [], [], [], [],
                             [], f"fp-{i}")
            conn.commit()
            snaps = repo.list_snapshots("T-A", "P-1", limit=3)
            assert len(snaps) == 3


class TestInputFingerprint:
    """输入 fingerprint 的确定性。"""

    def test_deterministic(self):
        inputs = {"product_version": "v2", "bom_revision": 3}
        fp1 = compute_input_fingerprint(inputs)
        fp2 = compute_input_fingerprint(inputs)
        assert fp1 == fp2

    def test_changes_with_input(self):
        fp1 = compute_input_fingerprint({"a": 1})
        fp2 = compute_input_fingerprint({"a": 2})
        assert fp1 != fp2


class TestReadinessSnapshotWiring:
    """ReadinessService.evaluate() 自动持久化快照。"""

    def test_evaluate_creates_snapshot(self, db):
        v_svc = ValidationService(db)
        i_svc = IssueService(db)
        r_svc = ReadinessService(v_svc, i_svc)
        # Create a PASS validation
        plan = v_svc.create_plan("T-A", "P-1", "EVT", "Test Plan")
        test = v_svc.create_test("T-A", "P-1", plan.plan_id, "Test", "EVT",
                                  required=True)
        run = v_svc.create_run("T-A", "P-1", test.test_id)
        v_svc.record_result("T-A", "P-1", run.run_id, test.test_id, RESULT_PASS)
        # Evaluate readiness
        report = r_svc.evaluate("T-A", "P-1",
                                 product_definition_complete=True,
                                 cad_maturity_ok=True,
                                 bom_release_ready=True,
                                 cost_complete=True,
                                 supply_chain_ready=True)
        # Snapshot should have been persisted
        with db.connect() as conn:
            repo = ReadinessSnapshotRepository(conn)
            latest = repo.latest("T-A", "P-1")
        assert latest is not None
        assert latest["overall_status"] == report.overall_status
        assert latest["ruleset_version"] == READINESS_RULESET_VERSION

    def test_new_evaluation_supersedes_old(self, db):
        v_svc = ValidationService(db)
        i_svc = IssueService(db)
        r_svc = ReadinessService(v_svc, i_svc)
        # First evaluation
        r_svc.evaluate("T-A", "P-1")
        # Second evaluation
        r_svc.evaluate("T-A", "P-1")
        with db.connect() as conn:
            repo = ReadinessSnapshotRepository(conn)
            snaps = repo.list_snapshots("T-A", "P-1")
            latest = repo.latest("T-A", "P-1")
        # Should have 2 snapshots, but latest is not superseded
        assert len(snaps) == 2
        assert latest is not None
        # The older one should be superseded
        older = [s for s in snaps if s["snapshot_id"] != latest["snapshot_id"]]
        assert older[0]["superseded"] == 1
