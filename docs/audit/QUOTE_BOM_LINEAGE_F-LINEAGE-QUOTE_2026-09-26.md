# F-LINEAGE-QUOTE 第 50 片：给 `artifact=bom` 补上入边（改了报价 ⇒ 那笔成本该重算）

日期：2026-09-26　　轮次：第 50 片　　依据登记：`industrialize.quote_to_bom_cost`、`product_truth.impact_propagation`、F-SUPPLY-03

## 一、改前事实（取证，不是叙述）

全 `src/aipd_os` 按 `add_edge` / `add_fact` / `ProductTruthStore` 三个符号交叉普查（不是按名字 grep）：

- `supply_chain/` 的写点**全是** `db.add_fact(...)`：
  `supply_chain/persistence.py:46,83,118`、`supply_chain/writeback.py:47,78`、`supply_chain/impact.py:108`
  ——**一处 `add_edge`、一处 `ProductTruthStore` 都没有**；
- `artifact=bom` 的版本记录**唯一**写点是 `bom/cost_lineage.py`（只有跑过 `cost calc --truth-lineage` 才存在）。

⇒ `aipd quote apply` 把官方报价的单价**就地写进 BOM 行**之后，
「当初那笔成本是按哪些单价算的」在库里已经变了，而第 48 片登记过的那条成本结论仍是 `active`。
第 48/49 两片 §七 都记了这条，本轮去接。

## 二、技术选型：为什么又没有外部检索（按例外条款明写理由）

本轮唯一的新决策是「报价这一跳的**身份**吃哪些字段、连不上下游不存在时怎么办」：
- 后者本仓已有定案（第 46 片：连不上上游时**记录照写、边数 0、点名原因**），直接沿用；
- 前者由 `ApplyReport`/`Quote` 的字段集合决定，答案在本仓代码里。
判据形状（按输入签名认身份、重算是显式一步、opt-in 旗子 + 明说跳过）分别取自
第 46 / 45+47 / 48 片，那三轮的实读出处写在各自取证文档里（Bazel action key、
Reproducible Builds、dbt `state:modified`、FreeCAD TechDraw）。
⇒ **本片没有做新的外部检索**，也没有查阅任何未实际访问的项目或文档。

## 三、做法

新增 `src/aipd_os/supply_chain/quote_lineage.py`：`quote_input_signature` + `record_quote_lineage`
+ `find_current_bom_record`；接线 `aipd quote apply` 的新旗子 `--truth-lineage`。

- 签名 = 批次币种 + **全部参与判定的报价事实**
  （`quote_id` / 供应商 / 件号 / 版本号 / 状态 / 单价 / 行币种），按 `(quote_id, part)` 排序后规范哈希；
- **来源文件名不进签名**（§四会记它是怎么被抓出来的）；文件路径仍写进 `metadata.source` 当**来源观测**，
  与第 46 片把 `dxf_sha256` 当观测同形；
- 边指向**当前**有效的 `artifact=bom` 记录；找不到 ⇒ 记录照写、`edges=0`、`reason` 点名；
- `applied` 为空 ⇒ 什么都不写；不给旗子是明说的跳过；抛异常 ⇒ `ok=False` 且退码 4。

## 四、实测读数

### 4.1 真实 CLI（`/tmp/s50/state.db`，项目 `D50`，走 `.venv/bin/aipd`）

| 步 | 命令 | 读数 |
|---|---|---|
| 1 | `bom add 支架` + `cost calc --truth-lineage` | bom=`T-001`、cost=`T-002` |
| 2 | `quote apply --file q1.csv --truth-lineage` | `ok=true`；`written=true`、`edges=1`、`quote_record_id=T-003`、`bom_record_id=T-001` |
| 3 | `truth propagate --upstream T-003` | **rc=4**；`affected=[T-001, T-002]`、`marked_stale=[T-001, T-002]`；生成 `RW-001`(T-001) 与 `RW-002`(T-002) |
| 4 | 重放 q1.csv | `written=true`、`created=false`、仍 `T-003`、`edges=1` |
| 5 | 同一批价**换个文件名**再 apply | `created=false`（同一条 `T-003`）——这是把文件名挡在签名外的直接读数 |
| 6 | 新库只有报价、没有任何 BOM 版本记录 | `written=true`、`edges=0`、`bom_record_id=null`、`reason` 点名「要先跑一次 cost calc --truth-lineage」 |

第 3 步是本片的理由：**从报价记录出发，传播一路打到了那笔成本结论**（跨两跳：quote → bom → cost）。
第 6 步那次 `ok` 读成 `false`，是因为那个裸库里根本没有对应的 BOM 行、报价全部 unmatched——
「没连上下游」与「报价本身没落地」是两件事，用例里分开各钉一条
（`test_no_bom_version_record_yet_is_written_but_said_out_loud` 在有 BOM 行、只缺版本记录的形状下
断言 `ok=true` 且退码 0）。

