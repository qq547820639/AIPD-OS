# F-DRAW-01 第 15 片：装配图明细表的材料列，与「哪几行还没有材料」的判据

日期：2026-09-25　范围：`cad.2d_drawings`（材料列）+ `industrialize.release_evidence`（材料覆盖判定）
上一片：`CAD_ASSEMBLY_BOM_LINK_F-DRAW-01_2026-09-25.md`（球标↔BOM 绑定）、
`RELEASE_EVIDENCE_ASSEMBLY_F-DRAW-01_2026-09-25.md`（发布证据分清单件图/装配图）

## 一、本片要收的三件事（任务原文口径）

1. 材料列取值**只认 BOM 行**——与数量同一权威、同一个绑定结果；绑不上留空，
   不写 `-`，也不猜。
2. **决定并写明** `supplier` 是否属于零件图明细表（明细表 vs 采购清单的边界）。
3. 与 release manifest 的材料覆盖一起看：C6 要「材料与工艺」，检查是否有一条判据
   能说出「哪些行还没有材料」。

## 二、调研：拿到什么、没拿到什么（诚信记录）

**没有拿到 ISO 7200 / GB/T 10609.2 / ASME Y14.38 的标准原文。** 具体过程：

- 检索命中的中文页面绝大多数是文档分享站转载（renrendoc / doc88 / 3d66 / so.com /
  baike），不作为判据来源，也未据其下任何结论。
- 真正读到内容的只有一条：RoyMech *Item Reference Numbers and Parts Lists*
  （<https://www.roymech.co.uk/Useful_Tables/Drawing/Item_Ref.html>）。它给出的条目清单是
  **Item / Description / Quantity / Reference / Material**，供货信息只作为
  「其他完成产品所必需的信息（e.g. Supply information）」被提到，**不是**标准列。
- SolidWorks 材料明细表模板页与 DraftSight BOM 对话框页两次抓取**只返回了 CSS，
  正文一个字都没取到**（`help.solidworks.com/2024/.../c_Bill_of_Materials_Templates.htm`、
  `help.solidworks.com/2023/.../r_BOM_dialog_box.htm`）；xometry 那篇返回 403。
  这几条**没有**支持本片任何结论，写在这里只为说明「查过且没查到」。
- GitHub 代码检索（`mcp__github__search_code`，repo:FreeCAD/FreeCAD 三种查询式）
  对 `DrawViewBalloon` 之外的 TechDraw PartList 一律 **0 命中**，
  `get_file_contents` 猜的 `src/Mod/TechDraw/App/DrawViewPartList.cpp` 不存在——
  所以**没有**读到上游 TechDraw 的 BOM 列定义，本片的列集合不引用它。

于是列集合按**本仓自己的契约**裁，这两条是本仓的既有声明，不是我编的：

- `references/production-cad-deliverables.md:3`：C6 生产图纸包至少包括…BOM…**材料与工艺**…。
- `references/deliverable-contracts.md:9`：BOM **每行**必须包含：层级、料号、名称、
  规格/材料、数量、单位、工艺、关键特性、**候选供应商**…
- `references/deliverable-contracts.md:17`：**供应链开发清单**才是要素含「供应商、MOQ、
  模具、交期、A/B源」的那张表。

**候选方案与取舍（六维里真正起作用的三条）**

| 方案 | 功能匹配 | 适配成本 | 结果 |
| --- | --- | --- | --- |
| A. 沿用「有值才长列」的写法，只多加一个 `MATERIAL` 表头 | 能印，但**全部行都没材料时整列消失**，第 3 件事就没法判 | 最低 | 否：把最需要看见的一种情况弄成不可见 |
| B. 列集合跟着**接上的权威**走（BOM 接上 ⇒ QTY/UNIT/MATERIAL 三列恒在，每格独立留空） | 图纸与证据都能回答「哪几行没有材料」 | 低（改 `draw_parts_list` 的门槛 + `bind_bom` 多带一个键） | **选它** |
| C. 引入上游/第三方 BOM 表引擎（TechDraw PartList、ERP 的 BOM 报表） | 列可配置 | 高：本仓锁 ezdxf 1.4.2 无原生 TABLE 写作 API（第 12 片实测），且要把采购侧字段一起搬进受控技术文件 | 否：没有可复用的落点，且方向与第 2 项裁决相反 |

