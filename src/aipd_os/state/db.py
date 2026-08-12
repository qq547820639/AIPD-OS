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

import hashlib
import json
import logging
import sqlite3
import threading
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
# 认知/分类状态（epistemic_status）。U=Unknown / 未验证（无证据、未确认的认知状态）。
# 正式语义（v5.8.2 锁定，三正交维度之一；禁止与 ClaimAssessment/definition_status 混用）：
#   V=Verified（正式确认：实测/正式文件/Owner 明确确认）
#   S=Simulation（模拟/仿真支持；非实测）
#   C=Calculation（可复核计算）
#   E=External evidence（可靠外部证据）
#   A=Assumption（假设，未验证）
#   P=Pending（待第三方确认）
#   T=Testable（待测试）
#   U=Unknown（未知）
#   R=Retired（已退役；不是 Rejected）
# 注意：expiry.py 用 "S" 标记 stale、supply_chain 用 "S" 标记 superseded、
# experience 用 "C" 表示 owner-instruction 确认 —— 均为对既有状态位的历史复用
# （见 docs/architecture/STATUS_SEMANTICS.md §1.2），新代码不得新增此类复用。
FACT_STATUSES = {"V", "S", "C", "E", "A", "P", "T", "R", "U"}
PROJECT_STATUSES = {"active", "awaiting_owner_decision", "blocked_external",
                    "internal_rework", "released", "archived"}

