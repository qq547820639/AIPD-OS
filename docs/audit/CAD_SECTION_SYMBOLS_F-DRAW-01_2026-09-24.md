# F-DRAW-01 第 8 片：剖切符号与剖面标题 «A-A»，并把「告警」和「未收口」分成两档

日期：2026-09-24　范围：`src/aipd_os/cad/drawings2d.py`（`_section_line_in_view`、
`assign_section_letters`、`_draw_section_symbols`、`section_warnings` 通道）、
`src/aipd_os/cli/commands_drawing.py`（告警打印、尾注更正）、能力行 `cad.2d_drawings`、
新增常驻用例 `tests/test_cad_section_symbols.py`（12 条）与
`tests/test_cad_section_views.py::TestSeverityIsNotCollapsed`（2 条）。

一句话结论：剖视从「算对了但没标出来」变成**图纸上能找到那一刀**——母视图上有剖切线、
指向保留侧的短划和两端字母，剖视自己带 «A-A» 标题；顺带把真机跑出来的另一处不实
（空剖视也被编号标号、面积告警被当成阻断）一起改掉。

## 一、缺口是交付缺陷，不是美观问题

第 4 片把剖视**算对**了（真布尔切割、材料区量积、真 `HATCH`），但当轮收尾时能力行与
`docs/audit/CAD_SECTION_VIEWS_F-DRAW-01_2026-09-24.md` 都写着「未做剖切符号 A-A」：
图纸上只有一张叫 `SECTION_Y` 的视图，母视图上没有剖切线也没有字母。
车间/审图人拿到这样的图，**无法定位这一刀切在哪、往哪看**——在交付图纸里这是歧义，
不是好不好看的问题。

## 二、符号位置是算出来的（可机器核验的判据）

正交投影把点 `p` 映成 `(p·right, p·up)`；剖切平面 `p·n̂ = offset` 投到母视图上就是直线

```
a·u + b·v = offset,   a = right·n̂,  b = up·n̂
```

于是有四条能被用例钉死的结论：

1. `a = b = 0` ⇔ 视线与剖切面法向平行 ⇒ **该视图不是母视图**，不画符号
   （`FRONT` 对 `Y=0` 这一刀就是这种情形）；
2. 剖切线两端必须严格落在那条直线上（`v = offset` 的水平线，投影没歪的证据）；
3. 保留侧方向 = `(a, b)/√(a²+b²)`：沿它移动让 `p·n̂` 变大，也就是 `>= offset` 那一侧 ⇒
   字母与短划必须在保留侧，且短划**垂直**于剖切线；
4. 长度必须**盖住**母视图轮廓在该方向的跨度（由 bbox 四角点投影算出）并向两端各伸出余量。

`SECTION_BASIS`/`view_basis` 已经在第 4 片把「谁是母视图」的几何定死了，本片只是把同一套基
用到符号放置上，没有新依赖、没有新约定。

## 三、真机读数（黄金件，临时目录，输出原文）

```
$ aipd drawing generate --out c.dxf --part GOLD --views FRONT,TOP --section Y=0 --section Z=2   # rc=0
  剖视告警：材料区含 4 个内环，本轮只填外边界，孔/槽面积会被高估
```

证据与 DXF 读回：

```
section_letters = {"SECTION_Y": "A", "SECTION_Z": "B"}
  TOP     symbols=[("A", [-54.0, 0.0], [54.0, 0.0], [0.0, 1.0])]      label=''
  FRONT   symbols=[("B", [-54.0, 2.0], [54.0, 2.0], [0.0, 1.0])]      label=''
  SECTION_Y label='A-A' symbols=[]
  SECTION_Z label='B-B' symbols=[]
SECTION 层：LINE 6 + TEXT 4（A×2、B×2），线型 {PHANTOM, BYLAYER}
recover.audit()  0 错 0 修
```

`±54` = 母视图轮廓半跨 50 + 两端余量 4；`B` 落在 `v=2` 而不是 `v=0`，
证明符号位置真的由偏移决定（把它改成过原点是会被用例杀的 R3）。

