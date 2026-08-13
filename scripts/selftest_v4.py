#!/usr/bin/env python3
"""v4 supervisor 自检：状态初始化走唯一权威 AIPDStateDB（不再用废弃的
``aipd_store.AIPDStore``），Supervisor 调度/门禁脚本行为保持不变。"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from aipd_os.state.db import AIPDStateDB  # noqa: E402
from aipd_supervisor import Supervisor  # noqa: E402
from decision_policy import evaluate  # noqa: E402


def run(cmd, expect=0):
    r = subprocess.run(cmd, text=True, capture_output=True)
    if r.returncode != expect:
        raise AssertionError((cmd, r.returncode, r.stdout, r.stderr))
    return r


with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    db_path = td / "p.sqlite"
    base = AIPDStateDB(str(db_path))
    base.ensure_default_tenant()
    base.init_project("default", "T-001", "test", "deliver a product")
    sup = Supervisor(db_path)
    sup.init_lifecycle()
    w1 = sup.add_work("S1_theory", "research", "build theory", "evidence-backed theory", 90)
    w2 = sup.add_work("S2_product_definition", "product", "define v1",
                      "approved architecture", 80, [w1])
    w3 = sup.add_work("S3_manual", "manual", "plan manual", "manual plan", 70, [w2])
    assert sup.next_work()["work_id"] == w1
    sup.complete(w1, {"theory": "theory.docx"})
    assert sup.next_work()["work_id"] == w2
    sup.complete(w2, {"prd": "prd.docx"})
    assert sup.next_work()["work_id"] == w3
    assert evaluate({"category": "ordinary_layout_fix"})["ask_owner"] is False
    assert evaluate({"category": "tooling_or_purchase",
                     "irreversible": True})["ask_owner"] is True
    sup.register_capability("faceted-step", "available", "local", "C1")
    run([sys.executable, str(ROOT / "scripts/capability_gate.py"),
         "--ceiling", "C1", "--target", "C3"], 1)
    manifest = td / "life.json"
    manifest.write_text(json.dumps({"project_brief": "a", "truth_baseline": "b",
                                    "risk_register": "c", "work_plan": "d"}))
    run([sys.executable, str(ROOT / "scripts/lifecycle_gate.py"),
         "--manifest", str(manifest), "--phase", "S0_intake"])
    claim = td / "claim.json"
    claim.write_text(json.dumps({"manual_complete": 1, "manual_quality_report": 1,
                                 "page_lineage": 1}))
    run([sys.executable, str(ROOT / "scripts/claim_gate.py"),
         "--manifest", str(claim), "--claim", "manual_complete"])
    run([sys.executable, str(ROOT / "scripts/claim_gate.py"),
         "--manifest", str(claim), "--claim", "production_release_ready"], 1)
print("v4 supervisor selftest passed")
