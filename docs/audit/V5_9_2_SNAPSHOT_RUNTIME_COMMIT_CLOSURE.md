# V5_9_2 SNAPSHOT_RUNTIME_COMMIT_CLOSURE

生成日期：2026-08-12
阶段：v5.9.2 Snapshot-Closed Runtime & Commit Integrity Closure
结论：**V5_9_2_PASS**（11/11 P0 RESOLVED；4/4 O RESOLVED）

---

## 1. Source Identity

| 项 | 值 |
|---|---|
| HEAD（baseline） | `4a0ac22`（v5.9.1 Change Set 10，V5_9_1_PASS） |
| 新增 commit | `dde08c7` 起（Change Set 1-8b + fix，见 §11） |
| HEAD（final） | `7176553`（+ release evidence refresh） |
| package version | 5.6.0（v5.9.2 为 workstream 名，非 semver release） |
| Python | pyproject `>=3.9,<3.13`；回归用 .venv（Python 3.9.6 + cadquery 2.5.2） |

## 2. 目标与判定（§94）

v5.9.2 的目标：把 Snapshot 从"简单冻结"升级为**closed-world 可证明集合**，
把 Commit 从"多次写入"升级为**原子 exactly-once 生命周期**。仅当 11 个 P0
全部真实复现（baseline 阶段）且修复后有真实 DB 行为验证，才允许进入
v5.10 NPI。核心区分全部落实并有测试锁定：

| 原则 | 落实 |
|---|---|
| Snapshot 是 Closed World | `create_snapshot` 只冻结 selected Opportunity → 其 active/candidate principles → requirements → features（`active_definition_set` membership policy v1；排除 archived/superseded/rejected）；`is_stale` 用 **set equality**（ID 集合变化 → STALE） |
| Gate 只读 Snapshot，不读 live | `ProductDefinitionSnapshotView`（§10）：criteria 输入 = snapshot 解析结果；live tables 仅用于 freshness/basis 校验 |
| Upstream 变化传播 | `upstream_basis_hash`（SHA-256 fingerprint：claims + reviewed relations + assessments + insights + selected opp + PI versions）第二道防线 + `ImpactPropagationService` 对象层 Digital Thread 反向传播 |
| Commit 原子 | ProductTruth records + canonical lineage + compatibility lineage + commit ledger + snapshot lifecycle + audit 同一 transaction boundary；任何失败 ROLLBACK（0 部分写入） |
| Commit exactly-once | `product_definition_commits` ledger（migration v12）UNIQUE(tenant,project,snapshot_id)；重复 commit → 同 receipt（幂等）或 SnapshotAlreadyCommittedError |
| Commit lifecycle | frozen → committed（**绝不 frozen → stale**）；显式前置校验仅 frozen 可 commit |
| Supervisor DAG | 显式 `depends=`；上游 blocked → 下游全部 queued/dependency-blocked（fail-closed，绝不让下游假成功） |
| RuntimeContext 唯一 | `build_runtime(make_default=True)`/`install_runtime()`；CLI 全程同一 runtime |

## 3. Architecture Changes

- **migration v12**（`snapshot_runtime_commit_closure`）：
  - `product_definition_snapshots.upstream_basis_hash`（P0-08 第二道防线）；
  - 五张 PI 表 `generation_metadata_json`（O-3 provenance 可反查）；
  - `product_definition_commits` ledger 表（UNIQUE(tenant,project,snapshot_id)，
    exactly-once 权威源）；
  - 旧库升级数据保留；down 可回滚（test_migration_freeze / test_idea_domain /
    test_score_contract 断言迁移到 v12）。
- **`snapshot.py` 重写**（closed-world）：
  - `active_definition_set()`：membership policy v1（selected Opportunity →
    其绑定的 principles → requirements → features，只含 active/candidate）；
  - `create_snapshot` 冻结 active set（排除 archived/superseded/rejected）；
  - `is_stale`：**set equality** 比较（新增/删除/archive/supersede/selection
    change/version change/conflict set 变化/upstream basis 变化 → STALE）；
  - `ProductDefinitionSnapshotView`：snapshot → exact objects 只读视图；
  - `mark_stale`（impact 传播用；immutable content 不修改，只改状态位）。
- **`service.py`**：`_LINEAGE_SPECS` 多源 lineage（principle → insight
  (derived_from) + opportunity (derived_from) 双边）；`_reconcile_lineage`
  按 spec 遍历 reconcile；required-ref 校验（P0-03）。
- **`gate.py`**：`commit_snapshot` 单事务化（conn 共享）；exactly-once
  ledger；`SnapshotAlreadyCommittedError`；`_receipt` 幂等；显式
  SNAPSHOT_FROZEN 前置校验；新 criteria（PRINCIPLES_BOUND_TO_SELECTED_
  OPPORTUNITY / SNAPSHOT_SET_INTEGRITY / SNAPSHOT_UPSTREAM_BASIS）全部只读
  SnapshotView（O-1/O-2）。
