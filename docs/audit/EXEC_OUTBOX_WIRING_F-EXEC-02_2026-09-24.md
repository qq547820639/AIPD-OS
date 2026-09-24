# F-EXEC-02 / 03 / 04 · 外部副作用事件化接线（outbox → dispatcher → 台账）

日期：2026-09-24 ｜ 轮次：承 F-NET-01 / F-REL-01 之后
状态：**已闭合**（产品调用点 + 4 处语义缺陷 + 25 条常驻用例 + 全量回归 + 静态门禁）
关闭的遗留：`OutboxDispatcher` 无产品调用点（P2-M5 起记录，见
`docs/audit/P2_M10_STATE_PERF_CLOSURE_2026-09-24.md:317-323` 与
`CHANGELOG.md:94`）

## 1. 结论速览（全部现算，非引用旧文）

| 项 | 接线前 | 接线后 |
| --- | --- | --- |
| `OutboxDispatcher` 产品调用点 | **0**（`src/`、`scripts/` 全量 grep：只有 `tests/test_dispatcher.py:11` 导入它） | CLI `aipd outbox drain` + `build_rfq_dispatcher()`（`cli/commands_outbox.py:19`） |
| `OutboxRepository.append_event` 产品调用点 | **0**（其余命中全在测试与 `scripts/state_perf_gate.py`） | `OutboxQueue.enqueue` ← `MailRfqAdapter.execute`（带队列时） |
| `external_operations` 写入者 | **0**（dispatcher `import` 了仓储却从不调用） | RFQ handler 每次对外投递一条，含状态机与 `external_reference` |
| v16 部分唯一索引 `idx_ext_ops_idempotency_unique` | 从未被任何用例经过 | `test_v16_unique_index_actually_rejects_a_duplicate` 开火 |
| `max_attempts` | 写死 5、**从未被读** ⇒ 一次 `drain()` 内毒事件无限重领 | 预算生效：实测旧代码 handler 被调 **20/20** 次，新代码 **5** 次后 `TERMINAL_ATTEMPTS_EXHAUSTED` |
| handler 抛 `TimeoutError` | 走 `mark_retry`（**会自动重发**）却返回 `UNKNOWN_OUTCOME` | 新增 `mark_unknown`：离开可领集合，等人工核对；配 `ConnectionError` 仍可重投做极性对照 |
| `claim_available` | 「先 SELECT 再逐行无条件 UPDATE」，docstring 称「原子」；返回的是**写之前**的快照 | 单条 `WITH due AS (…) UPDATE … RETURNING *`，带租约返回 |
| `run_once()` 提交 | 无条件 `self._conn.commit()` ⇒ 会提交调用方未提交的领域写 | 仅当没有别人持有该 (库, 线程) 事务时提交 |
| 载荷安全 | —— | SMTP 口令**不入事件表**，投递瞬间从环境取（用例断言载荷里搜不到 `password`） |

## 2. 缺陷本体

### F-EXEC-02（关闭遗留：机制齐备但无人调用）
`state/outbox.py` + `state/dispatcher.py` 提供了事务内追加、租约领取、结果分类，
`external_operations` 还有完整状态机（`PENDING→DISPATCHED→…→UNKNOWN_OUTCOME`）。
但产品侧一行都没写过：RFQ 适配器在 `router.run()` 里**内联**调 `send_email`，
外部副作用既没有「先落账再执行」的凭据，也没有可核对的历史。
`ExternalOperationRepository` 被 dispatcher 构造出来却一次都没用（`git grep` 实测）。

### F-EXEC-03（会重复对外发送的两个洞）
- `mark_retry` 把 `claimed_at` 置空 ⇒ 同一次 `drain()` 的下一轮立刻能再领到；
  `max_attempts` 从未参与判断 ⇒ 一台连不上的 SMTP 会在一次 drain 里被重试
  `max_iterations=100` 次（实测 handler 调用数 20/20，仅受测试里 `max_iterations=20` 限制）。
- `TimeoutError` 分支写的是 `mark_retry`：超时不证明「没送到」，自动重投就是**给同一家
  供应商发第二封信**——而同一个分支返回的字符串却自称 `UNKNOWN_OUTCOME`，
  等于代码与读数互相矛盾。仓库既有 doctrine（UNKNOWN ≠ FAILED）与 F-EXEC-01
  （结果未知的重驱动挂起等人工核对）都站在「不重发」一边。

