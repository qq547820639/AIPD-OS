# 阶段 2/3 审计：AI 主管真实执行 (Execution Router) 与 理论基础与研究链

> 审计类型：只读深度审计（未修改任何生产代码）
> 审计日期：2026-08-06
> 审计范围：
>   - AREA A：`src/aipd_os/execution/*` + `src/aipd_os/tool_adapters/*` + `scripts/aipd_supervisor.py`
>   - AREA B：`src/aipd_os/research/*` + `scripts/research/*` + `src/aipd_os/security/prompt_injection.py`
> 判定标准：真实可执行代码 + 真实工具调用 + 通过测试 + 证据。凡仅抽象接口 / 空适配器 / 模拟数据 / 仅日志标签者，如实标注。

## 测试运行结果（实测）

| 命令 | 结果 |
|---|---|
| `.venv/bin/python -m pytest tests/test_execution_router.py tests/test_supervisor_execution.py tests/test_adapters.py -q` | **14 passed** |
| `.venv/bin/python -m pytest tests/test_credibility.py tests/test_prompt_injection.py -q` | **17 passed** |
| `scripts/research/selftest_postprocess.py` | **GREEN 15/15** |
| `scripts/research/selftest_runtime.py` | **OK 16/16** |

---

## AREA A — 阶段 2：AI 主管真实执行（Execution Router）

核心实现链路：
- 监督器主循环：`scripts/aipd_supervisor.py::Supervisor.run_supervisor`（L169-247）
- 执行路由：`src/aipd_os/execution/execution_router.py::ExecutionRouter.run`（L67-155）
- 存储/哈希：`src/aipd_os/execution/runs.py`（RunStore / canonical_hash）
- 适配器基类：`src/aipd_os/execution/adapter.py::ToolAdapter`（ABC）
- 注册表：`src/aipd_os/execution/registry.py::AdapterRegistry`

监督器主循环**确实**调用真实工具：`run_supervisor` → `router.run` → `adapter.execute`。
对 `doc.generate` 产生真实 Markdown 文件（`document_adapter.py` L31-56），对 `cad.faceted-fallback` 产生真实 STEP 文件（`faceted_adapter.py` L48-…）。因此"主管只排序/标记工作项而不真实调用工具"这一最坏情况**不成立**。

### A. 子能力逐项判定

