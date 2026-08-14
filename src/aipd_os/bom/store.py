"""BOM 存储（tenant+project 作用域 sqlite，乐观锁 + 原子 ID + 审计）。

与 ``AIPDStateDB`` 正交：BOM 使用独立库文件（``<state.db>.bom.db`` 约定由
调用方决定路径），避免给权威状态库加表（迁移冻结）。集成桥：调用方可把
成本汇总等结果经 ``AIPDStateDB.add_fact`` 写回 Product Truth（见 CLI）。
"""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .models import BOM_STATUSES, BomHeader, BomLine, now_iso

SCHEMA = r"""
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS boms(
  bom_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL DEFAULT 'default',
  project_id TEXT NOT NULL DEFAULT 'default',
  name TEXT NOT NULL,
  revision TEXT NOT NULL DEFAULT '0.1',
  status TEXT NOT NULL DEFAULT 'draft',
  version_no INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (bom_id, tenant_id, project_id)
);
CREATE TABLE IF NOT EXISTS bom_lines(
  line_id TEXT NOT NULL,
  bom_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL DEFAULT 'default',
  project_id TEXT NOT NULL DEFAULT 'default',
  item TEXT NOT NULL,
  parent_item TEXT,
  description TEXT NOT NULL DEFAULT '',
  quantity REAL NOT NULL DEFAULT 1.0,
  unit TEXT NOT NULL DEFAULT 'pcs',
  material TEXT,
  supplier TEXT,
  unit_cost REAL,
  currency TEXT NOT NULL DEFAULT 'CNY',
  source_deliverable TEXT,
  quote_ref TEXT,
  status TEXT NOT NULL DEFAULT 'planned',
  version_no INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (line_id, tenant_id, project_id)
);
CREATE INDEX IF NOT EXISTS idx_bom_lines_bom ON bom_lines(bom_id, tenant_id, project_id);
CREATE TABLE IF NOT EXISTS bom_id_sequences(
  name TEXT PRIMARY KEY,
  next_val INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS bom_changes(
  change_id INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_id TEXT NOT NULL DEFAULT 'default',
  project_id TEXT NOT NULL DEFAULT 'default',
  object_type TEXT NOT NULL,
  object_id TEXT NOT NULL,
  action TEXT NOT NULL,
  before_json TEXT,
  after_json TEXT,
  reason TEXT,
  created_at TEXT NOT NULL
);
"""


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class OptimisticLockError(RuntimeError):
    """BOM 行/头版本冲突（并发更新被拒）。"""


