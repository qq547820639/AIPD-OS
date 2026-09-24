# F-DRAW-01 第 12 片：装配图（逐件投影 + 序号球标 + 明细表）

本轮把「多零件」这一维接进二维图纸：`aipd drawing assembly` 吃一份装配清单
（每零件一个 STEP + 作者声明的件号 + 偏移），出一张带序号球标与明细表的 DXF 装配图，
并落 `.evidence.json`。范围、判据、真实读数与踩到的坑都写在下面。

## 一、缺口是「装配无从表达」，不是「再多一种画法」

单件图这一侧已经很厚：六视图、总体尺寸/孔径、尺寸链闭合差、按声明的公差与合格域回查、
GD&T 形位框、剖视与剖切符号、局部放大。C6 生产图纸包（`references/production-cad-deliverables.md`
第 3 行）要的是「总装图 + 零件图 + BOM + …」，缺的不是单件画法，而是**多个零件如何在一张
图上被分别指认**。球标编号正是图纸与 BOM 之间唯一可能的共同语言：没有它，明细表里的
「支架」和图上的某个轮廓之间没有任何可核的对应关系。

## 二、选型调研（真实检索；结论改了两处，其中一处是我自己先写错的引用）

### 2.1 上游到底怎么做球标

真读了 FreeCAD TechDraw 源码（`raw.githubusercontent.com/FreeCAD/FreeCAD/main`，本轮取回）：

- `src/Mod/TechDraw/App/DrawViewBalloon.h` 的属性清单：`SourceView`（指向哪个视图）、
  `Text`、`EndType`、`BubbleShape`、`ShapeScale`、`EndTypeScale`、`OriginX`、`OriginY`、
  `TextWrapLen`、`KinkLength`。
- `src/Mod/TechDraw/App/DrawViewBalloon.cpp:51-54` 的注释：
  「Balloon coordinates are relative to the position of the SourceView / X, Y is the center
  of the balloon bubble / OriginX, OriginY is the tip of the arrow / these are in unscaled
  SourceView coordinates」。
- 同文件 `:67`：`ADD_PROPERTY_TYPE(Text, (""), "", App::Prop_None, "The text to be displayed")`。

结论：**编号是作者写进属性里的字符串，箭头落点也是作者指的**；上游没有「按遍历顺序发号」
这种机制。本仓实现与之一致（编号只认 manifest），差别在落点：FreeCAD 让作者指，本仓
**量出来**（取该零件在该视图里已投影折线的长度加权质心），因为「挂点是不是指对零件」
在本仓是可机器核的判据，而作者手点不是。

> **一处自我更正（要记着）**：`assembly.py` 与本片的测试文件初稿都把上游语义写成
> 「`DrawViewBalloon.ModelIndex`（作者指定）」。本轮按 `ModelIndex` 在 FreeCAD/FreeCAD
> 全仓检索（GitHub code search，`glo=*.cpp`，101 命中全是 Qt 的 `QModelIndex`，TechDraw
> 里 0 命中），再打开 `DrawViewBalloon.h` 逐项核对属性清单 —— **该属性不存在**。
> 也就是说这一句在写下时没有依据。现已改成上面可逐行核对的引用。教训与第 9 片的
> 「记账漂移」同类：引用上游要说得出文件与行，说不出就别写。

### 2.2 候选方案六维对比

| 维度 | A. 合并 compound 一次投影 | B. CadQuery `Assembly` 摆放 + 逐件取形 | C. 逐件投影 + `BRepBuilderAPI_Transform`（**选中**） |
|---|---|---|---|
| 功能匹配度 | 差：归属要靠事后聚类猜 | 中：给出 `(shape, name, loc, color)`，自带约束求解 | 好：投影调用次数 = 零件数，归属由构造保证 |
| License | Apache-2.0（OCP） | Apache-2.0 | Apache-2.0（只用 OCP/CadQuery 的公开 API） |
| 维护活跃度 | 同库 | 本机装 2.5.2，上游最新 release `v2.8.0`（2026-06-20，GitHub API） | 同库，不新增依赖 |
| 安全风险 | 无网络无新面 | 引入 `Assembly.solve/constrain` 的求解器面，本轮用不到 | 最小：只有 STEP 读入 + 刚体平移 |
| 代码质量 | 需自己写聚类 | 依赖 `toCompound()` 的 locate 语义（见下） | 单一职责：读件→摆件→投影→归属 |
| 适配成本 | 低但错 | 需把 manifest 改成 `Location`，并改掉现有 `classify_view` 的入参形状 | 低：`view_basis`/`classify_view`/`_bbox` 原样复用 |

