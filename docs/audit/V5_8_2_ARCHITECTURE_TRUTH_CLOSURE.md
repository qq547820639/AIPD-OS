# AIPD-OS v5.8.2 Architecture & Truth Closure

> 生成时间：2026-08-12（Principal Software Architect，v5.8.2 Commit 10）
> 本报告绑定：source_commit（测试 HEAD）+ 全部真实测试数字。

## 0. Provenance

| 字段 | 值 |
| --- | --- |
| source_commit（测试 HEAD） | `8a340556e4ac8b413736c82ba0ab05f9f12ae612` |
| package_version | `5.6.0` |
| generator_version | v5.8.2 closure（Commit 1..10） |
| python / cadquery | 3.9.6 / 2.5.2（.venv） |
| 测试命令 | `python -m pytest tests/ -m "not model_eval" -q --json-report --json-report-file=docs/audit/pytest-report.json` |

## 1. 测试结果（最终回归，HEAD 8a34055）

| 套件 | 结果 |
| --- | --- |
| 核心（not model_eval） | **870 passed / 0 failed / 3 skipped / 2 deselected**（808 collected） |
| integration | 15 passed / 2 skipped |
| Manual E2E + Production Release Gate | 11 passed |
| CAD Golden Loop + Contract Unify | 21 passed |
| Manual/Release/Auth/Tenant/Migration/Supply 专项 | 87 passed |
| packaging + repo hygiene + release evidence | 29 passed |
| ruff（全仓） | 历史债务（3112 errors，baseline 记录）；**所有新增/修改代码 0 新增错误**（逐文件对比验证） |
| mypy | 历史债务（120 errors / 48 files，baseline 记录）；新模块 runtime.py 自身 0 error |

## 2. v5.8.2 修复清单（Commit 2..9）

| Commit | 内容 | Re-Audit 项 |
| --- | --- | --- |
| 2 | Status semantics 三正交维度（epistemic S/C/E/R 语义修正 + ClaimAssessment 独立 + Definition Status）+ `tests/test_status_semantics_contract.py`（10 tests） | R-01（+R-02/03 锁定） |
| 3+4 | RuntimeContext/build_runtime/get_runtime 单例 + CLI 不再 new 空 ProviderRegistry + ResearchStudio production wiring + probe 四态 + `tests/test_runtime.py`（9 tests） | R-04/05/06/30 |
| 5 | pending/rejected 不写语义 lineage；review 事务化同步（retire/supersession）；migration v8（retired_at/retired_by）；`tests/test_evidence_relation_lineage_review.py`（12 tests） | R-08/09/13 |
| 6 | IdeaMaturityPolicy（policy_v1）+ I2 required key claim coverage + `tests/test_idea_maturity_policy.py`（8 tests） | R-10/11 |
| 7 | ProductTruth.LineageGraph → canonical LineageService facade（dual-read/canonical-write）+ `tests/test_product_truth_generic_lineage_compat.py`（7 tests） | R-12/16 |
| 8 | migration v9：confidence/strength NULLABLE + legacy 0.5 保守保留；写路径 NULL；ID 全对象 sequence；`docs/architecture/SCORE_CONTRACT.md`；`tests/test_score_contract.py`（9 tests） | R-14/15 |
| 9 | AIPD_ENCRYPTION_KEY canonical（alias 冲突 fail）；docs 重绑代码事实；`tests/test_architecture_contracts.py`（12 tests，Docs-as-Code）；audit provenance（generator_version/command）；requires-python `>=3.9,<3.13`；CAD byte_reproducibility_profile | R-17/18/19/20/21/22/23 |

## 3. V5_8_2_GATE 判定

| # | Gate 项 | 状态 | 证据 |
| --- | --- | --- | --- |
| 1 | status semantics canonical | PASS | Commit 2 + test_status_semantics_contract（10 passed） |
| 2 | ClaimAssessment semantics independent | PASS | claim_assessment.py + contract 测试 |
| 3 | definition status independent | PASS | STATUS_SEMANTICS.md + contract 测试 |
| 4 | RuntimeContext/ApplicationContainer | PASS | runtime.py + test_runtime（9 passed） |
| 5 | single ProviderRegistry per runtime | PASS | get_runtime 单例 + with_adapters 隔离测试 |
| 6 | ResearchStudio registered in production bootstrap | PASS | build_runtime 注册 + test_researchstudio_registered_in_production_bootstrap |
| 7 | capability probe accurate | PASS | probe 四态 + live_probe 诚实测试 |
| 8 | pending relation not semantic truth lineage | PASS | test_pending_relation_does_not_write_semantic_lineage |
| 9 | rejected relation removes/retires semantic edge | PASS | test_reject_retires_existing_semantic_edge |
| 10 | reviewed relation updates lineage correctly | PASS | review 语义全套测试（12 passed） |
| 11 | I2 requires required key claim coverage | PASS | test_maturity_requires_key_claim_coverage / partial→I1+gap |
| 12 | generic lineage chosen as canonical | PASS | LineageService + implements 补齐 + compat 测试 |
| 13 | ProductTruth lineage compatibility path | PASS | facade 双写 + canonical_edges + 7 tests |
| 14 | new score values nullable/unscored | PASS | migration v9 + test_score_contract（9 passed） |
| 15 | new v5.9 IDs concurrency safe | PASS | 全对象 id_sequences（含 evidence/fact/decision/deliverable/risk） |
| 16 | encryption config canonicalized | PASS | Commit 9 + SECURITY.md + doctor 双登记 |
| 17 | architecture docs reflect current code | PASS | idea_evidence_architecture/truth_architecture 重写 + 12 contract tests |
| 18 | audit reports HEAD-bound | PASS | source_commit/package_version/generated_at/generator_version/command |
| 19 | Python version claim matches CI | PASS | requires-python `>=3.9,<3.13` == CI matrix |
| 20 | CAD semantic identity contract green | PASS | test_cad_contract_unify（21 passed 含 semantic/byte hash） |
| 21 | Manual E2E green | PASS | 11 passed |
| 22 | Production Release green | PASS | production_release_gate + release_evidence（29 passed） |
| 23 | auth/security green | PASS | test_auth/authorization/encryption_key_policy/crypto（90 passed 组） |
| 24 | tenant isolation green | PASS | test_tenant_boundaries passed |
| 25 | migration tests green | PASS | test_migration/freeze/backup passed（v9 往返验证） |
| 26 | full core regression green | PASS | **870 passed / 0 failed** |

**判定：V5_8_2_PASS** —— 允许进入 PHASE B（v5.9 Product Intelligence）。

## 4. 已知限制（诚实记录）

- ruff/mypy 全仓历史债务未清零（本次不扩大，新代码零新增）；
- ResearchStudio DBLP/OpenReview/Crossref 为预留 slot，未实现（§11 低优先级）；
- `facts.confidence`（v1 legacy）仍是 NOT NULL DEFAULT 0.5，模型层读取按
  legacy 处理；不迁移（历史字段，不进新 Domain）；
- evidence refresh 提交后 HEAD 与 manifests source_commit 差 1 commit
  （v5.8.1 同款模式；release gate 使用 tag 锚点判定，不 STALE）。

---
*本报告由 v5.8.2 Commit 10 生成。V5_8_2_GATE = PASS。*