| # | 子能力 | 状态 | 证据（文件:函数/行） | 测试 | 实际限制 |
|---|---|---|---|---|---|
| A1 | 领取下一工作项 get next work item | **fully_implemented** | `aipd_supervisor.py:next_work` L95-107（按优先级+依赖领取，置 running） | `test_supervisor_execution.py::test_run_supervisor_no_work_stops` | 无 |
| A2 | 校验依赖 / 事实 validate deps/facts | **partially_implemented** | 依赖：`aipd_supervisor.py:_deps_complete` L90-94；事实校验：无 | 依赖校验隐含于 `test_run_supervisor_executes_doc_to_complete` | 依赖完整才执行（真实）；但无"事实/输入事实"校验概念，仅 `router.validate_input` 做输入格式校验 |
| A3 | 发现工具 discover tools | **fully_implemented** | `execution_router.py` L88 `adapter.discover()`；`adapter.py:discover` L108-117 | `test_adapters.py::test_all_builtin_adapters_discover_validate_execute` | 无 |
| A4 | 检查能力地板 check capability floor | **fully_implemented** | `aipd_supervisor.py` L216-222（capability_floor + adapter registry 存在性检查） | `test_supervisor_execution.py::test_run_supervisor_executes_doc_to_complete` | 只检查"有适配器"，不校验成熟度地板数值 |
| A5 | 选择工具 select tool | **fully_implemented** | 路由按 capability_id 选适配器 + `adapter.fallback_chain()` 降级选型（`execution_router.py` L79-82, L205-224） | `test_execution_router.py::test_fallback_switch_records_tool_change` | 无 |
| A6 | 执行 execute | **partially_implemented** | 路由真实调用 `adapter.execute`（`execution_router.py` L170）；但多工具为模拟/外部包：`research_adapter.py` L50-66（simulated）、`imggen_adapter.py` L48-56（status:simulated）、`cad_adapter.py` L53 | `test_adapters.py`（doc/faceted 真实；research/imggen 仅模拟分支） | 主循环机制是真实的；但 research / imggen / cad 适配器在"可用"时仍只返回**模拟占位**，非真实工具结果 |
| A7 | 监控进度/超时 monitor progress/timeout | **not_implemented** | 无 heartbeat、无 timeout、无进度回调；`duration_ms` 恒为 0（`execution_router.py` L183/L150） | 无 | 主管与路由均无执行超时/心跳/进度上报 |
| A8 | 收集产物 collect artifacts | **fully_implemented** | `adapter.py:collect_artifacts` L134；`execution_router.py` L173 | `test_execution_router.py::test_success_records_all_fields_and_persists`；`test_adapters.py::test_faceted_writes_real_step_artifact` | 无 |
| A9 | 校验产物 validate artifacts | **not_implemented** | 无产物内容/存在性校验；`_quality_gate`（`aipd_supervisor.py` L147-159）仅检查 `evidence_references` 与 `output_hash` 存在 | 无 | 质量门不校验产物文件本身 |
| A10 | 保存哈希/证据 save hashes/evidence | **fully_implemented** | `canonical_hash`（`runs.py` L54-57）；output_hash / evidence_refs 持久化（`execution_router.py` L175-192） | `test_execution_router.py::test_hashes_stable_and_sensitive_to_input`、`test_success_records_all_fields_and_persists` | 无 |
| A11 | 更新 Product Truth update Product Truth | **not_implemented** | 全库无 `product_truth`；监督器只写 `supervisor_work_items` / `supervisor_*` 表，**不**调用 `aipd_store.py::AIPDStore.add_fact` / `src/aipd_os/state/db.py::add_fact`（facts 表） | 无 | 主管执行结果不回写事实表（Product Truth）；"update_facts_evidence" 仅为 steps_log 标签（`aipd_supervisor.py` L230） |
| A12 | 标记 stale mark stale | **partially_implemented** | `aipd_supervisor.py:_mark_stale` L160-168（写 lineage 'invalidates'） | 无独立测试（未在运行的 3 个测试文件中断言） | 仅登记"失效"血缘，不自动重建/重排被标记的依赖工件 |
| A13 | 自动创建返工 auto-create rework | **partially_implemented** | `aipd_supervisor.py:fail` L112-114（失败置 `internal_rework`，被 `next_work` 重新领取） | `test_supervisor_execution.py::test_run_supervisor_executes_doc_to_complete`（成功路径）；失败返工仅经 `test_execution_router.py` 间接覆盖 | 返工 = 复用同一工作项重试，**不创建新的返工工作项**，无返工次数上限 |
| A14 | 推进生命周期 advance lifecycle | **not_implemented** | `supervisor_phase_runs` 仅 init 创建（`aipd_supervisor.py` L82）与 status 读取（L128），**从不更新**；`steps_log` 含 'create_rework_or_advance' 但仅为字符串标签 | 无 | 阶段永不推进（S0 恒 active，其余恒 planned）；无真实阶段跃迁逻辑 |
| A15 | 仅在真实决策点暂停 pause at decision points | **fully_implemented** | `decision_policy.py::should_ask_decision` L45-80 + `aipd_supervisor.py` L210-215（owner_required / 政策命中才 block_decision） | `test_supervisor_execution.py::test_run_supervisor_owner_required_returns_decision` | 无（普通重做/检索/批量不触发） |

### A. 健壮性子能力判定

| # | 子能力 | 状态 | 证据 | 测试 | 实际限制 |
|---|---|---|---|---|---|
| A16 | 幂等 idempotency | **not_implemented** | 无幂等键 / 去重；`canonical_hash` 仅用于记录 | 无 | 不能防止同输入重复执行（`test_hashes_stable…` 两次同输入产生两条 run） |
| A17 | 有界重试 bounded retry | **fully_implemented** | `execution_router.py` L108-136（max_attempts + 指数退避 + record_retry） | `test_execution_router.py::test_failing_adapter_records_retry_lineage` | 无 |
| A18 | 工具降级 tool degradation | **fully_implemented** | `execution_router.py:_try_fallback` L195-240（fallback_chain + status='fallback'） | `test_execution_router.py::test_fallback_switch_records_tool_change` | 无 |
| A19 | 取消 cancellation | **partially_implemented** | `fail()` 支持 'cancelled' 状态（`aipd_supervisor.py` L112-113）；`STATUS_CHOICES` 含 cancelled | `test_adapters.py` 间接（分类） | 无执行中取消机制，仅事后标记状态 |
| A20 | 心跳 heartbeat | **not_implemented** | 无 | 无 | 无 |
| A21 | 超时 timeout | **not_implemented** | 主管/路由无超时；仅 research 脚本层有 HTTP 超时（`_http_runtime.py`） | 无（主管层） | 工具执行可无限阻塞 |
| A22 | 错误分类 error classification | **fully_implemented** | `adapter.py:classify_failure` L143-147；`models.py:ERROR_CLASSIFICATIONS` | `test_execution_router.py::test_failing_adapter_records_retry_lineage` | 无 |
| A23 | 成本记录 cost recording | **fully_implemented** | `models.py:cost`；`execution_router.py` L189 | `test_execution_router.py::test_success_records_all_fields_and_persists` | 无 |
| A24 | token 记录 token recording | **fully_implemented** | `models.py:tokens_in/out`；`execution_router.py` L190-191 | `test_execution_router.py::test_success_records_all_fields_and_persists` | 无 |
| A25 | 产物哈希 artifact hashing | **partially_implemented** | 仅 input/output 内容哈希（`runs.py:canonical_hash`）；`artifacts` 列表仅存路径，不哈希文件 | 无 | 产物文件本身无哈希/校验 |
| A26 | 执行血缘 execution lineage | **fully_implemented** | `retry_lineage`（`runs.py:record_retry`）+ `supervisor_lineage` 表（`aipd_supervisor.py` L38-42, L119-120） | `test_execution_router.py::test_failing_adapter_records_retry_lineage`、`test_unified_record_all_19_keys_and_fallback_round_trip` | 无 |
| A27 | 失败/中断后恢复 recovery | **partially_implemented** | 失败项置 `internal_rework`，下次 run 重新领取（`aipd_supervisor.py` L112, L99） | 无独立测试 | 无运行中 checkpoint/resume；中断的 in-flight run 无法原地恢复 |

