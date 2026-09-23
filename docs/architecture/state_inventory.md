# State Inventory — AIPD-OS P2

> Updated: 2026-09-24 (P2-M10 收口；schema HEAD = v17)
> Purpose: P2 State Ownership Convergence — complete persistence point audit

## Physical Stores

| # | Store | Path Convention | Module | Tables | Status |
|---|-------|----------------|--------|--------|--------|
| 1 | AIPDStateDB | `state.db` | `state/db.py` | 30+ tables | CANONICAL |
| 2 | ExecutionRuns | `*.runs.db` | `execution/runs.py` | execution_runs | EXECUTION_LOG |
| 3 | ClosureStore | `<db>.closure.db` | `execution/closure_core.py` | 6 tables | EXECUTION_LOG |
| 4 | BomStore | `<state.db>.bom.db` | `bom/store.py` | boms, bom_lines, bom_changes | CANONICAL |
| 5 | ProductTruth | `<state.db>.truth.db` | `product_truth/store.py` | product_truth, truth_lineage, rework_tasks | CANONICAL |
| 6 | Supervisor | `<state.db>.supervisor.db` | `supervisor/supervisor.py` | 7 tables | CANONICAL |
| 7 | Manual JSON | `<db>.manual.json` | `cli/commands_manual.py` | N/A (JSON file) | LEGACY → canonicalized |
| 8 | Outbox/Operations | `state.db` (v14) | `state/outbox.py` | outbox_events, external_operations | ACTIVE |
| 9 | Readiness Snapshots | `state.db` (v15) | `validation/readiness.py` | readiness_snapshots | ACTIVE |

## Tenant/Project Scope Analysis

| Store | tenant_id | project_id | Status | Notes |
|-------|-----------|------------|--------|-------|
| AIPDStateDB | ✅ | ✅ | CURRENT | Migration v1+ |
| ExecutionRuns | ✅ | ✅ | CURRENT | Added post-v5.7 |
| **ClosureStore** | **✅** | **✅** | **FIXED (P2-M2)** | All 6 tables have tenant_id + project_id with indexes |
| BomStore | ✅ | ✅ | CURRENT | |
| ProductTruth | ✅ | ✅ | CURRENT | |
| Supervisor | ✅ | ✅ | CURRENT | default 'default' |
| Manual JSON | ✅ (canonical) | ✅ (canonical) | FIXED (P2-M4) | ManualStateRepository with scope |
| Outbox/Operations | ✅ | ✅ | CURRENT (P2-M5) | |
| Readiness Snapshots | ✅ | ✅ | CURRENT (v15) | |

## State Infrastructure (P2-M1)

| Module | Status | Purpose |
|--------|--------|---------|
| `state/connection.py` | ✅ EXISTS | ConnectionFactory, unified pragmas, 可重入事务（SAVEPOINT） |
| `state/transaction.py` | ✅ EXISTS | Transaction context manager |
| `state/errors.py` | ✅ EXISTS | 8 unified error types |
| `state/outbox.py` | ✅ EXISTS (P2-M5) | OutboxRepository + ExternalOperationRepository |
| `state/manual_state.py` | ✅ EXISTS (P2-M4) | ManualStateRepository with legacy import |
| `state/migrations/sqlsplit.py` | ✅ EXISTS (P2-M10) | 语句拆分/执行叶子模块，断开 definitions→helpers→runner 导入环 |

## Performance Validation (P2-M10)

| 资产 | 位置 | 作用 |
|------|------|------|
| 性能量具 | `scripts/state_perf_gate.py` | 12 个场景 × N 轮，min/median/mean/max/stdev + 相对阈值棘轮门禁 |
| 基线 | `docs/audit/state_perf_baseline.json` | 提交进仓的 median 基线；`--update-baseline` 采集（`data/` 是 gitignore 的运行时目录，不能放契约） |
| 报告 | `docs/audit/state_perf_report.json` | 最近一次完整测量输出 |
| 确定性门禁 | `tests/test_state_perf_gates.py` | EXPLAIN QUERY PLAN、连接复用计数、claim 互斥、语句数线性度 |

Schema 版本：HEAD = **v17**（v17 = 两条热读路径索引 `idx_changes_scope_time`、
`idx_outbox_due`，见 `state_infrastructure.md` §6.1）。

## Migration 版本清单

| Version | Name |
|---------|------|
| v14 | outbox_events + external_operations |
| v15 | readiness_snapshots |
| v16 | outbox_lease_and_manual_workflows |
| v17 | hot_read_perf_indexes |

## Direct sqlite3.connect Classification

| Module | Classification | Notes |
|--------|---------------|-------|
| state/connection.py | INFRASTRUCTURE_ALLOWED | ConnectionFactory |
| state/transaction.py | INFRASTRUCTURE_ALLOWED | transaction_from_path |
| state/backup.py | INFRASTRUCTURE_ALLOWED | Backup tooling |
| state/health.py | HEALTH_READ_ONLY | Read-only health check |
| state/recovery.py | INFRASTRUCTURE_ALLOWED | Recovery tooling |
| migrations/runner.py | MIGRATION_INTERNAL | Migration runner |
| bom/store.py | DOMAIN_STORE_TO_MIGRATE | BomStore |
| execution/closure_core.py | DOMAIN_STORE_TO_MIGRATE | ClosureStore |
| execution/runs.py | DOMAIN_STORE_TO_MIGRATE | ExecutionRunsStore |
| product_truth/store.py | DOMAIN_STORE_TO_MIGRATE | ProductTruthStore |
| supervisor/supervisor.py | DOMAIN_STORE_TO_MIGRATE | SupervisorStore |
| state/db.py | DOMAIN_STORE_TO_MIGRATE | AIPDStateDB |
| cli/_helpers.py | CLI_PROHIBITED | CLI direct connection |
