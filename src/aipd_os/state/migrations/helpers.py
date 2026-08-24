"""迁移步骤中使用的 callable 辅助函数。

这些函数被 MIGRATIONS 列表中的 "up"/"down" 引用，用于执行无法用
纯 SQL 表达的幂等 DDL 操作（ALTER TABLE ADD COLUMN、表重建等）。
"""
from __future__ import annotations

import sqlite3


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


# ---------------------------------------------------------------------------
# v9 helpers
# ---------------------------------------------------------------------------
def _make_claim_confidence_nullable(conn: sqlite3.Connection) -> None:
    """v9 up：claims.confidence NOT NULL DEFAULT 0.5 → NULLABLE。

    旧 0.5 值**保守保留**（不猜测是否真实评分；模型层读取时按
    legacy_unscored 处理为 None，行为不变）。SQLite 无 ALTER COLUMN，
    重建表保持 PK 与约束。
    """
    from .runner import _exec_script

    _exec_script(conn, """
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
    from .runner import _exec_script

    _exec_script(conn, """
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
    from .runner import _exec_script

    _exec_script(conn, """
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
    from .runner import _exec_script

    _exec_script(conn, """
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
    from .runner import _exec_script

    _exec_script(conn,
        "DELETE FROM id_sequences WHERE name IN "
        "('fact','decision','deliverable','risk');"
    )


# ---------------------------------------------------------------------------
# v11 helpers
# ---------------------------------------------------------------------------
def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _add_selection_status(conn: sqlite3.Connection) -> None:
    """v11 up：opportunities.selection_status（candidate/selected/rejected/
    superseded；显式 Opportunity Selection，P0-07）。存量行默认 candidate
    （不猜测历史选择；显式 select 由新 API 完成）。"""
    cols = _table_columns(conn, "opportunities")
    if "selection_status" not in cols:
        conn.execute(
            "ALTER TABLE opportunities ADD COLUMN selection_status TEXT "
            "NOT NULL DEFAULT 'candidate'")


def _drop_selection_status(conn: sqlite3.Connection) -> None:
    cols = _table_columns(conn, "opportunities")
    if "selection_status" in cols:
        conn.execute("ALTER TABLE opportunities DROP COLUMN selection_status")


def _add_decision_metadata(conn: sqlite3.Connection) -> None:
    """v11 up：decisions.metadata_json（snapshot 绑定 / waiver / 决策版本）。
    存量行 {}（历史决策不猜测绑定对象 —— 新语义下历史 approve 不再自动
    授权任何 snapshot，见 get_effective_decision）。"""
    cols = _table_columns(conn, "decisions")
    if "metadata_json" not in cols:
        conn.execute("ALTER TABLE decisions ADD COLUMN metadata_json TEXT "
                     "NOT NULL DEFAULT '{}'")


def _drop_decision_metadata(conn: sqlite3.Connection) -> None:
    cols = _table_columns(conn, "decisions")
    if "metadata_json" in cols:
        conn.execute("ALTER TABLE decisions DROP COLUMN metadata_json")


def _create_snapshot_tables(conn: sqlite3.Connection) -> None:
    """v11 up：product_definition_snapshots（immutable，无 UPDATE 路径）。

    refs 列存 [{id, version}]（canonical JSON）：content_hash 必须覆盖
    id + version（同 id 更新后 hash 变化 → stale 检测真实）。"""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS product_definition_snapshots ("
        " snapshot_id TEXT NOT NULL,"
        " project_id TEXT NOT NULL,"
        " tenant_id TEXT NOT NULL DEFAULT 'default',"
        " idea_id TEXT NOT NULL DEFAULT '',"
        " opportunity_id TEXT NOT NULL DEFAULT '',"
        " opportunity_version INTEGER,"
        " principle_refs_json TEXT NOT NULL DEFAULT '[]',"
        " requirement_refs_json TEXT NOT NULL DEFAULT '[]',"
        " feature_refs_json TEXT NOT NULL DEFAULT '[]',"
        " critical_unknown_refs_json TEXT NOT NULL DEFAULT '[]',"
        " conflict_refs_json TEXT NOT NULL DEFAULT '[]',"
        " source_projection_version TEXT NOT NULL DEFAULT '',"
        " content_hash TEXT NOT NULL,"
        " lifecycle_status TEXT NOT NULL DEFAULT 'frozen',"
        " created_at TEXT NOT NULL,"
        " created_by TEXT NOT NULL DEFAULT 'system',"
        " PRIMARY KEY (snapshot_id, project_id, tenant_id))")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS gate_evaluations ("
        " evaluation_id TEXT NOT NULL,"
        " project_id TEXT NOT NULL,"
        " tenant_id TEXT NOT NULL DEFAULT 'default',"
        " snapshot_id TEXT NOT NULL DEFAULT '',"
        " snapshot_hash TEXT NOT NULL DEFAULT '',"
        " result TEXT NOT NULL,"
        " hard_blockers_json TEXT NOT NULL DEFAULT '[]',"
        " conditional_blockers_json TEXT NOT NULL DEFAULT '[]',"
        " warnings_json TEXT NOT NULL DEFAULT '[]',"
        " information_json TEXT NOT NULL DEFAULT '[]',"
        " criteria_results_json TEXT NOT NULL DEFAULT '[]',"
        " evaluated_at TEXT NOT NULL,"
        " evaluator_version TEXT NOT NULL DEFAULT '',"
        " policy_version TEXT NOT NULL DEFAULT '',"
        " PRIMARY KEY (evaluation_id, project_id, tenant_id))")
    conn.execute(
        "INSERT OR IGNORE INTO id_sequences(name, next_val) VALUES"
        " ('product_snapshot', 0), ('gate_evaluation', 0);")


def _drop_snapshot_tables(conn: sqlite3.Connection) -> None:
    conn.execute("DROP TABLE IF EXISTS gate_evaluations;")
    conn.execute("DROP TABLE IF EXISTS product_definition_snapshots;")
    conn.execute("DELETE FROM id_sequences WHERE name IN"
                 " ('product_snapshot','gate_evaluation');")


# ---------------------------------------------------------------------------
# v12 helpers
# ---------------------------------------------------------------------------
def _add_snapshot_basis(conn: sqlite3.Connection) -> None:
    """v12 up：product_definition_snapshots.upstream_basis_hash（P0-08/O-3）。

    hash 覆盖冻结 Product Definition 的 upstream lineage basis（claims/
    relations/assessments/insights/selected opportunity/PI versions），
    is_stale 的第二道防线。存量行 ''（不猜测）。"""
    cols = _table_columns(conn, "product_definition_snapshots")
    if "upstream_basis_hash" not in cols:
        conn.execute(
            "ALTER TABLE product_definition_snapshots ADD COLUMN "
            "upstream_basis_hash TEXT NOT NULL DEFAULT ''")


def _drop_snapshot_basis(conn: sqlite3.Connection) -> None:
    cols = _table_columns(conn, "product_definition_snapshots")
    if "upstream_basis_hash" in cols:
        conn.execute(
            "ALTER TABLE product_definition_snapshots DROP COLUMN "
            "upstream_basis_hash")


def _add_generation_metadata(conn: sqlite3.Connection) -> None:
    """v12 up：五张 PI 表加 generation_metadata_json（§37 反查生成来源）。"""
    for table in ("insights", "opportunities", "product_principles",
                  "requirements", "features"):
        cols = _table_columns(conn, table)
        if "generation_metadata_json" not in cols:
            conn.execute(
                f"ALTER TABLE {table} ADD COLUMN "
                "generation_metadata_json TEXT NOT NULL DEFAULT '{{}}'")


def _drop_generation_metadata(conn: sqlite3.Connection) -> None:
    for table in ("insights", "opportunities", "product_principles",
                  "requirements", "features"):
        cols = _table_columns(conn, table)
        if "generation_metadata_json" in cols:
            conn.execute(
                f"ALTER TABLE {table} DROP COLUMN generation_metadata_json")


def _create_commit_ledger(conn: sqlite3.Connection) -> None:
    """v12 up：product_definition_commits（P0-06 exactly-once commit ledger）。

    UNIQUE(tenant_id, project_id, snapshot_id) —— 同一 snapshot 只能提交
    一次；重复 commit 返回已有 receipt（幂等）或拒绝。"""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS product_definition_commits ("
        " commit_id TEXT NOT NULL,"
        " project_id TEXT NOT NULL,"
        " tenant_id TEXT NOT NULL DEFAULT 'default',"
        " snapshot_id TEXT NOT NULL,"
        " snapshot_hash TEXT NOT NULL,"
        " gate_evaluation_id TEXT NOT NULL DEFAULT '',"
        " owner_decision_id TEXT NOT NULL DEFAULT '',"
        " committed_truth_refs_json TEXT NOT NULL DEFAULT '[]',"
        " committed_at TEXT NOT NULL,"
        " actor TEXT NOT NULL DEFAULT 'system',"
        " PRIMARY KEY (commit_id, project_id, tenant_id),"
        " UNIQUE (tenant_id, project_id, snapshot_id))")
    conn.execute(
        "INSERT OR IGNORE INTO id_sequences(name, next_val) VALUES"
        " ('product_commit', 0);")


def _drop_commit_ledger(conn: sqlite3.Connection) -> None:
    conn.execute("DROP TABLE IF EXISTS product_definition_commits;")
    conn.execute("DELETE FROM id_sequences WHERE name='product_commit';")


# ---------------------------------------------------------------------------
# v14 helpers: Outbox + External Operation Ledger
# ---------------------------------------------------------------------------
def _create_outbox(conn: sqlite3.Connection) -> None:
    """v14 up：outbox_events + external_operations 表。

    outbox_events：域事务内追加的事件，dispatcher 异步消费。
    external_operations：外部副作用操作台账，记录 UNKNOWN_OUTCOME 语义。
    """
    conn.execute(
        "CREATE TABLE IF NOT EXISTS outbox_events ("
        " event_id TEXT NOT NULL,"
        " tenant_id TEXT NOT NULL DEFAULT 'default',"
        " project_id TEXT NOT NULL DEFAULT '',"
        " aggregate_type TEXT NOT NULL DEFAULT '',"
        " aggregate_id TEXT NOT NULL DEFAULT '',"
        " event_type TEXT NOT NULL DEFAULT '',"
        " payload_json TEXT NOT NULL DEFAULT '{}',"
        " schema_version INTEGER NOT NULL DEFAULT 1,"
        " created_at TEXT NOT NULL,"
        " available_at TEXT NOT NULL,"
        " claimed_at TEXT,"
        " completed_at TEXT,"
        " attempt_count INTEGER NOT NULL DEFAULT 0,"
        " max_attempts INTEGER NOT NULL DEFAULT 5,"
        " last_error TEXT NOT NULL DEFAULT '',"
        " idempotency_key TEXT NOT NULL DEFAULT '',"
        " PRIMARY KEY (event_id, tenant_id, project_id))")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS external_operations ("
        " operation_id TEXT NOT NULL,"
        " tenant_id TEXT NOT NULL DEFAULT 'default',"
        " project_id TEXT NOT NULL DEFAULT '',"
        " idempotency_key TEXT NOT NULL DEFAULT '',"
        " provider TEXT NOT NULL DEFAULT '',"
        " operation_kind TEXT NOT NULL DEFAULT '',"
        " request_hash TEXT NOT NULL DEFAULT '',"
        " status TEXT NOT NULL DEFAULT 'PENDING',"
        " attempt INTEGER NOT NULL DEFAULT 0,"
        " external_reference TEXT NOT NULL DEFAULT '',"
        " started_at TEXT,"
        " completed_at TEXT,"
        " last_error TEXT NOT NULL DEFAULT '',"
        " PRIMARY KEY (operation_id, tenant_id, project_id))")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_outbox_available "
        "ON outbox_events(tenant_id, project_id, available_at) "
        "WHERE completed_at IS NULL")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_outbox_claim "
        "ON outbox_events(claimed_at) WHERE completed_at IS NULL")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ext_ops_status "
        "ON external_operations(tenant_id, project_id, status)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ext_ops_idempotency "
        "ON external_operations(tenant_id, project_id, idempotency_key)")


def _drop_outbox(conn: sqlite3.Connection) -> None:
    conn.execute("DROP TABLE IF EXISTS external_operations")
    conn.execute("DROP TABLE IF EXISTS outbox_events")
