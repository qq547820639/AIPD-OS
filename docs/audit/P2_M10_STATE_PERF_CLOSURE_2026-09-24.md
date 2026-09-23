# P2-M10 收口：状态层性能验证 + 全量回归（2026-09-24）

> 范围：P2 状态归属收敛路径的最后两个里程碑（M8 遗留导入环、M10 性能验证与
> 全量回归），以及收口过程中由回归与量具**实测暴露**的 3 个缺陷（F5/F6/F7）。
> 起点 HEAD：`1d0f84f`（P2-M7 Readiness Snapshot wiring），工作区干净。

## 0. 结论速览（全部为本机实测，非推断）

| 项 | 结果 |
|---|---|
| 起点全量回归 | **6 failed / 1262 passed / 3 skipped**（178.48s） |
| 收口全量回归 | **1289 passed / 0 failed / 3 skipped**（166.41s，清单重算后复跑） |
| release-ready 门禁 | **8/8 PASS**（exit 0；CVE 项需 `pip-audit` 在 PATH 上，见 §8.4/§8.5）。注意其中 3 项描述的是 v5.6.0 那次发布的 bundle，不是当前提交，见 §8.5 注意事项 |
| `audit_repo --strict` | 哈希两项已消除；`source_commit == HEAD` 这一条自 v5.6.0 发布起对**任意**后续提交都必红（已证实为既有状态，未擅自放宽，见 §8.6） |
| ruff（CI 口径 `src tests state_service`） | 0 错误 |
| mypy（CI 口径，356 文件） | 0 错误 |
| 新增测试 | `tests/test_connection_reentrancy.py` 8 例、`tests/test_state_perf_gates.py` 10 例、`test_stale_propagation.py` +3 例、`test_migration.py` 迁移到新模块 |
| Schema 版本 | v16 → **v17**（两条热读索引，可回滚） |
| 量具 | `scripts/state_perf_gate.py`（12 场景）+ `docs/audit/state_perf_baseline.json` + `docs/audit/state_perf_report.json` |

## 1. 技术选型（M10 量具）

按要求先检索成熟实现，检索结果真实可复核：

| 候选 | 功能匹配 | License | 维护活跃度 | 安全 | 代码质量 | 适配成本 |
|---|---|---|---|---|---|---|
| **pytest-benchmark** | 高：轮次校准、统计、`--benchmark-json`、`--benchmark-compare-fail` | BSD-2-Clause ✅ | 活跃（PyPI：5.3.0，2026-08-23 发布） | 纯测试期依赖 | 成熟 | **阻断点**：5.3.0 `requires-python>=3.10`，而本包契约是 `>=3.9,<3.13` 且 CI 校验 3.9–3.12。实测在 py3.9.6 可装可导入的是 **5.1.0**（`requires_python>=3.9`），因此引入即需在 dev extra 永久钉 `>=5.1,<5.2`；且多变量场景每轮需重建数据库，与 fixture 模型不匹配 |
| **asv (Airspeed Velocity)** | 面向跨 commit 历史追踪，不是单次发布验证 | **未能取证**：PyPI 页面仅返回 JS 占位、GitHub 抓取失败（`fetch failed`） | 未取到 | 未取到 | 未取到 | 需自建 venv 矩阵，重 |
| **stdlib 量具 + 基线棘轮**（本仓 `scripts/*_gate.py` 既有惯例） | 高：可测吞吐/并发/扩展性，并用 `EXPLAIN QUERY PLAN` 做机器无关门禁 | MIT（自有）✅ | n/a | 零新增依赖 | 自维护约 300 行 | 最低 |

**选定：stdlib 量具 + 基线棘轮**，并复用 pytest-benchmark 的**设计**（rounds、
min/median/mean/max/stdev、`--benchmark-compare-fail` 的相对阈值语义）；基线
JSON 结构保持与其可比，日后替换成本低。asv 未取证即不作为推荐依据。

## 2. F5（Critical）重入事务自死锁

**现象**：`tests/test_supervisor_execution.py::test_run_supervisor_executes_doc_to_complete`
返回 `internal_rework / error='database is locked'`；`test_mark_stale_exact_dependency_match`
在 `_mark_stale → add_lineage → project_id → connect → transaction` 处抛
`sqlite3.OperationalError: database is locked`。单条用例耗时 5.3s ≈ `busy_timeout`。

