# AIPD-OS 深度实现审查报告（第二轮走读，2026-08-13）

生成日期：2026-08-13
基线 HEAD：`744960c`（v5.9.2 V5_9_2_GATE PASS + release evidence）
性质：纯走读，未修改任何源码（唯一写操作即本报告）
定位：在昨日 `REPO_WALKTHROUGH_2026-08-13.md`（结构全景 + Q-1~Q-5）之上的**实现深度与完成度审查**，不重复 Q-1~Q-5 的罗列（仅以编号引用）。

---

## 1. 执行摘要

AIPD-OS 的**确定性工程闭环已全部实现并被测试锁定**（958 passed / 0 failed / 3 skipped）：
State 数据底座、Supervisor 编排、ExecutionRouter、Product Intelligence 的 snapshot/gate/commit
/ImpactPropagation、Product Truth、CAD 双后端、security、WebConsole、CLI —— 均为真实实现而非骨架。

**但用户核心问题「代码是否已全部实现」的答案是：否，且有一个明确的分水岭——**

> **「确定性/可追溯」的骨架 100% 实装；「AI 智能推理」的生产接线 0% 接入。**

所有需要真实 LLM 的能力在生产中均为「契约 + 诚实 external_dependency」占位，无一条生产 Provider 已接线：
- `idea.decompose`（一句话想法 → 结构化 Idea + Claims，I0→I1）：`build_runtime` 里 `ProviderRegistry()` 为空，生产无真实 LLM decomposer → `CAPABILITY_UNAVAILABLE`。
- `product.derive_insights / identify_opportunity / derive_principles / derive_requirements / derive_features`：`runtime.py:281` 硬编码 `provider=None` → `EXTERNAL_DEPENDENCY`。
- `evidence.assess_relation`、`research.fulltext / related_work / novelty_check / idea_spark / asset_extract`：只定义契约，**未注册任何 adapter** → probe 恒 `UNAVAILABLE`。
- 全仓唯一的真实 LLM HTTP 客户端在 `evals/runner.py` 与 `evals_runner/completion.py`（读 `AIPD_MODEL_API_KEY`），仅用于**模型评估**，不驱动产品链路。
- 唯一真实接线的外部能力是 `research.academic_search`（ResearchStudio：arxiv/OpenAlex/SemanticScholar 多引擎 HTTP 聚合，`research/providers/researchstudio.py`）。

此外，**v5.10 NPI 计划（制造就绪）所列接口全部 NOT_STARTED**：BOM 表、Cost 表、ValidationTest 表、
Issue 独立表、MMDProjection 实现、Manufacturing Readiness 与 Product Truth/NPI Gate 打通 —— 在
`docs/audit/V5_9_1_PRODUCT_DEFINITION_RUNTIME_CLOSURE.md` §14 中明确列为「v5.10 动作」，当前仓库内不存在。

结论：**这是「基础设施与诚实降级框架完备、智能推理接线与制造就绪两段未动工」的状态。** 对"不会写代码的产品负责人"而言，`aipd onboard → run` 会真实跑起来并停在一个诚实提示上（"需要配置真实 Provider / 外部依赖"），不会假成功——这正是设计目标；但也意味着"全程 AI 推进"目前在默认安装下只能推进到确定性可算的部分。

---

## 2. 顶层与配置走读要点（第 1 步）

### 2.1 包与依赖（pyproject.toml）
- 运行时依赖**极简**：`dependencies = ["jsonschema>=4.0"]`（line 27-29）—— 印证"不捆绑 LLM SDK"的现状。
- 可选依赖分层：`server`（cryptography）、`cad`（cadquery>=2.4）、`server-mcp`（mcp>=1.0，单独 extra 因需 Python≥3.10）、`full`、`dev`（line 31-56）。
- `requires-python = ">=3.9,<3.13"`（line 13），与 CI python-core-matrix（3.9-3.12）一致，3.13+ 不宣称。
- entry point 唯一：`aipd = aipd_os.cli.main:main`（line 59）。
- ruff select `E,F,I,W,UP,B,SIM` / mypy `warn_return_any + ignore_missing_imports`（line 75-89）—— 配置完整但历史上存在未清零的 mypy 债务（v5.9.2 报告 §7 自述"11 个错误全在历史文件"）。

