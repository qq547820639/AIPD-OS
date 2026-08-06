"""报价附件解析与规范化登记。

只做真实、确定性的解析与登记：不伪造报价。报价未登记为 official 时，
``get_official`` 会直接抛错而非虚构。
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# 规范 CSV 表头
CANONICAL_CSV_HEADER = [
    "supplier",
    "part",
    "moq",
    "tooling_fee",
    "unit_price",
    "lead_time_days",
]

SUPPORTED_EXTENSIONS = (".csv", ".json", ".xlsx", ".pdf")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_quote(record: Dict[str, Any]) -> Dict[str, Any]:
    """将一条原始报价记录规范化为确定的数值字段。

    - moq/lead_time_days 规范为非负 int
    - tooling_fee/unit_price 规范为非负 float
    - supplier/part 为去空格的字符串
    """
    record = dict(record or {})
    moq = max(0, _to_int(record.get("moq")))
    tooling_fee = max(0.0, _to_float(record.get("tooling_fee")))
    unit_price = max(0.0, _to_float(record.get("unit_price")))
    lead_time_days = max(0, _to_int(record.get("lead_time_days")))
    return {
        "supplier": str(record.get("supplier", "")).strip(),
        "part": str(record.get("part", "")).strip(),
        "moq": moq,
        "tooling_fee": tooling_fee,
        "unit_price": unit_price,
        "lead_time_days": lead_time_days,
    }


def _records_from_rows(rows: List[Dict[str, Any]], source: str) -> Dict[str, Any]:
    records = [normalize_quote(r) for r in rows]
    return {
        "source": source,
        "format": "dict",
        "records": records,
        "count": len(records),
        "errors": [],
    }


def _records_result(rows: List[Dict[str, Any]], source: str, fmt: str) -> Dict[str, Any]:
    records = [normalize_quote(r) for r in rows]
    return {
        "source": source,
        "format": fmt,
        "records": records,
        "count": len(records),
        "errors": [],
    }


def _not_verified_result(source: str, fmt: str, error: str) -> Dict[str, Any]:
    """无法解析时返回空记录 + 错误，数据保持 not_verified（绝不虚构）。"""
    return {
        "source": source,
        "format": fmt,
        "records": [],
        "count": 0,
        "errors": [{"error": error, "external_dependency": True, "not_verified": True}],
    }


def _parse_rows_from_xlsx(rows: List[tuple]) -> List[Dict[str, Any]]:
    if not rows:
        return []
    header = [str(h).strip().lower() if h is not None else "" for h in rows[0]]
    parsed: List[Dict[str, Any]] = []
    for line in rows[1:]:
        rec: Dict[str, Any] = {}
        for i, col in enumerate(header):
            rec[col] = line[i] if i < len(line) else None
        parsed.append(rec)
    return parsed


def _parse_quote_xlsx(p: Path) -> Dict[str, Any]:
    """解析 .xlsx 报价；需要 openpyxl，缺失时返回 not_verified 结构。"""
    try:
        import openpyxl  # noqa: WPS433
    except ImportError:
        return _not_verified_result(
            str(p), "xlsx",
            "openpyxl 未安装，无法解析 xlsx 报价；请安装 openpyxl 或走外部工具（数据保持 not_verified）",
        )
    try:
        wb = openpyxl.load_workbook(str(p), data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
    except Exception as exc:  # noqa: BLE001 - 解析失败保持 not_verified
        return _not_verified_result(str(p), "xlsx", f"xlsx 解析失败: {exc}")
    return _records_result(_parse_rows_from_xlsx(rows), str(p), "xlsx")


def _rows_from_pdf_text(text: str) -> Dict[str, Any]:
    """从 PDF 提取的纯文本中尝试结构化报价。

    仅做确定性启发式：先尝试 CSV 行解析，再尝试 JSON。无法提取时返回
    空记录 + 错误（not_verified）。
    """
    text = (text or "").strip()
    if not text:
        return {"records": [], "errors": ["PDF 文本为空，无法提取报价"]}
    # 尝试 CSV 行
    trimmed = "\n".join(ln for ln in text.splitlines() if ln.strip())
    try:
        reader = csv.DictReader(io.StringIO(trimmed))
        rows = list(reader)
        if rows and any(rows):
            return {"records": rows, "errors": []}
    except Exception:  # noqa: BLE001
        pass
    # 尝试 JSON
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            rows = data.get("records") or data.get("quotes") or []
        elif isinstance(data, list):
            rows = data
        else:
            rows = []
        if rows:
            return {"records": rows, "errors": []}
    except Exception:  # noqa: BLE001
        pass
    return {"records": [], "errors": ["无法从 PDF 文本提取结构化报价（数据保持 not_verified）"]}


def _parse_quote_pdf(p: Path) -> Dict[str, Any]:
    """解析 .pdf 报价；通过简单的文本提取器（pypdf/PyPDF2，可选）。

    缺少解析库或无法提取结构化报价时，返回 not_verified 结构（不虚构）。
    """
    try:
        from pypdf import PdfReader  # noqa: WPS433
    except ImportError:
        try:
            from PyPDF2 import PdfReader  # noqa: WPS433
        except ImportError:
            return _not_verified_result(
                str(p), "pdf",
                "pypdf/PyPDF2 未安装，无法解析 pdf 报价；请安装 pypdf 或走外部工具（数据保持 not_verified）",
            )
    try:
        reader = PdfReader(str(p))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as exc:  # noqa: BLE001
        return _not_verified_result(str(p), "pdf", f"pdf 解析失败: {exc}")
    extracted = _rows_from_pdf_text(text)
    if extracted["errors"]:
        return _not_verified_result(str(p), "pdf", "; ".join(extracted["errors"]))
    return _records_result(extracted["records"], str(p), "pdf")


def parse_quote_file(path: Union[str, Path, List[Dict[str, Any]]]) -> Dict[str, Any]:
    """解析报价文件（CSV/JSON），或一组行字典列表。

    支持规范 CSV 表头：supplier,part,moq,tooling_fee,unit_price,lead_time_days。
    若传入的是行字典列表，则直接规范化返回。不支持的文件扩展名抛出
    :class:`ValueError` 并列明支持格式。
    """
    if isinstance(path, list):
        return _records_from_rows(path, "inline-rows")

    p = Path(path)
    ext = p.suffix.lower()
    if not p.is_file():
        raise FileNotFoundError(f"报价文件不存在: {p}")

    if ext == ".csv":
        with open(p, "r", newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)
        records = [normalize_quote(r) for r in rows]
        return {
            "source": str(p),
            "format": "csv",
            "header": CANONICAL_CSV_HEADER,
            "records": records,
            "count": len(records),
            "errors": [],
        }

    if ext == ".json":
        with open(p, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            rows = data.get("records") or data.get("quotes") or []
        elif isinstance(data, list):
            rows = data
        else:
            raise ValueError("JSON 报价文件须为记录数组或含 records/quotes 的对象")
        records = [normalize_quote(r) for r in rows]
        return {
            "source": str(p),
            "format": "json",
            "records": records,
            "count": len(records),
            "errors": [],
        }

    if ext == ".xlsx":
        return _parse_quote_xlsx(p)

    if ext == ".pdf":
        return _parse_quote_pdf(p)

    raise ValueError(
        f"不支持的报价文件格式: {ext or '(无扩展名)'}；支持: {', '.join(SUPPORTED_EXTENSIONS)}"
    )


@dataclass
class QuoteVersion:
    """某供应商+零件的一条报价版本。"""

    quote_id: str
    supplier: str
    part: str
    version: int
    data: Dict[str, Any]
    received_at: str = field(default_factory=_now)
    source_file: str = ""
    status: str = "official"  # draft / official / superseded

    def __post_init__(self) -> None:
        self.data = normalize_quote(self.data)


class QuoteRegistry:
    """报价登记表：同一供应商+零件多次登记会递增版本并把旧版本标记 superseded。"""

    def __init__(self) -> None:
        self._quotes: Dict[tuple, List[QuoteVersion]] = {}

    def add_quote(
        self,
        *,
        supplier: str,
        part: str,
        data: Dict[str, Any],
        source_file: str = "",
        received_at: Optional[str] = None,
        status: str = "official",
    ) -> QuoteVersion:
        """登记一条报价；同 supplier+part 已存在则版本 +1 并把前者标记 superseded。"""
        normalized = normalize_quote(data)
        supplier = normalized["supplier"] or supplier
        part = normalized["part"] or part
        key = (supplier.lower(), part.lower())
        versions = self._quotes.setdefault(key, [])
        prev = versions[-1] if versions else None
        new_version = (prev.version + 1) if prev else 1
        if prev is not None and prev.status != "superseded":
            prev.status = "superseded"
        quote = QuoteVersion(
            quote_id=f"{supplier}-{part}-v{new_version}",
            supplier=supplier,
            part=part,
            version=new_version,
            data=normalized,
            received_at=received_at or _now(),
            source_file=source_file,
            status=status,
        )
        versions.append(quote)
        return quote

    def get_official(self, supplier: str, part: str) -> QuoteVersion:
        """返回该供应商+零件的 official 报价；没有则抛错（绝不虚构）。"""
        key = (supplier.lower(), part.lower())
        versions = self._quotes.get(key, [])
        for q in reversed(versions):
            if q.status == "official":
                return q
        raise KeyError(f"未接收到 {supplier}/{part} 的 official 报价，无法返回")

    def all_versions(self, supplier: str, part: str) -> List[QuoteVersion]:
        key = (supplier.lower(), part.lower())
        return list(self._quotes.get(key, []))


__all__ = [
    "normalize_quote",
    "parse_quote_file",
    "QuoteVersion",
    "QuoteRegistry",
    "CANONICAL_CSV_HEADER",
    "SUPPORTED_EXTENSIONS",
]