### F-EXEC-04（接线才会踩到的三个洞）
- `run_once()` 末尾无条件 `commit()`：把它放进调用方事务里，就会把别人
  **尚未提交**的领域写一起提交（与 F-STATE-05 的 `executescript()` 隐式 COMMIT 同形状）。
- `claim_available()` 的读写窗口 + 恒真谓词：docstring 承诺「原子 claim + lease」，
  实际是 SELECT 后按主键无条件 UPDATE；返回的字典还是领取**之前**的快照，
  handler 看不见自己的租约（`claimed_by` 读到空串，实测）。
- `find_by_idempotency_key` 少了 `operation_kind` 一列，而唯一索引包含它 ⇒
  不同种类共用一个键时命中哪条不确定（`fetchone()` 无 `ORDER BY`）。

## 3. 选型（六维）

检索过：PyPI/GitHub 生态内**没有**找到可直接复用的 Python + stdlib `sqlite3` 事务性
outbox 库（命中物是博客、Go demo、`python-cqrs`（Web/CQRS 框架，非嵌入式 SQLite 场景）、
以及一篇 Medium 文章）；因此按「复用仓内既有机制 + 采纳文献共识」处理，
未声称读过任何未实际访问的实现源码。

| 候选 | 功能匹配 | License | 维护活跃度 | 安全 | 代码质量 | 适配成本 | 结论 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 复用仓内 `outbox.py`/`dispatcher.py`，补齐预算/未知态/原子领取 | 表、状态机、租约、仓储已在（v14+v16+v17） | 无新增依赖 | 本仓自己维护 | 无外部面 | 已有测试与量具消费同一套 API | 低：改 2 个文件 + 新增 1 个编排模块 | ✅ **选用** |
| `python-cqrs`（GitHub 检索命中的事件驱动框架） | 面向 Web/CQRS 应用装配，不含 SQLite 租约领取与外部调用台账 | 未核验（未读 LICENSE） | 未核验 | 引入框架面 | 未读源码，不评价 | 高：与现有 `ConnectionFactory` 事务模型冲突 | ❌ 未采用（且明确：未读过其实现） |
| 外部 broker（Redis/RQ/Celery 一类） | 能解决投递，但把「一次询价」变成需要额外服务进程 | 各库不同 | 活跃 | 新增网络面与凭据面 | 成熟 | 高：产品当前是单文件 SQLite 嵌入式部署，违背部署形态 | ❌ 与部署形态不符 |
| 后台 daemon 线程轮询 | 只是换个地方触发 dispatcher | —— | —— | 静默失败难观测 | —— | 低 | ❌ 入口必须可指认：`aipd outbox drain` 显式驱动 |

采纳的文献共识（用作设计依据，不作为引用来源）：**领取必须是一条语句内完成
（或带来源态谓词的 CAS）**、**重试要有预算并落死信**、**结果未知不能等同失败**。

## 4. 实现

- `src/aipd_os/execution/side_effects.py`：`EVENT_RFQ_SEND`、`rfq_idempotency_key()`
  （按 项目+供应商+零件+数量 内容派生，与 F-EXEC-01 的 `auto:` 键同一 doctrine）、
  `OutboxQueue`（走 `ConnectionFactory.transaction()`，外层有事务就并入）、
  `rfq_send_handler()`（查台账 → 无则占键 → `DISPATCHED` → 真发 → `SUCCEEDED`；
  超时 `UNKNOWN_OUTCOME` 并原样抛出；失败按预算落 `FAILED_RETRYABLE`/`FAILED_TERMINAL`）、
  `build_rfq_dispatcher()`。
- `state/outbox.py`：单语句 claim + `RETURNING`；新增 `mark_unknown`；`mark_completed`
  接受 `note` 并清空陈旧 `last_error`；`find_by_idempotency_key` 补 `operation_kind`。
- `state/dispatcher.py`：预算判定、`deduped` 由 handler 返回值派生完成备注、
  事务归属判定（`ConnectionFactory.active_transaction()`），删除从未使用的台账仓储。
