# 阶段6 审计：跨会话恢复能力 + 状态服务生产就绪性

- 审计目标：AIPD-OS（HEAD `651dfbc`，源码版本 5.3.0）
- 审计范围：PART A 跨会话恢复（新会话自动识别/恢复/继续）；PART B 状态服务生产就绪
- 运行环境：`.venv/bin/python`（Python 3.9.6），cwd=`AIPD-OS`
- 判定等级：`fully_implemented` / `partially_implemented` / `external_dependency` / `not_implemented` / `not_verifiable`
- 核心规则：**仅有 SQLite 文件、checkpoint JSON 或 MCP skeleton 不得标记为生产级跨会话能力。**

---

## 测试结果

| 测试集合 | 命令 | 结果 |
|---|---|---|
| 跨会话恢复（PART A） | `pytest tests/test_backup_checkpoint.py tests/test_experience.py -q` | **12 passed** |
| 状态服务（PART B） | `pytest tests/test_state_db.py tests/test_auth.py tests/test_crypto.py tests/test_objects.py tests/test_health.py tests/test_server_local.py tests/test_backup_checkpoint.py -q` | **24 passed** |

---

## PART A — 跨会话恢复能力逐项判定

跨会话恢复的机制链：`AIPDStateDB`（SQLite 状态库）→ `CheckpointManager`（`state/checkpoint.py`）→ `build_resume_summary`（`experience/resume_summary.py`）→ `OwnerView`（`experience/views.py`）→ CLI `aipd resume` / `aipd status`（`cli/commands.py`）。

| # | 子能力 | 状态 | 证据 | 测试 | 局限 |
|---|---|---|---|---|---|
| A1 | 识别项目 | **fully_implemented** | `cli/commands.py:cmd_resume` L583-620：`pid = args.project or _resolve_project(db)`；`_resolve_project` L54-58 自动取租户内首个项目 | 间接：`test_server_local.py::test_local_full_flow` | 无 `--project` 时只能自动选"第一个项目"，多项目下需显式传参，非真正"自动识别" |
| A2 | 获取最新检查点 | **fully_implemented** | `state/checkpoint.py:restore_latest` L22-27 → `db.latest_checkpoint` L707-716；`save_checkpoint` L18-20 | `test_backup_checkpoint.py::test_checkpoint_save_restore` | 仅按 `checkpoint_id DESC` 取最新，无多检查点合并 |
| A3 | 恢复 Product Truth（事实） | **fully_implemented** | `resume_summary` L42-49 列出 checkpoint 之后新增/变更事实；`db.list_facts` L429-438；完整恢复走 `db.export` L749 / `export_checkpoint` | `test_experience.py::test_resume_summary_lists_new_facts_not_resolved` | 摘要只给 key/status，不重复 value；完整值需另走 export |
| A4 | 恢复 Evidence Register | **partially_implemented** | `db.list_evidence` L497-501、`db.export` 含 `"evidence"` L753；但 `resume_summary`（L29-93）**不包含任何 evidence 字段** | 无针对性测试 | 证据可经 export_checkpoint 恢复，但**不进入恢复摘要/所有者视图**，新会话摘要看不到证据状态 |
| A5 | 恢复决策 | **fully_implemented** | `resume_summary` L34-36/L89-91 输出 `pending_decisions` + `resolved_decision_ids` | `test_backup_checkpoint.py::test_resume_summary_does_not_relist_resolved_decisions` | 决策本体（选项/推荐/影响）仍需另查 `list_decisions` |
| A6 | 恢复手工附件链 | **not_implemented** | 手册链状态存于**独立 JSON** `<db>.manual.json`（`cli/commands.py` L242/L678-682），不在 SQLite DB 内；`resume_summary` 与 `BackupManager`（仅拷 `.db` 文件，`backup.py` L40）均不覆盖它 | 无 | 备份/检查点不覆盖手册链；新会话无法自动恢复前批页面附件继承关系 |
| A7 | 恢复 CAD/BOM 修订 | **partially_implemented** | `experience/artifact_preview.py:artifact_preview` L44-100 从 `deliverables` + `changes`（均在 DB 内）重建 CAD 版本/BOM 差异；经 `OwnerView.owner_update` L139-148 进入视图 | `test_experience.py::test_artifact_preview_seeded_structure` | `resume_summary` 本身不含 CAD/BOM 修订，仅 `OwnerView` 汇总时带出；修订历史依赖 `changes` 表已写入 before/after |
| A8 | 恢复外部等待项 | **fully_implemented** | `resume_summary` L58-63 从 `list_dependencies`（needs_external/blocked_by_external）+ 项目状态 `blocked_external` 汇总；`external_wait.py:summarize_external_wait` 分桶为供应商/实验室/其他 | 间接：视图测试 `test_experience.py::test_owner_view_composition` | 无直接单测覆盖外部等待项恢复 |
| A9 | 不重新追问已解决问题 | **fully_implemented** | `resume_summary` 跟踪 `resolved_decision_ids` L36/L91；`resume_summary.py:build_resume_summary` L19-26 过滤掉已解决决策，`decisions_to_ask` 只含未解决项 | `test_backup_checkpoint.py::test_resume_summary_does_not_relist_resolved_decisions`；`test_experience.py::test_resume_summary_lists_new_facts_not_resolved` | 仅对"决策"免重复追问；事实/其他问题仍可能重提 |
| A10 | 产出简洁恢复摘要 | **fully_implemented** | `build_resume_summary` L15-55 返回中文自然语言结构（where_left_off/current_phase/next_action/…）；CLI `cmd_resume` prose L605-618；`render_markdown` L60-125 | `test_experience.py::test_owner_view_composition` | 摘要为"汇总"而非执行轨迹回放 |
| A11 | 自动继续执行 | **not_implemented** | `cmd_resume` L583-620 只产出摘要，**不调用 `run_supervisor`/`cmd_run`**；`cmd_run`（L444-502）与 resume 相互独立，无 resume→run 自动接力 | 无 | 新会话"识别→恢复→自动继续"链条到"继续执行"一环断裂，需人工再发 `aipd run` |

