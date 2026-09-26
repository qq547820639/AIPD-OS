# F-DRIFT 第 51 片：库自己发现「上游已变、下游还 active」（`aipd truth drift`）

日期：2026-09-26　　轮次：第 51 片　　依据登记：`product_truth.impact_propagation`

## 一、这一轮补的是哪一半

第 48/49/50 三轮把血缘的写侧（生产者）与执行侧（返工执行器）都接上了，
但三轮的 §七 都留了同一句：**传播的触发靠人给 `--upstream`**。
也就是说「报价换了 / BOM 行了 / 声明文件改了」这件事，
库里既不自动传播、也没有任何东西能回答「现在有没有哪条记录已经不对但还挂着 active」。
本片补的是**发现**那一半：一条只读扫描命令。

## 二、技术选型（真实读到两处一手文档，对比之后改变了设计）

读了 dbt《Node selector methods》与 Nx《Run Only Tasks Affected by a PR》两页原文，
加上本仓第 46 片已实读的 Bazel action key，三个候选：

| 候选 | 判「变了」的基准 | 功能匹配度 | License | 维护活跃度 | 安全风险 | 代码质量 | 适配成本 |
|---|---|---|---|---|---|---|---|
| A dbt `state:*` | 与**上一份 manifest** 比；官方明确 body/configs/relations/descriptions 算变更、tags/meta 刻意不算，另有 `state:modified.relation` 逐字段变体 | 语义对得上，但要求每轮留一份基线工件 | Apache-2.0（不引依赖，只借语义） | 活跃 | 无 | 高 | **中**：要新增基线存储 + 「基线何时刷新」的策略 |
| B Nx `affected` | 原文 "Nx uses the Git history and the project graph"：从**真相源现算**再沿图扩散，不存基线 | 高：本仓的真相源就是当前 BOM 行 / 声明文件 / 模型，且每条记录**已经存着自己的输入键** | MIT（不引依赖） | 活跃 | 高 | 高 | **低**：不加表、不加刷新策略 |
| C Bazel action key | 现算输入键与缓存里那份比 | 高，但它判的是**执行时**，不是**审计时** | Apache-2.0 | 活跃 | 无 | 高 | 低 |

**择一决定：走 B 的思路（真相源现算 + 与记录里那份比），键的形状沿用 C。**
这条决定实际改变了设计：**不新建基线表、不做基线刷新策略**——
避开 A 那个坑（基线工件本身会比现实更旧，manifest 过期 ⇒ 该报的漂没报），
而本仓的记录里本来就存着上一份键，等于**基线就住在记录自己身上**。

命令形状也做了对比：给既有 `truth propagate` 加 `--scan` 会把它的
`--upstream`（实测 `cli/main.py:578` 是 `required=True`）从必填改松，
并新增「两个都不给」的退码语义——那是在改一条既有命令的契约；
新开一条只读命令的爆炸半径更小。**选新开命令。**

## 三、做法

- `src/aipd_os/product_truth/drift.py`：纯分类，四态
  `in_sync / drifted / undecidable / no_record_signature`。
  **键的两端都由各类制品自己的 resolver 交出**（`drawing_spec` 存的是 `spec_sha256`
  而不是 `input_signature`；用一个字段名去兜两类记录，会把「读不到那份键」与
  「键确实不同」混成同一种读数——这一点是写第一版时被用例当场打红才发现的）。
- `src/aipd_os/cli/commands_drift.py`：四类 resolver（读声明文件、取模型摘要、
  开 `bom.db` 取当前行）+ 命令与 prose；`product_truth` 层不知道这些路径在哪。
- 接线 `cli/main.py` 子解析器、`commands.py` 的 `COMMAND_FUNCS`、`command_contract.py`。

只读，不改状态。自动把 active 打成 stale 会扩大发布门禁的要求面（第 44 片那条方向），
但一次扫出一大片无人收口的任务是另一件事——先把半径量出来，写侧留给下一轮裁决。

## 四、实测读数

真实库 `/tmp/s50/state.db`（第 50 片留下的：`bom add` → `cost calc --truth-lineage`
→ `quote apply` 把单价从 30 改成 12.5，**没有**再跑 cost calc）：

```
$ aipd truth drift --db /tmp/s50/state.db --project D50
扫描 3 条有效制品记录：一致 0、漂移 2、不可判 1、没有可比对的键 0
  · T-001（bom）状态 stale：键已不同（已被标过，不算待处理）
  · T-002（bom_cost）状态 stale：键已不同（已被标过，不算待处理）
  ? T-003（quote_batch）不可判：这一类制品还没接漂移探测器
rc=4
```