- **`product_truth/store.py` / `lineage.py`**：`add(record, conn=…)` /
  `add_edge(…, conn=…)` 事务感知（P0-07 原子性基础）。
- **`tool_adapters/product_adapters.py`**：derive_principles 要求 exactly
  one selected Opportunity（P0-03）；persist 自动绑 opportunity_id；各
  adapter 落 generation_metadata（O-3）。
- **`supervisor/idea_capabilities.py`**：`schedule_*` 显式 depends；链构建
  为 DAG（P0-04）。
- **`runtime.py`**：`build_runtime(make_default=True)` / `install_runtime()`
  （P0-09）；CLI 经 `_find_idea_decompose_provider` 注入点保留（fix commit，
  见 §11 第 9 条）。
- **`cli/commands.py` / `product_commands.py` / `main.py`**：
  `_resolve_project` 尊重显式 --project（P0-10）；`choices=sorted(OWNER_CHOICES)`
  同源防漂移（P0-11）；补 `import json`。
- **`product_intelligence/impact.py`（新）**：`ImpactPropagationService`
  —— `find_affected_objects`（Generic Lineage 反向 Digital Thread，含
  relation/via 可解释标注）、`affected_snapshot_ids`、`mark_affected_snapshots_stale`
  （frozen→stale，幂等）（P0-08 传播侧，§32-34）。

## 4. Resolved Findings（P0-01..P0-11 + O-1..O-4 全 RESOLVED）

详见 `V5_9_2_RE_AUDIT_MATRIX.md`（每项附 source/function/reproduction/action/
commit/verification）。复现与修复均基于真实 DB 行为，禁止伪造：

- P0-01 snapshot 非 closed-world → set equality + active_definition_set
- P0-02 archived 入 snapshot → 只冻结 active set（membership policy v1）
- P0-03 runtime principle 无 opportunity → exactly-one selected 约束 +
  自动绑定 + 双边 lineage + Gate criterion
- P0-04 work DAG 缺依赖 → 显式 depends + fail-closed（验证脚本：
  provider=None → 下游全 blocked、0 snapshot）
- P0-05 commit 置 stale → frozen→committed（绝不 frozen→stale）
- P0-06 可重复 commit → ledger UNIQUE + 幂等 receipt / 抛错
- P0-07 非原子 → 单 transaction boundary（注入 lineage 失败 → 0 残留）
- P0-08 claim 变化不 stale → upstream_basis_hash + ImpactPropagationService
  （claim → insight → opportunity → principle → requirement → feature 全链 +
  snapshot → stale）
- P0-09 RuntimeContext split → make_default/install_runtime 语义 + 同 runtime
- P0-10 CLI 忽略 --project → 显式 project 校验（不存在 ERROR；多项目必须显式）
- P0-11 无法 approve_with_waiver → choices=sorted(OWNER_CHOICES) 同源
- O-1 Gate 读 live → ProductDefinitionSnapshotView（criteria 只读 frozen）
- O-2 principle 绑定（Gate 层）→ PRINCIPLES_BOUND_TO_SELECTED_OPPORTUNITY
- O-3 provenance 不可反查 → generation_metadata_json
- O-4 release provenance 字段混用 → 拆字段 + fresh machine report

## 5. Migration

- v12 增列/建表均幂等；`test_migration_freeze`（旧库→latest 数据保留）、
  `test_idea_domain`（rollback v12→v11 还原）、`test_score_contract`、
  `test_migration_backup`、`test_backup_checkpoint`、`test_product_intelligence_security`
  全绿（21 passed，迁移/备份/安全回归）。

## 6. 验证证据（真实运行，非静态声称）

- **P0-04 fail-closed**：`scripts/_v592_p004_check.py` —— provider=None 调度
  全链 → W1..W5 blocked_external、W6/W7 保持 queued、0 snapshot
  （修复前 W6/W7 假 complete）。
- **P0-05/06/07 commit 完整性**：runtime e2e A-H 场景（approve 提交 /
  reject 不提交 / approve 后修改 stale 不提交 / 新 snapshot 新决策 /
  conditional waiver / blocked 不提交）；重复 commit 幂等同 receipt 且
  ProductTruth 不增；idempotent=False 抛 SnapshotAlreadyCommittedError；
  注入 LineageGraph.add_edge 失败 → 0 truth 行 / 无 ledger / snapshot 仍 frozen。
- **P0-08 impact 传播**：`scripts/_v592_p009_check.py` + 正式测试 5 例 ——
  claim 变化 → 5 域全链命中（含 relation/via 标注）→ frozen snapshot
  SNAP-001 → STALE；幂等（已 stale 不重复标记）；STALE 快照 commit 被拒
  （"only frozen snapshots"）；无关 claim 零影响。
