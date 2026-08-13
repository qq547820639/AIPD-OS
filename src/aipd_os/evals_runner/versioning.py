"""评估数据版本化与回归门禁。

- :func:`save_eval_report`：把报告写入 ``<out_dir>/eval_reports/<version>/report.json``。
- :func:`load_baseline`：加载此前某一版本的基线。
- :func:`should_block_release`：当任一 case 的分数较基线下降超过阈值时阻止发布。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aipd_os import __version__ as _PKG_VERSION
from aipd_os.evals_runner.completion import (
    CATEGORY_LABELS,
    PROVIDER_CATEGORY_DETERMINISTIC_FIXTURE,
)


def _rate(passed: int, total: int) -> float:
    return round(passed / total, 4) if total else 0.0


def _split_by_category(results: list) -> dict[str, list]:
    """把结果按 provider_category 分组；外部/跳过计入对应类别但单独标记。"""
    groups: dict[str, list] = {}
    for r in results:
        cat = getattr(r, "provider_category", None) or PROVIDER_CATEGORY_DETERMINISTIC_FIXTURE
        groups.setdefault(cat, []).append(r)
    return groups


def build_report(
    results: list,
    version: str = _PKG_VERSION,
    model_version: str | None = None,
) -> dict[str, Any]:
    """把结果列表组装为报告 dict。

    诚实分离通过率：
    - ``summary.model_behavior``：真实模型行为通过率（排除 deterministic-fixture）。
    - ``summary.fixture_behavior``：夹具（contract-test）通过率，明确标注为夹具，
      绝不当作真实模型通过率。
    """
    mv = model_version or (results[0].model_version if results else "unknown")
    groups = _split_by_category(results)

    fixture_results = groups.get(PROVIDER_CATEGORY_DETERMINISTIC_FIXTURE, [])
    # 模型行为：真实模型（real-model）以及纯契约（code-driven）共同构成「非夹具」。
    model_results = [
        r for r in results
        if (getattr(r, "provider_category", None) or PROVIDER_CATEGORY_DETERMINISTIC_FIXTURE)
        != PROVIDER_CATEGORY_DETERMINISTIC_FIXTURE
    ]

    def _block(results_: list) -> dict[str, Any]:
        total = len(results_)
        passed = sum(1 for r in results_ if r.passed)
        external = sum(1 for r in results_ if "external" in r.failure_type)
        return {
            "total": total,
            "passed": passed,
            "external": external,
            "pass_rate": _rate(passed, total),
        }

    return {
        "version": version,
        "model_version": mv,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provider_categories": {
            cat: CATEGORY_LABELS.get(cat, cat) for cat in groups
        },
        "summary": {
            "total": len(results),
            "passed": sum(1 for r in results if r.passed),
            "external": sum(1 for r in results if "external" in r.failure_type),
            # 模型行为通过率：排除夹具。
            "model_behavior": _block(model_results),
            # 夹具通过率：明确标注为 fixture（contract-test），仅供参考，非真实模型通过率。
            "fixture_behavior": _block(fixture_results),
        },
        "results": [r.to_dict() for r in results],
    }

def _now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def save_eval_report(
    report: dict[str, Any],
    out_dir: str,
    version: str | None = None,
) -> str:
    """把报告写入 ``<out_dir>/eval_reports/<version>/report.json``，返回文件路径。"""
    version = version or report.get("version") or f"v{_now_ts()}"
    base = Path(out_dir) / "eval_reports" / str(version)
    base.mkdir(parents=True, exist_ok=True)
    path = base / "report.json"
    payload = dict(report)
    payload.setdefault("version", version)
    payload.setdefault("generated_at", datetime.now(timezone.utc).isoformat())
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def load_baseline(report_dir: str, version: str) -> dict[str, Any]:
    """加载指定版本基线报告。"""
    path = Path(report_dir) / "eval_reports" / str(version) / "report.json"
    if not path.exists():
        raise FileNotFoundError(f"baseline missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _scores_by_case(report: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for r in report.get("results", []):
        out[r["case_id"]] = float(r.get("score", 0.0))
    return out


def should_block_release(
    latest: dict[str, Any],
    baseline: dict[str, Any],
    threshold: float = 0.1,
) -> dict[str, Any]:
    """比较最新与基线，任一 case 分数下降超过 ``threshold`` 则阻止发布。

    返回 ``{'blocked': bool, 'drop': float, 'reason': str, 'drops': {...}}``。
    """
    latest_scores = _scores_by_case(latest)
    baseline_scores = _scores_by_case(baseline)
    drops: dict[str, float] = {}
    for cid, base in baseline_scores.items():
        if cid in latest_scores:
            diff = base - latest_scores[cid]
            if diff > threshold:
                drops[cid] = round(diff, 4)
    blocked = bool(drops)
    drop = max(drops.values(), default=0.0)
    if blocked:
        reason = "release blocked: " + "; ".join(
            f"{cid} -{v}" for cid, v in sorted(drops.items())
        )
    else:
        reason = "no case dropped more than threshold"
    return {"blocked": blocked, "drop": round(drop, 4), "reason": reason, "drops": drops}


__all__ = ["build_report", "save_eval_report", "load_baseline", "should_block_release", "_now_ts"]
