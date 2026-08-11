# AIPD-OS v5.8.1 Evidence & Runtime Closure

> 状态：**RELEASE CLOSURE** — v5.8.1 全部 15 个 Commit 完成并通过全量回归。
> 本报告引用 `V5_8_1_RE_AUDIT.md`（复验），并记录运行时/证据链最终状态。

---

## 0. 审计元信息

| 项 | 值 |
|---|---|
| Current HEAD | `44ce21ad1997afa7c92d022139edcd99fa6fc10e`（短 `44ce21a`） |
| Version | `5.6.0` |
| Previous baseline | v5.8（802 passed 基线之后本轮 v5.8.1 继续推进） |
| 回归命令 | `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/ -m "not model_eval" -q` |
| 全量结果 | **802 passed / 0 failed / 3 skipped / 2 deselected（collected 807）** |
| 生成时间 | `2026-08-12` |

---

## 1. Re-Audit Matrix（引用 V5_8_1_RE_AUDIT.md）

12 项 CONFIRMED 问题全部 RESOLVED（修复 Commit + 验证）：

| # | 问题 | 原状态 | 修复 | 最终 |
|---|---|---|---|---|
| A | Idea I0→I1 双 Idea | CONFIRMED | Commit 2 | **RESOLVED** |
| B | raw_input 丢失 | CONFIRMED | Commit 2 | **RESOLVED** |
| C | constraints_json = repr | CONFIRMED | Commit 2 | **RESOLVED** |
| D | 任意 relation → I2 | CONFIRMED | Commit 3/5（保守 I2） | **RESOLVED** |
| E | pending 不查 review_status | CONFIRMED | Commit 4/5 | **RESOLVED** |
| F | classify_relation sources→supports | CONFIRMED | Commit 5（per-source） | **RESOLVED** |
| G | INSERT OR REPLACE | CONFIRMED | Commit 7 | **RESOLVED** |
| H | `_next_id` scan-max race | CONFIRMED | Commit 7（id_sequences） | **RESOLVED** |
| I | migration v1 未冻结 | CONFIRMED | Commit 8 | **RESOLVED** |
| J | audit.json 陈旧 | CONFIRMED | Commit 1 | **RESOLVED** |
| K | bundle_path 绝对路径 | CONFIRMED | Commit 1 | **RESOLVED** |
| L | test_repo_hygiene 无 .git 不可跑 | CONFIRMED | Commit 1 | **RESOLVED** |

---

## 2. Idea Identity（Commit 2）

- `decompose_existing` 对**同一个 Idea** 做结构化（I0→I1），不新建第二个 Idea；
  idea_id / raw_input / created_at 不变。
- raw_input 绝不置空；constraints 用真 JSON（`serialize_constraints`）。
- 测试：`test_idea_domain.py` / Golden E2E §6/§8/§9。

## 3. Evidence Semantics（Commit 3/4/5/6/7）

- **retrieval ≠ supports**：classify_relation 保守化；search 默认不输出 supports。
- **per-source relation**：relation 按 (claim, evidence, type) 唯一，source 级 provenance。
- **canonical dedupe**：DOI → arXiv → normalized(title+year) 任一命中即同证据。
- **review-aware**：projection/summary 只统计 reviewed relation；pending/rejected 单独计数（单一口径 `EvidenceGraph.compute_idea_evidence`）。
- **no INSERT OR REPLACE**：`EvidenceRelationConflictError` + `get_or_create` 幂等。
- **sequence IDs**：`id_sequences` 原子分配（8 线程并发无重复）。

## 4. ClaimAssessment（Commit 3/4）

- v1 规则：SUPPORTED / CONTRADICTED / INSUFFICIENT / NOT_SEARCHED 等；
- MIXED/CONTRADICTED 在 projection/summary 可见（`assessments` 字段）。
- Golden E2E §15 断言：`assessments[problem]=SUPPORTED`、`assessments[user]=CONTRADICTED`。

## 5. Maturity Contract（Commit 3/5）

- lifecycle（raw/active/archived）与 maturity（I0/I1/I2）分离；
- 保守 I2：4 个 key claims（problem/user/mechanism/technology）全部检索+评审才算 I2；
- `KEY_CLAIM_TYPES` 单源定义。

## 6. ResearchStudio Integration（Commit 10）

