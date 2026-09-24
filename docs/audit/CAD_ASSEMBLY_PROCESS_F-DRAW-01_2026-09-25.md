# F-DRAW-01 第 16 片：明细表的工艺列，覆盖判据分「材料 / 工艺」两半

日期：2026-09-25　范围：`bom.*`（新增 process 字段与就地补列）+ `cad.2d_drawings`（PROCESS 列）
+ `industrialize.release_evidence`（`process_missing` 与 `bom_line_coverage`）
+ 能力表补账（BOM 域本体此前**没有**行）
上一片：`CAD_ASSEMBLY_MATERIAL_F-DRAW-01_2026-09-25.md`（材料列）

## 一、这一片收什么

第 15 片把 C6「材料与工艺」里的**材料**落到了明细表，行内自己写着「只落了材料一半」。
本片收另一半：`aipd bom add --process` → `BomLine.process` → 装配明细表 `PROCESS` 列
→ 发布证据逐图点名「哪几行还没工艺」。供应商维持第 15 片的裁决：**不上图**。

## 二、调研：字段该长在哪儿（两篇真读到的官方文档）

问题不是「要不要工艺」——本仓契约已经写了（`references/deliverable-contracts.md:9`
每行必须含「规格/材料、数量、单位、**工艺**」；`references/production-cad-deliverables.md:3`
C6 要「材料与工艺」）。问题是**建模形状**：单列字符串，还是独立的工序对象。

| 候选 | 真实出处 | 功能匹配 | 适配成本 | 判定 |
| --- | --- | --- | --- | --- |
| A. BOM 行上一列 `process TEXT`（与 `material` 同形） | 本仓契约（工艺写在**每一行**）+ 明细表一行只有**一格** | 恰好是图纸要的那一格 | 低：一个字段、一条 ALTER、一格一列 | **选它**，但语义边界必须写死 |
| B. 独立工序/路线对象，行上只留链接 | Dynamics 365 Business Central *Create production BOMs*：BOM 行字段是 Type / No. / Quantity per / Scrap % / **Routing Link Code**，工序在另一张 **Routing** 里（原文还区分「行上的报废率」与「路线行上的报废率」）；ERPNext v15 *Utilizing and Handling Manufacturing*：BOM 的子表 **BOM Operation** 存 “Workstations, times, and costs”，靠 “With Operations” 开关 | 更真（能放多工序、工时、工序成本） | 高：新表 + CRUD + CLI + 「哪道工序上图」本身是个未决口径 | **不在本片做**，但它改变了 A 的定义 |

**调研实际改变了决策的地方**：因为两家成熟实现都把多工序建成独立对象，A 不能自称工艺真相。
所以 `BomLine.process` 的语义被钉成「**明细表那一格要的那道主工艺/表面工艺**」，
并在 `bom/models.py` 的类 docstring、`cad/assembly.py` 的模块 docstring、registry 行内文字
**三处**写明：工序顺序 / 工时 / 工序成本不建模，要做得先建 operations 表，
别把多工序塞进一个字符串（那会被明细表读成一个工序）。

未取到的：`mcp__github__search_code` 对 `repo:FreeCAD/FreeCAD` 的三种查询式仍 0 命中，
猜的 `src/Mod/TechDraw/App/DrawViewPartList.cpp` 不存在 —— **没有**读到上游 TechDraw 的
BOM 列定义，本片不引用它。ISO/GB 标准原文同样未取到（上一片已记录）。

## 三、迁移：为什么是 store 内就地补列，不是接迁移框架

- `tests/test_migration_freeze.py` 冻结的是**状态库**（V1 schema 哈希 + migration runner
  是唯一建库路径）；`bom.db` 归 `BomStore` 自有，不在那条 registry 里。
- 仓内已有同形状先例：`ProductTruthStore._ensure_columns`（PRAGMA 查列 → ALTER 补齐），
  配套用例 `tests/test_product_truth_scoping.py::test_old_schema_auto_migrates`。
  本片照抄这个形状，并补一条同形状用例 `test_old_bom_library_gets_the_process_column_and_keeps_its_rows`。
- 补出来的列**一律可空**：旧行读出 `None`（= 没填），不给 `NOT NULL DEFAULT ''`——
  空串会被下游当成「有值但为空」，`_bom_text` 的留空规矩就白设了（该形状由变异 P5 杀掉）。

## 四、改了什么（file:line 由写盘时的实际行号取）

- `src/aipd_os/bom/models.py`：`BomLine.process` + 类 docstring 的语义边界 + `to_dict`；
  模块 docstring 的诚实原则补 process。