# 明文存储告警只打一次（避免每个敏感字段写入都刷日志）。
_plaintext_warned = False

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
  -- v5.8.1 Commit 9：generic lineage 扩展列（migration v6）
  created_at TEXT NOT NULL DEFAULT '',
  provenance TEXT NOT NULL DEFAULT '{}',
  version_no INTEGER NOT NULL DEFAULT 1,
  -- v5.8.2 Commit 5：边失效列（migration v8；soft-retire，不物理删除）
  retired_at TEXT,
  retired_by TEXT,
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
-- v5.8 Idea & Evidence Foundation（Commit 9/10/11）：
-- ideas / claims / claim_evidence_relations 由 Idea/Claim/EvidenceRelation 域使用。
-- 均为幂等 CREATE TABLE IF NOT EXISTS；迁移版本见 migrations.py v2/v3/v4。
CREATE TABLE IF NOT EXISTS ideas (
  idea_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL DEFAULT 'default',
  title TEXT NOT NULL DEFAULT '',
  raw_input TEXT NOT NULL DEFAULT '',
  goal TEXT NOT NULL DEFAULT '',
  problem TEXT NOT NULL DEFAULT '',
  target_user TEXT NOT NULL DEFAULT '',
  desired_outcome TEXT NOT NULL DEFAULT '',
  constraints_json TEXT NOT NULL DEFAULT '{}',
  source TEXT NOT NULL DEFAULT '',
  lifecycle_status TEXT NOT NULL DEFAULT 'raw',
  version_no INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (idea_id, project_id, tenant_id)
);
CREATE TABLE IF NOT EXISTS claims (
  claim_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL DEFAULT 'default',
  idea_id TEXT NOT NULL DEFAULT '',
  claim_type TEXT NOT NULL,
  statement TEXT NOT NULL,
  epistemic_status TEXT NOT NULL DEFAULT 'A',
  lifecycle_status TEXT NOT NULL DEFAULT 'active',
  confidence REAL,
  source TEXT NOT NULL DEFAULT '',
  version_no INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (claim_id, project_id, tenant_id)
);
CREATE TABLE IF NOT EXISTS claim_evidence_relations (
  relation_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL DEFAULT 'default',
  claim_id TEXT NOT NULL,
  evidence_id TEXT NOT NULL,
  relation_type TEXT NOT NULL,
  strength REAL,
  applicability TEXT NOT NULL DEFAULT '',
  reasoning_summary TEXT NOT NULL DEFAULT '',
  limitations TEXT NOT NULL DEFAULT '',
  review_status TEXT NOT NULL DEFAULT 'pending',
  created_by TEXT NOT NULL DEFAULT 'system',
  version_no INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (relation_id, project_id, tenant_id),
  UNIQUE (claim_id, evidence_id, relation_type, project_id, tenant_id)
);
-- v5.8.1 Commit 7：id_sequences —— 并发安全 ID 分配（migration v5）。
-- 本 SCHEMA 常量仅是「目标 schema 参考」（见文件头 authority 注释）；
-- 实际建库由 migration runner（migrations.py）负责。
CREATE TABLE IF NOT EXISTS id_sequences (
  name TEXT PRIMARY KEY,
  next_val INTEGER NOT NULL
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


# 事务上下文（thread-local；connect 在事务内复用活动连接）
_db_tls = threading.local()


class AIPDStateDB:
    """多租户多项目 SQLite 状态存储。

    v5.8.1 Commit 8（schema authority 收口）：**migration runner 是唯一
    schema authority** —— 新建库/既有库升级统一走 ``migrations.migrate()``
    （v1..v5 全链），不再旁路 ``executescript(SCHEMA)``。
    ``db.SCHEMA`` 仅作为「目标 schema 参考」保留（不再被 __init__ 执行）。
    """

    def __init__(self, db_path: str, encryption_key: str = ""):
        self.path = Path(db_path)
        self._encryption_key = encryption_key
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # 唯一 schema authority：迁移 runner（v1..v5 全链；幂等）
        from .migrations import migrate
        migrate(str(self.path))

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        # v5.9.1：事务内复用活动连接（不 commit/close）—— 同一事务的所有
        # 语句（含 helper 内部 connect）落在同一连接上，保证原子性且无
        # SQLite 写锁自死锁（历史 add_edge→add_audit 锁问题的根因修复）。
        active = getattr(_db_tls, "tx_conn", None)
        if active is not None:
            yield active
            return
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

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """显式事务上下文（v5.9.1，P0-05/19）。

        - 顶层事务：BEGIN → 所有经 :meth:`connect` 的语句复用同一连接 →
          COMMIT；异常 → ROLLBACK（任何失败 = 无部分写入）；
        - 嵌套事务：SAVEPOINT（不重复 BEGIN）；
        - 禁止在内部 helper 偷偷 commit 破坏原子性（connect 在事务内
          不 commit）。

        用法::

            with db.transaction() as c:
                c.execute(...)           # 直接 SQL
                db.add_audit(...)        # helper（复用活动连接）
        """
        active = getattr(_db_tls, "tx_conn", None)
        if active is not None:
            # 嵌套：SAVEPOINT
            depth = _db_tls.tx_depth
            _db_tls.tx_depth = depth + 1
            conn = active
            conn.execute(f"SAVEPOINT sp_{depth}")
            try:
                yield conn
                conn.execute(f"RELEASE SAVEPOINT sp_{depth}")
            except Exception:
                conn.execute(f"ROLLBACK TO SAVEPOINT sp_{depth}")
                raise
            finally:
                _db_tls.tx_depth = depth
            return
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.isolation_level = None  # autocommit；显式 BEGIN/COMMIT/ROLLBACK
        conn.execute("BEGIN")
        _db_tls.tx_conn = conn
        _db_tls.tx_depth = 0
        try:
            yield conn
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()
            _db_tls.tx_conn = None
            _db_tls.tx_depth = 0

    # ------------------------------------------------------------------ helper
    def next_sequence(self, name: str, prefix: str,
                      digits: int = 3) -> str:
        """原子分配带格式的 display id（v5.8.1 Commit 7）。

        基于 ``id_sequences`` 表（migration v5）的 atomic UPSERT：
        - 首次调用插入 (name, 1) → 返回 ``{prefix}-001``；
        - 后续调用 ``ON CONFLICT DO UPDATE next_val=next_val+1`` → 串行化，
          无 scan-max 并发 race（SQLite 写锁保证同一时刻只有一个递增）。
        """
        with self.connect() as c:
            c.execute(
                "INSERT INTO id_sequences(name, next_val) VALUES(?, ?) "
                "ON CONFLICT(name) DO UPDATE SET next_val = next_val + 1",
                (name, 1))
            row = c.execute(
                "SELECT next_val FROM id_sequences WHERE name=?", (name,)).fetchone()
            if row is None:
                raise RuntimeError(f"id_sequences missing row for {name!r}")
            n = int(row["next_val"])
        return f"{prefix}-{n:0{digits}d}"

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
        global _plaintext_warned
        if self._encryption_key and key in SENSITIVE_KEYS:
            return _json({"__encrypted__": True, "data": encrypt_secret(_json(value), self._encryption_key)})
        if key in SENSITIVE_KEYS and not _plaintext_warned:
            # 无 encryption_key 时敏感字段明文落库：fail-open 仅限本地/dev 模式，
            # 生产 server 模式已在 StateService 层 fail-closed。
            _plaintext_warned = True
            logging.warning(
                "sensitive field %r stored in plaintext: no AIPD_ENCRYPTION_KEY "
                "configured (local/dev only; server mode fails closed)", key)
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
            fact_id = self.next_sequence("fact", "F")
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
        # v5.8.1 Commit 15（QA）：evidence_id 走 id_sequences 原子分配
        # （同 idea/claim/relation 一致；保留 E-001 display 格式）。
        eid = self.next_sequence("evidence", "E")
        with self.connect() as c:
            c.execute("INSERT INTO evidence(evidence_id,project_id,tenant_id,kind,title,url,identifier,"
                      "accessed_at,quality,summary,metadata_json,created_at,version_no) "
                      "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (eid, project_id, tenant_id, kind, title, url, identifier, accessed_at or ts,
                       quality, summary, _json(metadata or {}), ts, 1))
        return eid

    # ------------------------------------------------------------------
    # Evidence 去重 identity（v5.8.1 Commit 6）
    # ------------------------------------------------------------------
    @staticmethod
    def _canonical_url(url: str) -> str:
        """规范化 URL 用于 identity：去空白、去尾斜杠、小写。"""
        return str(url or "").strip().rstrip("/").lower()

    @staticmethod
    def _normalize_id(value: Any) -> str:
        """规范化 identity 标识（doi/arxiv_id/identifier）。"""
        return str(value or "").strip().lower()

    @staticmethod
    def _title_year_hash(title: str, year: Any) -> str:
        """normalized(title+year) hash（低优先 identity）。"""
        raw = f"{str(title or '').strip().lower()}|{year or ''}".encode()
        return hashlib.sha256(raw).hexdigest()[:32]

    @staticmethod
    def _evidence_identity_keys(row: dict[str, Any]) -> set:
        """从一条 evidence 行推导 identity keys（set of (kind, value)）。

        来源：metadata_json.source_metadata.{doi,arxiv_id}、identifier 列、
        canonical url 列、normalized(title+year) hash。
        """
        keys = set()
        try:
            md = json.loads(row.get("metadata_json") or "{}")
        except (ValueError, TypeError):
            md = {}
        src_md = md.get("source_metadata") or {}
        if src_md.get("doi"):
            keys.add(("doi", AIPDStateDB._normalize_id(src_md["doi"])))
        if src_md.get("arxiv_id"):
            keys.add(("arxiv_id", AIPDStateDB._normalize_id(src_md["arxiv_id"])))
        if row.get("identifier"):
            keys.add(("identifier", AIPDStateDB._normalize_id(row["identifier"])))
        if row.get("url"):
            keys.add(("url", AIPDStateDB._canonical_url(row["url"])))
        keys.add(("title_year", AIPDStateDB._title_year_hash(
            row.get("title"), src_md.get("year"))))
        return keys

    def get_or_create_evidence(self, tenant_id: str, project_id: str, *,
                               kind: str, title: str, url: str | None = None,
                               identifier: str | None = None,
                               doi: str | None = None,
                               arxiv_id: str | None = None,
                               metadata: dict[str, Any] | None = None) -> str:
        """按 identity 去重的 evidence 写入（v5.8.1 Commit 6）。

        同一 tenant+project 内按 identity 去重，优先级：
        doi → arxiv_id → OpenAlex/Semantic Scholar id（identifier）→
        normalized canonical URL → normalized(title+year) hash。

        - 命中已有 Evidence → 返回现有 evidence_id（把新 provenance/
          retrieval_context 合并进 metadata，不新建）；
        - 未命中 → 新建 Evidence 并返回新 evidence_id。

        doi/arxiv_id 存储在 metadata_json.source_metadata（避免 schema 变更；
        去重以 metadata 为准）。
        """
        metadata = dict(metadata or {})
        # 确保 identity 字段进入 source_metadata
        src_md = dict(metadata.get("source_metadata") or {})
        if doi and not src_md.get("doi"):
            src_md["doi"] = doi
        if arxiv_id and not src_md.get("arxiv_id"):
            src_md["arxiv_id"] = arxiv_id
        metadata["source_metadata"] = src_md

        # candidate identity keys（优先级顺序）
        candidate_keys: list[tuple] = []
        if doi:
            candidate_keys.append(("doi", self._normalize_id(doi)))
        if arxiv_id:
            candidate_keys.append(("arxiv_id", self._normalize_id(arxiv_id)))
        if identifier:
            candidate_keys.append(("identifier", self._normalize_id(identifier)))
        if url:
            candidate_keys.append(("url", self._canonical_url(url)))
        candidate_keys.append(("title_year", self._title_year_hash(
            title, src_md.get("year"))))

        with self.connect() as c:
            rows = c.execute(
                "SELECT * FROM evidence WHERE tenant_id=? AND project_id=?",
                (tenant_id, project_id)).fetchall()
        row_keys = [self._evidence_identity_keys(dict(r)) for r in rows]
        for kind_key, value in candidate_keys:
            for row, keys in zip(rows, row_keys):
                if (kind_key, value) in keys:
                    # 命中：合并 provenance / retrieval_context 到 metadata
                    return self._merge_evidence_provenance(
                        tenant_id, project_id, dict(row), metadata)

        ts = now_iso()
        with self.connect() as c:
            eid = self.next_sequence("evidence", "E")
            c.execute(
                "INSERT INTO evidence(evidence_id,project_id,tenant_id,kind,title,"
                "url,identifier,accessed_at,quality,summary,metadata_json,"
                "created_at,version_no) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (eid, project_id, tenant_id, kind, title, url, identifier, ts,
                 None, None, _json(metadata), ts, 1))
        return eid

    def _merge_evidence_provenance(self, tenant_id: str, project_id: str,
                                   existing: dict[str, Any],
                                   new_metadata: dict[str, Any]) -> str:
        """把新 provenance / retrieval_context 合并进已有 evidence 的 metadata。"""
        try:
            md = json.loads(existing.get("metadata_json") or "{}")
        except (ValueError, TypeError):
            md = {}
        # 合并 provenance（latest wins；只填非空）
        prov = new_metadata.get("provenance") or {}
        if prov:
            merged_prov = dict(md.get("provenance") or {})
            for k, v in prov.items():
                if v is not None and v != "":
                    merged_prov[k] = v
            md["provenance"] = merged_prov
        # 追加 retrieval_context 到 retrieval_history（并把旧 retrieval_context 迁移进历史）
        rc = new_metadata.get("retrieval_context")
        if rc:
            history = md.setdefault("retrieval_history", [])
            old_rc = md.get("retrieval_context")
            if old_rc and old_rc not in history:
                history.append(old_rc)
            history.append(rc)
            md["retrieval_context"] = rc  # 最新一次检索上下文
        # 合并 identity 字段（source_metadata doi/arxiv_id 补齐空缺）
        src_md = dict(md.get("source_metadata") or {})
        for k, v in (new_metadata.get("source_metadata") or {}).items():
            if k in ("doi", "arxiv_id") and not src_md.get(k) and v:
                src_md[k] = v
        md["source_metadata"] = src_md
        with self.connect() as c:
            c.execute(
                "UPDATE evidence SET metadata_json=?, version_no=version_no+1 "
                "WHERE tenant_id=? AND project_id=? AND evidence_id=?",
                (_json(md), tenant_id, project_id, existing["evidence_id"]))
        return existing["evidence_id"]

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
                         recommendation: str, options: Any,
                         trigger: str | None = None,
                         metadata: dict[str, Any] | None = None) -> str:
        ts = now_iso()
        with self.connect() as c:
            did = self.next_sequence("decision", "D")
            c.execute(
                "INSERT INTO decisions(decision_id,project_id,tenant_id,topic,"
                "trigger,recommendation,options_json,status,created_at,"
                "version_no,metadata_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (did, project_id, tenant_id, topic, trigger, recommendation,
                 _json(options), "proposed", ts, 1, _json(metadata or {})))
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
        out = []
        for r in rows:
            d = dict(r)
            # v5.9.1：暴露解析后的 metadata（原 metadata_json 键保留兼容）
            try:
                d["metadata"] = json.loads(d.get("metadata_json") or "{}")
            except (ValueError, TypeError):
                d["metadata"] = {}
            out.append(d)
        return out

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
            did = self.next_sequence("deliverable", "DEL")
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
            rid = self.next_sequence("risk", "RISK")
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
