#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Verdict:
    status: str
    score: float
    hard_failures: list[dict[str, Any]]
    missing_artifacts: list[str]
    regressions: list[Any]
    high_risk_assumptions: list[Any]
    improvement: float | None
    reason: str
    next_action: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "score": round(self.score, 6),
            "hard_failures": self.hard_failures,
            "missing_artifacts": self.missing_artifacts,
            "regressions": self.regressions,
            "high_risk_assumptions": self.high_risk_assumptions,
            "improvement": None if self.improvement is None else round(self.improvement, 6),
            "reason": self.reason,
            "next_action": self.next_action,
        }


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def artifact_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def normalized_objective_score(objective: dict[str, Any], actual: float) -> float:
    direction = objective["direction"]
    target = float(objective["target"])
    limit = float(objective["limit"])
    if direction == "min":
        if limit <= target:
            raise ValueError(f"{objective['id']}: for min objective, limit must be greater than target")
        if actual <= target:
            return 1.0
        if actual >= limit:
            return 0.0
        return (limit - actual) / (limit - target)
    if direction == "max":
        if limit >= target:
            raise ValueError(f"{objective['id']}: for max objective, limit must be less than target")
        if actual >= target:
            return 1.0
        if actual <= limit:
            return 0.0
        return (actual - limit) / (target - limit)
    raise ValueError(f"Unsupported direction: {direction}")


def compute_score(contract: dict[str, Any], report: dict[str, Any]) -> tuple[float, list[str]]:
    objectives = contract.get("soft_objectives", [])
    if not objectives:
        return 1.0, []
    metrics = report.get("metrics", {})
    weighted = 0.0
    total_weight = 0.0
    missing: list[str] = []
    for objective in objectives:
        metric = objective["metric"]
        weight = float(objective["weight"])
        total_weight += weight
        if metric not in metrics:
            missing.append(metric)
            continue
        actual = float(metrics[metric])
        weighted += normalized_objective_score(objective, actual) * weight
    if total_weight <= 0:
        raise ValueError("soft objective weights must sum to a positive value")
    return weighted / total_weight, missing


def prior_scores(history: dict[str, Any] | None) -> list[float]:
    if not history:
        return []
    values = history.get("scores", [])
    return [float(x) for x in values if isinstance(x, (int, float)) and math.isfinite(float(x))]


def evaluate(contract: dict[str, Any], report: dict[str, Any], history: dict[str, Any] | None = None) -> Verdict:
    required = contract.get("required_artifacts", [])
    artifacts = report.get("artifacts", {})
    missing_artifacts = [name for name in required if not artifact_present(artifacts.get(name))]

    by_id = {item.get("id"): item for item in report.get("hard_constraint_results", [])}
    hard_failures: list[dict[str, Any]] = []
    for constraint in contract.get("hard_constraints", []):
        cid = constraint["id"]
        result = by_id.get(cid)
        if not result:
            hard_failures.append({"id": cid, "reason": "missing_result"})
            continue
        if not bool(result.get("passed")):
            hard_failures.append({
                "id": cid,
                "reason": "failed",
                "actual": result.get("actual"),
                "evidence": result.get("evidence"),
                "safety_critical": bool(constraint.get("safety_critical")),
            })
        elif constraint.get("evidence_required") and not artifact_present(result.get("evidence")):
            hard_failures.append({"id": cid, "reason": "missing_evidence"})

    score, missing_metrics = compute_score(contract, report)
    for metric in missing_metrics:
        hard_failures.append({"id": f"METRIC:{metric}", "reason": "missing_soft_metric"})

    regressions = list(report.get("regressions", []))
    assumptions = list(report.get("high_risk_assumptions", []))
    scores = prior_scores(history)
    improvement = None if not scores else score - scores[-1]
    policy = contract.get("release_policy", {})
    min_score = float(policy.get("minimum_score", 0.9))
    min_improvement = float(policy.get("minimum_improvement", 0.01))
    max_iterations = int(policy.get("max_internal_iterations", 8))
    iteration = int(report.get("iteration", 1))
    conflict = bool(report.get("approved_requirement_conflict", False))

    if conflict:
        return Verdict(
            "owner_decision", score, hard_failures, missing_artifacts, regressions, assumptions, improvement,
            "已批准硬约束之间存在冲突，继续建模需要改变产品目标、成本、周期或风险接受度。",
            "生成单一决策包，给出推荐路线、选项及对成本/周期/性能的影响。",
        )
    if missing_artifacts:
        return Verdict(
            "repair", score, hard_failures, missing_artifacts, regressions, assumptions, improvement,
            "缺少 CAD Contract 要求的必需交付物。",
            "补齐缺失交付物后重新运行检查，不向产品所有者询问执行细节。",
        )
    if hard_failures:
        return Verdict(
            "repair", score, hard_failures, missing_artifacts, regressions, assumptions, improvement,
            "一个或多个硬约束未通过或缺少证据。",
            "修改最小责任源码区域，重新生成并复跑失败项、安全项和回归项。",
        )
    if regressions:
        return Verdict(
            "repair", score, hard_failures, missing_artifacts, regressions, assumptions, improvement,
            "本轮引入了已识别回归。",
            "回滚或修复回归，并复跑受影响的全部硬约束。",
        )
    if assumptions:
        return Verdict(
            "continue_validation", score, hard_failures, missing_artifacts, regressions, assumptions, improvement,
            "仍存在会影响生产发布的高风险假设。",
            "用测量、供应商数据、仿真或实体测试消除假设；无法消除时转入明确的外部验证任务。",
        )
    if score >= min_score:
        return Verdict(
            "ready_for_internal_release", score, hard_failures, missing_artifacts, regressions, assumptions, improvement,
            "硬约束、证据和回归检查通过，软目标达到发布阈值。",
            "生成受控 CAD 发布包；若下一步为发图、开模或下单，提交不可逆行为放行决策。",
        )

    plateau = improvement is not None and improvement < min_improvement
    if iteration >= max_iterations and plateau:
        return Verdict(
            "internal_replan", score, hard_failures, missing_artifacts, regressions, assumptions, improvement,
            "达到内部迭代上限且综合分数改善不足，但尚未证明需要改变产品所有者目标。",
            "重新分解目标、检查权重与几何策略；只有确认目标冲突时才提交产品所有者决策。",
        )
    return Verdict(
        "continue_optimization", score, hard_failures, missing_artifacts, regressions, assumptions, improvement,
        "硬约束已通过，但软目标尚未达到发布阈值。",
        "选择对综合分数贡献最高且风险最低的下一项优化，保持硬约束回归检查。",
    )