- `tool_adapters/mail_rfq_adapter.py`：`MailRfqAdapter(queue=...)` ⇒ 不内联发送，
  返回 `{"queued": True, "sent": False, "event_id", "idempotency_key", ...}`；
  没有队列时旧行为逐字保留（配对用例钉住，避免装配缺失时静默改变产品行为）。
- `tool_adapters/builtin.py` + `supervisor/supervisor.py`：`build_registry(state_db=...)`，
  监督器默认带上状态库 ⇒ 产品默认路径就是事件化路径。
- `cli/{main,commands,command_contract,commands_outbox}.py`：新增 `aipd outbox drain`
  （`--db` 必填、`--limit`、`--worker-id`、`--json`），打印 真发/去重/待办 三个数。
- `registry_data.py`：`industrialize.email_execution` 的 `entry_point` 原写
  `mail_rfq_adapter.send`（**该符号不存在**），现指向真实可解析的
  `aipd_os.execution.side_effects.rfq_send_handler`，并补 `run_command` 与
  `unit_test`；顺带修 `state/stale_propagation.py:74` 的「Append propagation event to
  outbox」不实注释（它写的是 `changes` 表）。

## 5. 本轮自己制造又被抓出的六处（登记以免被当成顺带改动）

1. `tests/.../TestCliDrain` 里 `class _Args: db = db` —— class 体用 `LOAD_NAME`，
   绑到了模块级同名 **fixture 函数**上，表现为「no such table: outbox_events」
   而不是 `NameError`。改用 `SimpleNamespace`，并把这条写进用例注释。
2. handler 自己 `mark_completed(note=…)` 后，dispatcher 又无条件
   `mark_completed(*key)` 把备注覆盖成空 ⇒ 「去重痕迹」读数恒为 0。改成
   完成状态由 dispatcher 单点写、备注从 handler 返回值派生（避免两个写入者）。
3. 预置台账的用例直接 `PENDING → SUCCEEDED`，被状态机拒绝——这是**台账状态机在
   替我把关**（非法边本来就该拒），用例补上 `DISPATCHED` 这一跳而不是放宽判据。
4. 上一轮 F-REL-01 归档的 `pytest-report-v5.6.0.json` 让
   `tests/maturity_consistency_test.py::test_no_faceted_overclaim` 判红：那条门禁按
   **字面文件名**豁免机器测试报告（`{'pytest-report.json','lastreport.json'}`），
   新归档件同性质但换了名，于是报告里的测试 nodeid 字符串
   （`faceted_brep_never_reaches_C2`）被当成产品散文扫了出来。
   把豁免改成按属性判定（`pytest-report*.json`）并补双向控制用例：归档件与轮级件
   都豁免、同前缀的 `.md` 与非报告 JSON 仍在语料内。
   同一门禁**第二次**判红是我的审计文档正文引了同一个 nodeid —— 这次不是文件名问题，
   是否定词表不全：`NEGATION_HINTS` 收了 `cannot`/`not reach` 却没有 `never`。
   补词而不是改措辞（改措辞躲得过一次躲不过三次），并加配对控制：
   `faceted_brep_never_reaches_C2` 不判红、只差一个 `never` 的
   `faceted_brep_reaches_C2` 必须仍判红。**把产物写进仓库，就是给所有文档扫描器
   喂新语料**——归档动作要与扫描面对齐，而不是让扫描器记住每个文件名。
5. 同一个坏测试还在**仓库根留下了 4 个垃圾文件**：`str(fixture 函数)` 被当作数据库
   路径，`ConnectionFactory` 于是照着这个名字建了空文件。全量测试全绿，没人看见；
   最后是发布门的 `workspace_clean` 把它们抓出来（4 个 `?? "<pytest_fixture(...)>"`）。
   处置：删掉（0 字节、本轮产物、非他人工作），并在 CLI 用例里加前提断言
   `assert Path(db).is_file()` —— 装配错了就地判红，别让文件系统替我记账。
6. `SKILL.md` 的散文计数「主线共 38 个」**在本轮之前就已经漂了**：契约里 public
   命令实测 39 条（`get_all_commands()` 现算）。也就是说这个数字已经错着过了
   至少一次命令新增。补上新命令后写为 40，并加
   `tests/test_skill_command_surface.py`：总数按契约同源核对、每条 public 命令的
   名字必须出现在 SKILL 里、外加两条注入反证（总数改错要红、句式漂移要红）。
   注意既有 `skill_quality_audit.py` 只问「有没有被声明」，不问「总数写对没有」——
   两者不互相替代。