### 4.2 一次被用例逼出来的设计修正

签名初版**把来源文件名吃了进去**。是 `test_replay…` 与 `test_changed_price…` 两条用例
（各自数 `artifact=quote_batch` 的记录数）当场翻红暴露的：
`_priced_bom` 里已经 apply 过一次，再 apply 一个同名/异名文件就多出一版。
顺着查下去，「同一批价换个路径重下载」会另起一版并把 BOM 与成本标 stale，
这和第 46 片「同输入两份 DXF 只差 `$TDCREATE` 两行时间戳」是同一族错——
文件名是来源，不是工程变更。⇒ **把 source 从签名里拿掉**，只留进 `metadata` 当观测，
并补一条**正反对照**：改单价/改币种/改版本/改状态/加一行都必须换签名，
改文件名必须不换（电池 Q9 就是把文件名塞回身份的那支注入，它必须红）。

## 五、常驻用例与电池

- `tests/test_quote_lineage.py` 共 **10 条**：边真的连上、重放与改名命中同一条、
  改价另起一版且两条都指向同一 BOM 版本记录、**传播一路打到成本**、
  没给旗子是明说跳过、写失败判未收口（退码 4 且 `ok` 同向）、
  没有 BOM 版本记录时「记录照写 + 边数 0 + 点名」且 `ok` 不因此变、
  空报价什么都不写、签名的撞键复现（8 个变体两两不同）、生产者已登记。
- 撤改电池 `/tmp/s50/battery.py`：**对照臂 rc=0 先立**，9 支注入 **9 杀 / 0 活 / 0 注入无效**。
  Q1 不连边→2 红；Q2 没有下游时静默→1 红；Q3 空报价也写→1 红；Q4 签名不吃单价→1 红；
  Q5 签名不吃行币种→1 红；Q6 不做按内容复用→2 红；Q7 写失败不改 ok→1 红；
  Q8 没给旗子时静默→1 红；Q9 把文件名算进身份→2 红。
- 电池这一轮教了自己三次，都记下来：
  1. **还原不许用反向 `replace`**。Q5 的注入串短到 `"}\n"`，反向替换命中全文，
     把 `find_current_bom_record` 与函数末行一起吃掉，且**语法仍合法**
     （`meta = rec.metadata or {  "currency": str(a.get("currency"))}` 只在 metadata 为空的记录上才 NameError）
     ——10 条用例照样全绿，是 `ruff` 的 F821 抓到而不是用例抓到。
     改成「写回注入前读到的原文」后不复现。
  2. **Q9 第一版是恒真注入**：把 `"source": "x"` 加进签名字典，所有记录同值 ⇒ 与不注入等价，
     读出 SURVIVED 会被误判成「缺用例」。改成在去重键上真的拼上文件名（会把行为翻过来）才杀掉。
  3. **Q5 第一次存活是真缺陷**：撞键用例只改了**批次**币种，没改**行**币种，
     所以那一列没有任何独立覆盖。补了「只换某一行的币种」这个变体才杀得动。
- 生产者棘轮：`REGISTERED_PRODUCERS` 登记 `src/aipd_os/supply_chain/quote_lineage.py`。
- 镜像同步：`registry_data.py` 三处（生产者计数 四→五、第五处生产者叙述、
  `industrialize.quote_to_bom_cost` 那一行的 run_command/input_output/unit_test）、
  `truth_architecture.md`、README 速查。**只给既有命令加旗子、未新增命令** ⇒
  命令面计数与 census 分母不动（常驻 census 用例复跑见 §七）。

## 六、连带改判

无。本片没有推翻任何既有断言：`quote apply` 原有的
「同文件重放为零新事实/零改价」（`test_quote_to_cost_chain.py`）与
「BOM 侧缺价不改退码」两条都在，新旗子是 opt-in、不给就与改前完全同形。

## 七、仍然没接上的（是读数，不是完成度）

- **触发仍靠人给 `--upstream`**：`quote apply` 写完边之后，
  没有任何东西自动去调 `truth propagate`；库里报价换了、下游仍是 `active` 这一态仍然存在。
- **`artifact=bom` 自己没有返工执行器**：从报价 propagating 会同时生成
  BOM 版本记录与成本结论两条任务，前者仍走点名拒（第 49 片只接了 `bom_cost`）。
- **CTQ 方向仍断**：图纸那条链的根是 CTQ；BOM 这一支的根现在是报价批次，
  「改一条 CTQ 会打到成本」仍然不成立。
- 报价批次记录**没有**执行器，也没有「报价文件与库里记录不符」的常驻判定。

## 八、终读数

（收尾复算后填）