**归因（已证实为 P2 引入）**：在 `1509746`（P2-M1..M7 之前）建 worktree 复跑，
`tests/test_supervisor_execution.py` 4 例**全绿**；HEAD 上 2 例红。

**根因**：`ConnectionFactory.transaction()` 每次都新建连接并 `BEGIN IMMEDIATE`。
SQLite 写锁按连接持有，因此同一线程「外层事务未提交 + 内层再开事务」是
**单线程自我死锁**，与并发无关。`Supervisor.connect()` 还每次新建
`ConnectionFactory` 实例，所以任何按实例存放的重入状态都看不见外层事务。

**修复**：登记表 key 改为 **(解析后的绝对库路径, 线程 ident)**；重入时复用外层
连接并用 `SAVEPOINT`（内层失败回滚到保存点后重抛，外层事务仍有效）。
这与 `AIPDStateDB` 自 v5.9.1 起已在用的形状（TLS + 复用 + SAVEPOINT）收敛，
不是新发明，是把 P2-M3 迁出来的 store 补上同一契约。

**反向验证（证明量具能判红）**：把 `connection.py` 换回 HEAD 版本重跑新契约测试
→ **6 of 8 失败，总耗时 31.76s**（≈6×5s 等锁）。换回修复版 → 8 例 0.05s 全绿。

**遗留风险（记录在案，未修）**：`AIPDStateDB` 用自己的
`_db_tls.tx_conn`，`ConnectionFactory` 用 `_ACTIVE_TX`，两套登记表互不可见。
若将来有代码对**同一个 state.db** 同时使用两套事务接口，会以另一种形式重现
同类死锁。实测当前不可达：`ConnectionFactory(...)` 的全部产品调用点为
`bom/store.py`、`product_truth/store.py`、`execution/closure_core.py`、
`execution/runs.py`、`supervisor/supervisor.py`，均为独立 db 文件；
`validation/readiness.py` 与 `state/stale_propagation.py` 走 `AIPDStateDB.connect()`。

## 3. F6 stale 传播写入不存在的列

`StalePropagationService._mark_downstream_stale` 的 cost_snapshot 分支向
`changes` 写 `(tenant_id, project_id, entity_type, entity_id, change_type,
change_data, created_at)`，而真实表是
`(change_id, project_id, tenant_id, object_type, object_id, action,
before_json, after_json, reason, created_at)`（`PRAGMA table_info` 实测）。
**只要依赖图非空就必然 `OperationalError`**。

原有 8 条 P2-M6 用例全部跑在零依赖图上（fixture 只建租户、不建依赖），
所以该分支从未被执行——这是「测试通过 ≠ 功能可用」的又一例。
`validation_result` 分支经实测列名正确（`stale/stale_reason/updated_at` 均存在），
无需改动。

**修复 + 3 条新用例**（BOM→cost 落到 changes、CAD→validation_result 标 stale
且保留原 PASS、零依赖合法路径）。反向验证：回退 `stale_propagation.py` 到
HEAD → 新用例报
`sqlite3.OperationalError: table changes has no column named entity_type`。

## 4. F7 / migration v17 热读索引

`EXPLAIN QUERY PLAN` 实测（v17 前）：

```
claim   : SCAN outbox_events USING INDEX idx_outbox_claim | USE TEMP B-TREE FOR ORDER BY
changes : SCAN changes                                                  | USE TEMP B-TREE FOR ORDER BY
```

新增 `idx_changes_scope_time ON changes(tenant_id, project_id, created_at)` 与
partial 索引 `idx_outbox_due ON outbox_events(available_at) WHERE completed_at IS NULL`。

同机 A/B（`--rounds 2/3`，v17 与手动 DROP INDEX 对比）：

| 场景 | v16（无索引） | v17（有索引） | 说明 |
|---|---|---|---|
| `changes_recent_100_ms`（2 万条审计，取最近 100） | 5.57ms | 1.36ms | ≈4.1× |
| `outbox_claim_batch_ms`（5000 积压，limit=100，含 100 次 UPDATE） | 2.62ms | 2.32ms | ≈1.1× |
| claim 的纯候选 SELECT（无写入） | 0.29ms | 0.01ms | ≈29×；排序成本随积压增长而消失 |
| `outbox_append_ops_s`（写放大检查） | 129.6k ops/s | 139.7k ops/s | **不可测出**，落在 run-to-run 噪声内 |

