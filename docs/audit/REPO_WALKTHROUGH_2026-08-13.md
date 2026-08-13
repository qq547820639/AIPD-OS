# AIPD-OS 仓库系统性走读报告（2026-08-13）

生成日期：2026-08-13
基线 HEAD：`744960c`（v5.9.2 V5_9_2_GATE PASS + release evidence）
范围：163 个源文件 / 36,064 行 / 26 子包 / 124 测试文件 / 49 脚本
性质：纯走读，未修改任何源码

---

## 1. 执行摘要

AIPD-OS 是"AI 产品工程决策操作系统"：以 **Idea（理论层）→ Supervisor（编排层）→
ExecutionRouter（执行层）→ Adapter/Provider（能力层）** 四层主线为核心，辅以
**State（数据底座）**、**Product Intelligence + Product Truth（产品定义闭环）**
两条正交纵深。整体架构分层纪律良好：state 无上层依赖、product_truth 不依赖
product_intelligence、execution 不反向依赖 idea，无环依赖。

本次走读新发现（非历史审计已覆盖项）：
- **Q-1** `registry.py:310` 导出表名写错：`_all__`（应为 `__all__`）——
  `from aipd_os.registry import *` 实际失效，是静默的公开 API 缺陷。
- **Q-2** `logging_utils.setup_logging` 的 if/else 两个分支重复同一段
  handler 装配代码（约 15 行重复），且 `_configured_loggers` 的"已配置"判定
  与 `get_logger` 的惰性初始化存在状态错位风险。
- **Q-3** `idea/research_provider.py` 直接 import `execution`（ToolAdapter /
  ExecutionRouter）：idea 域（数据模型层）反向依赖执行层，形成
  idea→execution 层次泄漏（虽无环，但 idea 的单元测试因此耦合执行装配）。
- **Q-4** 大文件集中：11 个文件 >600 行（commands.py 1561 最大），
  其中 product_intelligence 四件套（gate 979 / snapshot 610 / service 626 /
  models 593）合计 2808 行，处于拆分解耦的临界点。

---

## 2. 顶层目录职责

| 路径 | 职责 |
|---|---|
| `src/aipd_os/` | 主包（26 子包，见 §3） |
| `tests/` | 124 个测试文件（pytest；`-m "not model_eval"` 为 CI 默认口径） |
| `scripts/` | 49 个工具脚本：审计（audit_repo / capability_matrix / selftest_*）、发布（release_evidence / sign_release / regenerate_release_manifest / production_release_gate）、CAD 门禁（cad_*_gate / faceted_step）、验收（e2e_acceptance / outcome_acceptance） |
| `docs/` | architecture（分层文档）、audit（各阶段审计矩阵与收口报告）、security |
| `releases/` | 发布 zip + 5.6.0 目录（RELEASE_MANIFEST） |
| `build/` | 构建中间物（bundle_stage / release） |
| `assets/` | schemas / templates / golden_samples（声明式数据，不参与运行） |
| `evals/`、`evals_out/` | 模型评估输入与产物 |
| `state_service/`、`migrations/`、`templates/`、`data/` | 服务/迁移/模板/运行时数据目录 |
| 根级 evidence | SOURCE/BUNDLE/PROVENANCE/RELEASE_MANIFEST（tag 锚点发布证据四件套） |

**核心入口**：
- CLI：`pyproject.toml` → `aipd = aipd_os.cli.main:main`
- 运行时装配：`runtime.py` 的 `build_runtime()` / `get_runtime()`（唯一 bootstrap 契约）
- Web：`web/server.py`（状态服务）与 `web/views.py` 的 `WebConsole`（Owner 控制台）

---

## 3. 26 子包职责矩阵

