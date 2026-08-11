"""研究链数据模型：摘要/全文区分、统一引用格式、研究发现状态。

诚实建模原则：
  - ``abstract`` 与 ``full_text`` 是两种不同的内容形态，绝不混为一谈；
  - 只有真正发生下载并解析成功时，``full_text`` 才被标记为 ``obtainable=True``；
  - 检索失败 / 网络不可达时，finding 状态保持 ``not_verified``，不产生确定性结论。

v5.7 语义收敛（Commit 7A）：
  - **retrieval_status**（检索状态）与 **epistemic_status**（内容认知状态）彻底分开。
    ``Document.status`` / ``ResearchFinding.status`` 保留为「检索状态」兼容名
    （verified=已获取并解析），绝不等于「命题为真」。
  - 回写 Product Truth 时写保守认知状态：外部来源（论文/报告）默认 ``E``
    （Reliable external evidence，外部来源最多 E），绝不自动 ``V``（verified）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

# 发现状态：verified=已获取并解析；not_verified=未能获取/未验证；external_pending=等外部回填
STATUS_VERIFIED = "verified"
STATUS_NOT_VERIFIED = "not_verified"
STATUS_EXTERNAL_PENDING = "external_pending"

# 检索状态（retrieval domain，Document 级别）：
#   文档「拿到了什么」——与「内容是否为真」无关。
RETRIEVAL_NOT_RETRIEVED = "not_retrieved"
RETRIEVAL_ABSTRACT_ONLY = "abstract_only"
RETRIEVAL_FULLTEXT_RETRIEVED = "fulltext_retrieved"
RETRIEVAL_PARSE_FAILED = "parse_failed"

# 认知状态（epistemic domain，写事实时使用）：
#   E=Reliable external evidence（外部来源最多 E）；U=Unknown / 未验证；
#   V=verified 仅当显式工程/所有者确认（绝不自动）。
EPISTEMIC_EXTERNAL_EVIDENCE = "E"
EPISTEMIC_UNKNOWN = "U"
EPISTEMIC_VERIFIED = "V"


def default_epistemic_status(finding: ResearchFinding) -> str:
    """保守认知状态：无任何外部证据 → U（unknown）；有外部证据 → E（external evidence）。

    绝不自动返回 V（verified）——外部来源（论文/报告/供应商数据）到达后最多是
    可靠外部证据，命题是否为真需另行确认。
    """
    if not finding.citations:
        return EPISTEMIC_UNKNOWN
    return EPISTEMIC_EXTERNAL_EVIDENCE


def utc_now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


@dataclass
class Citation:
    """统一引用格式：来源 / 时间 / URL / 置信度。"""

    source: str
    title: str
    published_at: Optional[str] = None
    url: Optional[str] = None
    confidence: float = 0.5
    authors: List[str] = field(default_factory=list)
    identifier: Optional[str] = None
    kind: str = "unknown"  # standard / patent / competitor / paper / attachment
    accessed_at: Optional[str] = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0,1]")
        if not self.source:
            raise ValueError("source is required")
        if not self.title:
            raise ValueError("title is required")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "title": self.title,
            "published_at": self.published_at,
            "url": self.url,
            "confidence": self.confidence,
            "authors": list(self.authors),
            "identifier": self.identifier,
            "kind": self.kind,
            "accessed_at": self.accessed_at or utc_now_iso(),
        }


@dataclass
class Abstract:
    """摘要：仅包含标题/摘要元数据，不含可解析的全文。"""

    title: str
    snippet: Optional[str] = None
    citation: Optional[Citation] = None

    @property
    def obtainable(self) -> bool:
        return False


@dataclass
class FullText:
    """全文：仅当发生真实下载并解析成功时，obtainable 才为 True。"""

    title: str
    text: str
    citation: Optional[Citation] = None
    format: str = "txt"  # pdf / txt / ...

    @property
    def obtainable(self) -> bool:
        return bool(self.text.strip())


@dataclass
class Document:
    """研究文档：明确区分摘要与全文。

    ``status`` 保留为检索状态兼容名；新增 ``retrieval_status`` 提供细粒度
    检索域（not_retrieved / abstract_only / fulltext_retrieved / parse_failed）。
    ``status`` 或 ``retrieval_status`` 都只是「文档拿到了什么」，不等于
    「内容认知状态」（epistemic）——后者由回写层（write_finding）保守决定。
    """

    citation: Citation
    abstract: Optional[Abstract] = None
    full_text: Optional[FullText] = None
    sha256: Optional[str] = None

    @property
    def has_full_text(self) -> bool:
        return self.full_text is not None and self.full_text.obtainable

    @property
    def retrieval_status(self) -> str:
        """检索状态（细粒度）：拿到了什么。"""
        if self.full_text is not None and self.full_text.obtainable:
            return RETRIEVAL_FULLTEXT_RETRIEVED
        if self.full_text is not None:
            # 有 full_text 对象但无内容 → 解析失败 / 空正文
            return RETRIEVAL_PARSE_FAILED
        if self.abstract is not None:
            return RETRIEVAL_ABSTRACT_ONLY
        return RETRIEVAL_NOT_RETRIEVED

    @property
    def status(self) -> str:
        """检索状态兼容名：fulltext 已获取并解析 → verified；否则 not_verified。"""
        if self.has_full_text:
            return STATUS_VERIFIED
        return STATUS_NOT_VERIFIED


@dataclass
class ResearchFinding:
    """一条研究结论。失败时 status 保持 not_verified 且不含确定性结论。

    - ``status``：检索状态兼容名（verified=已获取并解析，不是命题为真）；
    - ``retrieval_status``：显式检索域（可选）；
    - ``epistemic_status``：内容认知状态（写事实时使用；缺省由
      :func:`default_epistemic_status` 保守推导，绝不自动 verified）。
    """

    key: str
    value: Any
    status: str = STATUS_NOT_VERIFIED
    is_fact: bool = True
    confidence: float = 0.5
    citations: List[Citation] = field(default_factory=list)
    notes: Optional[str] = None
    retrieval_status: Optional[str] = None
    epistemic_status: Optional[str] = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0,1]")

    def add_citation(self, citation: Citation) -> None:
        self.citations.append(citation)

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "key": self.key,
            "value": self.value,
            "status": self.status,
            "is_fact": self.is_fact,
            "confidence": self.confidence,
            "citations": [c.to_dict() for c in self.citations],
            "notes": self.notes,
        }
        if self.retrieval_status is not None:
            d["retrieval_status"] = self.retrieval_status
        if self.epistemic_status is not None:
            d["epistemic_status"] = self.epistemic_status
        return d


__all__ = [
    "STATUS_VERIFIED",
    "STATUS_NOT_VERIFIED",
    "STATUS_EXTERNAL_PENDING",
    "RETRIEVAL_NOT_RETRIEVED",
    "RETRIEVAL_ABSTRACT_ONLY",
    "RETRIEVAL_FULLTEXT_RETRIEVED",
    "RETRIEVAL_PARSE_FAILED",
    "EPISTEMIC_EXTERNAL_EVIDENCE",
    "EPISTEMIC_UNKNOWN",
    "EPISTEMIC_VERIFIED",
    "default_epistemic_status",
    "utc_now_iso",
    "Citation",
    "Abstract",
    "FullText",
    "Document",
    "ResearchFinding",
]