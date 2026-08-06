"""EVT/DVT/PVT 阶段报告导入、根因提取、纠偏建议与回归验证。

只做真实、确定性的分析：根因（root cause）与纠偏行动（corrective action）
只在数据中真实存在时被提取；缺失时保持 not_verified，绝不虚构。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from aipd_os.supply_chain.analysis import analyze_stage, mark_regression
from aipd_os.supply_chain.lab import import_lab_report

VALID_STAGES = ("evt", "dvt", "pvt")


def import_stage_report(path: Union[str, Path], stage: str) -> Dict[str, Any]:
    """导入某物理验证阶段（EVT/DVT/PVT）的报告。

    委托给 :func:`aipd_os.supply_chain.lab.import_lab_report`；PDF/DOCX 等
    无法在本地解析的格式会抛 ``external_blocked``（不伪造）。
    """
    if stage not in VALID_STAGES:
        raise ValueError(f"'stage' 必须是 {sorted(VALID_STAGES)} 之一，收到 {stage!r}")
    returned = import_lab_report(path, stage)
    returned = dict(returned)
    returned["stage"] = stage
    return returned


def extract_root_cause(records: List[Dict[str, Any]], test_item: str) -> Dict[str, Any]:
    """提取某个失败测试项的根因。

    - 优先读取记录中的显式 ``root_cause`` 字段；
    - 否则从 ``notes``/``result`` 中做确定性启发式提取；
    - 找不到时返回 ``status="not_verified"``（不虚构根因）。
    """
    records = list(records or [])
    failing = [
        r for r in records
        if str(r.get("test_item", "")).strip() == test_item
        and str(r.get("pass_fail", "")).strip().lower() == "fail"
    ]
    if not failing:
        return {
            "test_item": test_item,
            "status": "not_verified",
            "root_cause": None,
            "reason": f"无 {test_item} 的失败记录，无法提取根因",
        }

    # 1) 显式 root_cause 字段
    for r in failing:
        rc = str(r.get("root_cause") or "").strip()
        if rc:
            return {
                "test_item": test_item,
                "status": "identified",
                "root_cause": rc,
                "sample_id": r.get("sample_id"),
                "evidence_ref": r.get("sample_id"),
            }

    # 2) 从 notes/result 启发式提取（确定性关键词语法）
    for r in failing:
        blob = " ".join(
            str(r.get(k) or "") for k in ("notes", "result", "failure_mode", "comment")
        ).strip()
        if not blob:
            continue
        for marker in ("焊接", "开裂", "断裂", "变形", "过温", "漏电", "错位", "松脱", "氧化"):
            if marker in blob:
                return {
                    "test_item": test_item,
                    "status": "identified",
                    "root_cause": marker,
                    "evidence_ref": r.get("sample_id"),
                    "extracted_from": "notes",
                }

    return {
        "test_item": test_item,
        "status": "not_verified",
        "root_cause": None,
        "reason": "失败记录缺少 root_cause/notes 信息，无法在本机确定根因（不虚构）",
    }


def propose_corrective_actions(
    analysis: Dict[str, Any],
    stage: str,
    records: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """为每个失败项生成纠偏建议，并附带已识别的根因。

    根因缺失时 ``root_cause`` 保持 None，且不虚构纠偏有效性。
    """
    records = list(records or [])
    out: List[Dict[str, Any]] = []
    for i, item in enumerate(analysis.get("failing_items", [])):
        test_item = item["test_item"]
        rc = extract_root_cause(records, test_item)
        actions = item.get("actions") or ["rerun"]
        out.append({
            "work_id": f"{stage}-ca-{i + 1}",
            "type": "corrective_action",
            "stage": stage,
            "test_item": test_item,
            "action": actions[0],
            "root_cause": rc,
            "rationale": f"{test_item} 在 {stage} 阶段失败；请按 {actions[0]} 纠偏并复测。",
        })
    return out


def verify_regression(
    records: List[Dict[str, Any]],
    prior_baseline: Optional[Dict[str, str]],
    stage: str = "pvt",
) -> Dict[str, Any]:
    """回归验证：核对此前失败项在本轮是否已通过。

    - 未提供任何记录的调用属于"无数据"，不判定任何项通过；
    - 此前失败且当前通过 -> verified；
    - 此前失败且当前仍失败/无数据 -> not_verified（保持未验证）。
    """
    records = list(records or [])
    analysis = analyze_stage(records, stage)
    current = {it["test_item"]: it.get("status") for it in analysis.get("items", [])}
    prior = prior_baseline or {}

    verified: List[str] = []
    not_verified: List[str] = []
    not_executed: List[str] = []
    for test_item, prior_status in prior.items():
        if prior_status != "fail":
            continue
        cur = current.get(test_item)
        if cur == "pass":
            verified.append(test_item)
        elif cur == "fail":
            not_verified.append(test_item)
        else:
            not_executed.append(test_item)
            not_verified.append(test_item)

    regressions = mark_regression(analysis, prior).get("regressions", [])
    return {
        "stage": stage,
        "verified": verified,
        "not_verified": not_verified,
        "not_executed": not_executed,
        "regressions": regressions,
        "all_verified": bool(verified) and not not_verified,
        "has_evidence": bool(records),
    }


__all__ = [
    "VALID_STAGES",
    "import_stage_report",
    "extract_root_cause",
    "propose_corrective_actions",
    "verify_regression",
]