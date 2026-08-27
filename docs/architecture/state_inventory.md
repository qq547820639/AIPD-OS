# State Inventory — AIPD-OS P2

> Updated: 2026-08-25 (HEAD: 10f8020)
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
| `state/connection.py` | ✅ EXISTS | ConnectionFactory, unified pragmas |
| `state/transaction.py` | ✅ EXISTS | Transaction context manager |
| `state/errors.py` | ✅ EXISTS | 8 unified error types |
| `state/outbox.py` | ✅ EXISTS (P2-M5) | OutboxRepository + ExternalOperationRepository |
| `state/manual_state.py` | ✅ EXISTS (P2-M4) | ManualStateRepository with legacy import |

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
