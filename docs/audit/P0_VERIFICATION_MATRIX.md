# AIPD-OS Foundation Stabilization — P0/P1 逐项核实矩阵

**Date**: 2026-08-12 · **HEAD**: 2541be8 (v5.6.0)
**原则**: 以真实源码为最终事实来源；不因任务描述假定问题存在。判定：**CONFIRMED**（问题真实存在）/ **ALREADY RESOLVED**（代码已解决，附证据）/ **NOT REPRODUCED**（不存在）。
证据格式 `文件:行号`。全部结论经主理人第一手读码核实或架构师探勘交叉验证。

---

## P0 项

### P0-1 统一认证与授权边界 — **CONFIRMED（高危）**
- 授权缺口：`StateService` 大量 project-scoped RPC 无 `_authorize`：
  `list_projects`(server.py:107)、`get_project`(:111)、`list_facts`(:132)、`list_decisions`(:152)、`add_evidence`(:156)、`add_risk`(:167)、`add_deliverable`(:176)、`save_checkpoint`(:184)、`restore_checkpoint`(:190)、`object_put/get_b64/list/delete`(:204-218)、`create_backup`(:221)、`list_backups`(:227)、`restore_backup`(:230)、`retention_prune`(:233)、`audit`(:239)、`grant_access`(:89)。
- `grant_access` 无管理员/Owner 校验（server.py:89-90 → auth.py:89-90 直通 db）。
- MCP 通道（state_service/mcp_server.py）完全无认证（直接调用 StateService，actor=None 全跳过）。
- **实测发现的隐藏 bug**：`auth_register` 默认授予 `project_id=None` 行，`has_access`(db.py:335-341) 对该行既不匹配具体项目也不匹配 `'*'` → 注册用户实际无任何访问权；而受保护方法一旦生效，流程即断裂。
- 修复：Change Set 1（已下发实施，含通配规范化 + 全量授权 + 管理员门控 + 6 类隔离测试）。
- **QA 独立复核追加发现（严重）**：`server.py _inject_actor` 用 `params.setdefault("actor", actor)`，客户端显式传 actor 可覆盖认证身份 → 任意已认证用户可冒充任意用户/管理员（实测 alice 传 actor=admin 读审计 200）。修复：改为 `params["actor"] = actor` 强制覆盖 + 403 语义（AccessError → 403，401=未认证/403=无权限）。状态：CS1-FIX 已下发。**授权失败与参数错误统一 400 的问题同时修正为 403。**

### P0-2 authentication bootstrap — **CONFIRMED**
- HTTP RPC 层 `_RpcHandler._authenticate`(server.py:301-309) 无条件要求 user+token；`auth_login`/`auth_register` 也是 RPC → 经 HTTP 无法完成引导（「要登录必须先有 token」循环）。测试 test_server_local.py:83 只能绕过 HTTP 直接调用 `svc.auth_register` 佐证。
- 修复：Change Set 1 加 `PUBLIC_RPC_METHODS` 白名单，仅限 auth_login/auth_register。

### P0-3 audit 名称遮蔽 — **CONFIRMED**
- `self.audit = AuditLogger(...)`(server.py:48) 遮蔽方法 `def audit(self, limit=100)`(server.py:239)；`call("audit")` 经 `getattr` 取到 AuditLogger 实例而非方法 → RPC audit 实际不可用。
- 修复：Change Set 1 改名 `self._audit_logger`，保留 `audit()` 方法 + `list_audit_events` 别名。

### P0-4 取消默认生产 secret — **CONFIRMED**
- `AuthManager.__init__(secret="change-me-secret")`(auth.py:27)；`StateService.__init__(secret="change-me-secret")`(server.py:37)；CLI `--secret` 默认同值(server.py:346)；mcp_server.py 同(::33)。server 模式缺失显式 secret 时**不 fail closed**。
- 修复：Change Set 2（显式安全随机 secret 或 `AIPD_INSECURE_DEV_MODE=1` 显式降级 + WARNING；缺失 → 启动失败）。

