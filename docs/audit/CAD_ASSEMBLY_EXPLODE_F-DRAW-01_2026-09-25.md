# F-DRAW-01 第 17 片：装配图爆炸视图（位移由作者声明，不自动求拆卸方向）

日期：2026-09-25　范围：`cad.2d_drawings`（爆炸视图）+ `industrialize.release_evidence`
（第五条装配判据）+ `scripts/c6_coverage.py` 档位升档
承接：`C6_COVERAGE_CENSUS_F-C6-01_2026-09-25.md` §九（本片就是照那排序建议走的第 1 项）

## 一、这一片收什么

普查把「爆炸图」判成 `absent`：全仓只有「未做」这句话。它同时是**可完全数字化**
（几何 + 投影，不需要属主给新事实）那一项，所以排第一。收完后 C6 档位从
10/2/3 变成 **11/2/2**，零实现只剩 ICD 与装配/维护两项。

## 二、形状问题先问证据（这一步真的改变了做法）

要的是「爆炸视图」，但先要回答：**位移从哪来**。

| 候选 | 依据（真读到的） | 六维里起决定作用的 | 判定 |
| --- | --- | --- | --- |
| A. 作者声明每件位移（`"explode": [x,y,z]`） | 本仓既有纪律：球标编号、`bom_item` 对应关系都「声明不外推」 | 功能匹配（图纸那一格要的就是作者意图）、适配成本（复用第 12 片逐件投影与球标机制） | **选它** |
| B. 自动求拆卸/爆炸方向 | JCAD《智能装配规划中的拆卸方向计算》摘要：「applying discrete spherical algorithm to analyzing assembly constraints」，并且「the global disassembly direction is finally determined by finding a collision free path for a component to be assembled」 | **前提缺两样**：①装配约束/配合数据（`cad.assembly_constraints` 那行 implementation_file 与 unit_test 两栏皆空）②干涉/碰撞检查（本仓只报包络投影重叠，模块 docstring 明写不做实体求交） | **不做**：缺 ①② 就自动摆，等于画一张没证过的拆卸顺序 |
| 可复用实现 | 本地实测 CadQuery 2.5.2 `cq.Assembly`：`add/children/constrain/constraints/export/load/loc/save/shapes/solve/toCompound/traverse` — **没有 explode**；FreeCAD 侧只检到博客与「exploded assembly 插件安装」文（不是可复用 API 文档）；SolidWorks 爆炸视图帮助页**两次抓取只返回 CSS**，正文一字未取到 | — | 无现成件可搬 → 借文献的「一步=零件+方向+距离」结构，来源换成声明 |

诚实记录：SolidWorks 那页没读到内容，所以 A 的依据是「本仓纪律 + B 的前提缺两样」，
**不是**「主流 CAD 也这么设计」。

## 三、四条可机器核的规矩

1. **缺声明就拒画**：`--explode` 时任何一个零件没写 `explode` ⇒ 出图前整体校验拒
   （rc=2，不留半成品图纸），文案点名缺的是谁。摆开一半的爆炸图会让读者把「没动」
   当成「就该在那儿」——那是图纸在替作者说一个他没说的装配顺序。视图内部另留一道兜底。
2. **位移不折零**：没声明读成 `None`，不是 `[0,0,0]`。两者在图上同形、含义不同。
3. **每件一条装配位→爆炸位连线**（EXPLODE 层；证据 `exploded` + `connectors` 两头坐标都在）。
   编号仍只认作者写的 `balloon`，摆开后**不按位置重发号**。
4. **位移与视线平行时告警「看不出分离」**：图没错（爆炸真做了），但读者拿不到信息，
   所以是告警不是未收口——与本仓「告警 ≠ 阻断」的口径一致。

几何做法：平行投影下「先把实体平移到爆炸位再投影」与「投影后把折线在视图里平移
`proj(explode)`」逐位等价（每件各自做 HLR，件与件之间不互相遮挡），所以走后者：
省一次内核投影，且不引入任何新的几何假设。

## 四、发布证据加第五条装配判据

`explode_unconnected`（阻断）：某视图标了 `exploded` 而连线数 < 零件数。
生产者不会产出不一致的证据——**这条是给手改过的、或旧版本留下的 sidecar 准备的**，
因为门禁吃的是磁盘上的证据文件。同时把视图名钉进断言（证据里的键是 `view` 不是 `name`，
取错键只会往文案里印 `None`，读的人不知道是哪个视图）。

## 五、用例（explode 文件 19 个函数 / 参数化后 23 条；release_manifest +3）

`tests/test_cad_assembly_explode.py`：声明解析（含 5 种非法形状）、缺声明拒画、
`None` 不折零、位移投影逐位对、连线两头分别是谁、球标挂爆炸位、
编号不被位置重排、**包络投影重叠真的变小**（这条是爆炸图的正面价值：
第 12 片那个「挂点重合」告警的根因就是它）、视线平行告警、EXPLODE 层线条数、
证据记两个位置、BOM 绑定不受影响、`--explode` 双向。
`tests/test_release_manifest.py::TestExplodedViewIsJudged`：一致图不报、
抹掉连线必判阻断（含视图名）、没爆炸的图不受这条管。

## 六、变异电池：13/13 killed