---

## AREA B — 阶段 3：理论基础与研究链

真实组件链：
- 多源聚合：`scripts/research/search_papers.py`（跨源 worker 编排）
- 单一来源 worker：`scripts/research/source_worker.py`
- HTTP 超时/重试策略：`scripts/research/_http_runtime.py`
- 去重/排序：`scripts/research/postprocess.py`
- 6 个来源 connector：`search_papers_by_{arxiv,crossref,dblp,open_alex,openreview,semantic_scholar}.py`
- 证据可信度：`src/aipd_os/research/credibility.py`
- 提示注入隔离：`src/aipd_os/security/prompt_injection.py`

### B. 子能力逐项判定

| # | 子能力 | 状态 | 证据（文件:函数/行） | 测试 | 实际限制 |
|---|---|---|---|---|---|
| B1 | 用户附件接管 user attachment takeover | **not_implemented** | 无研究侧附件摄取管线；`prompt_injection.py` 仅把 'attachment' 当来源类型做净化；`evals_runner` 的 `attachment_continuity` 仅为评测打分，非真实附件接管 | 无 | 没有"接手用户附件用于研究"的代码 |
| B2 | 多源学术检索 multi-source | **fully_implemented** | `search_papers.py:search_papers` L275-329 + `_SOURCE_MODULE` L40-48（arxiv/crossref/dblp/open_alex/openreview/semantic_scholar 六源）；各 connector 真实 HTTP 调用（如 `search_papers_by_arxiv.py` L71-94、`_crossref` L27-96、`_semantic_scholar` L29-88、`_openreview` L143-181、`_dblp` L42-43、`_open_alex` L46-49） | `selftest_runtime.py`（16/16，含本地 HTTP 服务器 + mock 校验） | 真实 HTTP 代码；离线测试用 mock/本地服务器，未做真实公网调用（合理） |
| B3 | 全文 vs 摘要区分 full-text vs abstract | **not_implemented** | 所有 connector 仅取 `abstract`；无全文拉取/区分逻辑 | 无 | 仅摘要，无全文能力 |
| B4 | 去重与排序 dedup and ranking | **fully_implemented** | `postprocess.py:dedup` L86-137、`rank` L140-156（`found_in` 溯源、max 引用、survey 沉底、opt-in min_score） | `selftest_postprocess.py`（15/15 GREEN） | 无 |
| B5 | 标准/法规 standards/regulations | **not_implemented** | 检索侧无标准/法规来源；`credibility.py` 仅有 `official_standard` 评分分类 | 无 | 无检索实现 |
| B6 | 专利 patents | **not_implemented** | 检索侧无专利来源；`credibility.py` 仅有 `patent` 评分分类 | 无 | 无检索实现 |
| B7 | 竞争者 competitors | **not_implemented** | 无 | 无 | 无 |
| B8 | 证据可信度 evidence credibility | **fully_implemented** | `credibility.py:score_evidence` L59-88、`source_credibility` L36-40 | `tests/test_credibility.py`（9 项通过） | 无 |
| B9 | 证据时效性 evidence timeliness | **fully_implemented** | `credibility.py:time_decay` L43-49（30 天满值+线性衰减+0.2 下限） | `tests/test_credibility.py::test_time_decay_floor` | 无 |
| B10 | 假设与事实隔离 assumption vs fact | **fully_implemented** | `credibility.py:separate_facts_from_assumptions` L91-100、`assumption_factor` L52-56 | `tests/test_credibility.py::test_separate_facts_from_assumptions` | 无 |
| B11 | 引用 citations | **not_implemented** | 论文仅有 URL/DOI 字段，无引用格式化/写回 | 无 | 无引用生成 |
| B12 | 外部内容提示注入隔离 prompt-injection isolation | **fully_implemented** | `prompt_injection.py:sanitize_external_content` L227-291、`detect_suspicious_instructions` L83-120、`external_never_controls_policy` L123-135、`external_can_not_send_sensitive_info`、`requires_human_approval` | `tests/test_prompt_injection.py`（8 项通过） | 无 |
| B13 | 检索结果写回 Product Truth / Evidence Register | **not_implemented** | research 脚本只写本地 JSON；监督器不调用 `add_fact`/`add_evidence`（`aipd_store.py` facts/evidence 表 / `state/db.py` L407/L482）；`research_adapter.py` 仅把 URL+run_id 存入 `execution_runs.evidence_refs_json` | 无 | 研究结果不写回事实表与证据登记表 |
| B14 | 检索/解析失败保持未验证（不虚构结论） | **fully_implemented** | `source_worker.py` L47-63（错误捕获并入 errors）、`search_papers.py:_collect_worker` L159-183（worker 崩溃/坏 JSON 仅跳过该源）、`credibility.py::score_evidence` 缺来源返回 `not_verifiable`、`research_adapter.py` 缺 API key 抛 `external_blocked` 不再是模拟 | `selftest_runtime.py::test_worker_crash_and_invalid_json_do_not_cancel_other_sources`、`test_adapters.py::test_research_unavailable_writes_task_package`、`test_credibility.py::test_score_evidence_missing_source_not_verifiable` | 失败路径诚实，无虚构结论 |

