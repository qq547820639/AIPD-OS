"""真实模型评测的诚实记录与预算门控 runner。

核心原则（诚实门控）：
  - 只有发生**真实网络调用**（``ModelCall.network_call is True``）才计入
    「模型行为通过率」；
  - fixture / contract 结果永远进入 ``fixture_behavior``，绝不进入
    ``model_behavior``；
  - 无真实凭据时（HOLD）报告 0 个样本，绝不把夹具当作真实通过率；
  - 记录 provider / model version / 网络调用 / token / 费用 / 延迟 / 重试 / trace，
    并对预算设上限、对凭据做保护（trace/报告中绝不出现密钥）。

凭据从环境读取：``AIPD_MODEL_API_KEY`` / ``AIPD_MODEL_BASE_URL`` /
``AIPD_MODEL_VERSION``；预算与调用上限：``AIPD_MODEL_EVAL_BUDGET_USD`` /
``AIPD_MODEL_EVAL_MAX_CALLS``。
"""

from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

# 任务状态
STATUS_HOLD = "HOLD"           # 无凭据/预算受限：不发起真实调用
STATUS_COMPLETED = "completed"  # 已执行真实调用并完成

# 默认成本估算（每 1k token 的美元成本，仅用于无真实计费时的估算）。
DEFAULT_USD_PER_1K_TOKENS = 0.002
DEFAULT_MAX_RETRIES = 3
DEFAULT_TIMEOUT_SECONDS = 60.0

# 真实调用结果状态
CALL_OK = "ok"
CALL_ERROR = "error"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_float_env(name: str, default: float | None) -> float | None:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        raise ValueError(f"{name} 必须是非负浮点数，got {raw!r}")


def _parse_int_env(name: str, default: int | None) -> int | None:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"{name} 必须是非负整数，got {raw!r}")


# ---------------------------------------------------------------------------
@dataclass
class ModelEvalConfig:
    """真实模型评测配置（凭据 + 预算 + 调用上限）。"""

    api_key: str = ""
    base_url: str = ""
    model_version: str = "aipd-eval-model"
    budget_usd: float | None = None
    max_calls: int | None = None
    max_retries: int = DEFAULT_MAX_RETRIES
    timeout: float = DEFAULT_TIMEOUT_SECONDS
    rate_usd_per_1k: float = DEFAULT_USD_PER_1K_TOKENS

    @property
    def configured(self) -> bool:
        """是否具备真实调用凭据。"""
        return bool(self.api_key) and bool(self.base_url)

    @property
    def base_host(self) -> str:
        from urllib.parse import urlparse

        return urlparse(self.base_url or "").netloc or "(unknown)"


def load_model_eval_config(
    api_key_env: str = "AIPD_MODEL_API_KEY",
    base_url_env: str = "AIPD_MODEL_BASE_URL",
    model_version_env: str = "AIPD_MODEL_VERSION",
    budget_env: str = "AIPD_MODEL_EVAL_BUDGET_USD",
    max_calls_env: str = "AIPD_MODEL_EVAL_MAX_CALLS",
    default_version: str = "aipd-eval-model",
) -> ModelEvalConfig:
    """从环境读取配置；缺凭据时 ``configured`` 为 False（诚实 HOLD）。"""
    return ModelEvalConfig(
        api_key=os.environ.get(api_key_env, "") or "",
        base_url=os.environ.get(base_url_env, "") or "",
        model_version=os.environ.get(model_version_env, "") or default_version,
        budget_usd=_parse_float_env(budget_env, None),
        max_calls=_parse_int_env(max_calls_env, None),
    )


@dataclass
class ModelCall:
    """一次真实模型调用的诚实记录。"""

    provider: str
    model_version: str
    network_call: bool = True
    token_count: int = 0
    prompt_token_count: int = 0
    completion_token_count: int = 0
    cost: float = 0.0
    latency: float = 0.0
    retry_count: int = 0
    status: str = CALL_OK
    trace: str = ""
    sample_id: str = ""
    prompt_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "provider": self.provider,
            "model_version": self.model_version,
            "network_call": self.network_call,
            "token_count": self.token_count,
            "prompt_token_count": self.prompt_token_count,
            "completion_token_count": self.completion_token_count,
            "cost": self.cost,
            "latency": self.latency,
            "retry_count": self.retry_count,
            "status": self.status,
            "trace": self.trace,
            "prompt_hash": self.prompt_hash,
        }


def estimate_cost(token_count: int, usd_per_1k: float | None = None) -> float:
    """按 token 估算成本（美元）。无真实计费信息时使用默认单价。"""
    rate = usd_per_1k if usd_per_1k is not None else DEFAULT_USD_PER_1K_TOKENS
    return round((token_count / 1000.0) * rate, 6)


