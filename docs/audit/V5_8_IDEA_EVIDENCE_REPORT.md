# AIPD-OS v5.8 Idea & Evidence Foundation Report

> 生成时间：2026-08-12（团队交付：software-engineer ×2 + software-qa-engineer）
> 前置：v5.7 Foundation Gate **PASS**（见 V5_7_FOUNDATION_CLOSURE.md），v5.8 据此解锁。
> 本报告是 v5.8 Idea & Evidence Foundation 的正式交付物，所有数字来自真实执行。

---

## 1. Current HEAD

| 项 | 值 |
|---|---|
| HEAD SHA | `9ded1e85ce38fdf49753259eb49b2f4c15c2cff2` |
| 分支 | `main`（与 origin/main 同步） |
| package version | `5.6.0`（v5.7/v5.8 为 [Unreleased]，版本推进待 release 提交时执行） |
| 最近 tag | `v5.6.0` → `66a735f7`（immutable 未动） |
| python / cadquery | 3.9.6 / 2.5.2 |

## 2. v5.8 交付（Commit 9-16）

### Idea Domain（Commit 9）
- `src/aipd_os/idea/`：models.py（Idea 全字段）/ service.py（CRUD，tenant+project scoped + audited + version_no 乐观锁）/ maturity.py / decomposer.py（骨架起，Commit 12 完整化）/ projections.py（骨架起，Commit 14 完整化）。
- migration v2（ideas 表，up/down 齐）；db.py SCHEMA 幂等同步。
- 复用 canonical evidence 表，未建第二 truth source。

### Claim Domain（Commit 10）
- claims.py：CLAIM_TYPES 11 类（problem/user/behavior/mechanism/technology/product/market/business/safety/regulatory/engineering）；`DEFAULT_EPISTEMIC_STATUS="A"`（初始 Candidate Claim 为 Assumption，**绝不默认 V**）；epistemic_status ∈ FACT_STATUSES（含 U）。
- claim_service.py：_ensure_idea_in_scope 强制同 scope；migration v3（claims 表，默认 'A'）。
- 软引用 idea_id（不强外键，迁移简洁）。

### EvidenceRelation + Evidence Graph（Commit 11）
- evidence_relations.py：RELATION_TYPES 五值（supports/contradicts/partially_supports/inconclusive/not_applicable）；`EvidenceRelationScopeError`；_ensure_evidence_in_scope 查询 canonical evidence 表——**无第二 truth source**；跨 project/tenant link 拒绝。
- evidence_graph.py：get_claim / get_claim_evidence / get_supporting_evidence / get_contradicting_evidence / get_inconclusive_evidence / get_unknown_claims / get_evidence_gaps / get_idea_evidence_summary，全部 tenant+project scoped。
- migration v4（claim_evidence_relations 表，UNIQUE 含 scope）。

### IdeaDecomposer Provider 抽象（Commit 12）
- decomposer.py（291 行）：raw prompt → StructuredCandidate → jsonschema（Draft7Validator）validation → normalize → persist（IdeaService.create + ClaimService.create，Claims 默认 A）→ audit。
- `IdeaDecompositionProvider` 抽象 + ProviderRegistry 注册 capability `idea.decompose`（capability 架构对齐）。
- 无 provider → `IdeaDecompositionUnavailable`（CAPABILITY_UNAVAILABLE）不写 DB；校验失败 → `IdeaDecompositionValidationError`（FAILED_VALIDATION）不落库。
- Fake/Broken provider 在 tests/fixtures/idea/，不进 runtime 路径。
- Candidate Claims 是「待验证命题」，绝非产品事实。

### Research 集成契约（Commit 13）
- **ResearchStudio 真实检查：不存在**（ls/find /Volumes/Extra/CodeProj/ 确认）→ 只实现 Provider contract，不伪造 integration。
- research_provider.py：RESEARCH_CAPABILITIES 6 个（research.academic_search / fulltext / related_work / novelty_check / idea_spark / asset_extract）。
- ResearchToolAdapter 适配 ToolAdapter → AdapterRegistry → ExecutionRouter 路由（依赖 capability 不依赖 provider 名）。
- ResearchIntegration：Claim evidence gap → EvidenceRequest → router.run → canonical evidence → EvidenceRelationService.add → EvidenceGraph 可查；无 provider → external_blocked 不写 evidence，不模拟成功。
- 既有 research.search_papers（Semantic Scholar）保留兼容。

### Idea Truth + Maturity（Commit 14）
- projections.py（127 行）：IdeaTruthProjection = 查询组合（known/assumption/evidence/contradicted/unknown/gaps/maturity），**非第二 Store**（无 CREATE TABLE）；IdeaTruthSnapshot frozen 不可变，JSON 可序列化。
- maturity.py（58 行）：I0_RAW_IDEA / I1_STRUCTURED_IDEA / I2_EVIDENCE_BACKED_IDEA 确定性判定（无 claims→I0；有真实 evidence→I2；否则 I1）；I3 仅 contract。
- Supervisor S0-S8 编号未改（正交维度：S0 承载 I0→I1、S1 承载 I1→I2，仅文档映射）。

