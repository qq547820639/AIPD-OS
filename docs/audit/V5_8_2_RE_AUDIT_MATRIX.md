# AIPD-OS v5.8.2 Re-Audit Matrix（Commit 1：先验证、后修改）

> 生成时间：2026-08-12（Principal Software Architect）
> 判定方式：读当前 HEAD `e15d5f4` 源码 + 真实测试复验。Status 取值仅限：
> `CONFIRMED` / `PARTIALLY_RESOLVED` / `ALREADY_RESOLVED` / `NOT_REPRODUCED` /
> `SUPERSEDED` / `REGRESSION`。

## 0. 验证范围说明

- 代码基线：HEAD `e15d5f4`（与提示词 source_commit `df74c08` 代码一致，差异仅为 evidence refresh 提交）。
- 核心测试：803 passed / 0 failed（`-m "not model_eval"`）；integration 15/0；CAD 21/0。

## 1. 矩阵

| ID | Issue（提示词节） | Current Status | Code Evidence | Test | Action |
| --- | --- | --- | --- | --- | --- |
| R-01 | STATUS_SEMANTICS：epistemic S/C/E 语义被文档写成 Supported/Contradicted/Evaluated（§6-A） | **RESOLVED（Commit 2）** | `docs/architecture/STATUS_SEMANTICS.md` L29-31 写 `S=Supported（有支持证据）`、`C=Contradicted（有反驳证据）`、`E=Evaluated（已评估但结论未定）`；而 `src/aipd_os/state/db.py` L33-35 注释明确 `S=Simulation（模拟/仿真值）`，`FACT_STATUSES={"V","S","C","E","A","P","T","R","U"}` | 现有测试不校验文档语义 | 更新文档 + 新增 `tests/test_status_semantics_contract.py`（Commit 2） |
| R-02 | ClaimAssessment 语义独立（§6-B） | **ALREADY_RESOLVED** | `idea/claim_assessment.py`：`SUPPORTED/PARTIALLY_SUPPORTED/MIXED/CONTRADICTED/INSUFFICIENT/NOT_SEARCHED/NOT_APPLICABLE`，版本化 `claim_assessment_v1`，与 FACT_STATUSES 分离 | `tests/test_claim_assessment.py` | 无（contract 测试并入 Commit 2） |
| R-03 | Definition Status 独立（§6-C） | **ALREADY_RESOLVED（文档级）** | `docs/architecture/STATUS_SEMANTICS.md` 已声明 `CONFIRMED/DERIVED/RECOMMENDED/ESTIMATED/TBD/CONFLICT/OBSOLETE` 三维正交；代码无 Requirement 对象（v5.9 建） | 文档已示例 REQ-001 三字段 | v5.9 Requirement 落地时带 definition_status 列（§40） |
| R-04 | Runtime 共享 registry：CLI 每 command 内 new 空 `ProviderRegistry()`（§7） | **RESOLVED（Commit 3+4）** | `cli/commands.py` L674-686 `_find_idea_decompose_provider()`：`reg = ProviderRegistry()`（L683）无任何注册 → `get_by_capability` 恒 None；`tool_adapters/builtin.py` L43 `build_registry()` 每次 new `AdapterRegistry()` | 现有测试无「注册后 CLI 可发现」用例 | 建 `runtime.py` RuntimeContext + `build_runtime()`，CLI/Supervisor 统一走（Commit 3） |
| R-05 | ResearchStudio production wiring（§9） | **RESOLVED（Commit 3+4）** | `research/providers/researchstudio.py` L344 `register_researchstudio`；全仓 grep 仅 `tests/test_researchstudio_provider.py:189` 调用；`tool_adapters/builtin.py` 不含 researchstudio adapter | `tests/test_researchstudio_provider.py`（测试内注册） | `build_runtime()` 中注册 + probe（Commit 4） |
| R-06 | Provider availability 探测粒度（§10） | **ALREADY_RESOLVED（provider 层）** | `researchstudio.py` L272-293：`successful_sources/failed_sources/partial` 暴露；全失败抛 `ResearchCapabilityUnavailable` | `tests/test_researchstudio_provider.py` 有 partial 语义用例 | Runtime probe 汇总进 capability 状态（Commit 4 接入） |
| R-07 | ResearchStudio 六源（DBLP/OpenReview/Crossref slot）（§11） | **NOT_REPRODUCED（本轮不做）** | 现有实现仅 arxiv/openalex/semanticscholar；无 DBLP/OpenReview/Crossref 代码 | - | 保留 provider slot（`default_engines` 可注入），不阻塞 Gate（§11 明确低优先级） |
| R-08 | pending EvidenceRelation 写 supported_by 语义 lineage（§12） | **RESOLVED（Commit 5）** | `idea/evidence_relations.py` L245-246：`add()` 无条件 `_link_lineage`，`supports + review_status=pending` 也建 `supported_by`；`_RELATION_TO_LINEAGE` L37-41 无 review 条件 | 无「pending 不写语义边」测试 | Commit 5：仅 `reviewed` 写语义边；pending/rejected 中性化 |
| R-09 | Relation review 更新 lineage（§13） | **RESOLVED（Commit 5）** | `evidence_relations.py` L351-377 `review()` 仅 `update(review_status=...)`，不增删/retire lineage 边；rejected 后旧 `supported_by` 残留 | 无 review→lineage 用例 | Commit 5：review→事务化 lineage 更新 + 保留 audit version/supersession |
| R-10 | I2 要求 key claim type 全覆盖（§14） | **RESOLVED（Commit 6）** | `idea/maturity.py` L78-86：仅要求已有 key claims 非 NOT_SEARCHED；若只有 problem/user 两类（缺 mechanism/technology）仍判 I2；无 key claims 分支 L88-95 仅需一条 reviewed evidence 即 I2 | 无「缺 key claim 类别→I1+gap」用例 | Commit 6：IdeaMaturityPolicy + required types 全覆盖 |
| R-11 | KEY_CLAIM_TYPES 硬编码（§15） | **RESOLVED（Commit 6）** | `maturity.py` L33 `KEY_CLAIM_TYPES = frozenset({...})` 模块级常量 | 现有测试直接引用 | Commit 6：`IdeaMaturityPolicy`（explicit/testable/versioned），保留兼容常量 |
| R-12 | Generic/ProductTruth 双套 lineage（§16/17） | **RESOLVED（Commit 7，Phase 1 facade）** | `state/lineage.py`（dependencies 表）与 `product_truth/lineage.py`（truth_lineage 表）并存 | `tests/test_generic_lineage.py`、`tests/test_product_truth_propagation.py` | Commit 7：ProductTruth.LineageGraph → canonical LineageService facade（dual-read/canonical-write），新增 compat 测试 |
| R-13 | Generic lineage edge 无 retired/superseded 状态（§18） | **RESOLVED（Commit 5）** | `state/lineage.py` `LineageEdge` 无 retired 字段；dependencies 表无 retired 列；`add_edge` INSERT OR IGNORE 幂等，无法表达边失效 | 现有测试无 retired 用例 | Commit 5/7：dependencies 增 `retired_at/retired_by` 列（migration v8）+ `LineageService.retire_edge()` |
| R-14 | Claim.confidence / Relation.strength DB 仍 NOT NULL DEFAULT 0.5（§19） | **RESOLVED（Commit 8）** | `migrations.py` V3 L305 `confidence REAL NOT NULL DEFAULT 0.5`；V4 L321 `strength REAL NOT NULL DEFAULT 0.5`；模型层 Optional + 读取时 0.5→None（`claims.py` L109-111、`evidence_relations.py` L110-112） | `tests/test_claim_domain.py` 等已测 legacy 映射 | Commit 8：migration v8 改 NULLABLE；新记录 NULL；旧 0.5 保守保留（模型层已按 legacy_unscored 处理，行为不变） |
| R-15 | Score contract：numeric score 无 score_model 版本（§20） | **RESOLVED（Commit 8，文档化 contract）** | 全仓无 `score_model/score_model_version/inputs/generated_at` 字段；`facts.confidence` 等裸数字 | 无 | Commit 8：文档化 Score contract；v5.9 新对象按 contract 建模（本轮不迁移 legacy facts） |
| R-16 | ID 生成统一（§21） | **RESOLVED（Commit 8；supervisor W- 单表顺序保留）** | idea/claim/relation/evidence(add_evidence) 已用 `id_sequences`（migration v5/v7）；仍 scan max+1：`db.py _next_id`（facts/decisions/deliverables/risks）、`get_or_create_evidence` L721、`supervisor.py next_id`（W- 项）、`mcp_server` 无独立 ID | `tests/test_relation_versioning.py` 等 | Commit 8：`get_or_create_evidence` 改 sequence；facts/decisions/deliverables/risks 迁移到 sequence（保守：保留显示格式）；supervisor W 项迁移 |
| R-17 | 加密 key 统一（§22） | **RESOLVED（Commit 9）** | runtime 真用 `AIPD_ENCRYPTION_KEY`（`state/server.py` L111/L537、`mcp_server.py` L59、docker-compose）；`config.py` Settings 却读 `AIPD_DATA_ENCRYPTION_KEY`（L86-87）；`cli/commands.py` L1319 也查 DATA 变量 | `tests/test_encryption_key_policy.py` 存在 | Commit 9：`AIPD_ENCRYPTION_KEY` canonical，DATA 为 deprecated alias；双设不同 → fail/warning（不静默） |
| R-18 | Architecture docs 绑定代码事实（§23） | **RESOLVED（Commit 9）** | `docs/architecture/idea_evidence_architecture.md` L41 仍写 `I2… lifecycle='evidence_backed'`（旧语义；代码已 lifecycle 分离）；L48 `S1 Theory/Research 承载 I1→I2` 未提 key claim coverage；无 decompose_existing 描述 | - | Commit 9：更新 idea_evidence_architecture.md / STATUS_SEMANTICS.md / state_ownership.md / architecture.md |
| R-19 | Docs-as-Code Gate（§24） | **RESOLVED（Commit 9，12 tests）** | 无 `tests/test_architecture_contracts.py` | - | Commit 9：新增，检查 status 语义 / package 路径 / capability 名 / lineage 实现 |
| R-20 | Audit provenance 字段（§25） | **RESOLVED（Commit 9）** | `scripts/audit_repo.py` L339-342 已含 generated_at/source_commit/package_version；缺 `generator_version` 与 `command` 字段 | `tests/test_release_evidence.py` 已测 source_commit 绑定 | Commit 9：audit_repo/capability_matrix 补 generator_version+command；release gate 保持 HEAD 检查 |
| R-21 | evidence_note 不允许漂移（§26） | **NOT_REPRODUCED** | 未发现机器字段与人类文本并存的两写路径；release_evidence 单一来源 | `tests/test_release_evidence.py` | 随 R-20 补测试 |
| R-22 | Python support contract（§27） | **RESOLVED（Commit 9，requires-python <3.13）** | `pyproject.toml` `requires-python=">=3.9"`；CI `python-core-matrix` 仅 3.9/3.10/3.11/3.12（`ci.yml`），无 3.13 验证 | - | Commit 9：选择 B —— `requires-python=">=3.9,<3.13"`（与已验证矩阵一致，不宣称未验证支持） |
| R-23 | CAD artifact identity contract（§28） | **RESOLVED（Commit 9，文档化 byte_reproducibility_profile）** | `tests/test_cad_contract_unify.py`：`semantic_geometry_hash` 稳定/变化、`sha256`（byte hash）tamper 检测、契约后端不伪造 hash | 21 passed | Commit 9：文档化 `byte_reproducibility_profile`（不承诺跨环境 byte 一致） |
| R-24 | Release Gate source_commit==HEAD（§25） | **ALREADY_RESOLVED** | `tests/test_release_evidence.py` freshness 门禁；`test_production_release_gate.py` 11 passed | PASS | 无 |
| R-25 | Requirement/NPI schema 兼容（§61） | **NOT_REPRODUCED（v5.9 范畴）** | 无 Requirement 对象（v5.9 建）；`docs/architecture/MMD_AIPD_CROSSWALK.md` 存在 | - | v5.9 Requirement 按 §38 字段建模（含 definition_status/nominal/limits/verification） |
| R-26 | Supervisor idea capabilities（§54 前置） | **ALREADY_RESOLVED** | `supervisor/idea_capabilities.py` 存在（119 行），`schedule_idea_structure` 可用；`supervisor.py` 有 `idea.structure` 路由 | `tests/test_supervisor_idea_runtime.py` 等 | v5.9 S2 扩 capability 编排 |
| R-27 | I2 无 simulated evidence（§14-7） | **ALREADY_RESOLVED** | `EvidenceRelationService._ensure_evidence_in_scope` 强制 evidence 真实存在；`maturity.py` 依赖 graph | `tests/test_idea_to_evidence_golden.py` | 无 |
| R-28 | cli/commands.py 持续膨胀（§64） | **CONFIRMED（设计约束）** | `cli/commands.py` 1541 行，COMMAND_FUNCS 约 30+ 命令 | - | v5.9 新逻辑全部进 Service，CLI 只调用（硬约束，Commit 11+） |
| R-29 | scripts 不再新增 runtime logic（§65） | **ALREADY_RESOLVED（现状）** | v5.8.1 以来新 domain 均入 `src/aipd_os/`；scripts 均为操作入口 | - | v5.9 延续该约束 |
| R-30 | Provider availability 状态枚举（§10：AVAILABLE/UNAVAILABLE/EXTERNAL_DEPENDENCY/PARTIAL） | **RESOLVED（Commit 3+4，probe 四态 + live_probe）** | `providers/sdk.py ProbeResult`（ok/reason）二元；researchstudio 内部 partial 语义；无统一四态枚举 | - | Commit 4：RuntimeContext.probe 输出 `available_sources/failed_sources` + 四态归类 |

## 2. 结论

- **P0 级（v5.8.2 Gate 硬性）**：R-01（文档语义）、R-04（runtime 空 registry）、R-05（ResearchStudio 未进 production）、R-08、R-09（lineage 语义）、R-10（I2 coverage）。
- **P1 级**：R-11、R-12、R-13、R-14、R-15、R-16、R-17、R-18、R-19、R-20、R-22、R-30。
- **ALREADY_RESOLVED / 不阻塞**：R-02、R-03、R-06、R-23、R-24、R-26、R-27、R-29。
- **v5.9 范畴**：R-07、R-25。

---
*本矩阵由 v5.8.2 Commit 1 生成；后续 Commit 更新矩阵中对应行的 Current Status 与证据。*
