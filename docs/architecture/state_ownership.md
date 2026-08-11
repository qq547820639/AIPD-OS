# State Ownership：对象归属、事务边界与收敛路径（P1-2）

> 目标：明确每类对象的 canonical owner / storage / 事务边界 / 版本化 / 审计行为，
> 回答「一个 project 的 canonical truth 在哪里」，并给出收敛路径。

## 1. 对象归属表（来源：REPOSITORY_MAPS.md D 节）

| 状态对象 | 存储 | Canonical Owner | 租户/项目 | 版本化 | 审计 |
|---|---|---|---|---|---|
| Project / Fact / Evidence / Decision / Risk / Deliverable / Gate / Change / Checkpoint | `AIPDStateDB`（`state/db.py`，复合主键含 tenant_id+project_id） | StateService | ✓ | `version_no` 乐观锁（`_update`，冲突抛 `OptimisticLockError`） | `audit_log` 表 + `audit.log` JSONL（`AuditLogger`） |
| user_access / sessions | `AIPDStateDB` | AuthManager | ✓（user_access 含 tenant/project） | 无（授权行直接覆盖） | 敏感操作经 StateService 审计 |
| supervisor_work_items / phase_runs / capabilities / reviews / lineage / claims | Supervisor 表（`scripts/aipd_supervisor.py`） | Supervisor | 仅 project_id，**无 tenant_id** | 无显式版本 | 部分经 audit |
| product_truth / truth_lineage / rework_tasks | `ProductTruthStore`（`product_truth/store.py`） | ProductTruthStore | ✓（CS6 起含 tenant/project） | `version` 递增（返工 bump） | 无独立审计表 |
| execution_runs | `RunStore`（`execution/runs.py`） | ExecutionRouter | project_id（无 tenant_id） | 追加式（retry_lineage） | evidence_refs / output_hash |
| 附件 / manual_batch / visual_bible 对象 | `ObjectStore`/`LocalStateBackend` + attachment index | UnifiedStateService | ✓ | sha256 | 统一备份 manifest |
| Manual 状态（pages/prompts/batches） | `.manual.json`（独立 JSON） | ManualChain | 仅 project_id 字段 | 无 | 无（已知债务，见收敛） |
| 闭包运行 | `ClosureStore`（`execution/closure_core.py`） | ClosureEngine | 待查 | 无显式版本 | 无 |

## 2. 一个 project 的 canonical truth 在哪里

**主事实**（facts）在 `AIPDStateDB.facts`：epistemic 状态 V/S/C/E/A/P/T/R + confidence + source，
是 owner/dashboard/supervisor 读取的「当前真相」。但 **Product Truth 级对象、
Supervisor 工作项、Manual 状态、执行记录分散在多个独立存储**，互不统一
（REPOSITORY_MAPS.md 已记录此债务）。CS6 已把 ProductTruth 三表纳入
tenant/project 作用域，但尚未并入主库。

## 3. 事务边界

- 单对象写操作（fact/decision/evidence/risk/deliverable）在 `AIPDStateDB.connect()`
  的单个事务内完成（`db.py` contextmanager：成功 commit、异常 rollback）。
- 跨存储操作（例如「执行成功 → 写 Product Truth + 更新 deliverable」）**没有
  分布式事务**：目前靠执行顺序 + 追加式记录保证可审计，不保证原子性。
- 乐观锁只保护单表版本冲突；跨表一致性需要上层补偿/返工（`propagation` 的
  stale/blocked 语义）。

## 4. 收敛路径（不一次性重写 DB）

1. **先定边界**：以 StateService 为 canonical API，禁止外部直接写 `AIPDStateDB`
   之外的存储（Manual/Closure/Supervisor 表逐步收敛到 StateService 门面）。
2. **统一作用域**：为 supervisor 表、execution_runs、`.manual.json` 补齐
   tenant_id（已在计划中；`state_backend.py` 已提供统一对象存储抽象）。
3. **统一版本化**：对需要跨对象因果链的证据（执行 → truth → 制品），复用
   `execution_runs.idempotency_key / remote_operation_id` 与 truth `version` 串联。
4. **统一审计**：所有状态变更经 `AuditLogger.log`（JSONL + audit_log 表）落审计；
   独立存储自身的写入也追加 audit 事件，不改变既有表结构。

收敛是增量迁移：每一步保持旧读路径可用，新写路径统一走 StateService。
