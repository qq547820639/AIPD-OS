# AIPD-OS Foundation Stabilization Report

**Date**: 2026-08-12 · **HEAD**: 2541be8 (v5.6.0) + CS1–CS14 工作树
**Gate 判定**: **PASS**（依据见 §8）
**执行方式**: 仓库接管 → 基线 → 14 个 change set（小 diff / 每步真实跑测 / QA 独立复核）→ 全量回归。

---

## 1. 修改内容（CS1–CS14）

| # | Change Set | 覆盖 | 核心变更 |
|---|---|---|---|
| CS1 | 认证与授权边界 | P0-1/2/3 | 全量 project-scoped RPC 授权；grant_access 管理员门控；通配规范化（None→'*'，历史 NULL 兼容）；HTTP public 白名单（auth_login/register）；audit 遮蔽修复（_audit_logger + list_audit_events） |
| CS1-FIX | actor 冒充漏洞 | P0-1 | `_inject_actor` 强制覆盖客户端 actor；授权失败 403（401=未认证/403=无权限）；删除 server.py 本地重复 AuthError 类 |
| CS2 | secret/crypto 门控 | P0-4/5 | 服务模式缺/弱 secret fail-closed（require_strong_secret）；AIPD_INSECURE_DEV_MODE 显式降级 + WARNING；crypto XOR 回退仅 dev 模式允许；docstring 修正 |
| CS3 | Web 批准安全 | P0-13 | start_run 不再自授 approved；needs_approval 落 pending decision；AIPD_WEB_TOKEN 认证；非 localhost 拒启；1MB 请求限制 |
| CS4 | 执行幂等 | P0-6 | side_effect_mode（PURE/IDEMPOTENT/EXTERNAL_SIDE_EFFECT/NON_RETRYABLE）；idempotency_key 去重；EXTERNAL 副作用不重试；remote_operation_id/execution_id/attempt_number |
| CS5 | Research 诚实 | P0-7 | research adapter 真实 Semantic Scholar API（urllib）；错误→external_blocked；router 对 simulated 标记强制降级（含嵌套 cad_contract） |
| CS6 | ProductTruth 作用域 | P0-8/9/10 | 三表 tenant/project 列（就地 ALTER 迁移）；metadata 完整往返；无 executor 返工 blocked（删 _default_rework 假成功） |
| CS7 | Manual 诚实 | P0-11 | _build_defn 缺省 → 显式 TBD + truth_gaps 审计字段；删除伪造曲线/外骨骼默认事实 |
| CS8 | Manual 状态统一 | P0-12 | 文档化架构债务与收敛路径（对象化迁移列入后续） |
| CS9 | CAD 契约/哈希 | P0-15/14 | validate_param/validate_geometry_params 单源校验（fillet=0 合法）；ContractBackend 对齐；semantic_geometry_hash |
| CS10 | 版本/文档 | P0-16, P1-3/4/5 | README/QUICKSTART/SECURITY/THREAT_MODEL/architecture/cli 对齐 5.6.0；跨文件版本一致性测试；4 份架构文档；import-cycle 测试；bundle 排除 .venv/dist-info |
| CS11 | 异常治理 | P1-6 | 19 处空 except 全处置（9 修复带 log + 10 noqa 豁免带原因）；AST 卫生测试 |
| CS12 | Supervisor 包化 | P1-1 | scripts/aipd_supervisor.py → src/aipd_os/supervisor/ + 兼容 wrapper；CLI/selftest_v4 全兼容 |
| CS13 | golden 隔离 | 基线副作用 | golden e2e 默认写临时目录；AIPD_GOLDEN_RELEASE/AIPD_PIN_COMMIT pin 模式才写 tracked |
| CS14 | ruff 增量清零 | 质量门 | 新增文件 0 违规；全仓 3090 < 基线 3298（存量债未清零，非目标） |

## 2. Schema / Migration

| 存储 | 变更 | 迁移方式 |
|---|---|---|
| user_access | 通配写入 '**'（None 规范化）；历史 NULL 行兼容读取 | 无 DDL 变更（逻辑兼容） |
| execution_runs | +idempotency_key/side_effect_mode/remote_operation_id | `_ensure_columns` 就地 ALTER（旧库自动补列，默认 PURE/''） |
| product_truth / truth_lineage / rework_tasks | +tenant_id/project_id（默认 'default'）；product_truth +metadata_json；lineage UNIQUE 复合键 | `_ensure_columns` 就地 ALTER（迁移测试覆盖） |
| schema_migrations | 未新增版本（均采用就地 ALTER 兼容模式，避免破坏既有迁移链） | — |

## 3. Breaking Changes

- **有意的行为变更（符合任务要求）**：
  - HTTP RPC 授权缺口全部封闭：越权访问从"可访问"变为 **403**；未认证 **401**（语义分化）。
  - `auth_register` 不再隐式授予租户通配；`init_project(actor=...)` 创建者自动成为成员。
  - Web `start_run` 不再自动批准（needs_approval 落决策中心显式批准）。
  - research adapter 配置 key 后行为从 simulated 占位变为真实 API 调用（或 external_blocked）。
  - manual_chain 缺 facts 时输出 TBD 而非外骨骼默认文案。
  - 服务模式（server/mcp）缺失强 secret 拒绝启动。