**PART A 小结**：A1/A2/A3/A5/A8/A9/A10 为真实代码+测试，genuinely implemented；A4/A7 部分实现；A6（手工附件链）、A11（自动继续执行）**未实现**。跨会话恢复的"读取与汇总"能力扎实，但**恢复后不会自动继续执行**，且**手工附件链不在状态库/备份范围内**。

---

## PART B — 状态服务生产就绪性逐项判定

状态服务 = `src/aipd_os/state/`（`server.py` 的 `StateService`，本地库）+ `state_service/mcp_server.py`（MCP 薄层）。`state_service/README.md` 自述"可运行骨架 + 本地持久状态实现"，并列出"生产化必须补充"清单。

| # | 能力 | 状态 | 证据 | 测试 | 局限 |
|---|---|---|---|---|---|
| B1 | 身份认证 | **fully_implemented**（库） | `state/auth.py:AuthManager`：PBKDF2-HMAC-SHA256 密码哈希 L32-46、HMAC 令牌签发/校验 L65-86、register/login/verify L48-62；`server.py` 暴露 `auth_register/auth_login/auth_verify` L70-86 | `test_auth.py`（4 例） | 默认密钥 `change-me-secret`（`auth.py` L27、`server.py` L37）；**HTTP 传输层不校验令牌**（见 B2） |
| B2 | 项目权限 | **partially_implemented** | 库层：`require_project_access` L92-97 + `user_access` 表（`db.py` L49-54/L330-341）；`StateService._authorize` L60-63 | `test_auth.py::test_project_access_denied_for_unauthorized` | **HTTP `/rpc` 传输（`server.py` L271-283）不解析也不校验任何令牌**，`actor=None` 直接跳过授权；`init_project/add_evidence/add_risk/add_deliverable/object_*` 等也未调用 `_authorize`。网络层可被绕过 |
| B3 | 多租户隔离 | **fully_implemented** | `tenant_id` 全表字段 + 查询按租户过滤（`db.py` SCHEMA）；`list_projects` L368、`get_project` L360 | `test_state_db.py::test_multi_tenant_isolation` | 隔离仅在库层查询参数层面，无网络层强制 |
| B4 | 数据加密 | **partially_implemented** | `state/crypto.py`：Fernet（cryptography 可选）/XOR+HMAC 回退 L39-72；`db.py` `_store_value/_read_value` 仅对 `SENSITIVE_KEYS`（L26-29）加密 | `test_crypto.py`（4 例）、`test_state_db.py::test_sensitive_field_encrypted_at_rest` | 仅**敏感字段**加密，且仅在提供 `encryption_key` 时；**SQLite 整库文件未做静态加密**；无密钥轮换 |
| B5 | 文件对象存储 | **fully_implemented** | `state/objects.py:ObjectStore` put/get/list/delete/retention（L33-79）；`server.py` object_put/get/list/delete L203-217 | `test_objects.py`（3 例，含租户隔离目录） | 对象按 `<base>/<tenant>/<project>/<key>` 本地目录存放，非分布式对象存储 |
| B6 | 数据库迁移 | **fully_implemented** | `state/migrations.py`：schema_migrations 记录、migrate/rollback/applied_versions L71-123；`migrations/v4_to_v5.py`、`rollback_v5.py` | `test_migration.py::test_migrate_then_rollback` | 迁移表仅初始 v1 一条 |
| B7 | 并发与事务 | **fully_implemented**（有限） | `db.py:connect` L255-267 事务提交/回滚；乐观锁 `_update` L270-280（version_no 校验，冲突抛 `OptimisticLockError`） | `test_state_db.py::test_optimistic_lock_conflict...` | SQLite 单文件，无 WAL / busy_timeout，多写并发能力有限；非高可用数据库 |
| B8 | 备份 | **fully_implemented** | `state/backup.py:BackupManager.create_backup` L31-50（拷库+sha256 manifest）；`server.py:create_backup` L220-224 | `test_backup_checkpoint.py::test_create_restore` | 仅备份 `.db` 文件，**不含手册链 JSON、对象存储目录** |
| B9 | 恢复 | **fully_implemented** | `backup.py:restore_backup` L69-88（校验 checksum，不匹配拒绝）；`server.py:restore_backup` L229-230 | `test_backup_checkpoint.py::test_create_restore` | 恢复前不停机/无锁，SQLite 文件替换有并发风险 |
| B10 | 审计日志 | **fully_implemented** | `state/audit.py:AuditLogger` 追加式 JSONL + 同步 `audit_log` 表 L24-37；`server.py` 各写方法 `_audit` L65-67 | 无独立单测 | 日志未做防篡改/加密/签名；`list_projects/get_project/list_facts/restore_checkpoint` 等读操作不记审计 |
| B11 | 保留期（retention） | **fully_implemented** | `backup.py:retention_prune` L90-108；`objects.py:retention_prune` L61-79 | `test_backup_checkpoint.py::test_retention_prune`、`test_objects.py::test_retention_prune` | 纯本地目录清理，无策略持久化 |
| B12 | 健康检查 | **fully_implemented** | `state/health.py:health_check` L13-59（连通性/schema 版本/备份新鲜度/磁盘剩余）；`server.py:health` L242-243、HTTP `/health` L265-269 | `test_health.py` | 无 gRPC/系统负载等深度指标 |
| B13 | 指标（metrics） | **not_implemented** | 全仓无 metrics 模块；`server.py` 仅 `/health`，无 Prometheus/统计端点/请求计数 | 无 | 无任何可观测性指标 |
| B14 | 密钥管理 | **partially_implemented** | 仅环境变量 `AIPD_SECRET`（默认 `change-me-secret`）、`AIPD_ENCRYPTION_KEY`（默认空）传入（`server.py` L301-312）；crypto 用 HMAC 密钥派生 | 无 | 无 Vault/密钥仓库/轮换/加密存储；默认弱密钥，生产不可直接使用 |

