"""Research provider 确定性夹具（v5.8 Commit 13）。

仅测试路径使用：生产默认无 research provider（external_dependency，诚实降级）；
测试通过 :class:`FakeResearchProvider` 显式注入，验证 Claim→Evidence→Relation 链。

EPISTEMIC_NOTE: fixture 数据仅用于测试系统行为，不代表真实研究结论。
"""
from __future__ import annotations

from typing import Any

from aipd_os.idea import ResearchProvider

FAKE_SUPPORT_RESULT = {
    "sources": [
        {"title": "Fake Paper: adherence in home-based rehab",
         "url": "https://example.invalid/fake-adherence",
         "identifier": "fake-paper-1"},
    ],
    "evidence_relation": "supports",
    "provider": "fake-research",
    "reasoning_summary": "fixture: supports claim (non-medical, test only)",
    "EPISTEMIC_NOTE": "FIXTURE ONLY: 非真实研究结论；仅用于测试系统行为。",
}

FAKE_CONTRADICT_RESULT = {
    "sources": [
        {"title": "Fake Paper: visual feedback ineffective",
         "url": "https://example.invalid/fake-contr",
         "identifier": "fake-paper-2"},
    ],
    "evidence_relation": "contradicts",
    "provider": "fake-research",
    "reasoning_summary": "fixture: contradicts claim (non-medical, test only)",
    "EPISTEMIC_NOTE": "FIXTURE ONLY: 非真实研究结论；仅用于测试系统行为。",
}

FAKE_INCONCLUSIVE_RESULT = {
    "sources": [
        {"title": "Fake Paper: mixed evidence",
         "url": "https://example.invalid/fake-mixed",
         "identifier": "fake-paper-3"},
    ],
    "evidence_relation": "inconclusive",
    "provider": "fake-research",
    "reasoning_summary": "fixture: inconclusive (non-medical, test only)",
    "EPISTEMIC_NOTE": "FIXTURE ONLY: 非真实研究结论；仅用于测试系统行为。",
}


class FakeResearchProvider(ResearchProvider):
    """确定性研究 provider（仅测试路径）。"""

    name = "fake-research"

    def __init__(self, capability_id: str = "research.academic_search",
                 result: dict[str, Any] | None = None) -> None:
        self.capability_id = capability_id
        self._result = result or FAKE_SUPPORT_RESULT
        self.execute_count = 0

    def available(self) -> bool:
        return True

    def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        self.execute_count += 1
        data = dict(self._result)
        data.pop("EPISTEMIC_NOTE", None)
        return data


class EmptyFakeResearchProvider(FakeResearchProvider):
    """返回无 sources 的 provider（用于「无结果 → 不写 evidence」测试）。"""

    def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        self.execute_count += 1
        return {"sources": [], "provider": "fake-research",
                "reasoning_summary": "no results (fixture)"}


__all__ = [
    "FAKE_SUPPORT_RESULT",
    "FAKE_CONTRADICT_RESULT",
    "FAKE_INCONCLUSIVE_RESULT",
    "FakeResearchProvider",
    "EmptyFakeResearchProvider",
]