### 2.2 部署与安全
- `Dockerfile`：默认 `server` 模式（`state.server:main`），端口 8000，HEALTHCHECK `/health`；`INSTALL_CAD=1` 才装真实内核。
- `docker-compose.yml`：`AIPD_ENCRYPTION_KEY` / `AIPD_SECRET` 均要求显式提供，缺失 fail-closed。
- `SECURITY.md` / `THREAT_MODEL.md`：T1 提示注入、T2 敏感数据、T3 跨租户、T4 篡改、T5 DoS、T6 发布物 —— 六类威胁均有对应源码模块与测试，与实现一一对应（无"文档写了代码没有"的悬空）。

### 2.3 migrations / scripts / build / assets
- `migrations/` 下只有 `v4_to_v5.py` + `rollback_v5.py`（历史脚本）；**真实迁移权威在 `state/migrations.py`（v1-v12）**，二者并存但不冲突（历史脚本不再被调用）。
- `scripts/` 49 个，职责四类：审计（audit_repo/capability_matrix/selftest_*）、发布（release_evidence/sign_release/regenerate_release_manifest/production_release_gate）、CAD 门禁（cad_*_gate/faceted_step）、验收（e2e_acceptance/outcome_acceptance）—— 与 v5.9.2 的 P0 验证脚本 `_v592_p004_check.py` / `_v592_p009_check.py` 并存。
- `assets/`：schemas（fact/cad_contract/supervisor_project/manual_chain_state 等 JSON Schema）、templates（work_package/decision_package/design_intent_package 等）、golden_samples/golden-references（视觉审计黄金样本）、examples —— 声明式数据，不参与运行。

### 2.4 26 子包实际结构核实
与昨日矩阵一致（此处只补充昨日遗漏）：`research/` 实际有 **11 个文件**（昨日 `ls *.py` 未算 `research/providers/` 子目录的 `__init__.py` + `researchstudio.py`）。`registry_data.py` 为 88 行 / 47KB（超长行），含 **77 项能力 / 7 领域**（70 项自动生成用双引号 + 7 项 product.* 手写块用单引号，见 §6 N-2）。

---

## 3. 核心链路实现深度审查（第 2 步）——「骨架 vs 实装」逐层判定

### 3.1 state/（数据底座）→ **FULLY_IMPLEMENTED**
- `AIPDStateDB`（`state/db.py`，1148 行）生产级：多租户多项目、乐观锁（`_update` WHERE version_no）、`SENSITIVE_KEYS` 透明加密（`_store_value`/`_read_value`）、evidence 按 doi/arxiv_id/identifier/url/title+year 去重（`get_or_create_evidence`）、`id_sequences` 原子 ID 分配。
- `transaction()`（db.py:378-425）：顶层 BEGIN/COMMIT/ROLLBACK + 嵌套 SAVEPOINT + thread-local 连接复用；`connect()` 在事务内复用活动连接不 commit（db.py:356-375）。这是 v5.9.1 原子性的根因修复，实测质量高。
- 迁移 `state/migrations.py`：V1 冻结 SQL 文本 + `V1_FROZEN_SHA256` 漂移校验（line 214），v1-v12 均带幂等 up/down；v9 重建表处理 NULLABLE、v11/v12 增列/建表/账本。质量显著高于常见"手写 DDL 不迁移"的实现。

