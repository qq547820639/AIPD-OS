# State Ownership：对象归属、事务边界与收敛路径（P2）

> 目标：明确每类对象的 canonical owner / storage / 事务边界 / 版本化 / 审计行为，
> 回答「一个 project 的 canonical truth 在哪里」，并给出收敛路径。
> 详见 `state_inventory.md` 完整审计。

## 1. 对象归属表（P2 verified against HEAD 1509746）

| 状态对象 | 存储 | Canonical Owner | tenant_id | project_id | 版本化 | 审计 |
|---|---|---|---|---|---|---|
| Project / Fact / Evidence / Decision / Risk / Deliverable / Gate / Change | `AIPDStateDB` | StateService | ✓ | ✓ | `version_no` 乐观锁 | `audit_log` 表 |
| ValidationPlan / Test / Run / Result | `AIPDStateDB` (v13) | ValidationService | ✓ | ✓ | optimistic_version | audit_trail |
| Issue / CorrectiveAction | `AIPDStateDB` (v13) | IssueService | ✓ | ✓ | version | audit_trail_json |
| BOM / bom_lines | `BomStore` | BomService | ✓ | ✓ | version | bom_changes |
| Product Truth / lineage | `ProductTruthStore` | ProductTruthService | ✓ | ✓ | version | 无独立审计表 |
| Supervisor work/phase/capability/review/lineage | `SupervisorDB` | Supervisor | ✓ | ✓ | 无显式版本 | 部分经 audit |
| Execution runs | `ExecutionRunsDB` | RunStore | ✓ (post-v5.7) | ✓ | 追加式 | evidence_refs |
| **Closure runs/events/checkpoints/tool_calls/deps/stale** | **`ClosureStore`** | **ClosureEngine** | **❌ MISSING** | **✓ (run_id only)** | **无** | **无** |
| Manual state (pages/prompts/batches) | `.manual.json` | ManualChain | ❌ | 部分 | 无 | 无 |

## 2. Critical P2 Findings

### F1: ClosureStore missing tenant_id — HIGH risk
All 6 closure tables have NO tenant_id. Only `closure_runs.project_id` exists.
Cross-tenant data leakage possible if two tenants share a closure DB path.
**Fix**: Migration v14 adds tenant_id to all closure tables.

### F2: Manual JSON has no scope — HIGH risk
`*.manual.json` stores state as flat JSON with no tenant/project scope.
**Fix**: ManualStateRepository with canonical DB + legacy JSON fallback.

### F3: No unified connection policy
6+ modules call `sqlite3.connect()` independently with no common pragmas.
**Fix**: `state/connection.py` with ConnectionFactory + transaction context manager.

### F4: No outbox for external side effects
External operations have no idempotency ledger. UNKNOWN_OUTCOME not distinguished from FAILED.
**Fix**: outbox_events + operation_ledger tables.

## 3. Canonical Truth Map

```
AIPDStateDB (state.db)          ← CANONICAL: Project domain truth
├── tenants, users, sessions
├── projects, facts, evidence, decisions
├── ideas, claims, requirements, features
├── validation_plans/tests/runs/results
├── issues, corrective_actions
├── product_definition_snapshots
└── gate_evaluations, product_definition_commits

BomStore (*.bom.db)             ← CANONICAL: BOM truth
ProductTruthStore (*.truth.db)  ← CANONICAL: Product definition truth
SupervisorDB (*.supervisor.db)  ← CANONICAL: Work management truth

ExecutionRunsDB (*.runs.db)     ← EXECUTION_LOG: Runtime telemetry
ClosureStore (*.closure.db)     ← EXECUTION_LOG: Runtime telemetry
Manual JSON (*.manual.json)     ← LEGACY_STATE: Being migrated
```

## 4. Single-Writer Rule

| Canonical Domain | Writer | Readers |
|------------------|--------|---------|
| Project/Fact/Evidence | StateService | CLI, Web, Supervisor, Dashboard |
| Validation | ValidationService | CLI, ReadinessService, IssueService |
| Issues | IssueService | CLI, ReadinessService |
| BOM | BomService | CLI, CostService, ReadinessService |
| Product Truth | ProductTruthService | CLI, Supervisor, ReadinessService |
| Supervisor | Supervisor | CLI, Dashboard |

**Prohibited**: CLI, Web, Supervisor, Adapter directly writing SQL to canonical tables.

## 5. Transaction Model

- **Same-DB atomic**: AIPDStateDB operations within `db.connect()` context manager
- **Cross-store**: No distributed transaction — use outbox + idempotency (P2-M5)
- **External side effects**: Operation ledger with UNKNOWN_OUTCOME semantics (P2-M5)

## 6. Stale Propagation Rules

| Source Change | Affected Domain | Stale Rule |
|---------------|-----------------|------------|
| BOM material change | Cost snapshot | Old snapshot → stale |
| CAD revision change | Validation results | Affected results → stale |
| Requirement/CTQ change | Validation coverage | Linked results → stale |
| Supplier qualification change | Supply readiness | Supply dimension → stale |
| Blocking issue opens | Readiness | Immediately no longer PASS |
| Validation PASS becomes stale | Readiness | Readiness → HOLD |

## 7. Convergence Path (incremental, no big-bang)

1. **P2-M1**: Common DB infrastructure (connection factory, pragmas, transaction boundary)
2. **P2-M2**: Tenant/project scope for ClosureStore + ExecutionRuns
3. **P2-M3**: Repository facades (upper layers don't touch SQLite directly)
4. **P2-M4**: Manual JSON → canonical DB migration
5. **P2-M5**: Outbox + external operation ledger
6. **P2-M6**: Unified stale/dependency propagation
7. **P2-M7**: Readiness snapshot with ruleset versioning
8. **P2-M8**: Migration modularization
9. **P2-M9**: Optimistic concurrency + audit trail
10. **P2-M10**: Performance validation + full regression
