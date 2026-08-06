"""检索接口（契约 + 本地确定性测试服务 + 真实网络桩）。

三类检索：标准（StandardsRetriever）、专利（PatentRetriever）、竞品（CompetitorRetriever）。

诚实建模：
  - 本地测试实现返回确定性引用，供离线验证与集成测试；
  - 真实网络桩在未配置凭据/网络不可达时显式返回 ``not_verified``，绝不伪造
    在线检索结果（``external_dependency``）。
"""

from __future__ import annotations

import abc
from typing import List, Optional

from .models import Abstract, Citation, Document, STATUS_NOT_VERIFIED

# 本地确定性测试数据（键：检索词 -> 引用列表）
_LOCAL_STANDARDS = {
    "quality management": [
        Citation(source="official_standard", title="ISO-9001:2015",
                 published_at="2015-09-15", url="https://www.iso.org/standard/62085.html",
                 confidence=0.95, kind="standard", identifier="ISO-9001:2015"),
    ],
    "pcb design": [
        Citation(source="official_standard", title="IPC-H05K",
                 published_at="2021-01-01", url="https://example.invalid/ipc-h05k",
                 confidence=0.9, kind="standard", identifier="IPC-H05K"),
    ],
}

_LOCAL_PATENTS = {
    "additive manufacturing": [
        Citation(source="patent", title="US-PAT-10404000",
                 published_at="2020-06-16", url="https://patents.example/US10404000",
                 confidence=0.85, kind="patent", identifier="US-PAT-10404000",
                 authors=["Publisher US Patent Office"]),
    ],
}

_LOCAL_COMPETITORS = {
    "thermal management": [
        Citation(source="industry_report", title="Competitor Thermal Report 2024",
                 published_at="2024-03-01", url="https://example.invalid/comp-thermal",
                 confidence=0.7, kind="competitor"),
    ],
}


class Retriever(abc.ABC):
    """检索接口统一契约。"""

    @abc.abstractmethod
    def search(self, query: str, limit: int = 5) -> List[Document]:
        """按查询返回文档列表；失败/不可用时返回 status=not_verified 的空文档列表。"""

    @abc.abstractmethod
    def available(self) -> bool:
        """具备真实检索能力（False 表示 external_dependency）。"""


class _LocalRetriever(Retriever):
    """本地确定性测试服务：返回固定引用（仅摘要，无全文下载）。"""

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
    """标准检索：默认本地确定性服务；可注入真实网络桩。"""

    def __init__(self, backend: Optional[Retriever] = None) -> None:
        self._backend = backend or _LocalRetriever(_LOCAL_STANDARDS)

    def available(self) -> bool:
        return self._backend.available()

    def search(self, query: str, limit: int = 5) -> List[Document]:
        return self._backend.search(query, limit)


class PatentRetriever(Retriever):
    """专利检索。"""

    def __init__(self, backend: Optional[Retriever] = None) -> None:
        self._backend = backend or _LocalRetriever(_LOCAL_PATENTS)

    def available(self) -> bool:
        return self._backend.available()

    def search(self, query: str, limit: int = 5) -> List[Document]:
        return self._backend.search(query, limit)


class CompetitorRetriever(Retriever):
    """竞品情报检索。"""

    def __init__(self, backend: Optional[Retriever] = None) -> None:
        self._backend = backend or _LocalRetriever(_LOCAL_COMPETITORS)

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
    "StandardsRetriever",
    "PatentRetriever",
    "CompetitorRetriever",
    "network_standards",
    "network_patents",
    "network_competitors",
]