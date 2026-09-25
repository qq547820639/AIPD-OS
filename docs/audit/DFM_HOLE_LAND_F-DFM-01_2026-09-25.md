# 第 25 片：孔周留肉（hole-to-edge land）+「孔还是外圆」+ 借数的第三类来处

关联缺陷：F-DFM-01（能力 `cad.dfm_dfa`）｜日期：2026-09-25｜内核：cadquery 2.5.2 /
cadquery-ocp 7.7.2（OCP 7.7）｜全部读数为**本机实测**，命令与夹具见 §六。

## 一、这一片补的是什么

C6 生产图纸包与制造方最常挑的两类几何问题里，本仓只答了一半：

1. 「这堵墙太薄」——第 19 片起有壁厚（两法，第 24 片补了方向正确的那一条）；
2. 「这个孔离边/离邻居太近，钻完会翻边」——**之前完全没有**。孔心到边的距离在
   `facts.holes[].axis_point` 里间接可读，但没人愿意让读者自己减半径，而且
   「孔口到最近自由边剩下多少肉」与「孔心到边」不是一回事：Ø6 与 Ø12 的孔放在
   同一个孔心，前者剩 3mm、后者剩 0mm。

这一片量的就是后者：`measure_hole_lands()` 逐孔逐口给出**留肉宽度**（`land_mm`）
与中心距（`centerline_to_edge_mm`），并给三条规则（只报事实 + 金属/塑料各一档 advisory）。

## 二、先量出一个旧错：整周回转 ≠ 孔

写量具时第一件事是拿圆棒试：`cq.Workplane("XY").circle(10).extrude(20)`。
旧口径（第 19 片起，`geometry_facts` 与留肉共用）判「孔」只看**圆柱面角向张角是否满一周**
（u 参数区间 ÷ 2π ≥ 0.999）。Ø20 圆棒的侧面同样满一周，于是：

| 夹具 | 旧读数（本机） | 应该是 |
|---|---|---|
| Ø20×20 圆棒 | `holes = [Ø20 深 20]`（1 个孔） | 0 个孔 |
| 垫片 Ø30 盘 + Ø8 中心孔 | `holes = [Ø8, Ø30]`（2 个孔） | 1 个孔（Ø8） |
| 40×20×6 板上 Ø14 凸台 + Ø6 通孔 | 3 个整周圆柱面里 2 个被当成孔 | 1 个孔 |

后果不是「多报一个数」：Ø20 被当成孔之后，`hole_depth_to_diameter`（深径比）会拿**外圆直径**
去比钻孔能力，`same_axis_hole_count`（一次装夹钻几个孔）会数进外圆，留肉会拿
「外圆到内孔边的距离」冒充「孔口剩下的肉」——三个判据一起错，而且错得看起来很专业。

补的判据与张角**正交**：从圆柱面上一点沿**径向**外移 1µm，问 `BRepClass3d_SolidClassifier`
——落进材料里 ⇒ 这一圈壁的外侧是材料 ⇒ 是孔；落在材料外 ⇒ 是外圆。
不用面法向，是因为不依赖面的朝向标记（同一模型里正反面都有）；用逐**实体**分类器，
与第 24 片壁厚那条同一处置（compound 里两个实体不该互相把对方内部当材料）。
没有实体可分类（纯曲面/线框输入）⇒ 返回 `None`，**不知道**，既不猜成孔也不猜成外圆；
这条路径在报告里单独计数（`bore_undecided_cylinder_count`），不静默。

外圆不再计成孔之后，`facts` 仍把「排除了什么」交出来：`outer_cylinder_count`。
本机复测三件：圆棒 0 孔/1 外圆、垫片 1 孔(Ø8)/1 外圆、凸台件 1 孔(Ø6)/1 外圆。

## 三、阈值从哪来：这一片新增第三类来处 `borrowed_out_of_scope`