诚实标注：claim 的端到端收益取决于批大小与写入占比（本例写入占主导），
纯读候选扫描的收益才是数量级的；早期一次 147× 的读路径估算是**错的**
（查询条件与插入的 scope 不一致，实测返回 0 行），已用有界 `LIMIT 100` +
真实 scope 重测为 4.1×。

## 5. M8 导入环（F8）

`migrations` 拆包后 `definitions → helpers → runner → definitions` 成环
（helpers 以函数内 `from .runner import _exec_script` 取工具）。
`tests/test_import_cycles.py` 在 `1509746` 起即红，本轮关闭：
工具下沉到叶子模块 `migrations/sqlsplit.py`（`split_statements` / `exec_script`），
runner 与 helpers 均改为向下依赖。

## 6. 量具自身的反向验证

一个不会判红的门禁等于没有门禁。两组控制实验：

1. **收紧基线**（把 `docs/audit/state_perf_baseline.json` 的 ms/us/ratio 一律减半、
   ops/s 一律翻倍，模拟「历史更快」）→ 退出码 1，逐条给出劣化百分比
   （`migrate_cold_ms +98.1% > 35%`、`fact_batched_ops_s -49.6% > 40%` …）。
2. **真实退化**（运行时 DROP 掉 v17 两条索引）→ 退出码 1：
   `outbox_claim_batch_ms +79.5% > 50%`、`changes_recent_100_ms +446.3% > 50%`。

正常复跑（`--rounds 5`，与刚采集的基线比）→ **性能门禁：PASS**，
全部场景漂移在 ±20% 内。

**测量环境噪声（必读）**：本机同时存在其他会话的 pytest 作业
（`ps` 实测到非本会话的 `pytest -m "not sqlite_only" --cov=app` 等）。
同一份量具在 3 分钟前后测得的绝对值相差约 2.5×（`migrate_cold_ms`
10.1ms vs 27.9ms）。因此：**绝对毫秒数只用于趋势与同机 A/B，
门禁一律用相对阈值 + 轮内比值**；换机或换负载后应
`--update-baseline` 重采，而不是把别机数字当契约。

## 7. 文档修正（不是注释，是纠正错误事实）

`docs/architecture/state_infrastructure.md` 记载的连接策略包含
`PRAGMA timeout = 10000 — 10s 连接超时`。SQLite **没有**这个 pragma：
实测发出后不报错、不返回行、`busy_timeout` 读数不变（未识别 pragma 被静默忽略）。
真实超时来自 `sqlite3.connect(timeout=10)`。已从策略中删除并加注释说明，
同时补写 §4.1 重入规则与 §6.1 索引门禁。

## 8. 回归与发布证据记录

### 8.1 全量回归（`pytest -q -m "not model_eval"`）

| 阶段 | 结果 |
|---|---|
| 起点（HEAD `1d0f84f`，工作区干净） | `6 failed / 1262 passed / 3 skipped / 2 deselected in 178.48s` |
| 收口（清单未重算时） | `2 failed / 1287 passed / 3 skipped / 2 deselected in 220.68s` |
| 收口（清单重算后复跑） | **`1289 passed / 0 failed / 3 skipped / 2 deselected in 166.41s`** |

起点 6 项失败：`test_exception_hygiene::test_no_uncommented_empty_except`、
`test_import_cycles::test_no_import_cycles`、
`test_packaging::{test_release_manifest_hashes_match_disk, test_source_manifest_hashes_match_disk}`、
`test_supervisor_execution::{test_run_supervisor_executes_doc_to_complete, test_mark_stale_exact_dependency_match}`。

质量门禁：ruff（CI 口径 `src tests state_service`）0 错误；
mypy（CI 口径，356 文件）0 错误（顺带修掉 `test_architecture_contracts.py`
里过期的 `# type: ignore[import-not-found]`——本机 mypy 对 pyyaml 报的是
`import-untyped`，两个码同时保留才在有无 `types-PyYAML` 的环境下都成立）。

