# AIPD-OS v5.9 Product Intelligence Report

> 生成时间：2026-08-12（Principal Software Architect，v5.9 Commit 14）
> 前置：V5_8_2_PASS（docs/audit/V5_8_2_ARCHITECTURE_TRUTH_CLOSURE.md）。

## 0. Provenance

| 字段 | 值 |
| --- | --- |
| source_commit（测试 HEAD） | 见 pytest-report.json（`docs/audit/pytest-report.json`） |
| package_version | `5.6.0` |
| generator_version | v5.9 report（Commit 11..14） |
| 测试命令 | `python -m pytest tests/ -m "not model_eval" -q --json-report --json-report-file=docs/audit/pytest-report.json` |

## 1. 交付概览

| 组件 | 内容 |
| --- | --- |
| `product_intelligence/models.py` | Insight / Opportunity / ProductPrinciple / Requirement / Feature 五个 canonical domain（三正交状态维度：definition_status / epistemic_status / lifecycle_status；criticality；NPI-ready Requirement 字段） |
| `product_intelligence/service.py` | tenant+project scoped CRUD + deterministic lineage 契约 + canonical LineageService 接线 + trace_upstream / feature_evidence_trace / principle_why |
| `product_intelligence/gate.py` | ProductDefinitionGate（13 项确定性 criteria → READY/CONDITIONAL/BLOCKED；Owner Decision 复用 canonical decisions；commit_approved → ProductTruth） |
| `product_intelligence/projections.py` | ProductDefinitionProjection（查询组合，非 Store） |
| migration v10 | insights / opportunities / product_principles / requirements / features 五表 + id_sequences（INS-/OPP-/PRN-/REQ-/FTR-） |
| Supervisor S2 | product.* 六项 capability 编排（Supervisor 只调度，不生成内容） |
| CLI | `aipd product show` / `aipd product gate`（--propose / --decision-id/--choice，--json） |

## 2. 测试数字

| 套件 | 结果 |
| --- | --- |
| 核心（not model_eval，含全部新测试） | **895 passed / 0 failed / 3 skipped**（2 failed 为 manifests 刷新前记录，最终回归见 pytest-report） |
| product intelligence（新） | 21 passed（§60 最低 16 项全覆盖 + 5 项扩展） |
| Golden E2E（新） | 7 passed（4 insights/2 opportunities/4 principles/7 requirements/5 features；BLOCKED→Owner approve→ProductTruth；Feature→Evidence 全链） |
| migration 回归 | 24 passed（v10 up/down、数据保留） |
| product_truth 回归 | 19 passed（propagation/lineage compat） |
| CLI/supervisor 回归 | 58 passed |

## 3. v5.9 Definition of Done 判定

| 项 | 状态 | 证据 |
| --- | --- | --- |
| V5_8_2 PASS | ✅ | V5_8_2_ARCHITECTURE_TRUTH_CLOSURE.md |
| Insight canonical domain | ✅ | models/service + tests |
| Opportunity canonical domain | ✅ | 同上 |
| ProductPrinciple canonical domain | ✅ | 同上 |
| Requirement canonical domain | ✅ | NPI-ready 字段 + MMD crosswalk 声明 |
| Feature canonical domain | ✅ | 同上 |
| all tenant/project scoped | ✅ | scope 校验 + 跨项目拒绝测试 |
| no duplicate truth store | ✅ | 复用 AIPDStateDB（migration v10 五表）+ ProductTruthStore（commit 目标） |
| all PI lineage uses canonical LineageService | ✅ | dependencies 表，无第三套 lineage（compat 测试验证） |
| Requirement compatible with future NPI/MMD | ✅ | definition_status 正交 + nominal/limits/tolerance/verification/derivation 字段 |
| ProductDefinitionProjection | ✅ | projections.py + 测试 |
| ProductDefinitionGate deterministic | ✅ | 13 criteria + gate_version + LLM 不可覆盖 |
| Owner approval mandatory | ✅ | commit 前强制检查（测试验证） |
| Gate before ProductTruth commit | ✅ | commit_approved 拒绝 BLOCKED/rejected |
| ChangeRequest after commit → rework | ✅ | on_upstream_changed → stale + rework tasks 测试 |
| feature→evidence traceability | ✅ | feature_evidence_trace 全链测试 |
| unknown preserved | ✅ | projection unknowns + waiver 要求 |
| contradiction visible | ✅ | projection + gate 显式列出 |
| LLM candidate ≠ verified truth | ✅ | candidate lifecycle + A 默认 + gate 前不 commit |
| migrations green | ✅ | v10 往返 + 数据保留 |
| security green（PI 域） | ✅ | tenant/project 隔离测试 |
| Idea/Evidence regressions green | ✅ | 核心 895 passed 内含 |
| Manual / CAD / Supply / Release green | ✅ | 核心回归内含 |
| current HEAD audit fresh | ✅ | 审计产物绑定 HEAD |

**判定：V5_9_PASS。**

## 4. 已知限制（诚实记录）

- Product Intelligence 的 LLM provider 接口（§45）**未实现**：当前全部为
  deterministic/手动创建路径（candidate 语义已就位，未来接入 provider 时
  产出即为 candidate，需显式评审）；
- ChangeRequest 对象本身未建表：Gate 后变更通过 ProductTruth propagation
  （stale + rework tasks）表达（§53 兼容路径）；
- NPI Runtime / MMD Runtime / Prototype Engine / Validation Engine 按
  §63 明确不做（本轮范围外）；
- `scripts/` 未新增 runtime 逻辑；CLI 仅调用 Service（§64/65 遵守）。

---
*本报告由 v5.9 Commit 14 生成。V5_9_GATE = PASS。*