---

## 结论：未 fully_implemented 的子能力清单

**AREA A（执行主管）**
- A2 校验依赖/事实：依赖真实，但无"事实"校验（partially）
- A6 执行真实工具：主循环真实，但 research/imggen/cad 适配器可用时仍返回模拟占位（partially）
- A7 监控进度/超时：主管与路由均无（not_implemented）
- A9 校验产物：无产物内容校验（not_implemented）
- A11 更新 Product Truth：主管不回写事实表（not_implemented）
- A12 标记 stale：仅登记血缘，不重建/重排（partially）
- A13 自动创建返工：复用旧项重试，不新建返工项、无上限（partially）
- A14 推进生命周期：阶段表从不更新，仅日志标签（not_implemented）
- A16 幂等：无幂等键/去重（not_implemented）
- A19 取消：仅事后标记状态，无执行中取消（partially）
- A20 心跳：无（not_implemented）
- A21 超时：主管层无（not_implemented）
- A25 产物哈希：产物文件不哈希（partially）
- A27 失败/中断恢复：无 checkpoint/resume（partially）

**AREA B（研究链）**
- B1 用户附件接管：无管线（not_implemented）
- B3 全文 vs 摘要：仅摘要，无全文（not_implemented）
- B5 标准/法规：无检索（not_implemented）
- B6 专利：无检索（not_implemented）
- B7 竞争者：无（not_implemented）
- B11 引用：无引用生成（not_implemented）
- B13 检索结果写回 Product Truth / Evidence Register：无写回（not_implemented）

---

## 关键发现摘要

1. **监督器确实真实调用工具**：`run_supervisor → router.run → adapter.execute`，`doc.generate` 与 `cad.faceted-fallback` 产出真实文件。并非"只排序/标记工作项"的空壳。
2. **最弱的执行能力**：推进生命周期（A14）、更新 Product Truth（A11）、监控/超时/心跳（A7/A20/A21）、产物校验（A9）完全缺失——`create_rework_or_advance`、`update_facts_evidence` 只是 `steps_log` 字符串标签，无真实实现。
3. **多工具适配器是"模拟可用"**：`research`、`imggen`、`cad` 在配置了凭据/"后端"时仍返回 `simulated` 占位（诚实标注），并非真实工具调用。
4. **研究链检索是真实代码**：6 源 connector + worker 编排 + HTTP 超时/重试 + 去重/排序均为可执行真实代码，离线 selftest 全绿；失败路径诚实无虚构。
5. **研究结果未写回统一事实/证据登记**：research 与 supervisor 均不调用 `add_fact`/`add_evidence`，Product Truth / Evidence Register 与执行链脱节。
6. **测试覆盖不均**：`test_execution_router.py`/`test_adapters.py`/`test_supervisor_execution.py` 14 项通过，但未断言产物校验、stale 重建、生命周期推进、Product Truth 写回、幂等、取消、心跳、超时、恢复——与上述 not/partially 判定一致。