- `src/aipd_os/bom/store.py`：SCHEMA 加 `process TEXT`；`_ensure_columns`（新）；
  `add_line` 的 INSERT 列与值；`_line` 回读；`update_line` 的可编辑字段集合。
- `src/aipd_os/cli/main.py` / `commands_manufacturing.py`：`bom add --process`，
  回显行同时打印材料与工艺。
- `src/aipd_os/cad/assembly.py`：`_material_of` → **`_bom_text(line, name)`**（材料与工艺
  共用同一处取值规矩，避免两份实现各自漂）；`bind_bom` 行 dict 恒带 `process`；
  `draw_parts_list` 的列集合改为 `QTY/UNIT/MATERIAL/PROCESS`、第 6 格留空规矩同材料；
  模块 docstring 的「未实现」清单把工艺列换成**多工序路线**。
- `src/aipd_os/cli/commands_drawing.py`：绑定成功时打印
  「材料已填 m/n 行、工艺已填 m/n 行，缺的点名到球标」，「没有做的事」换成多工序路线。
- `src/aipd_os/release_manifest.py`：`_check_assembly` 逐行读两格，**两半各一条**阻断判定
  （`material_missing` / `process_missing`）；每图引用里的块名 `material` →
  **`bom_line_coverage`**，字段 `missing_balloons` → `missing_material` + `missing_process`；
  文档级 `material_coverage` → **`bom_line_coverage`**（加 `with_process`、
  `missing_process_drawings`）。改名理由：一个装两半的容器不该叫材料。
- `src/aipd_os/registry_data.py`：`cad.2d_drawings` 与 `industrialize.release_evidence`
  行内文字同步；**新增 `industrialize.bom_model_cost` 行**（见 §七）。

## 五、用例（净 +21 条：三个文件各 +7，`grep -c 'def test_'` 现算 7→14 / 33→40 / 24→31；diff 里新增 22 个 `def test_`、删掉 1 个（第 15 片那条「满覆盖⇒无问题」在新世界不成立，改名改判为「材料齐就不报材料、缺的工艺单独点名」）；另有两条列集合断言 5 列→6 列）

- `tests/test_bom.py`：round-trip、缺省 `None` 不折空串、**逐字段全量 round-trip**
  （`test_a_fully_populated_line_round_trips_every_field`：漏在 INSERT 列表里的字段只有这条抓得住）、
  **模型字段集合 == 表列集合**（`test_bom_line_fields_and_table_columns_agree`：
  两边各自漂的通用守卫）、`update_line` 改工艺、旧库补列、CLI 写读。
- `tests/test_cad_assembly_bom_link.py`（`TestProcessColumnComesFromTheBom`）：绑定值、
  真画到 `TABLECONTENT`、留空不占位、空白串算缺、**两格不许互顶**、manifest 的 process 不读、
  命令行报「哪一半还缺」。夹具 `_bom` 扩成可传 dict（位置参数第五、六格没人读得懂）。
- `tests/test_release_manifest.py`（`TestProcessIsReportedApartFromMaterial`）：缺工艺单独阻断、
  两半分别点名、两半齐了才无问题、没绑上的行不重复计入、盲区一并覆盖两半、
  **工艺值不会渗进材料格**（整图只有工艺时材料照样判缺）、
  以及**逐行不按位置**的那条排列用例。
- 同批改判：第 15 片的「满覆盖 ⇒ 无任何问题」在新世界里不成立（材料齐、工艺缺），
  改为断「不报材料、单独报工艺」；两条列集合断言 5 列 → 6 列。

## 六、变异电池（13/13 killed）

| # | 改法 | 实测红几条 | 代表用例 |
| --- | --- | --- | --- |
| P1 | 材料格子拿工艺凑 | 3 | `test_process_never_borrows_the_material_cell_and_the_other_way_round` |
| P2 | 工艺格子拿材料凑 | 6 | 同上（反向那一半） |
| P3 | 工艺改从零件记录取（第二个来源） | 4 | `test_bound_row_carries_the_process_from_the_bom_line` |
| P4 | 旧库不补列（去掉 `_ensure_columns`） | 1 | `test_old_bom_library_gets_the_process_column_and_keeps_its_rows` |
| P5 | 补列给非空默认（缺工艺被折成空格） | 1 | 同上（`process is None` 那一断） |
| P6 | INSERT 带着列名却不写值 | 3 | `test_a_fully_populated_line_round_trips_every_field` |
| P7 | 明细表不印 PROCESS | 14 | `test_process_is_drawn_and_completes_the_bom_column_set` |
| P8 | 工艺格写 `str(None)` | 2 | `test_a_row_without_process_is_blank_and_the_column_still_exists` |
| P9 | 缺工艺只告警不阻断 | 2 | `test_a_bound_row_without_process_holds_the_release` |
| P10 | 只判材料不判工艺 | 7 | `test_full_coverage_of_both_halves_leaves_no_issue` 等 |
| P11 | 两半合成一条问题 | 6 | `test_the_two_halves_are_named_separately` |
| P12 | 没绑上的行也算缺工艺 | 2 | `test_a_row_that_never_bound_is_not_counted_against_process` |
| P13 | `with_*` 拿位置当计数 | 2 | `test_the_process_count_is_per_row_not_positional` |

