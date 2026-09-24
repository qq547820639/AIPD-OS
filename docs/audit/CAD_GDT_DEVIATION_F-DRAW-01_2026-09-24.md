# F-DRAW-01 第 7 片：位置度偏差拿实测圆心核对，超带的框不再当覆盖凭据

日期：2026-09-24　范围：`src/aipd_os/cad/gdt.py`（`_basic_point` / `_position_check` /
框新增 `basic`、`deviation_mm`、`within_zone`、`verified`）、`src/aipd_os/release_manifest.py`
（超带不盖章 + 覆盖条目带 `verified`）、`src/aipd_os/cli/commands_drawing.py`（读数与未收口打印）、
能力行 `cad.2d_drawings` 与 `industrialize.release_evidence` 行内改写、
新增常驻用例 `tests/test_cad_gdt_deviation.py`（13 条）。

一句话结论：GD&T 覆盖从「画上去了」升级到**数值核对**——理论精确位置由需求侧声明，
投影实测圆心由模型侧量出，两边独立，所以这一半判据不是自证；
而**偏差超带的框不再被门禁当作覆盖凭据**。

## 一、缺的不是判据，是输入

第 6 片收尾时能力行明写：形位那一半「**不**核形位偏差数值」。当时不是不想核，
而是没有可核的输入：位置度成立与否取决于「理论精确位置（theoretically exact location）」，
它

- 不在图纸几何里——投影只能量出**实际**圆心；
- 不能从公差带反推——那等于把要求当事实；
- 不能拿实测值当标称——那是让被检对象给自己定基准（第 4、5 片已两次踩过同一形状）。

所以本片把理论位置作为**声明的一部分**接进来：`gdt` 条目带 `basic: [x, y]`，
与挂点同一套视图坐标、同一单位；`spec_from_ctq` 原样透传，需求侧写一次即可。

## 二、口径（六条，全部写成用例）

1. **直径带按 `2 × 距离`**：偏差 = `2 × hypot(实测 − 基本)`；非直径带按方形带，
   两个方向各自不越过半个带宽；
2. **偏差 == 带 ⇒ 合格**：边界值不判罚，容差是噪声级的 `POSITION_DEV_TOL = 1e-6`
   （圆拟合与离散化在这个量级）；
3. **二维距离，不是一维相减**：纯 y 偏心同样开火（防「只比 x」的实现自欺）；
4. **没给 `basic` ⇒ 点名 `position_basic_missing`**（阻断），
   不拿实测圆心当理论位置、不拿 `(0,0)` 兜底、也不默认「偏差就是 0」；
5. **形状/方向类不假装**：平面度等需要整面采样，本仓内核不做 ⇒
   `deviation_mm = None`、`within_zone = None`、`verified = "presence_only"`；
6. **超带不盖章**：`release_manifest` 见到 `position_deviation_exceeded` 的特征
   **不**计覆盖（`gdt` 数组里不出现它），并落一条带数值的阻断问题。

## 三、真机端到端读数（临时目录，黄金件，输出原文）

种子 2 条 CTQ：`T-001` 基准 A（`TOP.overall_width`）、
`T-002` 孔位置度（带 0.05 直径带、基准 A、`basic: [-30.04, 0.0]`——**故意**与实测偏心 0.04）。

```
$ aipd drawing spec --db state.db --project dev-demo --out spec.json      # rc=0
  基准 A → TOP.overall_width（CTQ T-001）
  TOP.hole_1: 形位 position 带 0.05 ← CTQ T-002

$ aipd drawing generate --out p.dxf --part GOLD --views TOP --spec spec.json   # rc=4
  GD&T 框 TOP→TOP.hole_1：⌖|⌀0.05|A（挂点 [-30.0, -0.0]，来自实测，位置度实测偏差 0.08 / 带 0.05（超带））
  GD&T 形位未收口：position_deviation_exceeded TOP.hole_1 类型 position 偏差 0.08 > 带 0.05
```

同一张图交给发布证据装配：

