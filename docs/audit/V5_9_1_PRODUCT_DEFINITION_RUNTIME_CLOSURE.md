# V5_9_1 PRODUCT_DEFINITION_RUNTIME_CLOSURE

生成日期：2026-08-12
阶段：v5.9.1 Product Definition Integrity & Runtime Closure
结论：**V5_9_1_PASS**

---

## 1. Source Identity

| 项 | 值 |
|---|---|
| HEAD（baseline） | `3a98538`（v5.6.0-28-g3a98538） |
| 新增 commit | `2d0822a` 起（Change Set 1-9，见 §11） |
| package version | 5.6.0（v5.9.1 为 workstream 名，非 semver release，§56） |
| Python | pyproject `>=3.9,<3.13`（不变） |

## 2. 目标与判定（§80）

v5.9.1 的目标不是"增加更多 Product Intelligence 功能"，而是让 Product
Definition 从"对象存在"升级为"**运行时真实可执行、决策绑定、事务安全、
可审计、可追溯、可冻结**"。六条核心区分全部落实并有测试锁定：

| 原则 | 落实 |
|---|---|
| Candidate ≠ Committed | Provider 输出恒为 candidate；只有 Owner/Gate 批准 snapshot 才 commit（Runtime E2E） |
| Approval ≠ Verification | trust_level 按 epistemic + verification_test_refs 推导；approve 不自动 verified（integrity tests） |
| Live Projection ≠ Frozen Snapshot | Projection 是 live view；Snapshot 是 immutable 冻结（id+version refs + content_hash） |
| Historical Decision ≠ Current Authorization | get_effective_decision 最新 resolved 为准；旧 approve 不授权新 snapshot |
| Exception = No Partial Mutation | 所有 PI 写路径事务化（validate → mutate → reconcile → audit 单事务） |
| Capability Declared ≠ Capability Available | probe 四态；provider 缺失 → EXTERNAL_DEPENDENCY（绝不 fake success） |

## 3. Architecture Changes

- **migration v11**（`product_definition_integrity`）：`opportunities.selection_status`
  （显式选择）、`decisions.metadata_json`（snapshot 绑定/waiver/决策版本）、
  `product_definition_snapshots`（immutable 冻结）、`gate_evaluations`
  （结构化评估落库）；旧库升级数据保留；down 可回滚。
- **`AIPDStateDB.transaction()`**：显式 BEGIN/COMMIT/ROLLBACK + SAVEPOINT 嵌套；
  `connect()` 事务内复用活动连接 —— 所有既有 helper 自动获得事务性
  （修复历史 add_edge→add_audit 自死锁类问题）。
- **`product_intelligence/snapshot.py`**（新）：immutable
  ProductDefinitionSnapshot（INSERT only；SHA-256 canonical hash 覆盖
  id+version；stale 检测：opportunity 选择/version/冲突集合漂移）。
- **`product_intelligence/gate.py`**（重写）：GateEvaluation 结构化输出
  （hard_blockers/conditional_blockers/warnings/information/criteria_results）；
  技术评估（12 criteria）+ Authorization（APPROVED/REJECTED/PENDING/
  APPROVED_WITH_WAIVER）+ Commit Eligibility 三层分离。
- **`product_intelligence/provider.py`**（新）：ProductIntelligenceProvider
  ABC + typed candidates + GenerationProvenance + schema validation
  （不绑定模型供应商；无第二套 LLM client）。
- **`tool_adapters/product_adapters.py`**（新）：7 个 product.* adapters
  （5 生成类 provider-backed + create_snapshot/definition_gate 本地确定性）。
- **`cli/product_commands.py`**（新，§67）：product show/gate 拆出 commands.py；
  snapshot/technical/authorization/eligibility + `--json`。
- **runtime.py**：production bootstrap 注册 product adapters（provider=None →
  诚实 EXTERNAL_DEPENDENCY）；probe 覆盖 product.* 四态。

## 4. Resolved Findings（P0-01..P0-12 全 RESOLVED）