按「不发明阈值」的规矩先检索（2026-09-25 实检，与第 24 片同一次调研的延续）：

- HLH Rapid《CNC Machining Design Guide》：给了金属最小壁厚 0.8mm、塑料 ±1.5mm、
  内圆角比值、深径比 >4 需二次操作；**没有**机加件的孔边距（edge distance / land）一条。
- Xometry《CNC 加工的行业标准》：金属 0.794mm（=1/32″）、塑料 1.5mm、深径比 ≤4（上限 10）；
  同样**没有**孔边距。
- 3ERP 转述的 ISO 2768-1：把 edge distance 列成「由一般公差覆盖的尺寸」，
  是**被覆盖的对象**，不是阈值。
- 另两家（Protolabs 的 1.574/3.175mm）是**钣金** Domain 的规则，不是铣削孔边距；
  Eurocode 的螺栓边距是连接件规则，不能搬。

⇒ 结论：**没有一个厂商页写着机加件的孔周留肉阈值**。把「≥2×D」这类行话写进规则会是编数。
处置：
- `hole_land_reported`（`own_measure`，`limit=None`）只交实测值；
- `hole_land_metal` / `hole_land_plastic` 用 `borrowed_out_of_scope`：数**借自本表内
  真有页撑着的那两条壁厚**（0.8 / 1.5mm），`source.stated_for` 明写借哪条，
  note 明写「页内原述是给壁厚的，这是外推」，severity 只到 advisory。

为什么要新加一类而不是挂在 `vendor_capability` 或 `own_measure` 上：常驻用例本来就钉着
「`own_measure` 不许挂 URL」「非 `own_measure` 必须有 URL」，挂错类就是把外推冒充标准
（第一次实现确实错挂在 `own_measure` 上，被这条不变量当场判红 —— 闸长出来了）。

新来处的机器核对（运行时 `_check_source_integrity` + 常驻用例双向）：
`stated_for` 必须存在 → 指到的规则自己必须是 `vendor_capability` → limit 必须**一字不差**
→ URL 必须是**同一页**。运行时也**逐格各给一句话**：首轮电池里 R2/R4/R6 三条注入
「看起来都被杀了」，其实是被同一道 limit 检查顶替（用例只要求抛 ValueError）——
改成每类坏法各匹配各的报错文案之后才分得开。

## 四、量法与实现落位

`src/aipd_os/cad/dfm.py`：

- `_solid_classifiers(shape)` / `_cylinder_is_bore(face, classifiers)`：§二 那根正交判据。
- `geometry_facts`：整周圆柱面先过孔/外圆这一关；外圆进 `outer_cylinder_count`，
  分不出的进 `bore_undecided_cylinder_count`。
- `measure_hole_lands(shape)`：
  1. 遍历**孔**（整周 + 是孔）的圆柱面，取其上半径与圆柱半径一致、轴平行的圆边当孔口；
     取不到圆口边（孔口开在曲面上）⇒ `why += ["rim_circle_not_found"]`；
  2. 每个口找宿主平面：法向平行于孔轴 **且** 平面含住这个口圆的圆心
     （台阶孔/沉孔的两层口因此各归各的面）；
  3. 宿主面上除去「孔自己这圈周边」之外的所有边都是候选自由边 —— 相邻孔的口边、
     板的外轮廓边、沉孔底 Ø10 的圆都在里面；
  4. 逐边 `BRepExtrema_DistShapeShape(口边, 边)` 取最小 = 该口留肉；
  5. 逐口读数全部交出去（`rim_readings`），行的 `land_mm` 取其中最薄的一个。
     **两口分别给数**是这一片第二次被电池教的地方：只取遍历碰到的第一个口（L4 注入）
     在只交一个聚合数时**测不出来**，因为 OCCT 的面序不保证哪个口在前。