## 6. 诚实边界

- **没有对任何真实邮件服务器发起投递**。全部发送证据来自注入的假 transport；
  `tests/test_mail_protocol.py` 的 Mailpit 实投递用例仍按 `AIPD_MAILPIT_*` 缺失而 SKIP。
  真 SMTP/Gmail 通道属 owner 配置项，仍是 `external_dependency`。
- 幂等去重的**并发**面只做到「单连接内两条同键事件 + 唯一索引 + IntegrityError 分支」；
  两个进程同时 drain 的交错没有被观测（SQLite 写锁会串行化，但我不把它写成已证明）。
- 事件表与 `execution_runs.db` 跨文件，做不到与执行记录同事务；选择的失败方向
  （事件可能在执行记录之前存在 ⇒ 最多多发一次且有台账）已写进模块 docstring。
- 后台守护进程有意不做：外部副作用发生的时刻必须是可指认的入口。

## 7. 复算入口

```bash
cd /Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS
# 接线后的产品调用点（应有 cli/commands_outbox.py 与 side_effects.py 命中）
grep -rn "build_rfq_dispatcher\|OutboxQueue(" src/aipd_os | grep -v "side_effects.py"
# 语义 + 接线（25 条）
.venv/bin/python -m pytest tests/test_outbox_dispatcher_semantics.py \
  tests/test_outbox_rfq_wiring.py tests/test_dispatcher.py \
  tests/test_outbox_operations.py tests/test_state_perf_gates.py -q
# 变异反证：把预算判断摘掉 ⇒ 重试预算用例必须红（曾被实测为 handler 调用 20 次）
.venv/bin/python scripts/capability_matrix.py --repo . --out docs/audit
.venv/bin/ruff check src tests state_service && .venv/bin/mypy
```

## 8. 收尾读数（本轮，全部现场复算）

| 门禁 | 读数 |
| --- | --- |
| 全量 `pytest -q --json-report` | **1412 passed / 0 failed / 3 skipped**（重锚清单前那 2 条 manifest 哈希红已随重锚消失） |
| 新增常驻用例 | 28（`test_outbox_dispatcher_semantics.py` 9 + `test_outbox_rfq_wiring.py` 16 + `test_skill_command_surface.py` 3） |
| `ruff check src tests state_service` / `mypy` | 0 / 0（372 个文件） |
| `production_release_gate --release-ready --tag v5.6.0` | **8/8 exit 0**（认证 v5.6.0 那棵树，见 F-REL-01 的读法约束） |
| `state_perf_gate` | PASS：批处理比 0.0467 ≤ 0.34；嵌套事务边际 42.2µs（本机与其他 agent 并发跑测试，绝对值只用于同机趋势，见 `overview.md` 测量口径提醒） |
| `skill_quality_audit` | 0 警告 0 失败（新命令已声明） |
| 能力矩阵 | 总数仍 77；`industrialize.email_execution` 的分类保持 `external_dependency`（真发仍依赖外部 SMTP），只补齐了入口符号、run_command 与 unit_test 引用 |
| 工作树 | `git status --short` 空；提交未 push、tag 未动、bundle 未重签 |

---

# 第二部分 F-EXEC-05 · 「结果未知」必须可见，预算与耗时只能有一处真相

接线闭合后复跑遗留清单时量出来的第二条：上一部分把事件化跑通了，但也留下一个
**只有接线才会出现**的洞。

## 9. 缺陷

1. **未知行凭空蒸发**（上一部分自己造成的）。`mark_unknown` 给事件置
   `completed_at`——它必须离开可领集合，否则超时=可重投=供应商收到两封信。
   代价是这些行从此不在任何 `completed_at IS NULL` 的查询里，包括 `drain` 自己
   唯一的 `pending` 计数。实测一次超时后的读数：`sent=0 / deduped=0 / pending=0`
   ⇒ 三个数都正常，什么都不说。
2. **台账有状态机、有索引、有专用异常，但无人查询、无人 raise**：
   `idx_ext_ops_status`（`migrations/helpers.py:413`）服务的查询全仓不存在；
   `state/errors.py:54 ExternalOperationUnknownError` 的唯一引用是契约测试里
   `issubclass(...)` 那一行——它从来没被 raise 过。
