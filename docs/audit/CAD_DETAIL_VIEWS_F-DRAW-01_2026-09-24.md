# F-DRAW-01 第 9 片：局部放大图（圆形裁剪 + «DETAIL n k:1»），并补记第 8 片漏改的能力声明

本轮把 `cad.2d_drawings` 的「局部放大」从**声明里没有**改成**产品代码真能出**：
`--detail "TOP@(-30,0)/12=2"` 在母视图上画裁剪圈 + 编号，另出一张按 2 倍放的详图，
并把母视图里**落在圈内**的那条实测尺寸带过去（公差与 CTQ 引用一起带）。

## 一、缺口是「读不出来」，不是「不好看」

第 7 片起，位置度偏差已经能数值核对、超带判未收口；但一张 A3 上 1:1 的 Ø8 孔，
字高 3.5mm 的 `±0.02` 与孔本身挤在一起，车间拿尺量图上那 8mm 的圆去对 0.02 的要求——
标注存在但不可读，等于把判定推给了人眼。第 8 片解决的是「剖视在哪里」，这一片解决的是
「紧公差那一处能不能看清」。这在交付图纸上是可读性缺陷，属于交付质量而不是排版偏好。

## 二、选型调研（真实检索，结论改变了实现路线）

先按技术选型规矩检索成熟实现，四路都真查过：

| 候选 | 功能匹配 | License | 维护活跃度 | 安全 | 代码质量 | 适配成本 | 结论 |
|---|---|---|---|---|---|---|---|
| A 复用 FreeCAD TechDraw `DrawViewDetail` | 高（正规 CAD 语义） | LGPL-2.1-or-later | 活跃 | — | 高 | **不可行**：`src/Mod/TechDraw/App/` 内的 C++/Qt 应用模块，无 pip 包，引入等于引入整个 FreeCAD | 借鉴语义，不复用 |
| B `shapely` 2.0.7（`line.intersection(circle.buffer)`） | 中：只裁线，不管视图排版/标注继承 | BSD-3-Clause | 活跃 | 多一个 GEOS 二进制依赖 | 高 | 中：轮子进 `cad` extra；返回 `GeometryCollection` **无序**，缝回折线顺序仍要自己写 | 可用但不划算 |
| C `pyclipper` 1.3.0 / `clipper2` / `pyclipper2` 0.0.8 / `skia-pathops` 0.9.2 | 低：pyclipper 只裁闭合多边形且整数坐标；`clipper2` 这个名字在 PyPI 不存在（404）；`pyclipper2` 0.0.8 无 license 元数据；`skia-pathops` 要求 `>=3.10` | MIT / — / — / BSD-3 | C2 不活跃 | — | — | `skia-pathops` 与本仓 `requires-python >=3.9,<3.13`（CAD 内核只在 3.9 验证）直接冲突 | 排除 |
| D 自研解析式「线段 ∩ 圆」＋既有缝合纪律 | 完全贴合本模块 `ViewGeometry`/尺寸继承/按名溯源 | — | — | 零新依赖 | — | 低（约 50 行） | **选定** |

检索到的关键事实（`https://raw.githubusercontent.com/FreeCAD/FreeCAD/main/src/Mod/TechDraw/App/`
的 `DrawViewDetail.h` / `.cpp`，本轮逐行读过）：`DrawViewDetail : public DrawViewPart`，属性是
`BaseView` / `AnchorPoint`(Vector) / `Radius`；`makeDetailShape()` 用
`BRepPrimAPI_MakeCylinder mkTool(cs, radius, extrudeLength)` 对源形状分别按 SOLID / SHELL / EDGE
做 `FCBRepAlgoAPI_Common` 求交、拼成 `m_detailShape` 后**重新投影**；并且
`m_fudge = 1.01`（`getFudgeRadius() = Radius * 1.01`）——成熟实现自己在兜「正好落在边界上」的碎屑。

