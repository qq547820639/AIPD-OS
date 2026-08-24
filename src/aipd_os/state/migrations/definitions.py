"""MIGRATIONS 列表定义。

按版本顺序排列的所有迁移。每个条目包含 ``version``、``name``、``up``（应用）
和 ``down``（回滚）步骤。步骤可以是 SQL 字符串或 callable(conn)。

**禁止在此文件外修改迁移顺序或内容**——必须保持 migration order 和旧数据库
升级兼容。
"""
from __future__ import annotations

from typing import Any

from .helpers import (
    _add_decision_metadata,
    _add_generation_metadata,
    _add_lineage_columns,
    _add_retire_columns,
    _add_selection_status,
    _add_snapshot_basis,
    _create_commit_ledger,
    _create_outbox,
    _create_snapshot_tables,
    _drop_commit_ledger,
    _drop_decision_metadata,
    _drop_generation_metadata,
    _drop_lineage_columns,
    _drop_outbox,
    _drop_retire_columns,
    _drop_selection_status,
    _drop_snapshot_basis,
    _drop_snapshot_tables,
    _make_claim_confidence_nullable,
    _make_relation_strength_nullable,
    _restore_score_defaults,
    _seed_legacy_sequences,
    _unseed_legacy_sequences,
)
from .schema import V1_INITIAL_SCHEMA