**A 被实测否掉**（本机，两个 20×20×8 盒子）：单盒 **24 条 raw edge**、合成 compound
**48 条**（`TopExp_Explorer(EDGE)`）；`classify_view` 投影出来是 **8 条折线 vs 16 条** ——
几何上一次投得完，条数也正好翻倍，但孔会被全局重编号、`_bbox` 变成并集包络、
`_coincident` 会把「A 的轮廓压住 B 的那条边」判成不存在。归属就从「已知」退化成「猜」。

**B 没有被我的第一版理由否掉**：我原本假设 `Shape.locate()` 会**覆盖** STEP 子实体自带的
TopoDS location，从而静默摆错位置。实测把它否了：给形状先加 +10 偏移（bbox_y `[0,20]`），
再套 `Compound.makeCompound([...]).locate(+45)` 得 `[45,65]`，`BRepBuilderAPI_Transform`
也得 `[45,65]` —— 两条路都正确**叠加**。所以 B 的真实弱点只是：`Assembly.__iter__` 交回的
shape **不带**摆放（实测 PART_B 迭代出来 bbox_y 仍是 `[-10,10]`，loc 单独给），要拿到已摆放
的几何仍得自己走 `toCompound()`；而 `cq.Assembly` 的价值在约束求解（`solve/constrain`），
本轮明确不做约束与爆炸图。结论：B 是「以后做旋转摆放/装配约束时该走的路」，
本轮换成它收益为零、还要改动既有投影入口的入参形状 —— 记录为后续切入口，不在此轮预支。

### 2.3 明细表用什么画

- **ezdxf 原生 TABLE 实体：不可用。** 本机实测 `ezdxf.new().modelspace().add_table`
  不存在，`ezdxf.entities` 里没有 `Table` 类（1.4.2）。
- **`ezdxf.addons.tablepainter.TablePainter`：选中。** 签名为
  `TablePainter((0,0), nrows, ncols, cell_width, cell_height)`、
  `text_cell(row, col, text, span=(1,1), style='default')`、`render(layout, insert=None)`；
  实测一张 3×2 表 render 出 **6 个 TEXT + 17 条 LINE**，落在 `TABLECONTENT` / `TABLEGRID` 两层。
  许可：安装的 dist-info METADATA 里 `License :: OSI Approved :: MIT License`；
  上游无 GitHub Release，最新 tag `v1.4.4`（本机装 1.4.2）。
- **手绘 LINE+TEXT 网格**：能画，但等于复刻 TablePainter，且要自己管单元格尺寸；放弃。
- 实测方向：`insert` 是**左上角**，表体向下长。bbox 按这个方向写，否则证据会把表说成在图纸别处。

## 三、判据为什么可机器核

1. **归属是构造出来的**：投影调用次数 = 零件数；每条 segment 带 `part`；
   用例断言「同一视图里两个零件各自的折线数与自己的投影一致」，而不是断总数。
2. **编号是声明的**：`balloon` 缺失/重号/写 0/零件重名/STEP 不存在一律 `ValueError`
   （命令行 rc=2），且**不落半成品 DXF**（用例直接断 `not out.exists()`）。
   变异 M2 把编号改成 `slot + 1`（按遍历顺序发号）必须红 —— 它红了，说明用例真的在看守「作者说过什么」。
3. **挂点是量的**：引线终点 = 该零件已投影折线的长度加权质心；用例断该点落在**自己**包络内
   且**不**落在别的零件包络内。位移式断言（引线 = 挂点 − 球标边缘）加一条「起点正好落在某个球标圆周上」
   —— 后者正是上一轮抓到 `leader_start` 写反的判据。
4. **「这个视图负不负责任号」是明写的**：`balloon_view` 为真值字段。
   少了它，非编号视图的 `balloons == []` 与「发号那步坏了」在证据里同形。
   这条是本轮新用例**先失败**逼出来的（原断言写 `is None`，实读是 `[]`）。
5. **不越判据下结论**：包络两两投影重叠只报「包络投影重叠 N mm²」，并当场写明
   「不是干涉判定：本轮不做实体求交」。

## 四、真机读数（临时目录，命令行原文，非记忆）