def _prompt_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# 真实 HTTP 客户端（OpenAI 兼容 /chat/completions）
# ---------------------------------------------------------------------------
ClientFn = Callable[[str, ModelEvalConfig], dict[str, Any]]


def _default_http_client(cfg: ModelEvalConfig) -> ClientFn:
    """构造 OpenAI 兼容的 HTTP 客户端。

    返回 ``{"text": ..., "usage": {"prompt_tokens": N, "completion_tokens": N}}``。
    凭据只用于请求头，绝不写入 trace/报告。
    """

    def caller(sample: str, cfg_: ModelEvalConfig) -> dict[str, Any]:
        import requests

        url = cfg_.base_url.rstrip("/")
        if not url.endswith("/chat/completions"):
            url = url.rstrip("/") + "/chat/completions"
        payload: dict[str, Any] = {
            "model": cfg_.model_version,
            "messages": [{"role": "user", "content": sample}],
            "stream": False,
        }
        headers = {"Authorization": f"Bearer {cfg_.api_key}", "Content-Type": "application/json"}
        resp = requests.post(url, json=payload, headers=headers, timeout=cfg_.timeout)
        resp.raise_for_status()
        data = resp.json()
        usage = data.get("usage") or {}
        content = data["choices"][0]["message"]["content"]
        return {"text": content, "usage": usage}

    return caller


# ---------------------------------------------------------------------------
# 报告构建（诚实区分 fixture 与真实模型）
# ---------------------------------------------------------------------------
def _rate(passed: int, total: int) -> float:
    return round(passed / total, 4) if total else 0.0


def model_behavior_block(calls: list[ModelCall]) -> dict[str, Any]:
    """真实模型行为：只统计真实网络调用（network_call=True）。"""
    real = [c for c in calls if c.network_call]
    total = len(real)
    passed = sum(1 for c in real if c.status == CALL_OK)
    external = sum(1 for c in real if c.status != CALL_OK)
    return {
        "total": total,
        "passed": passed,
        "external": external,
        "pass_rate": _rate(passed, total),
    }


def fixture_behavior_block(fixture_results: list[Any] | None = None) -> dict[str, Any]:
    """fixture/contract 结果：单独标注为 fixture，绝不进入 model_behavior。"""
    results = list(fixture_results or [])
    total = len(results)
    passed = sum(1 for r in results if getattr(r, "passed", False))
    return {
        "total": total,
        "passed": passed,
        "pass_rate": _rate(passed, total),
        "fixture": True,
        "note": "fixture/contract-test 仅供回归，不构成真实模型通过率",
    }


def build_eval_report(
    calls: list[ModelCall],
    *,
    status: str = STATUS_COMPLETED,
    reason: str = "",
    fixture_results: list[Any] | None = None,
    budget_usd: float | None = None,
) -> dict[str, Any]:
    """组装真实模型评测报告。

    - ``samples`` = 真实网络调用数；
    - ``summary.model_behavior`` 只含真实调用；
    - ``summary.fixture_behavior`` 仅含 fixture（不进入 model_behavior）。
    """
    samples = sum(1 for c in calls if c.network_call)
    total_token = sum(c.token_count for c in calls)
    total_cost = round(sum(c.cost for c in calls), 6)
    return {
        "status": status,
        "reason": reason,
        "samples": samples,
        "budget_usd": budget_usd,
        "generated_at": _now_iso(),
        "summary": {
            "model_behavior": model_behavior_block(calls),
            "fixture_behavior": fixture_behavior_block(fixture_results),
        },
        "totals": {
            "token_count": total_token,
            "cost": total_cost,
            "latency": round(sum(c.latency for c in calls), 4),
            "retries": sum(c.retry_count for c in calls),
        },
        "calls": [c.to_dict() for c in calls],
    }


