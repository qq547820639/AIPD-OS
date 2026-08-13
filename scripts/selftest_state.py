#!/usr/bin/env python3
"""状态服务自检（生产路径）：走唯一权威实现 ``aipd_os.state.db.AIPDStateDB``。

历史版本基于废弃的 ``aipd_store.AIPDStore``（旧单项目库）；本脚本已切换
到多租户权威实现，自检结果即生产路径行为。
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

SRC = str(Path(__file__).resolve().parents[1] / "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from aipd_os.state.db import AIPDStateDB  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory() as d:
        db = AIPDStateDB(str(Path(d) / "state.sqlite"))
        tenant, pid = "default", "TEST-001"
        db.ensure_default_tenant()
        db.init_project(tenant, pid, "Test Product", "Test autonomous workflow")
        db.add_fact(tenant, pid, "target_mass", "2.0", "A",
                    unit="kg", confidence=0.4, source="assumption")
        eid = db.add_evidence(tenant, pid, "paper", "Example paper",
                              identifier="doi:test", quality="peer-reviewed")
        facts = db.list_facts(tenant, pid)
        db.link_evidence(tenant, pid, facts[0]["fact_id"], eid)
        did = db.propose_decision(tenant, pid, "Core route", "Route A",
                                  [{"id": "A"}, {"id": "B"}],
                                  trigger="mutually exclusive route")
        assert db.get_project(tenant, pid)["status"] == "awaiting_owner_decision"
        db.resolve_decision(tenant, pid, did, "A", comment="approved")
        assert db.get_project(tenant, pid)["status"] == "active"
        db.add_deliverable(tenant, pid, "project_brief",
                           status="complete", gate="G0")
        assert db.list_facts(tenant, pid)[0]["value"] == "2.0"
        resolved = db.list_decisions(tenant, pid)
        assert resolved[0]["choice"] == "A"
    print("state self-test passed")


if __name__ == "__main__":
    main()
