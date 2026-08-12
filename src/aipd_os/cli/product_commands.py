"""CLI product 命令（v5.9.1，§55-58/67）。

CLI 只做 parse → call service → render；业务逻辑在
:mod:`aipd_os.product_intelligence`。

输出（§57）：Live（Insights/Opportunities/Principles/Requirements/Features +
Selected Opportunity）、Snapshot（id/hash/fresh-stale）、Technical Gate
（READY/CONDITIONAL/BLOCKED）、Authorization（APPROVED/REJECTED/PENDING/
APPROVED_WITH_WAIVER）、Commit Eligibility（YES/NO + reason）。所有命令支持
``--json``（§58：CI/Web/automation 稳定读取）。
"""
from __future__ import annotations

import json
from typing import Any, cast

from aipd_os.product_intelligence import (
    GATE_CHOICE_APPROVE_WITH_WAIVER,
    ProductDefinitionGate,
    ProductDefinitionProjection,
    ProductDefinitionSnapshotService,
)
from aipd_os.state.db import AIPDStateDB

DEFAULT_TENANT = "default"


def _db(args) -> tuple[AIPDStateDB, str, str]:
    db = AIPDStateDB(args.db)
    tenant = getattr(args, "tenant", DEFAULT_TENANT)
    return db, tenant, _resolve_project(db, tenant)


def _resolve_project(db: AIPDStateDB, tenant: str) -> str:
    try:
        projects = db.list_projects(tenant)
    except Exception:  # noqa: BLE001 - 兼容旧接口
        projects = []
    if not projects:
        return "default"
    return cast(str, projects[0]["project_id"])


def _emit(payload: dict[str, Any] | None, args, human: str) -> int:
    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(human)
    return 0


def cmd_product_show(args) -> int:
    """aipd product show：live 产品定义 + snapshot + gate 状态（--json）。"""
    db, tenant, pid = _db(args)
    proj = ProductDefinitionProjection(db, tenant, pid)
    if getattr(args, "json", False):
        return _emit(proj.project(), args, "")
    print(proj.to_markdown())
    return 0


def _snapshot_summary(db: AIPDStateDB, tenant: str, project: str) -> dict:
    snaps = ProductDefinitionSnapshotService(db)
    latest = snaps.latest_snapshot(tenant, project)
    if latest is None:
        return {"id": None, "hash": None, "fresh": None,
                "stale_reasons": [], "lifecycle_status": None}
    stale, reasons = snaps.is_stale(latest, tenant, project)
    return {"id": latest.snapshot_id, "hash": latest.content_hash,
            "fresh": not stale, "stale_reasons": reasons,
            "lifecycle_status": latest.lifecycle_status}


def _gate_status(db: AIPDStateDB, tenant: str, project: str) -> dict:
    """technical + authorization + eligibility（§57）。"""
    gate = ProductDefinitionGate(db, tenant, project)
    snaps = ProductDefinitionSnapshotService(db)
    latest = snaps.latest_snapshot(tenant, project)
    if latest is None:
        return {
            "snapshot": None,
            "technical": {"result": "NO_SNAPSHOT", "hard_blockers": [],
                          "conditional_blockers": [], "warnings": [],
                          "information": ["create_snapshot() first"]},
            "authorization": {"state": "PENDING", "decision_id": None,
                              "choice": None, "waiver": None},
            "eligibility": {"eligible": False, "reason": "no snapshot"},
        }
    evaluation = gate.evaluate_snapshot(latest)
    authorization = gate.authorization_status(latest.snapshot_id)
    eligibility = gate.commit_eligibility(evaluation, authorization)
    return {
        "snapshot": {"id": latest.snapshot_id, "hash": latest.content_hash},
        "technical": {
            "result": evaluation.result,
            "hard_blockers": evaluation.hard_blockers,
            "conditional_blockers": evaluation.conditional_blockers,
            "warnings": evaluation.warnings,
            "information": evaluation.information,
        },
        "authorization": authorization,
        "eligibility": eligibility,
    }


def cmd_product_gate(args) -> int:
    """aipd product gate：snapshot + technical gate + authorization +
    eligibility；--propose 创建 Owner Decision；--decision-id/--choice 裁定
    （approve_with_waiver 需 --waiver-conditions/--waiver-risks）。"""
    db, tenant, pid = _db(args)
    gate = ProductDefinitionGate(db, tenant, pid)

    if getattr(args, "propose", False):
        did = gate.propose_owner_decision(actor="owner-cli")
        return _emit({"command": "product gate", "ok": True,
                      "decision_id": did, "action": "proposed"},
                     args,
                     f"Owner Decision 已创建：{did}"
                     f"（approve/reject/request_revision/approve_with_waiver）")

    if getattr(args, "decision_id", None):
        if not getattr(args, "choice", None):
            raise ValueError(
                "--choice 必填（approve/reject/request_revision/"
                "approve_with_waiver）")
        waiver = None
        if args.choice == GATE_CHOICE_APPROVE_WITH_WAIVER:
            if not getattr(args, "waiver_conditions", None):
                raise ValueError(
                    "--waiver-conditions 必填（approve_with_waiver 需显式 "
                    "waiver，P0-04）")
            waiver = {
                "accepted_conditions": args.waiver_conditions,
                "accepted_risks": getattr(args, "waiver_risks", "") or "",
                "owner": "owner-cli",
                "expires_if_changed": True,
            }
        outcome = gate.resolve_owner_decision(
            args.decision_id, args.choice, getattr(args, "comment", "") or "",
            actor="owner-cli", waiver=waiver)
        return _emit({"command": "product gate", "ok": True, **outcome},
                     args,
                     f"决策 {args.decision_id} 已裁定：{args.choice}")

    # 无操作参数 → 状态输出
    snapshot = _snapshot_summary(db, tenant, pid)
    gate_status = _gate_status(db, tenant, pid)
    payload = {"command": "product gate", "tenant_id": tenant,
               "project_id": pid, "snapshot": snapshot,
               "technical": gate_status["technical"],
               "authorization": gate_status["authorization"],
               "eligibility": gate_status["eligibility"]}
    if getattr(args, "json", False):
        return _emit(payload, args, "")
    lines = [f"Product Definition Gate: {payload['technical']['result']}"]
    snap = payload["snapshot"]
    if snap["id"]:
        lines.append(f"Snapshot: {snap['id']} hash={snap['hash'][:12]}… "
                     f"fresh={snap['fresh']} ({snap['lifecycle_status']})")
        for r in snap["stale_reasons"]:
            lines.append(f"  stale: {r}")
    for b in payload["technical"]["hard_blockers"]:
        lines.append(f"  HARD: {b}")
    for b in payload["technical"]["conditional_blockers"]:
        lines.append(f"  CONDITIONAL: {b}")
    for b in payload["technical"]["warnings"]:
        lines.append(f"  WARN: {b}")
    auth = payload["authorization"]
    lines.append(f"Authorization: {auth['state']}"
                 + (f" (decision {auth['decision_id']}, "
                    f"choice={auth['choice']})" if auth["decision_id"] else ""))
    elig = payload["eligibility"]
    lines.append(f"Commit Eligibility: "
                 f"{'YES' if elig['eligible'] else 'NO'} ({elig['reason']})")
    return _emit(None, args, "\n".join(lines))


__all__ = ["cmd_product_show", "cmd_product_gate"]
