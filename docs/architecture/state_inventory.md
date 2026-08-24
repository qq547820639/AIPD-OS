# State Inventory — AIPD-OS P2 Baseline

> Generated: 2026-08-24 (HEAD: 1509746)
> Purpose: P2 State Ownership Convergence — complete persistence point audit

## Physical Stores

| # | Store | Path Convention | Module | Tables |
|---|-------|----------------|--------|--------|
| 1 | AIPDStateDB | `state.db` | `state/db.py` | 30+ (tenants, users, projects, facts, evidence, claims, ideas, requirements, features, validation_*, issues, corrective_actions, product_definition_snapshots, gate_evaluations, product_definition_commits, ...) |
| 2 | ExecutionRuns | `*.runs.db` | `execution/runs.py` | execution_runs |
| 3 | ClosureStore | `<db>.closure.db` | `execution/closure_core.py` | closure_runs, closure_events, closure_checkpoints, closure_tool_calls, closure_dependencies, closure_stale |
| 4 | BomStore | `<state.db>.bom.db` | `bom/store.py` | boms, bom_lines, bom_id_sequences, bom_changes |
| 5 | ProductTruth | `<state.db>.truth.db` | `product_truth/store.py` | product_truth, truth_lineage, rework_tasks |
| 6 | Supervisor | `<state.db>.supervisor.db` | `supervisor/supervisor.py` | supervisor_work_items, supervisor_phase_runs, supervisor_capabilities, supervisor_reviews, supervisor_lineage, supervisor_assertions, decisions |
| 7 | Manual JSON | `<db>.manual.json` | `cli/commands_manual.py` | N/A (JSON file) |

## Tenant/Project Scope Analysis

| Store | tenant_id | project_id | Composite PK | Cross-tenant risk |
|-------|-----------|------------|--------------|-------------------|
| AIPDStateDB | ✅ (migration v1+) | ✅ | (entity_id, tenant_id, project_id) | LOW |
| ExecutionRuns | ✅ (added post-v5.7) | ✅ | (run_id) with tenant_id column | MEDIUM — PK is just run_id |
| **ClosureStore** | **❌ MISSING** | ✅ | (run_id) PK only | **HIGH — no tenant isolation** |
| BomStore | ✅ | ✅ | (bom_id, tenant_id, project_id) | LOW |
| ProductTruth | ✅ | ✅ | (entity_id, tenant_id, project_id) | LOW |
| Supervisor | ✅ (default 'default') | ✅ | varies by table | LOW |
| Manual JSON | ❌ | ❌ | N/A | HIGH — no scope |

## Critical Findings

### F1: ClosureStore missing tenant_id (P2-M2)
- All 6 closure tables have NO tenant_id column
- Only `project_id` exists on `closure_runs` (and empty string default)
- Other closure tables (events, checkpoints, tool_calls, dependencies, stale) have only `run_id` FK
- **Risk**: Cross-tenant data leakage if two tenants share a closure DB path
- **Fix**: Add tenant_id to all closure tables via migration v14

### F2: ExecutionRuns PK not tenant-scoped (P2-M2)
- `execution_runs` has `run_id TEXT PRIMARY KEY` (not composite)
- tenant_id was added as ALTER TABLE post-v5.7 with DEFAULT 'default'
- **Risk**: If run_id collides across tenants, data corruption
- **Fix**: Add composite index (tenant_id, project_id, run_id); consider PK rebuild

### F3: Manual JSON has no scope (P2-M4)
- `*.manual.json` stores plan/generate state as flat JSON
- No tenant_id, no project_id, no version
- CLI reads/writes directly via Path operations
- **Fix**: ManualStateRepository with canonical DB storage + legacy JSON fallback

### F4: No unified connection policy (P2-M1)
- 6+ modules call `sqlite3.connect()` independently
- No common pragmas (foreign_keys, busy_timeout, timeout)
- No shared transaction boundary
- **Fix**: `state/connection.py` with ConnectionFactory + transaction context manager

### F5: No outbox for external side effects (P2-M5)
- External operations (CAD generation, supplier calls) have no idempotency ledger
- `execution_runs.side_effect_mode` exists but no structured operation tracking
- UNKNOWN_OUTCOME not distinguished from FAILED
- **Fix**: outbox_events table + operation_ledger table

### F6: Supervisor legacy decisions table (P2-M2)
- `SUPERVISOR_LEGACY_DECISIONS_SCHEMA` creates `decisions` without tenant_id
- Used only when `state_db` not provided
- **Risk**: Legacy decisions table has no tenant scope
- **Fix**: Migration to ensure all decisions go through AIPDStateDB

## Classification

| Store | Classification | Rationale |
|-------|---------------|-----------|
| AIPDStateDB | CANONICAL | Single source of truth for project domain |
| ExecutionRuns | EXECUTION_LOG | Runtime telemetry, not product truth |
| ClosureStore | EXECUTION_LOG | Runtime telemetry, not product truth |
| BomStore | CANONICAL | BOM is product truth |
| ProductTruth | CANONICAL | Product definition truth |
| Supervisor | CANONICAL | Work items and phase runs are authoritative |
| Manual JSON | LEGACY_STATE | Being migrated to canonical DB |
