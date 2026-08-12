"""ImpactPropagationService 验证（v5.9.2，§32-34）。

场景：完整 Runtime 链产出 5 域对象 + frozen snapshot 后，
上游 claim 变化 → 全链受影响（insight→opportunity→principle→
requirement→feature）+ frozen snapshot 被标记 STALE。
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "tests")
from test_product_intelligence_runtime_e2e import (  # noqa: E402
    _env, _run_all,
)
from aipd_os.supervisor.idea_capabilities import (  # noqa: E402
    schedule_product_intelligence_chain,
)
from aipd_os.product_intelligence.impact import (  # noqa: E402
    ImpactPropagationService,
)
from aipd_os.product_intelligence.service import (  # noqa: E402
    NODE_FEATURE, NODE_INSIGHT, NODE_OPPORTUNITY, NODE_PRINCIPLE,
    NODE_REQUIREMENT,
)
from aipd_os.product_intelligence.snapshot import (  # noqa: E402
    ProductDefinitionSnapshotService, SNAPSHOT_FROZEN,
)

env = _env(tempfile.mkdtemp())
pi = env["pi"]
sup = env["sup"]

# Segment A: insights + opportunities
wids_a = schedule_product_intelligence_chain(
    sup, env["idea"].idea_id,
    steps=("derive_insights", "identify_opportunity"))
for _ in range(3):
    _run_all(env, steps=1)

opps = pi.list_opportunities("default", "p1")
assert len(opps) >= 1, "need opportunity"
pi.select_opportunity("default", "p1", opps[0].opportunity_id)

# Segment B: principles..gate
wids_b = schedule_product_intelligence_chain(
    sup, env["idea"].idea_id,
    steps=("derive_principles", "derive_requirements", "derive_features",
           "create_snapshot", "definition_gate"))
for _ in range(6):
    _run_all(env, steps=1)

insights = pi.list_insights("default", "p1")
principles = pi.list_principles("default", "p1")
requirements = pi.list_requirements("default", "p1")
features = pi.list_features("default", "p1")
snaps = ProductDefinitionSnapshotService(env["db"]).list_snapshots("default", "p1")
assert len(snaps) == 1, "exactly one snapshot"
assert snaps[0].lifecycle_status == SNAPSHOT_FROZEN, "snapshot frozen"

imp = ImpactPropagationService(env["db"])
# 上游变化：第一个 claim
claim_id = env["claims"]["problem"].claim_id

affected = imp.find_affected_objects("default", "p1", "claim", [claim_id])
types = {a["node_type"] for a in affected}
print("affected types:", sorted(types))
for a in affected:
    print("  ", a["node_type"], a["node_id"][:8], "via", a["relation"],
          a["via"][:8])
assert NODE_INSIGHT in types, "insight must be affected"
assert NODE_OPPORTUNITY in types, "opportunity must be affected"
assert NODE_PRINCIPLE in types, "principle must be affected"
assert NODE_REQUIREMENT in types, "requirement must be affected"
assert NODE_FEATURE in types, "feature must be affected"
assert affected, "non-empty"

snap_ids = imp.affected_snapshot_ids("default", "p1", "claim", [claim_id])
print("affected snapshot ids:", snap_ids)
assert len(snap_ids) == 1, "frozen snapshot affected"

staled = imp.mark_affected_snapshots_stale("default", "p1", "claim",
                                           [claim_id], actor="tester")
print("staled:", staled)
snap = ProductDefinitionSnapshotService(env["db"]).get_snapshot(
    "default", "p1", snaps[0].snapshot_id)
print("snapshot lifecycle after:", snap.lifecycle_status)
assert snap.lifecycle_status == "stale", "frozen -> stale"
assert staled == [snaps[0].snapshot_id]

# 幂等性：再次传播不再产生新影响（已 stale 快照不重复处理）
again = imp.affected_snapshot_ids("default", "p1", "claim", [claim_id])
assert again == [], "already stale snapshot not re-flagged"

print("IMPACT PROPAGATION OK (§32-34: full chain + snapshot stale)")
