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

## 5. 本轮自己制造又被抓出的四处（登记以免被当成顺带改动）

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
