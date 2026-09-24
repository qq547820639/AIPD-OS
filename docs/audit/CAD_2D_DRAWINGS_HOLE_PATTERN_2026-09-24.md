# CAD 二维图纸落地 + 一处参数实现缺陷（F-CAD-01）

日期：2026-09-24 ｜ 轮次：v5.10 制造就绪之后、图纸链补齐 ｜ 锚点：`5f6d4dd`（未 push）

本轮把能力注册表里唯一还挂着「依赖外部工具」的商用主链环节——`cad.2d_drawings`
（想法 → 产品定义 → 手册/图纸治理 → BOM → 成本核算 → 发布门）——做成了真实可运行的
功能，并在做它的过程中用真实 CLI 跑出了一个**建模器的几何缺陷**。

---

## 1. 结论速览

| 项 | 读数 | 取证方式 |
|----|------|----------|
| `cad.2d_drawings` 分类 | `external_dependency` → **`partially_implemented`** | `scripts/capability_matrix.py --repo . --out docs/audit` 复算 |
| 全能力分布 | fully 36 / partially 28 / external 13 / 其余 0（共 77） | `docs/audit/capability_matrix.json` |
| 图纸用例 | 27 passed | `tests/test_cad_drawings2d.py` |
| CAD 黄金闭环用例 | 18 passed（新增 6 条） | `tests/test_cad_golden_loop.py` |
| 全量回归 | **1323 passed / 0 failed / 3 skipped**（清单重算后复跑） | 重算前那 2 条哈希失败见 §6 |
| F-CAD-01 | 已修 + 已入门禁 + 已配反证 | §5 |
| ruff（`src tests state_service`）/ mypy（359 文件） | 0 项 | CI 作用域 |

---

## 2. 技术选型调研（检索时间 2026-09-24）

按「先检索成熟实现再动手」的要求做了候选比较。**注**：本轮动手前未做完整书面调研，
实际调研发生在实现落定后的复核阶段（诚实声明，见 §7 的教训条目）；下表结论与已落
地的实现一致，因此没有引发返工，但顺序上不合规。

许可信息取自**本机已安装包的元数据**（`importlib.metadata`），不是记忆：
`cadquery 2.5.2` → `Apache Public License 2.0`；`ezdxf 1.4.2` →
classifier `License :: OSI Approved :: MIT License`。

| 候选 | 功能匹配 | License | 维护活跃度 | 安全风险 | 代码质量 | 适配成本 | 判定 |
|------|----------|---------|-----------|----------|----------|----------|------|
| **CadQuery/OCP `HLRBRep_Algo` + `ezdxf`**（选用） | 投影视图 + DXF 实体 + 标注，覆盖需求 | Apache-2.0 + MIT，与仓内既有依赖一致 | 二者均为本仓已声明依赖（`pyproject` 的 `cad` extra，`cadquery>=2.4`） | 纯本地几何计算，不新增网络面 | 内核即 OCCT | 0：模型构建已在用同一内核，只加一个 writer | ✅ 选 |
| `pythonocc-core` 直接调同一内核 API | 同上（同一 OCCT） | LGPL-2.1 + OCCT 例外 | 活跃 | 同上 | 同上 | 需新增一份与 cadquery 重叠的内核绑定，双依赖 | ✗ 无收益 |
| FreeCAD `TechDraw` | 成品图纸方案，功能最全 | GPL（与本仓许可不兼容） | 活跃 | — | 高 | 需整套 App；官方仓库 issue #5710 反映**无头导出**长期是缺口 | ✗ 许可 + 部署 |
| `trimesh` 网格切片 | 只给轮廓线，无 B-Rep 相切/隐藏线语义，无标注 | MIT | 活跃 | — | 中 | 低 | ✗ 表达力不足 |

选定理由：功能全部落在**已有依赖**能覆盖的范围里，符合「优先直接复用成熟方案」；
FreeCAD 路线唯一能多给的是 GD&T/标题栏模板，但 GPL 与无头运行两条都卡。