```
$ aipd release manifest --db state.db --project dev-demo --drawing p.dxf --out ev.json   # rc=4
  [阻断] position_deviation_exceeded: TOP.hole_1 的位置度实测偏差 0.08 超出公差带 0.05（CTQ T-002）
  gdt = []        ← 覆盖被拒：不能拿一条没达成的要求给自己盖章
```

对照的一极（`basic` 给成实测同位 `[-30.0, 0.0]`）：出图 `rc=0`，
框读数 `位置度实测偏差 0 / 带 0.05（合格）`，覆盖条目
`covered_by=feature_control_frame`、`verified=deviation`（用例
`test_a_within_zone_frame_is_counted_and_says_it_measured_the_deviation`）。
证据 JSON 里 `basic/deviation_mm/within_zone` 三件套存盘读回一致
（`test_deviation_survives_the_dxf_round_trip_as_evidence`）。

夹具量出的前提（写进用例）：100×20×10 板 + 4 个 Ø6 通孔在 `y=0`、`x=-30,-10,10,30`
⇒ TOP 视图 `TOP.hole_1` 实测圆心 `(-30.0, 0.0)`。

## 四、落点

| 位置 | 做了什么 |
| --- | --- |
| `src/aipd_os/cad/gdt.py:26` | `import math`（偏差要开方） |
| `src/aipd_os/cad/gdt.py:50` | `POSITION_DEV_TOL = 1e-6`：边界与噪声容差 |
| `src/aipd_os/cad/gdt.py:168` | 每个框算一次 `_position_check` |
| `src/aipd_os/cad/gdt.py:171` | 没有理论位置 ⇒ `position_basic_missing`（阻断），结论留 `presence_only` |
| `src/aipd_os/cad/gdt.py:176` | 超带 ⇒ `position_deviation_exceeded`（带 basic/measured/deviation/zone/ctq_ref） |
| `src/aipd_os/cad/gdt.py:205` | `_basic_point`：只收两个真数，脏值与缺省一律按「没给」 |
| `src/aipd_os/cad/gdt.py:218` | `_position_check`：直径带 `2×距离`、方形带分轴、形状类不参与 |
| `src/aipd_os/release_manifest.py:154` | 汇总本图上超带的特征 |
| `src/aipd_os/release_manifest.py:160` | 超带的框不计覆盖，另落阻断问题 |
| `src/aipd_os/release_manifest.py:187` | 覆盖条目新增 `verified`（deviation / presence_only） |
| `src/aipd_os/cli/commands_drawing.py:215` | 框读数带「实测偏差 x / 带 y（合格/超带）」 |
| `src/aipd_os/cli/commands_drawing.py:227` | 未收口前缀改为「GD&T 形位未收口」并附数值 |

## 五、用例与变异（6 条变异全部被杀）

`tests/test_cad_gdt_deviation.py` 13 条，4 类：
`TestDeviationIsMeasuredNotAssumed`（7）、`TestCliHoldsOnDeviation`（3）、
`TestProducerCarriesBasic`（1）、`TestManifestRefusesBadCoverage`（2）。

| 变异 | 杀于 |
| --- | --- |
| Q1 没给 basic 时拿实测圆心当理论位置 | `test_position_without_basic_is_named_not_defaulted`、`test_a_missing_basic_holds_the_command` |
| Q2 直径带忘了乘 2 | `test_offset_beyond_half_the_diametral_zone_is_a_violation` 等 5 条 |
| Q3 边界值判罚（`<=` 改 `<`） | `test_deviation_exactly_equal_to_the_zone_is_inside` |
| Q4 只核 x 不看 y | `test_y_component_counts_too` |
| Q5 形状类也假称核过偏差 | `test_a_shape_control_claiming_no_deviation_stays_presence_only` |
| Q6 门禁照旧给超带的框盖章 | `test_an_out_of_zone_frame_is_not_counted_as_coverage` |

两个源文件还原后与原件逐字节相同。另记一处**测量脚本自己的坑**（不改结论但值得留）：
第一次量 `drawing generate` 的退出码时写成 `… | tail -4; echo rc=$?`，
`$?` 记的是 `tail` 的 0——真值是 4。判退出码必须用不带管道的运行（本轮已按此复核）。