- 资产确认：`/Volumes/Extra/新躯纪元/ResearchStudio-main.zip`（**MIT License, Copyright (c) 2026 Happy**）；
- `ResearchStudioPaperSearchProvider`：capability `research.academic_search`；
- §27 contract 输出 + §28 局部降级（partial + successful/failed_sources）；
- 去重 DOI/arXiv/title；found_in 保留；MIT attribution 保留；
- 14 unit + 1 integration（env-skip，不访问外网）。

## 7. Runtime Flow（Commit 11，§57 真实运行链）

```
CLI intake --run / Supervisor
  → schedule work item (capability_floor)
  → ExecutionRouter.run(capability)
  → idea.* adapter (IdeaStructure/ClaimResearch/EvidenceAssessRelation/IdeaTruthRefresh)
  → Domain Service (IdeaDecomposer/ResearchIntegration/EvidenceRelationService/Projection)
```

- Supervisor 只 plan/schedule/route/observe/gate，不 bypass；
- Golden E2E §46 全 23 步走 Supervisor → Router（§14/§15/§20 已补齐断言）。

## 8. Migration（Commit 8/9）

- v1 **冻结**（`V1_INITIAL_SCHEMA` + `V1_FROZEN_SHA256`，不 import db.SCHEMA）；
- **migration runner 是唯一 schema authority**（AIPDStateDB.__init__ → migrate()）；
- v1→v6 全链：多租户基础 → ideas → claims → claim_evidence_relations →
  id_sequences → generic lineage 列；
- 旧库升级幂等、数据保留（v1-era/v2-era 测试）。

## 9. Lineage（Commit 9）

- generic lineage **复用 dependencies 表**（不建第二套 graph persistence）；
- `LineageService`：add_edge（scope/cycle/relation 校验 + audit）、outgoing/incoming/path；
- Idea→Claim `derived_from`、Claim→Evidence `supported_by/contradicted_by` 自动接线；
- version 持久化（`{node_id}@{version}`）支持 supersedes 语义。

## 10. CAD Artifact Semantics（Commit 13）

- `semantic_geometry_hash` = 几何身份（同参必同、改参必变、跨环境）；
- `sha256`（artifact_byte_hash）= 字节完整性（本环境可复现；tamper 检测）；
- `verify_artifact` 成立/篡改失败；byte_reproducibility_profile 文档化。

## 11. CI / Release（Commit 1/13）

- `release-ready.needs` 含 `python-core-matrix`（Python 3.12 失败阻止发布）；
- bundle_path 相对（relocatable）；
- **Audit Freshness（Commit 15 §38-39）**：pytest-report 必须含
  `source_commit == git HEAD`，否则 STALE 不能 gate release。

## 12. Security（回归）

- tenant/project isolation 全量回归通过（idea/claim/relation/evidence/lineage/decision 均 scoped）；
- `test_golden_tenant_project_isolation`、`test_authorization`、`test_product_truth_scoping` 绿。

---

## 13. Test Results（真实数字）

| 套件 | 结果 |
|---|---|
| 全量（not model_eval） | **802 passed / 0 failed / 3 skipped / 2 deselected（collected 807）** |
| integration 标记 | 15 passed / 2 skipped |
| smoke / manual_e2e / release_gate 标记 | 0 collected（未使用） |
| CAD（golden_loop + contract_unify） | 全绿 |
| 强制回归（每 Commit） | 全部通过 |
| ruff（核心模块） | 750 errors（基线 751 → **0 新增**，存量债务记录） |
| mypy（本轮新增 5 文件） | **5/5 Success** |

---

## 14. Known Limitations

- ruff ~750 / mypy 存量债务未全清（非本轮门禁；ratchet 保证 0 新增）。
- ResearchStudio 真实网络引擎仅在 `AIPD_RESEARCHSTUDIO_INTEGRATION=1` 时运行（CI 不访问外网）。
- idea_truth.refresh 为动态 projection；历史 snapshot 由调用方按需生成（`IdeaTruthSnapshot`）。
- NPI/MMD 导入（requirements/bom_items/suppliers/validation_tests/open_issues）需 v5.9 schema extension。
- NPI alpha.3 无 LICENSE 文件——授权状态未确认前**不复制其代码**（见 §18.8）。

---

## 15. V5_8_1 Gate

