# Idea & Evidence Architecture（v5.8 Commit 12-16 / v5.8.1 Commit 2-4 / v5.8.2 Commit 6）

> 目标：明确 Idea → Claim → EvidenceRelation → Evidence → Idea Truth 的调用链、
> maturity（I0/I1/I2）映射、与 Supervisor 的正交关系，以及 Provider/capability 架构。
> 本文档绑定当前代码事实（v5.8.2）：decompose_existing（同一 Idea I0→I1）、
> I2 = required key claim coverage、Review-aware semantics、RuntimeContext 装配。

## 1. 调用链

```
Raw Idea（prompt）
  → IdeaDecomposer.decompose_existing(idea_id)   # v5.8.1 Commit 2：同一 canonical Idea
      → StructuredCandidate（schema validation → FAILED_VALIDATION 不落库）
      → IdeaService.update（I0→I1 保持 idea_id/raw_input/created_at 不变；不建新 Idea）
      → ClaimService.create（Candidate Claims，默认 epistemic_status=A/U，绝不 V）
  → ResearchIntegration（Claim evidence gap → EvidenceRequest）
      → ExecutionRouter.run(capability, inputs)   # capability 架构，不依赖 provider 名
      → ResearchToolAdapter / ResearchProvider（无 provider → external_blocked 诚实）
      → AIPDStateDB.add_evidence（复用 canonical evidence 表）
      → EvidenceRelationService.add（pending 默认；跨 scope link 拒绝）
      → EvidenceRelationService.review（reviewed/rejected → lineage 同步）
      → EvidenceGraph（可查询）
  → IdeaTruthProjection.project(idea_id)           # 查询组合，非第二 Store
      → IdeaTruthSnapshot（不可变快照，仅快照语义）
```

## 2. 域对象与表

| 域 | 模型 | 表（db.py SCHEMA + migrations） | 说明 |
|---|---|---|---|
| Idea | `idea/models.py` Idea | `ideas`（v2） | Raw→Structured canonical 对象（同一 idea_id）；tenant+project scoped；version 乐观锁 |
| Claim | `idea/claims.py` Claim | `claims`（v3/v9） | 需要证据支持/反驳/验证的命题；默认 A/U，绝不默认 V；confidence v9 起 NULLABLE |
| EvidenceRelation | `idea/evidence_relations.py` | `claim_evidence_relations`（v4/v9） | Claim↔Evidence 关系；跨 scope link 拒绝；strength v9 起 NULLABLE |
| Evidence | `state/db.py` evidence 表 | 既有（v1） | 复用 canonical evidence，不建第二 truth source |

全部写操作：tenant scoped + project scoped + audited（audit_log）+ versioned。
ID：idea/claim/relation/evidence/fact/decision/deliverable/risk 全部走
`id_sequences` 原子分配（v5.8.1 v5/v7 + v5.8.2 v9）。

## 3. Maturity 判定（确定性规则，v5.8.2 Commit 6）

`IdeaMaturity.evaluate` 只读 graph；`lifecycle_status` 只表达对象生命状态
（active/archived/superseded），**不携带成熟度**（v5.8.1 Commit 3）。

| 成熟度 | 判定（IdeaMaturity.evaluate + IdeaMaturityPolicy） |
|---|---|
| I0_RAW_IDEA | idea 存在但无 claims |
| I1_STRUCTURED_IDEA | 有 claims，但未满足 I2 全部条件 |
| I2_EVIDENCE_BACKED_IDEA | **(a)** 有 claims；(b) **所有 required key claim types 都存在**（`IdeaMaturityPolicy.required_claim_types` = {problem, user, mechanism, technology}）；(c) 每个 required key claim 已执行 Evidence Search（有 reviewed relation；pending/rejected 不算）；(d) 每个 required key claim 的 ClaimAssessment 非 NOT_SEARCHED；(e) 无 fake/simulated evidence（relation 的 evidence_id 必须真实存在） |
| I3_PRODUCT_OPPORTUNITY | 只定义 contract，不实现 |

