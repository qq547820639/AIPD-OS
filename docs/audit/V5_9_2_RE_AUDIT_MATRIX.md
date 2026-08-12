# V5_9_2 Re-Audit Matrix（Snapshot-Closed Runtime & Commit Integrity Closure）

生成日期：2026-08-12（基线）／2026-08-12（最终更新）
基线 HEAD：`4a0ac22`（Change Set 1，未改代码前逐项复现）
状态枚举：CONFIRMED / PARTIALLY_RESOLVED / ALREADY_RESOLVED / NOT_REPRODUCED /
SUPERSEDED / REGRESSION
最终状态：**11/11 P0 RESOLVED，4/4 O RESOLVED**（验证见 `V5_9_2_SNAPSHOT_RUNTIME_COMMIT_CLOSURE.md`）

每项附：source file / function / reproduction（真实运行输出）/ action / 修复 commit / 验证。

## P0-01 Snapshot 不是 Closed World
- **状态**：**RESOLVED**（CS2+3 `147d6cd`）
- source：`src/aipd_os/product_intelligence/snapshot.py` `is_stale()`（只比较 refs 存在 + version）
- reproduction：`create snapshot(reqs=1) → add new Requirement → is_stale()=False`（live=2）
- action：stale 比较 **set equality**（active principle/requirement/feature ID 集合）；新增/删除/archive/supersede/selection change/version change 全部 STALE。
- 验证：`active_definition_set()`（membership policy v1）closed-world；`is_stale` set equality；`test_product_intelligence.py` closed-world 测试（新增/archive/supersede/selection 变化 → STALE）全绿。

## P0-02 archived object 被 Snapshot 收入
- **状态**：**RESOLVED**（CS2+3 `147d6cd`）
- source：`snapshot.py` `create_snapshot()`（refs = 全部 list_*，无 lifecycle 过滤）
- reproduction：`Requirement.lifecycle_status=archived → create_snapshot → archived req 进入 requirement_refs`
- action：`create_snapshot` 只冻结 active set（selected Opportunity → 其 principles → 其 requirements → 其 features；排除 archived/superseded/rejected）；建 `definition_membership_policy_v1`。
- 验证：frozen snapshot 仅含 active 对象（archived/superseded/rejected 排除）测试锁定。

## P0-03 Runtime Principle 没有 Opportunity
- **状态**：**RESOLVED**（CS2+3 `147d6cd`）
- source：`src/aipd_os/tool_adapters/product_adapters.py` `ProductDerivePrinciplesAdapter.execute()`（persist 时 `opportunity_id=input_.get("opportunity_id","")`，work item inputs 无此字段）
- reproduction：Runtime 生成后 `principle.opportunity_id=['','']`（Opportunity 存在 OPP-001）
- action：`derive_principles` 要求 exactly one selected Opportunity；provider context 只传 selected；adapter persist 自动绑 `opportunity_id=selected_id`；lineage 加 Opportunity→Principle 边（_LINEAGE_SPECS 多源）。
- 验证：runtime e2e 断言 principle.opportunity_id == selected id；gate criterion `PRINCIPLES_BOUND_TO_SELECTED_OPPORTUNITY`。

## P0-04 Product Work DAG 缺 dependencies
- **状态**：**RESOLVED**（CS4 `9154453`）
- source：`src/aipd_os/supervisor/idea_capabilities.py` `schedule_product_intelligence_chain()`（add_work 无 `depends=`）
- reproduction：provider=None 调度全链 → W1-W5 blocked_external，**W6 create_snapshot=complete、W7 definition_gate=complete**（下游未阻塞；snapshot 被创建）
- action：Supervisor 使用显式 `depends=[work_id]` DAG；上游 blocked → 下游全部 queued/dependency-blocked（fail-closed）。
- 验证：`scripts/_v592_p004_check.py` + runtime DAG 测试（6 tests）——provider=None 下游全 blocked、0 snapshot。

## P0-05 commit snapshot lifecycle 错误
- **状态**：**RESOLVED**（CS5 `8eefa7f` + CS8b `1d01e12`）
- source：`src/aipd_os/product_intelligence/gate.py` `commit_snapshot()`（尾部 UPDATE 置 `SNAPSHOT_STALE`）
- reproduction：`commit → snapshot.lifecycle_status='stale'`（系统已定义 SNAPSHOT_COMMITTED）
- action：commit 成功 → `frozen → committed`（绝不 frozen → stale）；commit 前置显式校验仅 frozen 可 commit。
- 验证：commit 后 lifecycle=committed；stale 快照 commit → RuntimeError("only frozen snapshots")（impact 测试锁定）。

## P0-06 Snapshot 可重复 commit
- **状态**：**RESOLVED**（CS5 `8eefa7f`）
- source：`gate.py` `commit_snapshot()`（无 exactly-once 保护）
- reproduction：`commit SNAP-001 两次 → 第二次成功 → duplicate ProductTruth`
- action：`product_definition_commits` 表（migration v12）UNIQUE(tenant,project,snapshot_id)；第二次 → 返回已有 receipt（幂等）或 SnapshotAlreadyCommitted。
- 验证：idempotent=True 同 receipt 且 ProductTruth 不增；idempotent=False 抛 SnapshotAlreadyCommittedError。