# v1 初始 schema（多租户多项目）
MIGRATIONS: list[dict[str, Any]] = [
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
    {
        "version": 5,
        "name": "id_sequences",
        "up": [
            "CREATE TABLE IF NOT EXISTS id_sequences ("
            " name TEXT PRIMARY KEY,"
            " next_val INTEGER NOT NULL);",
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
    # v5.8.1 Commit 9：Generic Lineage —— 复用 dependencies 表。
    {
        "version": 6,
        "name": "generic_lineage",
        "up": [_add_lineage_columns],
        "down": [_drop_lineage_columns],
    },
    # v5.8.1 Commit 15：evidence_id 改为 id_sequences 原子分配。
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
    # v5.8.2 Commit 5：dependencies 边失效列。
    {
        "version": 8,
        "name": "lineage_edge_retire",
        "up": [_add_retire_columns],
        "down": [_drop_retire_columns],
    },
    # v5.8.2 Commit 8：结束 legacy 0.5 sentinel。
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
    # v5.9（Product Intelligence）：五张 canonical 表。
    {
        "version": 10,
        "name": "product_intelligence_domains",
        "up": [
            "CREATE TABLE IF NOT EXISTS insights ("
            " insight_id TEXT NOT NULL, project_id TEXT NOT NULL,"
            " tenant_id TEXT NOT NULL DEFAULT 'default',"
            " idea_id TEXT NOT NULL DEFAULT '', statement TEXT NOT NULL DEFAULT '',"
            " insight_type TEXT NOT NULL DEFAULT 'user_problem',"
            " source_claim_ids_json TEXT NOT NULL DEFAULT '[]',"
            " source_assessment_versions_json TEXT NOT NULL DEFAULT '[]',"
            " epistemic_status TEXT NOT NULL DEFAULT 'A',"
            " lifecycle_status TEXT NOT NULL DEFAULT 'candidate',"
            " rationale TEXT NOT NULL DEFAULT '', limitations TEXT NOT NULL DEFAULT '',"
            " version_no INTEGER NOT NULL DEFAULT 1,"
            " created_at TEXT NOT NULL, updated_at TEXT NOT NULL,"
            " PRIMARY KEY (insight_id, project_id, tenant_id));",
            "CREATE TABLE IF NOT EXISTS opportunities ("
            " opportunity_id TEXT NOT NULL, project_id TEXT NOT NULL,"
            " tenant_id TEXT NOT NULL DEFAULT 'default',"
            " idea_id TEXT NOT NULL DEFAULT '', title TEXT NOT NULL DEFAULT '',"
            " statement TEXT NOT NULL DEFAULT '', target_user TEXT NOT NULL DEFAULT '',"
            " problem TEXT NOT NULL DEFAULT '', desired_outcome TEXT NOT NULL DEFAULT '',"
            " opportunity_type TEXT NOT NULL DEFAULT 'new_product',"
            " source_insight_ids_json TEXT NOT NULL DEFAULT '[]',"
            " differentiation TEXT NOT NULL DEFAULT '',"
            " known_alternatives_json TEXT NOT NULL DEFAULT '[]',"
            " evidence_gaps_json TEXT NOT NULL DEFAULT '[]',"
            " lifecycle_status TEXT NOT NULL DEFAULT 'candidate',"
            " epistemic_status TEXT NOT NULL DEFAULT 'A',"
            " version_no INTEGER NOT NULL DEFAULT 1,"
            " created_at TEXT NOT NULL, updated_at TEXT NOT NULL,"
            " PRIMARY KEY (opportunity_id, project_id, tenant_id));",
            "CREATE TABLE IF NOT EXISTS product_principles ("
            " principle_id TEXT NOT NULL, project_id TEXT NOT NULL,"
            " tenant_id TEXT NOT NULL DEFAULT 'default',"
            " opportunity_id TEXT NOT NULL DEFAULT '',"
            " statement TEXT NOT NULL DEFAULT '', rationale TEXT NOT NULL DEFAULT '',"
            " source_insight_ids_json TEXT NOT NULL DEFAULT '[]',"
            " source_claim_ids_json TEXT NOT NULL DEFAULT '[]',"
            " definition_status TEXT NOT NULL DEFAULT 'RECOMMENDED',"
            " epistemic_status TEXT NOT NULL DEFAULT 'A',"
            " lifecycle_status TEXT NOT NULL DEFAULT 'candidate',"
            " criticality TEXT NOT NULL DEFAULT 'normal',"
            " version_no INTEGER NOT NULL DEFAULT 1,"
            " created_at TEXT NOT NULL, updated_at TEXT NOT NULL,"
            " PRIMARY KEY (principle_id, project_id, tenant_id));",
            "CREATE TABLE IF NOT EXISTS requirements ("
            " requirement_id TEXT NOT NULL, project_id TEXT NOT NULL,"
            " tenant_id TEXT NOT NULL DEFAULT 'default',"
            " title TEXT NOT NULL DEFAULT '', statement TEXT NOT NULL DEFAULT '',"
            " requirement_type TEXT NOT NULL DEFAULT 'functional',"
            " definition_status TEXT NOT NULL DEFAULT 'RECOMMENDED',"
            " epistemic_status TEXT NOT NULL DEFAULT 'A',"
            " lifecycle_status TEXT NOT NULL DEFAULT 'candidate',"
            " criticality TEXT NOT NULL DEFAULT 'normal',"
            " nominal_value TEXT, unit TEXT, lower_limit TEXT, upper_limit TEXT,"
            " tolerance TEXT, test_condition TEXT,"
            " rationale TEXT NOT NULL DEFAULT '',"
            " source_principle_ids_json TEXT NOT NULL DEFAULT '[]',"
            " source_evidence_refs_json TEXT NOT NULL DEFAULT '[]',"
            " derivation_method TEXT NOT NULL DEFAULT '',"
            " derivation_input_refs_json TEXT NOT NULL DEFAULT '[]',"
            " verification_method TEXT NOT NULL DEFAULT '',"
            " verification_test_refs_json TEXT NOT NULL DEFAULT '[]',"
            " affected_item_refs_json TEXT NOT NULL DEFAULT '[]',"
            " required_by_gate TEXT NOT NULL DEFAULT '', owner TEXT NOT NULL DEFAULT '',"
            " version_no INTEGER NOT NULL DEFAULT 1,"
            " created_at TEXT NOT NULL, updated_at TEXT NOT NULL,"
            " PRIMARY KEY (requirement_id, project_id, tenant_id));",
            "CREATE TABLE IF NOT EXISTS features ("
            " feature_id TEXT NOT NULL, project_id TEXT NOT NULL,"
            " tenant_id TEXT NOT NULL DEFAULT 'default',"
            " title TEXT NOT NULL DEFAULT '', description TEXT NOT NULL DEFAULT '',"
            " feature_type TEXT NOT NULL DEFAULT 'capability',"
            " source_requirement_ids_json TEXT NOT NULL DEFAULT '[]',"
            " source_principle_ids_json TEXT NOT NULL DEFAULT '[]',"
            " assumptions_json TEXT NOT NULL DEFAULT '[]',"
            " constraints_json TEXT NOT NULL DEFAULT '[]',"
            " definition_status TEXT NOT NULL DEFAULT 'RECOMMENDED',"
            " epistemic_status TEXT NOT NULL DEFAULT 'A',"
            " lifecycle_status TEXT NOT NULL DEFAULT 'candidate',"
            " validation_required INTEGER NOT NULL DEFAULT 0,"
            " version_no INTEGER NOT NULL DEFAULT 1,"
            " created_at TEXT NOT NULL, updated_at TEXT NOT NULL,"
            " PRIMARY KEY (feature_id, project_id, tenant_id));",
            "INSERT OR IGNORE INTO id_sequences(name, next_val) VALUES"
            " ('insight', 0), ('opportunity', 0), ('product_principle', 0),"
            " ('requirement', 0), ('feature', 0);",
        ],
        "down": [
            "DROP TABLE IF EXISTS features;",
            "DROP TABLE IF EXISTS requirements;",
            "DROP TABLE IF EXISTS product_principles;",
            "DROP TABLE IF EXISTS opportunities;",
            "DROP TABLE IF EXISTS insights;",
            "DELETE FROM id_sequences WHERE name IN"
            " ('insight','opportunity','product_principle','requirement','feature');",
        ],
    },
    # v5.9.1（Product Definition Integrity）：immutable snapshot + GateEvaluation
    {
        "version": 11,
        "name": "product_definition_integrity",
        "up": [
            _add_selection_status,
            _add_decision_metadata,
            _create_snapshot_tables,
        ],
        "down": [
            _drop_snapshot_tables,
            _drop_decision_metadata,
            _drop_selection_status,
        ],
    },
    # v5.9.2（Snapshot-Closed Runtime & Commit Integrity）
    {
        "version": 12,
        "name": "snapshot_closed_world_and_commit_ledger",
        "up": [
            _add_snapshot_basis,
            _add_generation_metadata,
            _create_commit_ledger,
        ],
        "down": [
            _drop_commit_ledger,
            _drop_generation_metadata,
            _drop_snapshot_basis,
        ],
    },
    # v5.10（Canonical Validation Domain）：6 张新表
    {
        "version": 13,
        "name": "canonical_validation_domain",
        "up": [
            """CREATE TABLE IF NOT EXISTS validation_plans (
                plan_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                stable_id TEXT NOT NULL DEFAULT '',
                version TEXT NOT NULL DEFAULT '1.0',
                revision INTEGER NOT NULL DEFAULT 1,
                lifecycle_status TEXT NOT NULL DEFAULT 'draft',
                stage TEXT NOT NULL DEFAULT 'EVT',
                title TEXT NOT NULL DEFAULT '',
                objective TEXT NOT NULL DEFAULT '',
                required INTEGER NOT NULL DEFAULT 1,
                owner TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT '',
                provenance TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                optimistic_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (plan_id, tenant_id, project_id)
            )""",
            """CREATE TABLE IF NOT EXISTS validation_tests (
                test_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                plan_id TEXT NOT NULL DEFAULT '',
                name TEXT NOT NULL DEFAULT '',
                stage TEXT NOT NULL DEFAULT 'EVT',
                category TEXT NOT NULL DEFAULT '',
                procedure TEXT NOT NULL DEFAULT '',
                method TEXT NOT NULL DEFAULT '',
                requirement_refs_json TEXT NOT NULL DEFAULT '[]',
                ctq_refs_json TEXT NOT NULL DEFAULT '[]',
                pass_criteria TEXT NOT NULL DEFAULT '',
                measurement TEXT,
                unit TEXT,
                lower_limit REAL,
                upper_limit REAL,
                tolerance REAL,
                required INTEGER NOT NULL DEFAULT 1,
                evidence_requirements TEXT NOT NULL DEFAULT '',
                test_equipment TEXT NOT NULL DEFAULT '',
                version TEXT NOT NULL DEFAULT '1.0',
                lifecycle_state TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (test_id, tenant_id, project_id)
            )""",
            """CREATE TABLE IF NOT EXISTS validation_runs (
                run_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                test_id TEXT NOT NULL DEFAULT '',
                tested_artifact_version TEXT NOT NULL DEFAULT '',
                tested_artifact_hash TEXT NOT NULL DEFAULT '',
                operator TEXT NOT NULL DEFAULT '',
                provider TEXT NOT NULL DEFAULT '',
                started_at TEXT,
                finished_at TEXT,
                environment TEXT NOT NULL DEFAULT '',
                execution_status TEXT NOT NULL DEFAULT 'NOT_RUN',
                idempotency_key TEXT NOT NULL DEFAULT '',
                external_operation_id TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                PRIMARY KEY (run_id, tenant_id, project_id)
            )""",
            """CREATE TABLE IF NOT EXISTS validation_results (
                result_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                run_id TEXT NOT NULL DEFAULT '',
                test_id TEXT NOT NULL DEFAULT '',
                result_status TEXT NOT NULL DEFAULT 'NOT_RUN',
                measured_values TEXT NOT NULL DEFAULT '',
                units TEXT NOT NULL DEFAULT '',
                pass_evaluation TEXT NOT NULL DEFAULT '',
                evidence_references_json TEXT NOT NULL DEFAULT '[]',
                raw_artifact_hash TEXT NOT NULL DEFAULT '',
                reason TEXT NOT NULL DEFAULT '',
                evaluator TEXT NOT NULL DEFAULT '',
                evaluated_at TEXT,
                stale INTEGER NOT NULL DEFAULT 0,
                stale_reason TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (result_id, tenant_id, project_id)
            )""",
            ("CREATE INDEX IF NOT EXISTS idx_vtests_plan "
             "ON validation_tests(tenant_id, project_id, plan_id)"),
            ("CREATE INDEX IF NOT EXISTS idx_vruns_test "
             "ON validation_runs(tenant_id, project_id, test_id)"),
            ("CREATE INDEX IF NOT EXISTS idx_vresults_test "
             "ON validation_results(tenant_id, project_id, test_id)"),
            ("CREATE INDEX IF NOT EXISTS idx_vresults_stale "
             "ON validation_results(tenant_id, project_id, stale)"),
            # Issue / Corrective Action 表
            """CREATE TABLE IF NOT EXISTS issues (
                issue_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                source_object_type TEXT NOT NULL DEFAULT '',
                source_object_id TEXT NOT NULL DEFAULT '',
                validation_result_ref TEXT NOT NULL DEFAULT '',
                severity TEXT NOT NULL DEFAULT 'MAJOR',
                priority TEXT NOT NULL DEFAULT 'P1',
                blocking_release INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'OPEN',
                owner TEXT NOT NULL DEFAULT '',
                opened_at TEXT,
                resolved_at TEXT,
                closed_at TEXT,
                root_cause TEXT NOT NULL DEFAULT '',
                disposition TEXT NOT NULL DEFAULT '',
                corrective_action_refs_json TEXT NOT NULL DEFAULT '[]',
                revalidation_required INTEGER NOT NULL DEFAULT 0,
                revalidation_result_ref TEXT NOT NULL DEFAULT '',
                audit_trail_json TEXT NOT NULL DEFAULT '[]',
                version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (issue_id, tenant_id, project_id)
            )""",
            """CREATE TABLE IF NOT EXISTS corrective_actions (
                action_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                issue_id TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                affected_objects_json TEXT NOT NULL DEFAULT '[]',
                change TEXT NOT NULL DEFAULT '',
                revalidation_requirement TEXT NOT NULL DEFAULT '',
                verification_result_ref TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'OPEN',
                owner TEXT NOT NULL DEFAULT '',
                started_at TEXT,
                completed_at TEXT,
                verified_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (action_id, tenant_id, project_id)
            )""",
            ("CREATE INDEX IF NOT EXISTS idx_issues_status "
             "ON issues(tenant_id, project_id, status)"),
            ("CREATE INDEX IF NOT EXISTS idx_issues_blocking "
             "ON issues(tenant_id, project_id, blocking_release)"),
            ("CREATE INDEX IF NOT EXISTS idx_cactions_issue "
             "ON corrective_actions(tenant_id, project_id, issue_id)"),
        ],
        "down": [
            "DROP TABLE IF EXISTS corrective_actions",
            "DROP TABLE IF EXISTS issues",
            "DROP TABLE IF EXISTS validation_results",
            "DROP TABLE IF EXISTS validation_runs",
            "DROP TABLE IF EXISTS validation_tests",
            "DROP TABLE IF EXISTS validation_plans",
        ],
    },
    # v5.11（P2-M5: Outbox + External Operation Ledger）：
    # - outbox_events：域事务内追加的事件，dispatcher 异步消费
    # - external_operations：外部副作用操作台账，UNKNOWN_OUTCOME 语义
    # 全部包含 tenant_id + project_id 作用域。
    {
        "version": 14,
        "name": "outbox_and_external_operations",
        "up": [
            _create_outbox,
        ],
        "down": [
            _drop_outbox,
        ],
    },
]
