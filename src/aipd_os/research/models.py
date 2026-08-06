"""研究链数据模型：摘要/全文区分、统一引用格式、研究发现状态。

诚实建模原则：
  - ``abstract`` 与 ``full_text`` 是两种不同的内容形态，绝不混为一谈；
  - 只有真正发生下载并解析成功时，``full_text`` 才被标记为 ``obtainable=True``；
  - 检索失败 / 网络不可达时，finding 状态保持 ``not_verified``，不产生确定性结论。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

# 发现状态：verified=已获取并解析；not_verified=未能获取/未验证；external_pending=等外部回填
STATUS_VERIFIED = "verified"
STATUS_NOT_VERIFIED = "not_verified"
STATUS_EXTERNAL_PENDING = "external_pending"


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
    """研究文档：明确区分摘要与全文。"""

    citation: Citation
    abstract: Optional[Abstract] = None
    full_text: Optional[FullText] = None
    sha256: Optional[str] = None

    @property
    def has_full_text(self) -> bool:
        return self.full_text is not None and self.full_text.obtainable

    @property
    def status(self) -> str:
        if self.has_full_text:
            return STATUS_VERIFIED
        if self.abstract is not None:
            return STATUS_NOT_VERIFIED
        return STATUS_NOT_VERIFIED


@dataclass
class ResearchFinding:
    """一条研究结论。失败时 status 保持 not_verified 且不含确定性结论。"""

    key: str
    value: Any
    status: str = STATUS_NOT_VERIFIED
    is_fact: bool = True
    confidence: float = 0.5
    citations: List[Citation] = field(default_factory=list)
    notes: Optional[str] = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0,1]")

    def add_citation(self, citation: Citation) -> None:
        self.citations.append(citation)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "status": self.status,
            "is_fact": self.is_fact,
            "confidence": self.confidence,
            "citations": [c.to_dict() for c in self.citations],
            "notes": self.notes,
        }


__all__ = [
    "STATUS_VERIFIED",
    "STATUS_NOT_VERIFIED",
    "STATUS_EXTERNAL_PENDING",
    "utc_now_iso",
    "Citation",
    "Abstract",
    "FullText",
    "Document",
    "ResearchFinding",
]