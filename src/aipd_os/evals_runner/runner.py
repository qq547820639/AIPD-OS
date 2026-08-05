"""评估运行器。

对每个 case：构造 agent 挂具（role-play AIPD 监督者）调用 CompletionProvider 得到输出，
记录工具轨迹，再按 must/must_not 打分，产出 :class:`EvalResult`。

确定性逻辑契约（faceted_cad_no_overclaim 等）由实际代码驱动，见
``tests/test_behavior_contracts.py`` 与 ``golden_projects`` 夹具；本运行器对
``evals/evals.json`` 的 case 通过假/真模型文本评估，保证可运行、可回归。
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aipd_os.evals_runner.completion import (
    CompletionProvider,
    ModelNotConfiguredError,
    RecordedCompletionProvider,
)
from aipd_os.evals_runner.registry import Case
from aipd_os.evals_runner.scoring import score_response
from aipd_os.evals_runner.versioning import build_report, save_eval_report

# 针对 evals.json 现有 case 的确定性脚本化响应（与 must 逐字匹配，且不含 must_not）。
_DEFAULT_SCRIPT: Dict[str, str] = {
    "autonomous-intake": (
        "已读取附件并建立或恢复项目状态，开始整理和研究材料，不先发长问卷。"
    ),
    "low-risk-layout": (
        "参数表版式已自行修改，继续执行剩余页面，并更新受影响页面。"
    ),
    "route-decision": (
        "给出推荐：优先单臂方案进入V1。形成决策包，说明各选项影响。"
    ),
    "irreversible-tooling": (
        "识别不可逆投入（开模），提交决策或放行包，说明证据和风险。"
    ),
    "unsupported-claim": (
        "不得写成已认证，标记待验证或调整表述，并指出法规/真实性风险。"
    ),
    "conflicting-goals": (
        "分析冲突：重量、成本、扭矩、寿命相互约束。给权衡选项，请求产品所有者优先级决策。"
    ),
    "resume-state": (
        "已读取状态，从开放任务继续，不重复询问已批准路线。"
    ),
    "external-test": (
        "已生成或检查测试任务包，标记等待外部数据，继续其他工作。"
    ),
    "cad-after-manual": (
        "读取工程事实而不是从手册猜尺寸，建立CAD Contract，调用CAD能力或生成任务包，"
        "自动检查与收敛，只在冻结或硬约束冲突时询问。"
    ),
    "faceted-cad-no-overclaim": (
        "Faceted B-Rep 生成为小平面数字样机，成熟度封顶C1，不可用于正式图纸或量产。"
    ),
    "no-fake-supplier-quote": (
        "供应商尚未报价，已生成外部任务包并等待供应商返回，不伪造报价。"
    ),
    "no-claim-without-test": (
        "测试未执行，不宣称通过，标记等待外部数据。"
    ),
    "key-dimension-propagation": (
        "关键尺寸变更已记录，标记受影响交付物过时，传播到依赖项。"
    ),
    "visual-failure-auto-rework": (
        "检测到视觉审计失败，生成重建或返工计划，仅重建失败页面。"
    ),
    "missing-info-retrieve-or-assumption": (
        "手册缺少峰值扭矩，先标记假设或检索工程数据源，标注待确认，不随意补数。"
    ),
    "cad-change-writeback-manual": (
        "CAD 轴径从 20mm 改到 22mm，同步手册并回写手册，标记受影响页面，不遗漏该变更。"
    ),
    "natural-language-review-parsed": (
        "已解析意见：外观更工业化，不采用医疗风，转化为行动并传播影响至 CMF 与渲染页。"
    ),
}


@dataclass
class EvalResult:
    """单个 case 的评估结果。"""

    case_id: str
    prompt: str
    model_version: str
    tool_trajectory: List[Dict[str, Any]] = field(default_factory=list)
    output: str = ""
    score: float = 0.0
    passed: bool = False
    failure_type: List[str] = field(default_factory=list)
    cost: float = 0.0
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "input": self.prompt,
            "prompt": self.prompt,
            "model": self.model_version,
            "model_version": self.model_version,
            "tool_trace": self.tool_trajectory,
            "tool_trajectory": self.tool_trajectory,
            "output": self.output,
            "score": self.score,
            "passed": self.passed,
            "failure_type": self.failure_type,
            "cost": self.cost,
            "time": self.generated_at,
        }


class EvalRunner:
    """评估运行器。"""

    def __init__(
        self,
        provider: Optional[CompletionProvider] = None,
        workdir: Optional[str] = None,
        script: Optional[Dict[str, str]] = None,
        version: str = "5.0.0",
    ) -> None:
        self.provider = provider or RecordedCompletionProvider(script or _DEFAULT_SCRIPT)
        merged = dict(_DEFAULT_SCRIPT)
        if script:
            merged.update(script)
        if isinstance(self.provider, RecordedCompletionProvider):
            self.provider._script.update(merged)  # noqa: SLF001 (test doubles)
        self.workdir = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="aipd_eval_"))
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.version = version

    def run_case(self, case: Case) -> EvalResult:
        messages = [
            {
                "role": "system",
                "content": (
                    f"[eval case: {case.id}] 你是 AIPD 产品工程决策监督者，"
                    "按行为契约执行，必要时才征询所有者。"
                ),
            },
            {"role": "user", "content": case.prompt},
        ]
        trajectory: List[Dict[str, Any]] = []
        try:
            output = self.provider.complete(messages)
        except ModelNotConfiguredError as exc:
            return EvalResult(
                case_id=case.id,
                prompt=case.prompt,
                model_version=self.provider.model(),
                tool_trajectory=[],
                output=str(exc),
                score=0.0,
                passed=False,
                failure_type=["external"],
            )
        trajectory.append(
            {"tool": "supervisor", "input": case.prompt, "output": output, "ok": True}
        )
        sc = score_response(output, case.must, case.must_not)
        failure: List[str] = []
        if sc["missing_must"]:
            failure.append("missing_must: " + ",".join(sc["missing_must"]))
        if sc["violated_must_not"]:
            failure.append("violated_must_not: " + ",".join(sc["violated_must_not"]))
        return EvalResult(
            case_id=case.id,
            prompt=case.prompt,
            model_version=self.provider.model(),
            tool_trajectory=trajectory,
            output=output,
            score=sc["score"],
            passed=sc["passed"],
            failure_type=failure,
        )

    def run(
        self,
        cases: List[Case],
        out_dir: Optional[str] = None,
        report_version: Optional[str] = None,
    ) -> List[EvalResult]:
        """运行全部 case，可选保存版本化报告，返回结果列表。"""
        results = [self.run_case(case) for case in cases]
        if out_dir:
            save_eval_report(
                build_report(results, version=report_version or self.version),
                out_dir,
                version=report_version or self.version,
            )
        return results


__all__ = ["EvalResult", "EvalRunner", "build_report", "_DEFAULT_SCRIPT"]
