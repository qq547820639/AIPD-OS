# F-SWEEP 第 54 片：`aipd truth sweep` —— 发现漂移之后，落刀不再靠人抄 id

日期：2026-09-26 ｜ HEAD 起点 `00858e6`（第 53 片收尾）

## 一、要闭的那格（第 51~53 片各留一次）

第 51 片能**发现**（`truth drift` 只读扫描），第 52 片把五类制品的键都接到"按当前世界重算"，
第 53 片让 `truth rework` 收得了四类制品的返工任务。中间断的一格是三片 §六 都留着的同一句：
**扫描之后要不要 propagate，仍靠人把 `record_id` 抄进命令行**。
读到的分派面事实（不是推测）：`truth propagate` 的 `--upstream` 是
`required=True`（`cli/main.py:578`），并且被命令契约声明为必带
（`cli/command_contract.py:126` `requires_args=frozenset({"--db", "--project", "--upstream"})`）
⇒ "把扫描接进 propagate"要么放宽一条既有命令的契约，要么新开一面。

## 二、技术选型（动手前做完，四段齐全；本轮真实打开了两页官方文档）

**候选清单**

1. **中间 plan 工件**（OpenTofu/Terraform 形状）——出处
   <https://opentofu.org/docs/cli/commands/plan/>（本轮亲开，短摘原文）：
   "You can use the optional `-out=FILE` option to save the generated plan to a file on disk,
   which you can later execute by passing the file to `tofu apply` as an extra argument."；
   "The `plan` command alone does not actually carry out the proposed changes"；
   "By default, the 'apply' command automatically generates a new plan and prompts for you to approve it."
2. **同一套选择器、列与执行各一条命令**（dbt 形状）——出处
   <https://docs.getdbt.com/reference/node-selection/methods>（本轮亲开）：
   "The `state` method is used to select nodes by comparing them against a previous version…
   represented by a manifest"，需 `--state`；`dbt ls --select "state:modified"` 是列、
   `dbt run --select "state:modified"` 是执行。
3. **未检索到（如实记）**：Nx 与 Bazel 两页本轮都没抓到——
   `nx.dev/docs/features/ci-features/affected` 与
   `developer.hashicorp.com/terraform/cli/commands/plan` 两次 WebFetch 都 `fetch failed`。
   不补位、不引用没打开过的页面。

**六维对比**

| 维度 | ① plan 工件 | ② 选择器分面（本仓已有 drift） |
|---|---|---|
| 功能匹配度 | 能把发现与落刀隔成可审计工件，正对本仓"扫描只读、执行靠人记 id" | 同一份"哪些变了"两种消费方式，但无中间工件 ⇒ 审计面弱一档 |
| License | MPL-2.0（OpenTofu），**只借语义不引依赖** | Apache-2.0（dbt-core），同样只借语义 |
| 维护活跃度 | 主流活跃项目（本轮只看文档页，release 频率**未亲验**） | 同左，**未亲验** |
| 安全风险 | 引入"plan 比现实更旧"这一类新洞；OpenTofu 自己靠"apply 默认重算并要求确认"兜底，本仓没这个预算 | 落刀依据是同进程现算的键差 ⇒ 不存在陈旧工件 |
| 代码质量 | 要么把 plan 塞进 `truth drift`（破它自己"一个字都不写"的常驻断言，第 51 片钉死），要么加两条新命令 | 只需一条新命令 + 一次边表查询，**不动任何既有契约** |
| 适配成本 | 新工件格式 + 过期判定 + 对应门禁 | 新增公开命令的镜像一档（第 51 片刚跑通过，成本已知） |

