# F-TRUTH-PROP-01：失效传播从产品面走得到，返工执行刻意仍不可达

这一片不改判据、不加制图功能，补的是一个**声明与事实的差**：
`PropagationEngine` 的失效传播 + 有界返工写了很久，但产品侧 0 调用点——
只有测试会构造它。结果是「上游需求变了 ⇒ 下游哪些产物要返工」这条链在软件上不存在，
而登记里那句话读起来像它存在。

## 一、接线前的取证（本轮逐条读，不是记忆）

| 事实 | 出处 |
|---|---|
| 引擎定义 `PropagationEngine`，6 个公开方法 | `src/aipd_os/product_truth/propagation.py:33`（`on_upstream_changed:44` / `list_tasks:101` / `get_task:121` / `run_rework:153` / `explain_change:230` / `pending_approval:255`） |
| 产品侧 0 调用点，9 处构造全在测试 | `grep` + AST 普查；`product_truth/__init__.py:18,25` 只是再导出 |
| 产品侧唯一 truth 写入者 `commit_snapshot` 自己也不可经 CLI 触达 | `product_intelligence/gate.py:454,475`；`src/aipd_os/cli/` 内 `commit_snapshot` 命中 0 |
| 血缘边也只由 `commit_snapshot` 写 | `gate.py:469,487` |
| `rework_tasks` 只被引擎读写 | `propagation.py:80,92,104,126,148`；表定义 `product_truth/store.py:57-69` |
| 声明门禁看不见「不可达」 | `src/aipd_os/registry.py:244 probe_entry_callable` 只验入口能解析成 callable；`:287-290` 明写「入口可调用性不作为降级门槛」；`run_command` 全程不执行（只在 `scripts/capability_matrix.py:157` 被渲染） |

最后一行是这类缺口能长期存活的机制原因：**门禁核的是「名字解析得到」，不是「走得到」**。
所以本轮补一条常驻断言（§五），而不是再靠人记。

## 二、触发位置怎么选（三候选）

| 候选 | 优点 | 缺点 | 结论 |
|---|---|---|---|
| (a) 挂在 `gate.commit_snapshot` 成功处（`gate.py:490-515`） | 与唯一的产品级 truth 写入者同事务，自动触发 | `commit_snapshot` 自己在产品侧也是 0 调用点 ⇒ 挂上去只是把「不可达」上移一层；让它可从 CLI 触发要动「AI 不自批」的批准不变量 | 不在本轮做，另立 |
| (b) 新增命令面 `aipd truth propagate` / `truth tasks` | 操作者/工程变更可显式触发；仓内已有同型先例：`drawing spec`（CLI→ProductTruthStore，`commands_drawing.py:84`）、`industrialize --lab-data`（CLI→`propagate_lab_impact`，`commands_cad.py:116-125`） | 不自动 | **选定** |
| (c) 挂到 `OutboxDispatcher` 异步排产 | 与 F-EXEC-02 那条已接线的重试机制同构 | 需要一个真实返工执行器，本仓没有（引擎自己就为此 `refusing fake success`，`propagation.py:177-185`）⇒ 接上去是装饰性接线 | 排除 |

外部对照（真实读过的一页）：阿里云 Flink 物化表文档把刷新分成 continuous / 由工作流定时
/ 人工 Trigger Update 三档，并说「automated pipelines 可以级联到相关对象」——它**不**描述
stale 标记机制。本轮只借它确认「触发位置分人工/自动两档」这个分法，取人工那一档；
不宣称外部做法与本文的语义等价。除此之外再检索两轮（ECN affected items、OpenLineage
下游失效）拿到的都是术语表与营销页，没有可复用的成熟实现，这一点如实记下。

## 三、判据（为什么这几条可以机器核）

1. **真落库**：命令跑完，`truth` 表里下游记录状态变 `stale`、`rework_tasks` 里真有一行
   `pending`——不是只打印一句「已传播」。命令返回之前表是空的（前提断言），之后才有行。
2. **「已过期」不等于「没影响」**：引擎的 `stale` 只含**本次新置**的（`propagation.py:54-58`）。
   第二次传播同一上游时 `stale` 是空列表；如果原样转述，读的人会把「下游早就过期、还欠着
   返工」听成「这次什么都没影响」。所以命令分两栏：`marked_stale` / `already_stale`，
   且 `ok` 只对**没有任何下游待返工**为真（`pending_rework = bool(affected)`）。
   与 `supply_chain/impact` 的 `already_stale_deliverables` 是同一条纪律。