## P0-07 Commit 非原子
- **状态**：**RESOLVED**（CS5 `8eefa7f`）
- source：`gate.py` `commit_snapshot()`（ProductTruthStore.add 独立连接提交 → LineageGraph.add_edge 独立连接 → 失败残留）
- reproduction：注入 lineage failure → commit raises，**ProductTruth reqs=1 残留**（应为 0）
- action：ProductTruth records + canonical lineage + compatibility lineage + commit ledger + snapshot lifecycle + audit 进入**同一 transaction boundary**（复用 db.transaction + store.add(conn=...)）。
- 验证：注入 add_edge 失败 → 0 truth 行 / 无 ledger / snapshot 仍 frozen（原子性测试锁定）。

## P0-08 Upstream Claim 变化不会 stale Snapshot
- **状态**：**RESOLVED**（CS2+3 `147d6cd` basis hash + CS8b `1d01e12` ImpactPropagationService）
- source：`snapshot.py` `is_stale()`（只查 PI 对象，不查 upstream claims/relations）
- reproduction：`create snapshot → update Claim → is_stale()=False`
- action：snapshot 存 `upstream_basis_hash`（claim ids+versions / reviewed relation ids+versions+status / assessment / insight versions / selected opp / PI versions）；is_stale 同时校验 basis hash（第二道防线）+ ImpactPropagationService 传播。
- 验证：`scripts/_v592_p009_check.py` + `tests/test_product_intelligence_impact.py`（5 tests）：claim 变化 → insight→opportunity→principle→requirement→feature 全链命中，frozen snapshot → stale，幂等。

## P0-09 RuntimeContext split
- **状态**：**RESOLVED**（CS6+7 `7ab8e94`）
- source：`src/aipd_os/runtime.py` `build_runtime()`（默认不安装单例）；`get_runtime()` 自建
- reproduction：`r1=build_runtime(db_path=X); r2=get_runtime() → r1 is r2=False，不同 DB/adapters`
- action：`build_runtime(make_default=True)` / `install_runtime(runtime)` 语义明确；cmd_intake 全程同一 runtime（不再 fallback get_runtime）；移除 `_import_module("aipd_supervisor")`。
- 验证：runtime 测试（owner approve 经 supervisor 真实执行）+ CLI scope/waiver 测试。

## P0-10 Product CLI 忽略 --project
- **状态**：**RESOLVED**（CS6+7 `7ab8e94`）
- source：`src/aipd_os/cli/product_commands.py` `_resolve_project()`（无显式 project 时 fallback 第一个）
- reproduction：p1/p2 存在，`product show --project p2 --json → project_id=p1`
- action：显式 --project 必须使用且校验存在（不存在 ERROR）；多项目无 --project → 要求显式；单项目才自动。
- 验证：CLI 测试（多项目 scope 解析、不存在 project ERROR、waiver 决策）。

## P0-11 CLI 无法 approve_with_waiver
- **状态**：**RESOLVED**（CS6+7 `7ab8e94`）
- source：`src/aipd_os/cli/main.py`（choices=["approve","reject","request_revision"] 硬编码）
- reproduction：`--choice approve_with_waiver → argparse invalid choice`
- action：`choices=sorted(OWNER_CHOICES)`（与 ProductDefinitionGate 常量同源，防漂移）。
- 验证：`--choice approve_with_waiver` 正常解析并产生 waiver 决策（CLI 测试）。

## 其它观察

### O-1 Gate 读取 Snapshot 外 live data（§10）
- **状态**：**RESOLVED**（CS8 `b08624f`）
- source：`gate.py` 各 `_crit_*` 直接 `self._pi.list_*`
- action：建 `ProductDefinitionSnapshotView`（Snapshot → exact objects）；Gate criteria 只读 view；live table 仅用于 freshness validation。
- 验证：先冻结再破坏 live（新增 req）→ Gate 仍按 snapshot 精确集合评估；新 criteria（SNAPSHOT_SET_INTEGRITY / SNAPSHOT_UPSTREAM_BASIS）锁定。

### O-2 Principle 未绑定 selected Opportunity（Gate 层面）
- **状态**：**RESOLVED**（CS8 `b08624f`）
- action：新 criterion `PRINCIPLES_BOUND_TO_SELECTED_OPPORTUNITY`（全部 principle.opportunity_id == snapshot.selected_opportunity_id）。
- 验证：违反绑定 → gate hard_blocker。

### O-3 Generation provenance 不可反查（§37）
- **状态**：**RESOLVED**（CS2+3 `147d6cd`）
- source：`product_adapters.py`（仅 execute 返回值带 provider metadata，对象无）
- action：对象加 `generation_metadata_json`（execution run/provider/model/prompt_version/generated_at）。
- 验证：runtime e2e 断言对象 generation_metadata 含 execution run / provider。

### O-4 Release provenance 字段混用（§42-44）
- **状态**：**RESOLVED**（最终报告刷新）
- action：拆 `archive_head_commit` / `tested_commit` / `source_tree_hash` / `package_version` / `evidence_generated_at` / `artifact_hash`；最终报告引用 fresh machine report。
- 验证：最终 `V5_9_2_SNAPSHOT_RUNTIME_COMMIT_CLOSURE.md` + release evidence 三件套按 tag 锚点刷新。
