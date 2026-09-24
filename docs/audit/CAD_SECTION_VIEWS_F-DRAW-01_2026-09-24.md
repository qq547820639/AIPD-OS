# F-DRAW-01 第 4 片：剖视图（真布尔切割 + 剖面材料区量积 + DXF HATCH 填充）

日期：2026-09-24　范围：新增 `src/aipd_os/cad/drawings2d.py` 的 `section_view` 一族
（剖切规格解析、半空间布尔切割、剖面材料区筛选与量积、边界接环、`HATCH` 填充、
`section_issues` 证据）、`src/aipd_os/cli/main.py`（`drawing generate --section`）、
`src/aipd_os/cli/commands_drawing.py`（剖视逐视图读数 + 未收口判退出码 4）、
能力行 `cad.2d_drawings` 行内改写、新增常驻用例 `tests/test_cad_section_views.py`（12 条）、
顺带把 GD&T 格宽公式收成一处（`gdt.py` `compartment_width`，新增 1 条用例）。

一句话结论：图纸从「只有六个外部正视图」推进到「能把内部切给人看」——剖切是**真做的布尔运算**，
剖面线是**真的 `HATCH` 实体**，材料面积是**内核量出来的**；切不到材料或边界接不成闭合环
一律如实说出来并判未收口，不交一张空白剖视当成果。

## 一、选型与取证（都做过实测/检索）

1. **ezdxf 1.4.2（本机实装版）读源码核实填充 API**：
   `set_pattern_fill` 实际定义在 `.venv/lib/python3.9/site-packages/ezdxf/entities/polygon.py:270`
   （`Hatch` 类**没有**自己实现这个方法，是继承来的——按名去 `entities/hatch.py` 找会找不到）；
   边界路径工厂 `add_polyline_path` 在 `entities/boundary_paths.py:212`；
   预定义图案 ANSI31 的定义在 `tools/_iso_pattern.py:76`：
   `[[45.0, (0.0, 0.0), (-2.2450640303, 2.2450640303), []]]`（45° 斜线 + 偏移，无虚线段）。
   最小文档实测：`msp.add_hatch()` → `paths.add_polyline_path(pts, is_closed=True)` →
   `set_pattern_fill("ANSI31", scale=1.0)` → 存盘读回，实体标签为
   `2=ANSI31`、`70=0`（非 solid，即由图案线填充）、`91=1`（1 条边界路径）、`92=3`
   （polyline 边界）、`93=4`（4 个顶点）、`75=1`（写入 **1 条 pattern line**）、
   `43/44=0.0`、`45=-2.2450640303`、`79=0`、`97=0` ⇒ 剖面线定义确实进了 DXF 标签流，
   不是只贴了个图案名。
2. **`Layout` 没有 hatch 之外的「剖面」概念**：ezdxf 只给容器（`HATCH` 实体 + 边界路径 + 图案定义），
   截面几何得自己从 3D 内核拿。
3. **布尔切割用已在场的 cadquery/OCP**：`cq.Solid.makeBox(...)` 造半空间大切刀，`solid.cut(cutter)`
   一刀切完，再复用本仓已有的射线遮挡投影 `build_view`。不引入新依赖。