```
$ aipd drawing assembly --manifest assembly.json --out final.dxf --part ASSY-1 --views FRONT,TOP
已出装配图：/tmp/aipd-assy-fSan/final.dxf（A3 1:1.0，2 个零件 / 2 个视图）
  ASSY_FRONT  包络 40.0x10.0mm 实线 17 条 / 虚线 0 条（分段按零件归属：17 段）
        1 支架           可见折线 8 条 / 隐藏 1 条 挂点 (0, 0)
        2 压板           可见折线 8 条 / 隐藏 0 条 挂点 (0, 0)
      球标 2 个，包络投影重叠 160.0mm²
  ASSY_TOP    包络 40.0x65.0mm 实线 18 条 / 虚线 0 条（分段按零件归属：18 段）
        1 支架           可见折线 10 条 / 隐藏 0 条 挂点 (0, -0)
        2 压板           可见折线 8 条 / 隐藏 0 条 挂点 (0, 45)
      本视图不标球标（装配图只在一个视图上编号）
明细表：2 行，列 ['ITEM', 'PART']，绘制方式 ezdxf.addons.tablepainter
  装配告警：ASSY_FRONT：球标 压板、支架 落在视图上的同一个位置 (0, 0)——零件沿投影方向叠着，图上指不出各是谁；换一个能分开零件的视图当球标视图（--views 的第一个）
  装配告警：ASSY_FRONT：零件 支架 与 压板 的包络投影重叠 160.000mm²（不是干涉判定：本轮不做实体求交，只说明图上这两处叠在一起、看不出前后）
  没有做的事：干涉检查（只报包络投影重叠，不做实体求交）、爆炸图/装配约束、明细表数量与材料列（数量权威在 BOM，尚未接线）。
rc=0
```

证据读数：`views = [(ASSY_FRONT, balloon_view=True, 2 球标, 17 段), (ASSY_TOP, False, 0, 18 段)]`，
`parts_list.insert = [20.0, 41.0]`、`bbox = [20.0, 20.0, 88.0, 41.0]`（图框内左下，向上是 41 即 MARGIN+10+表高 21），
`assembly_issues = []`、`assembly_warnings` 2 条，`bytes = 51096`、`sha256 = 7fa8ea66e79d4561…`。

**这段读数本身就抓到一个缺陷**：两个零件沿 Y 偏移，而 FRONT 的投影方向正是 Y，
于是两个球标挂在同一个 `(0, 0)`。图没错、几何没错，但读图的人分不出哪个圈指哪件。
先前 19 条用例全绿也看不见它 —— 位移式与「落在自己包络内」式断言对「两点重合」都不敏感。
补法是先写一条会红的用例（M1 关掉告警必须红），再让它**只作告警**、不改作者的视图顺序。

## 五、落点

- `src/aipd_os/cad/assembly.py`（新增）：清单解析与声明校验、逐件读 STEP（含 sha256 与
  `solid_count`）、`_translate` 刚体平移、`build_assembly_view`（含质心挂点、包络、重叠、
  `balloon_view`、锚点冲突告警）、`parts_list_rows`、`overlap_warnings`、`draw_parts_list`、
  `render_assembly`。
- `src/aipd_os/cad/drawings2d.py`：`ViewGeometry.assembly` 字段；`write_dxf` 新增
  `assembly_parts` / `bom` 入参与 `assembly` / `parts_list` / `bom` / `assembly_issues` /
  `assembly_warnings` 证据键；每视图新增 `segments` / `balloons` / `balloon_view` /
  `envelope` / `overlap_area_mm2`；`_draw_view` 末尾用**同一个 `place`** 调 `render_assembly`；
  装配分支 `_generate_assembly` 拒绝 `--section/--detail`；`_finish_evidence` 抽出共用收尾。
- CLI：`cmd_drawing_assembly` + `main.py` 的 `drawing assembly` 子命令 +
  `command_contract` 一条 PUBLIC 条目（public 48 条，SKILL.md 同步 47→48）。
- `registry_data.py` 的 `cad.2d_drawings`：实现文件、input_output、unit_test、e2e_evidence、
  current_limitation 五处**同一轮**改；另把两行 B-Rep 能力里「装配…仍依赖外部工具」
  改成「装配建模…（二维的装配图与形位框已本地出图）」，避免被读成图纸侧也没做。
- `tests/test_cad_assembly_balloons.py`（新增 27 条）、`tests/test_cad_drawings2d.py`（声明看守收紧）。

## 六、用例与变异（9 条变异全部被杀）

27 条常驻用例（`tests/test_cad_assembly_balloons.py`）。变异跑法见 §九，逐条与结果：

| 变异 | 打红的那条 |
|---|---|
| M1 锚点冲突告警永不发出 | `test_two_parts_collapsing_to_one_anchor_are_reported_as_ambiguity` |
| M2 球标编号改成遍历顺序 `slot+1` | `test_balloon_numbers_come_from_the_manifest_and_the_column_is_ordered` |
| M3 所有 segment 归属写成第一个零件 | `test_each_part_contributes_geometry_and_keeps_its_own_identity` |
| M4 明细表不画 | `TestPartsList`（整类） |
| M5 每个视图都标球标 | `test_only_the_first_requested_view_gets_balloon_numbers` |
| M6 命令行把 hold 吞成 rc=0 | `test_part_without_solids_holds_the_command_at_rc4` |
| M7 `balloon_view` 恒真 | `test_only_the_first_requested_view_gets_balloon_numbers` |
| M8 登记指向不存在的实现文件 | `test_registry_declares_real_entry_and_honest_limitation` |
| M9 登记的 limitation 不再写「不是干涉判定」 | 同 M8 |