详见 `V5_9_1_RE_AUDIT_MATRIX.md`（每项附 source/function/reproduction/test/action）。
- P0-01 0 contradiction = information（非 blocker）
- P0-02/03 decision 绑定 snapshot_id+hash；latest resolved 为准
- P0-04 CONDITIONAL 需 APPROVE_WITH_WAIVER（waiver 结构化记录）
- P0-05/06/18/20 事务化 update + lineage reconcile（先校验后 mutate）
- P0-07 Opportunity 显式 selection（单 selected 约束）
- P0-08 approval ≠ verified（trust 按真实来源推导）
- P0-09/10/37/38 Provider contract + 7 capability 注册 + 动态四态
- P0-11/12 RuntimeContext 统一 + Supervisor S2 真实执行链

## 5. Remaining Findings

- 生产 ProductIntelligenceProvider 未接入（contract + hook 就绪；接入真实
  模型供应商后 probe 自动变 AVAILABLE —— 诚实 EXTERNAL_DEPENDENCY 现状）。
- ChangeRequest 经 ProductTruth propagation（stale+rework）表达，无独立表。
- ruff/mypy 历史债务未清零（本轮**新代码 0 新增**；registry_data E501 文件级
  豁免为声明式数据文件既有风格）。
- Release evidence 绑定测试 HEAD（tag 锚点模式，evidence refresh commit 差 1
  不 STALE，与 v5.8.1/v5.9 一致）。

## 6. Migration

- v11 增列/建表均幂等；`test_migration_freeze`（旧库→latest 数据保留）、
  `test_idea_domain`（rollback v11→v10 还原）、`test_score_contract`、
  `test_migration_backup`、`test_backup_checkpoint` 全绿（28 passed）。

## 7. Runtime Wiring（§3 最终数据流）

已真实运行（Runtime Golden E2E，tests/test_product_intelligence_runtime_e2e.py）：

```
Idea I2 → Supervisor S2 → ExecutionRouter → ProductAdapter →
FakeProductIntelligenceProvider（tests-only）→ candidate Insights →
Opportunity → Principles → Requirements → Features → ProductDefinitionSnapshot
→ Technical Gate → Owner Decision → Commit Eligibility → ProductTruth
```

所有阶段由 Supervisor/ExecutionRouter 真实触发（work items complete），
测试代码不直接 create（除 A-H 决策场景的 Domain 层驱动）。

## 8. Capability Matrix（§37/64）

| capability | adapter | provider req | probe（无 provider） | tests |
|---|---|---|---|---|
| product.derive_insights | ProductDeriveInsightsAdapter | yes | EXTERNAL_DEPENDENCY | runtime/integrity |
| product.identify_opportunity | ProductIdentifyOpportunityAdapter | yes | EXTERNAL_DEPENDENCY | runtime/integrity |
| product.derive_principles | ProductDerivePrinciplesAdapter | yes | EXTERNAL_DEPENDENCY | runtime/integrity |
| product.derive_requirements | ProductDeriveRequirementsAdapter | yes | EXTERNAL_DEPENDENCY | runtime/integrity |
| product.derive_features | ProductDeriveFeaturesAdapter | yes | EXTERNAL_DEPENDENCY | runtime/integrity |
| product.create_snapshot | ProductCreateSnapshotAdapter | no（本地） | AVAILABLE | runtime/integrity |
| product.definition_gate | ProductDefinitionGateAdapter | no（本地确定性） | AVAILABLE | runtime/integrity |

## 9. Gate / Decision / Transaction / Lineage / Security 语义

- **Gate**：technical（READY/CONDITIONAL/BLOCKED）+ authorization +
  eligibility；0 contradiction 不触发 CONDITIONAL；BLOCKED 永不 commit。
- **Decision**：绑定 snapshot_id+content_hash+gate_evaluation_id；
  latest reject 覆盖旧 approve；历史保留（audit 可见）；旧 approve 不授权
  新 snapshot；snapshot 变化 → stale → 旧审批失效。
- **Transaction**：validate → optimistic lock → mutate → lineage reconcile →
  audit 单事务；跨 project/乐观锁/audit 失败/lineage 失败全部回滚（对象 +
  lineage + audit 一致，测试锁定）。
- **Lineage**：desired vs current diff → retire old（历史保留）+ add new；
  active trace 只用 active 边；幂等。
- **Security**：snapshot/gate_evaluation/decision/ProductTruth 全部
  tenant+project scoped；跨 scope 引用拒绝且无残留（测试锁定）。

