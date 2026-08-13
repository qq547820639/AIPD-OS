#!/usr/bin/env python3
"""手册发布门禁：结构校验 + 视觉语义审计 + 黄金样本差距评测。

叠加三层检查，产出 ``release_decision``（PASS / HOLD / FAIL）：
1. 结构：``manual_chain.py validate``（页面/提示词/锚点/批次连续性）。
2. 视觉语义：``VisualAuditor.audit_batch``（页面结构/参数真实性/中文真文字/
   结构一致/人物一致/CMF/禁止旧图拼版/低清放大/占位伪文字）。
3. 黄金样本：``GoldenGapEvaluator.evaluate``（模块一致/场景写实/文案来源/
   参数来源/拼版/旧图复用/伪文字/参数臆造），需 ``--golden`` 提供清单。

诚实原则：未配置视觉后端时，人物/CMF 等维度标记 ``requiring_vision``，
顶层状态为 HOLD/not_verified，绝不假通过；黄金清单缺失字段按中性 0.5 计
并标记 golden_missing，同样落入 HOLD。

退出码：0=PASS（可发布），1=HOLD（缺外部能力/黄金数据，需所有者处理），
2=FAIL（硬件失败：结构/非视觉维度/渲染缺失）。
"""
import argparse, json, os, subprocess, sys
from pathlib import Path

# 允许独立运行 / 被测试子进程调用时导入 src 下的 aipd_os 包
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))


def _load_json(path):
    if not path:
        return None
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - 清单缺失/损坏时诚实计入失败
        return {"_error": str(exc)}


def _golden_needs_owner(golden: dict) -> bool:
    """黄金清单是否缺少可供判真的字段（modules/copy_text/params）。"""
    if not golden:
        return True
    return not (golden.get("modules") or golden.get("copy_text") or golden.get("theory")
                or golden.get("params") or golden.get("facts"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", required=True)
    ap.add_argument("--pages-dir", help="渲染后的页面目录（提供后执行视觉语义审计）")
    ap.add_argument("--facts", help="Product Truth facts JSON")
    ap.add_argument("--prior-hashes", help="前哈希 JSON 数组，用于禁止旧图复用")
    ap.add_argument("--golden", help="黄金样本清单 JSON 路径（可选）")
    ap.add_argument("--vision-backend", help="视觉后端标识（默认取环境变量 AIPD_VISION_BACKEND）")
    ap.add_argument("--json-out")
    a = ap.parse_args()

    # 1) 结构校验（manual_chain.py validate）
    tool = Path(__file__).with_name("manual_chain.py")
    r = subprocess.run([sys.executable, str(tool), "validate", "--state", a.state],
                       text=True, capture_output=True)
    try:
        structure = json.loads(r.stdout)
    except Exception:  # noqa: BLE001
        structure = {"passed": False, "errors": [r.stderr or r.stdout]}
    validate_passed = bool(structure.get("passed", False))

    d = json.loads(Path(a.state).read_text(encoding="utf-8"))

    vision_backend = a.vision_backend or os.environ.get("AIPD_VISION_BACKEND", "")
    facts = _load_json(a.facts)
    prior_hashes = _load_json(a.prior_hashes) or []

    # 2) 视觉语义审计（仅提供 pages_dir 时执行；向后兼容 selftest_v3 的结构门）
    visual_audit = None
    decision = "PASS"
    hard_fail = not validate_passed
    hold_reasons = []

    if a.pages_dir:
        from aipd_os.visual_audit import VisualAuditor, VisionAuditProvider
        # 真实视觉审核依赖 VisionAuditProvider 凭据（AIPD_VISION_PROVIDER_URL+KEY）；
        # 仅传 --vision-backend 字符串不再导致假通过（P1-1 修复）。
        vision_provider = VisionAuditProvider() if os.environ.get("AIPD_VISION_PROVIDER_URL") else None
        audit = VisualAuditor(
            vision_backend=vision_backend, vision_provider=vision_provider,
        ).audit_batch(d, a.pages_dir, facts=facts, prior_hashes=prior_hashes)
        visual_audit = audit
        if not audit["passed"]:
            if audit.get("rebuild_plan"):
                # rebuild_plan 只含非视觉维度失败的责任页 → 硬失败
                hard_fail = True
                hold_reasons.append("visual audit FAIL: 存在非视觉维度失败（需重建责任页）")
            else:
                hold_reasons.append("visual audit HOLD: 存在 requiring_vision 维度（无视觉后端）")

    # 3) 黄金样本差距评测（可选）
    golden_gap = None
    if a.golden:
        from aipd_os.visual_audit.golden import golden_gap_evaluate
        golden_result = golden_gap_evaluate(d, a.pages_dir, a.golden)
        golden_gap = golden_result
        if golden_result.get("error"):
            hard_fail = True
            hold_reasons.append(f"golden manifest 读取失败: {golden_result['error']}")
        elif any(p.get("render_missing") for p in golden_result.get("pages", [])):
            hard_fail = True
            hold_reasons.append("golden gap: 存在渲染缺失页面")
        elif not golden_result.get("passed"):
            hold_reasons.append("golden gap: 未达黄金阈值")
        elif _golden_needs_owner(_load_json(a.golden)):
            hold_reasons.append("golden gap: 黄金清单缺模块/文案/参数字段（golden_missing）")

    if hard_fail:
        decision = "FAIL"
    elif hold_reasons:
        decision = "HOLD"

    report = {
        "command": "manual_chain_gate",
        "passed": decision == "PASS",
        "release_decision": decision,
        "structure": structure,
        "visual_audit": visual_audit,
        "golden_gap": golden_gap,
        "hold_reasons": hold_reasons,
        "vision_backend": vision_backend or None,
        "manual_chain_planned": any(p.get("purpose") == "plan" for p in d.get("prompts", [])),
        "manual_anchors_locked": bool(d.get("anchors")),
        "manual_complete": validate_passed and len(d.get("pages", [])) >= d.get("minimum_pages", 10),
        "design_intent_frozen": bool(d.get("design_intent_package"))
            and validate_passed and len(d.get("pages", [])) >= d.get("minimum_pages", 10),
    }
    if a.json_out:
        Path(a.json_out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))

    code = {"PASS": 0, "HOLD": 1, "FAIL": 2}[decision]
    raise SystemExit(code)


if __name__ == "__main__":
    main()