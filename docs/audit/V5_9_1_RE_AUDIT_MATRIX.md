# V5_9_1 Re-Audit Matrix（Product Definition Integrity & Runtime Closure）

生成日期：2026-08-12
基线 HEAD：`3a98538`（Change Set 1，未改代码前逐项复现）
状态枚举：CONFIRMED / PARTIALLY_RESOLVED / ALREADY_RESOLVED / NOT_REPRODUCED /
SUPERSEDED / REGRESSION

每项附：source file / function / reproduction / test / action。

## P0 类

### P0-01 零 contradiction 强制 CONDITIONAL
- **状态**：**RESOLVED（Change Set 3，commit 9aa1f82）**
- source：`src/aipd_os/product_intelligence/gate.py`
- function：`_check_assessments()`（line 122-124）
- reproduction：`blockers.append(f"explicit contradiction visibility: {contradicted} ...")` 无条件执行（contradicted=0 也 append）；`evaluate()`（line 222-229）用 `startswith("explicit contradiction")` 分类：无 hard + 有 contradiction 前缀 → `GATE_CONDITIONAL`。0 contradiction 时 blockers=[visibility 0]，result=CONDITIONAL。
- test：`tests/test_product_intelligence.py` 现有用例在 gate READY 场景必然携带 contradiction 0 信息 → 但现有测试未断言 CONDITIONAL 细节（新语义需新增 `test_zero_contradiction_not_conditional`）。
- action：Gate 重构为结构化 `GateEvaluation`（hard_blockers/conditional_blockers/warnings/information），contradiction=0 → information；>0 → 按 criticality/review/waiver 分类。visibility 不进 blockers。

### P0-02 Owner Approval 未绑定确切 Product Definition
- **状态**：**RESOLVED（Change Set 3）**
- source：`src/aipd_os/product_intelligence/gate.py`
- function：`_check_owner_approval()`（line 196-206）；`owner_decision_status()`（line 279-291）
- reproduction：仅按 `topic == product_definition_gate and status == resolved and choice == approve` 匹配**任意**历史 decision（`any()`）；无 snapshot_id/content_hash 绑定。Project 曾 approve 一次 → 永久 approved。
- test：现有 `test_gate_approved_commits_product_truth` 只建一条 approve。新测试：`test_old_approve_does_not_approve_new_snapshot`、`test_decision_bound_to_snapshot_hash`。
- action：Decision 绑定 snapshot_id + snapshot_hash + gate_evaluation_id（decisions.metadata_json，migration v11）；`get_effective_decision(snapshot_id)` 确定性投影（最新 resolved 为准，历史保留）。

### P0-03 Latest Decision Semantics 缺失
- **状态**：**RESOLVED（Change Set 3）**
- source：`src/aipd_os/state/db.py` `resolve_decision`/`list_decisions`（line 818-863）；gate.py 无 `get_effective_decision`
- reproduction：同一 snapshot 先 APPROVE 后 REJECT，任何查询 `any(resolved approve)` 仍返回 True；无 supersede/version 语义。
- test：`test_latest_reject_overrides_old_approve`、`test_superseded_approval_is_audit_visible`（新增）。
- action：`get_effective_decision()`：按 metadata.snapshot_id 过滤 resolved decisions，取最新（resolved_at desc / version_no desc / created_at desc tiebreak），deterministic projection，无 mutable boolean。

### P0-04 CONDITIONAL commit 无显式 Waiver
- **状态**：**RESOLVED（Change Set 3）**
- source：`src/aipd_os/product_intelligence/gate.py` `commit_approved()`（line 294-358）
- reproduction：`commit_approved` 只禁 `result == BLOCKED`（line 311-314）；`CONDITIONAL + approve` 直接 commit，无 waiver 记录（accepted_conditions/owner/decision_id/snapshot_id 均无）。
- test：`test_conditional_without_waiver_cannot_commit`、`test_conditional_with_waiver_commits_and_records`（新增）。
- action：commit 语义：READY+APPROVE → 允许；CONDITIONAL+APPROVE → 禁止；CONDITIONAL+APPROVE_WITH_WAIVER → 允许 + waiver 入 metadata；BLOCKED → 永远禁止。Waiver 绑定 snapshot_id/decision_id/owner。

### P0-05 ProductIntelligence update 非事务化（validate-after-commit）
- **状态**：**RESOLVED（Change Set 2-3）**
- source：`src/aipd_os/product_intelligence/service.py` `_update()`（line 261-302）
- reproduction：`UPDATE`（line 284-292，`with connect()` 隐式提交）→ **之后** `_ensure_refs_in_scope`（line 296-301）。跨 project ref 异常时非法引用已入库。`_create()`（line 193-226）insert → audit → lineage 三步骤亦无事务。
- test：`test_cross_project_update_rolls_back_object_change`、`test_invalid_ref_update_rolls_back_lineage`、`test_optimistic_lock_failure_changes_nothing`、`test_audit_failure_rolls_back_update`（新增）。
- action：`AIPDStateDB.transaction()`（SAVEPOINT 嵌套 + connect 复用活动连接）；`_update` 重排：construct candidate → validate refs/lifecycle → optimistic UPDATE → reconcile lineage → audit，全在事务内。

### P0-06 Lineage Reconciliation 缺失
- **状态**：**RESOLVED（Change Set 3）**
- source：`src/aipd_os/product_intelligence/service.py` `_link_lineage()`（line 172-186）
- reproduction：update 引用变化时仅 `add_edge`（幂等 add）；旧边保持 active。Requirement 从 Principle A 改到 B → A 边仍在 active 查询中。
- test：`test_requirement_source_change_retires_old_edge`、`test_feature_requirement_change_retires_old_edge`、`test_repeated_same_update_is_idempotent`、`test_retired_edge_not_used_by_active_trace`（新增）。
- action：`_reconcile_lineage()`：desired refs vs current active edges diff → to_retire（retire_edge，保留历史）+ to_add（add_edge）。