**为什么不走 A 的重投影路线**（调研确实改了决策，不是走完全按原计划）：本仓整条溯源链是按
视图前缀名建立的——`cad/gdt.py:96` 的 `by_view = {v.name: v}` 与 `:112` 的
`feature.partition(".")[0]`、`release_manifest.py:117-124` 遍历 `views[].dimensions[].feature`。
重新投影会**重新测量并重新命名**（`DETAIL_1.hole_1`），于是 `--spec` 里写好的
`TOP.hole_1` 全部落进 `spec_unmatched_features`：判据成立的那一侧被换掉了。此外它还要再跑一遍
本仓已知不可靠的相切遮挡判定。所以取 TechDraw 的**圆形局部**语义、shapely 的**裁剪意图**，
实现留在解析式自研。

## 三、判据为什么可机器核

1. **裁掉什么是闭式的**：线段 `a+t(b-a)` 与 `|p-c|<=R` 的交集由一元二次方程给出。夹具
   100×20×10 板、TOP 视图外沿 `v=±10`、裁剪圆心 `(-30,0)` 半径 12 ⇒ 交线在
   `u=-30±√(144-100)`，被裁出的外沿长度精确等于 `2√44 = 13.266499…`，放大 2 倍后
   图上那段必是 `26.532998…`mm。用例直接比这个数（`abs=1e-9`），不靠调容差。
   判别式 `<0` 分支必须再拿**起点到圆心的距离**判全内还是全外——只看起点会整条丢掉全内的线。
2. **放大图的尺寸只继承、不重量**：裁剪窗宽 `2√44`、高 `20` 是「窗」的尺寸，标成
   `overall_width` 就是凭空造一条零件上不存在的尺寸（与「缺声明不折算成 0」同一条线）。
   所以 `overall_*` 一律不带入；链尺寸要求**两端都落在某个孔心上**（以零件边缘为锚的那两段
   不算），否则放大图上会出现一条零件上不存在的 20mm。
3. **继承必须保住特征名**：`TOP.hole_1` 到放大图仍是 `TOP.hole_1` + `inherited_from`，
   否则按名建立的 CTQ 溯源整条断掉。用例正向钉「名字与公差、ctq_ref 三样都在放大图上出现」，
   反向钉「改名会把 `spec_unmatched_features` 打开」（变异 M4 由此被杀）。
4. **整圆在内才算孔**：被圆边裁成开弧的孔**不许**继续报 Ø——开弧量不出圆心。
   `detect_circles` 的闭合 + 角向覆盖判据在裁剪后的几何上重跑，用例两条各钉一侧。
5. **空圈不编号不画圈**：与第 8 片「空剖视不编号」同一条规矩；圆心写错时图纸不该声称
   这里有一张读得清的详图。

## 四、真机读数（黄金件默认模型，临时目录，输出原文）

黄金件 TOP 视图量出 4 个 Ø8 孔（孔心 x=-30/-10/10/30）。第一轮只给 `--detail` 不给 `--spec`：

```
已出图：/tmp/aipd-detail-e2e.y1GOc5/e2e.dxf（A3 1:1.0，4 个视图）
  TOP    100.0x50.0mm 实线 56 条 / 虚线 0 条
         尺寸链 5 段，各段之和 100.0 vs 总体宽 100.0，闭合差 0.0
  FRONT  100.0x10.0mm 实线 34 条 / 虚线 4 条
  SECTION_Y 100.0x10.0mm 实线 60 条 / 虚线 9 条
  DETAIL_1 16.0x16.0mm 实线 2 条 / 虚线 0 条
         放大 ×2 ←TOP 圆(-30,0)/R12：按 2 画，继承尺寸 1 条（母视图上已画裁剪圈）
证据文件：… sha256=7b6f2faf5498719d…
```

`--views TOP,FRONT` 加两份放大（×2 与 ×3）、`--spec` 声明 `TOP.hole_1` 的 `±0.02` 带
`ctq_ref` 与位置度框（`basic=[-30,0]`）：

