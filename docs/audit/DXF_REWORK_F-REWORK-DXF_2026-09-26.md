# F-REWORK-DXF 第 47 片：给 `drawing_dxf` 接上返工执行器

日期：2026-09-26 归属：Product Truth 返工闭环 / CAD 出图链路
状态：已闭（执行器 + 命令面分派 + 常驻 14 条 + 电池 9 条 + 四处极性改判 + 一道参数面门禁）
落点：`src/aipd_os/cad/dxf_rework.py`、`src/aipd_os/cli/commands_truth.py`、
`src/aipd_os/cli/commands_drawing.py`（`render_dxf_from_record`）
用例：`tests/test_dxf_rework.py`

## 一、缺口是第 46 片自己造出来的（这是好事）

第 46 片把 `声明 → 图纸` 的边接上之前，`drawing_dxf` 上**根本不会有返工任务**；
接上之后 `aipd truth propagate` 一次就把声明和图纸各生成一条任务
（`tests/test_drawing_dxf_lineage.py::test_third_hop_propagation_reaches_the_drawing` 就是这么钉的），
而第 45 片的执行器只认 `drawing_spec`，于是图纸那条的唯一处置是
「在烧 attempts 之前逐条点名拒掉」。缺口从"没人提"变成"每次传播都产生一批被拒的任务"——
这就是本轮该做的那件事，不是新能力清单上的一项偏好。

## 二、判据形状从哪来（本轮真实读到的 / 明确没读到的）

| 候选 | 来处 | 借走的那一半 | 结论 |
| --- | --- | --- | --- |
| FreeCAD TechDraw 的视图-源对象关系 | **本轮实读** wiki 的 TechDraw View 页：视图靠 `Source` 挂在可绘制对象上，模型改了要显式 `doc.recompute()` 才更新 | 「派生物 + 显式重算」这一步：返工不顺手改文件，而是按记录里那份输入集合重跑一次投影 | 采用（形状，不引依赖） |
| Bazel action key | 第 46 片实读官方 Glossary（Action Cache 是 "a mapping of executed actions to the outputs they created"；Action Key 是 "The cache key of an action"） | 要不要重算**按输入签名判**，不看产物字节 | 沿用本片已有实现 |
| 自己写一份 `generate` 的简化版投影 | 无外部依据 | —— | **否掉**：两份实现对默认值/参数处理一旦有差异，"返工重画出来的图"和"人跑出来的图"会在同一条记录下不同形 |
| Nix fixed-output / content-addressed derivation | **上一轮未读到**（`nix.dev/concepts` 无相关内容、manual 路径 404），本轮也没再查 | —— | 不引用 |

最终形状：执行器**只负责判定与记账**，真正出图由调用面注入的 `render` 完成，
默认实现 `render_dxf_from_record` 调的就是 `drawing generate` 的 handler `cmd_drawing`
（不带 `--db`，走第 46 片写下的「明说的跳过」分支）。**为什么不调 `cli.main`**：
`main → commands → commands_truth → commands_drawing → main` 会成环，
`tests/test_import_cycles.py` 在本轮 886s 的全量里真翻过一次红。
代价是参数面要手工还原成 `argparse.Namespace`，因此补了 `TestRenderArgumentSurface`：
按 AST 从 subparser 反查 `drawing generate` 的旗子清单，还原器漏一个就红。这样 `cad` 层不 import CLI 层，
而失败类判据又能拿假 renderer 在秒级内逐条验。

## 三、四条判据与一条前置纪律

1. **重跑走生产路径**：`render` 内就是 `cmd_drawing(dxf_render_namespace(meta, staged))`，
   参数全部来自版本记录的 metadata（模型来源按记录的 `model_kind`/`model_source` 还原），
   参数面的完整性由 `TestRenderArgumentSurface` 对照 subparser 钉。
2. **只认退码 0**：退码 4 = 图出来了但判未收口（如 `ctq_window_violation`）。把它记成返工成功，
   等于让引擎替我们把一条未收口的事实 bump 成新版本。
3. **先出到暂存目录，确认收口才替换正式产物**：一次失败的返工不许顺手毁掉现状。
   证据侧车 `<name>.dxf.evidence.json` 与图纸一起替换，不留半个新证据配一份旧图。
4. **返工不新增版本记录**：引擎 `run_rework` 成功时 bump 的是**这一条**，所以执行器演进它本身
   （content/metadata 到新签名、`dxf_sha256` 观测刷新）并把边改挂到**当前**那份声明记录上。
   生产面「换输入 ⇒ 另起一版 + 旧版 superseded」的规则刻意不适用——两边不同形是有意的，
   各自有用例钉住（`test_rework_never_leaves_a_second_active_version_on_one_path` vs
   第 46 片的 `test_changed_declaration_starts_a_new_version_and_supersedes_old`）。

前置纪律（延续第 45 片）：**重建不出同一次出图就点名拒，不许猜**。
第 46 片之前写的记录里没有 `model_*`/`material`/`sections`/`details`，
执行器一律 `missing_inputs` 返回失败——拿默认黄金模型 + 空剖切猜一遍，
会把猜出来的图在库里记成"按当前声明重算过"。

## 四、撤改电池（`/tmp/s47/battery.py`，9 条：杀 9 / 存活 0 / 注入无效 0）

对照臂（未注入）rc=0 先立。靶：`test_dxf_rework.py` + `test_drawing_dxf_lineage.py`
+ `test_truth_rework_cli.py`。

