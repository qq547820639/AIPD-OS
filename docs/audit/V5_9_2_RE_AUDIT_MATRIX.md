# V5_9_2 Re-Audit Matrix（Snapshot-Closed Runtime & Commit Integrity Closure）

生成日期：2026-08-12
基线 HEAD：`4a0ac22`（Change Set 1，未改代码前逐项复现）
状态枚举：CONFIRMED / PARTIALLY_RESOLVED / ALREADY_RESOLVED / NOT_REPRODUCED /
SUPERSEDED / REGRESSION

每项附：source file / function / reproduction（真实运行输出）/ action。

## P0-01 Snapshot 不是 Closed World
- **状态**：**CONFIRMED**
- source：`src/aipd_os/product_intelligence/snapshot.py` `is_stale()`（只比较 refs 存在 + version）
- reproduction：`create snapshot(reqs=1) → add new Requirement → is_stale()=False`（live=2）
- action：stale 比较 **set equality**（active principle/requirement/feature ID 集合）；新增/删除/archive/supersede/selection change/version change 全部 STALE。

## P0-02 archived object 被 Snapshot 收入
- **状态**：**CONFIRMED**
- source：`snapshot.py` `create_snapshot()`（refs = 全部 list_*，无 lifecycle 过滤）
- reproduction：`Requirement.lifecycle_status=archived → create_snapshot → archived req 进入 requirement_refs`
- action：`create_snapshot` 只冻结 active set（selected Opportunity → 其 principles → 其 requirements → 其 features；排除 archived/superseded/rejected）；建 `definition_membership_policy_v1`。

## P0-03 Runtime Principle 没有 Opportunity
- **状态**：**CONFIRMED**
- source：`src/aipd_os/tool_adapters/product_adapters.py` `ProductDerivePrinciplesAdapter.execute()`（persist 时 `opportunity_id=input_.get("opportunity_id","")`，work item inputs 无此字段）
- reproduction：Runtime 生成后 `principle.opportunity_id=['','']`（Opportunity 存在 OPP-001）
- action：`derive_principles` 要求 exactly one selected Opportunity；provider context 只传 selected；adapter persist 自动绑 `opportunity_id=selected_id`；lineage 加 Opportunity→Principle 边（_LINEAGE_SPECS 多源）。

## P0-04 Product Work DAG 缺 dependencies
- **状态**：**CONFIRMED**
- source：`src/aipd_os/supervisor/idea_capabilities.py` `schedule_product_intelligence_chain()`（add_work 无 `depends=`）
- reproduction：provider=None 调度全链 → W1-W5 blocked_external，**W6 create_snapshot=complete、W7 definition_gate=complete**（下游未阻塞；snapshot 被创建）
- action：Supervisor 使用显式 `depends=[work_id]` DAG；上游 blocked → 下游全部 queued/dependency-blocked（fail-closed）。

## P0-05 commit snapshot lifecycle 错误
- **状态**：**CONFIRMED**
- source：`src/aipd_os/product_intelligence/gate.py` `commit_snapshot()`（尾部 UPDATE 置 `SNAPSHOT_STALE`）
- reproduction：`commit → snapshot.lifecycle_status='stale'`（系统已定义 SNAPSHOT_COMMITTED）
- action：commit 成功 → `frozen → committed`（绝不 frozen → stale）。

## P0-06 Snapshot 可重复 commit
- **状态**：**CONFIRMED**
- source：`gate.py` `commit_snapshot()`（无 exactly-once 保护）
- reproduction：`commit SNAP-001 两次 → 第二次成功 → duplicate ProductTruth`
- action：`product_definition_commits` 表（migration v12）UNIQUE(tenant,project,snapshot_id)；第二次 → 返回已有 receipt（幂等）或 SnapshotAlreadyCommitted。

## P0-07 Commit 非原子
- **状态**：**CONFIRMED**
- source：`gate.py` `commit_snapshot()`（ProductTruthStore.add 独立连接提交 → LineageGraph.add_edge 独立连接 → 失败残留）
- reproduction：注入 lineage failure → commit raises，**ProductTruth reqs=1 残留**（应为 0）
- action：ProductTruth records + canonical lineage + compatibility lineage + commit ledger + snapshot lifecycle + audit 进入**同一 transaction boundary**（复用 db.transaction + store.add(conn=...)）。

## P0-08 Upstream Claim 变化不会 stale Snapshot
- **状态**：**CONFIRMED**
- source：`snapshot.py` `is_stale()`（只查 PI 对象，不查 upstream claims/relations）
- reproduction：`create snapshot → update Claim → is_stale()=False`
- action：snapshot 存 `upstream_basis_hash`（claim ids+versions / reviewed relation ids+versions+status / assessment / insight versions / selected opp / PI versions）；is_stale 同时校验 basis hash（第二道防线）+ ImpactPropagationService 传播。

## P0-09 RuntimeContext split
- **状态**：**CONFIRMED**
- source：`src/aipd_os/runtime.py` `build_runtime()`（默认不安装单例）；`get_runtime()` 自建
- reproduction：`r1=build_runtime(db_path=X); r2=get_runtime() → r1 is r2=False，不同 DB/adapters`
- action：`build_runtime(make_default=True)` / `install_runtime(runtime)` 语义明确；cmd_intake 全程同一 runtime（不再 fallback get_runtime）；移除 `_import_module("aipd_supervisor")`。

## P0-10 Product CLI 忽略 --project
- **状态**：**CONFIRMED**
- source：`src/aipd_os/cli/product_commands.py` `_resolve_project()`（无显式 project 时 fallback 第一个）
- reproduction：p1/p2 存在，`product show --project p2 --json → project_id=p1`
- action：显式 --project 必须使用且校验存在（不存在 ERROR）；多项目无 --project → 要求显式；单项目才自动。

## P0-11 CLI 无法 approve_with_waiver
- **状态**：**CONFIRMED**
- source：`src/aipd_os/cli/main.py`（choices=["approve","reject","request_revision"] 硬编码）
- reproduction：`--choice approve_with_waiver → argparse invalid choice`
- action：`choices=sorted(OWNER_CHOICES)`（与 ProductDefinitionGate 常量同源，防漂移）。

## 其它观察

### O-1 Gate 读取 Snapshot 外 live data（§10）
- **状态**：**CONFIRMED**
- source：`gate.py` 各 `_crit_*` 直接 `self._pi.list_*`
- action：建 `ProductDefinitionSnapshotView`（Snapshot → exact objects）；Gate criteria 只读 view；live table 仅用于 freshness validation。

### O-2 Principle 未绑定 selected Opportunity（Gate 层面）
- **状态**：**CONFIRMED**（随 P0-03 一并修）
- action：新 criterion `PRINCIPLES_BOUND_TO_SELECTED_OPPORTUNITY`（全部 principle.opportunity_id == snapshot.selected_opportunity_id）。

### O-3 Generation provenance 不可反查（§37）
- **状态**：**CONFIRMED**
- source：`product_adapters.py`（仅 execute 返回值带 provider metadata，对象无）
- action：对象加 `generation_metadata_json`（execution run/provider/model/prompt_version/generated_at）。

### O-4 Release provenance 字段混用（§42-44）
- **状态**：**CONFIRMED**（PROVENANCE.source_commit 承担多义）
- action：拆 `archive_head_commit` / `tested_commit` / `source_tree_hash` / `package_version` / `evidence_generated_at` / `artifact_hash`；最终报告引用 fresh machine report。