**择一决定**：**借 ② 的语义（检测与执行分面、同一份选择结果两种消费）+ 借 ① 的
"落刀必带可复核依据"，自研一条新命令 `aipd truth sweep`**，**不落 plan 文件**。
理由两条：① 本仓的"检测"那一半已经是 `truth drift`（只读、JSON、退码 4），
再补一个工件等于把同一个事实存两处；② 审计性改由"落刀时把 `stored_signature →
current_signature` 两个键一起打印并写进每条任务原因"提供——事后能问出当时按什么落的刀，
而不引入"工件比现实更旧"。
不选"放宽 `truth propagate`"的理由是内部事实而不是口味：那要改 `--upstream` 的必带语义
与契约 `requires_args`，第 51 片已按同一条理由否过一次"给 propagate 加 `--scan`"。

**落地处**：`src/aipd_os/product_truth/sweep.py`（纯计划）、
`src/aipd_os/cli/commands_truth.py::cmd_truth_sweep`（接线，落刀走
`PropagationEngine.on_upstream_changed` 这个与 propagate **同一个**入口）、
`src/aipd_os/cli/main.py` 子解析器 + `commands.py` 注册 + `command_contract.py` 契约项、
镜像 `SKILL.md`（主线 58→59 与产品事实分组）/ `README.md`（速查块）/
`registry_data.py`（`run_command`、`unit_test`、`current_limitation`）/
`tests/test_command_surface_census.py`（两处手写分母 68→69，附本轮增长理由）。

## 三、判据三条（各有一臂注入证明它有牙）

1. **只认边表交得出的上游**：`graph.upstream_of(rid)` 为空 ⇒ 进 `orphaned`，
   逐条点名不办，绝不"就近挑一条 active 记录"当上游（那会把不相干的东西标成过期）。
   `str(u)` 之前先判原值：`str(None)=="None"` 既非空也不等于自己，会被当成真上游（S3）。
2. **一次调用覆盖一片下游**：两条漂移记录共享上游 ⇒ 只排一刀（S4）。
   已 `stale` 的记录根本不进计划（S1）——否则每次 sweep 都在重烧 attempts。
3. **不新增传播逻辑**：AST 读 `cmd_truth_sweep` 的函数体，必须出现
   `.on_upstream_changed(...)` 调用且**不得**出现 `.set_status(...)`（S5 同时被这两条抓住）。

`--dry-run` 只交计划：这条不是靠叙述，是靠**整表快照逐字段不变 + pending 任务数 0**（S6）。

## 四、效力证明（电池 `/tmp/s54/battery.py`，8 臂：**杀 8 / 活 0 / 注入无效 0**）

对照臂（未注入）rc=0 先行；还原一律写回注入前读到的原文；每臂一原告。

| 臂 | 注入 | 原告（红条数） |
|---|---|---|
| S1 | 已 stale 的记录也进计划 | 2 红（含幂等用例） |
| S2 | 自环：把自己当上游 | `test_plan_ignores_self_loop_and_empty_ids` |
| S3 | `str(None)` 被当成真上游 | 同上 |
| S4 | 共享上游不去重 | `test_plan_calls_one_upstream_even_when_two_records_share_it` |
| S5 | 落刀绕过 propagate 入口 | 4 红（含 AST 接线判据） |
| S6 | dry-run 也写 | `test_sweep_dry_run_writes_nothing` |
| S7 | `ok` 与退码不同向 | 同上（本轮把 `ok is False` 补成断言） |
| S8 | 空库也算"扫过了、没漂" | `test_sweep_on_an_unscannable_world_is_not_reported_as_clean` |

**S7 的第一版是错的，记下来**：我原本造的注入是"把 `unresolved`（落了刀但没建任务）
那一项摘掉"，结果**存活**——顺着它读到 `propagation.py:54-61` 对每个 affected **都**建任务，
所以那个字段恒为空：它不是"判据弱"，是**一个永远不会变的读数被当成信号**。
处置：删掉 `unresolved` 与那一格 payload，换成"退码与 `ok` 同向"这条真有读数的判据（现 S7），
并补一条正向用例把"两个上游指向同一条记录 ⇒ 引擎建两条任务"钉成事实
（`test_two_blades_on_one_record_create_two_tasks`）。

## 五、真库读数（生产路径自己造出来的库，`/tmp/s54/state.db`，项目 `SW-DEMO`）

用真 CLI 依次跑 `bom add` → `cost calc --truth-lineage` → `quote apply --truth-lineage`
→ 再 `bom add` 一行（制造漂移），然后：

```
$ aipd truth sweep --dry-run --json        # rc=4
scanned 3, drifted 2, drifted_active 2, orphaned 0
targets: 上游 T-001 ← T-002(bom_cost) d5991cedf3e6 → 0e21c0476f01
         上游 T-003(quote_batch) ← T-001(bom) 4f9f3f81cf38 → 5837dab973c0

