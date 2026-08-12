"""schema 迁移运行器。

使用 ``schema_migrations`` 表记录已应用的迁移版本，按顺序执行 ``up``，
并支持按目标版本回滚到任意历史版本（执行 ``down``）。

迁移列表中的每个条目：``{"version": int, "name": str, "up": [sql|callable], "down": [sql|callable]}``。

v5.8.1 Commit 8：**migration runner 是唯一 schema authority**——
- V1 迁移使用**冻结的历史 SQL 文本**（:data:`V1_INITIAL_SCHEMA`），不再 import
  ``db.SCHEMA``（活 schema 常量）；:data:`V1_FROZEN_SHA256` 冻结校验防漂移；
- ``db.SCHEMA`` 仅作为「目标 schema 参考」保留（AIPDStateDB 建库走本 runner）。
"""
from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List

# v1 初始 schema（多租户多项目）—— **冻结的历史 SQL 文本**（Commit 8）。
# 不可 import db.SCHEMA（活常量会随代码演进而改变 v1 语义）。
V1_INITIAL_SCHEMA = r"""
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

# v1 冻结文本的 SHA-256（Commit 8：防漂移校验，见 test_frozen_v1_schema_does_not_drift）
V1_FROZEN_SHA256 = "a014a959286d1bfea11717d4e4f54a39bcbb5c4c9b2ad49e2d0f249f49fc52c7"


def _v1_frozen_sha256() -> str:
    """重算 v1 冻结文本的 SHA-256（用于漂移校验）。"""
    return hashlib.sha256(V1_INITIAL_SCHEMA.encode("utf-8")).hexdigest()


def _dependencies_columns(conn: sqlite3.Connection) -> set:
    """dependencies 表现有列名集合。"""
    rows = conn.execute("PRAGMA table_info(dependencies)").fetchall()
    return {r[1] for r in rows}


def _add_lineage_columns(conn: sqlite3.Connection) -> None:
    """幂等添加 lineage 扩展列（v6 up）。"""
    cols = _dependencies_columns(conn)
    additions = [
        ("created_at", "created_at TEXT NOT NULL DEFAULT ''"),
        ("provenance", "provenance TEXT NOT NULL DEFAULT '{}'"),
        ("version_no", "version_no INTEGER NOT NULL DEFAULT 1"),
    ]
    for col, ddl in additions:
        if col not in cols:
            conn.execute(f"ALTER TABLE dependencies ADD COLUMN {ddl}")


def _drop_lineage_columns(conn: sqlite3.Connection) -> None:
    """回滚 lineage 扩展列（v6 down；列不存在时跳过）。"""
    cols = _dependencies_columns(conn)
    for col in ("created_at", "provenance", "version_no"):
        if col in cols:
            conn.execute(f"ALTER TABLE dependencies DROP COLUMN {col}")


def _add_retire_columns(conn: sqlite3.Connection) -> None:
    """幂等添加边失效列（v8 up）：retired_at / retired_by。"""
    cols = _dependencies_columns(conn)
    additions = [
        ("retired_at", "retired_at TEXT"),
        ("retired_by", "retired_by TEXT"),
    ]
    for col, ddl in additions:
        if col not in cols:
            conn.execute(f"ALTER TABLE dependencies ADD COLUMN {ddl}")


def _drop_retire_columns(conn: sqlite3.Connection) -> None:
    """回滚边失效列（v8 down；列不存在时跳过）。"""
    cols = _dependencies_columns(conn)
    for col in ("retired_at", "retired_by"):
        if col in cols:
            conn.execute(f"ALTER TABLE dependencies DROP COLUMN {col}")


def _make_claim_confidence_nullable(conn: sqlite3.Connection) -> None:
    """v9 up：claims.confidence NOT NULL DEFAULT 0.5 → NULLABLE。

    旧 0.5 值**保守保留**（不猜测是否真实评分；模型层读取时按
    legacy_unscored 处理为 None，行为不变）。SQLite 无 ALTER COLUMN，
    重建表保持 PK 与约束。
    """
    conn.executescript("""
    CREATE TABLE claims_new (
      claim_id TEXT NOT NULL, project_id TEXT NOT NULL,
      tenant_id TEXT NOT NULL DEFAULT 'default',
      idea_id TEXT NOT NULL DEFAULT '', claim_type TEXT NOT NULL,
      statement TEXT NOT NULL, epistemic_status TEXT NOT NULL DEFAULT 'A',
      lifecycle_status TEXT NOT NULL DEFAULT 'active',
      confidence REAL,
      source TEXT NOT NULL DEFAULT '', version_no INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
      PRIMARY KEY (claim_id, project_id, tenant_id));
    INSERT INTO claims_new SELECT claim_id,project_id,tenant_id,idea_id,
      claim_type,statement,epistemic_status,lifecycle_status,confidence,source,
      version_no,created_at,updated_at FROM claims;
    DROP TABLE claims;
    ALTER TABLE claims_new RENAME TO claims;
    """)


def _make_relation_strength_nullable(conn: sqlite3.Connection) -> None:
    """v9 up：claim_evidence_relations.strength NOT NULL DEFAULT 0.5 → NULLABLE。

    旧 0.5 值保守保留（legacy_unscored 语义，模型层读取时映射 None）。
    """
    conn.executescript("""
    CREATE TABLE claim_evidence_relations_new (
      relation_id TEXT NOT NULL, project_id TEXT NOT NULL,
      tenant_id TEXT NOT NULL DEFAULT 'default',
      claim_id TEXT NOT NULL, evidence_id TEXT NOT NULL,
      relation_type TEXT NOT NULL, strength REAL,
      applicability TEXT NOT NULL DEFAULT '',
      reasoning_summary TEXT NOT NULL DEFAULT '',
      limitations TEXT NOT NULL DEFAULT '',
      review_status TEXT NOT NULL DEFAULT 'pending',
      created_by TEXT NOT NULL DEFAULT 'system',
      version_no INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
      PRIMARY KEY (relation_id, project_id, tenant_id),
      UNIQUE (claim_id, evidence_id, relation_type, project_id, tenant_id));
    INSERT INTO claim_evidence_relations_new SELECT relation_id,project_id,
      tenant_id,claim_id,evidence_id,relation_type,strength,applicability,
      reasoning_summary,limitations,review_status,created_by,version_no,
      created_at,updated_at FROM claim_evidence_relations;
    DROP TABLE claim_evidence_relations;
    ALTER TABLE claim_evidence_relations_new RENAME TO claim_evidence_relations;
    """)


def _restore_score_defaults(conn: sqlite3.Connection) -> None:
    """v9 down：恢复 NOT NULL DEFAULT 0.5（NULL → 0.5 legacy 哨兵）。"""
    conn.executescript("""
    CREATE TABLE claims_old (
      claim_id TEXT NOT NULL, project_id TEXT NOT NULL,
      tenant_id TEXT NOT NULL DEFAULT 'default',
      idea_id TEXT NOT NULL DEFAULT '', claim_type TEXT NOT NULL,
      statement TEXT NOT NULL, epistemic_status TEXT NOT NULL DEFAULT 'A',
      lifecycle_status TEXT NOT NULL DEFAULT 'active',
      confidence REAL NOT NULL DEFAULT 0.5,
      source TEXT NOT NULL DEFAULT '', version_no INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
      PRIMARY KEY (claim_id, project_id, tenant_id));
    INSERT INTO claims_old SELECT claim_id,project_id,tenant_id,idea_id,
      claim_type,statement,epistemic_status,lifecycle_status,
      COALESCE(confidence, 0.5),source,version_no,created_at,updated_at
      FROM claims;
    DROP TABLE claims;
    ALTER TABLE claims_old RENAME TO claims;
    CREATE TABLE claim_evidence_relations_old (
      relation_id TEXT NOT NULL, project_id TEXT NOT NULL,
      tenant_id TEXT NOT NULL DEFAULT 'default',
      claim_id TEXT NOT NULL, evidence_id TEXT NOT NULL,
      relation_type TEXT NOT NULL, strength REAL NOT NULL DEFAULT 0.5,
      applicability TEXT NOT NULL DEFAULT '',
      reasoning_summary TEXT NOT NULL DEFAULT '',
      limitations TEXT NOT NULL DEFAULT '',
      review_status TEXT NOT NULL DEFAULT 'pending',
      created_by TEXT NOT NULL DEFAULT 'system',
      version_no INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
      PRIMARY KEY (relation_id, project_id, tenant_id),
      UNIQUE (claim_id, evidence_id, relation_type, project_id, tenant_id));
    INSERT INTO claim_evidence_relations_old SELECT relation_id,project_id,
      tenant_id,claim_id,evidence_id,relation_type,COALESCE(strength, 0.5),
      applicability,reasoning_summary,limitations,review_status,created_by,
      version_no,created_at,updated_at FROM claim_evidence_relations;
    DROP TABLE claim_evidence_relations;
    ALTER TABLE claim_evidence_relations_old RENAME TO claim_evidence_relations;
    """)


def _seed_legacy_sequences(conn: sqlite3.Connection) -> None:
    """v9 up：为 legacy scan-max 对象（fact/decision/deliverable/risk）seed
    id_sequences（从存量 display id 推导 next_val，防新行与存量冲突）。"""
    conn.executescript("""
    INSERT OR IGNORE INTO id_sequences(name, next_val) SELECT 'fact',
      COALESCE(MAX(CAST(substr(fact_id, 3) AS INTEGER)), 0)
      FROM facts WHERE fact_id LIKE 'F-%';
    INSERT OR IGNORE INTO id_sequences(name, next_val) SELECT 'decision',
      COALESCE(MAX(CAST(substr(decision_id, 3) AS INTEGER)), 0)
      FROM decisions WHERE decision_id LIKE 'D-%';
    INSERT OR IGNORE INTO id_sequences(name, next_val) SELECT 'deliverable',
      COALESCE(MAX(CAST(substr(deliverable_id, 5) AS INTEGER)), 0)
      FROM deliverables WHERE deliverable_id LIKE 'DEL-%';
    INSERT OR IGNORE INTO id_sequences(name, next_val) SELECT 'risk',
      COALESCE(MAX(CAST(substr(risk_id, 5) AS INTEGER)), 0)
      FROM risks WHERE risk_id LIKE 'RISK-%';
    """)


def _unseed_legacy_sequences(conn: sqlite3.Connection) -> None:
    """v9 down：移除 v9 新增的 sequence seed。"""
    conn.executescript(
        "DELETE FROM id_sequences WHERE name IN "
        "('fact','decision','deliverable','risk');"
    )


# v1 初始 schema（多租户多项目）
MIGRATIONS: List[Dict[str, Any]] = [
    {
        "version": 1,
        "name": "multi_tenant_initial_schema",
        "up": [V1_INITIAL_SCHEMA],
        "down": [
            "DROP TABLE IF EXISTS backups;",
            "DROP TABLE IF EXISTS checkpoints;",
            "DROP TABLE IF EXISTS audit_log;",
            "DROP TABLE IF EXISTS gates;",
            "DROP TABLE IF EXISTS changes;",
            "DROP TABLE IF EXISTS dependencies;",
            "DROP TABLE IF EXISTS risks;",
            "DROP TABLE IF EXISTS deliverables;",
            "DROP TABLE IF EXISTS decisions;",
            "DROP TABLE IF EXISTS fact_evidence;",
            "DROP TABLE IF EXISTS evidence;",
            "DROP TABLE IF EXISTS facts;",
            "DROP TABLE IF EXISTS projects;",
            "DROP TABLE IF EXISTS sessions;",
            "DROP TABLE IF EXISTS user_access;",
            "DROP TABLE IF EXISTS users;",
            "DROP TABLE IF EXISTS tenants;",
        ],
    },
    # v5.8 Commit 9：Idea Domain（canonical idea 表；对已存在 v1 库就地 CREATE）。
    {
        "version": 2,
        "name": "idea_domain",
        "up": [
            "CREATE TABLE IF NOT EXISTS ideas ("
            " idea_id TEXT NOT NULL, project_id TEXT NOT NULL,"
            " tenant_id TEXT NOT NULL DEFAULT 'default',"
            " title TEXT NOT NULL DEFAULT '', raw_input TEXT NOT NULL DEFAULT '',"
            " goal TEXT NOT NULL DEFAULT '', problem TEXT NOT NULL DEFAULT '',"
            " target_user TEXT NOT NULL DEFAULT '', desired_outcome TEXT NOT NULL DEFAULT '',"
            " constraints_json TEXT NOT NULL DEFAULT '{}',"
            " source TEXT NOT NULL DEFAULT '', lifecycle_status TEXT NOT NULL DEFAULT 'raw',"
            " version_no INTEGER NOT NULL DEFAULT 1,"
            " created_at TEXT NOT NULL, updated_at TEXT NOT NULL,"
            " PRIMARY KEY (idea_id, project_id, tenant_id));",
        ],
        "down": ["DROP TABLE IF EXISTS ideas;"],
    },
    # v5.8 Commit 10：Claim Domain（命题表；idea_id 为软引用，不强外键）。
    {
        "version": 3,
        "name": "claim_domain",
        "up": [
            "CREATE TABLE IF NOT EXISTS claims ("
            " claim_id TEXT NOT NULL, project_id TEXT NOT NULL,"
            " tenant_id TEXT NOT NULL DEFAULT 'default',"
            " idea_id TEXT NOT NULL DEFAULT '', claim_type TEXT NOT NULL,"
            " statement TEXT NOT NULL, epistemic_status TEXT NOT NULL DEFAULT 'A',"
            " lifecycle_status TEXT NOT NULL DEFAULT 'active',"
            " confidence REAL NOT NULL DEFAULT 0.5,"
            " source TEXT NOT NULL DEFAULT '', version_no INTEGER NOT NULL DEFAULT 1,"
            " created_at TEXT NOT NULL, updated_at TEXT NOT NULL,"
            " PRIMARY KEY (claim_id, project_id, tenant_id));",
        ],
        "down": ["DROP TABLE IF EXISTS claims;"],
    },
    # v5.8 Commit 11：EvidenceRelation（claim ↔ evidence 关系表）。
    {
        "version": 4,
        "name": "claim_evidence_relations",
        "up": [
            "CREATE TABLE IF NOT EXISTS claim_evidence_relations ("
            " relation_id TEXT NOT NULL, project_id TEXT NOT NULL,"
            " tenant_id TEXT NOT NULL DEFAULT 'default',"
            " claim_id TEXT NOT NULL, evidence_id TEXT NOT NULL,"
            " relation_type TEXT NOT NULL, strength REAL NOT NULL DEFAULT 0.5,"
            " applicability TEXT NOT NULL DEFAULT '',"
            " reasoning_summary TEXT NOT NULL DEFAULT '',"
            " limitations TEXT NOT NULL DEFAULT '',"
            " review_status TEXT NOT NULL DEFAULT 'pending',"
            " created_by TEXT NOT NULL DEFAULT 'system',"
            " version_no INTEGER NOT NULL DEFAULT 1,"
            " created_at TEXT NOT NULL, updated_at TEXT NOT NULL,"
            " PRIMARY KEY (relation_id, project_id, tenant_id),"
            " UNIQUE (claim_id, evidence_id, relation_type, project_id, tenant_id));",
        ],
        "down": ["DROP TABLE IF EXISTS claim_evidence_relations;"],
    },
    # v5.8.1 Commit 7：id_sequences —— 并发安全 ID 分配（atomic sequence table）。
    # 从存量 ideas/claims/claim_evidence_relations 的 display id（IDEA-001 等）
    # 推导 next_val（= 现有最大值），避免新建行与存量 id 冲突。
    {
        "version": 5,
        "name": "id_sequences",
        "up": [
            "CREATE TABLE IF NOT EXISTS id_sequences ("
            " name TEXT PRIMARY KEY,"
            " next_val INTEGER NOT NULL);",
            # seed：next_val = 现有最大编号（首次 next_sequence 会 +1 后返回）
            "INSERT INTO id_sequences(name, next_val) SELECT 'idea', "
            " COALESCE(MAX(CAST(substr(idea_id, 6) AS INTEGER)), 0) "
            " FROM ideas WHERE idea_id LIKE 'IDEA-%';",
            "INSERT INTO id_sequences(name, next_val) SELECT 'claim', "
            " COALESCE(MAX(CAST(substr(claim_id, 5) AS INTEGER)), 0) "
            " FROM claims WHERE claim_id LIKE 'CLM-%';",
            "INSERT INTO id_sequences(name, next_val) SELECT 'relation', "
            " COALESCE(MAX(CAST(substr(relation_id, 5) AS INTEGER)), 0) "
            " FROM claim_evidence_relations WHERE relation_id LIKE 'REL-%';",
        ],
        "down": ["DROP TABLE IF EXISTS id_sequences;"],
    },
    # v5.8.1 Commit 9：Generic Lineage —— 复用 dependencies 表（本来就是通用
    # 有向边存储：source_type/source_id/target_type/target_id/relation + scope）。
    # 补 created_at / provenance / version_no 三列（已有行取默认值；幂等：
    # 列已存在时跳过，避免重建 v1-era 库时 duplicate column）。
    {
        "version": 6,
        "name": "generic_lineage",
        "up": [_add_lineage_columns],
        "down": [_drop_lineage_columns],
    },
    # v5.8.1 Commit 15（QA 观察）：evidence_id 改为 id_sequences 原子分配
    # （同 idea/claim/relation 一致）。从存量 evidence 推导 next_val
    # （E-001 → substr(evidence_id,3)="001"），避免新行与存量 id 冲突。
    {
        "version": 7,
        "name": "evidence_sequence_seed",
        "up": [
            "INSERT OR IGNORE INTO id_sequences(name, next_val) SELECT 'evidence', "
            " COALESCE(MAX(CAST(substr(evidence_id, 3) AS INTEGER)), 0) "
            " FROM evidence WHERE evidence_id LIKE 'E-%';",
        ],
        "down": [
            "DELETE FROM id_sequences WHERE name='evidence';",
        ],
    },
    # v5.8.2 Commit 5（EvidenceRelation ↔ Lineage review semantics）：
    # dependencies 边失效列 —— retire（soft）而非物理删除；active 查询
    # 默认过滤 retired 边；同键重建时旧 retired 行经 audit 留痕后移除。
    {
        "version": 8,
        "name": "lineage_edge_retire",
        "up": [_add_retire_columns],
        "down": [_drop_retire_columns],
    },
    # v5.8.2 Commit 8（结束 legacy 0.5 sentinel）：
    # claims.confidence / claim_evidence_relations.strength → NULLABLE。
    # 旧 0.5 值保守保留（不猜测真实评分；模型层读取按 legacy_unscored→None）；
    # 新记录未评分写 NULL（不再落 0.5 哨兵）。
    # 同时 seed fact/decision/deliverable/risk 的 id_sequences（scan-max 统一）。
    {
        "version": 9,
        "name": "nullable_scores_and_legacy_sequences",
        "up": [
            _make_claim_confidence_nullable,
            _make_relation_strength_nullable,
            _seed_legacy_sequences,
        ],
        "down": [
            _restore_score_defaults,
            _unseed_legacy_sequences,
        ],
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _conn(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.executescript("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _ensure_schema_migrations(conn: sqlite3.Connection) -> None:
    conn.executescript(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL);"
    )


def applied_versions(db_path: str) -> List[int]:
    with _conn(db_path) as c:
        _ensure_schema_migrations(c)
        rows = c.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
    return [r[0] for r in rows]


def _run_steps(conn: sqlite3.Connection, steps: List[Any]) -> None:
    for step in steps:
        if callable(step):
            step(conn)
        else:
            conn.executescript(step)


def migrate(db_path: str) -> List[int]:
    """应用所有未执行的迁移，返回本次应用到的版本列表。"""
    applied = []
    with _conn(db_path) as c:
        _ensure_schema_migrations(c)
        done = {r[0] for r in c.execute("SELECT version FROM schema_migrations").fetchall()}
        for mig in sorted(MIGRATIONS, key=lambda m: m["version"]):
            if mig["version"] in done:
                continue
            _run_steps(c, mig["up"])
            c.execute("INSERT INTO schema_migrations(version,name,applied_at) VALUES(?,?,?)",
                      (mig["version"], mig["name"], _now()))
            applied.append(mig["version"])
    return applied


def rollback(db_path: str, target: int) -> List[int]:
    """回滚到指定目标版本（不含 target），返回被回滚的版本列表。"""
    rolled_back = []
    with _conn(db_path) as c:
        _ensure_schema_migrations(c)
        done = sorted(r[0] for r in c.execute("SELECT version FROM schema_migrations").fetchall())
        for version in reversed(done):
            if version <= target:
                break
            mig = next(m for m in MIGRATIONS if m["version"] == version)
            _run_steps(c, mig["down"])
            c.execute("DELETE FROM schema_migrations WHERE version=?", (version,))
            rolled_back.append(version)
    return rolled_back


def current_version(db_path: str) -> int:
    try:
        versions = applied_versions(db_path)
    except sqlite3.DatabaseError:
        return 0
    return max(versions) if versions else 0


__all__ = [
    "MIGRATIONS",
    "migrate",
    "rollback",
    "applied_versions",
    "current_version",
    "V1_INITIAL_SCHEMA",
    "V1_FROZEN_SHA256",
    "_v1_frozen_sha256",
]