- `analyze` 里接上 `facts.min_hole_land_mm` / `facts.hole_land_measurement`；
  `_judge` 对三条 hole_land 规则的前提：没有整孔 ⇒ `no_full_cylindrical_hole`、
  有孔但一圈量不到 ⇒ `hole_land_unmeasurable`、材料认不出 ⇒ `material_class_unknown`、
  材料是另一类 ⇒ `material_is_the_other_class`。全是盲区，不折 pass。
- 报告散文：新增「孔周最小留肉」一行（含 `量到 x/y 个整孔`），
  「整孔 N 个」那行补 `整周外圆（不计入孔）N 个`，
  来处一行改印人话（`厂商能力页` / `借来的数：厂商页原述是别的特征`）并点名原述特征。

## 五、常驻用例与变异电池

`tests/test_cad_dfm_hole_land.py` **32 条**（`tests/test_cad_dfm.py` 另加 3 条来处不变量、
改 3 条既有的；`tests/test_cad_dfm_wall_normal.py` 另加 3 条采样上限的）：
孔/外圆分得开（6）、留肉量得对（含逐口/逐行复算，13）、判据三态（7）、报告散文（3）、
表内诚实（3）。这些组里所有毫米数都是 §六 与本机复算的实测值，不是推算。

`/tmp/slice25-mutations.py` **28 条**注入（留肉 L1-L10、孔/外圆 B1-B5、来处 R1-R10、
采样上限 C1-C3），**杀掉 28 / 存活 0 / 注入无效 0**。
两处电池自身的读数值得记：

1. 加了**对照组**（不改任何东西先跑同一批 node id）之后，B1 立刻被判「注入无效」——
   我把一条用例挂错了类名，pytest 用 rc=4（没收集）退出，旧版电池会把这当成「杀掉」。
   假绿的方向恰好是「以为有闸」。
2. 首轮 5 条存活（L4/L6/L9/R4/R5）。不是判据错，是**用例看不见**：
   L4 → 交一个聚合数时无法区分「量了两个口」，改成逐口都交读数；
   L6 → 夹具里第一行恰好就是最薄的那条，改成显式钉住行序（薄的那条在第二行）；
   L9 → 圆角是 1/4 周、放歪到 0.4 仍然拦得住，补一个 **1/2 周半圆缺口**（且它是凹面，
   只挡在张角这一关）；
   R4/R5 → 用例只要求「抛 ValueError」，limit 检查替 donor 检查背了锅，改成逐格各匹配各的文案。

## 六、端到端实测（`aipd drawing dfm`，金样品原文件）

```
$ .venv/bin/python -m aipd_os.cli.main drawing dfm \
    --step releases/golden-projects/B-cad-engineering-change/bracket.step \
    --out /tmp/dfm-e25/bracket-6061.md --part BRK-1 --material 6061-T6     # rc=0
```

几何那三行（`bracket-6061.md` 逐字，未换行）：

```
- 最小壁厚（取两法较小者；三轴网格射线间距 0.5mm、有命中的射线 24748 条、奇数命中 0 条；沿面法向探 1872 点、可用 1858 段、每面最多 12×12 点、法向退化跳过 0 点。三轴 2 mm、法向 2.23522 mm）：2 mm
- 孔周最小留肉（孔口圆到最近自由边，相邻孔口边同算一边）：2 mm，量到 3/3 个整孔
- 整孔 3 个；部分回转圆柱面 4 个；整周外圆（不计入孔）0 个；材料 6061-T6（分类：metal）
```

判定两条（逐字）：

```
- **孔周最小留肉（只报事实）**：只报事实｜实测 2mm vs 阈值 不设阈值（3/3 个整孔量到留肉，最小 2mm）｜事实
- **金属孔周留肉**：合格｜实测 2mm vs 阈值 0.8mm（孔口到最近自由边留肉 2mm）｜建议
```

借数那条在报告里印成：

```
（https://hlhrapid.com/knowledge/design-guide-cnc-machining/，访问 2026-09-25，借来的数：厂商页原述是别的特征，页内原述是给「金属最小壁厚」的）
```