| 门禁 | 状态 |
|---|---|
| 全量回归 0 failed | **PASS**（802 passed） |
| Re-Audit 12 项 RESOLVED | **PASS** |
| Golden E2E §46 全链（Supervisor → Router） | **PASS** |
| Migration freeze + authority | **PASS** |
| Generic lineage 自动接线 | **PASS** |
| ResearchStudio MIT attribution + §27/§28 | **PASS** |
| CAD 正式契约 + tamper | **PASS** |
| CI python-core-matrix 依赖 | **PASS** |
| Audit Freshness（report.source_commit==HEAD） | **PASS** |
| ruff 0 新增 / mypy 5/5 | **PASS** |
| 证据绑定当前 HEAD + relocatable | **PASS** |
| 未改 releases/、未 git commit（主理人统一提交） | **PASS** |

---

## 16. V5_9 Recommendation

基于 ClaimAssessment 的 Evidence → Insight → Opportunity → ProductPrinciple →
Requirement → Feature 主链（详见重新生成的 `V5_9_IMPLEMENTATION_PLAN.md`）：
- v5.9 以 `compute_idea_evidence` / ClaimAssessment 为输入，新建 Insight/Opportunity/
  ProductPrinciple/Requirement/Feature 域（schema extension 逐表迁移）。
- 关键前置：Requirement 表 + definition_status 三态语义（STATUS_SEMANTICS.md）、
  MMD 导入走 canonical service（MMD_AIPD_CROSSWALK.md）。

---

## 17. NPI Readiness（§92，8 项）

### 17.1 可直接复用的 NPI concepts
- `definition_status` 枚举语义（CONFIRMED/DERIVED/RECOMMENDED/ESTIMATED/TBD/CONFLICT/OBSOLETE）：
  作为状态词汇表直接复用（需遵循 STATUS_SEMANTICS.md 三维度）。
- `evidence → requirements → risks → decisions → changes → gate_reviews` 的
  产品数据形状与 AIPD canonical（evidence/risks/decisions/changes/gates）1:1。

### 17.2 与 AIPD 重复的 NPI concepts
- `evidence`/`risks`/`decisions`/`changes`/`gate_reviews`：AIPD 已有 canonical 实现
  （MMD_AIPD_CROSSWALK.md 前 5 行）→ 不重复建，MMD 走投影导入。
- `open_issues` 与 supervisor_work_items 部分重叠（issue 可表达为 blocked/internal_rework 工作项）。

### 17.3 需要 schema extension 的 NPI concepts
- `requirements`（Requirement 表 + definition_status 列）；
- `bom_items`（BOM 表：quantity/uom/material）；
- `suppliers`（supplier 表：contact/qualification）；
- `validation_tests`（validation 表：test_case/pass_criteria）；
- `open_issues`（issue 表：severity/assignee）。
  → 均归 v5.9 迁移（逐表 v7/v8/...）。

### 17.4 应作 deterministic rule 的 NPI concepts
- definition_status 推导：DERIVED = 从 CONFIRMED 项可推导（无独立观测）；
- status 冲突解决（CONFLICT → 需要 owner 决策，不自动选边）；
- MMD → AIPD 字段映射（crosswalk 表即 deterministic）。

### 17.5 应作 eval 的 NPI concepts
- requirement 质量/可行性评估（对比 golden idea_quality 模式）；
- definition_status 自动判定准确率（需要标注集，fixture 非真实数据不可作为 eval 基准）。

### 17.6 v5.10 代码落点
- 新建 `aipd_os/npi/`：`parse.py`（MMD 解析）、`project.py`（→ canonical service）、
  `export.py`（canonical → MMD）；`aipd_os/requirement/`（Requirement 域 + assess）。
- Supervisor 新增 capability：`requirement.structure` / `requirement.research`。

### 17.7 MMD 与 canonical State 映射
- 见 `docs/architecture/MMD_AIPD_CROSSWALK.md`：逐对象映射 + existing/missing/owner/
  source_of_truth/lineage/migration need；MMD 是 Projection/Interchange 非第二 Truth Store。

### 17.8 license/provenance 风险
- **NPI alpha.3 无 LICENSE 文件**：授权状态未确认前**不复制其代码**；
  仅可参考公开概念（状态枚举/数据结构形状）并自行实现；
  一旦确认 license（MIT/其他），须按 ResearchStudio 先例保留 attribution。