## 10. Tests

| 集合 | 结果 |
|---|---|
| 全量核心 `-m "not model_eval"` | **944 passed / 0 failed / 3 skipped / 2 deselected**（release evidence 刷新后全绿） |
| 新增测试 | test_product_definition_integrity(32) + runtime_e2e(13) + security(5) = 50 |
| 更新测试 | PI(21) / golden_e2e(6) / supervisor / CLI / migration 断言迁移到新语义 |
| ruff/mypy | 新增模块双 clean；commands.py 19=19、db.py 122<133（无新增债务） |

## 11. Commits（Change Sets）

1. `2d0822a` baseline + re-audit matrix
2. `20623a6` migration v11 + transaction API + decision metadata
3. `9aa1f82` snapshot + structured gate + decision binding + transactional service
4. `38c8e88` integrity contract tests（32）+ 旧测试迁移
5. `5ec0e90` provider contract + product adapters + capability catalog
6. `68f80ea` Supervisor S2 chain + Runtime Golden E2E（13）
7. `7cf7815` CLI product commands（show/gate UX + --json）
8. `ef190cd` security/tenant regression（5）
9. （最终）release evidence 刷新

## 12. Known Limitations（诚实记录）

- 生产 Provider 未接入（现状：EXTERNAL_DEPENDENCY，不伪造）。
- Golden fixture 非医学证明（epistemic_note 保留）。
- ChangeRequest 无独立表（走 propagation）。
- 历史 ruff/mypy 债务未清零。

## 13. Release Readiness

- **V5_9_1_PASS**：DoD（§74）逐项满足（0-contradiction 不 CONDITIONAL /
  结构化 criteria / immutable snapshot + deterministic hash + stale /
  decision 绑定 / latest-reject / 旧 approve 不授权新 snapshot / CONDITIONAL
  需 waiver / BLOCKED 永不 commit / update 先校验后 mutate / 失败全回滚 /
  lineage 事务化 + retire / Opportunity 显式选择 / approval ≠ verified /
  exact snapshot commit / Provider contract / adapters / capability 注册 /
  动态可用性 / 缺 provider 诚实 / RuntimeContext 共享 / Supervisor S2 可执行 /
  Runtime Golden E2E / Feature→Evidence trace / Snapshot→Decision→Truth trace /
  跨 scope 拒绝回滚 / tenant 隔离 / migration / backup-restore / 各域回归）。
- HOLD 条件（§75）逐项核查无命中。

**READY_FOR_V5_10_NPI**

## 14. v5.10 所需接口清单（§78，为 Manufacturing Readiness / NPI 准备）

| 接口 | 现状 | v5.10 动作 |
|---|---|---|
| Requirement | 已就绪（NPI-ready 字段：nominal/unit/limits/tolerance/test_condition/verification/derivation/affected_item_refs/required_by_gate，§70） | 接入 Manufacturing Projection |
| BOM | 无独立表（MMD crosswalk 标记待 schema extension） | migration + service + lineage |
| Supplier | 有 supply_chain 相关（mail_rfq adapter / supplier_adapter） | 完善 canonical 表 + scope 校验 |
| Cost | 无 | migration + service |
| ValidationTest | 无（requirement.verification_test_refs 为引用占位） | migration + lineage |
| Risk | 已有 risks 表 | 接入 NPI 链 |
| Issue | 无（change_request 经 propagation） | 决策：独立表或复用 changes |
| Decision | 已就绪（metadata_json + get_effective_decision 模式可复用） | 新 topic + snapshot 绑定复用 |
| Change | 已有 changes 表 | 与 propagation 打通 |
| Gate | 已就绪（GateEvaluation 结构化 + authorization + eligibility 分层） | 新 gate 类型复用同一模式 |
| Generic Lineage | 已就绪（node_type 扩展 + retire/reconcile + canonical 单一存储） | 连接 BOM/Supplier/Validation/MMD/MRL 节点 |
| MMDProjection | 仅 crosswalk 文档（Manufacturing Projection 原则已定） | 实现投影 + 导入/导出 |
| Manufacturing Readiness | production_release_gate 存在（CAD 域） | 与 Product Truth / NPI Gate 打通 |
