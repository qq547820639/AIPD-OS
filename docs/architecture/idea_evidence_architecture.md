# Idea & Evidence Architecture（v5.8 Commit 12-16）

> 目标：明确 Idea → Claim → EvidenceRelation → Evidence → Idea Truth 的调用链、
> maturity（I0/I1/I2）映射、与 Supervisor 的正交关系，以及 Provider/capability 架构。

## 1. 调用链

```
Raw Idea（prompt）
  → IdeaDecomposer（provider: idea.decompose）
      → StructuredCandidate（schema validation → FAILED_VALIDATION 不落库）
      → IdeaService.create（Idea: lifecycle=structured）
      → ClaimService.create（Candidate Claims，默认 epistemic_status=A/U，绝不 V）
  → ResearchIntegration（Claim evidence gap → EvidenceRequest）
      → ExecutionRouter.run(capability, inputs)   # capability 架构，不依赖 provider 名
      → ResearchToolAdapter / ResearchProvider（无 provider → external_blocked 诚实）
      → AIPDStateDB.add_evidence（复用 canonical evidence 表）
      → EvidenceRelationService.add（supports/contradicts/inconclusive…；跨 scope link 拒绝）
      → EvidenceGraph（可查询）
  → IdeaTruthProjection.project(idea_id)           # 查询组合，非第二 Store
      → IdeaTruthSnapshot（不可变快照，仅快照语义）
```

## 2. 域对象与表

| 域 | 模型 | 表（db.py SCHEMA + migrations） | 说明 |
|---|---|---|---|
| Idea | `idea/models.py` Idea | `ideas`（v2） | Raw→Structured canonical 对象；tenant+project scoped；version 乐观锁 |
| Claim | `idea/claims.py` Claim | `claims`（v3） | 需要证据支持/反驳/验证的命题；默认 A/U，绝不默认 V |
| EvidenceRelation | `idea/evidence_relations.py` | `claim_evidence_relations`（v4） | Claim↔Evidence 关系；跨 scope link 拒绝 |
| Evidence | `state/db.py` evidence 表 | 既有（v1） | 复用 canonical evidence，不建第二 truth source |

全部写操作：tenant scoped + project scoped + audited（audit_log）+ versioned。

## 3. Maturity 映射（确定性规则）

| 成熟度 | 判定（IdeaMaturity.evaluate） | 与 lifecycle 映射 |
|---|---|---|
| I0_RAW_IDEA | idea 存在但无 claims | lifecycle='raw' |
| I1_STRUCTURED_IDEA | claims 已创建（schema valid） | lifecycle='structured' |
| I2_EVIDENCE_BACKED_IDEA | 有 claims 关联真实 evidence（relation 的 evidence_id 真实存在，无 fake evidence） | lifecycle='evidence_backed' |
| I3_PRODUCT_OPPORTUNITY | 只定义 contract，不实现 | — |

## 4. 与 Supervisor 正交

Supervisor S0-S8 编号不变（正交维度）：
- **S0 Intake** 承载 I0→I1（raw idea intake + 结构化分解）；
- **S1 Theory/Research** 承载 I1→I2（claims 经 research retrieval 获得 evidence）。

只做文档映射，不改 Supervisor 代码。

## 5. Provider / capability 架构

- `idea.decompose`：IdeaDecompositionProvider（经 providers.sdk.ProviderRegistry 注册，
  IdeaDecompositionProviderAdapter 适配）；无 provider → CAPABILITY_UNAVAILABLE，不模拟成功。
- research 能力（ResearchStudio 检查：**/Volumes/Extra/CodeProj/ 下不存在**，本轮仅
  Provider contract + capability 注册骨架，诚实 external_dependency）：
  `research.academic_search` / `research.fulltext` / `research.related_work` /
  `research.novelty_check` / `research.idea_spark` / `research.asset_extract`。
- 既有 `research.search_papers`（Semantic Scholar adapter）保留兼容。
- 上层 Domain 依赖 **capability id**，不依赖具体 provider 名。

## 6. 诚实性护栏

- 无 provider / provider 不可用 → CAPABILITY_UNAVAILABLE / external_blocked，绝不模拟成功；
- Candidate Claims 默认 A/U，绝不产出 V 事实；
- relation 的 evidence_id 必须真实存在于 canonical evidence 表（EvidenceRelationService 强制）；
- fixture/golden 数据标注 EPISTEMIC_NOTE（非真实医学/研究结论，仅测试系统行为）。