- **无**：CLI 命令兼容性、本地模式（actor=None）行为、现有测试契约均保持。

## 4. Compatibility

- CLI：`aipd <cmd>` 34 命令与 `python scripts/aipd_supervisor.py <cmd>` 子命令完全兼容（wrapper 验证）。
- 本地 API：`StateService(...)` 构造兼容（secret 可选，本地模式弱 secret 自动随机 + WARNING）。
- ProductTruthStore：`ProductTruthStore(path)` 不传租户/项目 → 默认 'default'（旧测试原样通过）。
- golden 证据：releases/golden-projects 保持 pin 到已测 commit；测试默认不再写入。
- 根级清单（RELEASE/SOURCE/PROVENANCE）已按仓库惯例 dev-sync 刷新（未重建 bundle）。

## 5. Security Impact

- 关闭：actor 冒充漏洞（任意已认证用户可冒充管理员）、授权缺口（12+ RPC 无鉴权）、grant_access 无管理员校验、默认公开 secret、crypto 静默弱降级、auth 引导死锁、web 无认证/无批准门、simulated 假成功、外骨骼假事实、返工假成功。
- 新增控制：403/401 语义、AIPD_WEB_TOKEN、非 localhost 拒启、1MB 请求上限、幂等去重防重复副作用、fail-closed secret 策略、insecure_dev_mode 显式降级。
- 残余（本阶段未处理，见 §7）。

## 6. Tests（真实执行结果）

| 项 | 命令 | 结果 |
|---|---|---|
| 主套件 | `pytest tests/ -m "not model_eval" -q` | **597 passed, 0 failed, 2 skipped, 2 deselected**（161.64s） |
| 集成 | `pytest tests/ -m integration -q` | **15 passed, 2 skipped** |
| 新增测试 | CS1-CS14 新增 13 个测试文件 | 全部通过（详见各 CS 汇报：Authorization 13 / SecretPolicy 8 / Crypto+3 / Idempotency 13 / Scoping 8 / ManualHonesty 5 / CADContract 9 / VersionConsistency 5 / ImportCycles 2 / ExceptionHygiene 2 / SupervisorPackage 4 / GoldenIsolation 2 / Packaging 8） |
| ruff | `ruff check .` | **3090 errors**（基线 3298，-208；新增/修改代码零新增违规） |
| mypy | `mypy` | **138 errors**（基线 140，-2；checked 212 files） |
| schema | `python -m aipd_os.scripts.schema_check` | 全部通过 |
| audit_repo | `python scripts/audit_repo.py` | PASS（sbom/signing/dependency_lock=true） |
| capability | `python scripts/capability_matrix.py --out /tmp` | PASS（fully 35/partial 26/ext 9） |
| golden 隔离 | `git status --short releases/` | 0 改动（测试不再污染发布证据） |
| selftest | `python scripts/selftest_v4.py` | exit 0（"v4 supervisor selftest passed"） |

## 7. Known Limitations / Remaining Risks

1. **idempotency_key 全局去重**（CS4）：跨 project 同 key 也会 dedup——调用方须保证 key 全局唯一（已建议文档注明）。后续可加 (tenant,project,key) 复合去重。
2. **QUICKSTART 等文档历史节**保留历史版本描述（CHANGELOG 等），属有意保留。
3. **ruff/mypy 存量欠债**：全仓 3090 ruff / 138 mypy errors 为历史债务（typing 现代化 UP006/UP045 等为主），非 CI 门禁；本次仅保证新增/修改代码零新增。清理全仓欠债列为后续可选工程。
4. **BUNDLE_MANIFEST 残留**：现存 5.6.0 bundle 仍含旧 dist-info 痕迹（CS10 已修生成逻辑，重建 bundle 属发布动作，未执行）。
5. **Manual 状态**（P0-12）：.manual.json 仍为独立 JSON（已文档化，对象化迁移列入后续 Phase）。
6. **Supervisor 表无 tenant_id**（P1-2）：supervisor 工作项表仍单租户假设；统一状态 Ownership 收敛（含 decisions 表双 schema）列入后续架构收敛，本阶段未做大规模 DB 合并（符合"不一次性重写数据库"约束）。
7. **doctor 1 项环境级提示**：本机存在未登记敏感 env（CODEBUDDY_GATEWAY_* 等），属本机环境配置项。

## 8. Next Gate

**状态: PASS ✅**

- 主套件 0 failed（含全部新增回归测试）
- 集成、CAD golden loop、manual E2E、production release gate 全绿
- ruff/mypy 零新增违规；schema/audit/capability 全通过
- releases/ 零污染（golden 证据 pin 保持）

→ **允许进入下一阶段（Phase 2: Idea & Evidence Domain）**。