```
  DETAIL_1 16.0x16.0mm 实线 2 条 / 虚线 0 条
         放大 ×2 ←TOP 圆(-30,0)/R12：按 2 画，继承尺寸 1 条（母视图上已画裁剪圈）
  DETAIL_2 24.0x24.0mm 实线 2 条 / 虚线 0 条
         放大 ×3 ←TOP 圆(30,0)/R12：按 3 画，继承尺寸 1 条（母视图上已画裁剪圈）
公差：声明 2 项、落到图上 3 处（无声明则不写任何公差）
  GD&T 框 TOP→TOP.hole_1：⌖|⌀0.1|A（挂点 [-30.0, -0.0]，来自实测，位置度实测偏差 0 / 带 0.1（合格））
rc=0  sha256=33efb3c593708990…
```

「声明 2 项 ⇒ 印刷 3 处」正是设计：`TOP.hole_1` 在母视图与放大图各印一次（两处印刷、
一条测量），`TOP.chain_2` 一处。放大图 `size_mm` 16×16 / 24×24 是 Ø8 孔的包围盒
（8×8 模型单位）分别 ×2、×3——证明 `drawn_scale` 走的是「全局比例 × 倍数」而不是全局比例。

空圈一侧（`--detail "TOP@(0,80)/5=2"`）实测：

```
         放大 ×2 ←TOP 圆(0,80)/R5：圈空，未编号未标注
  放大未收口：放大圆 (0, 80) R=5 在 TOP 上没圈到任何图线（要么圆心写错，要么那处本来没有几何）
rc=4
```

顺带一条**我自己写错的声明**留下的真机读数：位置度的 `basic` 我初稿写成 `[30.0, 0.0]`
（孔在 -30），第 7 片的偏差核对立刻打出「实测偏差 120 / 带 0.1（超带）」并 rc=4——
那是判据在正常工作，不是回归。

## 五、落点

行号由本轮写文档时在盘上重新解析得到（`wc -l src/aipd_os/cad/drawings2d.py` = 1418）：

- `src/aipd_os/cad/drawings2d.py`：`parse_detail_spec`（`drawings2d.py:637`，写法解析，
  倍数 ≤1 直接拒）、`_circle_hit_interval`（`:672`，一元二次求 t 区间）+
  `_lerp` + `clip_polyline_to_circle`（`:702`，闭式裁剪、按序缝合）、
  `_inherited_dimensions`（`:738`，测点筛选、`overall_*` 与边缘锚链段一律不带入）、
  `detail_view`（`:772`）、`_ratio_text`（`:802`）、
  `assign_detail_numbers`（`:807`，空放大图不编号不挂圈）、
  `_draw_detail_marks`（`:1299`，母视图裁剪圈 + 编号、放大图自己的边界圈）、
  `ViewGeometry` 四个新字段、`assign_section_letters` 里「派生视图不当母视图」扩到放大图、
  `write_dxf` 的 `sc = scale * view.detail_factor` 与 DETAIL 图层、`generate_drawing(details=...)`。
- `src/aipd_os/release_manifest.py`：`_collect_drawings` 跳过带 `inherited_from` 的尺寸——
  同一处测量印两处只算一条覆盖凭据（否则画几张放大图就把分子刷几倍）。
- `src/aipd_os/cli/main.py`：`drawing generate --detail`（可重复）；
  `src/aipd_os/cli/commands_drawing.py`：传参、逐视图放大行、`放大未收口`、
  `held` 加 `detail_issues`、页脚把「未含局部放大」改成「未含爆炸图/装配图」。
- 用例：`tests/test_cad_detail_views.py`（新增 24 条）、
  `tests/test_release_manifest.py`（新增 1 条去重凭据）。

## 六、用例与变异（14 条变异全部被杀）

新增 **25** 条常驻用例（`tests/test_cad_detail_views.py` 24 + `tests/test_release_manifest.py` 1），
全部通过。变异电池逐条应用（每条锚点命中数必须 =1，否则报 NOT-INJECTED 而不是「被杀」；
跑完立刻还原并复算全绿）实测：

