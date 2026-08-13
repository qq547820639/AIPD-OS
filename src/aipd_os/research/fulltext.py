"""全文与文本类型：区分文本形态、合法全文获取、缓存去重、版权边界与结论绑定。

诚实建模原则：
  - 明确区分 ``metadata`` / ``abstract`` / ``full_text`` / ``ocr_text`` /
    ``quoted_snippet`` 五种文本类型，并给每条文本打标，绝不混为一谈；
  - 只抓取合法/开放访问来源：尊重 robots 与许可。对受版权保护全文（无法确认
    开放许可）**不越权获取**，标记为 ``restricted``，绝不把未获取内容当作全文；
  - 每条结论绑定：精确来源、段落（locator）、获取时间、适用范围与过期/重取策略，
    通过可写的 :class:`Conclusion` 结构承载。

在线下载能力为 ``external_dependency``：未配置下载器/未开放访问时诚实返回
``restricted`` 或空结果，绝不伪造成功全文。
"""

from __future__ import annotations

import abc
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

from .documents import sha256_of
from .models import utc_now_iso

# ------------------------------------------------------------------ 文本类型
TEXT_TYPE_METADATA = "metadata"
TEXT_TYPE_ABSTRACT = "abstract"
TEXT_TYPE_FULL_TEXT = "full_text"
TEXT_TYPE_OCR_TEXT = "ocr_text"
TEXT_TYPE_QUOTED_SNIPPET = "quoted_snippet"

TEXT_TYPES = (
    TEXT_TYPE_METADATA,
    TEXT_TYPE_ABSTRACT,
    TEXT_TYPE_FULL_TEXT,
    TEXT_TYPE_OCR_TEXT,
    TEXT_TYPE_QUOTED_SNIPPET,
)

TEXT_TYPE_LABELS: Dict[str, str] = {
    TEXT_TYPE_METADATA: "metadata（题录元数据）",
    TEXT_TYPE_ABSTRACT: "abstract（摘要）",
    TEXT_TYPE_FULL_TEXT: "full_text（全文）",
    TEXT_TYPE_OCR_TEXT: "ocr_text（OCR 文本）",
    TEXT_TYPE_QUOTED_SNIPPET: "quoted_snippet（引用片段）",
}

# 访问/版权边界
ACCESS_OPEN = "open"
ACCESS_RESTRICTED = "restricted"
ACCESS_BLOCKED = "blocked"

# 常见开放获取域名（启发式判断，仅用于确定默认开放访问）
OPEN_ACCESS_DOMAINS = {
    "arxiv.org",
    "openalex.org",
    "pubmedcentral.nih.gov",
    "core.ac.uk",
    "doabooks.org",
    "creativecommons.org",
    "zenodo.org",
}
# 允许全文获取的开放许可
OPEN_LICENSES = {"cc0", "cc-by", "cc-by-sa", "cc-by-nc", "public-domain", "open-access", "odc-by"}


def _utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def classify_text(item: Optional[Dict[str, Any]]) -> str:
    """根据字段区分文本类型并打标；无法判断时归为 metadata。

    优先级：显式 ``text_type`` > OCR 标志 > 全文 > 摘要 > 引用片段 > metadata。
    """
    item = item or {}
    explicit = item.get("text_type")
    if explicit in TEXT_TYPES:
        return explicit
    if bool(item.get("ocr") or item.get("is_ocr")):
        return TEXT_TYPE_OCR_TEXT
    if item.get("full_text") is not None or item.get("body") is not None:
        return TEXT_TYPE_FULL_TEXT
    if item.get("abstract") is not None:
        return TEXT_TYPE_ABSTRACT
    if item.get("quote") is not None or item.get("quoted_snippet") is not None:
        return TEXT_TYPE_QUOTED_SNIPPET
    return TEXT_TYPE_METADATA


def tag_text(item: Dict[str, Any]) -> Dict[str, Any]:
    """返回打上 ``text_type`` 标签的副本（不修改入参）。"""
    tagged = dict(item or {})
    tagged["text_type"] = classify_text(tagged)
    return tagged


@dataclass
class TextRecord:
    """一条被明确打标的文本记录。"""

    text_type: str = TEXT_TYPE_METADATA
    text: str = ""
    source: str = ""
    locator: str = ""  # 段落定位，如 "sec.3.2 ¶2"
    retrieved_at: str = field(default_factory=utc_now_iso)
    access: str = ACCESS_OPEN
    url: str = ""
    license: str = ""
    sha256: str = ""

    def __post_init__(self) -> None:
        if self.text_type not in TEXT_TYPES:
            self.text_type = TEXT_TYPE_METADATA
        if not self.sha256 and self.text:
            self.sha256 = sha256_of(self.text.encode("utf-8"))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text_type": self.text_type,
            "text": self.text,
            "source": self.source,
            "locator": self.locator,
            "retrieved_at": self.retrieved_at,
            "access": self.access,
            "url": self.url,
            "license": self.license,
            "sha256": self.sha256,
        }


