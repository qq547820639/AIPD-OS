"""AIPD-OS 多项目多租户状态数据库。

生产级 SQLite 实现，具备：
  - 多租户（tenants）+ 多项目（projects）数据模型；
  - 用户在特定 tenant/project 上的行级访问授权（user_access）；
  - 乐观锁：所有可更新业务表带 ``version_no`` 列，更新时 ``WHERE version_no=?``
    并校验 rowcount，冲突抛 :class:`OptimisticLockError`；
  - 写操作统一在事务中执行；
  - 敏感字段（supplier quote / contact / experiment_data 等）透明加密
    （标记 ``__encrypted__``）。

本模块不依赖任何第三方库；``cryptography`` 仅作可选加密后端。
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from .crypto import decrypt_secret, encrypt_secret

# 敏感字段 key：存储时自动加密
SENSITIVE_KEYS = {
    "supplier_quote", "supplier_quotes", "contact", "contacts",
    "experiment_data", "api_key", "credential", "secret", "token",
}
FACT_STATUSES = {"V", "S", "C", "E", "A", "P", "T", "R"}
PROJECT_STATUSES = {"active", "awaiting_owner_decision", "blocked_external",
                    "internal_rework", "released", "archived"}

SCHEMA = r"""
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS tenants (
  tenant_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
  user_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  username TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  salt TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS user_access (
  user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  tenant_id TEXT NOT NULL,
  project_id TEXT,
  PRIMARY KEY (user_id, tenant_id, project_id)
);
CREATE TABLE IF NOT EXISTS sessions (
  session_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  token TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS projects (
  project_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  goal TEXT NOT NULL,
  gate TEXT NOT NULL DEFAULT 'G0',
  status TEXT NOT NULL DEFAULT 'active',
  version TEXT NOT NULL DEFAULT '0.1.0',
  owner_policy TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  version_no INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (project_id, tenant_id)
);
CREATE TABLE IF NOT EXISTS facts (
  fact_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  key TEXT NOT NULL,
  value_json TEXT NOT NULL,
  unit TEXT,
  tolerance TEXT,
  conditions TEXT,
  status TEXT NOT NULL,
  confidence REAL NOT NULL DEFAULT 0.5,
  source TEXT,
  version TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  version_no INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (fact_id, project_id, tenant_id),
  UNIQUE(project_id, tenant_id, key, version)
);
CREATE TABLE IF NOT EXISTS evidence (
  evidence_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  url TEXT,
  identifier TEXT,
  accessed_at TEXT,
  quality TEXT,
  summary TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  version_no INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (evidence_id, project_id, tenant_id)
);
CREATE TABLE IF NOT EXISTS fact_evidence (
  fact_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  evidence_id TEXT NOT NULL,
  relation TEXT NOT NULL DEFAULT 'supports',
  PRIMARY KEY (fact_id, project_id, tenant_id, evidence_id, relation)
);
CREATE TABLE IF NOT EXISTS decisions (
  decision_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  topic TEXT NOT NULL,
  trigger TEXT,
  recommendation TEXT,
  options_json TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'proposed',
  choice TEXT,
  comment TEXT,
  created_at TEXT NOT NULL,
  resolved_at TEXT,
  version_no INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (decision_id, project_id, tenant_id)
);
CREATE TABLE IF NOT EXISTS deliverables (
  deliverable_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  type TEXT NOT NULL,
  path TEXT,
  status TEXT NOT NULL DEFAULT 'planned',
  version TEXT,
  gate TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  updated_at TEXT NOT NULL,
  version_no INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (deliverable_id, project_id, tenant_id)
);
CREATE TABLE IF NOT EXISTS dependencies (
  dependency_id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  source_type TEXT NOT NULL,
  source_id TEXT NOT NULL,
  target_type TEXT NOT NULL,
  target_id TEXT NOT NULL,
  relation TEXT NOT NULL DEFAULT 'affects',
  UNIQUE(project_id, tenant_id, source_type, source_id, target_type, target_id, relation)
);
CREATE TABLE IF NOT EXISTS risks (
  risk_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  title TEXT NOT NULL,
  probability TEXT,
  impact TEXT,
  mitigation TEXT,
  status TEXT NOT NULL DEFAULT 'open',
  owner TEXT NOT NULL DEFAULT 'AI',
  trigger TEXT,
  updated_at TEXT NOT NULL,
  version_no INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (risk_id, project_id, tenant_id)
);
CREATE TABLE IF NOT EXISTS changes (
  change_id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  object_type TEXT NOT NULL,
  object_id TEXT NOT NULL,
  action TEXT NOT NULL,
  before_json TEXT,
  after_json TEXT,
  reason TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS gates (
  gate_record_id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  gate TEXT NOT NULL,
  result TEXT NOT NULL,
  checks_json TEXT NOT NULL DEFAULT '{}',
  approved_by TEXT NOT NULL DEFAULT 'AI-internal',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
  entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  project_id TEXT,
  tenant_id TEXT,
  timestamp TEXT NOT NULL,
  before_json TEXT,
  after_json TEXT
);
CREATE TABLE IF NOT EXISTS checkpoints (
  checkpoint_id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  data_json TEXT NOT NULL,
  summary_json TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS backups (
  backup_id INTEGER PRIMARY KEY AUTOINCREMENT,
  backup_path TEXT NOT NULL,
  checksum TEXT NOT NULL,
  size INTEGER,
  created_at TEXT NOT NULL
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class OptimisticLockError(Exception):
    """乐观锁冲突：目标行的 version_no 与期望不一致。"""


class ProjectNotFoundError(Exception):
    """在指定 tenant 下找不到项目。"""


class TenantNotFoundError(Exception):
    """找不到租户。"""


class AIPDStateDB:
    """多租户多项目 SQLite 状态存储。"""

    def __init__(self, db_path: str, encryption_key: str = ""):
        self.path = Path(db_path)
        self._encryption_key = encryption_key
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

    # ------------------------------------------------------------------ helper
    def _update(self, c: sqlite3.Connection, table: str, set_cols: List[str],
                set_values: List[Any], where_cols: List[str], where_values: List[Any],
                expected_version: int) -> int:
        """乐观更新：``SET <set_cols..., version_no=version_no+1>``，WHERE 拼版本条件。"""
        set_sql = ", ".join([f"{col}=?" for col in set_cols] + ["version_no = version_no + 1"])
        where_sql = " AND ".join([f"{col}=?" for col in where_cols]) + " AND version_no=?"
        params = list(set_values) + list(where_values) + [expected_version]
        cur = c.execute(f"UPDATE {table} SET {set_sql} WHERE {where_sql}", params)
        if cur.rowcount != 1:
            raise OptimisticLockError(f"{table} optimistic-lock conflict (version mismatch)")
        return cur.rowcount

    def _store_value(self, key: str, value: Any) -> str:
        if self._encryption_key and key in SENSITIVE_KEYS:
            return _json({"__encrypted__": True, "data": encrypt_secret(_json(value), self._encryption_key)})
        return _json(value)

    def _read_value(self, key: str, value_json: str) -> Any:
        try:
            d = json.loads(value_json)
        except json.JSONDecodeError:
            return value_json
        if isinstance(d, dict) and d.get("__encrypted__"):
            if not self._encryption_key:
                raise ValueError(f"field {key!r} is encrypted but no encryption_key configured")
            return json.loads(decrypt_secret(d["data"], self._encryption_key))
        return d

    # -------------------------------------------------------------- tenants
    def create_tenant(self, tenant_id: str, name: Optional[str] = None) -> None:
        with self.connect() as c:
            c.execute("INSERT OR IGNORE INTO tenants(tenant_id,name,created_at) VALUES(?,?,?)",
                      (tenant_id, name or tenant_id, now_iso()))

    def get_tenant(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        with self.connect() as c:
            row = c.execute("SELECT * FROM tenants WHERE tenant_id=?", (tenant_id,)).fetchone()
        return dict(row) if row else None

    def ensure_default_tenant(self, tenant_id: str = "default") -> None:
        self.create_tenant(tenant_id, "Default Tenant")

    # --------------------------------------------------------------- users
    def create_user(self, user_id: str, tenant_id: str, username: str,
                    password_hash: str, salt: str) -> None:
        with self.connect() as c:
            c.execute("INSERT INTO users(user_id,tenant_id,username,password_hash,salt,created_at) "
                      "VALUES(?,?,?,?,?,?)",
                      (user_id, tenant_id, username, password_hash, salt, now_iso()))

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        with self.connect() as c:
            row = c.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        return dict(row) if row else None

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self.connect() as c:
            row = c.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        return dict(row) if row else None

    def grant_access(self, user_id: str, tenant_id: str, project_id: Optional[str] = None) -> None:
        # project_id 为 None 时写入 '*'（规范化租户通配），不再写 NULL 行。
        effective = project_id if project_id is not None else "*"
        with self.connect() as c:
            c.execute("INSERT OR IGNORE INTO user_access(user_id,tenant_id,project_id) VALUES(?,?,?)",
                      (user_id, tenant_id, effective))

    def has_access(self, user_id: str, tenant_id: str, project_id: Optional[str] = None) -> bool:
        with self.connect() as c:
            row = c.execute(
                "SELECT 1 FROM user_access WHERE user_id=? AND tenant_id=? "
                "AND (project_id=? OR project_id='*' OR project_id IS NULL)",
                (user_id, tenant_id, project_id)).fetchone()
        return row is not None

    def has_tenant_admin(self, user_id: str, tenant_id: str) -> bool:
        """用户是否为该租户管理员：存在 ``project_id='*'`` 或 NULL 的通配授权行。"""
        with self.connect() as c:
            row = c.execute(
                "SELECT 1 FROM user_access WHERE user_id=? AND tenant_id=? "
                "AND (project_id='*' OR project_id IS NULL)",
                (user_id, tenant_id)).fetchone()
        return row is not None

    # ------------------------------------------------------------- sessions
    def create_session(self, session_id: str, user_id: str, token: str, expires_at: str) -> None:
        with self.connect() as c:
            c.execute("INSERT INTO sessions(session_id,user_id,token,expires_at,created_at) "
                      "VALUES(?,?,?,?,?)",
                      (session_id, user_id, token, expires_at, now_iso()))

    # ------------------------------------------------------------- projects
    def init_project(self, tenant_id: str, project_id: str, name: str, goal: str,
                     owner_policy: str = "AI executes; owner reviews decisions only") -> None:
        ts = now_iso()
        with self.connect() as c:
            c.execute(
                "INSERT INTO projects(project_id,tenant_id,name,goal,gate,status,version,owner_policy,"
                "created_at,updated_at,version_no) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (project_id, tenant_id, name, goal, "G0", "active", "0.1.0", owner_policy, ts, ts, 1))

    def get_project(self, tenant_id: str, project_id: str) -> Dict[str, Any]:
        with self.connect() as c:
            row = c.execute("SELECT * FROM projects WHERE project_id=? AND tenant_id=?",
                            (project_id, tenant_id)).fetchone()
        if not row:
            raise ProjectNotFoundError(f"project {project_id!r} not found in tenant {tenant_id!r}")
        return dict(row)

    def list_projects(self, tenant_id: str) -> List[Dict[str, Any]]:
        with self.connect() as c:
            rows = c.execute("SELECT * FROM projects WHERE tenant_id=? ORDER BY created_at",
                             (tenant_id,)).fetchall()
        return [dict(r) for r in rows]

    def update_project(self, tenant_id: str, project_id: str, expected_version: int,
                       **fields: Any) -> Dict[str, Any]:
        allow = {"name", "goal", "gate", "status", "version", "owner_policy"}
        set_cols = [k for k in fields if k in allow]
        if not set_cols:
            raise ValueError("no editable fields provided")
        if "gate" in fields and not (len(fields["gate"]) == 2 and fields["gate"][0] == "G"
                                     and fields["gate"][1].isdigit()):
            raise ValueError("gate must be G0..G9")
        if "status" in fields and fields["status"] not in PROJECT_STATUSES:
            raise ValueError(f"invalid project status {fields['status']}")
        set_values = [fields[k] for k in set_cols] + [now_iso()]
        with self.connect() as c:
            self._update(c, "projects", set_cols + ["updated_at"], set_values,
                         ["project_id", "tenant_id"], [project_id, tenant_id], expected_version)
        return self.get_project(tenant_id, project_id)

    def delete_project(self, tenant_id: str, project_id: str) -> None:
        with self.connect() as c:
            c.execute("DELETE FROM projects WHERE project_id=? AND tenant_id=?", (project_id, tenant_id))

    # ---------------------------------------------------------------- facts
    def _next_id(self, c: sqlite3.Connection, table: str, column: str, prefix: str) -> str:
        values = [r[0] for r in c.execute(f"SELECT {column} FROM {table}").fetchall()]
        nums = []
        for value in values:
            if isinstance(value, str) and value.startswith(prefix + "-"):
                try:
                    nums.append(int(value.split("-")[-1]))
                except ValueError:
                    # noqa: EMPTY_EXCEPT - 跳过非数字后缀的既有 id（合法 id 过滤）
                    pass
        return f"{prefix}-{max(nums, default=0) + 1:03d}"

    def add_fact(self, tenant_id: str, project_id: str, key: str, value: Any, status: str,
                 unit: Optional[str] = None, tolerance: Optional[str] = None,
                 conditions: Optional[str] = None, confidence: float = 0.5,
                 source: Optional[str] = None, version: Optional[str] = None) -> str:
        if status not in FACT_STATUSES:
            raise ValueError(f"Invalid fact status: {status}")
        if not 0 <= confidence <= 1:
            raise ValueError("confidence must be in [0,1]")
        ts = now_iso()
        with self.connect() as c:
            fact_id = self._next_id(c, "facts", "fact_id", "F")
            c.execute("INSERT INTO facts(fact_id,project_id,tenant_id,key,value_json,unit,tolerance,"
                      "conditions,status,confidence,source,version,created_at,updated_at,version_no) "
                      "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (fact_id, project_id, tenant_id, key, self._store_value(key, value), unit,
                       tolerance, conditions, status, confidence, source, version, ts, ts, 1))
            c.execute("INSERT INTO changes(project_id,tenant_id,object_type,object_id,action,after_json,"
                      "reason,created_at) VALUES(?,?,?,?,?,?,?,?)",
                      (project_id, tenant_id, "fact", fact_id, "create",
                       _json({"key": key, "value": value, "status": status}), "add fact", ts))
        return fact_id

    def list_facts(self, tenant_id: str, project_id: str) -> List[Dict[str, Any]]:
        with self.connect() as c:
            rows = c.execute("SELECT * FROM facts WHERE tenant_id=? AND project_id=? ORDER BY created_at",
                             (tenant_id, project_id)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["value"] = self._read_value(d["key"], d.pop("value_json"))
            out.append(d)
        return out

    def get_fact(self, tenant_id: str, project_id: str, fact_id: str) -> Dict[str, Any]:
        with self.connect() as c:
            row = c.execute("SELECT * FROM facts WHERE tenant_id=? AND project_id=? AND fact_id=?",
                            (tenant_id, project_id, fact_id)).fetchone()
        if not row:
            raise KeyError(fact_id)
        d = dict(row)
        d["value"] = self._read_value(d["key"], d.pop("value_json"))
        return d

    def update_fact(self, tenant_id: str, project_id: str, fact_id: str, expected_version: int,
                    **fields: Any) -> Dict[str, Any]:
        allow = {"value", "status", "confidence", "unit", "tolerance", "conditions", "source", "version"}
        set_cols = [k for k in fields if k in allow]
        if not set_cols:
            raise ValueError("no editable fields provided")
        cur = self.get_fact(tenant_id, project_id, fact_id)
        col_map = {"value": "value_json"}
        set_db_cols = [col_map.get(k, k) for k in set_cols]
        set_values = []
        for k in set_cols:
            if k == "value":
                set_values.append(self._store_value(cur["key"], fields[k]))
            elif k == "confidence":
                if not 0 <= fields[k] <= 1:
                    raise ValueError("confidence must be in [0,1]")
                set_values.append(fields[k])
            else:
                set_values.append(fields[k])
        set_values.append(now_iso())
        with self.connect() as c:
            self._update(c, "facts", set_db_cols + ["updated_at"], set_values,
                         ["tenant_id", "project_id", "fact_id"],
                         [tenant_id, project_id, fact_id], expected_version)
        return self.get_fact(tenant_id, project_id, fact_id)

    def delete_fact(self, tenant_id: str, project_id: str, fact_id: str) -> None:
        with self.connect() as c:
            c.execute("DELETE FROM facts WHERE tenant_id=? AND project_id=? AND fact_id=?",
                      (tenant_id, project_id, fact_id))

    # ------------------------------------------------------------- evidence
    def add_evidence(self, tenant_id: str, project_id: str, kind: str, title: str,
                     url: Optional[str] = None, identifier: Optional[str] = None,
                     quality: Optional[str] = None, summary: Optional[str] = None,
                     metadata: Optional[Dict[str, Any]] = None,
                     accessed_at: Optional[str] = None) -> str:
        ts = now_iso()
        with self.connect() as c:
            eid = self._next_id(c, "evidence", "evidence_id", "E")
            c.execute("INSERT INTO evidence(evidence_id,project_id,tenant_id,kind,title,url,identifier,"
                      "accessed_at,quality,summary,metadata_json,created_at,version_no) "
                      "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (eid, project_id, tenant_id, kind, title, url, identifier, accessed_at or ts,
                       quality, summary, _json(metadata or {}), ts, 1))
        return eid

    def list_evidence(self, tenant_id: str, project_id: str) -> List[Dict[str, Any]]:
        with self.connect() as c:
            rows = c.execute("SELECT * FROM evidence WHERE tenant_id=? AND project_id=? ORDER BY created_at",
                             (tenant_id, project_id)).fetchall()
        return [dict(r) for r in rows]

    def link_evidence(self, tenant_id: str, project_id: str, fact_id: str,
                      evidence_id: str, relation: str = "supports") -> None:
        with self.connect() as c:
            c.execute("INSERT OR IGNORE INTO fact_evidence(fact_id,project_id,tenant_id,evidence_id,relation) "
                      "VALUES(?,?,?,?,?)", (fact_id, project_id, tenant_id, evidence_id, relation))

    def list_evidence_for_fact(self, tenant_id: str, project_id: str, fact_id: str) -> List[Dict[str, Any]]:
        """返回关联到某事实的证据列表（含关系）。"""
        with self.connect() as c:
            rows = c.execute(
                "SELECT e.*, fe.relation FROM evidence e "
                "JOIN fact_evidence fe ON fe.evidence_id=e.evidence_id "
                "AND fe.project_id=e.project_id AND fe.tenant_id=e.tenant_id "
                "WHERE fe.tenant_id=? AND fe.project_id=? AND fe.fact_id=? ORDER BY e.created_at",
                (tenant_id, project_id, fact_id)).fetchall()
        return [dict(r) for r in rows]

    def update_evidence_metadata(self, tenant_id: str, project_id: str, evidence_id: str,
                                 metadata: Dict[str, Any]) -> None:
        """整体替换单条证据的 metadata_json。"""
        with self.connect() as c:
            cur = c.execute("SELECT version_no FROM evidence WHERE tenant_id=? AND project_id=? "
                            "AND evidence_id=?", (tenant_id, project_id, evidence_id)).fetchone()
            if not cur:
                raise KeyError(evidence_id)
            c.execute("UPDATE evidence SET metadata_json=?, version_no=version_no+1 "
                      "WHERE tenant_id=? AND project_id=? AND evidence_id=? AND version_no=?",
                      (_json(metadata), tenant_id, project_id, evidence_id, cur["version_no"]))

    # ------------------------------------------------------------ decisions
    def propose_decision(self, tenant_id: str, project_id: str, topic: str,
                         recommendation: str, options: Any, trigger: Optional[str] = None) -> str:
        ts = now_iso()
        with self.connect() as c:
            did = self._next_id(c, "decisions", "decision_id", "D")
            c.execute("INSERT INTO decisions(decision_id,project_id,tenant_id,topic,trigger,recommendation,"
                      "options_json,status,created_at,version_no) VALUES(?,?,?,?,?,?,?,?,?,?)",
                      (did, project_id, tenant_id, topic, trigger, recommendation, _json(options),
                       "proposed", ts, 1))
            c.execute("UPDATE projects SET status='awaiting_owner_decision',updated_at=? "
                      "WHERE tenant_id=? AND project_id=?", (ts, tenant_id, project_id))
        return did

    def resolve_decision(self, tenant_id: str, project_id: str, decision_id: str,
                         choice: str, comment: Optional[str] = None) -> None:
        ts = now_iso()
        with self.connect() as c:
            row = c.execute("SELECT * FROM decisions WHERE tenant_id=? AND project_id=? AND decision_id=?",
                            (tenant_id, project_id, decision_id)).fetchone()
            if not row:
                raise KeyError(decision_id)
            c.execute("UPDATE decisions SET status='resolved',choice=?,comment=?,resolved_at=?,"
                      "version_no=version_no+1 WHERE tenant_id=? AND project_id=? AND decision_id=?",
                      (choice, comment, ts, tenant_id, project_id, decision_id))
            open_count = c.execute("SELECT COUNT(*) FROM decisions WHERE tenant_id=? AND project_id=? "
                                   "AND status='proposed'", (tenant_id, project_id)).fetchone()[0]
            new_status = "awaiting_owner_decision" if open_count else "active"
            c.execute("UPDATE projects SET status=?,updated_at=? WHERE tenant_id=? AND project_id=?",
                      (new_status, ts, tenant_id, project_id))

    def list_decisions(self, tenant_id: str, project_id: str) -> List[Dict[str, Any]]:
        with self.connect() as c:
            rows = c.execute("SELECT * FROM decisions WHERE tenant_id=? AND project_id=? ORDER BY created_at",
                             (tenant_id, project_id)).fetchall()
        return [dict(r) for r in rows]

    def list_open_decisions(self, tenant_id: str, project_id: str) -> List[Dict[str, Any]]:
        with self.connect() as c:
            rows = c.execute("SELECT * FROM decisions WHERE tenant_id=? AND project_id=? AND status='proposed' "
                             "ORDER BY created_at", (tenant_id, project_id)).fetchall()
        return [dict(r) for r in rows]

    def list_resolved_decisions(self, tenant_id: str, project_id: str) -> List[Dict[str, Any]]:
        with self.connect() as c:
            rows = c.execute("SELECT * FROM decisions WHERE tenant_id=? AND project_id=? AND status='resolved' "
                             "ORDER BY created_at", (tenant_id, project_id)).fetchall()
        return [dict(r) for r in rows]

    # ---------------------------------------------------------- deliverables
    def add_deliverable(self, tenant_id: str, project_id: str, dtype: str,
                        path: Optional[str] = None, status: str = "planned",
                        version: Optional[str] = None, gate: Optional[str] = None,
                        metadata: Optional[Dict[str, Any]] = None) -> str:
        ts = now_iso()
        with self.connect() as c:
            did = self._next_id(c, "deliverables", "deliverable_id", "DEL")
            c.execute("INSERT INTO deliverables(deliverable_id,project_id,tenant_id,type,path,status,version,"
                      "gate,metadata_json,updated_at,version_no) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                      (did, project_id, tenant_id, dtype, path, status, version, gate,
                       _json(metadata or {}), ts, 1))
        return did

    def list_deliverables(self, tenant_id: str, project_id: str) -> List[Dict[str, Any]]:
        with self.connect() as c:
            rows = c.execute("SELECT * FROM deliverables WHERE tenant_id=? AND project_id=? ORDER BY updated_at",
                             (tenant_id, project_id)).fetchall()
        return [dict(r) for r in rows]

    def update_deliverable(self, tenant_id: str, project_id: str, deliverable_id: str,
                           expected_version: int, **fields: Any) -> Dict[str, Any]:
        allow = {"type", "path", "status", "version", "gate", "metadata"}
        set_cols = [k for k in fields if k in allow]
        if not set_cols:
            raise ValueError("no editable fields provided")
        values = []
        for k in set_cols:
            if k == "metadata":
                values.append(_json(fields[k]))
            else:
                values.append(fields[k])
        set_values = values + [now_iso()]
        with self.connect() as c:
            self._update(c, "deliverables", set_cols + ["updated_at"], set_values,
                         ["tenant_id", "project_id", "deliverable_id"],
                         [tenant_id, project_id, deliverable_id], expected_version)
        with self.connect() as c:
            rows = c.execute("SELECT * FROM deliverables WHERE tenant_id=? AND project_id=? AND deliverable_id=?",
                             (tenant_id, project_id, deliverable_id)).fetchall()
        return dict(rows[0])

    # ----------------------------------------------------------------- risks
    def add_risk(self, tenant_id: str, project_id: str, title: str,
                 probability: Optional[str] = None, impact: Optional[str] = None,
                 mitigation: Optional[str] = None, status: str = "open",
                 trigger: Optional[str] = None) -> str:
        ts = now_iso()
        with self.connect() as c:
            rid = self._next_id(c, "risks", "risk_id", "RISK")
            c.execute("INSERT INTO risks(risk_id,project_id,tenant_id,title,probability,impact,mitigation,"
                      "status,owner,trigger,updated_at,version_no) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                      (rid, project_id, tenant_id, title, probability, impact, mitigation, status, "AI",
                       trigger, ts, 1))
        return rid

    def list_risks(self, tenant_id: str, project_id: str) -> List[Dict[str, Any]]:
        with self.connect() as c:
            rows = c.execute("SELECT * FROM risks WHERE tenant_id=? AND project_id=? ORDER BY updated_at DESC",
                             (tenant_id, project_id)).fetchall()
        return [dict(r) for r in rows]

    def update_risk(self, tenant_id: str, project_id: str, risk_id: str,
                    expected_version: int, **fields: Any) -> Dict[str, Any]:
        allow = {"title", "probability", "impact", "mitigation", "status", "owner", "trigger"}
        set_cols = [k for k in fields if k in allow]
        if not set_cols:
            raise ValueError("no editable fields provided")
        set_values = [fields[k] for k in set_cols] + [now_iso()]
        with self.connect() as c:
            self._update(c, "risks", set_cols + ["updated_at"], set_values,
                         ["tenant_id", "project_id", "risk_id"],
                         [tenant_id, project_id, risk_id], expected_version)
        with self.connect() as c:
            rows = c.execute("SELECT * FROM risks WHERE tenant_id=? AND project_id=? AND risk_id=?",
                             (tenant_id, project_id, risk_id)).fetchall()
        return dict(rows[0])

    # ---------------------------------------------------------- dependencies
    def add_dependency(self, tenant_id: str, project_id: str, source_type: str, source_id: str,
                       target_type: str, target_id: str, relation: str = "affects") -> None:
        with self.connect() as c:
            c.execute("INSERT OR IGNORE INTO dependencies(project_id,tenant_id,source_type,source_id,"
                      "target_type,target_id,relation) VALUES(?,?,?,?,?,?,?)",
                      (project_id, tenant_id, source_type, source_id, target_type, target_id, relation))

    def list_dependencies(self, tenant_id: str, project_id: str) -> List[Dict[str, Any]]:
        with self.connect() as c:
            rows = c.execute("SELECT * FROM dependencies WHERE tenant_id=? AND project_id=?",
                             (tenant_id, project_id)).fetchall()
        return [dict(r) for r in rows]

    # ---------------------------------------------------------------- gates
    def add_gate(self, tenant_id: str, project_id: str, gate: str, result: str,
                 checks: Dict[str, Any] = None, approved_by: str = "AI-internal") -> None:
        ts = now_iso()
        with self.connect() as c:
            c.execute("INSERT INTO gates(project_id,tenant_id,gate,result,checks_json,approved_by,created_at) "
                      "VALUES(?,?,?,?,?,?,?)",
                      (project_id, tenant_id, gate, result, _json(checks or {}), approved_by, ts))

    def list_gates(self, tenant_id: str, project_id: str) -> List[Dict[str, Any]]:
        with self.connect() as c:
            rows = c.execute("SELECT * FROM gates WHERE tenant_id=? AND project_id=? ORDER BY created_at",
                             (tenant_id, project_id)).fetchall()
        return [dict(r) for r in rows]

    # --------------------------------------------------------------- changes
    def add_change(self, tenant_id: str, project_id: str, object_type: str, object_id: str,
                   action: str, before: Any = None, after: Any = None, reason: Optional[str] = None) -> None:
        with self.connect() as c:
            c.execute("INSERT INTO changes(project_id,tenant_id,object_type,object_id,action,before_json,"
                      "after_json,reason,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                      (project_id, tenant_id, object_type, object_id, action,
                       _json(before) if before is not None else None,
                       _json(after) if after is not None else None, reason, now_iso()))

    def list_changes(self, tenant_id: str, project_id: str) -> List[Dict[str, Any]]:
        with self.connect() as c:
            rows = c.execute("SELECT * FROM changes WHERE tenant_id=? AND project_id=? ORDER BY created_at",
                             (tenant_id, project_id)).fetchall()
        return [dict(r) for r in rows]

    # ---------------------------------------------------------- audit log
    def add_audit(self, actor: str, action: str, project_id: Optional[str],
                  tenant_id: Optional[str], before: Any = None, after: Any = None) -> None:
        with self.connect() as c:
            c.execute("INSERT INTO audit_log(actor,action,project_id,tenant_id,timestamp,before_json,after_json) "
                      "VALUES(?,?,?,?,?,?,?)",
                      (actor, action, project_id, tenant_id, now_iso(),
                       _json(before) if before is not None else None,
                       _json(after) if after is not None else None))

    def list_audit(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self.connect() as c:
            rows = c.execute("SELECT * FROM audit_log ORDER BY entry_id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    # ---------------------------------------------------------- checkpoints
    def save_checkpoint(self, tenant_id: str, project_id: str, data: Any,
                        summary: Any = None) -> int:
        ts = now_iso()
        with self.connect() as c:
            cur = c.execute("INSERT INTO checkpoints(project_id,tenant_id,data_json,summary_json,created_at) "
                            "VALUES(?,?,?,?,?)",
                            (project_id, tenant_id, _json(data),
                             _json(summary) if summary is not None else None, ts))
            return int(cur.lastrowid)

    def latest_checkpoint(self, tenant_id: str, project_id: str) -> Optional[Dict[str, Any]]:
        with self.connect() as c:
            row = c.execute("SELECT * FROM checkpoints WHERE tenant_id=? AND project_id=? "
                            "ORDER BY checkpoint_id DESC LIMIT 1", (tenant_id, project_id)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["data"] = json.loads(d.pop("data_json"))
        d["summary"] = json.loads(d.pop("summary_json")) if d.get("summary_json") else None
        return d

    # ---------------------------------------------------------------- backups
    def add_backup(self, backup_path: str, checksum: str, size: int = 0) -> None:
        with self.connect() as c:
            c.execute("INSERT INTO backups(backup_path,checksum,size,created_at) VALUES(?,?,?,?)",
                      (backup_path, checksum, size, now_iso()))

    def list_backups(self) -> List[Dict[str, Any]]:
        with self.connect() as c:
            rows = c.execute("SELECT * FROM backups ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

    # ----------------------------------------------------- summary / export
    def summary(self, tenant_id: str, project_id: str) -> Dict[str, Any]:
        p = self.get_project(tenant_id, project_id)
        with self.connect() as c:
            fact_counts = {r["status"]: r["n"] for r in c.execute(
                "SELECT status, COUNT(*) n FROM facts WHERE tenant_id=? AND project_id=? GROUP BY status",
                (tenant_id, project_id))}
            counts = {t: c.execute(f"SELECT COUNT(*) FROM {t} WHERE tenant_id=? AND project_id=?",
                                   (tenant_id, project_id)).fetchone()[0]
                      for t in ["facts", "evidence", "decisions", "deliverables", "risks"]}
            open_decisions = c.execute("SELECT decision_id,topic,recommendation FROM decisions "
                                       "WHERE tenant_id=? AND project_id=? AND status='proposed'",
                                       (tenant_id, project_id)).fetchall()
            top_risks = c.execute("SELECT risk_id,title,probability,impact FROM risks "
                                  "WHERE tenant_id=? AND project_id=? AND status='open' "
                                  "ORDER BY updated_at DESC LIMIT 5", (tenant_id, project_id)).fetchall()
        return {"project": p, "counts": counts, "fact_statuses": fact_counts,
                "open_decisions": [dict(r) for r in open_decisions],
                "top_open_risks": [dict(r) for r in top_risks]}

    def export(self, tenant_id: str, project_id: str) -> Dict[str, Any]:
        return {
            "project": self.get_project(tenant_id, project_id),
            "facts": self.list_facts(tenant_id, project_id),
            "evidence": self.list_evidence(tenant_id, project_id),
            "decisions": self.list_decisions(tenant_id, project_id),
            "deliverables": self.list_deliverables(tenant_id, project_id),
            "risks": self.list_risks(tenant_id, project_id),
            "dependencies": self.list_dependencies(tenant_id, project_id),
            "changes": self.list_changes(tenant_id, project_id),
            "gates": self.list_gates(tenant_id, project_id),
        }


__all__ = ["AIPDStateDB", "SCHEMA", "OptimisticLockError", "ProjectNotFoundError",
           "TenantNotFoundError", "SENSITIVE_KEYS", "now_iso"]
