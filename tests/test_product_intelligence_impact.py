"""ImpactPropagationService 正式测试（v5.9.2，§32-34）。

验证：上游 Claim 变化 → 下游 PI 对象全链受影响（Digital Thread 反向）+
frozen snapshot 标记 STALE（旧审批失效）。复用 runtime e2e 装配。
"""

import pytest

from aipd_os.product_intelligence.impact import (
    ImpactPropagationService,
)
from aipd_os.product_intelligence.service import (
    NODE_FEATURE,
    NODE_INSIGHT,
    NODE_OPPORTUNITY,
    NODE_PRINCIPLE,
    NODE_REQUIREMENT,
)
from aipd_os.product_intelligence.snapshot import (
    SNAPSHOT_FROZEN,
    ProductDefinitionSnapshotService,
)
from aipd_os.supervisor.idea_capabilities import (
    schedule_product_intelligence_chain,
)
from tests.test_product_intelligence_runtime_e2e import _env, _run_all


@pytest.fixture()
def full_chain(tmp_path):
    """完整 runtime 链：5 域对象 + frozen snapshot（复用 e2e 装配）。"""
    env = _env(tmp_path)
    pi = env["pi"]
    sup = env["sup"]
    schedule_product_intelligence_chain(
        sup, env["idea"].idea_id,
        steps=("derive_insights", "identify_opportunity"))
    for _ in range(3):
        _run_all(env, steps=1)
    opps = pi.list_opportunities("default", "p1")
    assert len(opps) >= 1
    pi.select_opportunity("default", "p1", opps[0].opportunity_id)
    schedule_product_intelligence_chain(
        sup, env["idea"].idea_id,
        steps=("derive_principles", "derive_requirements", "derive_features",
               "create_snapshot", "definition_gate"))
    for _ in range(6):
        _run_all(env, steps=1)
    snaps = ProductDefinitionSnapshotService(env["db"]).list_snapshots(
        "default", "p1")
    assert len(snaps) == 1
    assert snaps[0].lifecycle_status == SNAPSHOT_FROZEN
    env["pi"] = pi
    env["snaps"] = snaps
    return env


# ---------------------------------------------------------------------------
# §32-34 对象层影响分析（Digital Thread 反向）
# ---------------------------------------------------------------------------
def test_claim_change_affects_full_downstream_chain(full_chain):
    """Claim 变化 → insight/opportunity/principle/requirement/feature 全链。"""
    env = full_chain
    claim_id = env["claims"]["problem"].claim_id
    affected = ImpactPropagationService(env["db"]).find_affected_objects(
        "default", "p1", "claim", [claim_id])
    types = {a["node_type"] for a in affected}
    assert affected, "claim change must affect downstream objects"
    for node_type in (NODE_INSIGHT, NODE_OPPORTUNITY, NODE_PRINCIPLE,
                      NODE_REQUIREMENT, NODE_FEATURE):
        assert node_type in types, f"{node_type} must be affected"
    # 每条受影响记录带 relation 标注（数字线程可解释）
    assert all(a["relation"] for a in affected)
    assert all(a["via"] for a in affected)


def test_unrelated_claim_does_not_affect_chain(full_chain):
    """无关 claim（未接入 lineage）不产生任何影响。"""
    env = full_chain
    from aipd_os.idea import Claim, ClaimService
    other = ClaimService(env["db"]).create(Claim(
        claim_id="", tenant_id="default", project_id="p1",
        idea_id=env["idea"].idea_id, claim_type="problem",
        statement="unrelated-claim", epistemic_status="A"))
    affected = ImpactPropagationService(env["db"]).find_affected_objects(
        "default", "p1", "claim", [other.claim_id])
    assert affected == []
    # 且快照不受影响（仍 frozen）
    snap = ProductDefinitionSnapshotService(env["db"]).get_snapshot(
        "default", "p1", env["snaps"][0].snapshot_id)
    assert snap.lifecycle_status == SNAPSHOT_FROZEN


def test_unrelated_claim_snapshot_not_staled(full_chain):
    """无关 claim 变化 → 不 stale 任何快照。"""
    env = full_chain
    from aipd_os.idea import Claim, ClaimService
    other = ClaimService(env["db"]).create(Claim(
        claim_id="", tenant_id="default", project_id="p1",
        idea_id=env["idea"].idea_id, claim_type="user",
        statement="unrelated", epistemic_status="A"))
    staled = ImpactPropagationService(env["db"]).mark_affected_snapshots_stale(
        "default", "p1", "claim", [other.claim_id], actor="tester")
    assert staled == []
    snap = ProductDefinitionSnapshotService(env["db"]).get_snapshot(
        "default", "p1", env["snaps"][0].snapshot_id)
    assert snap.lifecycle_status == SNAPSHOT_FROZEN


# ---------------------------------------------------------------------------
# §30/33 Snapshot 失效（旧审批立即失效）
# ---------------------------------------------------------------------------
def test_claim_change_stales_frozen_snapshot(full_chain):
    """上游 claim 变化 → frozen snapshot 标记 STALE。"""
    env = full_chain
    claim_id = env["claims"]["problem"].claim_id
    imp = ImpactPropagationService(env["db"])
    snap_ids = imp.affected_snapshot_ids("default", "p1", "claim",
                                         [claim_id])
    assert snap_ids == [env["snaps"][0].snapshot_id]

    staled = imp.mark_affected_snapshots_stale(
        "default", "p1", "claim", [claim_id], actor="tester")
    assert staled == [env["snaps"][0].snapshot_id]

    snap = ProductDefinitionSnapshotService(env["db"]).get_snapshot(
        "default", "p1", env["snaps"][0].snapshot_id)
    assert snap.lifecycle_status == "stale"
    # stale 快照不再被重复标记（幂等）
    assert imp.affected_snapshot_ids("default", "p1", "claim",
                                     [claim_id]) == []


def test_stale_snapshot_cannot_be_committed(full_chain):
    """STALE 快照不能通过 Gate commit（旧审批失效后 commit 必须拒绝）。"""
    env = full_chain
    claim_id = env["claims"]["problem"].claim_id
    imp = ImpactPropagationService(env["db"])
    imp.mark_affected_snapshots_stale("default", "p1", "claim",
                                      [claim_id], actor="tester")

    from aipd_os.product_intelligence.gate import (
        ProductDefinitionGate,
    )
    gate = ProductDefinitionGate(env["db"], "default", "p1")
    from aipd_os.product_intelligence.snapshot import (
        SNAPSHOT_STALE,
    )
    snap = ProductDefinitionSnapshotService(env["db"]).get_snapshot(
        "default", "p1", env["snaps"][0].snapshot_id)
    assert snap.lifecycle_status == SNAPSHOT_STALE
    with pytest.raises(RuntimeError, match="only frozen snapshots"):
        gate.commit_snapshot(snap, actor="owner")
