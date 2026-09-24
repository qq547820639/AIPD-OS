# State Infrastructure Architecture (P2-M1)

> Created: 2026-08-25 (HEAD: 13080c2)
> Updated: 2026-09-24 (HEAD: 1d0f84f + P2-M10 收口)
> Status: Accepted

## 1. Overview

统一状态基础设施层，规范 AIPD-OS 的数据库连接、事务管理、错误语义和
Repository scope 一致性。

## 2. Module Structure

```
src/aipd_os/state/
    connection.py    — ConnectionFactory, 统一 pragma 配置 + 可重入事务
    transaction.py   — transaction context manager
    errors.py        — 统一错误类型层次
    migrations/      — 迁移框架（已模块化）
    db.py            — AIPDStateDB（canonical state store）
    ...
```

## 3. Connection Policy

**ConnectionFactory** 统一所有 SQLite 连接：

- `foreign_keys = ON` — 必须
- `busy_timeout = 5000` — 5s 等待锁
- `synchronous = NORMAL` — 性能/安全平衡
- `row_factory = sqlite3.Row`
- 连接等待由 `sqlite3.connect(timeout=10)` 控制。
  本文此前记录的 `PRAGMA timeout = 10000` **不存在**：SQLite 对未识别的
  pragma 静默忽略（实测发出后 `busy_timeout` 读数不变），故从策略中删除。

**journal_mode=WAL** — 暂不全局开启。需要在 Windows/macOS/Linux/
共享文件系统和 test isolation 场景验证后再决定。当前使用默认 DELETE journal。

## 4. Transaction Policy

`transaction(conn)` context manager:

- yield conn → 使用方执行 SQL
- 成功 → `conn.commit()`
- 异常 → `conn.rollback()` + re-raise

Repository 方法不应在每个 INSERT 后自行 commit。
上层 Domain Service 定义事务边界。

### 4.1 重入规则（P2-M10 修订，必读）

`ConnectionFactory.transaction()` 在同一 **(库路径, 线程)** 上**可重入**：

- 外层无活动事务 → 新开连接 + `BEGIN IMMEDIATE`，并把连接登记为活动事务；
- 已有活动事务 → **复用同一连接**并开 `SAVEPOINT`；退出时 `RELEASE`，
  内层异常先 `ROLLBACK TO` 保存点再抛出，外层事务保持有效；
- 登记表以「解析后的绝对路径 + 线程 ident」为 key，而非以工厂实例为 key。
  原因：`Supervisor.connect()` 每次调用都新建一个 `ConnectionFactory`，
  实例级状态看不见外层事务。
- `AIPDStateDB.connect()/transaction()` 自 **F-STATE-06** 起委托
  `ConnectionFactory`，与所有 store **真的共用这一张表**。
  在此之前本文档写的是「共用同一形状」，而实现是两张互不可见的表，
  且 `AIPDStateDB` 的活动连接放在**模块级单个** thread-local 槽里、
  不按库路径分键 —— 结果是「A 库事务里开 B 库事务」会把 A 的连接交给 B，
  本该写进 B 的语句落进 A（不报错）。三条契约由
  `tests/test_connection_reentrancy.py::TestOneRegistryAcrossEntries` 锁住。

**为什么这是硬约束**：写锁按连接持有。若重入时另开连接再 `BEGIN IMMEDIATE`，
它会与自己的外层写锁互等，`busy_timeout` 到点后抛 `database is locked`——
这不是并发问题，是单线程自我死锁。P2-M3 把 5 个 store 迁到
ConnectionFactory 后，`run_supervisor` 的 execute 阶段因此整体退化为
`internal_rework`（`add_lineage → project_id → connect` 即触发）。
`tests/test_connection_reentrancy.py` 锁住该契约。

**禁止**：Repository 方法在自己的事务内调用另一个 store 的事务型方法
而不走 `transaction()` 重入——那会绕开保存点语义。

### 4.2 边界

跨库（例如 `state.db` 与 `*.bom.db`）不共享登记表：不同文件的不同连接
本就允许并存，但**不保证原子性**（见 §7）。

### 4.3 建表/DDL 不许用 `executescript()`（F-STATE-05）

`sqlite3` 的 `Cursor.executescript()` 在执行前先**隐式 COMMIT**。因此
「在 `transaction()` 里 `executescript()` 建表」会把调用方在同一库同一线程上
尚未提交的写一起提交掉（回滚失效），DDL 脚本自身也不再原子（中途失败留半个 schema）。

规则：多语句 DDL 一律走 `state/migrations/sqlsplit.exec_script(conn, script)`
（拆分后逐条 `execute`，不隐式提交）。`store.__init__` 里建表也在其内——
五个 store 都曾命中该形状。反证与配对对照见
`tests/test_ddl_transaction_atomicity.py`。

## 5. Error Taxonomy

| Error | 含义 |
|-------|------|
| `NotFoundError` | 请求的实体不存在 |
| `ConflictError` | 唯一约束违反 |
| `ConcurrentModificationError` | 乐观并发 lost update |
| `TenantScopeViolation` | 跨 tenant 数据访问 |
| `ProjectScopeViolation` | 跨 project 数据访问 |
| `InvalidTransitionError` | 状态转换不允许 |
| `MigrationError` | 迁移失败 |
| `ExternalOperationUnknownError` | 外部结果未知 (≠ FAILED) |

## 6. Repository Scope

所有 project-scoped entity 的查询必须包含 tenant_id + project_id。

危险模式: `get_by_id(id)` — 如果 id 非全局唯一
安全模式: `get(tenant_id, project_id, entity_id)`

## 6.1 热读路径必须有索引（P2-M10 / migration v17）

`EXPLAIN QUERY PLAN` 是门禁，不是文档（`tests/test_state_perf_gates.py`）：
热读查询不允许 `SCAN <table>`，也不允许 `USE TEMP B-TREE FOR ORDER BY`。

| 查询 | v17 前 | v17 后 |
|------|--------|--------|
| `changes` 按 (tenant, project) 取最近 N 条 | `SCAN changes` + 临时排序 | `SEARCH ... idx_changes_scope_time` |
| outbox `claim_available` | `SCAN ... idx_outbox_claim` + 对全量候选排序 | `SCAN ... idx_outbox_due`（有序、LIMIT 提前终止） |

实测收益与波动区间见 `docs/audit/P2_M10_STATE_PERF_CLOSURE_2026-09-24.md`
与 `docs/audit/state_perf_report.json`。

## 7. Cross-Store Boundary

同一业务动作跨 store 时，不要假装是 atomic。
后续由 Outbox/Saga 解决跨 store 一致性。
