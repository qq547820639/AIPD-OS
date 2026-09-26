# F-REWORK 第 45 片：给 `run_rework` 接上真实执行器

日期：2026-09-26 归属：Product Truth 返工闭环 / 命令面
状态：已闭（产品调用点 + 常驻 8 条 + 电池 5 条 + 极性改判四处）
落点：`src/aipd_os/cad/spec_rework.py`、`src/aipd_os/cli/commands_truth.py`
用例：`tests/test_truth_rework_cli.py`

## 一、这一片欠了三轮

第 31 片接传播时**刻意不接**返工的执行，理由写在代码里：没有执行器时引擎只能输出
`blocked`，而"一条永远不会成功的命令比没有命令更容易被读成返工跑过了"。
当时把缺口钉成断言（`TestUnwiredHalfStaysVisible`，AST 扫 `src/` 里 `run_rework` 的
代码引用必须为空），并写明**接上执行器那一轮必须连同该断言极性一起改判**。
第 43 片让 CTQ 真的能传播到图纸声明之后，"下游有一堆 pending 返工任务"从理论状态
变成日常状态——没有执行器，那些任务就只是挂着。

## 二、判据形状从哪来（两条成熟实现，本轮实读文档）

| 来源 | 读到的机制 | 本片借走的那一半 |
| --- | --- | --- |
| dbt `state:modified`（node-selection 文档） | 拿当前节点签名与 `--state` 指的上一份 manifest 比才判"变了"；纯 cosmetic 字段（tags/meta）变化**刻意不算**变更；`state:modified+` 只重跑受影响下游 | 比较**内容**而不是比较字节：磁盘文件先解析再走同一个 canonical 哈希，缩进/键序不算改动 |
| BitBake（Yocto concepts 文档） | 任务的输入校验和汇成签名；`STAMPS_DIR` 里有"签名匹配的戳文件"才跳过执行；上游签名变 ⇒ 依赖它的任务哈希连锁变 ⇒ 整条链重跑（`BB_SIGNATURE_HANDLER=OEBasicHash`） | **"记录说没变"不等于"产物还在"**：`unchanged` 要求库里的哈希一致 **且** 磁盘产物重算后也一致，否则是 `file_restored` |

两条都不引依赖（dbt 要 project/materialization 模型，BitBake 是 GPL 工具链），
只借判据形状，落本仓已有的 `artifact_version.spec_sha256` 与 `rework_tasks`。

## 三、执行器的三态与一条前置纪律

```
rework_artifact(store, truth_id) ->
  unsupported_artifact / missing_path / gap            → ok=False（交回有界退避）
  unchanged      （哈希一致 且 磁盘一致）              → ok=True，不动产物一个字节
  rewrote        （内容变了）                          → ok=True，重写 + 更新记录 + 补边
  file_restored  （内容没变但文件被删/被改/读不出）      → ok=True，重写补回
```

前置纪律：**不认识的制品不许烧 attempts**。`--all-pending` 会扫到别的制品类型，
CLI 在调用引擎**之前**用 `artifact_kind()` 判一次并逐条点名拒掉。
理由不是省时间——是被烧掉的 attempts 会让"这格还没有执行器"在库里长成
"这条返工尝试过三次都失败"，那是把缺口伪装成结论。

`unchanged` 走 `ok=True` 时引擎仍会 bump 版本、把 stale 关掉：库里必须能区分
"没人跑过"与"跑过且证明未变"，所以这条路径会写 `metadata.last_rework.outcome`，
只是**不动产物文件**。

## 四、撤改电池（`/tmp/s45/battery.py`，5 条：杀 5 / 存活 0 / 注入无效 0）

| 注入 | 半径 |
| --- | --- |
| E1 跳过引擎，直接伪造一次 `succeeded` | 5（含"产品侧真有调用点"那条极性断言） |
| E2 让 `unchanged` 分支走不到（未变也去重写） | 1 |
| E3 不认识的制品也照跑 | 2 |
| E4 重算出 gap 记成成功 | 1 |
| E5 只看记录哈希、不看磁盘现状 | 1 |

E2 与 E5 各自只打断一条——它们必须分开，否则"未变不写"与"文件丢了要补"会被一条
断言混成一个判据，任一半边坏掉都能被另一半蒙过去（对照臂形状沿用第 33/41 片）。

## 五、极性改判清单（一起走，不留半截）

| 位置 | 从 | 到 |
| --- | --- | --- |
| `tests/test_truth_propagate_cli.py` | `TestUnwiredHalfStaysVisible::test_run_rework_is_still_unreachable_from_product_code`（断言 hits 为空） | `TestReworkHalfIsWiredAndItsBoundaryStaysVisible::test_run_rework_has_a_product_call_site_now`（断言非空且落在 CLI 层） |
| 同文件第二条 | 登记里必须还写着「0 调用点」 | 登记里**不许**再写「0 调用点」，且必须写明是谁在跑（`truth rework`）与只认哪类制品（`drawing_spec`） |
| `registry_data` 两行 | `product_truth.impact_propagation` / `industrialize.physical_writeback` 里的 0 调用点说法 | 接线事实 + 边界 + 仍没接的那一半 |
| `docs/architecture/truth_architecture.md` | 「仍然没有任何产品调用点」 | 三态判据、拒烧配额的理由、测试改名后的指针 |
| `commands_truth.py` | 模块 docstring 与 `truth propagate` 的收口提示 | 指向 `aipd truth rework` |

第 43 片的**生产者棘轮当场开火**：`spec_rework.py` 多了一处 `add_edge` 调用点，
`tests/test_drawing_spec_lineage.py::TestProducerRatchet` 立刻红——按登记补进集合即可，
**没有**放宽判据。这条是本轮唯一一次"上一片装的闸替本片把关"。

## 六、仍然没接的那一半（是读数，不是完成度）

- **执行器只认图纸声明**：`DXF / BOM / 成本` 三类制品没有执行器，它们的返工任务正确地
  留在 pending。要接下去，得先有"制品 → 上游 truth"的血缘生产者（第 43 片只补了 CTQ→声明）
  和对应的重算入口。
- **`truth propagate` 的分母仍受 lineage 覆盖限制**：链长过声明那一跳的部分今天还是传不到。
- 命令面：公开命令 56 → 57，`command_contract` 的计数是派生的（`len(PUBLIC_COMMANDS)`），
  但 SKILL 分组清单、SKILL 那句「主线共 N 个」、README 速查、以及命令面 argv 位棘轮的
  分母（66 → 67）都是**手写的镜像**，漏一个就是一堆常驻用例红——本轮那四处全部同批改。

## 七、终读数

- 全量：待本轮收尾（预期 2316 passed / 3 skipped，collected 2319）
- `production_release_gate --release-ready --tag v5.6.0`：待填
- `audit_repo --strict`：待填

## 八、复算入口

```
.venv/bin/python -m pytest tests/test_truth_rework_cli.py -q                    # 8 条
.venv/bin/python -m pytest tests -k "command or skill or surface or contract"   # 命令面镜像
.venv/bin/python /tmp/s45/battery.py                                            # 5 条撤改
aipd truth propagate --db state.db --project P --upstream <CTQ> --json          # 造出 pending
aipd truth rework --db state.db --project P --all-pending --json                # 跑一次真实返工
```
