"""验证阶段结果分析、纠偏任务、回归、事实更新与 BOM/CAD 影响传播。"""

from __future__ import annotations

from typing import Any


def analyze_stage(records: list[dict[str, Any]], stage: str) -> dict[str, Any]:
    """对某阶段的实验室记录进行分组分析。

    返回 {stage, total, passed, failed, items, failing_items}。
    无已执行数据时 passed 不会为真（有记录才算通过）。
    """
    records = list(records or [])
    action_map = {"rerun": "rerun", "redesign": "redesign"}
    by_item: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        item = str(r.get("test_item", "")).strip()
        if not item:
            continue
        by_item.setdefault(item, []).append(r)

    passed = sum(1 for r in records if str(r.get("pass_fail", "")).lower() == "pass")
    failed = sum(1 for r in records if str(r.get("pass_fail", "")).lower() == "fail")

    items: list[dict[str, Any]] = []
    failing_items: list[dict[str, Any]] = []
    for item, recs in by_item.items():
        item_failed = sum(1 for r in recs if str(r.get("pass_fail", "")).lower() == "fail")
        status = "fail" if item_failed else "pass"
        items.append({"test_item": item, "status": status, "count": len(recs)})
        if item_failed:
            failing_items.append(
                {
                    "test_item": item,
                    "result": "fail",
                    "count": item_failed,
                    "actions": [action_map["rerun"], action_map["redesign"]],
                }
            )

    return {
        "stage": stage,
        "total": len(records),
        "passed": passed,
        "failed": failed,
        "items": items,
        "failing_items": failing_items,
    }


def create_correction_tasks(analysis: dict[str, Any], stage: str) -> list[dict[str, Any]]:
    """为每个失败项生成纠偏工作描述。"""
    tasks = []
    for i, item in enumerate(analysis.get("failing_items", [])):
        actions = item.get("actions") or ["rerun"]
        tasks.append(
            {
                "work_id": f"{stage}-corr-{i + 1}",
                "type": "correction",
                "stage": stage,
                "test_item": item["test_item"],
                "action": actions[0],
                "reason": f"{item['test_item']} 在 {stage} 阶段失败（{item['result']}）",
            }
        )
    return tasks


def mark_regression(
    analysis: dict[str, Any], prior_baseline: dict[str, str] | None
) -> dict[str, Any]:
    """与历史基线比较，找出回归与改进项。

    prior_baseline 形如 {test_item: "pass"/"fail"}。
    """
    prior = prior_baseline or {}
    current = {it["test_item"]: it.get("status") for it in analysis.get("items", [])}
    regressions = [
        ti for ti, st in current.items() if st == "fail" and prior.get(ti) == "pass"
    ]
    improved = [
        ti for ti, st in current.items() if st == "pass" and prior.get(ti) == "fail"
    ]
    return {"regressions": regressions, "improved": improved}


def update_facts(
    facts: dict[str, Any], analysis: dict[str, Any], stage: str
) -> dict[str, Any]:
    """把某阶段通过/失败计数合并进 consultation facts 的 verification.<stage>。"""
    facts = dict(facts or {})
    verification = dict(facts.get("verification") or {})
    entry = dict(verification.get(stage) or {})
    entry["total"] = analysis["total"]
    entry["passed"] = analysis["passed"]
    entry["failed"] = analysis["failed"]
    # 无失败才算通过；无执行数据不标记通过
    if analysis["total"] > 0 and analysis["failed"] == 0:
        entry["passed_flag"] = True
    else:
        entry["passed_flag"] = False
    verification[stage] = entry
    facts["verification"] = verification
    return facts


def propagate_impact(
    facts: dict[str, Any],
    bom: list[dict[str, Any]],
    affected_keys: list[str],
) -> list[dict[str, Any]]:
    """对每个变更影响键，把受影响（part/param 命中）的 BOM 行/CAD 项标记为 stale。"""
    changed = set(affected_keys or [])
    stale: list[dict[str, Any]] = []
    for line in bom or []:
        parts = {
            str(line.get("part", "")).strip(),
            str(line.get("name", "")).strip(),
            str(line.get("key", "")).strip(),
        }
        params = set(str(p) for p in (line.get("params") or []))
        if parts & changed or params & changed:
            marked = dict(line)
            marked["stale"] = True
            stale.append(marked)
    return stale


__all__ = [
    "analyze_stage",
    "create_correction_tasks",
    "mark_regression",
    "update_facts",
    "propagate_impact",
]
