# F-DRIFT-4 第 55 片：把漂移扫描的成本形状量成读数，并钉成门禁

日期：2026-09-26 · 分支：main · 相关：F-DRIFT 第 51 片 / F-DRIFT-2 第 52 片 / F-SWEEP 第 54 片

## 一、要拍的问题

第 51~54 片把"发现漂移"和"沿边落刀"接上了，但三片的取证文档都留着同一句：
**没量过成本**。`aipd truth drift` 与 `aipd truth sweep` 每跑一次，都要把库里每条
有效（`active`/`stale`）制品版本记录的输入键**按当前世界重算一遍**
（`src/aipd_os/product_truth/drift.py:scan_drift`），它是这条链上唯一会随交付物数量
长期变大的读路径。要拍的是两件事：

1. 它的成本形状到底是什么——线性？被什么主导？
2. "该不该担心它"这件事，能不能不靠感觉回答（= 有没有一道会红的闸）。

## 二、外部选型（本轮真的改变了落地位置）

### 1. 候选清单（均为本轮亲手打开的页面）

- **dbt《Run results JSON file》** — <https://docs.getdbt.com/reference/artifacts/run-results-json>。
  字段原文：`elapsed_time` = "Total invocation time in seconds."、每节点
  `execution_time` = "Total time spent executing this node"、`timing` =
  "Array that breaks down execution time into steps"（配 `started_at` / `completed_at`）。
- **Bazel《JSON trace profile》** — <https://bazel.google.cn/versions/8.6.0/advanced/performance/json-trace-profile>
  （规范站 `bazel.build` 同页本轮抓取超时，读的是这份镜像）。
  每条记录带 `ph`（事件相位）、`ts`（起始时间戳）、`dur`（微秒耗时）、`name`（人类可读标签，
  如 `"Compiling foo/bar.c"`）、`pid`/`tid`；读法是"按 `dur` 找慢项"，
  且极短的连续事件会被自动合并，要 `--noslim_profile` 才关掉。
- **仓内既有量具** `scripts/state_perf_gate.py`（P2-M10 建，文件头明写"对齐 pytest-benchmark
  的思路，零新增依赖"；绝对档用**相对阈值**棘轮，比值档用**轮内比值**当硬门禁）
  + 常驻硬门禁 `tests/test_state_perf_gates.py`（只放与墙钟无关的断言：查询计划、连接复用计数、
  语句数线性度）。

### 2. 六维对比（针对"要不要在产品面加 per-resolver 计时字段"）

| 维度 | 引 OpenTelemetry Python SDK（span 计时） | 借 dbt/Bazel 的"整次 + 每条"两层形状，落到仓内量具 | 在产品 CLI payload 里加 `timing` 字段 |
|---|---|---|---|
| 功能匹配度 | 能做分布式追踪，本仓是单进程 CLI，用不到 exporter | 正是本轮要的两层读数：整次 ms + 单条 µs | 同样两层，但要改产品面 payload 与四条命令 |
| License | Apache-2.0（可用） | 无新增依赖 | 无新增依赖 |
| 维护活跃度 | 活跃 | 已在仓内跑过 12+ 场景，`--update-baseline` 有既定流程 | 新代码，无既有流程 |
| 安全风险 | 引入 exporter 即引入网络出口（本仓 HTTP 出口已收敛到 `aipd_os.net.http`） | 零新增面 | 零新增面 |
| 代码质量 | 与现有量具并存的第二套计时口径 | 单一口径（同一 `Scenario` 结构、同一 judge） | 计时代码住进判决逻辑，`scan_drift` 要吞一个 sink 参数 |
| 适配成本 | 装包 + 初始化 tracer + 决定导出到哪 | 加两个 `sc_*` 场景 + 一条常驻用例类 | 改 4 条命令的 payload + 契约 + 文档 + 镜像 |

### 3. 择一决定：**借语义 + 复用成熟件，不引依赖、不新增产品面字段**

借的是 dbt 那两层形状（`elapsed_time` 对"整次扫描"、`execution_time`/`timing` 对"每条记录"）
与 Bazel"读数要自带单位与可定位标签"的读法；实现落在**已有量具**上，
所以既不加依赖也不改产品 payload。**决定性的一条是实测**（§四）：
一趟 CLI 的墙钟里扫描本体只占约 10 ms，其余是解释器启动与 import——
给一个被启动开销淹没的量加产品面字段，就是造一格没有读者的格子。

### 4. 落地处

- `scripts/state_perf_gate.py`：新增 `sc_drift_scan_us_per_record` /
  `sc_drift_scan_scaling_ratio` 两个场景（含 `_seed_truth_specs` / `_scan_once`），
  注册进 `SCENARIOS`，模块 docstring 覆盖路径同步；
- `tests/test_state_perf_gates.py`：新增 `TestDriftScanScaling` 三条（含 `_scan_shape`
  这个"扫一次顺便数 SQL 与文件读"的探针）；