| # | 改法 | 红几条 | 代表用例 |
| --- | --- | --- | --- |
| X1 | 声明的位移当成 0（不摆开） | 4 | `test_exploded_position_is_the_declared_shift_projected` |
| X2 | 连线两头都在爆炸位（没有出处） | 1 | `test_one_connector_per_part_between_assembled_and_exploded` |
| X3 | 球标挂回装配位 | 1 | `test_anchor_is_the_exploded_centroid_not_the_assembled_one` |
| X4 | 编号按摆开后位置重发 | 1 | `test_numbers_stay_author_declared` |
| X5 | 去掉出图前的整体声明校验 | 1 | `test_missing_declaration_holds_the_command_at_rc2` |
| X6 | `--explode` 不透传 | 2 | `test_explode_flag_switches_the_view` |
| X7 | 不给 `--explode` 也自动爆炸 | 1 | `test_without_the_flag_the_declared_explode_is_ignored` |
| X8 | 证据里不写 `exploded` | 3 | `test_exploded_drawing_carries_an_explode_layer_with_one_line_per_part` |
| X9 | 连线不画到 EXPLODE 层 | 1 | 同 X8 那条（数 LINE） |
| X10 | 视线平行时不告警 | 1 | `test_exploding_along_the_view_axis_warns_that_nothing_separates` |
| X11 | 缺声明折成 `[0,0,0]` | 3 | `test_absent_explode_is_none_not_zero` |
| X12 | 没爆炸的视图也被这条管 | 5 | `test_a_view_that_is_not_exploded_is_not_judged` |
| X13 | 连线判据方向写反 | 1 | `test_connectors_stripped_from_the_evidence_is_a_hold` |

**两处反证自身的坑（比电池结果更值得记）**：

1. X5 差点被当成「杀不掉的等价变异」：`build_assembly_view` 里还有一道兜底检查，
   删掉出图前那道也照样 rc=2。看清楚才发现**两道不是同一道**——早退的那道不建图纸对象、
   晚退的那道在投影中间抛。把断言从「rc=2 且含爆炸字样」换成
   **点名早退那道特有的措辞与缺失清单**（「爆炸视图要求每个零件都声明」+「压板」）才成立。
   规则：两道检查都挡同一件事时，断言必须能分辨是哪一道拒的，否则冗余会掩护漏检。
2. 普查 `--self-test` 的「档位与所列文件矛盾」注入原本写死在「爆炸图」上；
   这一片把爆炸图升到 `producer` 之后，那条注入**静默变成等价注入**（判据没红）。
   已改成 `_an_absent_item()` 按当前档位动态挑。规则：注入锚点要么动态选、
   要么由一条断言保证它仍在判据读的那一档里。

## 七、端到端（全走 `aipd`，临时目录，未碰开发库）

```
aipd drawing assembly --manifest assy.json --db state.db --bom BOM-001 \
                      --views TOP,FRONT --explode            → rc=0
  爆炸视图：2 个视图、4 条装配位→爆炸位连接线（位移由 manifest 的 explode 声明…）
  明细表：2 行，列 ['ITEM','PART','QTY','UNIT','MATERIAL','PROCESS']
    材料已填 2/2 行，没有缺行 / 工艺已填 2/2 行，没有缺行
DXF：EXPLODE 层 LINE 4 条（2 视图 × 2 件），BALLOON 层 CIRCLE 2 / LINE 2（仍只一个视图编号）
每视图证据：exploded=true，connectors=2，assembly_parts=2
aipd release manifest --drawing assy.dxf --bom BOM-001      → issues 里没有任何爆炸类问题
```

## 八、同步面

`cad.2d_drawings`：`input_output` 加爆炸视图与连线；`current_limitation` 两处
「爆炸图未做」的旧话删掉，换成「爆炸位移已能声明式出图 + 不自动求方向（写清缺哪两样前提）+
仍不做装配约束/配合」；`industrialize.release_evidence` 加 `explode_unconnected`；
README 场景 4 的命令行加 `--explode` 并写明拒画与告警；`scripts/c6_coverage.py` 映射升档，
`tests/test_c6_coverage.py` 的棘轮与缺席清单同步（11/2/2，缺席只剩 ICD 与装配/维护）。

## 九、收口读数（commit 后复算）

- 代码+文档：`e473b04`（16 files，+754/-53）；产物重锚：`09959f1`；
  被哈希面 596 → **597** 个文件（新增的 explode 用例文件）。
- 全量常驻用例（带 `AIPD_SOURCE_COMMIT=a66040520139…`）：**1772 passed / 0 failed / 3 skipped**
  （total 1775 = 上一轮 1749 + explode 23 条 + 证据侧 3 条）。
- `production_release_gate --release-ready --tag v5.6.0`：**rc=0、8/8、`release_ready: true`**，
  读数 `passed=1772 failed=0 total=1775 source_commit=a66040520139…`。
- `skill_quality_audit` rc=0（0/0）；`state_perf_gate` **PASS**；
  `audit_repo --strict` rc=1，只剩「tag 未重打的 provenance 锚点」那一条已知 ✗。
- 普查：`--self-test` **7/7**；档位 **15 项 = 11 / 2 / 2**（零实现只剩 ICD 与装配/维护）。
- 变异电池 **13/13 killed**（§六）。

## 十、仍未做

- 爆炸位移的自动求解（前提：装配约束/配合 + 实体干涉检查）。
- 爆炸图与剖视/局部放大的组合：装配视图上仍拒绝（折线按零件归属，裁剪会打散）。
- 爆炸步骤序列（一步一件、多步动画/顺序号）：现在是一步全摆开，多步要另一个数据结构。
- 装配/维护说明文档的生产者、ICD（C6 剩下的两个零实现项，都需要属主给口径）。