## 三、三条裁决（都可机器核）

1. **材料只有一个来源**：`BomLine.material`，走 `bind_bom` 那**同一个**绑定结果。
   没声明 `bom_item`、声明找不到、有歧义 ⇒ `material` 为 `None`；绑上了但那一行
   本身没填 ⇒ 也为 `None`。**不写 `-`、不写「未指定」**（占位符会被读成图上真有这么个材料），
   也不拿标题栏的 `--material` 回填（那是作者另填的一格，含义不同）。
   manifest 里的 `material` 键与 `quantity` 同遇：解析器两个都不读，所以它进不了零件数据。
2. **供应商不上图**（裁决，不是漏做）。理由：明细表随图纸版本冻结，而供应商是商务事实——
   本仓契约里它只叫「候选供应商」，正式登记在供应链开发清单（`deliverable-contracts.md:17`）。
   把供应商印到受控技术文件上，等于让图纸携带一个未取证就绪的采购承诺。
   要改这条得先给理由，所以裁决写在 `src/aipd_os/cad/assembly.py` 的模块 docstring 里，
   并有一条用例（`test_the_boundary_is_written_in_the_module_that_enforces_it`）
   钉住「代码旁边得留着这句话」——否则下一个人会当成漏做。
3. **发布证据必须说得出「哪些行还没有材料」**：绑上而没材料 ⇒ 阻断项 `material_missing`
   并逐图点名球标；压根没绑上的行**不重复计入**（那是 `assembly_unresolved` 已经判住的事）；
   出图时没接 BOM ⇒ 记 `drawings_without_bom` 这一格**盲区**，不折成 `with_material: 0`。
   「哪几行」一律**逐图读**：多张装配图的球标都从 1 开始编号，拍平成一份清单就分不清
   是谁家的 1 号，所以文档级 `material_coverage` 只聚合数得清的四项。

## 四、改了哪些地方

- `src/aipd_os/cad/assembly.py`
  - `_material_of`（:290）：`line.material or "" → strip() or None`（空白串算「没填」）；
  - `bind_bom`（:302）：行 dict 恒带 `"material"` 键，绑定成功时取 `_material_of(line)`；
  - `draw_parts_list`（:386）：列门槛从 `any("qty" in row)` 改为 **`bom is not None`**，
    三列 `QTY/UNIT/MATERIAL` 恒在；材料格 `row.get("material") or ""`；
  - 模块 docstring：材料并入「已接线」那段，供应商裁决与理由写成一段，
    「未实现」清单里把「明细表不含材料列」换成**工艺/表面处理列**。
- `src/aipd_os/release_manifest.py`：`_check_assembly`（:94）改为返回本图覆盖读数 +
  新增 `material_missing`；`_collect_drawings`（:173）把覆盖挂进各自的图纸引用（局部变量取名 `file_ref`：
     同一函数下游早有 `ref` 用作 CTQ 编号，撞名被 mypy 判红——那是它该管的事）；
  `build_release_manifest`（:358）写 `doc["material_coverage"]`（只聚合四项 + 一句
  `missing_detail` 指向逐图位置）。
- CLI：`commands_drawing.py` 三处文案（绑定成功时点名「数量、单位与材料都来自 BOM」、
  未接 BOM 时「不含数量与材料列」、「没有做的事」改列工艺/表面处理）；
  `main.py` 的 `--bom` 帮助补「与材料」。

## 五、用例（新增 17 条）

- `tests/test_cad_assembly_bom_link.py`：`TestMaterialColumnComesFromTheBom`（:227，8 条）
  与 `TestSupplierIsNotOnTheDrawing`（:339，2 条）。要点：夹具 `_bom` 扩成
  `(item, qty, unit[, material[, supplier]])`，**仍走 `bom_store_path`**（口径不另立）；
  「真画到图上」一条从 `TEXT[layer=="TABLECONTENT"]` 读回 `MATERIAL`/`6061-T6`，
  并断言 `-`、`未指定`、`None` 三种假装有值的写法都不许出现。
- `tests/test_release_manifest.py`：`TestMaterialIsCoveredByTheEvidence`（:428，7 条），
  含「两张装配图各留各的球标号」与「没有装配图就不写这一格」。