来源（本轮真实访问）：
- [HLRBRep_Algo Class Reference — Open CASCADE Technology](https://dev.opencascade.org/doc/refman/html/class_h_l_r_b_rep___algo.html)
- [OpenCASCADE Hidden Line Removal](https://www.cnblogs.com/opencascade/p/4204323.html)
- [freecad TechDraw 工作台中虚线（隐藏线）的实现方式](https://m.blog.csdn.net/njsgcs/article/details/148287791)
- [TechDraw: Ability to "Headless" export of SVG and PDF — FreeCAD#5710](https://github.com/FreeCAD/FreeCAD/issues/5710)
- [FreeCAD 许可证页](https://wiki.freecadweb.org/Licence/zh-cn)
- 未检索到「可嵌入的、许可证兼容的 STEP→带标注工程图」现成 Python 库；故图纸层
  （视图布局/尺寸/标题栏）按 OCCT 语义自写，几何层全部复用内核。

---

## 3. 实现要点（`src/aipd_os/cad/drawings2d.py`）

- **视图基**：`view_basis(direction, up)` 取 `R = U × N`，实测满足右手系且不镜像；
  六个标准视图 `FRONT/TOP/RIGHT/REAR/LEFT/BOTTOM`。
- **投影离散化**：`HLRBRep_Algo` + `HLRAlgo_Projector` 出边，`GCPnts_QuasiUniformDeflection`
  采样（弦高 `DEFAULT_DEFLECTION = 0.05 mm`）。OCCT 输出是 `(u, v, 0)` 视图坐标，
  不能再与本仓基向量点乘（早期版本把视图高算成 0，就是这样发现的）。
- **可见/隐藏分类 = 逐点射线遮挡**，不是 OCCT 的隐藏线化合物。依据是本构建实测：
  对实心盒 `VCompound()` 仍给出 8 条边（即未去掉隐藏线），`HCompound()` 恒为 0。
  遮挡判据 `IntCurvesFace_ShapeIntersector` 从**未平移**的投影点沿视线正向求交；
  早期把起点朝观察者外推 `OCCLUSION_EPS` 会让隐藏线恒为 0。
- **孔的识别 = Kåsa 代数圆拟合**（3×3 高斯消元）+ 闭合折线 + 残差 ≤ `max(tol·r, 2·deflection)`
  + 角向覆盖 ≥ 300° + 按 `(cx, cy, r)` 去重。四分之一圆角弧因覆盖不足被排除。
- **尺寸全部来自图上测量**（视图包围盒 + 拟合圆直径），不读参数字典——这样图纸用例
  同时检验「模型是否按声明构建」和「图纸是否忠实于模型」。
- DXF：`ezdxf.new('R2010', setup=True)`，图层 `OUTLINE/HIDDEN/DIMENSION/TEXT/FRAME`，
  隐藏线用非连续线型；并写 `<name>.evidence.json`  sidecar（视图位置、实体计数、
  字节 sha256、工具版本、`hidden_line_method` 说明来源）。
- 内核缺失时（`cadquery`/`ezdxf` 不可导入）CLI 返回 rc 4 的 `HOLD` 外部任务包，
  **不写任何文件、不外推结果**（`src/aipd_os/cli/commands_drawing.py`）。

---

## 4. 一次「量具假绿」的实录

真实 CLI 首次跑通时，黄金支架（声明 4×Ø8）报出的却是 **6 个孔、圆心 x ∈ {-40, -30, 0}**，
而当时单孔板的 19 条图纸用例全绿。根因：`detect_circles` 用「折线包围盒中点 + 盒宽」
充当圆心与直径——它在单孔板上恰好正确，在多孔件上把外轮廓也算成了「圆」。

教训：**只断言数量与直径的用例，掩不住位置错误**。补上的三条断言（`TestRealBracketPattern`）：

1. 4 个孔的 x 坐标必须逐一对上真值 `[-30, -10, 10, 30]`；
2. 圆角/倒角投出的弧段不得冒充孔（数量恰为 4）；
3. **负控**：孔阵整体平移 5 mm，检出中心必须同步平移——证明位置断言真的在约束输出，
   而不是恰好成立。

修复后同一 CLI 的真实读数（`aipd drawing generate --native releases/golden-projects/B-cad-engineering-change/bracket.py --views FRONT,TOP`）：

```
FRONT 100.0×10.0  visible 34  hidden 4
TOP   100.0×50.0  visible 56  hidden 0
  hole Ø8.0 at [-30,-0] [-10,0] [10,0] [30,0]
entities LWPOLYLINE 38 / LINE 58 / DIMENSION 8 / TEXT 18   bytes 76454
```

---

### 4.1 未跑过的入参分支 = 没交付：`--step` / `--native` 补测又抓出一处

写这轮文档时回头查覆盖，发现 `cmd_drawing` 只有 **HOLD 分支**有常驻用例，
`--native` 与 `--step` 全靠我手工命令验证。补 `TestCliInputPaths` 三条后，
第一条真跑就红了：`.evidence.json` 里**没有** `model_source`/`tool`/`ok`/`status`——
`generate_drawing` 先写 sidecar，`cmd_drawing` 之后才把溯源字段 `update` 进返回字典，
于是「本次输出说了画的是哪个模型」这件事**不落盘**。归档图纸时会丢掉来源。

修法：溯源在出图前就进 `provenance`，由 `generate_drawing` 唯一一次写盘，
磁盘证据与 stdout 同形（`evidence_file` 一条除外，它天然只能在写后加）。
现状钉住用例：默认回退（既无 `--step` 也无 `--native` ⇒ 用默认黄金模型）
必须在证据里点名 `model_source == "golden_default"`，翻转条件已写进 docstring。

教训：**手工跑过不等于有常驻断言**；一个从未被用例走过的入参分支，
它的证据链是否完整是未知的——本轮两处假绿（§4 的圆心、此处的 sidecar）都出自这类分支。

## 5. F-CAD-01：`hole_count=4` 实际只钻出 3 个孔（已修）**发现方式**：为 §4 定位「孔位为何对不上参数」时，直接量 B-Rep 的圆柱面，得到
`x = -40, -30, 0`——三个孔位，不是四个。也就是说图纸没错，**模型是错的**。

**根因**（实测三种写法，非推测）：CadQuery 的 `Workplane.center(x, y)` 相对
**当前笔位**偏移，而 `hole()` 不重置笔位，所以逐点循环里偏移会累加：

| 写法 | n=1 | n=2 | n=4 |
|------|-----|-----|-----|
| 循环 `center()` + `hole()`（旧） | `[0]` ✅ | `[-16.667, 0]` ✗ | `[-40, -30, 0]` ✗（4 次布尔只留 3 个孔位，两孔重合） |
| 一次 `pushPoints(pts)` + `hole()`（新） | `[0]` ✅ | `[-16.667, 16.667]` ✅ | `[-30, -10, 10, 30]` ✅ |

**影响面**：黄金件是「参数化 CAD + 工程变更」演示件；孔数/孔位错 ⇒ 体积错 ⇒
BOM 数量与模具摊销/成本核算跟着错，图纸也是错图的忠实投影。`n=1` 时恰好正确，
所以只要没人把 `hole_count` 调到 2 以上就看不见。

**修法**：`src/aipd_os/cad/backends.py`
- 新增 `_hole_pattern(length, count)` 作为孔阵**唯一真值源**；
- `_build()` 与 `.py` 模板各改用一次 `pushPoints(...).hole(HD)`（两处曾是同一份错误代码）。

**新增门禁**：`_verify_declared_features()` 把「声明的孔数/孔径/孔位」和实体上量到的
整圈通孔逐一对账，接进 `geometry_validity_check()`（`checks['declared_features']`）。
量具本身不读 OCCT 私有面类型：整圈圆柱面侧面积 `A = 2πrh` 反解 r，再要求包围盒
`xlen = ylen = 2r`（圆角的四分之一弧不满足），圆心取 `Face.Center()`。

**双向反证**（常驻用例 `test_hole_gate_fires_on_legacy_cumulative_center_loop`）：
把 `_build` 退回旧的逐点写法后——`n=4` 判红，错误消息带两侧清单；`n=1` 仍判绿。
后者同样必要：它证明这扇门不是「永远红」。

另有负控 `test_through_hole_measurement_ignores_partial_arc_faces`：只含圆角的件量出
0 个孔，含一个 Ø6 孔的件量出 `r=3`、`center=(5,0)`、`depth=10`。

---

## 6. 门禁与遗留

- 全量回归 2 条失败：`tests/test_packaging.py::test_{source,release}_manifest_hashes_match_disk`。
  原因是本轮改动了被清单跟踪的 `SKILL.md`、`src/aipd_os/cad/backends.py`、
  `src/aipd_os/cli/{command_contract,commands,main}.py`、`src/aipd_os/registry_data.py`。
  处理方式沿用 P2：改完内容后重生成清单，`SOURCE_MANIFEST.source_commit`
  **仍锚在 `v5.6.0` tag 提交**，不移动 tag、不重签名、不 push。
  §4.1 的 sidecar 修复之后这两条又红了一次（同一机制，不是回归）。
- 收尾读数：`production_release_gate --release-ready --tag` **8/8 绿**（exit 0），
  `state_perf_gate` **PASS**（批处理比 median 0.0161 ≤ 0.34），
  `skill_quality_audit` 0 警告 0 失败，`audit_repo --strict` 仍按既有原因红：
  「Provenance source commit mismatch: manifest=a660405… vs HEAD=…」——
  即发布锚点仍在 tag 上、本轮提交未发布，属预期状态而非本轮引入。
- **已发布黄金工件未再生成**：`releases/golden-projects/B-cad-engineering-change/`
  里的 `bracket*.py/step` 与 `report.json` 仍是修复前的几何（3 孔），其
  `source_commit = d58ab14…`。本轮没有覆盖它们：用未提交的代码重算出的字节，去声称
  来自某个已发布提交，是伪造证据。发布时由 owner 显式再生成：
  `AIPD_GOLDEN_RELEASE=1 .venv/bin/python -m pytest tests/test_golden_projects_e2e.py -q`
  （`tests/test_golden_projects_e2e.py:47` 的 pin 模式开关）。

## 7. 未做 / 边界（诚实清单）

- 图纸不含：GD&T 形位公差框、尺寸链与公差叠加、剖视/局部放大、爆炸图、装配图
  ⇒ C6「生产图纸包」整体仍不成立（已写进 `cad.2d_drawings` 的 `current_limitation`）。
- 相切轮廓只判出一侧：竖直孔筒壁轮廓线 `x=±3` 从正视图看与圆柱面相切，逐点射线在
  切点不可靠。已用 `TestTangencyLimit` **钉住现状**并写明翻转条件，不当已修。
- 隐藏线不是 OCCT 正式 HLR 结果，evidence sidecar 里用 `hidden_line_method` 声明了来源。
- 调研顺序不合规（§2）：功能已实现后才补的候选对比。影响后续纪律：**较大技术方案
  先出候选表再动手**，本轮把它写进本文档而不是事后修改成「当初就查过」。

## 8. 复算入口

```bash
.venv/bin/python -m pytest -q tests/test_cad_drawings2d.py tests/test_cad_golden_loop.py
.venv/bin/python scripts/capability_matrix.py --repo . --out docs/audit
.venv/bin/python scripts/skill_quality_audit.py
.venv/bin/python -m aipd_os.cli.main drawing generate \
  --native releases/golden-projects/B-cad-engineering-change/bracket.py \
  --out /tmp/bracket.dxf --part golden_bracket --revision A --views FRONT,TOP --json
.venv/bin/ruff check src tests state_service && .venv/bin/mypy
```