3. **重试预算被写了两遍**：`dispatcher._retry_or_exhaust` 与 handler 各自
   `attempt_count+1 >= max_attempts`，两条腿可以各说各话（事件终止、台账还在
   `FAILED_RETRYABLE`）。实测这是 `src/` 里第 4 份手写预算（另两份在
   `execution_router.py:165-194`、`product_truth/propagation.py:171-205`）。
4. **`duration_ms` 存的是写死的 0**：`execution_router.py` 四处 +
   `runs.record_retry` 一处全部 `duration_ms=0`，而常驻用例的断言是
   `assert rec.duration_ms >= 0` —— 0 >= 0 恒真。数据库里那条耗时字段从来没
   携带过信息。
5. **`PropagationEngine`（带 `backoff_until` 的持久化返工预算）产品侧 0 调用点**：
   `grep` 实测只有它自己 `__init__.py` 的再导出。这是与 outbox 同一类的第四条
   未跟踪遗留，先登记不做。
   **后续（2026-09-25，F-TRUTH-PROP-01）**：这一条已经落了——传播那半条链从
   `aipd truth propagate` / `aipd truth tasks` 可达，并新登记为
   `product_truth.impact_propagation`；`run_rework`（返工的执行）当时判断依然成立：
   没有真实执行器就刻意不接，缺口由
   `tests/test_truth_propagate_cli.py::TestUnwiredHalfStaysVisible` 钉住。
   本轮还顺手量到该引擎一个真实缺陷：`_next_task_id` 原先按 tenant/project 作用域取
   max，而 `task_id` 是全局主键 ⇒ 两个项目各自算出同一个 `RW-001`，第二条直接撞
   `UNIQUE constraint failed`（跨项目实跑撞到，已改为按整表分配并补常驻用例）。

## 10. 修法

- `ExternalOperationRepository.list_unresolved(tenant?, project?, limit)`：
  分母 = `UNRESOLVED_OP_STATUSES`（PENDING / DISPATCHED / ACKNOWLEDGED /
  FAILED_RETRYABLE / UNKNOWN_OUTCOME / COMPENSATING），收口三态
  （SUCCEEDED / FAILED_TERMINAL / COMPENSATED）不进来了。走已有的 `idx_ext_ops_status`。
- 新 CLI 动词 `aipd outbox review`：列未收口台账，**有则 exit 4**（`ok:false` +
  `status:HOLD`），`drain` 的读数里加 `needs_review` 与 `unresolved_statuses`。
- `rfq_send_handler` 对同一幂等键已处于 `UNKNOWN_OUTCOME` 的情况
  **raise `ExternalOperationUnknownError`** ⇒ 重新入队也拒发，等人工核对。
  该异常从此有 raise 点、有常驻用例。
- 预算收敛成 `state/dispatcher.attempt_budget(event) -> (已试次数, 上限, 是否用尽)`
  一处纯函数，事件表与台账都用它；新增配对用例断言两者同时终止。
- 耗时收敛成 `runs.elapsed_ms(start, end)` 一处，`update_run` 在调用方写了
  `end_time` 而没写 `duration_ms` 时派生；删掉 5 处硬编码 0；
  把恒真断言改成 `> 0`，并加 50ms sleep 的下界用例（≥40ms）与
  「显式给了就不覆盖」用例。缺时区/解析不了/回拨一律 `None` 或钳 0，不拿 0 冒充测量。
- CLI 传进去的 `--db` 路径**必须先存在**，否则 exit 2 并说明——绝不替用户建库
  （第一部分 §5-5 那种「在仓库根建了 4 个文件」的事不能再发生）。

## 11. 遗留清单的更正（closure / limits / telemetry 这条基本是陈账）

本轮实测三个模块的调用点后，`overview.md` 里「结构性大项：closure/limits/telemetry 接线」
需要按事实改写，避免下一轮又照着它去「接线」而重复实现已有的东西：