### P0-5 crypto fallback — **CONFIRMED**
- `crypto.py:44-49`：cryptography 不可用时**静默**自动降级 XOR+HMAC，前缀 `x1:`；docstring(:5-7) 宣称「两种方案都保证加密/解密往返一致」——未区分生产/开发，XOR 并非 encryption-at-rest 等价物。
- 修复：Change Set 2（生产 fail closed；仅 `AIPD_INSECURE_DEV_MODE` 下允许回退并显式标注 not production safe；修正 docstring）。

### P0-6 Execution side-effect 幂等 — **CONFIRMED**
- `ExecutionRecord`(models.py:38-67) 与 `execution_runs` 表(runs.py:20-47) 无 `idempotency_key`/`side_effect_mode`/`remote_operation_id`。
- `ExecutionRouter.run` 重试循环(execution_router.py:112-134) 直接重复 `adapter.execute(input)`，对 mail/RFQ/supplier 等有副作用操作无去重保护；`_finalize_success`(:161-193) 无条件 succeeded。
- 修复：Change Set 4（`side_effect_mode` PURE/IDEMPOTENT/EXTERNAL_SIDE_EFFECT/NON_RETRYABLE + `idempotency_key` 落库 + router 去重 + 模拟测试）。

### P0-7 Research honesty — **CONFIRMED（高危）**
- `research_adapter.py:41-66`：配置 `AIPD_RESEARCH_API_KEY` 后**仍不调用真实 API**，返回 `Simulated source`+`example.invalid` URL+`simulated=True` 且不抛错 → `ExecutionRouter._finalize_success` 无条件标 `succeeded`(execution_router.py:115-117,161-193)；`persist_evidence` 把 example.invalid 写为证据引用(research_adapter.py:76-84)；Supervisor 注册 capability available + complete(aipd_supervisor.py:227-232)，quality gate 不过滤(147-159)。
- 同模式：`imggen_adapter.py:53`、`cad_adapter.py:53`（结果内标注 simulated，但 run 状态仍为 succeeded）。
- 对照：`src/aipd_os/research/` 包自身诚实（retrieval.py:84-93 无凭据返回 not_verified；writeback.py:58,100-114 仅 verified 写事实）→ 风险集中在 tool_adapters 层与 router 无感知。
- 修复：Change Set 5（真实 Semantic Scholar API 调用；失败 → external_blocked；router 对 simulated 结果强制降级；imggen/cad adapter 同步处理）。

### P0-8 Product Truth project scope — **CONFIRMED**
- `product_truth`/`truth_lineage`/`rework_tasks` 三张表(store.py:19-52) **均无 tenant_id/project_id 列**；查询(add/store.py:126-160、lineage 全表、rework)均无项目过滤；`find_id_by_type_and_content`(:134-140) 全表去重。
- 修复：Change Set 6（按 runs.py `_ensure_columns` 模式加列 + 全 API 线程项目上下文 + 迁移测试）。

### P0-9 ProductTruth metadata 持久化 — **CONFIRMED**
- `TruthRecord.metadata`(models.py:95) 存在且 `to_dict` 输出(:129)，但 store `add()` INSERT(:104-111) 不含 metadata、`_row_to_record`(:59-73) 不恢复、schema 无 metadata 列 → model↔persistence↔serialization 契约断裂。
- 修复：Change Set 6（metadata_json 列 + round-trip 测试）。

### P0-10 禁止默认 rework 假成功 — **CONFIRMED**
- `PropagationEngine._default_rework`(propagation.py:193-194) 恒 `return True`；`run_rework`(132-191) 未传 `rework_fn` 时即 bump 版本 + 标 succeeded——没有真实执行却报告成功。现有测试均显式传 `_ok`/`_failing`，不依赖默认行为。
- 修复：Change Set 6（无 executor → 立即 blocked + 明确原因，绝不假成功）。

### P0-11 Manual demo truth 隔离 — **CONFIRMED**
- `scripts/manual_chain.py _build_defn`(:140-220) 在 facts 缺失时回退到**外骨骼硬编码事实**：产品名「外骨骼助力系统」(:158)、CMF「金属灰/工程橙/铝合金6061/阳极氧化」(:164,198-201)、工作原理/模块/场景(:175-194)、**伪造性能曲线数据点**(:206-207)、QA(:210-212)、结语(:215-217)。这些是「看起来合理」的产品事实而非 TBD。
- 修复：Change Set 7（facts 缺失 → 显式 TBD/UNKNOWN；真实数据仅存于 tests/fixtures/golden_projects；曲线无数据 → 不生成）。