- `docs/audit/state_perf_baseline.json`：`--update-baseline` 采集（13 → 15 条）；
- `docs/architecture/truth_architecture.md`：「扫描成本现状」一节；
- `docs/architecture/state_inventory.md`：性能量具那行**去掉手抄的"12 个场景"**
  （抄一次就漂一次），改为"场景数由 `SCENARIOS` 现算"并列出两个新场景名。

## 三、进程内形状读数（与机器无关的那半边）

`TestDriftScanScaling._scan_shape` 在扫描期间给 `ProductTruthStore.connect` 挂
`set_trace_callback`、给 `dxf_lineage.spec_file_digest` 挂计数包装（必须在
`build_resolvers` **之前**挂——resolver 在构造时就把函数绑进闭包，后挂在臂上会静默不计数），
记录数由 `aipd drawing spec` 用的**同一个生产助手** `cad.spec_lineage.record_spec_lineage`
造出来（手写 INSERT 会造出生产路径 never 走过的形状）：

```
$ .venv/bin/python /tmp/s55/shape.py        # 直接调那条常驻用例里的同一个探针
5   (5, 1, 5,   {'in_sync': 5,   'drifted': 0, 'undecidable': 0, 'no_record_signature': 0})
20  (20, 1, 20, {'in_sync': 20,  ...})
100 (100, 1, 100, {'in_sync': 100, ...})
300 (300, 1, 300, {'in_sync': 300, ...})
      ↑扫到几条  ↑SQL 条数  ↑声明文件读取次数  ↑四态计数
```

⇒ **SQL 条数恒为 1**（一条 SELECT 取全集，没有逐条回表），
**声明文件每条恰好读一次**（不重复哈希同一份文件）。两条都写成了常驻断言。

## 四、CLI 三档读数（墙钟那半边，含被推翻的第一版）

量具 `/tmp/s55/rig.py`：三档（每档 N 轮 `bom add` + `cost calc --truth-lineage` +
`drawing spec`，加一批 `quote apply --truth-lineage`）× 两遍 × 每档 7 次重复，
另测"扫不出任何东西"的底噪档；分母前提=库里数出的有效记录数必须等于命令自报 `scanned`。

```
底噪（0 条）中位 4228.6 ms   ← 冷启动，见下
档 (记录数, drift 中位 s) = [(4, 1.4222), (13, 1.3076), (33, 1.3786)]
首末档斜率（粗）：-1.503 ms/条
drift   两遍中位差：tier0 194% / tier1 0% / tier2 3%
sweep   两遍中位差：tier0 257% / tier1 18% / tier2 19%
```

三点读数各自说明一件事：

1. **斜率是负的（-1.5 ms/条）= 效应不可测**，不是"越多越快"。扫描本体 33 条约 3 ms，
   整个差值落在两遍读数的散布里。
2. **首趟读数被冷启动污染**：tier0 第一遍 4.19 s、第二遍 1.42 s（194%），底噪档 4.23 s
   就是同一件事——它是整个会话里第一条被跑的 CLI。**所以第一版的"扣底后 ms/条"字段是假的**
   （负数，`net_ms_per_record=-9.95`），本版改为：底噪只作诊断报出，
   不再拿它去减出每记录成本。
3. **墙钟档答不了"扫描贵不贵"，进程内档才答**：同一批工作在进程内是
   95.2 µs/条（另一趟 131.2 µs/条，跨趟 38% ⇒ 绝对档容差必须放到 60% 才不假红）。
   收尾时机器安静下来（load 从 26 掉到 5.6~6.1）复采，同一条场景读到
   **59.8 / 60.55 / 69.25 µs/条**——即先前那两趟都是**被同机负载抬起来的**。
   于是把基线从 131.24 重锚到 69.25（`--update-baseline`，只重锚这两条），
   方向是**收紧**：留着一个被负载吹大的基线，等于给未来 2× 的劣化留了免检额度。
   重锚后再跑一遍：`性能门禁：PASS`（median 60.55 vs 基线 69.25）。

## 五、两层门禁

- **硬门禁（常驻，与机器无关）**：`tests/test_state_perf_gates.py::TestDriftScanScaling`
  ① 干净库前提（四态必须全 `in_sync`，否则成本读数的不是那条分支）；
  ② SQL 语句数不随记录增长（实测边际 0.00，阈值 0.1）；
  ③ 每条记录只读一次声明文件（`reads == n`，5 条与 30 条两侧都钉）。