### P0-07 Opportunity Selection 非显式
- **状态**：**RESOLVED（Change Set 3）**
- source：`src/aipd_os/product_intelligence/models.py` Opportunity（line 178-255 无 selection_status）；`projections.py` line 77-80 `opportunity.selected = 非 archived`；`gate.py` `_check_opportunity_and_principles()`（line 127-139）"no selected Opportunity" 实为「无非 archived」
- reproduction：「存在任意非 archived Opportunity」被当作 selected。多 opportunity 时无单 selected 语义。
- test：`test_candidate_opportunity_does_not_satisfy_selection_gate`、`test_selected_opportunity_satisfies_gate`、`test_multiple_selected_opportunities_block_gate`、`test_archived_selected_opportunity_invalid`（新增）。
- action：`Opportunity.selection_status`（candidate/selected/rejected/superseded，migration v11 列）；`select_opportunity()`（单 selected 约束，事务）；Gate/Projection 用显式 selection。

### P0-08 Owner Approval 自动 verified
- **状态**：**RESOLVED（Change Set 3）**
- source：`src/aipd_os/product_intelligence/gate.py` `commit_approved()` line 330/346 `trust_level="verified"`（仅因 Owner approve）
- reproduction：approve → ProductTruth `trust_level=verified`，无 epistemic/verification 依据。
- test：`test_owner_approval_not_verified_truth`、`test_trust_level_derived_from_epistemic_and_verification`（新增）。
- action：trust_level 按真实来源推导：epistemic_status + verification_test_refs；metadata 记录 approval_state/definition_status/source_snapshot_id/hash/owner_decision_id；approval ≠ verified。

### P0-09 ProductIntelligenceProvider Contract 缺失
- **状态**：**RESOLVED（Change Set 5，commit 5ec0e90）**
- source：`src/aipd_os/product_intelligence/`（models.py line 22 docstring 引用 `:mod:`provider``，但 provider.py 不存在）；全仓无通用 LLM completion provider 可复用（evals_runner/completion.py 为 eval 专用）
- action：新建 `provider.py`：ABC + typed candidate（InsightCandidate 等）+ GenerationProvenance + schema validation；tests 内 FakeProvider；production bootstrap 不默认注册 fake（缺配置 → EXTERNAL_DEPENDENCY）。

### P0-10 Capability Catalog 缺 product.*
- **状态**：**RESOLVED（Change Set 5）**
- source：`src/aipd_os/registry_data.py`（grep `product.` = 0 条）；`src/aipd_os/supervisor/idea_capabilities.py` line 25-30 已声明常量
- action：registry_data.py 注册 7 条 product.*（derive_insights/identify_opportunity/derive_principles/derive_requirements/derive_features/create_snapshot/definition_gate），metadata 含 adapter/provider requirement/availability probe/tests。

### P0-11 RuntimeContext 未完全成为 Runtime Authority
- **状态**：**RESOLVED（Change Set 5；probe 覆盖 product.* 四态；CLI/Web/MCP 统一 bootstrap）**
- source：`src/aipd_os/runtime.py`（已存在 build_runtime/get_runtime/RuntimeContext，v5.8.2 Commit 3+4）；CLI `cmd_intake` 已用 build_runtime；`probe()`（line 105-131）只覆盖 research/idea/evidence，**无 product.*** 探测
- action：probe 扩展 product.* 动态四态（adapter 缺 → UNAVAILABLE；adapter 在但 provider 缺 → EXTERNAL_DEPENDENCY；adapter+provider 就绪 → AVAILABLE）；Supervisor 注入 runtime；test：`test_capability_probe_matches_provider_state` 等。

### P0-12 Supervisor S2 声明但不可执行
- **状态**：**RESOLVED（Change Set 6-7；Runtime Golden E2E 打通全链）**
- source：`src/aipd_os/supervisor/idea_capabilities.py` line 39-44（CAPABILITY_STAGE_MAP 已含 S2）+ schedule helpers（Commit 12）；但 AdapterRegistry 无 product.* adapter → `run_supervisor` 无法真实 route
- action：tool_adapters/product_adapters.py + build_runtime 注册（provider 未配置 → discover.available=False → 诚实 EXTERNAL_DEPENDENCY）；schedule_product_intelligence_chain；Runtime Golden E2E 用 FakeProvider（tests-only）打通 Supervisor→Router→Adapter→Provider→Service。

## 非 P0 观察

### O-1 Generic/ProductTruth lineage 双读（v5.8.2 已收敛）
- **状态**：**ALREADY_RESOLVED**（Commit 7 facade：canonical-write + dual-read）
- source：`src/aipd_os/product_truth/lineage.py`；test：`tests/test_product_truth_generic_lineage_compat.py`

### O-2 ID 生成统一（v5.8.2 Commit 8 已收敛）
- **状态**：**ALREADY_RESOLVED**（id_sequences 全对象；v9 seed）
- source：`src/aipd_os/state/db.py` `next_sequence`

### O-3 Migration 版本（v11 需要）
- **状态**：**RESOLVED（Change Set 2；v11 已落地，freeze/idea_domain/score_contract 断言同步）**
- test：`tests/test_migration_freeze.py` / `tests/test_idea_domain.py` 硬编码版本列表

### O-4 Audit provenance（v5.8.2 Commit 9 已收敛）
- **状态**：**ALREADY_RESOLVED**（generator_version/command/source_commit）
- 注意：本轮新审计产物一律写 `tested_commit`（报告 commit 进 repo 后 SHA 会变 —— 不制造自指承诺）。