# ------------------------------------------------------------------ 版权/访问边界
def is_open_access_url(url: str) -> bool:
    """启发式判断 URL 是否属于已知开放获取来源。"""
    host = (urlparse(url or "").netloc or "").lower()
    return any(host == d or host.endswith("." + d) for d in OPEN_ACCESS_DOMAINS)


def classify_access(url: str, *, robots_disallowed: bool = False, license: Optional[str] = None) -> str:
    """判定某全文是否允许获取。

    - robots 明确禁止 -> ``blocked``（不抓取）；
    - 开放许可或已知开放获取来源 -> ``open``；
    - 其余受版权保护全文 -> ``restricted``（不越权获取，仅标记）。
    """
    if robots_disallowed:
        return ACCESS_BLOCKED
    lic = (license or "").strip().lower()
    if lic in OPEN_LICENSES:
        return ACCESS_OPEN
    if is_open_access_url(url):
        return ACCESS_OPEN
    return ACCESS_RESTRICTED


# ------------------------------------------------------------------ 缓存与去重
class FullTextCache:
    """按 URL 缓存已获取的全文；可选用目录做文件持久化（仅标准库）。"""

    def __init__(self, cache_dir: Optional[str] = None) -> None:
        self._dir = Path(cache_dir) if cache_dir else None
        self._mem: Dict[str, TextRecord] = {}
        if self._dir is not None:
            self._dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
        return (self._dir / f"{digest}.json") if self._dir is not None else None

    def get(self, url: str) -> Optional[TextRecord]:
        if url in self._mem:
            return self._mem[url]
        path = self._path_for(url)
        if path is not None and path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                rec = TextRecord(**data)
                self._mem[url] = rec
                return rec
            except (ValueError, TypeError):
                return None
        return None

    def put(self, url: str, record: TextRecord) -> None:
        self._mem[url] = record
        path = self._path_for(url)
        if path is not None:
            path.write_text(json.dumps(record.to_dict(), ensure_ascii=False), encoding="utf-8")

    def has(self, url: str) -> bool:
        return self.get(url) is not None


def deduplicate_texts(records: List[TextRecord]) -> List[TextRecord]:
    """按内容 SHA-256 去重：保留每段内容首次出现的一条。"""
    seen: set = set()
    out: List[TextRecord] = []
    for r in records or []:
        key = r.sha256 or sha256_of((r.text or "").encode("utf-8"))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


# ------------------------------------------------------------------ 全文获取
Getter = Callable[[str], bytes]


def fetch_fulltext(
    url: str,
    *,
    source: str = "",
    cache: Optional[FullTextCache] = None,
    getter: Optional[Getter] = None,
    license: Optional[str] = None,
    robots_disallowed: bool = False,
    locator: str = "",
) -> TextRecord:
    """合法获取全文：开放访问才下载，缓存命中则复用，受限/阻断则标记且不越权获取。

    - 未开放访问（``restricted``/``blocked``）：返回空文本 + 对应 access，绝不假装拿到全文；
    - 开放访问但无下载器（``getter``）：视为无法获取，access 保持受限，不伪造；
    - 开放访问且可下载：解析字节、记录获取时间与 SHA-256，写入缓存。
    """
    if cache is not None and cache.has(url):
        return cache.get(url)  # type: ignore[return-value]

    access = classify_access(url, robots_disallowed=robots_disallowed, license=license)
    base = TextRecord(
        text_type=TEXT_TYPE_FULL_TEXT,
        text="",
        source=source,
        locator=locator,
        retrieved_at=utc_now_iso(),
        access=access,
        url=url,
        license=license or "",
    )
    if access != ACCESS_OPEN:
        return base  # 版权/robots 边界：不越权获取

    if getter is None:
        # 开放来源但无下载器：诚实标记为无法获取，不伪造全文。
        base.access = ACCESS_RESTRICTED
        return base

    raw = getter(url)
    text = raw.decode("utf-8", errors="replace")
    record = TextRecord(
        text_type=TEXT_TYPE_FULL_TEXT,
        text=text,
        source=source,
        locator=locator,
        retrieved_at=utc_now_iso(),
        access=ACCESS_OPEN,
        url=url,
        license=license or "",
        sha256=sha256_of(raw),
    )
    if cache is not None:
        cache.put(url, record)
    return record


# ------------------------------------------------------------------ 结论绑定
def default_expires_at(days: int = 180) -> str:
    """默认过期时间：now + days，UTC ISO。"""
    return (_utc() + timedelta(days=days)).isoformat() + "Z"


def refetch_strategy(expires_at: Optional[str], now: Optional[datetime] = None) -> str:
    """根据过期时间给出重取策略：none / async / sync。"""
    exp = _parse_iso(expires_at)
    if exp is None:
        return "none"
    now = now or _utc()
    remaining = exp - now
    if remaining <= timedelta(days=0):
        return "sync"
    if remaining <= timedelta(days=7):
        return "async"
    return "none"