**重要（v5.8.2 Commit 6）**：只有部分 key claims 被调查（如只有 problem/user
reviewed、缺 mechanism/technology）→ **I1 + Evidence Gap**（`IdeaMaturity.gap_reasons`
返回 `missing required key claim types: mechanism, technology` 等）。「已有 key
claims 都被调查」≠「必要 key claim categories 都存在」。

`IdeaMaturityPolicy`（`policy_id=idea_maturity_policy_v1`）是 key claim 策略的
**唯一载体**（显式/可测/版本化/可注入），禁止在 maturity 逻辑中硬编码。

## 4. Review-aware semantics（v5.8.1 Commit 4 + v5.8.2 Commit 5）

- ClaimAssessment 只统计 `review_status=reviewed` 的 relation；
- **pending/rejected EvidenceRelation 不建立 supported_by/contradicted_by 语义
  lineage 边**（v5.8.2 Commit 5）；只有 reviewed+supports/partially_supports →
  supported_by、reviewed+contradicts → contradicted_by；
- review()/update() 事务化同步 lineage：rejected → soft-retire 旧语义边
  （`LineageService.retire_edge`，历史保留在 dependencies 行 + audit_log）；
- inconclusive/not_applicable 永不建立语义边（inconclusive 不得支持 Claim Truth）；
- 同一 (claim, evidence) 可并存 supports+contradicts（MIXED 合法）。

## 5. 与 Supervisor 正交

Supervisor S0-S8 编号不变（正交维度）：
- **S0 Intake** 承载 I0→I1（raw idea intake + `idea.structure` 结构化分解，
  经 Supervisor → ExecutionRouter → IdeaStructureAdapter.decompose_existing）；
- **S1 Theory/Research** 承载 I1→I2（claims 经 research retrieval 获得 evidence +
  `evidence.assess_relation` 评审 + `idea_truth.refresh`）；
- S2+ 见 `docs/architecture/MMD_AIPD_CROSSWALK.md`（v5.9 Product Definition 扩展）。

Supervisor 只编排 capability，不直接调用 Domain Service
（`supervisor/idea_capabilities.py` 定义 capability 常量）。

## 6. Provider / capability 架构（v5.8.2 Commit 3-4：RuntimeContext）

- **RuntimeContext / build_runtime()**（`src/aipd_os/runtime.py`）是唯一 bootstrap
  契约：settings → State → ProviderRegistry → 外部 provider（ResearchStudio）→
  AdapterRegistry → 懒 ExecutionRouter/Supervisor → probe。CLI/Web/MCP/Supervisor
  统一依赖该契约；**禁止**在 command 内 new 空 ProviderRegistry/AdapterRegistry。
- `idea.decompose`：IdeaDecompositionProvider（经 ProviderRegistry 注册；
  CLI 经 `runtime.providers` 发现）；无 provider → CAPABILITY_UNAVAILABLE。
- `research.academic_search`：**ResearchStudioPaperSearchProvider 已接入 production
  bootstrap**（`build_runtime` 注册；v5.8.1 Commit 10 + v5.8.2 Commit 4）。
  多引擎聚合 + DOI/arXiv/title 去重 + partial 降级（successful_sources/
  failed_sources 暴露）。DBLP/OpenReview/Crossref 为预留 provider slot（未实现）。
- 既有 `research.search_papers`（Semantic Scholar adapter）保留兼容。
- 上层 Domain 依赖 **capability id**，不依赖具体 provider 名。

## 7. 诚实性护栏

- 无 provider / provider 不可用 → CAPABILITY_UNAVAILABLE / external_blocked，绝不模拟成功；
- Candidate Claims 默认 A/U，绝不产出 V 事实；
- relation 的 evidence_id 必须真实存在于 canonical evidence 表（EvidenceRelationService 强制）；
- 未评分 score 写 NULL（v9），不落 0.5 伪精确哨兵（见 `docs/architecture/SCORE_CONTRACT.md`）；
- fixture/golden 数据标注 EPISTEMIC_NOTE（非真实医学/研究结论，仅测试系统行为）。
