"""Research 检索确定性夹具（v5.7 Commit 7D）。

这些数据**仅用于测试**：生产 ``StandardsRetriever`` / ``PatentRetriever`` /
``CompetitorRetriever`` 默认 external_dependency（available()=False），
绝不把本地确定性数据当生产检索结果。测试通过
:class:`aipd_os.research.retrieval.TestRetriever` 显式注入本夹具。
"""
from __future__ import annotations

from aipd_os.research import Citation
from aipd_os.research.retrieval import TestRetriever

# 本地确定性测试数据（键：检索词 -> 引用列表）
STANDARDS_FIXTURES = {
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

PATENTS_FIXTURES = {
    "additive manufacturing": [
        Citation(source="patent", title="US-PAT-10404000",
                 published_at="2020-06-16", url="https://patents.example/US10404000",
                 confidence=0.85, kind="patent", identifier="US-PAT-10404000",
                 authors=["Publisher US Patent Office"]),
    ],
}

COMPETITORS_FIXTURES = {
    "thermal management": [
        Citation(source="industry_report", title="Competitor Thermal Report 2024",
                 published_at="2024-03-01", url="https://example.invalid/comp-thermal",
                 confidence=0.7, kind="competitor"),
    ],
}


def standards_test_retriever() -> TestRetriever:
    return TestRetriever(STANDARDS_FIXTURES)


def patents_test_retriever() -> TestRetriever:
    return TestRetriever(PATENTS_FIXTURES)


def competitors_test_retriever() -> TestRetriever:
    return TestRetriever(COMPETITORS_FIXTURES)