`rc=4` 是去掉管道之后单独测的（第一次读成 0，那是 `| tail` 的退码，同一个坑本仓第三次踩）。
两条漂移都对：报价确实改了单价。**`quote_batch` 落进「不可判」是刻意的**——
它的身份来自一份外部文件，本轮没接 resolver；按 D5 那支注入的教训，
静默跳过会把覆盖率读成 100%，所以必须占一格并说明理由。

## 五、常驻用例与电池

- `tests/test_truth_drift.py` 共 **13 条**：分类器四态各一条、resolver 抛异常归「不可判」
  且带上异常类型与消息、无 `artifact` 字段不许静默丢、未覆盖类型必须落「不可判」并写理由、
  `superseded` 不进扫描面、`should_be_stale` 只数 active、**空库不算通过**、
  真库三条（一致 / 只改 BOM 就被发现 / 第 48 片旧记录归不可判）、
  声明文件改一个数字 ⇒ 漂移（钉 `spec_sha256` 那类键也能吃）、库不存在退 2、
  **跑出漂移之后整表逐字段没动**（只读这句是断言不是叙述）。
- 撤改电池 `/tmp/s51/battery.py`：对照臂 rc=0 先立，7 支注入 **7 杀 / 0 活 / 0 注入无效**，
  每支写回注入前原文并按 sha256 断言还原。
  D1 空库算通过→1 红；D2 不可判折进一致→2 红；D3 已标过的也算待处理→1 红；
  D4 superseded 进扫描面→1 红；D5 未覆盖类型静默跳过→1 红；
  D6 扫描顺手标 stale→1 红；D7 无 artifact 的记录被丢→1 红。
- 新公开命令的镜像全套同步（按登记里「新增公开命令」那一档）：
  `command_contract.py` 加 `CommandEntry`、`commands.py` 的 import 与 `COMMAND_FUNCS`、
  `main.py` 子解析器 + `set_defaults`、`SKILL.md` 分组清单 + 「主线共 57 个」→58、
  README 速查、`registry_data.py` 的 run_command/unit_test/implementation_file 三处、
  `tests/test_command_surface_census.py` 两处手写分母 67 → 68
  （新命令**有** argv 位真调用用例，所以这是合法增长；不改它它会红两次）。
- 一次被门禁抓住的错写法：我先把 `truth drift` 塞进 registry 的 `entry_point`
  （用 `; ` 分隔两条点号路径），`test_capability_entry_surface` 当场红——
  那个字段只接受**单个**可导入 callable。改放 `implementation_file` 与 `run_command`。

## 五点五、两处自抓（都在门禁面上，不是风格问题）

1. **干净检出全量抓出一条本地没跑到的常驻用例**：
   `test_truth_propagate_cli.py::TestReworkHalfIsWiredAndItsBoundaryStaysVisible::test_the_registry_states_what_is_wired_and_what_is_not`
   把 `implementation_file` 当**单条路径**判 `(REPO / 整串).is_file()`；
   本轮把那一行改成 `"; "` 分隔的多文件（登记里别的行早就是这么写的），于是它断言失败。
   报告前置校验把绑定拒了（`exitcode=1`、坏 outcome、`passed+skipped != collected` 三条同时红），
   所以**没有 mint 任何证据**——这正是它存在的理由。
   修法是**加强那条断言**（split 之后每个路径都要存在），不是把登记退回单文件：
   退回就是为了让尺子闭眼。加强后配了一次反向对照——把 `src/nope/gone.py` 放到第二个位置，
   循环确实抓到它（只验第一项的话这里会静默通过）。
2. **一条提交信息里的数写错了**：`Re-anchor` 那次写「650 → 652」，实测清单是 **653**
   （漏算 `tests/test_truth_drift.py`）。不改历史（本地未推送也守"新提交优先"的规矩），
   正确读数记在这里与 §七 的表里。

## 六、仍然没接上的（是读数，不是完成度）

- **发现 ≠ 收口**：命令只报不写。`should_be_stale` 里的记录仍然挂着 active，
  要收口仍得 `truth propagate`（再 `truth rework`）。
- **`quote_batch` 没有 resolver**（它的身份来自外部报价文件），永久落「不可判」，
  直到有人把「报价文件还在不在、内容哈希对不对」接进来。
- **`drawing_dxf` 的 resolver 本轮没有真库端到端用例**（四类里只有它没有集成断言，
  分类器与键形状有断言、`build_resolvers` 的这条分支靠单测覆盖）——下一轮补。
- 扫描是 O(记录数 × 读盘)，没有缓存；库里记录多了之后的耗时未量。
- `data/state.db` 这类本地开发库本轮**刻意没碰**（不拿它当半径来源），
  所以「真实存量库里到底有多少条漂着」仍是未知数。

## 七、终读数

（收尾复算后填）
