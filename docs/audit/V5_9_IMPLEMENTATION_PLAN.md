# AIPD-OS v5.9 Implementation Plan（Evidence → Product，仅计划，不在 v5.8 实施）

> 状态：**PLAN ONLY** — 本文件是 v5.9 的实现计划，不属于本轮（v5.7/v5.8）交付范围。
> 前置：v5.7 Foundation Gate PASS + v5.8 Idea & Evidence Gate PASS（均已验证）。

---

## 1. v5.9 目标主链

```
Evidence
  ↓
Insight
  ↓
Opportunity
  ↓
Product Principle
  ↓
Requirement
  ↓
Feature
  ↓
Product Definition Gate（EXPLORE/CREATE → COMMIT/ENGINEER）
  ↓
Product Truth / Engineering Baseline / CAD（冻结工程事实）
```

关键能力：**Product Translator**（Evidence → Product 语义翻译器）。

## 2. 可追溯性契约（铁律）

- 任何 **Product Principle** 必须反向可追溯：
  `ProductPrinciple → EvidenceRelation → Evidence → Source`
- 任何 **Feature** 必须追溯：
  `Feature → Requirement → Product Principle → Evidence`
- 不可追溯的 Principle / Feature 视为未验证，禁止进入冻结工程事实。

## 3. Product Definition Gate

| 阶段 | 语义 |
|---|---|
| Gate 前 | `EXPLORE` / `CREATE`（探索、创作，可逆） |
| Gate 后 | `COMMIT` / `ENGINEER`（提交、工程化，冻结） |

Gate 通过后，Product Truth / Engineering Baseline / CAD 才允许成为冻结工程事实（进入 Engineering Truth）。

## 4. 建议实现顺序（Commit 草案，每步真实测试）

| # | 内容 | 关键点 |
|---|---|---|
| V5.9-1 | Insight 域 | 由 Evidence Graph 聚合：Idea → Claims → Evidence 的洞察投影（确定性规则，不伪造 AI 洞察） |
| V5.9-2 | Opportunity 域 | 机会识别（依赖 I2/I3 成熟度 + 无 fake evidence） |
| V5.9-3 | ProductPrinciple 域 | canonical 表 + 反向可追溯（principle→evidence relation） |
| V5.9-4 | Requirement 域 | Requirement → Principle 追溯；epistemic_status 继承 |
| V5.9-5 | Feature 域 | Feature → Requirement → Principle → Evidence 全链追溯 |
| V5.9-6 | Product Definition Gate | EXPLORE/CREATE ↔ COMMIT/ENGINEER 状态机 + 审计 |
| V5.9-7 | ProductTranslator | Provider 抽象（经 ProviderRegistry，无 provider → CAPABILITY_UNAVAILABLE），不做单一 LLM 绑定 |
| V5.9-8 | 冻结工程事实 | Gate 后 Product Truth / Engineering Baseline / CAD 写入 Engineering Truth |

## 5. v5.9 明确不做

- 完整 Opportunity Engine（只做最小可行）
- UI generator / Industrial concept generator
- 完整 Validation Planner / 自动 Product Definition Gate 全自动
- 大型前端重构

## 6. 依赖既有能力（无需重建）

- EvidenceGraph（v5.8 Commit 11）
- IdeaTruthProjection / maturity I0-I3（v5.8 Commit 14）
- ProviderRegistry / ExecutionRouter / AdapterRegistry（既有 + v5.8 Commit 12/13）
- Lineage / Audit / Gate（既有）