def validate_contract(contract: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = ["project_id", "contract_id", "cad_level", "spec_version", "required_artifacts", "hard_constraints", "soft_objectives", "release_policy"]
    for key in required:
        if key not in contract:
            errors.append(f"missing contract key: {key}")
    ids = [x.get("id") for x in contract.get("hard_constraints", [])]
    if len(ids) != len(set(ids)):
        errors.append("duplicate hard constraint id")
    obj_ids = [x.get("id") for x in contract.get("soft_objectives", [])]
    if len(obj_ids) != len(set(obj_ids)):
        errors.append("duplicate soft objective id")
    try:
        dummy = {"metrics": {x["metric"]: x["target"] for x in contract.get("soft_objectives", [])}}
        compute_score(contract, dummy)
    except Exception as exc:
        errors.append(str(exc))
    return errors


def selftest() -> None:
    contract = {
        "project_id": "T", "contract_id": "C", "cad_level": "CAD-L1", "spec_version": "1",
        "required_artifacts": ["source", "step", "inspection_report", "snapshot"],
        "hard_constraints": [{"id": "HC-1", "description": "valid", "evidence_required": True}],
        "soft_objectives": [{"id": "SO-1", "metric": "mass", "direction": "min", "target": 10, "limit": 20, "weight": 1}],
        "release_policy": {"minimum_score": 0.9, "minimum_improvement": 0.01, "max_internal_iterations": 3},
    }
    base = {
        "iteration": 1,
        "artifacts": {"source": "a.py", "step": "a.step", "inspection_report": "i.json", "snapshot": "s.png"},
        "hard_constraint_results": [{"id": "HC-1", "passed": True, "evidence": "i.json"}],
        "metrics": {"mass": 10}, "regressions": [], "high_risk_assumptions": [],
        "approved_requirement_conflict": False,
    }
    cases = []
    cases.append(("ready", base, None, "ready_for_internal_release"))
    missing = json.loads(json.dumps(base)); missing["artifacts"].pop("snapshot")
    cases.append(("missing", missing, None, "repair"))
    fail = json.loads(json.dumps(base)); fail["hard_constraint_results"][0]["passed"] = False
    cases.append(("hardfail", fail, None, "repair"))
    conflict = json.loads(json.dumps(base)); conflict["approved_requirement_conflict"] = True
    cases.append(("conflict", conflict, None, "owner_decision"))
    optimize = json.loads(json.dumps(base)); optimize["metrics"]["mass"] = 18
    cases.append(("optimize", optimize, {"scores": [0.1]}, "continue_optimization"))
    plateau = json.loads(json.dumps(optimize)); plateau["iteration"] = 3; plateau["metrics"]["mass"] = 17.95
    cases.append(("plateau", plateau, {"scores": [0.2, 0.205]}, "internal_replan"))
    assumptions = json.loads(json.dumps(base)); assumptions["high_risk_assumptions"] = ["unknown material"]
    cases.append(("assumption", assumptions, None, "continue_validation"))

    failures = []
    for name, report, history, expected in cases:
        actual = evaluate(contract, report, history).status
        if actual != expected:
            failures.append(f"{name}: expected {expected}, got {actual}")
    if failures:
        raise AssertionError("; ".join(failures))
    print(f"CAD convergence selftest: {len(cases)}/{len(cases)} passed")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate CAD iterations against an AIPD CAD Contract.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    validate = sub.add_parser("validate-contract")
    validate.add_argument("--contract", required=True)
    evaluate_p = sub.add_parser("evaluate")
    evaluate_p.add_argument("--contract", required=True)
    evaluate_p.add_argument("--report", required=True)
    evaluate_p.add_argument("--history")
    evaluate_p.add_argument("--out")
    sub.add_parser("selftest")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.cmd == "selftest":
        selftest()
        return 0
    contract = load_json(args.contract)
    errors = validate_contract(contract)
    if args.cmd == "validate-contract":
        result = {"ok": not errors, "errors": errors}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if not errors else 1
    if errors:
        print(json.dumps({"ok": False, "errors": errors}, ensure_ascii=False, indent=2))
        return 1
    report = load_json(args.report)
    history = load_json(args.history) if args.history else None
    result = evaluate(contract, report, history).as_dict()
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