`readiness.py` 的 `except Exception: pass` 改为
`logger.warning("readiness_snapshot_persist_failed", exc_info=True)`：
快照持久化失败仍不打断 readiness 评估（保持原语义），但不再静默丢快照。

### 8.2 `audit_repo.py --strict`：2 项哈希漂移已修，1 项是既有发布锚点漂移

本轮动手前实测三项红：

```
✗ Release manifest hash mismatch: 2 files
✗ Source manifest hash mismatch: 26 files
✗ Provenance source commit mismatch: manifest=a66040520139… vs HEAD=1465a249d35d…
```

- 前两项由 `scripts/regenerate_release_manifest.py` 与
  `scripts/release_evidence.py`（只取回 `SOURCE_MANIFEST.json`）重算后消除；
- 第三项**不是本轮引入**，也不是 `PROVENANCE.json` 的问题：`audit_repo` 把
  `SOURCE_MANIFEST.source_commit` 叫做「Provenance」并与 HEAD 比较，而
  `release_evidence.py` 缺省把 `source_commit` 写成**当时的 HEAD**。
  只要「生成证据 → 再提交证据」，HEAD 就必然领先，所以 v5.6.0 之后的每个提交
  都会让这条判红。修法是 `--source-commit <tag SHA>` 显式预置锚点：
  本轮生成时它一度被写成 `1465a24`（我引入的一次偏离），
  已用 `--source-commit a660405…` 重新生成，使 SOURCE_MANIFEST 与
  PROVENANCE 再次携带同一个发布锚点。

### 8.3 有意不做的发布动作

真正闭合「锚点落后于 HEAD」需要：重建 bundle → 重算 `BUNDLE_MANIFEST.json` →
Ed25519 重签 → 决定新版本号并打 tag（版本号双轨制本就是待决项）。
这些是**发布行为**，且涉及共享状态（tag / 远端），因此：

- 没有改写 `PROVENANCE.json` / `BUNDLE_MANIFEST.json` / 任何 `.sig`；
  生成到临时目录的新 `PROVENANCE.json` **未拷回仓库**，
  以免给一个未构建、未签名的提交留下「已发布证据」；
- 没有 `git push`，没有移动 `v5.6.0` tag；
- 发布锚点是否随本轮 P2 重锚，留给 owner 决定。

顺带修正了门禁自身一处**输出不实**：`commit_matches_head` 通过时的 detail
文案写的是 `HEAD matches`，而 `_check_commit` 实际比较的是
`provenance.source_commit` 与 **tag** 指向的提交（源码注释说明「HEAD 可能因
发布证据元数据提交略领先于 tag，属正常」）。逻辑没错、名字与文案误导，
已把通过文案改为「provenance source_commit 与 tag 指向同一提交」。

### 8.4 CVE / license 检查：一次「量具假阴性」的实录

`no_unacknowledged_cve` 缺 `pip-audit` 时按 fail-closed 判红（设计正确）。
但本轮装上 `pip-audit 2.9.0`（`.venv/bin/pip-audit --version` 可执行）后
首次复跑**仍然**报 `pip-audit not available`。根因不是没装：
检查用 `shutil.which('pip-audit')` 找可执行文件，而调用方式是
`.venv/bin/python scripts/production_release_gate.py …`——
`.venv/bin` 不在 PATH 上，`which` 自然找不到。

教训（写进本仓的量具纪律）：**「查不到」不等于「不存在」**，
否定结论前要先确认探针自身的前置条件（这里是 PATH）。
用 `PATH=.venv/bin:$PATH` 复跑后的真实结果见 §8.5。

### 8.5 release-ready 门禁最终判定

`PATH="$PWD/.venv/bin:$PATH" .venv/bin/python scripts/production_release_gate.py
--release-ready --tag v5.6.0`（工作树尚有本轮文档未提交时）：

```
FAIL workspace_clean            ← 仅因该次运行时 SOURCE_MANIFEST/文档未提交
PASS commit_matches_head        provenance source_commit 与 tag 指向同一提交
PASS source_manifest_zero_diff  zero diff
PASS bundle_manifest_zero_diff  zero diff
PASS test_numbers_from_report   passed=1096 failed=0 total=1099 source_commit=a660405…
PASS signature_verifiable       Ed25519 signature verified
PASS no_secrets                 no secret patterns found
PASS no_unacknowledged_cve      pip-audit: no unacknowledged CVE
```