### 3.2 idea/（理论层）→ **数据模型 FULLY_IMPLEMENTED，智能分解 NOT_WIRED**
- `IdeaService/ClaimService/EvidenceRelationService/EvidenceGraph`：tenant+project scoped、audited、versioned，CRUD 完整（`service.py` 153 行、`claim_service.py`、`evidence_graph.py` 12577B）。
- `IdeaDecomposer`（`decomposer.py` 383 行）：schema validation → normalize → persist → audit，`decompose_existing` 保持 Idea 身份连续（I0→I1）。**编排完整，但 `decompose_and_persist`/`decompose_existing` 在 `provider is None or not available()` 时诚实抛 `IdeaDecompositionUnavailable`（decomposer.py:293-295 / 331-334）。**
- `UnavailableProvider`（decomposer.py:159-171）`available()=False`：这是**诚实降级占位，非骨架**——但生产没有给它对应的真实实现。
- `IdeaMaturity`/`IdeaTruthProjection`/`IdeaTruthSnapshot`：完整（`maturity.py`、`projections.py` 111 行），昨日 `__init__.py` docstring 里的"projections 骨架（Commit 14 填充）"已过时——projections 已实装（doc 漂移，见 §6 N-5）。
- **层次泄漏 Q-3 确认**：`idea/research_provider.py:38-39` `from aipd_os.execution.adapter import ToolAdapter, external_blocked_error` + `from aipd_os.execution.execution_router import ExecutionRouter`（idea→execution 反向依赖）。

### 3.3 supervisor/（编排层）→ **FULLY_IMPLEMENTED**
- `Supervisor`（`supervisor/supervisor.py` 711 行）：work item 全生命周期（queued/ready/running/blocked_external/blocked_decision/internal_rework/complete/cancelled）、显式 `depends_on_json` DAG（`_deps_complete`）、`owner_required` 决策暂停、`next_work` 领取优先级、`run_supervisor` 固定顺序（领取→依赖→能力地板→执行→校验→注册工件→独立质量门→mark_stale→推进/返工→决策暂停）。
- fail-closed 真实：`blocked_external` 用 `external=True, retry=False`（supervisor.py:592-595）；无 adapter → `internal_rework`（552-565）；异常 → `internal_rework`（614-622）。
- 独立质量门 `_quality_gate`（453-469）以独立审计身份复核 `evidence_references`/`output_hash`。

### 3.4 execution/（执行层）→ **FULLY_IMPLEMENTED（契约 + 路由 + 诚实降级）**
- `ToolAdapter` 契约（`execution/adapter.py` 181 行）完整：discover/validate_input/execute/normalize/collect_artifacts/persist_evidence/classify_failure/retry_limits/fallback_chain/side_effect_mode。
- `external_blocked_error` + `write_external_task`（adapter.py:35-97）：外部能力不可用时写出"外部任务包" JSON 并 `external_blocked`，绝不伪造成功。
- `execution_router.py`（15KB）：`_has_simulated_marker`（199-212）防御纵深——adapter 返回 `{"status":"simulated"}` 占位时拒绝标记 succeeded（236-246）。这是全仓"诚实性"最硬的一道闸。
- `closure.py`/`closure_core.py`/`runs.py`/`models.py`：运行记录、证据引用、输出哈希、失败分类。

### 3.5 product_intelligence/ + product_truth/ → **确定性部分 FULLY_IMPLEMENTED，生成部分 NOT_WIRED**
- `gate.py`（979 行）：technical（READY/CONDITIONAL/BLOCKED）+ authorization + eligibility 三层分离；`commit_snapshot` 单事务原子 exactly-once（`product_definition_commits` ledger UNIQUE）。
- `snapshot.py`（610 行）：closed-world `active_definition_set` + `is_stale` set equality + `ProductDefinitionSnapshotView`（只读 frozen）。
- `impact.py`（新，`ImpactPropagationService`）：claim→insight→opportunity→principle→requirement→feature 反向 Digital Thread + snapshot stale 幂等。
- `product_truth/`：`store.py`/`lineage.py`/`propagation.py` 事务感知（`add(record, conn=…)`），canonical lineage + retire。
- **但 `product.derive_*` 五类 + `identify_opportunity` 的 provider 在生产为 None**：`runtime.py:281` `register_product_adapters(ctx.adapters, ctx.db, provider=None)`；`product_adapters.py:8-9` 明言"provider 未配置 → discover().available=False → EXTERNAL_DEPENDENCY"。只有 `product.create_snapshot` 与 `product.definition_gate` 是本地 deterministic（AVAILABLE）。

