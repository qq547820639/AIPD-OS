"""检索接口（契约 + 显式测试夹具 + 真实网络桩）。

三类检索：标准（StandardsRetriever）、专利（PatentRetriever）、竞品（CompetitorRetriever）。

v5.7 语义收敛（Commit 7D）：
  - **生产默认不再返回测试数据**。`StandardsRetriever()` / `PatentRetriever()` /
    `CompetitorRetriever()` 未注入真实 backend 时默认 ``external_dependency``
    （``available()=False``，search 返回空），绝不把本地确定性数据当生产检索结果。
  - 确定性测试数据/夹具移到 ``tests/fixtures/research/``，通过显式的
    ``TestRetriever`` / ``FixtureRetriever`` 注入测试路径。
  - 真实网络桩（``_NetworkRetriever``）在未配置凭据/网络不可达时显式返回
    ``not_verified``，绝不伪造在线检索结果。

诚实建模：
  - 本地测试实现返回确定性引用，供离线验证与集成测试（仅测试路径）；
  - 真实网络桩在未配置凭据/网络不可达时显式返回 ``not_verified``，绝不伪造
    在线检索结果（``external_dependency``）。
"""

from __future__ import annotations

import abc
from typing import List, Optional

from .models import Abstract, Citation, Document, STATUS_NOT_VERIFIED


class Retriever(abc.ABC):
    """检索接口统一契约。"""

    @abc.abstractmethod
    def search(self, query: str, limit: int = 5) -> List[Document]:
        """按查询返回文档列表；失败/不可用时返回 status=not_verified 的空文档列表。"""

    @abc.abstractmethod
    def available(self) -> bool:
        """具备真实检索能力（False 表示 external_dependency）。"""


class TestRetriever(Retriever):
    """显式测试/夹具检索器：返回确定性引用（仅摘要，无全文下载）。

    **不是生产默认路径**：生产 ``StandardsRetriever`` 等默认 external_dependency，
    只有测试显式注入本夹具才返回确定性数据。
    """

    def __init__(self, data: dict) -> None:
        self._data = data

    def available(self) -> bool:
        return True

    def search(self, query: str, limit: int = 5) -> List[Document]:
        hits = []
        for known, citations in self._data.items():
            if known.lower() in query.lower():
                hits.extend(citations)
        docs = []
        for c in hits[:limit]:
            abstract = Abstract(title=c.title, snippet=f"Abstract of {c.title}", citation=c)
            docs.append(Document(citation=c, abstract=abstract))
        return docs


class _UnavailableRetriever(Retriever):
    """生产默认：无真实 provider → external_dependency（available()=False）。"""

    def __init__(self, scope: str) -> None:
        self._scope = scope

    def available(self) -> bool:
        return False

    def search(self, query: str, limit: int = 5) -> List[Document]:
        return []


class _NetworkRetriever(Retriever):
    """真实网络桩：未配置凭据时返回空结果，标明 not_verified。"""

    def __init__(self, api_key: Optional[str] = None) -> None:
        self._api_key = api_key

    def available(self) -> bool:
        return bool(self._api_key)

    def search(self, query: str, limit: int = 5) -> List[Document]:
        # 无凭据/网络不可达：诚实返回空列表（调用方保持 not_verified），不伪造结果。
        if not self.available():
            return []
        raise NotImplementedError(
            "online retrieval requires a real search backend (external_dependency)."
        )


class StandardsRetriever(Retriever):
    """标准检索：生产默认 external_dependency；可注入真实网络桩或测试夹具。"""

    def __init__(self, backend: Optional[Retriever] = None) -> None:
        self._backend = backend or _UnavailableRetriever("standards")

    def available(self) -> bool:
        return self._backend.available()

    def search(self, query: str, limit: int = 5) -> List[Document]:
        return self._backend.search(query, limit)


class PatentRetriever(Retriever):
    """专利检索：生产默认 external_dependency。"""

    def __init__(self, backend: Optional[Retriever] = None) -> None:
        self._backend = backend or _UnavailableRetriever("patents")

    def available(self) -> bool:
        return self._backend.available()

    def search(self, query: str, limit: int = 5) -> List[Document]:
        return self._backend.search(query, limit)


class CompetitorRetriever(Retriever):
    """竞品情报检索：生产默认 external_dependency。"""

    def __init__(self, backend: Optional[Retriever] = None) -> None:
        self._backend = backend or _UnavailableRetriever("competitors")

    def available(self) -> bool:
        return self._backend.available()

    def search(self, query: str, limit: int = 5) -> List[Document]:
        return self._backend.search(query, limit)


# 网络桩工厂：未配置密钥时的诚实降级实现
def network_standards(api_key: Optional[str] = None) -> StandardsRetriever:
    return StandardsRetriever(backend=_NetworkRetriever(api_key))


def network_patents(api_key: Optional[str] = None) -> PatentRetriever:
    return PatentRetriever(backend=_NetworkRetriever(api_key))


def network_competitors(api_key: Optional[str] = None) -> CompetitorRetriever:
    return CompetitorRetriever(backend=_NetworkRetriever(api_key))


__all__ = [
    "Retriever",
    "TestRetriever",
    "StandardsRetriever",
    "PatentRetriever",
    "CompetitorRetriever",
    "network_standards",
    "network_patents",
    "network_competitors",
]
