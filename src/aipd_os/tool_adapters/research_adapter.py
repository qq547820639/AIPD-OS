"""研究适配器（'research.search_papers'）。

Semantic Scholar Graph API 公开搜索端点**无需 key**；``AIPD_RESEARCH_API_KEY``
用于私有/更高配额调用。配置语义与网络调用语义必须一致（v5.7 Commit 7E）：
  - 配置 key → 真实以 ``x-api-key`` header 发送（key 不是摆设）；
  - 未配置 key → 保守 ``external_dependency``（``available()=False``），
    不在 discover 阶段做网络探测；execute 时诚实写出外部任务包，
    绝不伪造论文检索结果。

任何 HTTP 错误 / 超时 / 解析失败都会转化为 ``external_blocked``
（诚实 NOT_VERIFIED），绝不返回 simulated 占位。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict

from aipd_os.execution.adapter import ToolAdapter, external_blocked_error
from aipd_os.tool_adapters._common import env, meta, token_meta

_API_KEY_ENV = "AIPD_RESEARCH_API_KEY"
_SEMANTIC_SCHOLAR_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
_REQUEST_TIMEOUT_S = 20
_USER_AGENT = "AIPD-OS/1.0 (research adapter)"


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
        """availability = 是否具备真实调用凭据。

        Semantic Scholar 公开端点无需 key，但生产路径保守按
        external_dependency 处理（不在 discover 时做网络探测）。
        配置 key 时 key 会真实用于 ``x-api-key`` header（配置语义==网络语义）。
        """
        return bool(env(_API_KEY_ENV))

    def validate_input(self, input: Dict[str, Any]) -> list:
        errors = []
        if not input.get("query"):
            errors.append("'query' 必填")
        return errors

    def _fetch_semantic_scholar(self, query: str, limit: int) -> dict[str, Any]:
        """真实调用 Semantic Scholar Graph API，返回解析后的 JSON dict。

        HTTP 错误 / 超时 / JSON 解析失败一律抛出 :class:`AdapterError`
        （classification=external_blocked）。
        """
        url = _SEMANTIC_SCHOLAR_URL + "?" + urllib.parse.urlencode({
            "query": query,
            "limit": limit,
            "fields": "title,authors,year,url,abstract",
        })
        headers: Dict[str, str] = {
            "User-Agent": _USER_AGENT,
            "Accept": "application/json",
        }
        api_key = env(_API_KEY_ENV)
        if api_key:
            # 配置语义 == 网络调用语义：key 真实用于请求头（私有/高配额端点）。
            headers["x-api-key"] = api_key
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT_S) as resp:
                raw = resp.read().decode("utf-8")
        except Exception as exc:  # noqa: BLE001 - HTTP/超时/网络错误统一转 external_blocked
            raise external_blocked_error(
                self.capability_id(),
                f"Semantic Scholar 检索失败（HTTP/超时/网络）：{exc}。"
                "请人工在目标库完成检索并把结果（标题/作者/年份/链接/摘要）回填。",
                work_id=None,
            ) from exc
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError) as exc:
            raise external_blocked_error(
                self.capability_id(),
                "Semantic Scholar 返回无法解析的 JSON；请人工检索并回填结果。",
                work_id=None,
            ) from exc

    def execute(self, input: Dict[str, Any]) -> Dict[str, Any]:
        if not self._is_available():
            raise external_blocked_error(
                self.capability_id(),
                "检索论文需要外部研究数据库（Semantic Scholar Graph API 公开搜索"
                "端点无需 key，但本适配器保守要求配置 AIPD_RESEARCH_API_KEY 或由"
                "人工在目标库完成检索并把结果（标题/作者/年份/链接/摘要）回填）。",
                work_id=input.get("work_id"),
            )
        query = input.get("query", "unknown")
        n = int(input.get("n", 3))
        payload = self._fetch_semantic_scholar(query, n)

        data = payload.get("data") or []
        sources = []
        for paper in data[:n]:
            if not isinstance(paper, dict):
                continue
            authors = [a.get("name", "") for a in (paper.get("authors") or [])
                       if isinstance(a, dict) and a.get("name")]
            source: dict[str, Any] = {
                "title": paper.get("title", ""),
                "authors": authors,
                "year": paper.get("year"),
                "url": paper.get("url", ""),
            }
            if paper.get("abstract"):
                source["abstract"] = paper["abstract"]
            sources.append(source)

        result = {
            "sources": sources,
            "query": query,
            "provider": "semantic-scholar",
            "_meta": token_meta(query, cost_per_1k=0.5),
        }
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