### 3.6 tool_adapters/ + providers/ + research/ → 真实 vs 降级 vs 未注册
| 能力 | 状态 | 证据 |
|---|---|---|
| research.academic_search | **REAL**（真实 HTTP 多引擎） | `research/providers/researchstudio.py`：ArxivEngine/OpenAlexEngine/SemanticScholarEngine + 去重聚合；`available()=True`（line 264-265） |
| CAD 参数化内核 | **REAL（可选）** / 诚实降级 C1 | `cad/backends.py`：`CadQueryBackend` C2（需 cadquery）、`ContractBackend` C1 faceted（line 337/538） |
| imggen / cad_adapter(text-to-cad) / mail_rfq / supplier | **external_blocked + simulated 标注** | `imggen_adapter.py:48-53`、`cad_adapter.py:53` 均 `"status":"simulated"` 诚实标注；`mail_rfq_adapter.py:39` 无凭据抛 external_blocked |
| research.fulltext/related_work/novelty_check/idea_spark/asset_extract | **未注册** | 只有 academic_search 经 register_researchstudio 注册；其余五类无 adapter 注册入口 → probe `UNAVAILABLE` |
| evidence.assess_relation | **未注册** | `ResearchProvider.assess_relation` 默认抛 `ResearchCapabilityUnavailable`（`idea/research_provider.py:91-102`） |
| idea.decompose | **未接线** | `runtime.py:240` `providers = ProviderRegistry()` 为空；`_register_external_providers` 不向 `ctx.providers` 注册任何 decomposer |

