"""配置驱动的 LLM IdeaDecompositionProvider（v5.9.2 N-1）。

继承 :class:`aipd_os.idea.decomposer.IdeaDecompositionProvider`，用通用
:class:`aipd_os.llm.client.LlmClient` 把 Raw Idea 分解为
:class:`aipd_os.idea.decomposer.StructuredCandidate`（candidate claims，
默认 epistemic_status=A，绝不产出最终产品事实 V）。

诚实原则：LLM 调用失败 / 响应无法解析 → 抛
:class:`aipd_os.idea.decomposer.IdeaDecompositionUnavailable`
（CAPABILITY_UNAVAILABLE），绝不伪造结构化 Idea。
"""
from __future__ import annotations

import json
from typing import Any

from aipd_os.idea.claims import CLAIM_TYPES
from aipd_os.idea.decomposer import (
    IdeaDecompositionProvider,
    IdeaDecompositionUnavailable,
    StructuredCandidate,
)
from aipd_os.llm.client import LlmClient

_SYSTEM_BASE = (
    "你是 AIPD 产品想法整理助手。你只输出 JSON，不要输出任何解释、"
    "注释或 JSON 以外的文字。"
)


def _strip_markdown_fence(text: str) -> str:
    """剥离 markdown 代码围栏（```json / ```）与前后空白。"""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def _parse_json_object(raw: str) -> dict[str, Any]:
    """把 LLM 响应解析为 JSON 对象；失败抛 IdeaDecompositionUnavailable。"""
    text = _strip_markdown_fence(raw)
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise IdeaDecompositionUnavailable(
            f"LLM 响应不是合法 JSON（{exc}）; CAPABILITY_UNAVAILABLE") from exc
    if not isinstance(data, dict):
        raise IdeaDecompositionUnavailable(
            "LLM 响应必须是 JSON 对象; CAPABILITY_UNAVAILABLE")
    return data


class LlmIdeaDecompositionProvider(IdeaDecompositionProvider):
    """OpenAI 兼容 LLM 驱动的 Idea Decomposition Provider。"""

    name = "llm-openai-compatible"

    def __init__(self, client: LlmClient) -> None:
        self._client = client

    def available(self) -> bool:
        """已配置（endpoint + api_key 齐备）才具备真实分解能力。"""
        return self._client.configured

    def decompose(
        self,
        raw_input: str,
        idea_context: dict[str, Any] | None = None,
    ) -> StructuredCandidate:
        if not self.available():
            raise IdeaDecompositionUnavailable(
                "LLM idea decomposition provider 未配置（缺 endpoint/api_key）；"
                "external_dependency (CAPABILITY_UNAVAILABLE)")

        claim_types = sorted(CLAIM_TYPES)
        stage_prompt = (
            "当前阶段：把原始想法（Raw Idea）分解为结构化候选。\n"
            "输出一个 JSON 对象，字段（满足 STRUCTURED_CANDIDATE_SCHEMA）：\n"
            "- title（字符串，必填，标题）\n"
            "- goal（字符串，目标）\n"
            "- problem（字符串，要解决的问题）\n"
            "- target_user（字符串，目标用户）\n"
            "- desired_outcome（字符串，期望结果）\n"
            "- constraints（字符串数组，约束）\n"
            f"- claims（对象数组，每项 {{claim_type, statement}}；claim_type 必须"
            f"取自 {claim_types}，statement 为命题陈述；至少 1 项）\n"
            "不要输出任何 JSON 以外的内容。"
        )
        system = _SYSTEM_BASE + "\n\n" + stage_prompt
        user = json.dumps(
            {"raw_input": raw_input, "idea_context": idea_context or {}},
            ensure_ascii=False)
        raw = self._client.complete([
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ])
        try:
            data = _parse_json_object(raw)
            candidate = StructuredCandidate.from_dict(data)
        except IdeaDecompositionUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001 - 映射失败统一诚实上抛
            raise IdeaDecompositionUnavailable(
                f"LLM 响应无法解析为 StructuredCandidate（{exc}）; "
                "CAPABILITY_UNAVAILABLE") from exc
        candidate.source = "llm_idea_decomposer"
        return candidate


__all__ = [
    "LlmIdeaDecompositionProvider",
]