$ aipd truth sweep --json                  # rc=4
T-001 一刀：affected [T-002] newly_stale [T-002] tasks [RW-001]
T-003 一刀：affected [T-001, T-002] newly_stale [T-001] tasks [RW-002, RW-003]
$ aipd truth tasks --status pending        # count 3，每条 reason 都带着那两个键
```

三点都 worth 记：① **第 50 片那条 `quote_batch → bom` 边在这里第一次变成"可执行的依据"**——
`bom` 记录自己漂了也能被落刀，因为它的上游在库里；② 一次 sweep 就把
BOM 版本与那笔成本结论一起收进队列（原来要人抄两次 id）；
③ 第二刀的 `affected` 覆盖两条，于是 `T-002` 拿到 `RW-001` 与 `RW-003` 两条任务——
这是引擎既有语义（每个 affected 都建任务），本轮把它钉成用例而不是当场改它。

## 六、委派与未做到

- 本轮按"机械件交子代理"派了 3 次：第 53 片的执行器审查、第 54 片的生态检索
  —— 两次撞 Chat 日额度（`tool_uses=0` 直接失败）；第 54 片的镜像同步
  跑到一半因**模型连接中断**失败（25 次工具调用，1.7M tokens）。
  事后 `git status` 核实：**它对镜像文件一处未改**（无半成品残留，不需要修复），
  镜像由主理人自己改完并过门禁。⇒ "已交叉复核"这句本轮不写。
- 生态检索只完成到 2 个候选 + 2 页亲开；Nx/Bazel 两页抓取失败已记在 §二。
  这一格是**外部网络/工具限制**，不是本轮偷懒：换源（GitHub raw 或本机缓存）留待下轮补。

## 七、终读数

@@FINAL@@

## 八、遗留

- **§八 的第一版写错了一格，在此按实测更正**：我原写"`drawing_spec` 这类上游是磁盘文件的
  记录仍只点名不办"。真库复算（`/tmp/s54/spec.db`：CTQ → `drawing spec` → 手改声明文件）
  读到的是 `targets: 上游 T-001 ← T-002(drawing_spec) 4d4b60804562 → c275d0081e6f`、
  `orphaned: []` —— 第 43 片那条 `CTQ → 声明记录` 的边让它**有**库里上游，所以 sweep 会落刀。
  代价面随之而来并已钉成常驻用例
  （`test_hand_edited_spec_sweeps_to_the_ctq_and_rework_writes_the_file_back`）：
  人手工改生成出来的声明文件 → sweep 把它标 stale → `truth rework` 按 CTQ **把那个文件覆盖回去**
  （断言改前含 `8.06`、返工后含 `8.05`）。语义不是 sweep 造的（propagate + 第 45 片执行器一直如此），
  但"一条命令就会走到"是本轮开始的，所以代价必须有主人。
  真正"只点名不办"的那一类是**上游压根没有边**的记录（本轮用手工造的孤立 `bom` 记录钉住）。
- 落刀与返工之间仍要人跑 `truth rework`（刻意：执行有配额与退避，不该被扫描顺带触发）。
- 一次 sweep 里多刀命中同一下游会建重复任务（引擎语义，本轮只钉读数未改行为）。
- 本地开发库 `data/state.db` 刻意未打开，存量漂移半径仍未量。

