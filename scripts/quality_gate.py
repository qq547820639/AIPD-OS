#!/usr/bin/env python3
"""质量门（G0-G9 交付物 + 所有者放行）：走唯一权威 AIPDStateDB。

历史版本基于废弃的 ``aipd_store.AIPDStore``；本脚本已切换到多租户权威
实现（tenant 固定 default，project 由 --project 指定）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SRC = str(Path(__file__).resolve().parents[1] / "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from aipd_os.state.db import AIPDStateDB  # noqa: E402

# Kept dependency-free: requirements mirror assets/templates/gate_requirements.yaml.
REQ = {
    'G0': ['project_brief', 'material_index', 'initial_fact_register', 'execution_map'],
    'G1': ['scenario_model', 'requirement_definition', 'non_goals', 'initial_risk_register'],
    'G2': ['concept_comparison', 'recommended_route', 'v1_value_test'],
    'G3': ['v1_engineering_definition', 'preliminary_bom', 'interface_register', 'dfmea_draft'],
    'G4': ['simulation_or_calculation_plan', 'result_or_execution_package', 'parameter_register'],
    'G5': ['product_specification', 'bom', 'key_parameter_table', 'supply_chain_plan',
           'rfq_package', 'dfm_dfa_review'],
    'G6': ['evt_plan', 'evt_raw_data', 'evt_report', 'issue_register'],
    'G7': ['dvt_plan', 'dvt_raw_data', 'dvt_report', 'compliance_status'],
    'G8': ['pvt_plan', 'process_capability', 'quality_control_plan',
           'mass_production_recommendation'],
    'G9': ['product_manual', 'release_package', 'release_audit', 'project_checkpoint'],
}
OWNER = {'G2', 'G5', 'G6', 'G7', 'G8', 'G9'}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True)
    p.add_argument("--project", default=None)
    p.add_argument("--gate")
    a = p.parse_args()

    db = AIPDStateDB(a.db)
    tenant = "default"
    pid = a.project
    if pid is None:
        projects = db.list_projects(tenant)
        if len(projects) != 1:
            print(json.dumps({"ok": False, "error":
                              "--project required (multiple projects)"},
                             ensure_ascii=False, indent=2))
            return 1
        pid = projects[0]["project_id"]
    project = db.get_project(tenant, pid)
    gate = a.gate or project["gate"]
    if gate not in REQ:
        print(json.dumps({"ok": False, "error": f"unknown gate {gate!r}"},
                         ensure_ascii=False, indent=2))
        return 1
    deliverables = db.list_deliverables(tenant, pid)
    complete = {d["type"] for d in deliverables
                if d.get("status") in {"complete", "approved", "released"}}
    missing = [x for x in REQ[gate] if x not in complete]
    proposed = [d for d in db.list_decisions(tenant, pid)
                if d.get("status") == "proposed"]
    result = {"gate": gate, "pass": not missing and not proposed,
              "missing_deliverables": missing,
              "open_decisions": [d["decision_id"] for d in proposed],
              "owner_approval_required": gate in OWNER}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