两档严重性是这一轮**跑出来才发现**的两处不实，都已改：

- `--section Z=5`（黄金件在 z=5 处没有材料）此前照样拿到字母 `B` 并在 `FRONT` 上画了剖切线，
  等于图纸声称「这里有一张 B-B 剖视」而它什么都没有 ⇒ 现在空剖视**不编号、不标符号**，
  原因仍由 `section_issues` 说清（`剖视未收口：剖切平面 Z=999 没切到任何材料`，`rc=4`）；
- 「材料区含 4 个内环 ⇒ 面积按高估」是**告警**，却和「什么都没切到」共用同一个未收口通道，
  导致一张可交付的图被判 `rc=4` ⇒ 新增 `section_warnings` 通道：打印但不拦，
  `rc=0`；`剖视未收口` 只留给真正不成的交付。

## 四、落点

| 位置 | 做了什么 |
| --- | --- |
| `src/aipd_os/cad/drawings2d.py:98-101` | 字母表（跳过 I）、余量、短划长、字高四个常量 |
| `src/aipd_os/cad/drawings2d.py:457` | `_section_line_in_view`：`a·u + b·v = offset`，非母视图返回 None |
| `src/aipd_os/cad/drawings2d.py:485` | `assign_section_letters`：按序编号 + 把符号算到所有真母视图上 |
| `src/aipd_os/cad/drawings2d.py:495` | 空剖视不编号（真机发现的缺陷） |
| `src/aipd_os/cad/drawings2d.py:601` | 内环 ⇒ `warnings`，不再挤进 `problems` |
| `src/aipd_os/cad/drawings2d.py:890` | 线型取文档里真有的 `PHANTOM`，没有则 `DASHED`，绝不硬写 |
| `src/aipd_os/cad/drawings2d.py:969` | 证据新增顶层 `section_warnings`（逐视图另有同名字段） |
| `src/aipd_os/cad/drawings2d.py:1074` | `_draw_section_symbols`：剖切线 + 两端短划 + 两端字母 |
| `src/aipd_os/cli/commands_drawing.py:238` | 打印「剖视告警：…」；未收口口径不变 |
| `tests/test_cad_section_views.py::TestSeverityIsNotCollapsed` | 两档各一条常驻用例（告警放行 / 空剖视仍拦） |

## 五、用例与变异（10 条变异全部被杀）

`tests/test_cad_section_symbols.py` 12 条（母视图符号、保留侧、非母视图不标、
标题与字母、短划垂直、多刀多号、无剖视则零符号、证据带端点、文件审计干净、
派生视图不当母视图、空剖视不编号、两个母视图共用同一字母）+ `TestSeverityIsNotCollapsed` 2 条。

| 变异 | 杀于 |
| --- | --- |
| R1 保留侧方向取反 | `test_the_letters_and_ticks_are_on_the_kept_side`、`test_two_cuts_get_two_letters_and_two_titles` |
| R2 剖切线不伸出余量（比轮廓还短） | `test_the_parent_view_gets_a_cutting_line_that_lies_on_the_cut_plane` |
| R3 忘了偏移，符号画过视图原点 | `test_two_cuts_get_two_letters_and_two_titles` |
| R4 短划沿剖切线本身画（不垂直） | `test_end_ticks_are_perpendicular_to_the_cut_line` |
| R5 只在一端写字母 | `test_the_letters_and_ticks_are_on_the_kept_side`、`test_evidence_records_the_line_endpoints_not_just_a_flag` |
| R6 剖面标题不画 | `test_the_section_view_itself_has_no_symbol_but_a_title` |
| R7 所有剖视都用同一个字母 A | `test_two_cuts_get_two_letters_and_two_titles` |
| R8 剖视图自己也标符号 | **首轮幸存** ⇒ 补 `test_a_section_view_never_carries_another_sections_symbol` 后杀 |
| R9 空剖视也编号并标符号 | `test_a_section_that_hits_no_material_is_not_lettered_or_symboled` |
| S1 内环告警塞回未收口通道 | `test_inner_rings_are_a_warning_not_a_hold` |