@dataclass
class Conclusion:
    """一条可写的结论，绑定精确来源、段落定位、获取时间、适用范围、过期策略。

    字段：
      - source：精确来源（域名/DOI/标准号）；
      - locator：段落定位（如 "sec.3.2 ¶2" / "p.12"）；
      - paragraph：该结论对应的实际段落文本；
      - retrieved_at：获取（打标）时间；
      - scope：适用范围（metadata / abstract / full_text / ocr_text / quoted_snippet …）；
      - expires_at：过期时间（None 表示不自动过期）；
      - refetch_policy：重取策略（none / async / sync）。
    """

    source: str
    locator: str = ""
    paragraph: str = ""
    retrieved_at: str = field(default_factory=utc_now_iso)
    scope: str = TEXT_TYPE_FULL_TEXT
    expires_at: Optional[str] = None
    refetch_policy: str = "async"
    binding: str = ""  # 精确来源 URL/DOI

    def __post_init__(self) -> None:
        if not self.refetch_policy:
            self.refetch_policy = refetch_strategy(self.expires_at)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "locator": self.locator,
            "paragraph": self.paragraph,
            "retrieved_at": self.retrieved_at,
            "scope": self.scope,
            "expires_at": self.expires_at,
            "refetch_policy": self.refetch_policy,
            "binding": self.binding,
        }

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        """是否已过期；无 expires_at 视为永不过期。"""
        exp = _parse_iso(self.expires_at)
        if exp is None:
            return False
        return (now or _utc()) >= exp

    def refetch_due(self, grace_days: int = 7, now: Optional[datetime] = None) -> bool:
        """是否应重取：已过期，或距过期不足 grace_days。"""
        exp = _parse_iso(self.expires_at)
        if exp is None:
            return False
        now = now or _utc()
        return now >= (exp - timedelta(days=grace_days))


# ------------------------------------------------------------------ 可替换 Provider
class Provider(abc.ABC):
    """研究数据提供器接口（标准 / 法规 / 专利 / 竞品）。

    未配置实现时保持 ``external_dependency``：``available()`` 为 False、
    ``provide()`` 诚实返回空结果，绝不伪造检索结果。
    """

    kind: str = "unknown"

    @abc.abstractmethod
    def available(self) -> bool:
        """是否具备真实数据能力（False 表示 external_dependency）。"""

    @abc.abstractmethod
    def provide(self, query: str) -> List[Dict[str, Any]]:
        """返回该 query 的发现列表；不可用时返回空列表。"""


class ExternalProvider(Provider):
    """未配置实现时的诚实等待：不伪造结果。"""

    def __init__(self, kind: str = "unknown") -> None:
        self.kind = kind

    def available(self) -> bool:
        return False

    def provide(self, query: str) -> List[Dict[str, Any]]:
        return []


class DelegateProvider(Provider):
    """把可替换实现委托给注入的 object；未注入/不可用则诚实降级。"""

    def __init__(self, kind: str, impl: Optional[Provider] = None) -> None:
        self.kind = kind
        self._impl = impl

    def available(self) -> bool:
        return self._impl is not None and getattr(self._impl, "available", lambda: False)()

    def provide(self, query: str) -> List[Dict[str, Any]]:
        if not self.available():
            return []
        return list(getattr(self._impl, "provide", lambda q: [])(query))


def _provider_for(kind: str, impl: Optional[Provider]) -> Provider:
    if impl is None:
        return ExternalProvider(kind)
    return DelegateProvider(kind, impl)


def standard_provider(impl: Optional[Provider] = None) -> Provider:
    """标准数据提供器；未配置时返回 external_dependency。"""
    return _provider_for("standard", impl)


def regulation_provider(impl: Optional[Provider] = None) -> Provider:
    """法规数据提供器；未配置时返回 external_dependency。"""
    return _provider_for("regulation", impl)


def patent_provider(impl: Optional[Provider] = None) -> Provider:
    """专利数据提供器；未配置时返回 external_dependency。"""
    return _provider_for("patent", impl)


def competitor_provider(impl: Optional[Provider] = None) -> Provider:
    """竞品数据提供器；未配置时返回 external_dependency。"""
    return _provider_for("competitor", impl)


__all__ = [
    "TEXT_TYPE_METADATA", "TEXT_TYPE_ABSTRACT", "TEXT_TYPE_FULL_TEXT",
    "TEXT_TYPE_OCR_TEXT", "TEXT_TYPE_QUOTED_SNIPPET", "TEXT_TYPES", "TEXT_TYPE_LABELS",
    "ACCESS_OPEN", "ACCESS_RESTRICTED", "ACCESS_BLOCKED",
    "OPEN_ACCESS_DOMAINS", "OPEN_LICENSES",
    "classify_text", "tag_text", "TextRecord",
    "is_open_access_url", "classify_access",
    "FullTextCache", "deduplicate_texts", "fetch_fulltext",
    "default_expires_at", "refetch_strategy", "Conclusion",
    "Provider", "ExternalProvider", "DelegateProvider",
    "standard_provider", "regulation_provider", "patent_provider", "competitor_provider",
]