class BomStore:
    """BOM + 成本快照的结构化存储（own sqlite；乐观锁；审计）。"""

    def __init__(self, db_path: str | Path) -> None:
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------- id 分配
    def _next_id(self, c: sqlite3.Connection, prefix: str) -> str:
        """原子 ID 分配（ON CONFLICT 自增，避免并发撞号）。"""
        c.execute(
            "INSERT INTO bom_id_sequences(name, next_val) VALUES(?, 1) "
            "ON CONFLICT(name) DO UPDATE SET next_val = next_val + 1",
            (prefix,))
        row = c.execute(
            "SELECT next_val FROM bom_id_sequences WHERE name=?", (prefix,)).fetchone()
        return f"{prefix}-{row[0]:03d}"

    # ------------------------------------------------------------- audit
    def _change(self, c: sqlite3.Connection, tenant_id: str, project_id: str,
                object_type: str, object_id: str, action: str,
                before: Any, after: Any, reason: str) -> None:
        c.execute(
            "INSERT INTO bom_changes(tenant_id,project_id,object_type,object_id,"
            "action,before_json,after_json,reason,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (tenant_id, project_id, object_type, object_id, action,
             _json(before) if before is not None else None,
             _json(after) if after is not None else None, reason, now_iso()))

    # ------------------------------------------------------------- BOM 头
    def create_bom(self, tenant_id: str, project_id: str, name: str,
                   revision: str = "0.1") -> BomHeader:
        # 先以占位 id 构造（模型校验 bom_id 必填），分配真实 id 后替换
        header = BomHeader(bom_id="pending", tenant_id=tenant_id,
                           project_id=project_id, name=name, revision=revision)
        with self.connect() as c:
            bom_id = self._next_id(c, "BOM")
            header.bom_id = bom_id
            c.execute(
                "INSERT INTO boms(bom_id,tenant_id,project_id,name,revision,"
                "status,version_no,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (bom_id, tenant_id, project_id, name, revision, "draft", 1,
                 header.created_at, header.updated_at))
            self._change(c, tenant_id, project_id, "bom", bom_id, "create",
                         None, header.to_dict(), "create bom")
        return header

    def get_bom(self, tenant_id: str, project_id: str,
                bom_id: str | None = None) -> BomHeader | None:
        with self.connect() as c:
            if bom_id is not None:
                row = c.execute(
                    "SELECT * FROM boms WHERE bom_id=? AND tenant_id=? AND project_id=?",
                    (bom_id, tenant_id, project_id)).fetchone()
                return self._header(row) if row else None
            row = c.execute(
                "SELECT * FROM boms WHERE tenant_id=? AND project_id=? "
                "ORDER BY updated_at DESC, bom_id DESC LIMIT 1",
                (tenant_id, project_id)).fetchone()
            return self._header(row) if row else None

    @staticmethod
    def _header(row: sqlite3.Row) -> BomHeader:
        return BomHeader(
            bom_id=row["bom_id"], tenant_id=row["tenant_id"],
            project_id=row["project_id"], name=row["name"],
            revision=row["revision"], status=row["status"],
            version_no=row["version_no"],
            created_at=row["created_at"], updated_at=row["updated_at"])

    def set_bom_status(self, tenant_id: str, project_id: str, bom_id: str,
                       status: str, expected_version: int | None = None) -> BomHeader:
        if status not in BOM_STATUSES:
            raise ValueError(f"invalid bom status {status!r}")
        ts = now_iso()
        with self.connect() as c:
            row = c.execute(
                "SELECT * FROM boms WHERE bom_id=? AND tenant_id=? AND project_id=?",
                (bom_id, tenant_id, project_id)).fetchone()
            if row is None:
                raise KeyError(bom_id)
            if expected_version is not None and row["version_no"] != expected_version:
                raise OptimisticLockError(
                    f"bom {bom_id} version mismatch: expected {expected_version}, "
                    f"got {row['version_no']}")
            c.execute(
                "UPDATE boms SET status=?, version_no=version_no+1, updated_at=? "
                "WHERE bom_id=? AND tenant_id=? AND project_id=?",
                (status, ts, bom_id, tenant_id, project_id))
            self._change(c, tenant_id, project_id, "bom", bom_id, "status",
                         {"status": row["status"]}, {"status": status}, "set status")
        header = self.get_bom(tenant_id, project_id, bom_id)
        assert header is not None
        return header

    # ------------------------------------------------------------- BOM 行
    def add_line(self, line: BomLine, reason: str = "add line") -> BomLine:
        with self.connect() as c:
            bom = c.execute(
                "SELECT 1 FROM boms WHERE bom_id=? AND tenant_id=? AND project_id=?",
                (line.bom_id, line.tenant_id, line.project_id)).fetchone()
            if bom is None:
                raise KeyError(f"bom {line.bom_id!r} not found in scope")
            self._ensure_no_parent_cycle(c, line.tenant_id, line.project_id,
                                         line.bom_id, line.item, line.parent_item)
            line_id = self._next_id(c, "LINE")
            line.line_id = line_id
            c.execute(
                "INSERT INTO bom_lines(line_id,bom_id,tenant_id,project_id,item,"
                "parent_item,description,quantity,unit,material,supplier,unit_cost,"
                "currency,source_deliverable,quote_ref,status,version_no,"
                "created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (line_id, line.bom_id, line.tenant_id, line.project_id, line.item,
                 line.parent_item, line.description, line.quantity, line.unit,
                 line.material, line.supplier, line.unit_cost, line.currency,
                 line.source_deliverable, line.quote_ref, line.status,
                 line.version_no, line.created_at, line.updated_at))
            self._change(c, line.tenant_id, line.project_id, "bom_line", line_id,
                         "create", None, line.to_dict(), reason)
        return line

    def _ensure_no_parent_cycle(self, c: sqlite3.Connection, tenant_id: str,
                                project_id: str, bom_id: str, item: str,
                                parent_item: str | None) -> None:
        """父链不得回指 item 自身（防循环层级）。"""
        cur = parent_item
        seen: set[str] = set()
        while cur is not None:
            if cur == item:
                raise ValueError(
                    f"parent chain cycle: {item!r} cannot be its own ancestor")
            if cur in seen:
                raise ValueError(f"parent chain cycle detected at {cur!r}")
            seen.add(cur)
            row = c.execute(
                "SELECT parent_item FROM bom_lines WHERE bom_id=? AND tenant_id=?"
                " AND project_id=? AND item=? LIMIT 1",
                (bom_id, tenant_id, project_id, cur)).fetchone()
            cur = row["parent_item"] if row else None

    @staticmethod
    def _line(row: sqlite3.Row) -> BomLine:
        return BomLine(
            line_id=row["line_id"], bom_id=row["bom_id"],
            tenant_id=row["tenant_id"], project_id=row["project_id"],
            item=row["item"], parent_item=row["parent_item"],
            description=row["description"], quantity=row["quantity"],
            unit=row["unit"], material=row["material"], supplier=row["supplier"],
            unit_cost=row["unit_cost"], currency=row["currency"],
            source_deliverable=row["source_deliverable"],
            quote_ref=row["quote_ref"], status=row["status"],
            version_no=row["version_no"],
            created_at=row["created_at"], updated_at=row["updated_at"])

    def list_lines(self, tenant_id: str, project_id: str,
                   bom_id: str | None = None) -> list[BomLine]:
        with self.connect() as c:
            if bom_id is not None:
                rows = c.execute(
                    "SELECT * FROM bom_lines WHERE bom_id=? AND tenant_id=? "
                    "AND project_id=? ORDER BY line_id",
                    (bom_id, tenant_id, project_id)).fetchall()
            else:
                rows = c.execute(
                    "SELECT * FROM bom_lines WHERE tenant_id=? AND project_id=? "
                    "ORDER BY bom_id, line_id",
                    (tenant_id, project_id)).fetchall()
        return [self._line(r) for r in rows]

    def get_line(self, tenant_id: str, project_id: str,
                 line_id: str) -> BomLine | None:
        with self.connect() as c:
            row = c.execute(
                "SELECT * FROM bom_lines WHERE line_id=? AND tenant_id=? AND project_id=?",
                (line_id, tenant_id, project_id)).fetchone()
        return self._line(row) if row else None

    def update_line(self, tenant_id: str, project_id: str, line_id: str,
                    expected_version: int, reason: str = "update line",
                    **fields: Any) -> BomLine:
        allow = {"item", "parent_item", "description", "quantity", "unit",
                 "material", "supplier", "unit_cost", "currency",
                 "source_deliverable", "quote_ref", "status"}
        set_cols = [k for k in fields if k in allow]
        if not set_cols:
            raise ValueError("no editable fields provided")
        ts = now_iso()
        with self.connect() as c:
            row = c.execute(
                "SELECT * FROM bom_lines WHERE line_id=? AND tenant_id=? AND project_id=?",
                (line_id, tenant_id, project_id)).fetchone()
            if row is None:
                raise KeyError(line_id)
            if row["version_no"] != expected_version:
                raise OptimisticLockError(
                    f"line {line_id} version mismatch: expected {expected_version}, "
                    f"got {row['version_no']}")
            candidate = self._line(row)
            for k, v in fields.items():
                if k in allow:
                    setattr(candidate, k, v)
            candidate.__post_init__()  # 重新校验（数量>0 / 成本>=0 / 非自父）
            if candidate.parent_item is not None:
                self._ensure_no_parent_cycle(c, tenant_id, project_id,
                                             row["bom_id"], candidate.item,
                                             candidate.parent_item)
            values = [getattr(candidate, k) for k in set_cols]
            set_sql = ", ".join(f"{k}=?" for k in set_cols)
            c.execute(
                f"UPDATE bom_lines SET {set_sql}, version_no=version_no+1, "
                f"updated_at=? WHERE line_id=? AND tenant_id=? AND project_id=?",
                values + [ts, line_id, tenant_id, project_id])
            self._change(c, tenant_id, project_id, "bom_line", line_id, "update",
                         self._line(row).to_dict(), candidate.to_dict(), reason)
        updated = self.get_line(tenant_id, project_id, line_id)
        assert updated is not None
        return updated

    def remove_line(self, tenant_id: str, project_id: str, line_id: str,
                    reason: str = "remove line") -> None:
        with self.connect() as c:
            row = c.execute(
                "SELECT * FROM bom_lines WHERE line_id=? AND tenant_id=? AND project_id=?",
                (line_id, tenant_id, project_id)).fetchone()
            if row is None:
                raise KeyError(line_id)
            c.execute(
                "DELETE FROM bom_lines WHERE line_id=? AND tenant_id=? AND project_id=?",
                (line_id, tenant_id, project_id))
            self._change(c, tenant_id, project_id, "bom_line", line_id, "delete",
                         self._line(row).to_dict(), None, reason)

    def list_changes(self, tenant_id: str, project_id: str,
                     limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as c:
            rows = c.execute(
                "SELECT * FROM bom_changes WHERE tenant_id=? AND project_id=? "
                "ORDER BY change_id DESC LIMIT ?",
                (tenant_id, project_id, limit)).fetchall()
        return [dict(r) for r in rows]


__all__ = ["SCHEMA", "BomStore", "OptimisticLockError"]
