"""CAD 产物证据：sha256 哈希、工具版本、时间戳与成熟度证据链。"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def sha256_file(path: Path) -> str:
    """计算文件的 sha256 十六进制摘要。"""
    h = hashlib.sha256()
    with open(str(path), 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def artifact_hash(path: Path) -> str:
    """产物哈希（等价于 sha256_file，语义命名）。"""
    return sha256_file(path)


def utc_now_iso() -> str:
    """返回 UTC ISO-8601 时间戳。"""
    return datetime.now(timezone.utc).isoformat()


def make_artifact_record(
    path: Path,
    tool: str,
    tool_version: str,
    *,
    for_level: Optional[str] = None,
    note: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """为一个已经写入磁盘的产物构造证据记录。

    :param path: 产物文件路径（必须存在）。
    :param tool: 生成工具名。
    :param tool_version: 工具版本。
    :param for_level: 该产物支撑的成熟度层级（如 ``C1``）。
    :param note: 诚实性备注（例如说明该产物是 faceted 临时件）。
    :param extra: 附加字段。
    :return: 含 path / sha256 / tool / tool_version / timestamp /
        maturity_evidence / note 的记录 dict。
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"artifact not found: {p}")
    record: Dict[str, Any] = {
        'path': str(p),
        'sha256': sha256_file(p),
        'tool': tool,
        'tool_version': tool_version,
        'timestamp': utc_now_iso(),
        'maturity_evidence': [for_level] if for_level else [],
    }
    if note:
        record['note'] = note
    if extra:
        record.update(extra)
    return record


def verify_artifact(record: Dict[str, Any]) -> bool:
    """校验记录中的 sha256 与磁盘文件一致。"""
    path = record.get('path')
    sha = record.get('sha256')
    if not path or not sha:
        return False
    p = Path(path)
    if not p.is_file():
        return False
    return sha256_file(p) == sha


__all__ = [
    'sha256_file', 'artifact_hash', 'utc_now_iso',
    'make_artifact_record', 'verify_artifact',
]