## 六、边界

- **只核位置类**：`position` 之外（平面度、垂直度、轮廓度、圆跳动等）仍只到
  `presence_only`；要往那一步走需要整面/整轴采样与基准体系构建，是独立的一片；
- **基准体系是二维视图内的点**：`basic` 与该视图的挂点同坐标同单位，
  不做三维基准参照系（DRF）投影，也不做基准修饰符（MMC/LMC）；
- 理论位置**只能来自声明**：图上不会自动长出「 nominal 位置」，
  生产者也不按孔径/孔距推算它——第 5 片的「不猜」口径在这里同样成立；
- 偏差用**投影圆心**，即圆拟合后的二维位置；孔轴倾斜造成的投影椭圆化不在本片口径内；
- 图纸侧仍未做：剖切符号 A-A/阶梯剖、局部放大、爆炸图、装配图；
  发布锚点与版本号双轨制仍属属主的真实发布动作。

## 七、复算

```bash
cd AIPD-OS
.venv/bin/python -m pytest tests/test_cad_gdt_deviation.py tests/test_cad_gdt_frames.py \
  tests/test_release_manifest.py -q
.venv/bin/python -m ruff check src tests state_service
.venv/bin/python -m mypy src tests
# 真机序列见第三节（跑门禁须带 PATH="$PWD/.venv/bin:$PATH"；
# 判退出码不要用管道）
```

## 八、收尾读数（全部来自本轮实跑输出，非记忆）

- 提交：实现 `174ac0f`（CAD: measure position deviation against the true position and refuse
  bad coverage）、产物重锚 `f967840`（Release artifacts: re-anchor manifests after the
  position-deviation slice），本节所在提交是本轮第三个；
- `regenerate_release_manifest.py --version 5.6.0` → **587 个文件**（586 → 587 = 新增的
  `tests/test_cad_gdt_deviation.py`；审计文档在 `docs/audit/` 下，两份清单整体排除该前缀）；
- `release_evidence.py --bundle releases/aipd-os-5.6.0.zip --version 5.6.0
  --test-report docs/audit/pytest-report-v5.6.0.json
  --source-commit a66040520139405095648461f7144d4f00629924` → 重写三份清单/溯源，
  bundle 未重建、未重签、tag 未动；
- 重锚前全量：**1582 passed / 2 failed / 3 skipped**（两条仍是 packaging 的清单哈希，
  正是这次重锚要清掉的）；重锚后：**1584 passed / 0 failed / 3 skipped**（118.84s）；
- `production_release_gate --release-ready --tag v5.6.0`：**rc=0，8/8 全绿**，
  `test_numbers_from_report` 读数 `passed=1096 failed=0 total=1099
  source_commit=a66040520139405095648461f7144d4f00629924`；
- `skill_quality_audit`：**0 项警告 0 项失败**；`state_perf_gate`：**PASS**（空闲单跑）。

一处**顺序**教训（本轮实测到，值得写在案上）：产物提交**之前**跑发布门禁，
`workspace_clean` 必然判红——读数 `[' M PROVENANCE.json', ' M RELEASE_MANIFEST.json',
' M SOURCE_MANIFEST.json', ' M docs/audit/pytest-report.json']`，`release_ready: False`，
其余 7 项全绿。这不是回归，是判据要求「发布产物已入库」。
所以每轮的顺序是：清单重算 → 全量复跑 → **提交产物** → 再跑门禁取 8/8。
本轮先按旧顺序跑了一次，取到 `rc=2`，提交后重跑才拿到 `rc=0`；
两个读数都留在这里，免得下一次把「先跑后跑」的差异当成不稳定。

- 未做且有意不做：不 `git push`、不动 tag、不重建 bundle、不重签、不放宽任何共享门禁；
  `audit_repo --strict` 仍按设计判红（锚点在 tag 而非 HEAD），留给属主的真实发布闭合。