- 同批改判（行为变了，不是放松）：`test_columns_grow_only_when_a_bom_is_bound` 与
  命令行那条列断言从 4 列改 5 列；CLI 文案断言换成新措辞，并加断言
  `"材料列" not in text`（命令行不许还在说材料没接线）。

## 六、变异电池：12/12 killed

「红了哪几条」不是推测：把 `-x` 关掉重跑一遍，逐条记下真失败的用例数与代表名（那一轮的原始终出留在 `tmp/slice15-mutation-table.txt`，临时件不入库）。

| # | 改法 | 实测红几条 | 代表用例 |
| --- | --- | --- | --- |
| M1 | 材料改从零件记录取（造第二个来源） | 2 | `test_the_material_of_a_bound_row_is_the_bom_line_material` |
| M2 | 缺失折成 `"-"` | 4 | `test_a_bound_row_without_material_stays_blank_and_holds_no_guess` |
| M3 | 空白串原样当材料 | 1 | `test_whitespace_only_material_counts_as_missing` |
| M4 | 格子写 `str(None)`（看起来有值） | 1 | 同 M2 那条（靠 `"None" not in texts`） |
| M5 | 长列回到「有值才长列」 | 5 | `test_the_material_column_is_there_even_when_no_row_has_one` |
| M6 | 供应商进明细表 | 4 | `test_a_bom_line_supplier_never_reaches_the_parts_list` |
| M7 | 把没绑上的行也算成有权威的行 | 1 | `test_a_row_that_never_bound_is_not_double_counted_as_missing_material` |
| M8 | 盲区折成 0 行 | 1 | `test_a_drawing_that_never_saw_a_bom_is_a_blind_spot_not_a_zero` |
| M9 | `material_missing` 改非阻断 | 1 | `test_a_bound_row_without_material_holds_the_release` |
| M10 | `with_material = bound_rows`（拿位置当计数） | 1 | **首轮存活** → 见下 |
| M11 | 不读明细表（覆盖永远为空） | 5 | `test_full_material_coverage_leaves_no_blocking_issue` 等 5 条 |
| M12 | 点名清单不填（只报数不说是谁） | 3 | `test_the_counted_rows_are_the_ones_the_drawing_did_draw` 等 3 条 |

**M10 首轮存活，暴露的是断言的形状而不是实现的错**：`with_material = bound_rows`
只在「有材料的那一行排在缺材料那行之后」时才算错，而我原先两条用例都恰好把有材料的
放在前面，所以两条都绿。修法是**把混合用例改成缺在前、有在后**，并同时断言
`(bound_rows, with_material) == (2, 1)` 与 `"球标 [1]" in detail`（原先断言 `"1" in detail`
也偏松——那句子开头就带「1 行」，位置计数错了它照样命中）。复跑 12/12。

复现用的 12 个锚点原样抄在这里（脚本本身是临时件，不入库）：

```python
MUTS = [
    ("M1 材料改从零件记录取（第二个来源）", "asm",
     '"material": _material_of(line)', '"material": part.get("material")', [BOM]),
    ("M2 缺失材料折成占位符 \"-\"", "asm",
     '    value = line.material or ""\n    return value.strip() or None',
     '    return (line.material or "-").strip()', [BOM]),
    ("M3 空格串当材料原样上图", "asm",
     '    value = line.material or ""\n    return value.strip() or None',
     '    return line.material or None', [BOM]),
    ("M4 格子写 str(None)（看起来有值）", "asm",
     'painter.text_cell(i, 4, row.get("material") or "")',
     'painter.text_cell(i, 4, str(row.get("material")))', [BOM]),
    ("M5 长列回到「有值才长列」", "asm",
     '    if bom is not None:\n        columns += ["QTY", "UNIT", "MATERIAL"]',
     '    if any(r.get("material") for r in rows):\n'
     '        columns += ["QTY", "UNIT", "MATERIAL"]', [BOM]),
    ("M6 供应商进明细表", "asm",
     'columns += ["QTY", "UNIT", "MATERIAL"]',
     'columns += ["QTY", "UNIT", "MATERIAL", "SUPPLIER"]', [BOM]),
    ("M7 manifest 把没绑上的行也算进有材料的一边", "rel",
     '        if row.get("bom_line_id") is None:\n            coverage["unbound_rows"] += 1\n'
     '            continue',
     '        if False:\n            coverage["unbound_rows"] += 1\n            continue',
     [RM]),
    ("M8 盲区折成 0 行", "rel",
     '        coverage["drawings_without_bom"] = 1',
     '        coverage["drawings_without_bom"] = 0', [RM]),
    ("M9 缺材料只告警不阻断", "rel",
     '"材料没落到图上就不算交齐", blocking=True)',
     '"材料没落到图上就不算交齐", blocking=False)', [RM]),
    ("M10 with_material 直接取 bound_rows", "rel",
     '            coverage["with_material"] += 1',
     '            coverage["with_material"] = coverage["bound_rows"]', [RM]),
    ("M11 不读明细表，覆盖永远为空", "rel",
     'rows = list((evidence.get("parts_list") or {}).get("rows") or [])',
     'rows = []', [RM]),
    ("M12 点名清单不填（只报数不说是谁）", "rel",
     '            coverage["missing_balloons"].append(row.get("item"))',
     '            pass', [RM]),
]
```


