# State Infrastructure Architecture (P2-M1)

> Created: 2026-08-25 (HEAD: 13080c2)
> Status: Accepted

## 1. Overview

统一状态基础设施层，规范 AIPD-OS 的数据库连接、事务管理、错误语义和
Repository scope 一致性。

## 2. Module Structure

```
src/aipd_os/state/
    connection.py    — ConnectionFactory, 统一 pragma 配置
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
- `timeout = 10000` — 10s 连接超时
- `synchronous = NORMAL` — 性能/安全平衡
- `row_factory = sqlite3.Row`

**journal_mode=WAL** — 暂不全局开启。需要在 Windows/macOS/Linux/
共享文件系统和 test isolation 场景验证后再决定。当前使用默认 DELETE journal。

## 4. Transaction Policy

`transaction(conn)` context manager:

- yield conn → 使用方执行 SQL
- 成功 → `conn.commit()`
- 异常 → `conn.rollback()` + re-raise

Repository 方法不应在每个 INSERT 后自行 commit。
上层 Domain Service 定义事务边界。

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

## 7. Cross-Store Boundary

同一业务动作跨 store 时，不要假装是 atomic。
后续由 Outbox/Saga 解决跨 store 一致性。
