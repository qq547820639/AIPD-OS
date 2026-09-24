# F-DRAW-01 第 3 片：GD&T 特征控制框（FCF）按声明绘制并回读

日期：2026-09-24　范围：新增 `src/aipd_os/cad/gdt.py`、`src/aipd_os/cad/drawings2d.py`
（GDT 图层 + 逐视图画框 + 证据 `gdt_frames`/`gdt_issues`/`gdt_unmatched_features`）、
`src/aipd_os/cli/commands_drawing.py`（GD&T 问题判未收口 exit 4）、能力行 `cad.2d_drawings`
行内改写、新增常驻用例 `tests/test_cad_gdt_frames.py`（11 条）。

一句话结论：图纸从「只有尺寸与公差」推进到「能按声明画出形位公差框，且框挂在**实测**特征位置上」；
但**没有**假装它是 AutoCAD 语义实体——那一部分的编码本轮无法核实，写进限制里。

## 一、选型与诚实边界（都做过实测/检索）

1. **ezdxf 1.4.2 有 DXF `TOLERANCE` 实体**（读 `.venv/.../entities/tolerance.py`：
   `AcDbFcf` 子类，属性 `dimstyle`/`insert`/`content`/`extrusion`/`x_axis_vector`，
   `MIN_DXF_VERSION_FOR_EXPORT = DXF2000`）。实测：`Tolerance.new(...)` + `msp.add_entity()`
   存盘读回 1 个实体、`audit()` 0 错。**但 `Layout` 没有 `add_tolerance` 工厂**（实测
   `hasattr(Layout,'add_tolerance') == False`）。
2. **`content` 的转义码本轮没找到权威来源**：WebFetch ezdxf 文档站失败（fetch failed），
   WebSearch（"DXF TOLERANCE entity AcDbFcf text codes …"）命中的是厂商博客、知乎培训文与
   商业软件页面，不足以作为「AutoCAD 会怎么渲染这串字符」的依据。
   ⇒ 因此本模块**不宣称** FCF 在 AutoCAD/其他查看器里的渲染形状，只做可回读核验的那一半。
3. 候选对比（六维从略，关键是可核验性）：
   **A** 语义实体（`TOLERANCE`）：语义正确、能被 CAD 识别，但核心断言（渲染）在本环境**不可核验**；
   **B** drawn 几何（分格矩形 + 每格 TEXT + 引线）：存盘读回即可核验，代价是丢语义实体；
   **C** 两者都画：在 AutoCAD 里可能双份重叠。
   **选 B + 证据里留结构化框内容**（特征、符号、公差带、直径符号、基准链、挂点），
   让下游 CAD 能据此重建语义实体；A 作为已知路径写在 docstring 与限制里，不当已交付。
4. 符号表是**本仓选定的码位表**（`⌖ ⏥ ⏤ ○ ⌭ ⊥ ∥ ∠ ⌒ ⌓ ↗`，直径用 U+2300 `⌀`）。
   实测这些码位在 R2010 文本实体里存盘读回原样（`doc.encoding` 报 cp1252 但字节层原样往返）。
   不认识的特征（如同轴度）判 `characteristic_unsupported`，**不猜近似符号**。

## 二、口径

- **框只来自声明**：没有 `gdt` 就一张图都不画（用例断言 GDT 层零实体）；
- **挂点必须实测**：`feature` 用尺寸证据里的名字（`TOP.hole_2`），引线终点取该孔**投影测出**的
  圆心；基准也一样，`datums` 解析到具体特征后取其实测圆心写进证据；
- **不画半截框**：类型不认识、公差带 ≤0 或没给、该有基准却没给、基准字母解析不到、
  基准指向图上不存在的特征、声明的特征在图上不存在 ⇒ 该框一律不画，问题结构化返回，
  命令判未收口（exit 4）；
- 与公差声明解耦：`spec.features[]` 条目现在可以只带 `gdt` 不带 `tolerance`
  （改动点见 `resolve_spec_tolerances`，缺 `tolerance` 键即跳过尺寸公差，不影响 GD&T）。

