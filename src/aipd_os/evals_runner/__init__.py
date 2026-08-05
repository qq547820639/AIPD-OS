"""行为评估运行器。

将静态评估描述转化为可运行的 agent 行为评估：确定性契约由实际代码驱动，
对话契约由假/真 CompletionProvider 驱动，产出带版本化的评估报告。
"""

from __future__ import annotations

from aipd_os.evals_runner.completion import (
    CompletionProvider,
    EnvCompletionProvider,
    ModelNotConfiguredError,
    RecordedCompletionProvider,
)
from aipd_os.evals_runner.registry import BEHAVIOR_CONTRACTS, Case, load_cases
from aipd_os.evals_runner.runner import EvalResult, EvalRunner
from aipd_os.evals_runner.scoring import score_response, semantic_check

__all__ = [
    "CompletionProvider",
    "EnvCompletionProvider",
    "ModelNotConfiguredError",
    "RecordedCompletionProvider",
    "BEHAVIOR_CONTRACTS",
    "Case",
    "load_cases",
    "EvalResult",
    "EvalRunner",
    "score_response",
    "semantic_check",
]