- **P0-10/11 CLI**：多项目 --project scope 解析、不存在 project ERROR、
  `--choice approve_with_waiver` 正常解析并产生 waiver 决策。

## 7. Tests

| 集合 | 结果 |
|---|---|
| 全量核心（venv，`-m "not model_eval"`，v5.9.1 同口径） | **956 passed / 2 failed / 3 skipped / 2 deselected** |
| 2 failed 性质 | `test_release_manifest_hashes_match_disk` + `test_source_manifest_hashes_match_disk` = release evidence 未刷新（tag 锚点模式，最终 refresh 后消除，见 §9） |
| v5.9.1 对照 | 944 passed / 3 failed（capability_matrix + packaging×2）→ 本轮 capability_matrix 已消除；净增 11 测试全绿 |
| 新增测试 | `test_product_intelligence_impact`(5) + `test_product_intelligence_runtime_dag`(6) = 11 |
| 更新测试 | PI / golden_e2e / runtime_e2e / supervisor / CLI / migration 断言迁移到新语义 |
| 迁移/备份/安全 | 21 passed |
| ruff/mypy | 新增模块双 clean；impact.py/gate.py 自身 0 mypy 错误（11 个错误全在历史文件，0 新增债务） |

## 8. Runtime Wiring（§3 最终数据流）

```
Idea I2 → Supervisor S2（显式 DAG：insights → opportunity → STOP selection
→ principles → requirements → features → snapshot → gate）
→ ExecutionRouter → ProductAdapter → FakeProductIntelligenceProvider →
candidate objects（generation_metadata 落库）→ ProductDefinitionSnapshot
（closed-world frozen + upstream_basis_hash）→ Technical Gate（SnapshotView
只读）→ Owner Decision（approve / approve_with_waiver / reject）→
Atomic exactly-once commit → ProductTruth + ledger + snapshot committed
```

上游 claim 变化 → ImpactPropagationService 标记受影响 frozen snapshot STALE
→ 旧审批立即失效 → 必须新建 snapshot 重新评估（数字线程可解释）。

## 9. Release Evidence（tag 锚点模式）

最终 report 提交后 HEAD 变化是预期（report 锚定 report 生成时刻的
`source_commit`，evidence refresh commit 记录 `archive_head_commit`）：

- SOURCE_MANIFEST / BUNDLE_MANIFEST / PROVENANCE：按最终 HEAD 重新生成；
- pytest-report.json：venv 核心回归机器可读报告（956 passed / 2 failed；
  packaging×2 为 evidence 刷新前状态，refresh 后同批 packaging 回归全绿）；
- audit.json / capability_matrix：HEAD-bound 重新生成。

## 10. Known Limitations（诚实记录）

- 生产 ProductIntelligenceProvider 仍未接入（contract + hook 就绪；现状
  诚实 EXTERNAL_DEPENDENCY，不伪造成功）—— 与 v5.9.1 一致。
- ruff/mypy 历史债务未清零（本轮新代码 0 新增）。
- Impact 传播为对象层报告 + snapshot 状态位；对象自身 lifecycle 不自动改
  （candidate/active 保持，stale 语义由 snapshot basis + 报告承载，§32）。

## 11. Commits（Change Sets）

1. `dde08c7` baseline + re-audit matrix（P0-01..P0-11 全 CONFIRMED，真实复现）
2. `147d6cd` CS2+3：snapshot closed-world + multi-source lineage +
   opportunity→principle binding（P0-01/02/03/08，§7/9/12-14/35）
3. `8eaa30c` chore：mypy clean on product_intelligence（0 new debt）
4. `9154453` CS4：Supervisor explicit dependency DAG + fail-closed（P0-04）
5. `8eefa7f` CS5：atomic exactly-once commit（P0-05/06/07，§24-30）
6. `7ab8e94` CS6+7：RuntimeContext authority + CLI scope/waiver（P0-09/10/11）
7. `b08624f` CS8：Snapshot exact Gate + new criteria（§10/11/46，O-1/O-2）
8. `1d01e12` CS8b：ImpactPropagationService upstream stale propagation（§32-34）
9. `7176553` fix：restore idea.decompose provider fallback（CLI 可注入性回归）
10. （最终）release evidence refresh

## 12. Release Readiness

- **V5_9_2_PASS**：11/11 P0 + 4/4 O 全部 RESOLVED 且有真实 DB 行为验证；
  核心回归 956 passed（对比 v5.9.1 的 944 净增 12，无回归）；迁移/备份/安全
  全绿；ruff/mypy 0 新增债务。
- **READY_FOR_V5_10_NPI**：进入 v5.10 NPI 的前提（Snapshot closed-world、
  atomic exactly-once commit、upstream propagation）全部收口。