| 变异 | 被谁杀 |
|---|---|
| M1 `disc<0` 一律保留 | test_a_line_outside_the_circle_yields_nothing 等 3 条 |
| M2 裁剪每段另起一段 | test_a_closed_circle_fully_inside_stays_a_closed_circle 等 2 条 |
| M3 总体尺寸也继承 | 13 条 |
| M4 继承时改名 | 12 条 |
| M5 链只要求一端在内 | test_only_the_hole_inside…、test_the_crop_window… |
| M6 空放大图照样编号 | test_a_circle_that_catches_nothing… |
| M7 比例一律印 `1:k` | test_the_detail_is_captioned…、test_two_details… |
| M8 放大图按全局比例画 | test_crop_keeps_only_geometry…、test_the_parent_carries… |
| M9 放大图当剖切母视图 | test_a_detail_is_never_a_section_parent |
| M10 不画声明的边界圈 | test_the_parent_carries…、test_two_details… |
| M11 放大图上仍贴 `NAME 1:1` | test_the_detail_is_captioned_and_the_stale_ratio_label_is_gone |
| M12 发布证据不去重继承行 | test_a_detail_view_inheriting_the_tolerance_adds_no_second_coverage |
| M13 母视图名写错静默丢弃 | test_an_unknown_parent_is_a_declaration_error_not_a_silent_drop |
| M14 放大倍数 ≤1 也接受 | test_a_factor_of_one_is_not_a_magnification |

M12 那条用例还带前提断言：先证「同一公差确实印了两处」（`printed == ["TOP", "DETAIL_1"]`），
再判「只算一条覆盖」——不然它会因为压根没印而假绿。

## 七、顺手发现的一处记账漂移（第 8 片漏改，本轮补）

用 `git show 28160b5 -- src/aipd_os/registry_data.py` 逐字段比对第 8 片那次提交：
`cad.2d_drawings` 行**只改了 `unit_test`**（追加 `tests/test_cad_section_symbols.py`），
`input_output` 与 `current_limitation` 一字未动，于是能力声明连着整轮声称
「但未做剖切符号 A-A」「剖切符号/局部放大/爆炸图/装配图未做」——与同一行自己的测试清单矛盾。
方向上是**低报**（不会假绿放行），但它证明：现有声明门禁只核 `implementation_file`
可 `import`、`entry_point` 可解析、`unit_test` 文件存在（`is_file()`），**不核散文字段是否过期**。
本轮把两句都改对，并把「散文字段与测试清单同轮更新」记进 §九 的复算清单当一条人肉核对项；
是否值得为它加一条机检（同一 commit 内 `unit_test` 变了而 `current_limitation` 没变即告警）
列为候选门禁，未自行开工。

另外更正一处我自己的历史记录：上一轮收尾时我记成「第 8 片已同步 limitation」，
diff 显示并非如此。**以 diff 为准。**

## 八、边界（不要当成已具备）

- 放大图是母视图**已判定**几何的二维裁剪，不是重新投影：母视图的可见/隐藏结论（含相切
  边界只判出一侧那条已知缺陷）原样带进放大图。这一点写进 `drawings2d` 模块 docstring 与
  registry 的 `current_limitation`，不宣称比母视图更正确。
- 形位框只贴在母视图上（框按 `视图名.特征` 解析，放大图没有独立名字可解析）。这是现状，
  不是「已实现放大图上的形位标注」。
- 同一处公差在母视图与放大图各印一次：图纸上属重复标注（本仓刻意保留，因为放大处的可读性
  是目的）；发布证据侧已按「一条测量」去重，不据此多算覆盖。
- 放大图不重排尺寸行（不做「把标注从母视图移到放大图」的搬迁），也不做局部剖。
- **母视图允许是剖视**（`--detail "SECTION_Y@(-30,0)/12=2"` 出得来），但本轮裁剪只处理
  折线，**不裁材料区**：从剖视放大出去的图有线无剖面线。这一条由
  `test_a_section_may_be_a_parent_but_its_hatching_is_not_cropped` 钉成机器可读事实
  （`det["cut_regions"] == 0` 而母剖视 `> 0`）——它是**边界声明不是永久基线**：
  补上裁剪 `cut_regions` 的那一轮必须连同这条断言一起翻极性，别让它悄悄固化。
  同一轮里 `SECTION_Y` 上没有整圆孔（筒壁投成两条竖线），所以那种放大图一条尺寸都不继承，
  这也是断言之一：没有测点就不硬凑尺寸。
