"""实验室验证数据导入（CSV/XLSX/报告）。

只做真实解析。无法在本地机器解析的格式（PDF/DOCX 报告）或缺少解析库
（openpyxl）时，会抛出 ``external_blocked`` 而不是伪造成功。
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Union

from aipd_os.execution.adapter import AdapterError

# 规范实验室 CSV 表头
CANONICAL_LAB_CSV_HEADER = [
    "stage",
    "test_item",
    "sample_id",
    "result",
    "pass_fail",
    "notes",
]

REPORT_EXTENSIONS = (".pdf", ".docx")


def _normalize_lab_record(record: Dict[str, Any], stage: str) -> Dict[str, Any]:
    record = dict(record or {})
    return {
        "stage": str(record.get("stage") or stage).strip().lower(),
        "test_item": str(record.get("test_item", "")).strip(),
        "sample_id": str(record.get("sample_id", "")).strip(),
        "result": str(record.get("result", "")).strip(),
        "pass_fail": str(record.get("pass_fail", "")).strip().lower(),
        "notes": str(record.get("notes", "")).strip(),
    }


def _records_from_rows(rows: List[Dict[str, Any]], stage: str, source: str, fmt: str) -> Dict[str, Any]:
    records = [_normalize_lab_record(r, stage) for r in rows]
    return {
        "source": source,
        "format": fmt,
        "stage": stage,
        "records": records,
        "count": len(records),
    }


def import_lab_csv(path: Union[str, Path], stage: str) -> Dict[str, Any]:
    """解析含表头的实验室结果 CSV。规范表头需含 test_item/pass_fail 等字段。"""
    p = Path(path)
    with open(p, "r", newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
    return _records_from_rows(rows, stage, str(p), "csv")


def import_lab_json(path: Union[str, Path], stage: str) -> Dict[str, Any]:
    """解析 JSON 实验室记录。"""
    p = Path(path)
    with open(p, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        rows = data.get("records") or data.get("results") or []
    elif isinstance(data, list):
        rows = data
    else:
        raise ValueError("JSON 实验室数据须为记录数组或含 records/results 的对象")
    return _records_from_rows(rows, stage, str(p), "json")


def import_lab_xlsx(path: Union[str, Path], stage: str) -> Dict[str, Any]:
    """解析 .xlsx 实验室数据。

    需要 openpyxl；未安装时抛 ``external_blocked``（诚实：不伪造解析）。
    """
    p = Path(path)
    try:
        import openpyxl  # noqa: WPS433
    except ImportError:
        raise AdapterError(
            f"openpyxl 未安装，无法解析 xlsx 实验室数据: {p}；请安装 openpyxl 或走外部工具",
            classification="external_blocked",
        )
    wb = openpyxl.load_workbook(str(p), data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return _records_from_rows([], stage, str(p), "xlsx")
    header = [str(h).strip().lower() if h is not None else "" for h in rows[0]]
    parsed = []
    for line in rows[1:]:
        rec = {}
        for i, col in enumerate(header):
            rec[col] = line[i] if i < len(line) else None
        parsed.append(rec)
    return _records_from_rows(parsed, stage, str(p), "xlsx")


def import_lab_report(path: Union[str, Path], stage: str) -> Dict[str, Any]:
    """导入实验室报告。

    - .json/.csv 委托给对应解析器
    - .pdf/.docx 无法在本地机器机器解析，抛 ``external_blocked``（不声称成功）
    """
    p = Path(path)
    ext = p.suffix.lower()
    if ext == ".csv":
        return import_lab_csv(p, stage)
    if ext == ".json":
        return import_lab_json(p, stage)
    if ext in REPORT_EXTENSIONS:
        raise AdapterError(
            f"无法在本地机器解析 {ext} 实验室报告: {p}；需外部工具/人工提取数据",
            classification="external_blocked",
        )
    raise ValueError(f"不支持的实验室数据格式: {ext or '(无扩展名)'}；支持: .csv, .json, .xlsx")


__all__ = [
    "import_lab_csv",
    "import_lab_json",
    "import_lab_xlsx",
    "import_lab_report",
    "CANONICAL_LAB_CSV_HEADER",
]
