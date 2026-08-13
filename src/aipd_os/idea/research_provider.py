"""Research Provider contract（v5.8 Commit 13 / v5.8.1 Commit 5-6）。

本模块只定义研究能力的**纯契约面**（idea 数据/契约层，不依赖 execution）。

能力按真实研究语义拆分（上层 Domain 依赖 capability 不依赖具体 provider 名）：
  - research.academic_search  —— 学术检索（Search）
  - research.fulltext         —— 全文获取
  - research.related_work     —— 相关工作检索
  - research.novelty_check    —— 新颖性检查
  - research.idea_spark       —— 灵感/想法生成
  - research.asset_extract    —— 资产抽取
  - evidence.assess_relation  —— 关系评估（Assessment，v5.8.1 Commit 5）

v5.8.1 Commit 5（Search ≠ Assessment）：Search provider 只输出 sources，
**不承担关系评估**；检索命中 ≠ 支持 —— 无显式评估时 relation 默认
``inconclusive`` + ``pending``；每 source 单独建 EvidenceRelation。

无真实后端时经 :class:`UnavailableResearchProvider` 诚实标注
external_dependency，不伪造 integration。

执行侧（把 provider 注册进 AdapterRegistry 的 ``ResearchToolAdapter``，以及做
Claim evidence gap → 路由 → canonical evidence 去重落库 → per-source
EvidenceRelation 的 ``ResearchIntegration``）已下沉至
``aipd_os.execution.research_integration`` —— idea 层不再依赖 execution 层。
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any

# 研究能力集合（注册骨架）
RESEARCH_CAPABILITIES: tuple = (
    "research.academic_search",
    "research.fulltext",
    "research.related_work",
    "research.novelty_check",
    "research.idea_spark",
    "research.asset_extract",
    # v5.8.1 Commit 5：Search ≠ Assessment 拆层 —— 关系评估是独立 capability。
    "evidence.assess_relation",
)

# relation_type 分类 key（provider 可在结果中显式声明；legacy）
RELATION_KEY = "evidence_relation"

# v5.8.1 Commit 5：evidence↔claim 关系评估能力（Assessment，独立于 Search）
EVIDENCE_ASSESS_RELATION_CAPABILITY = "evidence.assess_relation"


class ResearchCapabilityUnavailable(RuntimeError):
    """研究能力不可用（external_dependency；不写 evidence，诚实降级）。"""


class ResearchProvider(abc.ABC):
    """研究 provider 契约（单能力 provider）。

    v5.8.1 Commit 5（Search ≠ Assessment 拆层）：Search provider 只负责
    **检索**（输出 sources），**不承担关系评估**。evidence↔claim 的关系判定由
    独立 capability ``evidence.assess_relation`` 提供（:meth:`assess_relation`）；
    本轮定义 contract + CAPABILITY_UNAVAILABLE 路径，完整实现放后续 Commit。
    """

    #: provider 唯一名称（子类覆盖）
    name: str = "unnamed"
    #: 单能力 id（如 research.academic_search）
    capability_id: str = ""

    @abc.abstractmethod
    def available(self) -> bool:
        """是否具备真实能力（False 表示 external_dependency）。"""

    @abc.abstractmethod
    def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """执行一次研究调用，返回规范化 payload。"""

    def assess_relation(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """【Assessment capability】评估 evidence↔claim 关系（独立 capability）。

        Search provider 默认不承担评估 → 诚实抛
        :class:`ResearchCapabilityUnavailable`（external_dependency）。
        实现 assess_relation 的 provider 应注册 capability
        ``evidence.assess_relation``。
        """
        raise ResearchCapabilityUnavailable(
            f"evidence assess_relation capability unavailable: provider "
            f"{self.name!r} is a Search provider and does not assess relations "
            "(external_dependency, no fake reasoning)")


class UnavailableResearchProvider(ResearchProvider):
    """无真实后端时的默认实现：available()=False，execute 诚实抛错。"""

    def __init__(self, capability_id: str, reason: str = "") -> None:
        self.capability_id = capability_id
        self.name = f"unavailable:{capability_id}"
        self._reason = reason or (
            f"research capability {capability_id} unavailable (external_dependency)")

    def available(self) -> bool:
        return False

    def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        raise ResearchCapabilityUnavailable(self._reason)


def research_capability_declaration(capability_id: str) -> dict[str, Any]:
    """capability 声明（ProviderRegistry capability_schema 兼容）。"""
    return {
        "id": capability_id,
        "name": capability_id.replace("research.", "").replace("_", " ").title(),
        "domain": "research",
        "category": "retrieval",
        "evidence": {"impl_file": "src/aipd_os/idea/research_provider.py"},
    }


@dataclass
class EvidenceRequest:
    """Claim → 研究能力 的请求（evidence gap 驱动）。"""

    claim_id: str
    tenant_id: str = "default"
    project_id: str = "default"
    capability: str = "research.academic_search"
    gap_reason: str = ""
    inputs: dict[str, Any] = field(default_factory=dict)


__all__ = [
    "RESEARCH_CAPABILITIES",
    "EVIDENCE_ASSESS_RELATION_CAPABILITY",
    "ResearchCapabilityUnavailable",
    "ResearchProvider",
    "UnavailableResearchProvider",
    "research_capability_declaration",
    "EvidenceRequest",
]