| 子包 | 文件数 | 职责 | 关键类/函数 |
|---|---|---|---|
| state | 14 | SQLite 数据底座：多租户、事务、审计、迁移、备份/恢复、血缘、加密 | AIPDStateDB、transaction()（线程本地 + SAVEPOINT 嵌套）、MIGRATIONS v1-v12 |
| idea | 13 | Idea 理论层：Claim/Evidence/评估/成熟度/分解 | IdeaService、ClaimService、EvidenceGraph、IdeaDecomposer、IdeaMaturity |
| supervisor | 3 | 编排层：work item + 显式依赖 DAG + 生命周期 | Supervisor（next_work/complete/fail/run_supervisor）、schedule_*（idea_capabilities） |
| execution | 10 | 执行层：Adapter 契约、路由、闭环、运行记录、决策策略 | ToolAdapter(ABC)、AdapterRegistry、ExecutionRouter、RunStore、closure |
| product_intelligence | 8 | 产品定义：候选对象→closed-world snapshot→Gate→原子 commit | ProductIntelligenceService、ProductDefinitionSnapshotService、ProductDefinitionSnapshotView、ProductDefinitionGate、ImpactPropagationService |
| product_truth | 5 | 真值层：ProductTruth 存储、canonical lineage、传播 | ProductTruthStore、LineageGraph、propagation |
| tool_adapters | 15 | 能力适配器：research/doc/imggen/layout/cad/brep/faceted/mail-rfq/supplier/idea/product | builtin.build_registry() 注册 11 类 adapter |
| providers | 3 | Provider SDK：注册表 + 示例插件 | ProviderRegistry |
| research | 11 | 学术检索：arxiv/crossref/semanticscholar + ResearchStudio 生产接入 | register_researchstudio |
| mail | 3 | 邮件协议客户端（IMAP/SMTP 轮询） | client.py（705 行） |
| imggen | 6 | 图像生成（credential-gated） | — |
| supply_chain | 10 | 供应链 RFQ/供应商 | — |
| cad | 6 | CAD 内核契约：CadQuery 真实内核 C2 / ContractBackend 降级 C1 | backends.get_default_backend() |
| web | 4 | Owner Web 控制台（inline 渲染，React 仅镜像） | WebConsole、RunController |
| cli | 4 | 命令行：commands(1561) + product_commands + main | 30+ cmd_* 函数 |
| experience | 14 | 跨会话体验（历史审计重点域之一） | — |
| layout | 4 | 版式生成 | — |
| visual_audit | 4 | 视觉审计/诚实护栏 | — |
| telemetry | 3 | 遥测 | — |
| security | 5 | 密钥策略、脱敏、授权 | mask_secret_deep、secret_policy |
| evals_runner | 8 | 模型评估运行器 | — |
| evals | 2 | 评估数据 | — |
| scripts | 2 | 包内脚本子包 | — |

---

## 4. 数据流主线（真实链路，全部由测试锁定）

```
Idea (raw, I0)
  → IdeaDecomposer (idea.structure, I1)        [idea/]
  → Supervisor.add_work (显式 depends DAG)     [supervisor/]
  → next_work (领取→依赖→能力地板→选择)
  → ExecutionRouter.run (validate→execute→artifacts→evidence→quality gate)  [execution/]
  → ToolAdapter.execute (capability)           [tool_adapters/]
  → Provider (诚实四态: AVAILABLE/UNAVAILABLE/EXTERNAL_DEPENDENCY/PARTIAL)   [providers/]
  → 产物落 State (facts/evidence/decisions)    [state/]

产品定义支线（v5.9.x）:
  Insights → Opportunity(显式 selection) → Principles → Requirements → Features
  → create_snapshot (closed-world active set + upstream_basis_hash)
  → Gate (SnapshotView 只读 frozen；freshness 用 live)
  → Owner Decision (approve/approve_with_waiver/reject)
  → commit_snapshot (单事务原子 exactly-once; ledger UNIQUE)
  → ProductTruth + canonical lineage
  ↑ 上游 claim 变化 → ImpactPropagationService → frozen snapshot STALE
```

**事务模型**（state/db.py）：
- `connect()` 线程本地（`_db_tls.tx_conn`）复用活动连接——事务内所有 helper
  语句落在同一连接，修复历史 SQLite 写锁自死锁；
- `transaction()` 顶层 BEGIN/COMMIT/ROLLBACK + 嵌套 SAVEPOINT；helper 不得
  在事务内偷偷 commit。

**Runtime 契约**（runtime.py）：`build_runtime(make_default=...)` 是唯一装配入口；
CLI/Web/MCP 全程同一 runtime；probe 四态"注册 ≠ 可用"，不伪造成功。

---

## 5. 依赖方向图（本次实测）

```
                    ┌──────────────┐
                    │  cli / web   │  (传输层)
                    └──────┬───────┘
                           ↓
              ┌────────────┴───────────────┐
              ↓                            ↓
   ┌──────────────────┐          ┌─────────────────────┐
   │    supervisor    │ ←────── │  product_intelligence│
   └────────┬─────────┘   (调度)└──────────┬──────────┘
            ↓                              ↓
   ┌──────────────────┐          ┌─────────────────────┐
   │    execution     │          │   product_truth      │
   └───┬─────────┬────┘          └──────────┬──────────┘
       ↓         ↓                          ↓
   tool_adapters providers           state（数据底座，被一切依赖）
       ↑
   idea ──────→ execution  (Q-3 层次泄漏；execution 不反向依赖 idea，无环)
```