| 模块 | 产品调用点（实测） | 与今天 outbox 的关系 | 裁决 |
| --- | --- | --- | --- |
| `execution/limits.py` 10 个公开名字 | 0（只有 `tests/test_execution_limits.py`） | `RetryPolicy`/`ConcurrencyGate`/`CheckpointStore` 都被事件表的**持久化**版本取代（`attempt_count/max_attempts`、单语句 claim + 租约、`external_operations`）；只有 `DurationBudget` 不是重复，但「进程内累加」对可重启队列是错的形状 | **不再接线**；`RetryPolicy` 明确列为禁止复用项（§9-3 刚清掉一份重复，不迎第二份） |
| `execution/closure.py` + `closure_core.py`（13 个公开符号） | 0（只有两个测试文件） | 重试/返工/成本/进度台账与 `execution_runs` + `external_operations` 三处重复；`telemetry` 无关；它**不含**补偿逻辑，所以接它也修不好 `COMPENSATING→COMPENSATED` 不可达 | 保留但改标为「未接线的实验层」，并登记「三条腿重复记账」为技术债，不再当作待办功能 |
| `telemetry/metrics.py` / `logging.py` | 0；`get_telemetry_logger` 连测试都没有 | 无 sink：`snapshot()/to_json()` 只把 dict 交回调用方，没有任何文件/表/导出 | 接线的前提是先决定「数去哪儿」。当前最小有价值动作是本轮已做的 `duration_ms` 真测量——先把已有的表填对，再谈新指标 |
| `product_truth/PropagationEngine` | 0（新增登记） | 与 dispatcher 的预算重复，但它是**持久化 `backoff_until`** 的那一份 | 登记为第四条遗留；下一轮若做退避，应以它为准而不是再写第三份 |

`docs/audit/IMPRESSION_AND_P2_UX_CLOSURE_2026-08-14.md:125` 早就写过「决定去留
（接入 run_supervisor 或标记实验层并删除）」——本轮给的就是这个决定：**不接入、
标记为实验层、删除留给 owner**（1000+ 行仍在被维护的模块不在自动化轮次里删）。

## 12. 本部分自己制造又抓出的两处（同样登记）

1. **把恒真断言改成 `duration_ms > 0` 造出一个偶发红用例。** 单跑
   `test_success_records_all_fields_and_persists` 永远绿，全量第二次跑就红——
   `doc.generate` 常在 1ms 内完成，墙钟粒度足以让真值就是 0。判据比问题还抖时，
   下一步一定有人把 0 写回去。改法：快路径只钉「派生过且非 NULL」，
   **「真在测量」这个性质下移到 50ms sleep 的用例上钉 ≥40ms**（50 ≫ 1，稳定），
   并在注释里写清为什么这里不用 `> 0`。改完连跑 3 次全绿。
2. **提交信息被 shell 吃掉四处**：`git commit -m "..."` 用双引号时，正文里的反引号
   被当成命令替换执行（四段反引号内容变成空字符串），提交内容完好但信息留下空洞。
   同一个错误还有第二个后果：正文里的 `duration_ms >= 0` 被当作命令执行时，`>= 0` 里的
   `>` 变成重定向，于是**仓库根又多出一个 0 字节文件，名字叫 `=`**（与 §5-5 那四个
   `<pytest_fixture(...)>` 文件同一形状，同样是发布门的 `workspace_clean` 抓出来的）。
   不改写历史（本仓规则：只新增提交），在此登记；后续提交信息一律用 HEREDOC 传。
3. **CLI 拆函数后遗留两个作用域 bug**：`_drain` 里用了只在 `cmd_outbox` 内 import 的
   名字（NameError），以及 `review` 的 `limit` 默认值与 `drain` 混用。都是先写测试
   才立刻暴露的——把仓库根的 `--db` 前提检查写成用例（路径不存在 ⇒ exit 2 且不建库）
   时一起抓到。

## 13. 第二部分收尾读数（现场复算）

| 门禁 | 读数 |
| --- | --- |
| 全量 `pytest -q --json-report` | **1426 passed / 0 failed / 3 skipped** |
| 本轮新增/改写用例 | 14（`test_outbox_reconciliation.py` 10 + 耗时 4，`--collect-only` 现算）；另有 1 条恒真断言换成可失败形状 |
| `ruff` / `mypy` | 0 / 0（371 文件） |
| `production_release_gate --release-ready --tag v5.6.0` | 见本部分末尾（8/8 = v5.6.0 那棵树，非本轮树） |
