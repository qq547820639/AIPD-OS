# F-REWORK-COST 第 49 片：给 `bom_cost` 接上返工执行器（按记录重跑核算）

日期：2026-09-26　　轮次：第 49 片　　依据登记：`product_truth.impact_propagation`、`industrialize.quote_to_bom_cost`

## 一、这一轮要接的是哪一段

第 48 片收尾登记里明写「`bom` / `bom_cost` 两类制品没有返工执行器」，并且当场取了证：
`truth rework` 对 `RW-001`（`artifact_kind: bom_cost`）回的是
「本执行器只认 drawing_spec / drawing_dxf；不烧 attempts，这条任务仍是 pending 并如实点名」。

读码时另发现一条更硬的前提（第 48 片 §七 已就地记）：
`src/aipd_os/bom/cost_lineage.py` 写 `bom_cost` 记录时 metadata 里**只有输入签名的哈希**，
没有口径五项的值 ⇒ 光接分派分支也重算不出同一次核算。所以本片的第一步是补生产者，
第二步才是执行器。

## 二、技术选型：为什么这一片没有外部检索

按例外条款明写理由：本轮唯一的新决策是**「返工该不该另起一版」**，
而这个问题的答案在本仓代码里就能定死，不需要外部证据——
`src/aipd_os/product_truth/propagation.py` 的 `run_rework` 成功分支做的是
`self._store.bump_version(task.truth_id)` 并关闭 stale，**作用对象就是这一条记录**；
`rework_fn is None` 时直接标 blocked 且注释写着「绝不伪造成功」。
⇒ 执行器若走生产面（`record_cost_lineage` 会在签名变化时另起新版、把旧版标 superseded），
引擎随后 bump 的就是**被 superseded 的那一条**，收口等于没发生。
判据形状（重算是显式一步、输入签名决定要不要重做、缺输入点名拒）沿用第 45/47 片，
那两轮的实读出处分别是 dbt `state:modified` + BitBake/Yocto concepts（第 45 片）与
Bazel action key + Reproducible Builds 时间戳（第 46 片）。
本片**没有做新的外部检索**，也没有查阅任何未实际访问的项目或文档。

## 三、做法

1. **生产者**（`src/aipd_os/bom/cost_lineage.py`）：`bom_cost` 的 metadata 补上
   `tooling_fee` / `target_quantity` / `amortize_over` / `nre` / `margin_pct` 的**值**。
   版本正文 `version_content` 不变 ⇒ 同输入重跑仍命中同一条（不会因为多存几个字段而另起版）。
2. **共用入口**（`src/aipd_os/cli/commands_manufacturing.py`）：把「取当前 BOM 行 + 装
   `CostInputs` + 算」抽成 `calc_current_cost(...)`，`cmd_cost` 与重算器 `recalc_cost_from_record`
   都调它——两边各留一份「怎么取行」迟早与实现漂移（第 47 片对出图走的是同一条纪律）。
   重算器**不带** `--truth-lineage`：带了就会在 BOM 真的动了时另起一对新版本。
3. **执行器**（`src/aipd_os/bom/cost_rework.py`）：`rework_cost_artifact(store, truth_id, *, recalc)`，
   三态与第 47 片同形（`unchanged` / `recomputed`），失败面五种：
   `unsupported_artifact` / `missing_record` / `missing_inputs` / `recalc_failed` /
   `recalc_incomplete_result` / `bom_moved` / `cost_incomplete` / `recalc_disagrees`。
   `bom` 层不 import CLI 层（`recalc` 由调用面注入），且 `cli/*` 一律不 import `cli.main`。
4. **分派**（`src/aipd_os/cli/commands_truth.py`）：`supported` 由两类变三类，
   `run_executor` 加一条路由；prose 多打一行「重算后总成本 …」。

## 四、实测读数（真实 CLI）

作用域 `/tmp/s49/state.db`，项目 `D49`，命令走 `.venv/bin/aipd`（可编辑安装，跑的是本树 `src/`）。