- 圆内无任何图线判未收口（rc=4）；圆心/半径/倍数写错一律 ValueError（rc=2），不外推。
- 母视图比例非 1:1 时，裁剪圈半径按母视图比例画，`radius` 仍是模型单位——用例注释里写明了
  这条换算，避免读图时误判。

## 九、复算

```bash
cd AIPD-OS
.venv/bin/python -m pytest tests/test_cad_detail_views.py tests/test_release_manifest.py -q
.venv/bin/python -m ruff check src tests state_service
.venv/bin/python -m mypy src tests
W=$(mktemp -d) && .venv/bin/aipd drawing generate --part plate-e2e \
  --views TOP,FRONT --detail "TOP@(-30,0)/12=2" --detail "TOP@(30,0)/12=3" \
  --spec "$W/spec.json" --out "$W/tol.dxf"      # rc=0，「声明 2 项、落到图上 3 处」
```

变异复算：§六 表里每条都给出**唯一锚点文本**（`tmp/mut_detail.py` 只在本轮存活、未入库），
逐条把锚点替换成右列写法、跑 `tests/test_cad_detail_views.py`（M12 跑 manifest 那条）、
再还原。要点是替换前断言锚点在文件里命中数 =1，否则那条变异根本没注入成功——
「跑绿了」和「没打上变异」长得一模一样。

散文字段一致性（本轮的人肉核对项）：`registry_data.py` 里 `cad.2d_drawings` 的
`input_output` / `current_limitation` / `unit_test` 三者都提到局部放大与剖切符号，
且不再出现「局部放大未做」。

## 十、收尾读数（全部来自本轮实跑输出，非记忆）

- 新增用例：**25 条**（`tests/test_cad_detail_views.py` 24 + `tests/test_release_manifest.py` 1）。
- `mypy src tests`：**Success: no issues found in 391 source files**（上一轮 390，+1 个新测试文件）。
- `ruff check src tests state_service`：All checks passed。
- 变异电池：**14/14 全部被杀**，无幸存项（故本轮不需要中途补断言）；每条还原后复算全绿
  （电池脚本在还原不绿时返回 3 而不是 0）。
- 重锚前全量 **1621 passed / 2 failed / 3 skipped**（两条仍是 packaging 的 manifest 哈希核对，
  改了受跟踪源码未重锚时必红，不是回归）；重锚后 **1623 passed / 0 failed / 3 skipped**（131.83s）。
- 产物重锚：`RELEASE_MANIFEST.json` **589 个文件**，两次重锚内容一致 ⇒ 受跟踪源码集在两跑之间未动。
- 一处**流程自纠**（记下来因为它改了产物提交）：第一次产物提交里的报告 `source_commit` 是 HEAD
  （`67064cf`），门禁 `test_numbers_from_report` 立刻按 tag 锚点判 `report STALE` 并 rc=2。
  这条红是 F-REL-01 那条防陈旧报告判据在正常工作，不是回归：`tests/conftest.py:24` 先读
  `AIPD_SOURCE_COMMIT`，没设就退回 HEAD，而我漏设了。补设后重跑，`PROVENANCE.test_report`
  记为 `passed=1623 failed=0 source_commit=a6604052013…`（= tag v5.6.0 指向的提交）。
- `production_release_gate --release-ready --tag v5.6.0`（文档提交、工作区干净之后跑）与
  `skill_quality_audit` / `state_perf_gate` 的读数：记在下一节末（门禁必须在工作区干净时跑，
  所以它的输出只能晚于本文件的提交）。

## 十一、门禁读数（文档提交后运行）

补录于工作区干净之后：见下一次文档提交「record the gate readings」中的原文读数。