顺带记一条自己踩的工具坑：给 registry 那条超长字符串塞了带 ASCII 引号的 `"-"`，
`ast.parse` 与 `py_compile` **全过**（`"... " - " ..."` 是合法的字符串减法表达式），
但 `import` 时 `TypeError` ⇒ 能力表静默变空（`registry_data import failed;
capability registry will be empty`），最后由 3 条用例（`total_capabilities == 0`、
`cap is None`）抓住。**结论：改完字符串数据必须真 import 一次，语法检查不算。**

## 七、端到端实测（真命令行，临时目录，未碰任何开发库）

- `aipd drawing assembly --db state.db --bom BOM-001 …` → rc=0，
  `明细表：2 行，列 ['ITEM','PART','QTY','UNIT','MATERIAL']`；
- 读回 DXF：`TABLECONTENT` 层文本 = `['1','2','4','6061-T6','ITEM','MATERIAL','PART',
  'QTY','UNIT','pcs','set','压板','支架']`（第 2 行材料格为空，没有 `-`/`None`），
  全图任何 TEXT 都不含供应商串 `ACME`（`False`）；
- `aipd release manifest --db state.db --bom BOM-001 …` → **rc=4**，
  `issues=['material_missing']`、`ok=False`，
  `evidence.drawings[0].material = {bound_rows:2, with_material:1, unbound_rows:0,
  missing_balloons:[2], drawings_without_bom:0}`，
  文档级 `material_coverage={bound_rows:2, with_material:1, unbound_rows:0,
  drawings_without_bom:0, drawings_missing_material:1}`。

## 八、连带同步与一处补账

- README 场景 4：材料列进「接上 BOM」那段，新增供应商不上图的裁决、
  「三列在不在只看 BOM 接没接上」，`release manifest` 块从三条判定改四条并写覆盖读数。
- registry：`cad.2d_drawings` 的 `input_output`（QTY/UNIT/MATERIAL 三列）、
  `current_limitation`（材料走同一绑定、占位符禁令、单一材料来源、供应商裁决、
  未做项换成工艺/表面处理列），并**删掉第 12 片留在行内的过时句**
  「本轮未接线故不印任何猜测值」；`industrialize.release_evidence` 行补第四条判定与覆盖字段。
- **补账**：第 13 片的 `tests/test_cad_assembly_bom_link.py` 当时**没有**登记进
  `cad.2d_drawings.unit_test`（本片 grep 到该文件名在 registry 里出现 0 次），
  一并补上——声明面少一栏，等于那片的能力没有测试。

## 九、仍未做（别当已具备）

- 「材料与**工艺**」只落了材料：没有工艺/表面处理列，`BomLine` 侧也没有该字段。
- 爆炸图与装配约束/配合；干涉检查（仍只报包络投影重叠面积）。
- 单件图的明细表不适用（材料在标题栏 MATL 上，那是作者声明的一格，本片未动其默认 `-`，
  也未把行级材料与标题栏材料做一致性判定——两者含义不同，做判定要先说清谁权威）。
- 材料「对不对」不判：本仓不验材料牌号与零件是否匹配，只管有没有落到图上。