| 步 | 命令 | 读数 |
|---|---|---|
| 1 | `bom add bracket 12.5` + `cost calc --truth-lineage` | rc=0；bom=`T-001`、cost=`T-002` |
| 2 | 读 `T-002` metadata | `tooling_fee=50000.0`、`target_quantity=1000`、`amortize_over=None`、`nre=1000.0`、`margin_pct=20.0` |
| 3 | `truth propagate --upstream T-001` | rc=4；`T-002` → stale，任务 `RW-001` |
| 4 | `truth rework --task RW-001` | **rc=0**；`supported_artifacts=[drawing_spec, drawing_dxf, bom_cost]`；`refused=[]`；执行器 `outcome=unchanged`、`total=63500.0`、`edges=0`；任务 **succeeded** attempts=1 |
| 5 | 复读记录 | `T-001 active v1` / `T-002 active v2`（**同一条**，version 由引擎 bump）；边仍 1 条 |
| 6 | `bom add cover 3.2×2`（**不**重跑 cost calc）+ propagate | rc=4；`T-002` 再次 stale，任务 `RW-002` |
| 7 | `truth rework --task RW-002` | **rc=0**；`outcome=recomputed`、`total=69900.0`、`edges=1`、`upstream=T-001`；任务 succeeded |
| 8 | 复读记录 | 记录**仍是 2 条**（`T-002 active v3`），正文变成 `bom_cost BOM-001 inputs=531cab84f2f6299b total=69900.0`；边 1 条 |

第 7/8 步就是「返工不新增版本记录」的读数：BOM 动了、金额变了、边重挂了，但有效记录没多一条。

一次自查：第 4 步最初读成 rc=2 且 JSON 为空，是我漏了 `--task/--all-pending`
（命令按设计拒绝「不指定就不知道该跑哪一条」），且我把 stderr 用 `2>/dev/null` 吞掉了；
去掉重定向才看到那句拒绝理由。上表记的是补上参数之后的真实一次。

## 五、一条被改判的常驻断言

`tests/test_dxf_rework.py::test_rework_cli_now_supports_both_artifacts_and_still_refuses_bom`
钉的是「supported 清单只有两类」——那是第 47 片当时**缺口的形状**。
本片接上 `bom_cost` 后它当场翻红，改判方式是**只改清单那一行**（两类→三类并改名），
后半段（`artifact=bom` 仍点名拒、不烧 attempts、记录不许被打成 blocked）原样保留：
那半句今天仍然成立，是这一轮真正留下的缺口。

## 六、常驻用例与电池

- `tests/test_cost_rework.py` 共 **15 条**：1 条生产者落地口径值、
  2 条成功分支各断「有效记录条数不变」、1 条 CLI 端到端收口（含三类清单）、
  1 条 `make_cost_rework_fn` 只回 bool、7 条拒绝面各配一条、
  2 条 AST 门禁（旗子分类 + 「重算器读的键 == 生产者存的键 == 口径五项」）。
  每条拒绝用例都带 `_assert_untouched`：判 `ok=False` 的同时**复读整表**，
  不许拒跑那一支顺手写坏记录。
- 撤改电池 `/tmp/s49/battery.py`：**对照臂（未注入）rc=0 先立**，11 支注入
  **11 杀 / 0 活 / 0 注入无效**，每支按 sha256 还原并核对。
  R1 路由丢失→1 红；R2 清单退回两类→2 红；R3 缺输入不再拒→1 红；R4 异常当成功→1 红；
  R5 不完整也收口→1 红；R6 BOM 换了不拒→1 红；R7 签名不变而金额变照样 bump→1 红；
  R8 不重挂边→1 红；R9 执行器另起一版→1 红（打在「返工不新增版本记录」那条断言上）；
  R10 生产者不落口径值→**11 红**；R11 重算器把 `amortize_over` 硬编成 None→1 红。
  R9 特意写成「add 一条重复记录」这种**能跑通的错实现**，而不是引一个不存在的名字——
  后者只会被测成崩溃而误记为「杀掉」。
- 参数面门禁自己被抓到一次 over-collection：`cli/main.py` 里 `cp` 这个变量名被赋值过三次
  （`cad preflight` / `cad build` / `cost calc`），只按变量名收旗子会把
  `--manifest`、`--target` 一起收进来；且 `ast.walk` 是广度优先，
  按源码顺序推「进没进到这一段」的状态机不成立。
  改成按「该次赋值行号 → 该变量下一次赋值行号」切范围，并加一条**反向对照**
  （`manifest/target/views` 出现即判范围切错）。原第一版还留了一条更弱的前提断言
  （`dests ⊇ {tooling, quantity}`），它在并集里塞进垃圾时照样成立——这类前提断言要写成
  「坏东西不许出现」而不是「好东西够多」。