### 3.7 cli/ + web/ → 功能全但命令面双轨、文档漂移
- `cli/main.py`：30+ 子命令，覆盖 onboard/intake/init/resume/status/run/decide/manual/cad/industrialize/validate/audit/release/test/eval/package/version/doctor/operate/dashboard/reset/recover/ui/product，以及 legacy 的 init-project/restore-project/run-supervisor/project-summary/submit-decision/run-manual-chain/run-cad-chain/run-tests/run-evals/build-release。
- `cli/commands.py`（1561 行，Q-4）：`cmd_intake` 里 `intake --run` 走真实 Supervisor→Router→idea.structure 链（commands.py:613-660），provider 不可用则 `decompose_status=CAPABILITY_UNAVAILABLE` 并如实打印（675-684）。
- `web/views.py` WebConsole：onboarding_center/overview/decision_center/artifact_center/run_control/external_wait_center 六个中心 + `RunController`（确定性状态机，`views.py:95-179`）；`web/server.py` HTML(GET) + JSON API(POST /api/*) + 可选 `AIPD_WEB_TOKEN` 认证。
- **注意**：WebConsole 的"运行控制"是**确定性状态机驱动**（`start_run(intent_text, events, ...)` 接收 events，非真实 LLM）——与 CLI 一致的诚实边界，但 README"全程浏览器操作"的表述易让非技术用户误解。

### 3.8 横切（runtime/registry/security/telemetry/experience/evals_runner）
- `runtime.py`：`build_runtime`/`get_runtime`/`install_runtime` 唯一装配契约，probe 四态（AVAILABLE/UNAVAILABLE/EXTERNAL_DEPENDENCY/PARTIAL/REGISTERED）。**关键缺陷见 §6 N-3**：外部 Provider 装配是硬编码 `provider=None`，无配置驱动。
- `registry.py:310` `_all__`（Q-1 确认，typo → `__all__`）。
- `security/`（crypto/auth/masking/prompt_injection/sbom）全实装，THREAT_MODEL 六类威胁均有测试。
- `experience/`（`intent_engine.py`/`instructions.py`）明确"纯关键词+正则，不依赖任何 LLM"（docstring）——`aipd operate` 的自然语言闭环是确定性意图引擎，非 LLM。
- `evals_runner/completion.py:66` 的 `raise NotImplementedError` 是抽象基类 `CompletionProvider.complete()` 的合法抽象方法（非骨架）；其 `EnvCompletionProvider` 真实调 OpenAI 兼容端点。

---

## 4. 完成度矩阵（核心交付）

基准 = README 8 大能力 + `overview.md`（V5_9_1 报告 §14）v5.10 NPI 接口清单。

### 4.1 README 承诺的 8 大能力

| # | 能力 | 判定 | 证据与缺口 |
|---|---|---|---|
| 1 | 想法整理（一句话→结构化定义） | **PARTIAL** | 编排+校验+持久化完整（`decomposer.py`）；但真实 LLM decomposer 未接线，默认 `CAPABILITY_UNAVAILABLE` |
| 2 | 证据管理（可追溯、人工确认） | **FULLY_IMPLEMENTED** | Evidence 去重/关系/评审/图谱全实装；`research.academic_search` 真实检索 |
| 3 | 产品智能（证据→需求/功能转译） | **PARTIAL** | snapshot/gate/commit/impact 全实装；但 `derive_*` 生成类 provider 未接线（EXTERNAL_DEPENDENCY），转译链只能"人工回填或接 Provider 后运行" |
| 4 | 产品定义门禁（人把关） | **FULLY_IMPLEMENTED** | Gate 三层 + Owner 决策 + 原子 commit，本地 deterministic |
| 5 | 决策中心 | **FULLY_IMPLEMENTED** | `decision_policy` + `build_decision_package` + canonical decisions + Web 决策中心 |
| 6 | 随时可见的项目状态 | **FULLY_IMPLEMENTED** | `aipd status/dashboard/product show` + `--json` + WebConsole |
| 7 | 专业子系统（手册/CAD/供应链/发布门禁） | **FULLY_IMPLEMENTED**（CAD 内核为可选依赖，无内核诚实降级 C1） | manual/cad/supply_chain/production_release_gate 均有实现 |
| 8 | 诚实与安全 | **FULLY_IMPLEMENTED** | external_blocked + simulated 拒绝 + crypto/auth/masking/prompt_injection + 审计 |

### 4.2 v5.10 NPI 接口清单（overview.md §14）

| 接口 | 现状（V5_9_1 §14 自述） | 本轮核实判定 |
|---|---|---|
| Requirement | 已就绪（NPI-ready 字段） | **FULLY_IMPLEMENTED**（`migrations.py` v10 requirements 表含 nominal/unit/limits/tolerance/test_condition/verification/derivation/affected_item_refs/required_by_gate） |
| BOM | 无独立表 | **NOT_STARTED** |
| Supplier | 有 supply_chain（mail_rfq/supplier adapter） | **PARTIAL**（adapter 有，但 canonical 表 + scope 校验未完善；生产凭据未接） |
| Cost | 无 | **NOT_STARTED** |
| ValidationTest | 无（verification_test_refs 为引用占位） | **STUB**（字段是 JSON 引用占位，无独立表/服务） |
| Risk | 已有 risks 表 | **FULLY_IMPLEMENTED**（`state/db.py` risks CRUD），但"接入 NPI 链"未做 |
| Issue | 无（change_request 经 propagation） | **NOT_STARTED**（决策未定：独立表 or 复用 changes） |
| Decision | 已就绪 | **FULLY_IMPLEMENTED** |
| Change | 已有 changes 表 | **FULLY_IMPLEMENTED**，与 propagation 打通未做 |
| Gate | 已就绪 | **FULLY_IMPLEMENTED** |
| Generic Lineage | 已就绪 | **FULLY_IMPLEMENTED** |
| MMDProjection | 仅 crosswalk 文档 | **NOT_STARTED**（`docs/architecture/MMD_AIPD_CROSSWALK.md` 仅原则） |
| Manufacturing Readiness | production_release_gate 存在（CAD 域） | **PARTIAL**（存在但与 Product Truth/NPI Gate 未打通） |

### 4.3 总体判定
- **FULLY_IMPLEMENTED（确定性/可追溯/安全）：~60%** 的代码面（state、supervisor、execution、PI 确定性部分、product_truth、idea 数据模型、research.academic_search、CAD 双后端、security、web、cli）。
- **PARTIAL（契约就绪、生产 Provider 未接）：idea.decompose、product.derive_*、evidence.assess_relation、research 其余五能力、imggen/mail/supplier 生产凭据。**
- **STUB/NOT_STARTED：BOM、Cost、ValidationTest、Issue、MMDProjection、Manufacturing Readiness 打通。**

---

## 5. 骨架侦查（全文检索，文件:行号证据）

全仓 `raise NotImplementedError` 仅 3 处，均为**合法抽象方法**（非骨架）：
- `research/fetchers.py:123`、`research/retrieval.py:91`：抽象基类 `DocumentFetcher`/`Retriever` 的抽象方法。
- `evals_runner/completion.py:66`：抽象基类 `CompletionProvider.complete()`。

`pass` 语句 14 处，均为异常处理/幂等分支的合法占位（`state/db.py:603` 跳过非数字 ID 后缀、`cli/commands.py:1238/1311` 等）。

`TODO/FIXME/XXX`：**0 处**（源码层无遗留标记）。

`simulated`/`placeholder` 关键字：全部是**诚实降级标注**（非骨架）：
- `cad_adapter.py:53`、`imggen_adapter.py:48-53`：`"status":"simulated"` 诚实标注未真实调用引擎。
- `execution_router.py:199-246`：检测 simulated 占位并拒绝标记 succeeded（防御纵深）。
- `visual_audit/auditor.py:39` `PLACEHOLDER_MARKERS`：检测 lorem/占位文本的视觉审计护栏。

**结论：源码层不存在"偷偷 TODO/空实现"的骨架；所有未实现项都以「显式契约 + 诚实 external_dependency/UnavailableProvider」的形式存在。** 真正"未动工"的是 §4.2 的 v5.10 NPI 接口（连表/契约都没有，是 `NOT_STARTED` 而非 `STUB`）。

---

## 6. 深化迭代空间（架构层，非 Q-1~Q-5 重复）

### N-1（P1）生产 LLM Provider 装配是"最后一公里"，当前硬编码
`runtime.py:268-281` `_register_external_providers` 里 `register_product_adapters(ctx.adapters, ctx.db, provider=None)` 与 `providers = ProviderRegistry()`（line 240）把"智能层"写死为无。缺一个**配置驱动的 Provider 装配点**：读 `AIPD_MODEL_API_KEY`/`AIPD_MODEL_BASE_URL`（evals 已有同款约定 `evals/runner.py:92-101`）自动实例化一个 OpenAI 兼容的 `ProductIntelligenceProvider` 与 `IdeaDecompositionProvider`。这是让 README"全程 AI 推进"从承诺变现实的最小改造成本路径——契约、adapter、路由、服务、测试全已就绪，只差 provider 实例。

### N-2（P1）`registry_data.py` 双来源 + 文件头自相矛盾
文件头写"自动生成，勿手改"（`registry_data.py` 首行 docstring），但末尾 7 项 product.* 是**手写块**（单引号风格、字段与自动生成块不同，line 82-88）。77 项 = 70 项双引号（`migrate_capability_registry.py` 生成）+ 7 项手写。任何重新运行生成脚本都会**静默丢失手写块**。建议把手写块并入生成源或独立成 `product_capabilities.py`。

### N-3（P1）`research.*` 六能力只注册一项
`runtime.py:109-112` 的 probe 遍历 `research.fulltext/related_work/novelty_check/idea_spark/asset_extract`，但生产只注册 `research.academic_search`（researchstudio）。其余五类只有 `idea/research_provider.py` 里的 `RESEARCH_CAPABILITIES` 元组声明，无注册入口 → 永远 `UNAVAILABLE`。若这些能力短期不接，建议在 registry 中显式标注"未实现"而非让 probe 静默报告 UNAVAILABLE。

### N-4（P2）idea→execution 泄漏的延伸：research→idea→execution 跨层链
`research/providers/researchstudio.py:39-42` import `aipd_os.idea.research_provider`，而 `idea/research_provider.py` import `execution`（Q-3）。形成 `research → idea → execution` 的三层反向依赖。虽无环，但 idea 作为"数据模型层"被 execution 拉入其单测依赖树，与 Q-3 同源。

### N-5（P2）文档与实现状态漂移（多处）
- `idea/__init__.py:5-11` docstring 仍写"真实 LLM provider 在 Commit 12""projections 骨架（Commit 14 填充）"——实际 provider 仍未接、projections 已实装。
- `idea/research_provider.py:3-4` docstring 写"只实现 Provider contract 与 capability 注册骨架"，但下方 `ResearchIntegration.link_evidence_for_claim`（279-383）已是完整实现。
- `cli/main.py:3` 写"10 个一键子命令"，实际 30+。

### N-6（P2）legacy 与 one-click 双命令面并存
`main.py` 同时暴露 `init-project/init`、`submit-decision/decide`、`project-summary/status/dashboard`、`run-supervisor/run`、`run-manual-chain/manual generate` 等两套语义重叠的命令。legacy 命令缺 `--json`，与新命令的 `--json` 一致性差；`SKILL.md` 里还引用了 `scripts/aipd_supervisor.py`/`aipd_state.py` 这类已迁移进包的脚本名。

---

## 7. UX 优化空间（产品负责人视角）

### 7.1 CLI
- **文档互相矛盾（最高优先）**：README 用 `aipd onboard`/`aipd init`/`aipd decide`/`aipd product show`；QUICKSTART §1-10 用 `aipd init-project`/`aipd submit-decision`/`aipd run-supervisor`/`aipd project-summary`。同一用户两篇文档照着做会得到完全不同的命令集。
- **`--json` 一致性**：`run-supervisor`/`project-summary`/`submit-decision`/`init-project`/`restore-project` 等 legacy 命令无 `--json`，与 `run/status/decide/doctor/product` 的 `--json` 不一致。
- **`aipd run` 的停止语义**：README Q5 说三类停止原因（待决策/依赖外部/阶段完成），但 `--until-decision` vs `run-supervisor --steps N` 两套步进语义并存，非技术用户难以区分。
- **`aipd doctor` 输出**：已支持 `--json`，但 prose 版未对"外部能力不可用"给出可操作的下一步（如"配置 AIPD_MODEL_API_KEY 后可启用产品智能转译"），与 README Q4/Q8 的承诺有差距。

### 7.2 WebConsole
- 六中心（onboarding/overview/decision/artifact/run/external-wait）交互完整，`RunController` 是确定性状态机（非 LLM），诚实但**未呈现"为什么停了/下一步怎么解锁 Provider"的可操作引导**——对"不会写代码"的用户，`external_wait_center` 只列等待项，没有把"如何配置 Provider 或人工回填"串成闭环向导。

### 7.3 README/QUICKSTART 与实际行为
- README §三"快速上手"与 QUICKSTART §11"v5.6 一键命令"是两套并行的入门路径，未交叉引用、未声明哪套是"推荐"。建议统一到 README 的 onboard/intake/run/status/decide/product 主线，QUICKSTART 的 legacy 命令标注 deprecated。

---

## 8. 新质量发现（昨日报告未覆盖，P0/P1/P2）

### P0
- **无新增 P0**（昨日 Q-1/Q-2 仍为最高优先；本轮未发现比 `_all__` typo 更严重的新 P0）。

### P1（应排期）
| ID | 位置 | 问题 | 建议 |
|---|---|---|---|
| N-1 | `runtime.py:240,268-281` | 生产 Provider 装配硬编码 `provider=None`/空 `ProviderRegistry`，无配置驱动注入点，"智能层最后一公里"缺失 | 新增 OpenAI 兼容 `ProductIntelligenceProvider`/`IdeaDecompositionProvider` 实现 + 读 `AIPD_MODEL_*` 环境变量自动装配 |
| N-2 | `registry_data.py`（77 项，末尾 7 项手写） | 文件头"自动生成勿手改"与手写 product.* 块矛盾；重跑生成脚本会丢手写块 | 手写块并入生成源或拆独立文件 |
| N-3 | `runtime.py:109-112` vs `research/providers/` | research 六能力只注册 1 项，其余 5 项 probe 恒 UNAVAILABLE 无注册入口 | 显式标注"未实现"或补齐注册骨架 |
| Q-4' | `cli/main.py` | 双命令面（legacy + one-click）并存，语义重叠、`--json` 不一致 | 收敛到 one-click 主线，legacy 命令标 deprecated 或别名 |

### P2（记录在案）
- **N-4** `research→idea→execution` 跨层依赖链（researchstudio.py:39 → idea/research_provider.py:38-39 → execution）。
- **N-5** 文档漂移：`idea/__init__.py:5-11`、`idea/research_provider.py:3-4`、`cli/main.py:3` 的 docstring 与实现状态不一致。
- **N-6** `SKILL.md` 仍引用 `scripts/aipd_supervisor.py`/`aipd_state.py` 等已迁移进包的脚本路径（SKILL.md:58-62）。
- **测试盲区（承昨日）**：`web`（仅 test_owner_web_console 间接）、`providers/sdk`（无直接测试）、`supply_chain`（10 文件仅 1 测试）。
- **`registry_data.py` 单行超长（88 行 / 47KB）**：已 `# ruff: noqa: E501`，但 77 项能力挤在极长单行，diff 与 review 体验差。

---

## 9. 结论

1. **确定性工程闭环已全部实现并测试锁定**（958 passed/0 failed/3 skipped）：state 事务/迁移/加密、supervisor DAG/fail-closed、execution 路由/诚实降级、PI 的 snapshot/gate/commit/impact、product_truth、CAD 双后端、security、web、cli —— 无骨架、无 TODO、无空实现。

2. **「AI 智能推理」在生产中 0% 接线**：`idea.decompose`、`product.derive_*`/`identify_opportunity`、`evidence.assess_relation`、research 五能力均为「契约 + 诚实 external_dependency」占位；全仓唯一真实 LLM 客户端只服务于模型评估（`evals/runner.py`）。这正是 README"全程 AI 推进"承诺与现实之间的**核心缺口**，且是最低改造成本的缺口（契约/adapter/路由/服务/测试全就绪，只差 provider 实例 + 配置装配）。

3. **v5.10 NPI（制造就绪）全部 NOT_STARTED**：BOM/Cost/ValidationTest/Issue/MMDProjection/Manufacturing Readiness 无表无服务，仅 Requirement/Decision/Change/Gate/Generic Lineage 就绪。

4. **UX 是当前对目标用户（非技术产品负责人）最大的可感知短板**：README 与 QUICKSTART 命令面互相矛盾、legacy 与 one-click 双命令并存、`--json` 不一致、`doctor`/WebConsole 对"如何解锁外部能力"缺少可操作引导。

**一句话给主理人**：代码不是"没写完"——确定性骨架与诚实降级框架写得很扎实；是"智能与制造两段没接线"。下一轮迭代最有价值的方向不是继续加固确定性内核，而是（a）配置驱动的生产 LLM Provider 装配（把 derive_*/decompose 点亮），（b）统一 CLI 命令面与文档，二者都直接面向"让非技术用户真正跑通全程 AI 推进"这一产品承诺。