| 注入 | 结果 | 半径 |
| --- | --- | --- |
| E1 命令面不再把 `drawing_dxf` 交给执行器 | KILLED | 4 条（unchanged / rewrote / 未收口 / 不换版） |
| E2 不看磁盘现状就判 unchanged | KILLED | 3 条（render 异常 / 哈希不符 / file_restored） |
| E3 签名不参与判定 | KILLED | 3 条（rewrote / 未收口 / 不换版） |
| E4 缺输入不拒 | KILLED | `test_missing_inputs_refuse_instead_of_guessing` |
| E5 上游声明文件读不到降级成「无上游」 | KILLED | `test_unreadable_declaration_file_is_not_read_as_no_upstream` |
| E6 哈希与磁盘不一致也演进记录 | KILLED | `test_render_hash_disagreeing_with_disk_is_not_a_success` |
| E7 退码 4 也算返工成功 | KILLED | `test_a_drawing_that_does_not_hold_is_not_a_successful_rework` |
| E8 未收口的重跑先覆盖正式图纸 | KILLED | 同 E7（打的是该用例里"文件没被覆盖"那一半断言） |
| E9 rewrote 之后不把边连到当前声明记录 | KILLED（第二次） | `test_rework_after_declaration_change_redraws_the_same_record` |

**E9 首版存活，又是一次"docstring 里有、断言里没有"**：补边这件事当时只写在模块 docstring，
没有任何用例的断言指向它——`--json` 的 `edges` 字段没人读。补法不是加一条 print，
而是把断言落在**权威事实**上：返工后 `truth_lineage` 里必须存在
`当前声明记录 → 图纸记录` 这条边；并先断言"声明改了确实产生了两条 spec 版本记录"，
否则这条断言会因为前提塌掉而空转（这正是 [[feedback-instrument-validation]] 说的恒真集合）。

## 五、本轮自己撞出来的三件事（都不是被测代码的错）

`test_a_drawing_that_does_not_hold_is_not_a_successful_rework` 不是设计出来的，是写
"声明变了要重画"这条用例时踩到的：我最初把 CTQ 窗口挪到**不含实测 8.0** 的位置
（第 46 片量过 golden 支架 TOP 四个孔都是 8.0mm），于是重跑出图返回 4。
当时的第一反应是"用例前提错了"，改完就该走人；但停一下想"那真实场景里 CTQ 改到图不达要求怎么办"——
答案就是这条判据：**未收口的重跑既不是返工成功，也不许覆盖现状**。它现在有两个专属断言
（退码原因里点名 `ctq_window_violation`、磁盘哈希前后一致）和两支注入臂（E7/E8）。

另两件是自家量具/结构的问题，都在收口过程中被常驻门禁抓到：

- `test_import_cycles` 在 886s 的全量里翻红：render 里`from aipd_os.cli.main import main` 构成了
  `main → commands → commands_truth → commands_drawing → main` 的闭环。这不是「测试太严」，而是这条边
  确实是新耦合：CLI 模块之间可以互调 handler，但没有一个模块该回头调 `main`。改法即 §二 末段：
  直接调同模块的 `cmd_drawing`，代价（手工还原 Namespace）由新增的门禁补回。
- `TestRenderArgumentSurface` 的提取器第一轮按「子命令名叫 generate」找，撞上 `manual generate` 的 18 个旗子——
  非空前提照样成立，断言却指向一条与本片无关的命令。补的前提：分母必须含`--step/--views/--section`
  且不含 `--prompt/--output-dir`，并要求父子链解析出的目标恰好一个。

## 六、镜像同步与极性改判（一起走，不留半截）

- `truth rework --json` 的 `supported_artifact` 单值 → `supported_artifacts` 列表
  （新用例 `test_rework_cli_now_supports_both_artifacts_and_still_refuses_bom` 钉住，
  同一用例钉 BOM 仍被拒且记录不被打成 blocked）；
- 生产者棘轮 `TestProducerRatchet` 登记 `dxf_rework.py`（本轮它**当场开火**，
  和上一片同一形状）；
- `registry_data.py`：`product_truth.impact_propagation`（执行器从一种制品变两种，
  BOM/成本仍无）、`cad.2d_drawings`（"只有边没有执行器"改判）；
- `docs/architecture/truth_architecture.md`：执行器段 + §七「仍未接上」由两段收一段；
- `README.md` 出图例补一行返工语义；
- 第 46 片取证文档 §七 那句现在时措辞就地更正（保留当时的读数，注明由本片闭合）。

## 七、仍然没接上的（是读数，不是完成度）

- **BOM / 成本那一支既没有血缘生产者也没有返工执行器**；它们的返工任务正确地留在 pending。
- 图纸重跑要求**模型源文件还在原路径**（`--step`/`--native` 记录的是来源）；
  文件被挪走 ⇒ `model_unavailable` 失败，不做"按名字找一份像的"。
- 返工成功但 `edges=0`（上游声明记录连不上）时不判失败——记录已演进，边连不上是
  第 46 片定义过的「点名原因的 0 边」，不是缺牙齿。

## 八、复算入口

```bash
cd /Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS
PYTHONPATH=src:scripts .venv/bin/python -m pytest tests/test_dxf_rework.py \
  tests/test_drawing_dxf_lineage.py tests/test_drawing_spec_lineage.py \
  tests/test_truth_rework_cli.py tests/test_truth_propagate_cli.py -q
.venv/bin/python /tmp/s47/battery.py          # 电池（9 条）
.venv/bin/ruff check src tests
```

## 九、终读数

（收口链跑完后填：全量通过数与耗时、干净 worktree SHA、发布门禁 8/8、
audit_repo 单条按设计红、清单文件数、普查读数。）