## 三、真机端到端读数

内置黄金件（TOP，4 个 Ø8 孔），声明 `TOP.hole_2` 的位置度 ⌀0.05 |A|B（A→hole_1、B→hole_4）：

- DXF 里 GDT 层 **9 个实体**：4 个闭合分格矩形 + 4 条 TEXT（`⌖`、`⌀0.05`、`A`、`B`）+ 1 条引线；
- 证据 `gdt_frames[0]`：`attach=[-10.0, 0.0]`、`datums=[{A,attach=[-30.0,-0.0]},{B,attach=[30.0,0.0]}]`、
  `text="⌖|⌀0.05|A|B"`，`gdt_issues=[]`；
- 同一次运行里 `global_tolerance ±0.3` 让链叠加判 `inconsistent`（`worst=3.0 > closing=0.6`）
  ⇒ `rc=4` 来自叠加，与 GD&T 无关——两类门禁各自独立成立。

## 四、落点

| 位置 | 作用 |
|---|---|
| `src/aipd_os/cad/gdt.py:26` | `CHARACTERISTICS`：符号表 + 是否需要基准（本仓选定码位，不宣称渲染） |
| `:82` | `build_gdt_frames`：解析声明 → 框 / 问题 / 未匹配，六类不成立各自点名 |
| `:181` | `draw_frame`：分格矩形 + 每格 TEXT + 引线，全部落在 `GDT` 图层 |
| `src/aipd_os/cad/drawings2d.py:555` | `write_dxf`：建 GDT 图层、逐视图画框、证据新增 4 个键 |
| `src/aipd_os/cad/drawings2d.py:513` | 只带 `gdt` 不带 `tolerance` 的条目跳过尺寸公差应用（解耦点） |
| `src/aipd_os/cli/commands_drawing.py:142` | 打印每个框与每条 GD&T 问题；任一问题 ⇒ exit 4 |
| `src/aipd_os/registry_data.py` | `cad.2d_drawings` 行内：FCF 做到哪、用什么画的、为什么不算语义实体 |

## 五、用例与变异

11 条：声明驱动 3、基准必须解析 3、不臆造 4、CLI 判住 1。
变异 8 条全部打破：兜底符号（M1）、基准静默丢弃（M2）、挂点改声明坐标（M3）、忽略必须有基准（M4）、
`zone<=0` 放行（M5）、未匹配静默丢（M6）、基准特征不校验（M7）、CLI 不判住（M8）。

## 六、边界

- **未使用 DXF `TOLERANCE` 语义实体**（原因见一.2）；下游要语义版可据 `gdt_frames` 重建；
- 不做基准坐标系/最大实体条件（MMC/LMC）修饰符、不做复合框（多行 FCF）、
  不做 profile 的真实包络几何（只画框与文字）；
- 剖视与局部放大仍未做；`--spec` 仍只吃 JSON 文件。

## 七、收尾读数

- 全量回归：**1527 passed / 0 failed / 3 skipped**（本轮 +11 条）；
- `ruff check src tests state_service` 0；`mypy src tests` 0（**385** 文件）；
- `production_release_gate --release-ready --tag v5.6.0` 退出码 0（8/8）；
  `skill_quality_audit` 0/0；`state_perf_gate` **PASS**（load 4.12：
  `fact_batched_ops_s` 21333.9 ops/s、批处理比 0.0464、`nested_txn_marginal_us` 21.93µs）；
- 清单 **583 文件**（+2：`gdt.py` 与新用例），`SOURCE_MANIFEST.source_commit` 仍钉
  `a6604052`（v5.6.0 tag），未移 tag、未重建/重签 bundle、未 push；
- 提交：`fb6d467`（FCF 落图 + 用例 + 文档）/ `0016e46`（清单重锚）。
- 本轮自查抓到并改掉的两处自己的错：证据文档 §四 的行号是按记忆写的，逐条重新解析后修正
  （24→26、78→82、169→181、553→555、511→513、132→142）；CHANGELOG 锚点第一次没匹配上，
  先 grep 取到真实行再插条目，没有盲改。