- 生产者棘轮：`tests/test_drawing_spec_lineage.py::TestProducerRatchet` 登记
  `src/aipd_os/bom/cost_rework.py`（执行器重挂边时确实写 `truth_lineage`）。
- 镜像同步：`registry_data.py` 四处（执行器清单叙述两处、`quote_to_bom_cost` 的 limitation、
  unit_test 列表）、`truth_architecture.md` §二与 §七两处、README 速查加三类制品说明、
  第 48 片取证文档 §七 那句「仍没有执行器」在**原行内**标注已被本片推翻一半。
  命令数与 census 分母未动（只加分派分支，没加命令/旗子）。

## 七、仍然没接上的（是读数，不是完成度）

- **`artifact=bom` 那条版本记录仍没有执行器**：BOM 变动会把「成本结论」这条打上 stale 并能重算，
  但 BOM 版本记录自身的返工任务仍走点名拒那条路。
- **上游方向仍断**：没有任何生产者往 `artifact=bom` 连**入边**（`quote apply` 写的是 `quote.*` fact），
  所以「改一条 CTQ 会打到成本」仍不成立。
- **触发仍靠人给 id**（第 51 片补掉「发现」那一半：`aipd truth drift` 只读扫描能自己指出「登记时的键与当前输入的键不一致」的记录；收口仍要人跑 propagate + rework。原文：`truth propagate --upstream` 取的是 `cost calc` 打印的 `lineage.bom.record_id`。
- 执行器只重算并演进记录，**不写 `facts.cost.total`**（那是命令面的副作用，
  跑一次 `cost calc` 才会刷新）——所以返工之后库里会有「结论已收口、fact 还是旧数」的两态，
  本轮不做这条对账。
- 第 48 片写的旧记录（没有口径值）永久只能 `missing_inputs` 点名拒，本轮不做回填。

## 八、终读数

绑定前同样过那道自建报告校验（`/tmp/s49/verify_report.py`，11 条前提全成立才 mint）：
`root=/private/tmp/s49b`、`exitcode=0`、逐条 outcome 无坏项、
`summary.collected == len(tests) == 2368`、`passed+skipped == collected`、
报告内 `source_commit == tag SHA`、`tests/test_cost_rework.py` 恰 15 条且全 passed、
attested HEAD == 主仓 HEAD。这把尺子本轮先拿上一片的旧报告开过火
（旧报告 5 条前提判红、3 条真成立的判绿），所以它的绿不是恒绿。

| 项 | 读数 |
|---|---|
| 全量（干净 worktree @eea61c8） | **2365 passed / 3 skipped / 0 failed**，968.74s，rc=0 |
| 报告 | `docs/audit/pytest-report-v5.6.0.json`，sha256 `97573ec8717bf5a6…`，`source_commit` = tag SHA |
| 清单 | 646 → **648**（+`src/aipd_os/bom/cost_rework.py`、+`tests/test_cost_rework.py`）；两份清单的 `source_commit` 都保持在 tag SHA |
| `production_release_gate --release-ready --tag v5.6.0` | **8/8 passed，rc=0，`release_ready: true`**（一次就绿：绑定会连带重写 `SOURCE_MANIFEST`，这次与 `PROVENANCE`、报告同一次暂存） |
| `audit_repo --strict` | rc=1，**恰好 1 条 ✗**：`Provenance source commit mismatch: manifest=a66040520139… vs HEAD=13456f35c95d…`（按设计） |
| 撤改电池 | **11 杀 / 0 活 / 0 注入无效**（对照臂 rc=0，见 §六） |
| 镜像后受影响常驻用例 | 92 passed（cost rework/lineage、dxf rework、truth rework CLI、生产者棘轮、命令面 census、能力面/矩阵、文档引用普查、registry 导出、SKILL 命令面、import 环） |
| lint（CI 口径 `ruff check src tests`） | All checks passed |

改判记录（不是放宽）：`tests/test_dxf_rework.py` 那条「supported 清单两类」的常驻断言
按 §五 改判为三类，`artifact=bom` 仍被拒的后半段一字未动。
