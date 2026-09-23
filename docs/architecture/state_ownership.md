# State Ownership：对象归属、事务边界与收敛路径（P2）

> 目标：明确每类对象的 canonical owner / storage / 事务边界 / 版本化 / 审计行为，
> 回答「一个 project 的 canonical truth 在哪里」，并给出收敛路径。
> 详见 `state_inventory.md` 完整审计。
> 更新：2026-09-24 — P2-M10 关闭，收敛路径全部落地（F5–F8 为收口期新增发现）。

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
| Closure runs/events/checkpoints/tool_calls/deps/stale | `ClosureStore` | ClosureEngine | ✓ (P2-M2) | ✓ | 无 | 无 |
| Manual state (pages/prompts/batches) | Canonical + legacy JSON | ManualStateRepository | ✓ (P2-M4) | ✓ | version | import_ledger |
| Outbox events | `state.db` (v14) | OutboxRepository | ✓ (P2-M5) | ✓ | attempt_count | completed_at |
| External operations | `state.db` (v14) | ExternalOperationRepository | ✓ (P2-M5) | ✓ | status machine | idempotency_key |
| Readiness snapshots | `state.db` (v15) | ReadinessService | ✓ | ✓ | ruleset_version | superseded flag |

## 2. P2 Findings — Status

| Finding | Risk | Status | Notes |
|---------|------|--------|-------|
| F1: ClosureStore missing tenant_id | HIGH | ✅ FIXED (P2-M2) | All 6 tables have tenant_id + project_id |
| F2: Manual JSON has no scope | HIGH | ✅ FIXED (P2-M4) | ManualStateRepository with canonical + legacy import |
| F3: No unified connection policy | MEDIUM | ✅ FIXED (P2-M1) | ConnectionFactory + transaction context manager |
| F4: No outbox for external side effects | HIGH | ✅ FIXED (P2-M5) | OutboxRepository + ExternalOperationRepository with state machine |
| F5: `ConnectionFactory.transaction()` 重入即自死锁 | **CRITICAL** | ✅ FIXED (P2-M10) | 重入改为复用外层连接 + SAVEPOINT；`run_supervisor` 此前整体退化为 internal_rework |
| F6: stale 传播写 `changes` 用了不存在的列 | HIGH | ✅ FIXED (P2-M10) | `entity_type/entity_id/change_type/change_data` → `object_type/object_id/action/after_json/reason` |
| F7: 热读路径缺索引（changes scope / outbox claim 排序） | MEDIUM | ✅ FIXED (v17) | 两条索引；写放大实测不可测出 |
| F8: migrations 模块化引入导入环 | MEDIUM | ✅ FIXED (P2-M10) | 工具下沉到 `migrations/sqlsplit.py` 叶子模块 |

F5/F6/F8 由 P2-M10 的回归与性能量具暴露：F5、F8 是既有测试在 HEAD 上
真实失败（不是新测试判红），F6 只在「依赖图非空」时触发，而原有用例
全部跑在零依赖图上。详见 `docs/audit/P2_M10_STATE_PERF_CLOSURE_2026-09-24.md`。

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

| 里程碑 | 内容 | 状态 |
|---|---|---|
| P2-M1 | Common DB infrastructure（连接工厂、pragma、事务边界） | ✅ 完成；重入语义在 P2-M10 修订（见 F5） |
| P2-M2 | ClosureStore / ExecutionRuns 的 tenant/project scope | ✅ 完成 |
| P2-M3 | Repository facade（上层不再直连 SQLite） | ✅ 完成（5 个 store 迁移到 ConnectionFactory） |
| P2-M4 | Manual JSON → canonical DB | ✅ 完成 |
| P2-M5 | Outbox + external operation ledger | ✅ 完成（含 lease + dispatcher runtime） |
| P2-M6 | 统一 stale / dependency 传播 | ✅ 完成（cost_snapshot 分支在 P2-M10 修复，见 F6） |
| P2-M7 | Readiness snapshot + ruleset 版本化 | ✅ 完成 |
| P2-M8 | Migration modularization | ✅ 完成（导入环在 P2-M10 断开，见 F8） |
| P2-M9 | 乐观并发 + audit trail | ✅ 完成 |
| P2-M10 | 性能验证 + 全量回归 | ✅ 完成（`scripts/state_perf_gate.py` + `tests/test_state_perf_gates.py`） |

**P2 收敛路径到此关闭。** 后续变更需同时通过：全量回归、CI 范围的
ruff/mypy、`production_release_gate.py --release-ready`、以及性能棘轮。
