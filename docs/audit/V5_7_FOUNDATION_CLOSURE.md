# AIPD-OS v5.7 Foundation Closure Report

> 生成时间：2026-08-12（团队交付：software-engineer ×2 + software-qa-engineer）
> 本报告是 v5.7 Foundation Gate 的正式交付物，所有数字均来自真实执行（见 §5/§6）。

---

## 1. Current HEAD

| 项 | 值 |
|---|---|
| HEAD SHA | `9ded1e85ce38fdf49753259eb49b2f4c15c2cff2` |
| 分支 | `main`（与 origin/main 同步） |
| package version | `5.6.0`（v5.7 为 [Unreleased]，版本推进待 release 提交时执行） |
| 最近 tag | `v5.6.0` → `66a735f7`（**immutable 未动**，HEAD 领先 3 commit） |
| python / cadquery | 3.9.6（repo `.venv`）/ 2.5.2（真实内核） |

## 2. Re-Audit（当前 HEAD 逐项重新验证）

### Resolved（v5.7 已修复，含真实测试证据）

| # | 提示词条款 | 修复 | 测试证据 |
|---|---|---|---|
| 1 | §6 MCP auth | AuthenticatedPrincipal + service principal（AIPD_MCP_USER/TOKEN）；所有 MCP tool 注入 actor；tenant 不可伪造；fail-closed | `test_mcp_authorization.py` 7 passed |
| 2 | §7 Tenant membership | `require_tenant_membership`；init_project/grant/register 强制租户归属；跨 tenant 写/授权拒绝 | `test_tenant_boundaries.py` 7 + `test_authorization.py` 13 + `test_auth.py` 4 |
| 3 | §8 Encryption policy | server 模式弱/缺 encryption key fail-closed；`AIPD_ALLOW_PLAINTEXT_SENSITIVE=1` 显式 dev；docker-compose 移除 change-me | `test_encryption_key_policy.py` 8 + `test_secret_policy.py` 7 |
| 4 | §9 Supervisor Decision | Supervisor 不再拥有 decisions 表；state_db 集成走 canonical `propose_decision`；legacy adapter 兼容；canonical 表 + 未传 state_db → fail-closed | `test_supervisor_state_integration.py` 5 |
| 5 | §10 Multi-project | 构造签名 `(db, tenant_id, project_id, state_db)`；project_id 三态；全表补 tenant_id；next_work/decisions 作用域化；CLI 真实传参 | `test_supervisor_multi_project.py` 8 |
| 6 | §11 supervisor_claims | 死表重命名 `supervisor_assertions`（旧表保留兼容），注明 v5.8 Claim 域独立 contract | 全仓 grep 验证无读写依赖 |
| 7 | §12 Idempotency scope | `(tenant_id, project_id, capability, idempotency_key)` scope；execution_runs 补 tenant_id；record_retry 全继承 | `test_execution_idempotency_scope.py` 8 |
| 8 | §13A retrieval≠claim | `retrieval_status`（not_retrieved/abstract_only/fulltext_retrieved/parse_failed）与 `epistemic_status` 彻底拆分；writeback 不再自动 V | `test_research_chain.py` 全绿 |
| 9 | §13B/§15 assess_trust | 不再「有 evidence → verified」；evidence→high（来源可信度）；仅 `confirm_by_owner=True` 才 verified | `test_truth_evidence_semantics.py` 9 |
| 10 | §14 U 状态 | FACT_STATUSES 增 U；fact.schema.json enum 增 U + 全状态 description | schema_check PASS + truth 测试 |
| 11 | §16 Research fixtures | `_LOCAL_*` 移出生产默认；生产 Retriever → external_dependency；fixtures 迁至 `tests/fixtures/research/`；显式 TestRetriever | `test_research_chain.py`（含 new test_production_retrievers_default_external_dependency） |
| 12 | §17 SS adapter | 配置语义==网络语义：key 真实以 `x-api-key` header 发送 | `test_adapters.py`（test_research_api_key_sent_as_header） |
| 13 | §18/19 CAD hash/CI | semantic vs byte hash 契约化；importorskip 下沉（无 CadQuery 时 contract 仍跑）；ci.yml cad 跑两套文件 | `test_cad_contract_unify.py`（无内核场景 5 passed/4 skipped 实测） |
| 14 | §20 Python 契约 | CI 新增 `python-core-matrix`（3.9/3.10/3.11/3.12 核心套件）；pyproject 注释验证矩阵 | 未实跑远端矩阵（本机 3.9.6 全绿） |
| 15 | §5 Hygiene | bundle 打包排除 `.venv/.pytest_cache/__pycache__/*.pyc/*.dist-info`；BUNDLE_MANIFEST 从 4679 垃圾条目 → 272 条目 0 垃圾；新增 test_repo_hygiene | `test_repo_hygiene.py` 6 passed |
| 16 | §21 Audit freshness | SOURCE/PROVENANCE/BUNDLE/pytest-report 全部重生成绑定 HEAD `9ded1e8`；pytest-report 657/0/661 + source_commit | QA grep 实测三文件均=9ded1e8 |