### P0-12 Manual state 统一 — **CONFIRMED（结构性问题，Phase 1 部分处理）**
- Manual 状态为独立 `.manual.json`（manual_chain.py 全程 JSON 读写），与主 State 的 backup/restore/checkpoint/audit 无统一覆盖；仅 UnifiedStateService 的 attachment 索引部分桥接（recovery.py register_object）。
- 处理：Change Set 8（文档化 + 将 manual.json 纳入统一备份清单；长期对象化迁移列入 Phase 1 架构收敛）。

### P0-13 Web owner approval 安全 — **CONFIRMED**
- `WebConsole.start_run`(views.py:532-541) 硬编码 `approved=True` 调 `run_operation_loop`(operations.py:239,264) → 绕过 DecisionPolicy 的 requires_approval 门。
- web/server.py：默认 127.0.0.1(:177)，但 `serve` 可绑定任意 host，**无认证/CSRF/请求体大小限制**。
- 修复：Change Set 8（start_run 不再自授 approved；决策走 decision center 显式批准；非 localhost 无 token 拒绝启动 `AIPD_WEB_TOKEN`；请求大小限制；文档标注 localhost dev console 语义）。

### P0-14 CAD deterministic artifact — **部分解决 / 补强**
- 字节确定性已工程化：STEP 导出归一化时间戳(backends.py:409-411)，golden loop 断言同参数哈希稳定(test_cad_golden_loop.py:152-179)。
- 缺口：产物证据仅字节 sha256(evidence.py:10-21)，无独立 `semantic_geometry_hash`；几何测量塞在 `rec['extra']`(:415)。
- 处理：Change Set 9（`semantic_geometry_hash` 字段 + 文档说明 byte hash ≠ semantic identity）。

### P0-15 CAD 参数契约一致 — **CONFIRMED（架构师发现，已亲自复核）**
- `GOLDEN_PARAM_SPEC` fillet_radius/chamfer `min=0.0`(backends.py:182-183)，`edit_parameter` 允许 0(:353-355)，但 `geometry_validity_check` 要求**所有**参数 `v>0`(:430-433) → `fillet_radius=0.0` 契约合法却被几何校验拒绝。
- 三套手写校验漂移：`GOLDEN_PARAM_SPEC`+`edit_parameter`；`geometry_validity_check`（重复 min+正值+hole_diameter<板面）；`ContractBackend.DEFAULT_PARAMETERS`(461-463) 缺 fillet/chamfer/hole_count + 独立校验(544-555)。
- 修复：Change Set 9（统一单源参数校验函数，geometry 校验与 edit 校验共用；fillet/chamfer=0 合法）。

### P0-16 版本 Single Source of Truth — **CONFIRMED（漂移比初查更广，产品经理报告补充）**
- 权威版本 5.6.0：pyproject.toml:7、src/aipd_os/__init__.py:12、state/__init__.py:26、四清单（PROVENANCE/SOURCE/RELEASE/BUNDLE）头部。
- 漂移点：README.md:1 `v5.5.0`；QUICKSTART.md:3 `v5.3`、:105,108 `5.5.0`；SECURITY.md:11 支持表仍写 5.0.x、:77 `截至 v5.5.0`；THREAT_MODEL.md:3 与 docs/architecture.md:1 仍 v5.0；src/aipd_os/cli/main.py:21,320 打印 v5.5。
- 版本常量 ≥5 处手工维护（pyproject / 包 __init__ / state __init__ / CLI 打印 / test_packaging 硬断言），无跨文件一致性测试（test_packaging.py:39-41 只校验包内 __version__，抓不到文档漂移）。
- **发布卫生发现**：BUNDLE_MANIFEST.json:1195,1610-1660 打包进了 `.venv-ci` 的 `aipd_os-5.5.0.dist-info` 残留（发布物含旧版痕迹）→ 列入 CS10 修复（bundle 生成排除 venv 残留）或已知问题清单。
- 修复：Change Set 10（README/QUICKSTART/SECURITY/THREAT_MODEL/architecture/SKILL/cli 对齐 5.6.0 + 跨文件版本一致性测试 + bundle 残留清理）。