P13 是**上一轮 M10 的同类**，这次一开始就配了「缺的那行在前、有的那行在后」的排列，
所以首轮即被杀掉（材料那一半的同样排列由 `test_the_counted_rows_are_the_ones_the_drawing_did_draw`
守住）。每条「红在哪几条」是关掉 `-x` 复跑记下来的。

## 七、补的一处账：BOM 域本体在能力表里根本没有行

动手前查的：`tests/test_bom.py` 在 `registry_data.py` 里出现 **0 次**，
且**没有任何一行的 `implementation_file` 指向 `src/aipd_os/bom/*`**——
也就是说 `aipd bom add / show / release / cost calc` 这条已经发布为 PUBLIC 的产品面
（`command_contract.py` 里 5.10 的三条）在能力表里不可见。这与第 15 片补的那笔账同类
（那片漏的是一个测试文件名，这片漏的是整个域）。
处理：新增 `industrialize.bom_model_cost` 行（domain 工业化与验证，partially_implemented），
写清 4 个实现文件、字段集合、成本口径，以及 limitation：**process 不是工序路线**、
**成本齐备 ≠ 材料/工艺齐备**（后者由 `release manifest` 逐图点名）。
能力总数 80 → **81**，`docs/audit/capability_matrix.{json,md}` 与 `repository_snapshot.json`
由 `scripts/capability_matrix.py` 重新生成（这三个文件不在 SOURCE_MANIFEST 哈希面内）。

## 八、端到端实测（全部走 `aipd` 可执行文件，临时目录，未碰开发库）

```
aipd bom add --part BRACKET-01 --material 6061-T6 --process "CNC 铣削"   # 工艺填了
aipd bom add --part PLATE-02   --material SUS304                        # 工艺没填
aipd drawing assembly --db state.db --bom BOM-001 ...   → rc=0
  明细表：2 行，列 ['ITEM','PART','QTY','UNIT','MATERIAL','PROCESS']
    材料已填 2/2 行，没有缺行
    工艺已填 1/2 行，缺的球标 [2]
aipd release manifest --db state.db --drawing assy.dxf --bom BOM-001    → rc=4
  issues: [('no_ctq', True), ('process_missing', True), ('version_split', False)]
  每图：{bound_rows:2, with_material:2, with_process:1, unbound_rows:0,
         missing_material:[], missing_process:[2], drawings_without_bom:0}
```
读回 DXF 的 `TABLECONTENT` 层：`['1','2','4','6061-T6','CNC 铣削','ITEM','MATERIAL',
'PART','PROCESS','QTY','SUS304','UNIT','pcs','压板','支架']`
——第 2 行的工艺格为空（没有 `-`、没有 `None`），材料两行都有值，全图无供应商串。
（`no_ctq` 是因为这条 e2e 没种 CTQ，与本片无关；`version_split` 非阻断。）

## 九、收口读数（见文末追加）

## 十、仍未做（别当已具备）

- 多工序工艺路线（工序顺序 / 工时 / 工序成本 / 工位）：要做得先建 operations 表；
  成本模型也不会因此自动分工序——`compute_bom_cost` 目前按行乘单价。
- 材料与工艺的**对不对**不判：不验牌号与零件是否匹配、不验工艺是否可执行，只管有没有落到图上。
- 标题栏 `--material`（作者另填的一格）与行级材料/工艺的一致性未做判定——做之前要先定谁权威。
- `release_checklist`（开模可用清单）仍只判成本齐备，不判材料/工艺：这是刻意的分家，
  合并它需要业务口径（「成本齐但材料缺能不能开模」不是本仓能替属主拍的）。
- 爆炸图与装配约束/配合、干涉检查（仍只报包络投影重叠）。
