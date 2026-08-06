"""附件摄入与净化。

真实本地能力：
  - 摄入路径或字节，校验大小上限与扩展名白名单；
  - 剥离危险内容（脚本标签、URL、内联事件、危险宏关键词）；
  - 计算 SHA-256 并记录摄入元数据（来源、时间、原始大小、净化大小）。

本模块不做任何文件执行；净化为纯文本层处理。
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Union

from .models import utc_now_iso

# 扩展名白名单（真实可安全解析的类型）
ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf", ".csv", ".json"}
DEFAULT_MAX_BYTES = 20 * 1024 * 1024  # 20 MiB

# 危险内容模式（剥离而非执行）
_DANGEROUS_PATTERNS = [
    re.compile(r"<script\b[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<iframe\b[^>]*>.*?</iframe>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<object\b[^>]*>.*?</object>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<embed\b[^>]*/>", re.IGNORECASE),
    re.compile(r"on\w+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", re.IGNORECASE),
    re.compile(r"javascript:\s*", re.IGNORECASE),
    re.compile(r"vbscript:\s*", re.IGNORECASE),
    re.compile(r"data:\s*text/html", re.IGNORECASE),
    re.compile(r"\b(?:POWER|EXECUTIVE)\b\s*\(\s*[A-Za-z].*", re.IGNORECASE),
]


class IngestionError(ValueError):
    pass


class AttachmentTooLarge(IngestionError):
    pass


class DisallowedExtension(IngestionError):
    pass


def sanitize_text(text: str) -> str:
    """剥离危险内容，返回净化后的文本。"""
    cleaned = text or ""
    for pat in _DANGEROUS_PATTERNS:
        cleaned = pat.sub(" ", cleaned)
    return cleaned


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_bytes(source: Union[str, Path, bytes]) -> bytes:
    if isinstance(source, bytes):
        return source
    return Path(source).read_bytes()


def _extension_of(source: Union[str, Path, bytes]) -> str:
    if isinstance(source, bytes):
        return ""
    return Path(source).suffix.lower()


def ingest_attachment(
    source: Union[str, Path, bytes],
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    allowed_extensions: Optional[set] = None,
    original_name: Optional[str] = None,
) -> Dict[str, Any]:
    """摄入并净化附件。

    返回摄入元数据：sha256、原始大小、净化大小、时间、来源名、扩展名。
    不做任何文件执行。
    """
    allow = allowed_extensions if allowed_extensions is not None else ALLOWED_EXTENSIONS
    raw = _read_bytes(source)
    if len(raw) > max_bytes:
        raise AttachmentTooLarge(
            f"attachment {len(raw)} bytes exceeds limit {max_bytes}"
        )

    ext = _extension_of(source)
    if ext and ext not in allow:
        raise DisallowedExtension(f"extension '{ext or '(none)'}' not allowed: {sorted(allow)}")

    cleaned = sanitize_text(raw.decode("utf-8", errors="replace"))
    cleaned_bytes = cleaned.encode("utf-8")

    name = original_name or (Path(source).name if not isinstance(source, bytes) else "bytes")
    return {
        "sha256": sha256_of(raw),
        "original_size": len(raw),
        "sanitized_size": len(cleaned_bytes),
        "ingested_at": utc_now_iso(),
        "name": name,
        "extension": ext,
        "dangerous_markers": _danger_count(raw.decode("utf-8", errors="replace")),
        "sanitized_bytes": cleaned_bytes,
    }


def _danger_count(text: str) -> int:
    return sum(len(pat.findall(text)) for pat in _DANGEROUS_PATTERNS)


__all__ = [
    "ALLOWED_EXTENSIONS",
    "DEFAULT_MAX_BYTES",
    "IngestionError",
    "AttachmentTooLarge",
    "DisallowedExtension",
    "sanitize_text",
    "sha256_of",
    "ingest_attachment",
]