即 **8 项中 7 项绿**，唯一红项是「工作区不干净」。这条不是循环死结：
`workspace_clean` 判的是「工作树有无未提交改动」，所以只要把文档与清单一起
提交，它就重新成立。把上面的改动提交后（`e9206bf`）复跑同一条命令：

```
PASS workspace_clean            clean
PASS commit_matches_head        provenance source_commit 与 tag 指向同一提交
PASS source_manifest_zero_diff  zero diff
PASS bundle_manifest_zero_diff  zero diff
PASS test_numbers_from_report   passed=1096 failed=0 total=1099 source_commit=a660405…
PASS signature_verifiable       Ed25519 signature verified
PASS no_secrets                 no secret patterns found
PASS no_unacknowledged_cve      pip-audit: no unacknowledged CVE
→ 8/8，exit 0
```

**两条必须一起读的注意事项**（否则这串绿会被误读）：

1. `test_numbers_from_report` 的 1096/0 是 **v5.6.0 tag 那次发布**的数字
   （`source_commit=a660405`），不是当前 HEAD 的 1289/0。
   门禁按设计只校验「证据与被 tag 锚定的提交一致」，
   所以它绿 ≠ 当前提交被门禁测过；当前提交的测试事实来自 §8.1 的复跑。
2. `bundle_manifest_zero_diff` / `signature_verifiable` 校验的是
   8-14 构建的那个 zip 与它的签名，同样不覆盖当前源码。

### 8.6 `audit_repo --strict` 与门禁的不变量互相矛盾（待决，未擅自放宽）

同一个锚点，两个工具要求不同：

| 工具 | 不变量 | 对「发布之后的任意提交」 |
|---|---|---|
| `production_release_gate --release-ready --tag` | `provenance.source_commit == tag` 指向的提交（源码注释明确允许 HEAD 领先） | 可绿 |
| `audit_repo --strict` | `SOURCE_MANIFEST.source_commit == HEAD` | **必红** |

已证实这是既有状态，不是本轮引入：本轮起点 `1d0f84f` 上
`SOURCE_MANIFEST.source_commit` 就是 `a660405`（读 `git show` 比对，二者不等），
所以自 v5.6.0 发布以来的每个提交都会让 `audit_repo --strict` 判红。

两条出路，属发布决策，交 owner：
1. 重新发布（重建 bundle → 重算 BUNDLE_MANIFEST → Ed25519 重签 →
   决定新版本号并打 tag），顺带统一版本号双轨制；
2. 或让 `audit_repo --strict` 像门禁一样按 tag 锚定比较。
   本轮**没有**改这条判据：放宽一个发布安全检查不该在收口迭代里顺手做。




## 9. 未做 / 下一步

- **`executescript()` 与重入事务不兼容（本轮定位，当前不可达）**：
  Python 的 `Cursor.executescript()` 执行前隐式 COMMIT，所以
  `with factory.transaction() as c: c.executescript(...)` 之后的语句
  已不在该事务内；此时若再嵌套 `transaction()`，`SAVEPOINT`/`RELEASE`
  会自成一个小事务并提前提交。产品代码目前只在 `Supervisor.__init__`
  建表处使用 `executescript`，且该处无重入调用，故不触发。
  修法：DDL 也走 `migrations/sqlsplit.exec_script()`（拆分后逐条 execute，
  不隐式提交）。
- `OutboxDispatcher` 在 `src/`、`scripts/` 内**无任何产品调用点**（实测 grep），
  目前只有测试与量具消费它。M5 交付的是机制，接线尚未发生。
- 两套事务登记表（`AIPDStateDB` 与 `ConnectionFactory`）未统一，见 §2 遗留风险。
- WAL 仍未全局开启（量具可复测，属于需要跨平台验证的独立决策）。
- 版本号双轨制（pyproject 5.6.0 vs 功能 v5.10）仍留待正式发布统一。
- 概览文档 `overview.md`（工作区根，仓外）已同步到本轮。
