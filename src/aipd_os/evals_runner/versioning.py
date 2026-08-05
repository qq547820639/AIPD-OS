"""评估数据版本化与回归门禁。

- :func:`save_eval_report`：把报告写入 ``<out_dir>/eval_reports/<version>/report.json``。
- :func:`load_baseline`：加载此前某一版本的基线。
- :func:`should_block_release`：当任一 case 的分数较基线下降超过阈值时阻止发布。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def build_report(
    results: list,
    version: str = "5.0.0",
    model_version: Optional[str] = None,
) -> Dict[str, Any]:
    """把结果列表组装为报告 dict。"""
    mv = model_version or (results[0].model_version if results else "unknown")
    return {
        "version": version,
        "model_version": mv,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total": len(results),
            "passed": sum(1 for r in results if r.passed),
            "external": sum(1 for r in results if "external" in r.failure_type),
        },
        "results": [r.to_dict() for r in results],
    }

def _now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def save_eval_report(
    report: Dict[str, Any],
    out_dir: str,
    version: Optional[str] = None,
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


def load_baseline(report_dir: str, version: str) -> Dict[str, Any]:
    """加载指定版本基线报告。"""
    path = Path(report_dir) / "eval_reports" / str(version) / "report.json"
    if not path.exists():
        raise FileNotFoundError(f"baseline missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _scores_by_case(report: Dict[str, Any]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for r in report.get("results", []):
        out[r["case_id"]] = float(r.get("score", 0.0))
    return out


def should_block_release(
    latest: Dict[str, Any],
    baseline: Dict[str, Any],
    threshold: float = 0.1,
) -> Dict[str, Any]:
    """比较最新与基线，任一 case 分数下降超过 ``threshold`` 则阻止发布。

    返回 ``{'blocked': bool, 'drop': float, 'reason': str, 'drops': {...}}``。
    """
    latest_scores = _scores_by_case(latest)
    baseline_scores = _scores_by_case(baseline)
    drops: Dict[str, float] = {}
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