M5/M7 是本轮**补出来的**：先前只有圆圈总数在间接看守「只标一个视图」，
补了显式断言后两条变异才各自有了专属看守。变异器本身也修了一处假绿风险：
node id 写错时 pytest 返回 rc≠0 会被误记成「杀掉变异」，现在先跑 baseline、
并对「no tests ran」单独报 INVALID-TEST-ID（M3 的 id 就是这么被抓出来的）。

## 七、顺手发现：同一份登记的两种「存在性」检查形状不一致

`tests/test_cad_drawings2d.py` 原先把 `implementation_file` 当**单个路径**做
`(root / cap.implementation_file).is_file()`，而对 `unit_test` 已经是
「按 `;` 拆开、逐个断存在」。框架侧 `registry.probe_file_has_impl`
（`src/aipd_os/registry.py:194-199`）也按 `;` 拆，但用的是 **`any`** —— 只要有一个存在就算过。
本轮把装配实现登记进去后，那条本地断言立刻红了（它把 `"a.py; b.py"` 整体当路径）。

裁决：不改 `probe_file_has_impl` 的 `any`（它是全仓 80 行的公共判据，改严属于另一个决定，
且会立刻影响别行的读数）；把本 capability 的本地断言收紧成「逐个都存在」，
与同文件 `unit_test` 的写法对齐，并显式断 `src/aipd_os/cad/assembly.py` 在清单里。
M8 证明收紧后的尺子真会红。

## 八、边界（不要当成已具备）

- **没有干涉检查**。只报「包络投影重叠面积」，措辞里当场写明不是干涉判定。
- **球标 ↔ BOM 行没有交叉核对**。`BomLine` 今天没有件号/序号字段，只有自由文本 `item`；
  要核就得复用 `supply_chain/impact` 的 item 归一化全等规则，并把明细表的数量列接到
  BOM 权威上。**本轮一个猜测值都不印**，明细表只有 ITEM/PART 两列；`--spec` 也不在
  装配命令面上（装配视图只有包络尺寸，件级特征公差属于单件图）。
- **装配视图上拒绝剖视与局部放大**（rc=2）。裁剪/切割按合并折线做，会把归属打散，
  球标就成了指错零件的假标注。
- **爆炸图与装配约束/配合未做**。`cq.Assembly.solve/constrain` 是已记录的下一步入口。
- **零件只支持平移摆放**（manifest 的 `offset` 是三个数）。旋转要走 `Location`，与约束一起再做。
- C6 生产图纸包整体仍不成立：缺的是「总装图 + 爆炸图 + ICD + DFA」这一串，不是再一种画法。

## 九、复算

```bash
cd AIPD-OS
.venv/bin/python -m pytest tests/test_cad_assembly_balloons.py -q      # 27 passed
.venv/bin/python -m pytest tests/test_cad_*.py -q                       # 243 passed（含本片）
.venv/bin/python -m ruff check src tests                                # All checks passed
.venv/bin/python -m mypy src/aipd_os/cad/assembly.py src/aipd_os/cad/drawings2d.py \
    src/aipd_os/cli/commands_drawing.py tests/test_cad_assembly_balloons.py
.venv/bin/python -m pytest tests/test_skill_command_surface.py -q       # 3 passed
.venv/bin/python /tmp/mutate_assembly.py                                # 9/9 mutations killed
```

真机命令行（临时目录，不碰仓库产物）：先造两个 STEP + `assembly.json`，再跑 §四 那条命令。

## 十、收尾读数（全部来自本轮实跑输出，非记忆）

- `tests/test_cad_assembly_balloons.py`：**27 passed**。
- `tests/test_cad_*.py`：**243 passed**（本片前为 237；净增 6 条来自本轮补的用例与 CLI 面）。
- `tests/test_skill_command_surface.py`：3 passed；契约 public 条目 **48** 条，
  SKILL.md 的「主线共 48 个」由该用例现算核对，deprecated 侧仍 10 条。
- ruff（`src tests`）：All checks passed。mypy（本片四个文件）：Success, no issues。
- 变异：**9/9 killed**（先 baseline 绿、node id 失效单独报 INVALID）。
- 工作区：提交本片实现后 `git status --short` 只剩本文档与 CHANGELOG/README。
- 未做且不会做在本轮：`git push`、移动 tag、重建 bundle、重签 Ed25519、放宽任何共享发布门禁。
