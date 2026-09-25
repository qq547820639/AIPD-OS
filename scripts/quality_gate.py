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

from aipd_os import gate_attribution as ga  # noqa: E402
from aipd_os import gate_requirements as gr  # noqa: E402
from aipd_os import schema_binding as sb  # noqa: E402
from aipd_os.state.db import AIPDStateDB  # noqa: E402


def _tables() -> dict:
    """从声明文件现读 G 表。读不到就 fail-closed：不退回任何内联副本。"""
    decl = gr.load()
    if decl["status"] != "ok":
        return {"ok": False, "why": decl["why"], "req": {}, "owner": set(),
                "declared": {}, "unenforced": []}
    declared = decl["gates"]
    return {"ok": True, "why": "", "req": gr.enforced_table(declared),
            "owner": decl["owner_gates"], "declared": declared,
            "unenforced": gr.unproduced_in(declared)}


TABLES = _tables()
REQ: dict[str, list[str]] = TABLES["req"]
OWNER = TABLES["owner"]
DONE = {"complete", "approved", "released"}


def contracted_types(req: dict[str, list[str]] | None = None) -> dict[str, str]:
    """REQ 里哪些交付物**类型**有同名契约（`<type>.schema.json` 在盘上）。

    现算不写死：契约加一份、门就自动多核一类；契约改名则这一类从门里掉出去，
    由 `tests/test_quality_gate_shape.py` 钉住「今天恰好只有 project_checkpoint 一类」。
    """
    contracts = {sb.schema_stem(n): n for n in sb.list_schemas(sb.ASSET_ROOT)}
    table = REQ if req is None else req
    return {t: contracts[t] for t in {x for v in table.values() for x in v} if t in contracts}


def shape_findings(deliverables: list[dict], root: Path,
                   contracts: dict[str, str]) -> list[dict]:
    """已标完成的交付物里，凡是**有契约**的类型，都必须真交上一份合形的文件。

    四种不通过各有名字：没填 path、文件不在、读不到/不是 JSON、形状不符。
    刻意不「没 path 就跳过」——那等于让「标完成但没东西」继续算过。
    """
    findings: list[dict] = []
    for row in deliverables:
        dtype = row.get("type")
        if dtype not in contracts or row.get("status") not in DONE:
            continue
        path = (row.get("path") or "").strip()
        base = {"deliverable_id": row.get("deliverable_id"), "type": dtype,
                "contract": contracts[dtype], "path": path or None}
        if not path:
            findings.append(dict(base, finding="path_missing",
                                 detail="标了完成却没填 path，形状无从核起"))
            continue
        result = sb.validate_artifact_file(root, path)
        if result["status"] == sb.VALID:
            continue
        findings.append(dict(base, finding=result["status"],
                             detail="; ".join(result["errors"]) or result["status"]))
    return findings


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True)
    p.add_argument("--project", default=None)
    p.add_argument("--gate")
    p.add_argument("--root", default=".",
                   help="交付物 path 的相对根（缺当前目录）；只在有同名契约的类型上才去读文件")
    a = p.parse_args()

    db = AIPDStateDB(a.db)
    # 每次跑都现读权威表（不是 import 期缓存的那份）：YAML 被修好后不必重装/重启就生效，
    # 而读不到时**没有**可读的表可退回。
    tables = _tables()
    req = tables["req"]
    if not tables["ok"]:
        # 权威表读不到 ⇒ 不能说「这关没有要求」，也不能悄悄拿旧副本继续判
        print(json.dumps({"ok": False, "gate": a.gate,
                          "error": f"gate requirements unreadable: {tables['why']}",
                          "source": gr.DECLARATION},
                         ensure_ascii=False, indent=2))
        return 3
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
    if gate not in req:
        print(json.dumps({"ok": False, "error": f"unknown gate {gate!r}"},
                         ensure_ascii=False, indent=2))
        return 1
    deliverables = db.list_deliverables(tenant, pid)
    complete = {d["type"] for d in deliverables if d.get("status") in DONE}
    missing = [x for x in req[gate] if x not in complete]
    contracts = contracted_types(req)
    shapes = shape_findings(deliverables, Path(a.root), contracts)
    proposed = [d for d in db.list_decisions(tenant, pid)
                if d.get("status") == "proposed"]
    # 门禁台账的批准归属只**报**不**判**：这一格分到「写了个像人的名字」为止，
    # 没有身份源，拿它当放行依据等于把署名当证据（见 gate_attribution 模块说明）。
    approvals = ga.project_gates(db, tenant, pid)
    result = {"gate": gate, "pass": not missing and not proposed and not shapes,
              "missing_deliverables": missing,
              "contracted_types": contracts,
              "shape_findings": shapes,
              "requirement_source": gr.DECLARATION,
              "gate_approval_attribution": approvals,
              "declared_unenforced": [t for t in tables["unenforced"]
                                      if t in tables["declared"].get(gate, [])],
              "enforced_counts": {"declared": len(tables["declared"].get(gate, [])),
                                  "enforced": len(req.get(gate, []))},
              "open_decisions": [d["decision_id"] for d in proposed],
              "owner_approval_required": gate in tables["owner"]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