验证结论：
- `state → idea/supervisor/product_*`：0 条（底座干净）
- `idea → supervisor`：0 条；`execution → idea`：0 条（无环）
- `product_truth → product_intelligence`：0 条（正交干净）
- 唯一层次泄漏：`idea/research_provider.py → execution`（Q-3）

跨包 import 频次 Top：execution(38) > state(29) > tool_adapters(22) >
supply_chain(17) > evals_runner(13)——execution 是被依赖最多的模块，
是事实上的"内核"。

---

## 6. 质量发现清单（分文件可执行）

### P0（应尽快处理）

| ID | 位置 | 问题 | 建议 |
|---|---|---|---|
| Q-1 | `src/aipd_os/registry.py:310` | `_all__ = [...]` 应为 `__all__`，导致 `import *` 静默失效，公开 API 约定被破坏 | 改名为 `__all__`；加一条 `assert aipd_os.registry.__all__` 的测试 |
| Q-2 | `src/aipd_os/logging_utils.py:63-87` | `setup_logging` if/else 双分支重复装配同一段 handler 代码；`_configured_loggers` 全局 set 与 logger 实例状态可能错位（多 logger 名并发配置时） | 抽公共 `_attach_handlers(logger, log_file)`；`_configured_loggers` 改为按 name 存字典 |

### P1（应排期）

| ID | 位置 | 问题 | 建议 |
|---|---|---|---|
| Q-3 | `src/aipd_os/idea/research_provider.py:38-39` | idea 域 import execution（ToolAdapter/ExecutionRouter），数据模型层反向依赖执行层；测试时 idea 单测被迫装配执行层 | 将 idea 需要的执行语义下沉为 Protocol（typing.Protocol），或把 `ResearchIntegration` 拆到 `idea/` 之外 |
| Q-4 | `src/aipd_os/cli/commands.py`（1561 行） | 30+ cmd_* 函数 + 内部 helper 混居；此前审计记录"19=19 持平"仅控制不增长，未解决存量 | 按域拆 `commands_cad.py` / `commands_manual.py`（各约 300-400 行），commands.py 保留 intake/status/decide 核心 |
| Q-5 | product_intelligence 四件套（gate 979 + snapshot 610 + service 626 + models 593 = 2808 行） | 单域行数过高，gate.py 同时承载 criteria 定义、评估、授权、eligibility、commit 事务五职责 | gate.py 拆 `criteria.py`（静态 criteria 定义）+ `authorization.py`（owner 决策）；models.py 的 5 域对象模型已单一，保留 |

### P2（记录在案）

- **except Exception × 82**：多数带 `noqa: BLE001` 注释（probe/审计落库失败不中断的刻意设计）；建议区分"诚实降级"（保留）与"真正吞错"（改为 except Exception as exc + logger.warning 至少记录）。
- **测试覆盖盲区**：`web`（无 test_web* 前缀文件，靠 test_owner_web_console 间接覆盖）、`visual_audit`（仅 test_visual_* 2 文件）、`providers/sdk`（无直接测试）、`supply_chain`（10 文件仅 1 测试）。supply_chain 与 providers 值得各补 1 个契约级测试。
- **`_configured_loggers` 单例耦合**：测试间日志 handler 状态共享（本次走读曾观察到 intake 测试单独跑 vs 全量跑行为差异，根因即此）。
- **registry_data.py 77 项能力、7 领域**：声明式数据与 registry.py probe 逻辑分离良好；但 `_expand_braces` 手写 brace 展开器（registry.py:151-169）可用标准库替代（`itertools.product` 组合），降低自研复杂度。

---

## 7. 与历史审计的关系

本报告只覆盖"跨模块结构"层面，与既有矩阵不重复：
- V5_8_2（Architecture & Truth Closure）→ idea 域深度审计；
- V5_9_1（Product Definition Integrity & Runtime Closure）→ PI 对象事务化；
- V5_9_2（Snapshot-Closed Runtime & Commit Integrity）→ snapshot/commit 收口；
- **本报告** → 首次全仓库分层走读 + 依赖方向实测 + 分文件质量清单（Q-1..Q-5）。

## 8. 结论

架构分层纪律整体良好（无环依赖、底座无泄漏、真值层正交），主要改进空间集中在
**公开 API 卫生（Q-1/Q-2）**与**大文件拆分（Q-4/Q-5）**两处，均为低风险、
可分批落地项。建议按 P0 → P1 → P2 顺序小批量提交，每批附测试锁定。
