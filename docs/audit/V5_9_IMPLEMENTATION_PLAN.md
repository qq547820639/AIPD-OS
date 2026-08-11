# AIPD-OS v5.9 Implementation Plan（Evidence → Product，基于 v5.8.1 Closure）

> 状态：**PLAN ONLY** — 本文件是 v5.9 的实现计划（v5.8.1 Commit 15 重新生成，
> 覆盖旧版）。前置：v5.8.1 Closure Gate PASS（803 passed / 0 failed）。
> 设计依据：`V5_8_1_EVIDENCE_RUNTIME_CLOSURE.md` §16 + §17（NPI Readiness）。

---

## 1. v5.9 目标主链

```
Evidence（canonical，已有）
  ↓ ClaimAssessment（已有）
Insight（v5.9 新域）
  ↓
Opportunity（v5.9 新域）
  ↓
Product Principle（v5.9 新域）
  ↓
Requirement（v5.9 新域 + schema extension）
  ↓
Feature（v5.9 新域）
```

## 2. 关键前置（来自 v5.8.1）

1. `EvidenceGraph.compute_idea_evidence` / `ClaimAssessment` 作为输入（单一口径已收口）。
2. `STATUS_SEMANTICS.md`：definition_status / epistemic_status / lifecycle_status 三维度正交。
3. `MMD_AIPD_CROSSWALK.md`：MMD 是 Projection/Interchange，非第二 Truth Store。
4. Generic Lineage（dependencies 复用）已可承载跨域边（Idea→Claim→Evidence）。

## 3. Schema Extension（迁移 v7+）

| 迁移 | 表 | 关键列 |
|---|---|---|
| v7 | `insights` | insight_id/project_id/tenant_id/claim_id/evidence_ids_json/kind/confidence/version_no |
| v8 | `opportunities` | opportunity_id/project_id/tenant_id/insight_id/impact/effort/priority |
| v9 | `product_principles` | principle_id/project_id/tenant_id/statement/rationale_insight_ids_json |
| v10 | `requirements` | requirement_id/project_id/tenant_id/text/**definition_status**/acceptance_criteria_json/version_no |
| v11 | `features` | feature_id/project_id/tenant_id/requirement_id/scope_json/version_no |

- 全部列照 v2-v6 风格（text PK + tenant/project scope + version_no + created/updated_at）；
- migration runner 继续唯一 authority；v1 冻结不变。

## 4. 域 Service 与 capability

- 新建 `aipd_os/insight/`、`aipd_os/opportunity/`、`aipd_os/product_principle/`、
  `aipd_os/requirement/`、`aipd_os/feature/`（同 idea 域风格：Service + models +
  evidence_graph 查询 + projection）。
- Supervisor capability：`insight.synthesize` / `opportunity.evaluate` /
  `principle.derive` / `requirement.structure` / `requirement.research` /
  `feature.decompose`（复用 tool_adapters/idea_adapter 模式注册）。
- **definition_status 推导规则（deterministic）**：
  - 有 reviewed supports → CONFIRMED 候选；来自 insight 推导 → DERIVED；
  - 无证据 → RECOMMENDED（需求层）；冲突 → CONFLICT 待 owner 决策；
  - 被新版本取代 → OBSOLETE（lifecycle=superseded）。

## 5. NPI/MMD 接入（§92 8 项落点）

- `aipd_os/npi/`：`parse.py` / `project.py` / `export.py`（v5.10 落点，见 Closure §17.6）。
- v5.9 仅做 `requirements` 读取 MMD：走 RequirementService 导入（不直接写表）。
- **license 风险**：NPI alpha.3 无 LICENSE —— 不复制代码；仅参考公开概念自行实现。

## 6. 测试与门禁

- 每个新域：unit（CRUD/scope/audit/version）+ projection 测试；
- Golden E2E v5.9 扩展：Evidence → Insight → Requirement 全链（fixture 标注 EPISTEMIC_NOTE）；
- migration v7-v11 升级/回滚 + 冻结校验扩展；
- 全量回归 + ruff/mypy ratchet（0 新增债务）。

## 7. 验收（Definition of Done）

- [ ] Evidence → Feature 全链可运行（Supervisor → Router → adapter → Domain Service）；
- [ ] definition_status 三维度语义落地（STATUS_SEMANTICS.md 有测试）；
- [ ] MMD requirements 导入走 canonical service + lineage 边；
- [ ] 全量回归 0 failed；ruff/mypy 0 新增。
