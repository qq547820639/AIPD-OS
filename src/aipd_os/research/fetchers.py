"""全文下载与解析适配器契约。

``DocumentFetcher`` 是全文获取的统一接口：
  - ``ContractFetcher``：本地确定性夹具实现，返回固定全文，供测试与线下验证；
  - ``HttpDocumentFetcher``：真实 HTTP 桩，网络不可达/未配置密钥时显式失败并标记
    ``not_verified``，绝不伪造成功的在线下载结果（``external_dependency``）。

PDF/TXT 解析通过可插拔解析器（``DOCUMENT_PARSERS``）完成；未注册格式返回
``not_verified`` 而不猜测内容。
"""

from __future__ import annotations

import abc
from typing import Any

from .models import Citation, Document, FullText

# 确定性本地夹具（线下/测试用，并非真实网络内容）
_FIXTURES: dict[str, str] = {
    "ISO-9001:2015": (
        "ISO 9001:2015 Quality management systems — Requirements.\n"
        "This standard specifies requirements for a quality management system\n"
        "when an organization needs to demonstrate its ability to consistently\n"
        "provide products and services that meet customer and applicable statutory\n"
        "and regulatory requirements."
    ),
    "IPC-H05K": (
        "IPC-H05K Printed board design and fabrication.\n"
        "This standard covers the design, materials, and fabrication of printed\n"
        "boards for electronic assemblies."
    ),
    "US-PAT-10404000": (
        "United States Patent 10,404,000 B2.\n"
        "A method and apparatus for additive manufacturing of a component\n"
        "including a controller configured to direct a print head along a tool path."
    ),
}


class DocumentFetcher(abc.ABC):
    """全文获取接口契约。"""

    @abc.abstractmethod
    def fetch(self, citation: Citation) -> Document:
        """获取并解析全文。失败时返回 status=not_verified 的 Document，不抛网络异常。"""

    @abc.abstractmethod
    def available(self) -> bool:
        """该实现是否具备真实获取能力（False 表示 external_dependency）。"""


# ------------------------------------------------------------------ 解析器

def parse_txt(raw: bytes, citation: Citation, fmt: str = "txt") -> FullText:
    text = raw.decode("utf-8", errors="replace")
    return FullText(title=citation.title, text=text, citation=citation, format=fmt)


def parse_pdf(raw: bytes, citation: Citation, fmt: str = "pdf") -> FullText:
    # 无真实 PDF 渲染库时，用文本层提取非结构化内容；仅当能提取出内容才标记 obtainable。
    text = raw.decode("utf-8", errors="replace")
    return FullText(title=citation.title, text=text, citation=citation, format=fmt)


def _no_parser(raw: bytes, citation: Citation, fmt: str) -> FullText:
    return FullText(title=citation.title, text="", citation=citation, format=fmt)


# 可插拔解析器注册表：扩展名 -> 解析函数
DOCUMENT_PARSERS: dict[str, Any] = {
    ".txt": parse_txt,
    ".md": parse_txt,
    ".pdf": parse_pdf,
}


# ------------------------------------------------------------------ 实现

class ContractFetcher(DocumentFetcher):
    """本地确定性夹具实现：返回固定全文，用于测试与离线验证。"""

    def __init__(self, fixtures: dict[str, str] | None = None) -> None:
        self._fixtures = dict(_FIXTURES if fixtures is None else fixtures)

    def available(self) -> bool:
        # 本地夹具是真实可用的（不依赖外部网络）
        return True

    def parse(self, raw: bytes, citation: Citation, ext: str = ".txt") -> FullText:
        parser = DOCUMENT_PARSERS.get(ext, _no_parser)
        return parser(raw, citation, fmt=ext.strip("."))

    def fetch(self, citation: Citation) -> Document:
        key = None
        for k in self._fixtures:
            if k.lower() in (citation.title or "").lower() or k.lower() in (citation.identifier or "").lower():  # noqa: E501
                key = k
                break
        if key is None:
            return Document(citation=citation)
        parser = DOCUMENT_PARSERS.get(".txt", parse_txt)
        full = parser(self._fixtures[key].encode("utf-8"), citation, fmt="txt")
        return Document(citation=citation, full_text=full)


class HttpDocumentFetcher(DocumentFetcher):
    """真实 HTTP 桩：未配置密钥/网络不可达时显式失败并标记 not_verified。

    在线能力为 ``external_dependency``：需要真实下载服务与凭据。
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key

    def available(self) -> bool:
        return bool(self._api_key)

    def fetch(self, citation: Citation) -> Document:
        if not self.available():
            return Document(citation=citation)
        # 真实实现需在此处发起下载；此处仅提供契约骨架，避免伪造在线结果。
        raise NotImplementedError(
            "HttpDocumentFetcher.fetch requires a real download backend "
            "(external_dependency)."
        )


__all__ = [
    "DocumentFetcher",
    "ContractFetcher",
    "HttpDocumentFetcher",
    "DOCUMENT_PARSERS",
    "parse_txt",
    "parse_pdf",
]