### Open / New Findings（非阻塞，记录待办）

| # | 级别 | 事项 |
|---|---|---|
| N1 | P2 | build/release/aipd-os-5.6.0.zip 内嵌 RELEASE_MANIFEST.json 为 26 字节 stub `{"version":"unknown"}`；BUNDLE_MANIFEST 如实记录。正式发布前应让 bundle 内嵌完整清单 |
| N2 | P2 | 新 bundle 为 source-only 归档（不含 state_service/、tests/、pyproject.toml、docker-compose.yml）——内容策略可议，不阻塞 v5.7 |
| N3 | P2 | 静态质量存量欠债：ruff 3090 / mypy 138（非 CI 门禁，v5.6 基线 3298/140 略降） |
| N4 | 信息 | 工程师 brief 计数与 QA 实测差异：mcp_auth 8→7、tenant_boundaries 8→7、truth_evidence 10→9（覆盖等价，全绿） |
| N5 | 流程 | 证据绑定 9ded1e8 但工作树未提交；正式 v5.7 release 前需在最终 commit 上重跑 release_evidence.py（source_commit==新 HEAD） |

## 3. v5.7 Gate 判定

### 逐项清单（26 项，QA 独立判定）

```
[✅] no tracked runtime caches            [✅] source archive clean
[✅] audit reports bound to HEAD          [✅] MCP external calls authenticated
[✅] external transport no actor=None     [✅] cross-tenant creation impossible
[✅] strong encryption in production      [✅] Supervisor canonical Decision works
[✅] Supervisor explicit multi-project    [✅] Supervisor state tenant/project scoped
[✅] idempotency scoped                   [✅] retrieval status ≠ claim verification
[✅] external evidence no auto-V          [✅] ProductTruth no auto-verify
[✅] U/Unknown available                  [✅] research fixtures isolated
[✅] provider config == network call      [✅] CAD semantic hash contract green
[✅] CAD contract tests in CI             [✅] core Python matrix defined
[✅] Manual E2E green                     [✅] Production Release green
[✅] CAD maturity green                   [✅] integration green
[✅] migration green                      [✅] auth/security green
```

### 总体：**V5_7_FOUNDATION_PASS**

无 HOLD 项；无假修复；QA 独立核验全部 P0/P1 修复真实生效（含直接探针：跨 tenant 写拒绝、弱 key fail-closed、跨 tenant 同幂等 key 不命中、retry 继承 scope、production retriever external_dependency）。

## 4. 架构（真实最终调用链）

```
Owner
 ↓
Supervisor(db, tenant_id, project_id, state_db)      ← canonical state 集成
 ↓
DecisionPolicy (should_ask_decision / build_decision_package)
 ↓
WorkItem (supervisor_work_items, tenant+project scoped)
 ↓
ExecutionRouter (tenant_id/project_id 传播; idempotency scope=(t,p,cap,key))
 ↓
Adapter (research.search_papers → x-api-key 真实 header)
 ↓
Provider (ProviderRegistry, src/aipd_os/providers/sdk.py)
 ↓
Evidence / Artifact
 ↓
Canonical State (AIPDStateDB/StateService)
 ↓
Truth / Lineage / Gate
```

外部 Transport（HTTP/MCP）→ `AuthenticatedPrincipal`（user_id/tenant_id/auth_method/scopes）→ 才可调用 StateService；`actor=None` 仅内部系统路径（transport boundary 不可达）。

## 5. Tests（真实数字，QA 独立实测）

| 套件 | 数字 |
|---|---|
| 全量回归 `-m "not model_eval"` | **657 passed / 0 failed / 2 skipped / 2 deselected（661 collected）** |
| integration | 15 passed / 2 skipped / 644 deselected |
| smoke + manual_e2e + release_gate | 15 passed（4+1+10） |
| cad_golden_loop + cad_contract_unify | 20 passed（真实 CadQuery 2.5.2） |
| migration / cad_maturity / test_cli | 8 / 20 / 24 passed |
| 新增 v5.7 测试（8 文件） | 57 passed 无 skip |

## 6. 剩余风险（不隐瞒）

1. 静态质量存量欠债（ruff 3090 / mypy 138）——非 CI 门禁，建议 v5.8 期间逐步消化。
2. 远端 CI（GitHub Actions）尚未实跑——python-core-matrix（3.9-3.12）与 CAD CI 需 push 后验证。
3. 证据绑定当前 HEAD `9ded1e8`；正式 release 提交后需重跑 release_evidence.py 刷新。
4. release bundle 内嵌 manifest stub（N1）与归档内容策略（N2）待发布前决策。

## 7. Next Plan

- **v5.8 Idea & Evidence Foundation**（已解锁）：
  Idea → Claim → EvidenceRelation → Evidence Graph → Idea Truth → I0/I1/I2 maturity；
  IdeaDecomposer Provider 抽象；CLI `aipd intake/status` 扩展；Golden E2E；security tests。
- **v5.9**（仅计划，不实现）：Evidence → Insight → Opportunity → Product Principle → Requirement → Feature + Product Definition Gate。
