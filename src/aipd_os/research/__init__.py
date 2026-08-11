"""研究证据链（P1-2）：摄入净化、摘要/全文区分、全文获取、检索、可信度、回写与过期。

公开 API 一览：
  - 模型：Citation / Abstract / FullText / Document / ResearchFinding；
  - 附件摄入净化：ingest_attachment / sanitize_text / sha256_of；
  - 全文获取契约：DocumentFetcher / ContractFetcher / HttpDocumentFetcher；
  - 检索接口：StandardsRetriever / PatentRetriever / CompetitorRetriever；
  - 可信度与冲突：source_metadata / timeliness / confidence_tag / resolve_conflicts；
  - 回写与过期：ResearchBackend / run_research_chain / mark_evidence_expired。

在线检索/下载能力为 ``external_dependency``：未配置凭据时诚实返回 not_verified，
绝不伪造成功结果。
"""

from __future__ import annotations

from .credibility import (
    SOURCE_CREDIBILITY,
    SOURCE_METADATA,
    confidence_tag,
    resolve_conflicts,
    score_evidence,
    separate_facts_from_assumptions,
    source_credibility,
    source_metadata,
    timeliness,
    time_decay,
)
from .documents import (
    ALLOWED_EXTENSIONS,
    DEFAULT_MAX_BYTES,
    AttachmentTooLarge,
    DisallowedExtension,
    IngestionError,
    ingest_attachment,
    sanitize_text,
    sha256_of,
)
from .expiry import STALE_STATUS, expire_evidence_list, mark_evidence_expired
from .fulltext import (
    ACCESS_BLOCKED,
    ACCESS_OPEN,
    ACCESS_RESTRICTED,
    TEXT_TYPE_ABSTRACT,
    TEXT_TYPE_FULL_TEXT,
    TEXT_TYPE_METADATA,
    TEXT_TYPE_OCR_TEXT,
    TEXT_TYPE_QUOTED_SNIPPET,
    TEXT_TYPES,
    Conclusion,
    DelegateProvider,
    ExternalProvider,
    FullTextCache,
    Provider,
    TextRecord,
    classify_access,
    classify_text,
    competitor_provider,
    deduplicate_texts,
    default_expires_at,
    fetch_fulltext,
    is_open_access_url,
    patent_provider,
    refetch_strategy,
    regulation_provider,
    standard_provider,
    tag_text,
)
from .fetchers import (
    DOCUMENT_PARSERS,
    ContractFetcher,
    DocumentFetcher,
    HttpDocumentFetcher,
    parse_pdf,
    parse_txt,
)
from .models import (
    EPISTEMIC_EXTERNAL_EVIDENCE,
    EPISTEMIC_UNKNOWN,
    EPISTEMIC_VERIFIED,
    RETRIEVAL_ABSTRACT_ONLY,
    RETRIEVAL_FULLTEXT_RETRIEVED,
    RETRIEVAL_NOT_RETRIEVED,
    RETRIEVAL_PARSE_FAILED,
    STATUS_EXTERNAL_PENDING,
    STATUS_NOT_VERIFIED,
    STATUS_VERIFIED,
    Abstract,
    Citation,
    Document,
    FullText,
    ResearchFinding,
    default_epistemic_status,
    utc_now_iso,
)
from .retrieval import (
    CompetitorRetriever,
    PatentRetriever,
    Retriever,
    StandardsRetriever,
    TestRetriever,
    network_competitors,
    network_patents,
    network_standards,
)
from .writeback import ResearchBackend, run_research_chain

__all__ = [
    # 模型
    "Citation", "Abstract", "FullText", "Document", "ResearchFinding",
    "STATUS_VERIFIED", "STATUS_NOT_VERIFIED", "STATUS_EXTERNAL_PENDING", "utc_now_iso",
    # 检索/认知状态（v5.7 Commit 7A）
    "RETRIEVAL_NOT_RETRIEVED", "RETRIEVAL_ABSTRACT_ONLY",
    "RETRIEVAL_FULLTEXT_RETRIEVED", "RETRIEVAL_PARSE_FAILED",
    "EPISTEMIC_EXTERNAL_EVIDENCE", "EPISTEMIC_UNKNOWN", "EPISTEMIC_VERIFIED",
    "default_epistemic_status",
    # 摄入净化
    "ingest_attachment", "sanitize_text", "sha256_of",
    "ALLOWED_EXTENSIONS", "DEFAULT_MAX_BYTES",
    "IngestionError", "AttachmentTooLarge", "DisallowedExtension",
    # 全文获取
    "DocumentFetcher", "ContractFetcher", "HttpDocumentFetcher", "DOCUMENT_PARSERS",
    "parse_txt", "parse_pdf",
    # 检索
    "Retriever", "TestRetriever", "StandardsRetriever", "PatentRetriever", "CompetitorRetriever",
    "network_standards", "network_patents", "network_competitors",
    # 可信度与冲突
    "SOURCE_CREDIBILITY", "SOURCE_METADATA", "source_credibility", "source_metadata",
    "time_decay", "timeliness", "confidence_tag", "score_evidence",
    "separate_facts_from_assumptions", "resolve_conflicts",
    # 回写与过期
    "ResearchBackend", "run_research_chain", "mark_evidence_expired",
    "expire_evidence_list", "STALE_STATUS",
    # 文本类型 / 全文 / 结论 / Provider
    "TEXT_TYPE_METADATA", "TEXT_TYPE_ABSTRACT", "TEXT_TYPE_FULL_TEXT",
    "TEXT_TYPE_OCR_TEXT", "TEXT_TYPE_QUOTED_SNIPPET", "TEXT_TYPES",
    "ACCESS_OPEN", "ACCESS_RESTRICTED", "ACCESS_BLOCKED",
    "classify_text", "tag_text", "TextRecord",
    "is_open_access_url", "classify_access",
    "FullTextCache", "deduplicate_texts", "fetch_fulltext",
    "default_expires_at", "refetch_strategy", "Conclusion",
    "Provider", "ExternalProvider", "DelegateProvider",
    "standard_provider", "regulation_provider", "patent_provider", "competitor_provider",
]