## P1 项

### P1-1 Supervisor 正式 package 化 — **CONFIRMED（高危，P0 后处理）**
- 核心 Supervisor 仍为 scripts/aipd_supervisor.py:54（274 行单文件）；src 无 supervisor 包；cli/commands.py 5 处动态反向加载 scripts(118,164,455,541,570)；registry.py:252-258 probe 临时注入 scripts sys.path。
- 处理：Phase 1 架构收敛（迁移至 src/aipd_os/supervisor/，scripts 留兼容 wrapper，保持 CLI 兼容）。

### P1-2 统一状态 Ownership — **CONFIRMED（架构债务）**
- 事实状态碎片：AIPDStateDB / Supervisor 表 / ProductTruthStore / ClosureStore / RunStore / Manual JSON / ObjectStore 并存（见 REPOSITORY_MAPS.md D 节）；`decisions` 表在 state/db.py 与 aipd_supervisor.py:46-50 存在**同表名双 schema** 冲突；Supervisor 表无 tenant_id。
- 处理：Phase 1 架构收敛（先定义 Project State Architecture 文档，再逐步收敛，不一次性重写）。

### P1-3 统一 Truth Architecture — **大部分 ALREADY RESOLVED**
- epistemic 状态已存在：`FACT_STATUSES = {V,S,C,E,A,P,T,R}`(db.py:30)（注释见 FACT_STATUSES 语义：V=verified/S=simulation/C=calculation/E=external/A=assumption/P=pending third party/T=pending test/R=retired，与要求一致）。
- lifecycle 状态已存在：`TRUTH_STATUS = {active,stale,expired,blocked,superseded}`(product_truth/models.py:23)；confidence 已存在(db.py:86 facts.confidence)。
- 差距：需要文档化「epistemic ≠ lifecycle」「UNKNOWN 不是 stale」的映射语义（Change Set 10 文档）。

### P1-4 Registry 命名收敛 — **大部分 ALREADY RESOLVED**
- `CapabilityRegistry`(registry.py:88) 存在且带运行时诚实 probe；`AdapterRegistry`(execution/registry.py:10) 存在；`ProviderRegistry` 不存在（providers/ 为 SDK 包）。
- 处理：文档化三级职责（CapabilityCatalog=声明 / AdapterRegistry=实现 / ProviderRegistry=后端），不制造 breaking change（Change Set 10 文档）。

### P1-5 import cycle — **NOT REPRODUCED（现状无环）**
- state 包内相对子模块导入、无环（health.py:10、server.py:21-28）；包内无 `from aipd_os.state import`（0 命中）。re-export 偏重（research/__init__ ~30 名、state/__init__ 38 名）但未成环。
- 处理：新增 import-cycle 静态检查测试 + 内部代码风格指引（Change Set 10）。

### P1-6 异常处理 — **部分 CONFIRMED**
- 存在 `except Exception: pass`/吞异常路径：aipd_supervisor.py:144-145（`except Exception: pass`）、:157-158（review 失败吞掉）、recovery.py:222-223/263-264（sqlite 错误吞掉）、run_work_items(execution_router.py:302-303)（catch→continue 但如实记录 ok=False）。
- 处理：Change Set 11（按外部边界/内部逻辑分类处置，禁止 `except: pass` 静默成功）。

---

## 风险汇总

| 级别 | 项 |
|---|---|
| 高危 | P0-1、P0-7、P1-1 |
| 中-高 | P0-15 |
| 中 | P0-2、P0-3、P0-4、P0-5、P0-6、P0-8、P0-9、P0-10、P0-11、P0-13、P0-16、P1-2、P1-6 |
| 低 | P0-12、P0-14、P1-3（文档）、P1-4（文档）、P1-5（测试） |
| 已解决 | P1-3（主体）、P1-4（主体） |
