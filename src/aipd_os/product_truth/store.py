"""Product Truth 的 sqlite 存储层。

复用现有 ``AIPDStateDB`` 的 sqlite 文件（若传入实例则共享其连接文件），
在同一个库中新增 ``product_truth`` / ``truth_lineage`` / ``rework_tasks`` 表。
提供新增 / 更新 / 查询 / 删除 / 过期判定 / 可信度评估 API。
不再依赖把事实写进 steps_log 字符串 —— 这里全部落到结构化表。
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from .models import (SourceRef, TruthRecord, TrustAssessment, ensure_trust,
                     now_iso, TRUTH_TYPES)

SCHEMA = r"""
CREATE TABLE IF NOT EXISTS product_truth (
  id TEXT PRIMARY KEY,
  record_type TEXT NOT NULL,
  content TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT '{}',
  trust_level TEXT NOT NULL,
  effective_at TEXT,
  expires_at TEXT,
  version INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS truth_lineage (
  edge_id INTEGER PRIMARY KEY AUTOINCREMENT,
  upstream_id TEXT NOT NULL,
  downstream_id TEXT NOT NULL,
  relation TEXT NOT NULL DEFAULT 'affects',
  created_at TEXT NOT NULL,
  UNIQUE(upstream_id, downstream_id, relation)
);
CREATE TABLE IF NOT EXISTS rework_tasks (
  task_id TEXT PRIMARY KEY,
  truth_id TEXT NOT NULL,
  reason TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  backoff_until TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
"""


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _row_to_record(row: sqlite3.Row) -> TruthRecord:
    src = SourceRef.from_dict(json.loads(row["source"]))
    return TruthRecord(
        record_type=row["record_type"],
        content=row["content"],
        source=src,
        trust_level=row["trust_level"],
        effective_at=row["effective_at"],
        expires_at=row["expires_at"],
        record_id=row["id"],
        version=row["version"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class ProductTruthStore:
    """Product Truth 记录的结构化 sqlite 存储。"""

    def __init__(self, db_path: str):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ----------------------------------------------------------- 新增 / 查询
    def add(self, record: TruthRecord) -> str:
        ts = now_iso()
        cid = record.record_id or self._next_id()
        with self.connect() as c:
            c.execute(
                "INSERT INTO product_truth(id,record_type,content,source,trust_level,"
                "effective_at,expires_at,version,status,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (cid, record.record_type, record.content,
                 _json(record.source.to_dict() if record.source else {}),
                 record.trust_level, record.effective_at, record.expires_at,
                 record.version, record.status, record.created_at or ts, ts))
        return cid

    def _next_id(self) -> str:
        with self.connect() as c:
            rows = c.execute("SELECT id FROM product_truth").fetchall()
        nums = []
        for r in rows:
            if r["id"].startswith("T-"):
                try:
                    nums.append(int(r["id"].rsplit("-", 1)[1]))
                except ValueError:
                    pass
        return f"T-{max(nums, default=0) + 1:03d}"

    def get(self, record_id: str) -> TruthRecord:
        with self.connect() as c:
            row = c.execute("SELECT * FROM product_truth WHERE id=?",
                            (record_id,)).fetchone()
        if not row:
            raise KeyError(record_id)
        return _row_to_record(row)

    def find_id_by_type_and_content(self, record_type: str, content: str) -> Optional[str]:
        """按类型+内容精确查找（用于幂等新增/去重）。"""
        with self.connect() as c:
            row = c.execute(
                "SELECT id FROM product_truth WHERE record_type=? AND content=?",
                (record_type, content)).fetchone()
        return row["id"] if row else None

    def query(self, record_type: Optional[str] = None,
              status: Optional[str] = None) -> List[TruthRecord]:
        sql = "SELECT * FROM product_truth"
        conds, params = [], []
        if record_type is not None:
            conds.append("record_type=?")
            params.append(record_type)
        if status is not None:
            conds.append("status=?")
            params.append(status)
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        sql += " ORDER BY created_at"
        with self.connect() as c:
            rows = c.execute(sql, params).fetchall()
        return [_row_to_record(r) for r in rows]

    def list_all(self) -> List[TruthRecord]:
        return self.query()

    # ----------------------------------------------------------- 更新 / 删除
    def update(self, record_id: str, **fields: Any) -> TruthRecord:
        allow = {"content", "source", "trust_level", "effective_at", "expires_at",
                 "version", "status"}
        set_cols = [k for k in fields if k in allow]
        if not set_cols:
            raise ValueError("no editable fields provided")
        cur = self.get(record_id)
        values = []
        for k in set_cols:
            if k == "source":
                values.append(_json(fields[k].to_dict() if isinstance(fields[k], SourceRef)
                                    else fields[k]))
            elif k == "trust_level":
                ensure_trust(fields[k])
                values.append(fields[k])
            elif k == "status":
                values.append(fields[k])
            else:
                values.append(fields[k])
        values.append(now_iso())
        set_sql = ", ".join([f"{col}=?" for col in set_cols] + ["updated_at=?"])
        with self.connect() as c:
            c.execute(f"UPDATE product_truth SET {set_sql} WHERE id=?",
                      values + [record_id])
        return self.get(record_id)

    def bump_version(self, record_id: str) -> TruthRecord:
        """返工产生新版本：version+1 并标记 active。"""
        return self.update(record_id, version=self.get(record_id).version + 1,
                           status="active")

    def set_status(self, record_id: str, status: str) -> TruthRecord:
        return self.update(record_id, status=status)

    def delete(self, record_id: str) -> None:
        with self.connect() as c:
            c.execute("DELETE FROM product_truth WHERE id=?", (record_id,))

    # ----------------------------------------------------------- 过期判定
    def is_expired(self, record_id: str, at: Optional[str] = None) -> bool:
        return self.get(record_id).is_expired(at)

    def list_expired(self, at: Optional[str] = None) -> List[TruthRecord]:
        return [r for r in self.list_all() if r.is_expired(at)]

    # ----------------------------------------------------------- 可信度评估
    def assess_trust(self, record_id: str) -> TrustAssessment:
        """确定性可信度分级。

        规则：
          - 已过期 → unverified；
          - evidence 类自带 high（有内容即视为已核验来源）；其余类型若无
            upstream 证据或无内容 → unverified；
          - 有 upstream 证据链且未过期 → verified；
          - 否则按有效证据数量给出 low/medium。
        """
        rec = self.get(record_id)
        reasons: List[str] = []
        if rec.is_expired():
            return TrustAssessment("unverified", ["record is expired"])
        with self.connect() as c:
            up_n = c.execute(
                "SELECT COUNT(*) FROM truth_lineage WHERE downstream_id=?",
                (record_id,)).fetchone()[0]
            up_evidence = c.execute(
                "SELECT COUNT(*) FROM truth_lineage tl JOIN product_truth t "
                "ON t.id=tl.upstream_id WHERE tl.downstream_id=? AND t.record_type='evidence'",
                (record_id,)).fetchone()[0]
        if not rec.content.strip():
            reasons.append("empty content")
            return TrustAssessment("unverified", reasons)
        if rec.record_type == "evidence":
            return TrustAssessment("verified", ["evidence is a primary source"])
        if up_evidence >= 1:
            return TrustAssessment("verified", ["backed by upstream evidence"])
        if up_n >= 1:
            return TrustAssessment("medium", ["has upstream dependencies, no direct evidence"])
        reasons.append("missing evidence / upstream verification")
        return TrustAssessment("low", reasons)


__all__ = ["ProductTruthStore", "SCHEMA"]