4. **检索过的候选与不足**：WebSearch（OCC `HLBAlgo`/`BRepAlgoAPI` 剖视+填充、
   "open source python CAD drawing generator section view hatching"）命中
   [OpenCASCADE HLR 轮廓线](https://www.cnblogs.com/opencascade/p/occt_hlr_contour.html)、
   [opencascade 源码学习之 HLRAlgo 包](https://www.cnblogs.com/yzxxty/p/18443548)、
   [ezdxf 官网](https://ezdxf.mozman.at/) 等，**全部是博客/摘要级材料，没有可据以实现的权威 API 文档**；
   WebFetch ezdxf 文档页 `docs/dxfprimer.html` 返回 **404**（未取到内容，不作依据）。
   因此本轮实现依据只有两处：本机实装包源码（上面逐条给了路径与行号）+ 自己做的实测。
   另：**未检索到**一个「纯 Python、本地可跑、能出剖视并填剖面线」的成熟轮子，
   所以这一片是自己实现，但形状借自 DXF 标准（`HATCH` + 预定义图案）而不是自创。
5. 三个候选的取舍（六维里最关键的是「断言能不能落到可回读的数字上」）：
   - **A（选定）真布尔切割 + 真 `HATCH`**：功能匹配度最高（能看内壁、能量材料面积）；
     License 无新增（cadquery Apache-2.0、ezdxf MIT，均已在 `cad` extra 里）；
     维护活跃度由既有依赖承担；无新增安全风险；代码质量成本＝自己实现 ~90 行；
     适配成本＝复用现有投影/图层/证据骨架。
   - **B 只在投影里挑「落在切割面上的边」**：便宜（~15 行），但拿不到闭合区域、
     算不出材料面积、也证明不了投影没画歪 ⇒ 断言只能停在「有没有线」，放弃。
   - **C FreeCAD/TechDraw 的剖视**：功能最全（剖切符号、阶梯剖都有），但本机未安装、
     未读源码、需引入外部进程与 GPL 依赖，且与本仓「本地纯 Python 内核」方向冲突，放弃。

## 二、口径

- **剖切写法**：`--section "Y=0"`（`X/Y/Z` + 偏移），保留 **≥ 偏移** 的一侧；轴不认识或偏移不是数
  直接 `ValueError` ⇒ CLI 返回 2 且**不落任何文件**，不猜；
- **材料区 = 法向平行 且 面心落在剖切平面上**（两道筛选缺一不可，`SECTION_PLANE_TOL = 1e-6`）；
- **面积只量外边界**：材料区含内环（孔/槽）时，本轮只填外边界并**明说面积会被高估**，
  不假装做了带孔面积；
- **接不成闭合环就不填**：宁缺一块剖面线，也不静默填一个错多边形（`_chain_loop` 接不上时返回
  `(部分, False)`）；
- **空剖面不是成果**：切不到材料 ⇒ `section_empty` + `section_issues` + 未收口（退出码 4）；
- **原因不能说反**：切到了面但边界都断了 ≠ 没切到材料，两套措辞分开（用例钉住）。

## 三、真机端到端读数

命令（临时目录，内置黄金模型）：

```
aipd drawing generate --out sec.dxf --part SECT-PROBE --views FRONT,TOP \
  --section Y=0 --section Z=50
```

- 退出码 **4**（`--section Z=50` 在实体外），stderr 空；stdout 关键行原文：

```
  SECTION_Y 100.0x10.0mm 实线 60 条 / 虚线 9 条
         剖切 Y=0（保留 y>=0）：材料区 5 个 / 676.0mm²，剖面线 5 条
  SECTION_Z 0.0x0.0mm 实线 0 条 / 虚线 0 条
         剖切 Z=50（保留 z>=50）：材料区 0 个 / 0mm²，剖面线 0 条
  剖视未收口：剖切平面 Z=50 没切到任何材料
```

- DXF 读回（`ezdxf` + `recover.readfile`）：`audit()` **0 错 0 修**；
  `HATCH` **5 个**，全部 `pattern_name='ANSI31'`、`layer='HATCH'`、1 条闭合边界路径；
  逐条量边界多边形面积 = `[120, 120, 120, 158, 158]`，合计 **676 mm²**，
  与证据里的 `material_area_mm2 = 676.0` **逐字一致**；
  其中两块 6 顶点、三块 5 顶点 ⇒ 端部材料区确实带着倒/圆角的额外顶点
  （黄金件参数 `fillet_radius=3.0`、`chamfer=2.0`，见 `src/aipd_os/cad/backends.py:183-184`），
  不是 4 顶点矩形，说明填的是真实截面而不是简化的包围盒；
- 实体计数：`{'LWPOLYLINE': 56, 'LINE': 109, 'DIMENSION': 15, 'TEXT': 20, 'HATCH': 5}`；
  图层：`0, FRAME, HATCH, HIDDEN, OUTLINE, TEXT`（本次未带 `--spec` ⇒ 无 `GDT` 层，符合「框只来自声明」）。
- 用例侧固定件（100×20×10 板 + 4 个 Ø8 通孔，切 `y<0`）：`y=0` 上恰好 **5 个材料面**，
  面积 `160,120,120,120,160`（合计 **680 mm²**），与手算 `(16+12+12+12+16)×10` 一致。

## 四、落点

| 位置 | 做了什么 |
| --- | --- |
| `src/aipd_os/cad/drawings2d.py:91` | `SECTION_PLANE_TOL = 1e-6`：面心到剖切平面的容差 |
| `src/aipd_os/cad/drawings2d.py:430` | `parse_section_spec`：`X/Y/Z=偏移`，不合法即 `ValueError` |
| `src/aipd_os/cad/drawings2d.py:443` | `section_view`：半空间 `makeBox` + `solid.cut()` + 复用 `build_view` 投影 |
| `src/aipd_os/cad/drawings2d.py:502` | `matched += 1`：只数「过了两道筛选」的面，供后面区分失败原因 |
| `src/aipd_os/cad/drawings2d.py:506` | 边界接不成闭合环 ⇒ 报问题并 `continue`（不填） |
| `src/aipd_os/cad/drawings2d.py:517` | 空剖面分两支：`matched>0` 说「接不成闭合环」，否则说「没切到任何材料」 |
| `src/aipd_os/cad/drawings2d.py:547` | `_chain_loop`：把 OCP 给的**无序**边段接成闭合环，接不上返回 `(部分, False)` |
| `src/aipd_os/cad/drawings2d.py:586` | `_projected_wire`：逐边离散化 → 投影 → 接环 |
| `src/aipd_os/cad/drawings2d.py:835` | 证据 `section_issues`：跨视图去重后的剖视问题清单 |
| `src/aipd_os/cad/drawings2d.py:921` | `msp.add_hatch(layer="HATCH")` + `add_polyline_path(..., is_closed=True)` + `set_pattern_fill("ANSI31")` |
| `src/aipd_os/cli/commands_drawing.py:124` | 剖视图逐视图打印「剖切轴/偏移/保留侧/材料区数/材料面积/剖面线条数」 |
| `src/aipd_os/cli/commands_drawing.py:160` | 打印 `剖视未收口：…` |
| `src/aipd_os/cli/commands_drawing.py:167` | `section_issues` 进未收口集合 ⇒ 退出码 4 |
| `src/aipd_os/cad/gdt.py:172` | 框证据新增 `width_mm`（格宽求和） |
| `src/aipd_os/cad/gdt.py:177` | `compartment_width`：格宽公式**唯一一处**；`frame_width`（182）与绘制（196）都走它 |
| `src/aipd_os/registry_data.py` | `cad.2d_drawings` 行：`unit_test` 补 `tests/test_cad_gdt_frames.py`、`tests/test_cad_section_views.py`；`input_output` 补剖视与 `HATCH`；限制改写 |

## 五、用例与变异（8 条变异全部被杀）

常驻用例 12 条（`tests/test_cad_section_views.py`，4 个类：`TestCutIsRealGeometry`、
`TestHatchIsARealEntity`、`TestChainLoopGuard`、`TestCliSurface`）+ GD&T 格宽 1 条
（`tests/test_cad_gdt_frames.py::TestWidthIsOneFormula`）。

变异对照（逐条注入→跑用例→还原，三个源文件还原后与原件**逐字节相同**）：

| 变异 | 结果 | 杀于 |
| --- | --- | --- |
| M1 去掉「面心在剖切平面上」的距离筛选 | 6 失败 | 含 `test_outer_wall_is_not_mistaken_for_the_cut_face`、`test_section_finds_the_five_material_regions`、`test_section_projection_matches_the_model_envelope`、`test_cut_regions_become_closed_ansi31_hatches`（1000mm² 外壁混进剖面；另有 2 条同批失败，打印窗口只截了前 4 个名字） |
| M2 不做边段重排、直接顺次拼接 | 3 失败 | `test_section_finds_the_five_material_regions`、`test_hatch_boundary_area_equals_the_measured_region_area` |
| M3 接不成环也照样填充 | 1 失败 | `test_uncloseable_boundary_skips_fill_and_says_so` |
| M4 空剖面不当问题 | 2 失败 | `test_cutting_outside_the_geometry_is_reported_not_hidden`、`test_empty_section_holds_the_command` |
| M5 断环时也报「没切到任何材料」 | 1 失败 | `test_uncloseable_boundary_skips_fill_and_says_so`（原因说反） |
| M6 绘制格宽与记录格宽漂移（×1.1） | 1 失败 | `test_recorded_width_matches_the_drawn_compartments` |
| M7 剖视问题不再拦退出码 | 1 失败 | `test_empty_section_holds_the_command` |
| M8 剖视图不再打印材料区/面积 | 1 失败 | `test_cut_material_area_is_reported_per_view` |

补记：M2 只杀 3 条而不是全杀——`test_cut_regions_become_closed_ansi31_hatches` 在乱序拼接下
仍然数得出 5 个 `HATCH`（数量对、形状错），这正是「只数实体条数不算面积」的判据盲区，
所以面积一致性用例（`test_hatch_boundary_area_equals_the_measured_region_area`）不能省。

## 六、边界（还没做，别当已交付）

- **剖切符号 A-A、阶梯剖/旋转剖/局部剖**未做：只出「SECTION_Y」这种按轴命名的视图名，
  主视图上没有剖切线与字母标记，看图人需自行对应；

> **2026-09-24 当日更正（第 8 片）**：剖切符号与剖面标题 «A-A» 已在同一天补上（母视图上的剖切线 + 指向保留侧的短划 + 两端字母，位置由剖切平面在母视图投影面上的交线算出；剖视图与空剖视不编号不标号）。本文件其余结论按当轮状态保留。见 `docs/audit/CAD_SECTION_SYMBOLS_F-DRAW-01_2026-09-24.md`；阶梯剖/旋转剖仍未做。
- **只填外边界**：材料区含内环时面积按高估处理并明说，没做带孔截面净面积；
- **剖面区域不投影倾斜面**：材料区取的是剖切平面上的正平面（法向平行 + 面心在面上），
  斜剖（偏移面不平行坐标面）不支持；
- `section_empty` 判据是「有 `section_of` 且材料区为 0」，不含「切到了但全是断环」以外的细分；
  断环情形同样落进 `section_empty`，靠 `section_issues` 的措辞区分；
- 剖切仍是**手工命令行输入**，未与 Product Truth/CTQ 打通（谁要求剖、剖在哪，图纸自己不知道）；
- 局部放大图、爆炸图、装配图未实现。

## 七、复算

```bash
cd AIPD-OS
.venv/bin/python -m pytest tests/test_cad_section_views.py tests/test_cad_gdt_frames.py -q
.venv/bin/python -m ruff check src tests state_service
.venv/bin/python -m mypy src tests
TMP=$(mktemp -d) && PYTHONPATH=src .venv/bin/aipd drawing generate --out "$TMP/sec.dxf" \
  --part SECT-PROBE --views FRONT,TOP --section Y=0 --section Z=50   # 退出码 4
```

## 八、收尾读数

- 提交：实现 `b8ef3d7`（CAD: cut real section views and fill them with DXF HATCH entities）、
  产物重锚 `96efa03`（Release artifacts: re-anchor manifests after the section-view slice）；
  本节所在的 docs 提交是本轮第三个提交。

- `tests/test_cad_section_views.py`：**12 passed**；`tests/test_cad_gdt_frames.py`：**12 passed**；
- 全量：`1538 passed / 2 failed / 3 skipped`，两条失败**只**是
  `tests/test_packaging.py::test_release_manifest_hashes_match_disk` 与
  `::test_source_manifest_hashes_match_disk`——本轮改了 `src/`，清单哈希按惯例在收尾时重算（见下），
  不是回归；
- 收尾后（同一轮内实测）：清单重生成 `RELEASE_MANIFEST.json` **584 个文件**（+1 = 新增的
  `tests/test_cad_section_views.py`），`release_evidence.py --bundle releases/aipd-os-5.6.0.zip
  --test-report docs/audit/pytest-report-v5.6.0.json
  --source-commit a66040520139405095648461f7144d4f00629924` 重写
  `SOURCE_MANIFEST / BUNDLE_MANIFEST / PROVENANCE`（bundle 未重建、未重签、tag 未动）；
  重跑全量 **1540 passed / 0 failed / 3 skipped**；`production_release_gate --release-ready --tag v5.6.0`
  **8/8 通过**（`release_ready: true`，报告读数 `passed=1096 failed=0 total=1099
  source_commit=a660405…`，Ed25519 验签通过，pip-audit 无未承认 CVE）；
  `skill_quality_audit` **0 警告 0 失败**；`state_perf_gate` **PASS**
  （空闲单跑；本机读数与其他会话并发时绝对值可差数倍，不作跨机契约）。
- 一次踩坑记录（值得写下来）：门禁的 CVE 检查用 `shutil.which('pip-audit')` 找可执行文件，
  在本会话这种没激活 venv 的最小 PATH 下 `.venv/bin/pip-audit` 看不见，于是按 fail-closed
  判红（`pip-audit not available; cannot verify no_unacknowledged_cve`）——**这是判据在正常工作，
  不是回归**；跑门禁要带 `PATH="$PWD/.venv/bin:$PATH"`。
- 未做且有意不做：不 `git push`、不动 tag、不重建 bundle、不重签 Ed25519、不放宽任何共享门禁。
  `audit_repo --strict` 仍按设计判红（锚点在 tag 上，不在 HEAD），留给属主的真实发布闭合。