侧车 `bracket-6061.md.evidence.json`：`rulebook.rule_count` **10**（原 7 + 这一片 3），`blind` 三条 = 塑料两条壁厚/留肉（`material_is_the_other_class`） + 公差那条（`no_declared_tolerance`，本次没给 `--spec`）。

## 七、这一片没做的事


- **孔边距的「标准」不是本仓定的**：金属 0.8 / 塑料 1.5 是从壁厚外推的，
  判 advisory 由制造方核；真要接 ISO 2768 或客户规范，得先由属主定「件号字符集/引用哪一版」。
- 干涉与间隙仍不做实体求交（与第 17、20 片同一条边界）。
- 沉孔/锪孔/倒角孔的**功能**识别：本片把 Ø10 通孔与 Ø14 沉孔各当一根孔量，
  读数是「环形韧带 2.0」这种正确但没有语义的答案；要报「沉孔底厚」需要建特征语义。
- 孔口在曲面上的件（径向孔）只给盲区原因，不做曲线边的极值距离近似。
- `geometry_facts.holes` 现在**依赖实体分类**：纯曲面输入（无线框以外的实体）会退回
  「按最坏情况仍计成孔」并单独计数，这条路径本机没有真实夹具能走通（`analyze` 的入口
  都来自 STEP/Workplane 实体），所以它只有单元测试、没有生产实测。

## 八、收尾读数（落盘后由量具复算，不是计划）

提交：`fc6cd7c`（代码 + 用例 + 文档）→ `025f98a`（发布工件重锚）→ `0b9ed1a`（快照随片重算）。

| 量具 | 读数 |
|---|---|
| 全量 pytest（`docs/audit/pytest-report-v5.6.0.json`） | **1958 passed / 0 failed / 3 skipped**（共 1961；上一片收尾 1920/0/3=1923，本片 +38 条） |
| `PROVENANCE.json` | `test_report.{passed:1958, failed:0, total:1961, source_commit:a66040520139…}` |
| `SOURCE_MANIFEST.json` | 被哈希面 **606 → 607**（新增就是 `tests/test_cad_dfm_hole_land.py`）；快照 `hash_matches 607/607`、`tests 174 → 175` |
| `production_release_gate --release-ready --tag v5.6.0` | rc=0，`release_ready: true`，8/8 项全过（工作树干净状态下复跑） |
| `ruff check src tests state_service` / `mypy` | 均 rc=0 |
| `scripts/c6_coverage.py --self-test` | 7/7；档位仍 **13 / 1 / 1**（本片加厚 `DFM/DFA` 那一格的 note，不改档位） |
| 变异电池 `/tmp/slice25-mutations.py` | **28 条：杀 28 / 活 0 / 注入无效 0**（过程见 §五） |
| 端到端 | `aipd drawing dfm` 跑金样品 rc=0；报告与侧车读数见 §六 |

两处自己抓自己的读数，都记进规矩：

1. **第一次跑 gate 报了 rc=0，是假的。** 命令写成 `gate … | tail -14; echo "rc=$?"`，
   `$?` 取的是 `tail` 的退出码。去掉管道后真实 rc=2，三项红：
   `workspace_clean`（工件未提交，正常）、
   `commit_matches_head` 与 `test_numbers_from_report` —— 后两项是我把
   `--source-commit` / `AIPD_SOURCE_COMMIT` 传成了 tag 名 `v5.6.0`，
   而 gate 比的是 tag 解析出来的 **SHA**（`a660405…`）。锚点传参必须用 SHA，不能用 tag 名。
2. **`repository_snapshot.json` 是 gate 自己写的。** 第一次把它漏在工件提交之外，
   gate 跑完立刻把工作树弄脏 → `workspace_clean` 判红。要么与其余工件同批提交，
   要么承认「gate 之后再 commit 一次」这个顺序（这次走了后者）。