- **趋势档（墙钟，相对基线）**：`drift_scan_us_per_record`（容差 60%）、
  `drift_scan_scaling_ratio`（轮内比值，**阈值 2.0**）。
  比值档的阈值是**测出来两遍**的：初版按感觉写 3.0，电池 D4 臂（注入 N+1）实测 median 2.94
  **存活**；收到 1.5 后 D4b（合规侧）在重启后负载下读到单轮 6.44 的离群，两侧余量不对称
  ⇒ 定在 2.0：合规侧 median 观测 0.76 / 0.79 / 0.90 / 1.03，注入侧 median 观测 2.94 / 3.23 / 5.99。
  绝对档 `drift_scan_us_per_record` 由 D5 臂证明**拦不住**"每条多读一次文件"这类 2× 回归
  （注入后 median 134.7 µs vs 基线 131.2 µs，劣化 2.6% 存活）——它的定位是趋势读数，
  真正的回归闸是上面那三条常驻断言。

## 六、变异电池

`/tmp/s55/battery.py` v2，在 detached worktree `/tmp/s55w @ f8b57ca` 上跑；
先跑对照臂（未注入 rc=0），每条臂跑完按原字节写回。
**v1 的三条教训先记在这里**（都进了判据）：`FAILED` 行的解析写错
（`split(" ")[0]` 取到的是 "FAILED" 本身）⇒ 三条明明开火的臂被记成存活；
锚点 `return current, stored, None` 在 `commands_drift.py` 里有 4 处 ⇒ 必须整段两行做锚；
以及必须先用 `python -c "import …; print(__file__)"` 证明 worktree 里的 import
解析到 /tmp 那份（editable 安装默认指向主工作树，不校验就会把"改错文件"读成"门禁没牙"）。

```
$ .venv/bin/python -u /tmp/s55/battery.py      # 对照臂先跑，未注入必须 rc=0
import 解析处： /tmp/s55w/src/aipd_os/product_truth/drift.py
对照臂（未注入）rc=0 ✓ 3 条形状用例全绿
[KILLED]   D1 声明文件每条读两次            → test_each_record_reads_its_spec_file_exactly_once
[KILLED]   D2 每条记录回表重查一次（N+1）    → test_sql_statements_do_not_grow_per_record
[KILLED]   D3 探测器一律按不可判交回         → test_scan_is_all_in_sync_on_a_clean_library
[KILLED]   D4 趋势比值档 阈值 1.5：N+1 必须越线   → rc=1 median 3.229（min 2.58 / max 3.43）
[KILLED]   D4b 趋势比值档：合规侧必须不红         → rc=0 median 0.7644（但单轮 max 6.44）
[SURVIVED] D5 趋势绝对档：重复读文件应越 60% 容差 → rc=0 median 134.665 µs（劣化 2.6%）
SUMMARY killed=5 survived=1 invalid=0
电池结束后 worktree 残留（应为空）： (空)
```

那条 **SURVIVED 是真的没牙**，不是注入无效（同一份注入在 D2 臂上立刻把常驻用例打红）：
绝对毫秒档的量程本来就吃不下"每条多读一次小文件"这种回归，所以 §五 把它明确降级成趋势读数。
D4b 那个单轮 6.44 的离群促使阈值从 1.5 再收到 2.0，收完之后两侧各重跑一遍（`/tmp/s55/d4.py`，
worktree 同步到 `094926f`）：

```
[合规侧] rc=0（要求 0）  median 1.0274  min 0.2722  max 4.7765  stdev 1.6176
[注入侧] rc=1（要求 1）  median 5.9947  min 3.2939  max 7.3341  stdev 1.4678
两侧对照： 成立
```

⇒ 阈值两侧都有实测支撑，且**这台机器重启后的负载让合规侧 median 从 0.76 抬到 1.03**——
这条也写进 `Scenario.note`，防止下一个人把它当精确值复用。


## 七、终读数

@@FINAL@@

## 八、遗留与未证

- **趋势量具不在 CI 里跑**：`.github/workflows/ci.yml` 只跑 `audit_repo` /
  `capability_matrix` / `skill_quality_audit` / `audit_dependency_ack` 四把 script 门禁，
  `state_perf_gate.py` 是手动趋势件（本轮之前就是这个状态，不是本轮新造的洞）。
  所以本轮把**会红的东西放在常驻用例里**，趋势档只答"比上一版慢了多少"。
  要不要把性能门禁接进 CI 是一项待裁（收益=劣化当场拦；代价=CI 时长与墙钟抖动）。
- **底噪档只在单趟会话内可比**：本机 2026-09-27 01:19 左右重启过一次，
  `/tmp` 被清空（第 54/55 片的量具脚本与 v1 电池日志一并丢失），
  且重启后头几分钟的墙钟读数与之前不可直接比——
  本节所有 CLI 级数字都是**重启前**测的，进程内形状数字重启后复算过（见 §七）。
- **`scan_drift` 的绝对毫秒数不是契约**：跨趟 38% 的散布摆在那里，
  本轮没有把它写进任何产品承诺。
- **未证：真实存量的扫描成本**。本地开发库 `data/state.db` 刻意不打开（属主数据），
  所以"今天的库里到底有多少条有效记录、扫一次几毫秒"仍是**未量**，
  已知的是形状（一条 SELECT + 每条一次 resolver）。