# ---------------------------------------------------------------------------
# 真实评测执行
# ---------------------------------------------------------------------------
def _call_once(cfg: ModelEvalConfig, caller: ClientFn, sample: str, sample_id: str) -> ModelCall:
    """执行一次带重试的真实调用并记录元数据。"""
    start = time.monotonic()
    retries = 0
    while True:
        try:
            result = caller(sample, cfg)
            latency = round(time.monotonic() - start, 4)
            usage = result.get("usage") or {}
            pt = int(usage.get("prompt_tokens", 0) or 0)
            ct = int(usage.get("completion_tokens", 0) or 0)
            tokens = pt + ct
            cost = estimate_cost(tokens, cfg.rate_usd_per_1k)
            text = result.get("text", "")
            return ModelCall(
                provider=cfg.base_host,
                model_version=cfg.model_version,
                network_call=True,
                token_count=tokens,
                prompt_token_count=pt,
                completion_token_count=ct,
                cost=cost,
                latency=latency,
                retry_count=retries,
                status=CALL_OK,
                trace=f"real_model_call ok: {text[:80]!r}",
                sample_id=sample_id,
                prompt_hash=_prompt_hash(sample),
            )
        except Exception as exc:  # 网络/解析/HTTP 错误：重试后仍失败则记录 error
            retries += 1
            if retries > cfg.max_retries:
                latency = round(time.monotonic() - start, 4)
                return ModelCall(
                    provider=cfg.base_host,
                    model_version=cfg.model_version,
                    network_call=True,
                    retry_count=retries,
                    status=CALL_ERROR,
                    trace=f"real_model_call error after {retries} retries: {type(exc).__name__}: {exc}",
                    sample_id=sample_id,
                    prompt_hash=_prompt_hash(sample),
                    latency=latency,
                )
            time.sleep(0.4 * retries)


def run_model_eval(
    samples: list[str],
    *,
    client: ClientFn | None = None,
    config: ModelEvalConfig | None = None,
    budget_usd: float | None = None,
    max_calls: int | None = None,
    fixture_results: list[Any] | None = None,
) -> dict[str, Any]:
    """手动/定时真实评测 job。

    - 无凭据（``AIPD_MODEL_API_KEY``/``AIPD_MODEL_BASE_URL`` 缺失）-> HOLD，
      报告 0 个样本，绝不伪造；
    - 有凭据 -> 真实调用并记录 provider/model/token/费用/延迟/重试/trace；
    - ``budget_usd``/``max_calls`` 为预算与调用上限：超限即停止。
    """
    cfg = config or load_model_eval_config()
    if budget_usd is not None:
        cfg.budget_usd = budget_usd
    if max_calls is not None:
        cfg.max_calls = max_calls

    if not cfg.configured:
        return build_eval_report(
            [],
            status=STATUS_HOLD,
            reason="no_credentials: AIPD_MODEL_API_KEY/AIPD_MODEL_BASE_URL 未配置，"
                   "真实模型评测 HOLD（0 样本），绝不使用 fixture 代替",
            fixture_results=fixture_results,
            budget_usd=cfg.budget_usd,
        )

    caller = client or _default_http_client(cfg)
    calls: list[ModelCall] = []
    total_cost = 0.0
    for idx, sample in enumerate(samples):
        if cfg.max_calls is not None and len(calls) >= cfg.max_calls:
            break
        call = _call_once(cfg, caller, sample, str(idx))
        calls.append(call)
        total_cost += call.cost
        if cfg.budget_usd is not None and total_cost > cfg.budget_usd:
            reason = f"budget_exceeded: spent {total_cost:.4f} > {cfg.budget_usd:.4f} USD"
            return build_eval_report(
                calls, status=STATUS_HOLD, reason=reason,
                fixture_results=fixture_results, budget_usd=cfg.budget_usd,
            )
    return build_eval_report(
        calls, status=STATUS_COMPLETED, fixture_results=fixture_results,
        budget_usd=cfg.budget_usd,
    )


class ModelEvalJob:
    """可手动/定时触发的真实评测 job：带预算上限与凭据保护。"""

    def __init__(
        self,
        config: ModelEvalConfig | None = None,
        budget_usd: float | None = None,
        max_calls: int | None = None,
        client: ClientFn | None = None,
    ) -> None:
        self.config = config or load_model_eval_config()
        self.budget_usd = budget_usd
        self.max_calls = max_calls
        self.client = client
        self.last_result: dict[str, Any] = {}

    def run(self, samples: list[str], fixture_results: list[Any] | None = None) -> dict[str, Any]:
        """执行本 job；返回报告并保存到 ``last_result``。"""
        self.last_result = run_model_eval(
            samples,
            client=self.client,
            config=self.config,
            budget_usd=self.budget_usd,
            max_calls=self.max_calls,
            fixture_results=fixture_results,
        )
        return self.last_result


__all__ = [
    "STATUS_HOLD", "STATUS_COMPLETED", "CALL_OK", "CALL_ERROR",
    "DEFAULT_USD_PER_1K_TOKENS", "DEFAULT_MAX_RETRIES", "DEFAULT_TIMEOUT_SECONDS",
    "ModelEvalConfig", "load_model_eval_config",
    "ModelCall", "estimate_cost",
    "build_eval_report", "model_behavior_block", "fixture_behavior_block",
    "run_model_eval", "ModelEvalJob",
]