### CLI + Golden E2E（Commit 15）
- `aipd intake`：建 Raw Idea I0；无 provider 诚实 decompose_status=CAPABILITY_UNAVAILABLE。
- `aipd status`：有 idea 时输出 maturity/Claims total/Supporting/Contradicting/Unknown/Evidence gaps/Blocked capabilities；无 idea 时旧输出兼容；保留 --json。
- Golden E2E：tests/golden/idea_to_evidence/（prompt + fake fixtures + README 标注 EPISTEMIC_NOTE「非真实医学事实，仅测试用」）。

### Docs / Manifests（Commit 16）
- docs/architecture/idea_evidence_architecture.md（68 行，调用链/域对象表/Provider 架构/诚实性护栏）。
- truth_architecture.md 增补 Idea Truth projection 语义。
- RE_AUDIT_LATEST_HEAD.md 附录 C（v5.8 增量审计）。
- SOURCE/PROVENANCE/BUNDLE_MANIFEST/pytest-report 重生成绑定 HEAD（BUNDLE 285 条目，含 11 个 idea/ 文件，0 垃圾）。

## 3. v5.8 Gate 判定

### 逐项清单（27 项，QA 独立判定）

```
[✅] v5.7 Foundation Gate PASS          [✅] Idea canonical object
[✅] Claim canonical object             [✅] evidence 复用 canonical store（无 evidence_v2）
[✅] EvidenceRelation implemented       [✅] Idea Truth projection（非第二 Store）
[✅] I0/I1/I2 maturity                  [✅] IdeaDecomposer provider abstraction
[✅] structured validation             [✅] no provider → honest unavailable
[✅] Research via ExecutionRouter       [✅] no simulated success
[✅] contradictions visible            [✅] Unknown preserved
[✅] tenant/project isolation           [✅] migration
[✅] restore                            [✅] audit
[✅] lineage                            [✅] CLI/Owner status
[✅] golden E2E                         [✅] Manual regression green
[✅] CAD regression green              [✅] Production Release green
[✅] security tests green              [✅] repo hygiene green
[✅] current HEAD audit fresh
```

### 总体：**V5_8_IDEA_EVIDENCE_PASS**

无 HOLD 项；QA 独立核验全部 Commit 9-16 真实生效（含直接探针：跨 scope link 拒绝、无 provider 0 落库、非法输出 0 落库、tenant 隔离 IdeaNotFoundError、router blocked_external 不写 evidence）。

## 4. Tests（真实数字，QA 独立实测）

| 套件 | 数字 |
|---|---|
| 全量回归 `-m "not model_eval"` | **711 passed / 0 failed / 2 skipped / 2 deselected（715 collected）** |
| integration | 15 passed / 2 skipped / 698 deselected |
| smoke + manual_e2e + release_gate | 15 passed（4+1+10） |
| cad_golden_loop + cad_contract_unify | 20 passed（真实 CadQuery 2.5.2） |
| v5.8 新增测试（7 文件） | 54 passed 无 skip |
| security 套件（tenant/authorization/mcp/truth） | 36 passed |
| prompt_injection / lineage / hygiene | 11 / 4 / 5 passed |

## 5. 剩余风险（不隐瞒）

1. 静态质量存量欠债（ruff ~3090 / mypy ~138）——非 CI 门禁。
2. 远端 CI（GitHub Actions）未实跑；python-core-matrix（3.9-3.12）需 push 验证。
3. 证据绑定 HEAD `9ded1e8` 但工作树未提交；正式 release 前需在最终 commit 重跑 release_evidence.py。
4. bundle 内嵌 RELEASE_MANIFEST 为 26 字节 stub（P2 观察，延续 v5.7，未修复）——发布前应内嵌完整清单。
5. IdeaDecomposer 真实 LLM provider 未接（仅 contract + Fake 测试）——生产使用需配置 provider 或外部能力。
6. ResearchStudio 不存在——research.academic_search 等 6 个 capability 均为 contract + external_dependency，无真实执行后端。

## 6. Next Plan（v5.9，仅计划不实现）

**Evidence → Insight → Opportunity → Product Principle → Requirement → Feature**

- 关键能力：Product Translator。
- 任何 Product Principle 反向可追溯：EvidenceRelation → Evidence → Source。
- 任何 Feature 追溯：Requirement → Product Principle → Evidence。
- 建立 Product Definition Gate：Gate 前 EXPLORE/CREATE，Gate 后 COMMIT/ENGINEER；Gate 后才允许 Product Truth / Engineering Baseline / CAD 成为冻结工程事实。
- 本轮不做：完整 Opportunity Engine / 完整 Product Translator / 完整 Requirement generation / UI generator / 大型前端重构。
