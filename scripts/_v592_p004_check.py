"""P0-04 fail-closed 验证：provider=None 时下游全部保持 queued（§16/17/49）。"""
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "tests")
from test_product_intelligence_runtime_e2e import _env  # noqa: E402

from aipd_os.execution.execution_router import ExecutionRouter  # noqa: E402
from aipd_os.execution.runs import RunStore  # noqa: E402
from aipd_os.product_intelligence import (  # noqa: E402
    ProductDefinitionSnapshotService,
)
from aipd_os.supervisor.idea_capabilities import (  # noqa: E402
    schedule_product_intelligence_chain,
)
from aipd_os.tool_adapters.builtin import build_registry  # noqa: E402
from aipd_os.tool_adapters.product_adapters import (  # noqa: E402
    register_product_adapters,
)

env = _env(tempfile.mkdtemp())
reg = build_registry()
register_product_adapters(reg, env["db"], provider=None)
router = ExecutionRouter(RunStore(str(Path(tempfile.mkdtemp()) / "e.db")), reg)
wids = schedule_product_intelligence_chain(env["sup"], env["idea"].idea_id)
for _ in range(10):
    env["sup"].run_supervisor(steps=1, adapter_registry=reg, router=router,
                              project_id="p1")
with sqlite3.connect(str(env["db"].path)) as c:
    rows = c.execute(
        "SELECT work_id, capability_floor, status FROM supervisor_work_items "
        "ORDER BY work_id").fetchall()
for r in rows:
    print(" ", r[0], r[1], "->", r[2])
statuses = {r[2] for r in rows}
snaps = ProductDefinitionSnapshotService(env["db"]).list_snapshots("default",
                                                                   "p1")
assert "blocked_external" in statuses, "W1 should be blocked_external"
assert "complete" not in statuses, "downstream must NOT run"
assert len(snaps) == 0, "no snapshot allowed with blocked upstream"
print("P0-04 FAIL-CLOSED OK (downstream all blocked, no snapshot)")
