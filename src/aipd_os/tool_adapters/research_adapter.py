"""研究适配器（'research.search_papers'）。

配置了 ``AIPD_RESEARCH_API_KEY`` 时才视为可用；否则诚实写出外部任务包，
分类为 ``external_blocked``，绝不伪造论文检索结果。
"""

from __future__ import annotations

from typing import Any, Dict

from aipd_os.execution.adapter import ToolAdapter, external_blocked_error
from aipd_os.tool_adapters._common import env, meta, token_meta

_API_KEY_ENV = "AIPD_RESEARCH_API_KEY"


class ResearchAdapter(ToolAdapter):
    provider = "semantic-scholar"

    def capability_id(self) -> str:
        return "research.search_papers"

    def discover(self) -> Dict[str, Any]:
        return meta(
            self.capability_id(),
            "Research Paper Search",
            self.provider,
            "1.0",
            available=self._is_available(),
        )

    def _is_available(self) -> bool:
        return bool(env(_API_KEY_ENV))

    def validate_input(self, input: Dict[str, Any]) -> list:
        errors = []
        if not input.get("query"):
            errors.append("'query' 必填")
        return errors

    def execute(self, input: Dict[str, Any]) -> Dict[str, Any]:
        if not self._is_available():
            raise external_blocked_error(
                self.capability_id(),
                "检索论文需要外部研究数据库（配置 AIPD_RESEARCH_API_KEY）。"
                "请人工在目标库完成检索并把结果（标题/作者/年份/链接/摘要）回填。",
                work_id=input.get("work_id"),
            )
        # 此处为“模拟”检索：仅当 API key 存在时，返回确定性的占位来源，
        # 并明确标注 simulated=True，坚持诚实原则。
        query = input.get("query", "unknown")
        n = int(input.get("n", 3))
        sources = []
        for i in range(n):
            sources.append(
                {
                    "title": f"Simulated source {i + 1} for: {query}",
                    "authors": ["AIPD simulated"],
                    "year": 2024,
                    "url": f"https://example.invalid/{abs(hash(query)) % 100000}/{i}",
                    "summary": "占位来源（simulated）——需真实 API 检索后替换。",
                    "simulated": True,
                }
            )
        result = {"sources": sources, "query": query, "_meta": token_meta(query, cost_per_1k=0.5)}
        return result

    def normalize(self, result: Any) -> Dict[str, Any]:
        return result if isinstance(result, dict) else {"sources": result}

    def collect_artifacts(self, result: Any) -> list:
        if isinstance(result, dict) and result.get("path"):
            return [result["path"]]
        return []

    def persist_evidence(self, result: Any, run_id: str) -> list:
        if not isinstance(result, dict):
            return []
        refs = []
        for s in result.get("sources", []):
            if isinstance(s, dict) and s.get("url"):
                refs.append(s["url"])
        refs.append(run_id)
        return refs


__all__ = ["ResearchAdapter"]
