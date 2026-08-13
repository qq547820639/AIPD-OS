"""评估运行器。

对每个 case：构造 agent 挂具（role-play AIPD 监督者）调用 CompletionProvider 得到输出，
记录工具轨迹，再按 must/must_not 打分，产出 :class:`EvalResult`。

确定性逻辑契约（faceted_cad_no_overclaim 等）由实际代码驱动，见
``tests/test_behavior_contracts.py`` 与 ``golden_projects`` 夹具；本运行器对
``evals/evals.json`` 的 case 通过假/真模型文本评估，保证可运行、可回归。
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aipd_os import __version__ as _PKG_VERSION
from aipd_os.evals_runner.completion import (
    PROVIDER_CATEGORY_DETERMINISTIC_FIXTURE,
    CompletionProvider,
    EnvCompletionProvider,
    ModelNotConfiguredError,
    RecordedCompletionProvider,
)
from aipd_os.evals_runner.registry import Case
from aipd_os.evals_runner.scoring import evaluate_output
from aipd_os.evals_runner.versioning import build_report, save_eval_report

# 针对 evals.json 现有 case 的确定性脚本化响应（与 must 逐字匹配，且不含 must_not）。
# 注意：这些是 contract-test 夹具输出，绝不代表真实模型行为。
_DEFAULT_SCRIPT: dict[str, str] = {
    "autonomous-intake": (
        "已读取附件并建立或恢复项目状态，开始整理和研究材料，不先发长问卷。"
    ),
    "low-risk-layout": (
        "参数表版式已自行修改，继续执行剩余页面，并更新受影响页面，并继承前批附件状态。"
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
        "自动检查与收敛，只在冻结或硬约束冲突时询问。基于事实读取工程数据。"
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
    """单个 case 的评估结果。

    诚实元数据：provider / provider_category / endpoint_type / model /
    real_network_call / prompt_hash / token_count / cost / latency /
    retry_count / grader / trace / scoring_method / checks。
    """

    case_id: str
    prompt: str
    model_version: str
    tool_trajectory: list[dict[str, Any]] = field(default_factory=list)
    output: str = ""
    score: float = 0.0
    passed: bool = False
    failure_type: list[str] = field(default_factory=list)
    cost: float = 0.0
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    # ---- v5 诚实字段 ----
    provider: str = ""
    provider_category: str = PROVIDER_CATEGORY_DETERMINISTIC_FIXTURE
    endpoint_type: str = ""
    model: str = ""
    real_network_call: bool = False
    prompt_hash: str = ""
    token_count: int = 0
    latency: float = 0.0
    retry_count: int = 0
    grader: str = ""
    trace: str = ""
    scoring_method: list[str] = field(default_factory=list)
    checks: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "input": self.prompt,
            "prompt": self.prompt,
            "provider": self.provider,
            "provider_category": self.provider_category,
            "endpoint_type": self.endpoint_type,
            "model": self.model,
            "model_version": self.model_version,
            "real_network_call": self.real_network_call,
            "prompt_hash": self.prompt_hash,
            "token_count": self.token_count,
            "cost": self.cost,
            "latency": self.latency,
            "retry_count": self.retry_count,
            "grader": self.grader,
            "trace": self.trace,
            "scoring_method": self.scoring_method,
            "checks": self.checks,
            "tool_trace": self.tool_trajectory,
            "tool_trajectory": self.tool_trajectory,
            "output": self.output,
            "score": self.score,
            "passed": self.passed,
            "failure_type": self.failure_type,
            "time": self.generated_at,
        }


def _prompt_hash(messages: list[dict[str, Any]]) -> str:
    """对请求消息计算稳定 SHA-256 摘要（prompt hash）。"""
    raw = json.dumps(messages, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _estimate_tokens(text: str) -> int:
    """对输出做 token 估算（中英文混合：字符数/3 近似）。标为估算值。"""
    return max(0, int(len(text or "") / 3))


class EvalRunner:
    """评估运行器。"""

    def __init__(
        self,
        provider: CompletionProvider | None = None,
        workdir: str | None = None,
        script: dict[str, str] | None = None,
        version: str = _PKG_VERSION,
        state: list[dict[str, Any]] | None = None,
        artifacts: list[dict[str, Any]] | None = None,
        db: list[dict[str, Any]] | None = None,
        judge: Any | None = None,
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
        # 供 evaluate_output 使用的额外评分输入（结构化/状态/产物/DB/独立judge）
        self.state = state
        self.artifacts = artifacts
        self.db = db
        self.judge = judge

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
        trajectory: list[dict[str, Any]] = []
        p_hash = _prompt_hash(messages)
        provider_name = type(self.provider).__name__
        category = self.provider.category()
        endpoint_type = self.provider.endpoint_type()
        real_network = self.provider.real_network_call()
        model_name = self.provider.model()

        start = time.monotonic()
        try:
            output = self.provider.complete(messages)
        except ModelNotConfiguredError as exc:
            latency = round(time.monotonic() - start, 4)
            return EvalResult(
                case_id=case.id,
                prompt=case.prompt,
                model_version=model_name,
                tool_trajectory=[],
                output=str(exc),
                score=0.0,
                passed=False,
                failure_type=["external"],
                provider=provider_name,
                provider_category=category,
                endpoint_type=endpoint_type,
                model=model_name,
                real_network_call=real_network,
                prompt_hash=p_hash,
                latency=latency,
                retry_count=0,
                grader="external",
                trace="real_model_not_configured: external_dependency, no fake substitution",
            )
        latency = round(time.monotonic() - start, 4)
        trajectory.append(
            {"tool": "supervisor", "input": case.prompt, "output": output, "ok": True}
        )

        ev = evaluate_output(case, output, state=self.state, artifacts=self.artifacts,
                             db=self.db, judge=self.judge)
        scoring_method = ev["graders"]
        grader_label = "+".join(scoring_method) if scoring_method else "none"
        failure: list[str] = list(ev["failure_type"])
        return EvalResult(
            case_id=case.id,
            prompt=case.prompt,
            model_version=model_name,
            tool_trajectory=trajectory,
            output=output,
            score=ev["score"],
            passed=ev["passed"],
            failure_type=failure,
            provider=provider_name,
            provider_category=category,
            endpoint_type=endpoint_type,
            model=model_name,
            real_network_call=real_network,
            prompt_hash=p_hash,
            token_count=_estimate_tokens(output),
            latency=latency,
            retry_count=0,
            grader=grader_label,
            trace="\n".join(f"{c['method']}:{c['name']} ok={c['ok']}" for c in ev["checks"]),
            scoring_method=scoring_method,
            checks=ev["checks"],
        )

    def run(
        self,
        cases: list[Case],
        out_dir: str | None = None,
        report_version: str | None = None,
    ) -> list[EvalResult]:
        """运行全部 case，可选保存版本化报告，返回结果列表。"""
        results = [self.run_case(case) for case in cases]
        if out_dir:
            save_eval_report(
                build_report(results, version=report_version or self.version),
                out_dir,
                version=report_version or self.version,
            )
        return results


def run_real_model_smoke(
    cases: list[Case],
    out_dir: str | None = None,
    report_version: str | None = None,
    provider: CompletionProvider | None = None,
    endpoint_env: str = "AIPD_EVAL_MODEL_ENDPOINT",
    key_env: str = "AIPD_EVAL_MODEL_KEY",
    model_version_env: str = "AIPD_EVAL_MODEL_VERSION",
) -> list[EvalResult]:
    """真实模型冒烟/集成 job。

    仅在配置了真实端点凭据（AIPD_EVAL_MODEL_ENDPOINT/AIPD_EVAL_MODEL_KEY 一类）时
    才真实调用模型；未配置凭据时将每个 case 诚实标记为 ``external``/``skipped``，
    绝不使用假（deterministic-fixture）实现作为替代。
    """
    prov = provider or EnvCompletionProvider(
        endpoint_env=endpoint_env,
        key_env=key_env,
        model_version_env=model_version_env,
    )
    runner = EvalRunner(provider=prov)
    results = []
    for case in cases:
        result = runner.run_case(case)
        if result.failure_type == ["external"]:
            # 诚实：无凭据时不运行假实现替代，标记为外部跳过。
            result.trace = "real_model_smoke: no credentials -> external/skipped," \
                           " no fake substitution"
        results.append(result)
    if out_dir:
        save_eval_report(
            build_report(results, version=report_version or _PKG_VERSION),
            out_dir,
            version=report_version or _PKG_VERSION,
        )
    return results


__all__ = [
    "EvalResult",
    "EvalRunner",
    "build_report",
    "run_real_model_smoke",
    "_DEFAULT_SCRIPT",
]