R8 值得记一句：**「几何上不会发生」不等于「有断言保护」**。`SECTION_Y` 的视线与 `Y` 法向平行，
`_section_line_in_view` 本来就返回 None，所以去掉显式跳过仍然全绿——但**另一刀**（`Z=2`）
的法向在 `SECTION_Y` 里确实能投出交线，显式规则不是冗余，缺的用例补上后同一注入立刻被杀。
源文件在变异还原后与原件**逐字节相同**。

## 六、边界

- 符号是**单一切平面**的：阶梯剖/旋转剖/局部剖仍未做（需要在母视图上画折线剖切路径与转折标记）；
- 箭头方向按「短划 + 字母在保留侧」表达，**没有画投影方向箭头**（ISO 的箭头 + 字母样式未做），
  看图人由「B 落在 v=2、字母朝 +v」读出保留侧；
- 母视图有多个时（TOP 与 BOTTOM 都看得见 XY 面）**每个都标同一个字母**，
  由 `test_top_and_bottom_both_carry_A_for_the_same_cut` 钉住；母视图不在图纸上时不硬画，
  证据里就没有该符号（宁可少标不错标）；
- 字母超过 11 个（`ABCDEFGHJKL`）时后续剖视不编号，并把这条写进该剖视的 `section_problems`；
- 内环告警仍在（面积按高估），带孔截面净面积未做；
- 图纸侧仍未做：局部放大、爆炸图、装配图；`audit_repo --strict` 的发布锚点仍属属主动作。

## 七、复算

```bash
cd AIPD-OS
.venv/bin/python -m pytest tests/test_cad_section_symbols.py tests/test_cad_section_views.py -q
.venv/bin/python -m ruff check src tests state_service && .venv/bin/python -m mypy src tests
TMP=$(mktemp -d) && PYTHONPATH=src .venv/bin/aipd drawing generate --out "$TMP/c.dxf" \
  --part GOLD --views FRONT,TOP --section Y=0 --section Z=2 --json   # rc=0，看 section_letters
```

## 八、收尾读数（全部来自本轮实跑输出，非记忆）

- 提交：实现 `28160b5`（CAD: put the section symbol and A-A label on the sheet, split
  warnings from holds）、产物重锚 `9f621ff`（Release artifacts: re-anchor manifests after
  the section-symbol slice），本节所在提交是本轮第三个；
- `regenerate_release_manifest.py --version 5.6.0` → **588 个文件**（587 → 588 = 新增
  `tests/test_cad_section_symbols.py`）；`release_evidence.py` 按 tag 锚点重写
  `SOURCE_MANIFEST / BUNDLE_MANIFEST / PROVENANCE`（bundle 未重建、未重签、tag 未动）；
- 重锚前全量 **1596 passed / 2 failed / 3 skipped**（两条仍是 packaging 清单哈希），
  重锚后 **1598 passed / 0 failed / 3 skipped**（124.47s）；
- `production_release_gate --release-ready --tag v5.6.0`（产物提交之后跑）：**rc=0，
  release_ready true，8/8 全绿**；`skill_quality_audit` **0 项警告 0 项失败**；
  `state_perf_gate` **PASS**（空闲单跑）。

一处**自己写错又改掉**的记录（留在这里，因为它是可复用的教训）：产物提交信息初稿把重锚后的
全量写成 `1586 passed`——那是上一轮的数字，我在校对计数前就动了笔。修法是 message-only
amend，并先记 `git rev-parse HEAD^{tree}`、改后比对（`4a59534…` 前后相同 ⇒ 内容未动），
树未变、门禁重跑仍 8/8。规矩：**数字要来自刚读到的那行输出，不是上一轮的记忆**。

- 未做且有意不做：不 `git push`、不动 tag、不重建 bundle、不重签、不放宽任何共享门禁；
  `audit_repo --strict` 仍按设计判红（锚点在 tag 而非 HEAD）。