3. **作用域不溢出**：另一个 project 的边与记录看不见也改不着。
4. **没接的那一半要留痕**：`run_rework` 不接。将来接上时
   `TestUnwiredHalfStaysVisible::test_run_rework_is_still_unreachable_from_product_code`
   必须变红——它扫的是 **AST 里的代码引用**而不是子串，因为模块 docstring 与 `--help`
   都要提到这个名字，子串扫描会把「写清楚了没接」误判成「已经接了」，而这两种情况的处置
   正好相反（一个是保持现状，一个是连同登记与极性一起改判）。

## 四、真机读数（临时目录，输出原文）

两个项目各一条上游 + 一条下游（projA `T-001→T-002`、projB `T-003→T-004`）：

```
$ aipd truth propagate --db $W/state.db --project projA --upstream T-001
上游 T-001（truth）→ 受影响下游 1 条：本次新置 stale 1，此前已 stale 0
  · T-002 → stale
返工任务：1 条（有界，上限 3 次尝试）
  · RW-001 → T-002 状态 pending 已试 0/3
变更说明：truth T-001 (ctq) changed: projA 支架最大载荷 50kg
  为何影响：1 downstream items depend on T-001: T-002
  修复计划：bounded rework (max 3 attempts) will bump versions and re-validate 1 stale item(s)
  需要批准：owner approval required to accept new versions for: T-002
未收口：有下游处于待返工状态。返工的**执行**（run_rework）本仓尚未接线…
RC_PROSE=4

$ aipd truth propagate --db $W/state.db --project projB --upstream T-003 --json   # RC_B=4
   tasks: [('RW-002','T-004')]        ← 修好之前这里是 IntegrityError: UNIQUE(task_id)
$ aipd truth propagate --db $W/state.db --project projA --upstream T-001 --json   # RC=4
   marked_stale: []   already_stale: ['T-002']   pending_rework: True
$ aipd truth tasks --db $W/state.db --project projB                              # RC=0
返工待办 1 条，作用域 default/projB
  · RW-002 T-004 状态 pending 已试 0/3 原因 upstream T-003 changed
```

## 五、顺手量到的一个真实缺陷（`_next_task_id` 跨项目撞号）

`rework_tasks.task_id` 是**全局主键**，而 `_next_task_id` 原先按 `tenant_id/project_id`
过滤取 max ⇒ 每个项目都从 `RW-001` 开始，第二个项目插入时撞
`UNIQUE constraint failed: rework_tasks.task_id`，命令以 rc=2 退出。
这不是理论问题：跨项目传播正是这条命令的正常使用方式，是本轮的作用域用例先撞出来的。

修法是**按整表分配**（`propagation.py:_next_task_id`），作用域隔离仍由
`tenant_id/project_id` 两列负责——号段隔离不是这层的职责，读全局也不泄露什么。
**没有解决的那一半写在这里**：读-算-插之间没有加锁，多进程并发仍可能算出同一个号；
本仓按单写者假设运行，登记行的 `current_limitation` 里也这么写着。要真做到并发安全，
需要 `INSERT ... SELECT COALESCE(MAX,0)+1` 或撞号重试，那一次要连测试一起设计，不在本轮顺手做。

## 六、落点

- 新增 `src/aipd_os/cli/commands_truth.py`：`_open_store`（库不存在与读不出都是 2，
  读不到不等于「没有记录」）、`_upstream_kind`、`cmd_truth_propagate`、`cmd_truth_tasks`。
- `src/aipd_os/product_truth/propagation.py:_next_task_id`：整表分配（§五）。
- `src/aipd_os/cli/commands.py`（导入 + 两条 `COMMAND_FUNCS`）、
  `cli/command_contract.py`（两条 `PUBLIC`/`PRODUCT`/5.11 条目与 `requires_args`）、
  `cli/main.py`（`truth` 子解析器组）。