**PART B 小结**：B1/B3/B5/B6/B8/B9/B10/B11/B12 为真实代码 + 测试，构成一个**功能完整的本地状态库**；B2/B4/B7/B14 部分实现（存在传输层鉴权缺失、仅字段级加密、SQLite 并发受限、无密钥管理）；**B13 指标完全未实现**。

---

## 总体判定：状态服务是否生产级？

**不是生产级部署服务，但也不是"仅有 SQLite 文件 + checkpoint JSON + MCP skeleton"。**

- **真实实现（真实代码 + 通过测试）**：多租户 SQLite 状态库、PBKDF2 认证、项目级授权、字段级加密、对象存储、schema 迁移、乐观锁事务、备份/恢复（含校验和）、审计日志、retention、健康检查。这在**本地库/单进程**层面是完整且可用的，远不止一个 MCP skeleton。
- **不足以判定为"生产级"** 的关键缺口：
  1. **HTTP 传输层完全未鉴权**（`server.py` `_RpcHandler.do_POST` L271-283 直接调用 `service.call`，不校验令牌；`actor=None` 即跳过授权）——一旦作为网络服务部署，认证/权限/多租户隔离可被绕过；
  2. **无指标（metrics）**（B13 not_implemented）；
  3. **无真实密钥管理**（B14，默认弱密钥、明文环境变量、无轮换）；
  4. **SQLite 单文件**（无 WAL/busy_timeout/HA），多写并发与高可用不足；
  5. 备份/检查点**不覆盖手工附件链 JSON 与对象存储**，跨会话恢复完整性受影响；
  6. `state_service/README.md` L15-22 自述"生产化必须补充 身份认证/多租户/加密/密钥管理/备份/迁移/网络传输配置/限流"——其中多数已在 `src/` 补齐，但**网络传输鉴权、限流、指标、密钥管理仍缺失**。

结论：状态服务是**一个实现扎实、有测试证明的本地状态库**，可作为生产能力的"内核"，但**作为部署上线服务尚未达到生产就绪**，不能标记为"生产级跨会话能力"。

---

## 关键局限汇总（修复优先级参考）

- **P1**：HTTP/JSON RPC 传输层鉴权缺失（`server.py` L271-283），授权可绕过。
- **P1**：手工附件链存于独立 `<db>.manual.json`，不在状态库/备份/检查点范围内，新会话无法恢复（A6）。
- **P1**：`aipd resume` 只出摘要，不自动续跑（A11），"自动继续执行"未打通。
- **P2**：无 metrics（B13）、无真实密钥管理（B14）。
- **P2**：Evidence Register 不进恢复摘要（A4）；CAD/BOM 修订仅经 OwnerView（A7）。
- **P2**：默认弱密钥 `change-me-secret` / 空加密密钥；SQLite 无 WAL/busy_timeout。