- 登记 `src/aipd_os/registry_data.py`：新行 `product_truth.impact_propagation`
  （`entry_point` 指向 `cmd_truth_propagate`，`current_limitation` 写清未接的那半、
  血缘边只有 `commit_snapshot` 会写、号分配的并发前提、与 `supervisor.auto_rework`
  是两套机制）；同时改 `industrialize.physical_writeback` 里那句「仍是 0 调用点」——
  **同一趟把描述这件事的地方全改了**，这是第 9 片记下的教训（`docs/audit/CAD_DETAIL_VIEWS_F-DRAW-01_2026-09-24.md` §七）。
- 文档同趟更新：`docs/architecture/truth_architecture.md`（可达性现状）、
  `docs/audit/LAB_IMPACT_PROPAGATION_F-SUPPLY-03_2026-09-24.md`（带日期的更正，只更正失效的那半句）、
  `docs/audit/EXEC_OUTBOX_WIRING_F-EXEC-02_2026-09-24.md`（遗留 5 已落 + 撞号缺陷）、
  `docs/audit/P0_VERIFICATION_MATRIX.md`（P0-10 引用的 `_default_rework` 行号已失效，补指针更正）、
  README、CHANGELOG、SKILL.md（public 数 45→47，逐条点名）。

## 七、用例与变异（12 条，T9 首轮幸存后补断言才杀）

`tests/test_truth_propagate_cli.py` 18 条。变异电池逐条锚点命中数必须 =1：

| 变异 | 结果 |
|---|---|
| T1 `_next_task_id` 退回按作用域取 max | 杀（跨项目用例撞 `IntegrityError`） |
| T2 `pending` 改看本次新置的 stale | 杀（第二次跑会假绿） |
| T3 `already_stale` 塌成 `marked` | 杀（2 条） |
| T4 `upstream_kind` 恒报 truth | 杀 |
| T5 库不存在时静默开一个空库 | 杀（rc 2→0） |
| T6 `--reason` 丢弃 | 杀 |
| T7 `--max-attempts<=0` 不校验 | 杀 |
| T8 请求的上限没传给引擎 | 杀（`test_max_attempts_is_carried_onto_every_new_task`） |
| T9 `truth tasks` 顺手把任务推进到 running | **首轮幸存** → 补「库里状态绝对仍是 pending」断言后杀 |
| T10 在没有执行器时接上 `run_rework` | 杀（AST 可达性断言 + 只读断言） |
| T11 契约里降级成 INTERNAL | 杀（契约用例 + SKILL 总数用例） |
| T12 删掉 `COMMAND_FUNCS` 条目 | 杀（15 条） |

T9 的教训与既有记忆同族：**「比两次结果相同」挡不住第一次就把状态改掉**——两次都读到
被推进后的值，看起来完全一致。只读命令的断言必须落在**库里的绝对状态**上。

## 八、边界（不要当成已具备）

- 只接了传播：`run_rework` 零产品调用点，且这是刻意的（§三.4）。
- 血缘边目前只有 `commit_snapshot` 写，且只写「PI 需求 → truth 记录」这一类；
  CTQ/图纸/BOM 之间的边没有生产者 ⇒ 链条更长的那一段今天传播不到。
- 第二次传播会为同一下游再生成一条新任务（引擎现状，用例把它钉成读数）——
  没有做任务去重/合并，所以「任务数」不等于「待返工条目数」。
- 任务号并发安全未做（§五）。
- `truth propagate` 不改制品状态：制品侧的 stale 仍走 `supply_chain/impact` 那条 CAS 路径，
  两套机制并存，本轮没有合并语义。
- 另一处同类缺口本轮**未动**：`state/stale_propagation.py:43` 的
  `StalePropagationService`（方法 `propagate_requirement_change:82` /
  `propagate_cad_change:108`）依然 0 产品调用点，唯一使用者是
  `scripts/state_perf_gate.py:237`。

## 九、复算

```bash
cd AIPD-OS
.venv/bin/python -m pytest tests/test_truth_propagate_cli.py \
  tests/test_skill_command_surface.py tests/test_command_coverage.py \
  tests/test_capability_entry_surface.py tests/test_product_truth_propagation.py -q
.venv/bin/python -m ruff check src tests state_service
.venv/bin/python -m mypy src tests
W=$(mktemp -d)   # 两个项目各一条上游/下游后跑 §四 那四条命令
```
