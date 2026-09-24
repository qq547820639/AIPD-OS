# F-DRAW-01（第 1 片）：尺寸链与按声明的公差 —— 取证与落点

日期：2026-09-24　范围：`src/aipd_os/cad/drawings2d.py`、`src/aipd_os/cli/commands_drawing.py`、
`src/aipd_os/cli/main.py`、`src/aipd_os/registry_data.py`、
新增常驻用例 `tests/test_cad_drawings_chain_tolerance.py`（23 条）。

一句话结论：二维图纸从「只有总体宽/高和孔径、没有任何公差」推进到「尺寸链按实测孔心
自动排出并核对闭合、公差只允许来自声明且能被打在图纸上」；公差声明仍只吃 JSON 文件，
未与 Product Truth 的零件规格打通，GD&T/剖视/叠加分析未做，C6 生产图纸包不成立。

## 一、本轮取证（全部为实测读数，非推断）

1. **改前图纸不含链也不含公差**：`_measure_dimensions` 只产出 `overall_width`/`overall_height`
   /`hole_diameter` 三类；`write_dxf` 只画两个线性尺寸加孔径；`registry_data.py` 的
   `cad.2d_drawings.current_limitation` 自陈「未实现：……尺寸链/公差叠加……」。
2. **孔心只在孔轴垂直于视图的方向上可测**：100×20×10 板、4 个 Ø6 竖直孔，
   TOP 视图检出 4 个 `diameter=6.0` 闭合圆，FRONT/RIGHT 各检出 0 个 ⇒ 链只能长在 TOP。
   真实黄金件端到端读数：TOP dims=11（2 总体 + 4 孔 + 5 链）、FRONT dims=2、RIGHT dims=2。
3. **ezdxf 1.4.2 的公差符号约定与直觉相反**（读 `.venv/.../ezdxf/render/dim_base.py:205-212`）：
   `set_tolerance(upper, lower)` 把两值**原样**写进 `dimtp`/`dimtm`
   （`entities/dimstyleoverride.py:287-299`），而渲染下偏差时取 `sign_char(tol_lower * -1)`
   ⇒ `dimtm` 存的是「下偏差的相反数」。把 -0.05 当 lower 原样传入，图纸上打成 `+0.05`
   （实测读数 `\S+0.05^ +0.05;`，一条双向正的假公差）。正确写法 `set_tolerance(upper, -lower)`。
4. **四种偏差形状渲染后逐一核对**（同一块板、存盘再读回）：
   `+0.05/-0.05 → ±0.05`；`+0.10/-0.02 → \S+0.10^ -0.02;`；`+0.05/+0.01 → \S+0.05^ +0.01;`；
   `0.025（dimtdec=3）→ ±0.025`。
5. **`dimtdec` 默认 2 会把细偏差截断**：0.005 在默认显示位数下渲染成 0.01 ⇒ 显示位数必须由
   声明精度反推（`_tolerance_decimals`），且只允许「显示更多位」不允许更少。
6. **override 只在 `render()` 时落到实体**：只 `set_tolerance` 不渲染，读回 `dimtol` 是缺省 0。
   本轮前我据此以为「必须显式 `commit()`」——变异 M2（删掉 `commit()`）50 条用例全绿
   **证伪了这个说法**：`render()` 内部自带提交。代码里的冗余 `commit()` 已删，模块 docstring
   改成实测口径。这一条记在这里是因为「我以为已验证的结论」被自己的变异台打掉了。
7. **内核检出顺序 ≠ 实测 x 顺序**（grid 图样：`(-30,5),(30,-5),(-10,-5),(10,5)`）：
   检出顺序 `[(-10,-5),(30,-5),(-30,5),(10,5)]`，x 递增顺序 `[(-30,5),(-10,-5),(10,5),(30,-5)]`。
   首轮用的乱序图样（同 y 只打乱 x）检出顺序恰好等于 x 递增 ⇒ 变异 M4 当时**幸存**，
   换成 grid 图样后 M4 被打破。用例里加了「两种顺序必须仍可区分」的前提断言，
   这样图样失效时会显式报错而不是守卫静默变绿。
8. **DXF 尺寸实体的几何分两种**（存盘读回）：线性尺寸 `dimtype=32`，度量点在
   `defpoint2/defpoint3`；直径尺寸 `dimtype=35`，`defpoint2/3` 为空，弦两端在
   `defpoint/defpoint4`，`hypot=6.0`。⇒ 「文字 vs 几何是否分裂」的核验必须分两型处理，
   用同一套 defpoint 会读成 `None`。
9. **真实件端到端（`aipd drawing generate --spec`）**：声明 3 项（1 项故意写成图上没有的
   `TOP.hole_99`）+ 全局 ±0.2 ⇒ 登记 15 处尺寸 = DXF 里 15 个 `DIMENSION` 实体，
   15 处带公差，读回偏差集合 `{(0.05,-0.05),(0.1,-0.1),(0.2,-0.2)}`，
   TOP 链 5 段闭合差 0.0，`spec_unmatched_features=['TOP.hole_99']`，**退出码 4**。
   （说明：这条命令里 `--native` 的 shell glob 没匹配到文件、实参为空，走的
   `golden_default` 内置黄金件；结论按「内置黄金件」读，不是按外部 STEP 读。）
10. **下一片入口已验**：ezdxf 有 DXF `TOLERANCE` 实体类（`ezdxf.entities.tolerance.Tolerance`，
    即 GD&T 特征控制框），但 `Layout` 上**没有** `add_tolerance` 工厂 ⇒ 形位公差框要自己
    造实体，不是现成 API。

## 二、候选方案调研与选型（六维）

本轮新增的是「出图能力」，不是通用算法，因此候选按「谁来做链与公差」列。
License 由 GitHub API / PyPI JSON 现查：`tolerance-stackup-cli` = MIT、1 star、
唯一一次 push 2026-07-12；`steputils` 0.1 = MIT（PyPI classifiers 明列）。
诚实边界：C 只查了仓库元数据、**未读其源码**；D **未安装、未读源码**，一律不作为采信依据。

| 维度 | A ezdxf 一等公差 + 自排链（选定） | B steputils | C tolerance-stackup-cli（GitHub 检索命中） | D FreeCAD TechDraw 无头 |
|---|---|---|---|---|
| 功能匹配度 | 高：公差是 DXF 实体属性，链的几何必须从本仓投影量出 | 低：做 ISO 配合查表（H7/g6）与极限换算，不出 DXF | 中低：CSV 尺寸链的最坏值/RSS 叠加，不画尺寸也不写文件 | 高：完整工程图台架，但含我们不需要的 GUI 栈 |
| License 兼容性 | MIT（已是本仓依赖） | MIT（未采） | MIT（许可不是障碍，障碍在来路与功能面） | 主程序 GPL 系，与「本地纯 Python 内核」路线冲突 |
| 维护活跃度 | 高（本仓锁 1.4.2，源码在场） | 中 | 1 star、2026-07 新建，样本量不足以判断 | 高（但非本仓可控依赖） |
| 安全风险 | 无新增依赖、无外部进程 | 新增依赖换不来渲染能力 | 单文件零依赖但来路薄，引入即自建供应链信任 | 引入外部可执行程序与 IPC 面 |
| 代码质量 | 语义可由本仓读源码定案（本轮就是这么定 dimtm 的） | 未读源码，不作评价 | 未读源码，不作评价 | 未读源码，不作评价 |
| 适配成本 | 最低：`set_tolerance` + `commit/render` 实测四种偏差形状即定案 | 需再加一层 DXF 写出，等于把 A 再做一遍 | 需把几何测量结果导出 CSV 再喂回来，且仍要自己画 | 需装内核、走无头脚本，DXF 所有权不在本仓 |

**选定 A**，理由三条：① ezdxf 已是本仓 DXF 写出依赖，零新增依赖；② 公差的正确性问题是
「写进 DXF 的属性语义」，只有能读一手源码才能定案（事实 3/4/6 全部来自源码 + 存盘读回），
外部库反而把语义包黑；③ 链的各段值必须来自本仓投影出来的孔心（事实 2），任何外部
「尺寸链库」都没有这个几何来源，能借的只有算术。
**明确不选**：把一个 1-star、未审阅的叠加分析仓库引入成算术权威（C）；「公差叠加分析」
因此留在未实现清单里，不在本轮做。同时借鉴了它的思路一处：链与叠加是两件事——
本轮只画链并核对「图上印出来的各段之和 == 总体宽」，不做统计叠加。

## 三、落点

| 位置 | 作用 |
|---|---|
| `src/aipd_os/cad/drawings2d.py:71-75` | `DIMSTYLE`、链/总体尺寸的引出距离与 `MIN_TOLERANCE_DECIMALS` 常量 |
| `:89` | `ViewGeometry.chain_check` 字段（每视图一条闭合核对） |
| `:403` | `_measure_dimensions`：三类尺寸统一带 `feature` 名与 `tolerance` 位（缺省 None） |
| `:428` | `_holes_in_measured_order`：孔编号按实测 (x, y) 排，不按内核检出顺序 |
| `:433` | `_chain_dimensions`：「左沿→孔心…→右沿」，同 x 去重，<2 站不给链 |
| `:453` | `_chain_check`：用**四舍五入后的显示值**求和比对总体宽（要抓的是标注本身不闭合） |
| `:477` | `_tolerance_decimals`：显示位数按声明精度取，只多不少 |
| `:486` | `_declared_tolerance`：只认显式 upper/lower，缺项即 `ValueError`，不做缺省推断 |
| `:502` | `resolve_spec_tolerances`：贴声明公差 + 统计 `tolerance_applied` / `spec_unmatched_features` |
| `:614` | `_set_dim_tolerance`：`set_tolerance(upper, -lower, dec=…)`（事实 3 的正确写法） |
| `:628` | `_linear_dim`：统一的「建尺寸 → 贴公差 → render」路径（事实 6：render 才落实体） |
| `:636` | `_draw_view`：链一行、总体宽在链外侧一行、孔径公差同源 |
| `:546` / `:711` | `write_dxf`/`generate_drawing` 增 `spec=`，证据新增 4 个键 + 每视图 `chain_check` |
| `src/aipd_os/cli/commands_drawing.py:16` | `_load_spec`：文件不存在 / 非 JSON / 顶层非对象 ⇒ 退出码 2，不落图纸 |
| `:82`、`:127` | `--spec` 接到 `generate_drawing`；**声明落空即判未收口（退出码 4）** |
| `src/aipd_os/cli/main.py:226` | `drawing generate --spec` 参数面（help 里直接写 JSON 形状） |
| `src/aipd_os/registry_data.py:59` | `cad.2d_drawings` 行内改写：链/声明公差已实现，未实现项逐项点名 |
| `tests/test_cad_drawings2d.py:322` | 登记表守卫：`unit_test` 改为「列出的文件都得存在」+ 已落地能力也必须写进行内 |

证据新增键：`dimension_chain_check`（按视图）、`tolerance_applied`、`spec_declared_features`、
`spec_unmatched_features`、`global_tolerance_declared`，以及每视图 `chain_check`、每条尺寸的
`feature`/`tolerance`。

## 四、用例与变异对照

`tests/test_cad_drawings_chain_tolerance.py` 23 条：链 5、公差来源 6、DXF 自洽 3、
渲染文字 6（含 4 种偏差形状的参数化）、CLI `--spec` 4。
读数一律用 ezdxf **重新读回文件**取，不靠内存对象；渲染文字读的是块里的 MTEXT（事实 3/4
只有读文字才抓得住符号错）。

变异台（每条都必须打破用例；`landed=True` 表示已 grep 确认改动真落盘）：

| 变异 | 结果 | 打破的用例 |
|---|---|---|
| M1 `set_tolerance(upper, lower)`（丢 `-`） | 红 6 | 渲染文字 4 条 + `tolerance_lands_only…` + `global_tolerance_covers…` |
| M3 无声明也顺手给 ±0.1 | 红 10 | `no_spec_means_no_tolerances_anywhere`、CLI 两条、渲染文字全部… |
| M4 孔编号按检出顺序 | 红 1 | `features_are_named_by_measured_order_not_detection_order` |
| M6 链不含两端边距 | 红 5 | 闭合、跟几何、链段几何、命名、`view_geometry_carries…` |
| M7 显示位数写死 2 | 红 2 | `0.025` 参数化用例 + `tolerance_shown_in_full_not_truncated` |
| M8 链段不做同 x 去重 | 红 1 | `no_chain_when_holes_share_one_axis_position` |
| M5 CLI 无视未匹配声明 | 红 1 | `unmatched_declaration_holds_the_command` |
| M2 删掉 `commit()` | **绿（幸存）** | 证伪了「必须显式 commit」的既有说法 ⇒ `render()` 内部已提交，冗余调用已删；记录于事实 6 |

## 五、边界（本轮没做、也没声称做的事）

- **公差叠加分析**不做：链只保证「印出来的各段之和 == 总体宽」，不做统计/最坏值叠加。
- **GD&T 形位公差框**不做；入口已验（事实 10），下一片的活。
- **剖视/局部放大/爆炸图/装配图**不做；相切轮廓隐藏线只判出一侧的现状未动
  （`tests/test_cad_drawings2d.py::TestTangencyLimit` 仍钉着）。
- **公差声明与 Product Truth 未打通**：`--spec` 吃的是外部 JSON 文件，没有从权威事实里取
  零件规格；这一条写进了 registry 行内，不留作隐含债。
- 特征名带视图前缀（`TOP.hole_2`）是**本轮定的口径**：同一模型 FRONT 的 `overall_width`
  是 100、RIGHT 的是 10，不带前缀会把公差贴错尺寸。
- `releases/golden-projects/**` 的既有出图证据未重生成（属主动作，不自动盖章）。

## 六、复算

```bash
export PATH="$PWD/.venv/bin:$PATH"
python -m pytest tests/test_cad_drawings_chain_tolerance.py tests/test_cad_drawings2d.py -q
python scripts/capability_matrix.py --repo . --out docs/audit   # 只有 cad.2d_drawings 行变化
# 真实件端到端（空 --native 即走内置黄金件）：
python -m aipd_os.cli.main drawing generate --out /tmp/b.dxf --part golden_bracket \
  --views FRONT,TOP,RIGHT --spec /tmp/tol.json ; echo $?   # 声明落空时 4
# 清单/证据重锚（发布锚点仍钉 v5.6.0；--test-report 必须是 tag 锚定的那份）：
python scripts/regenerate_release_manifest.py
python scripts/release_evidence.py --repo . --out . --version 5.6.0 \
  --bundle releases/aipd-os-5.6.0.zip --test-report docs/audit/pytest-report-v5.6.0.json \
  --source-commit a66040520139405095648461f7144d4f00629924
python scripts/production_release_gate.py --release-ready --tag v5.6.0
```

## 七、收尾读数

- 全量回归：**1494 passed / 0 failed / 3 skipped**（重锚清单前为 1492 passed + 2 条
  manifest 判红，属预期，不是回归）；
- `ruff check src tests`（CI 口径）0；`mypy src tests` 0（**379** 文件）；
- `production_release_gate --release-ready --tag v5.6.0`：**8/8，release_ready=true**；
  其 `test_numbers_from_report` 读的是 tag 锚定那份报告
  （`passed=1096 failed=0 total=1099 source_commit=a660405…`），**与本轮树的 1494 不可互换引用**；
- `skill_quality_audit`：0 警告 / 0 失败；
- `state_perf_gate`：**PASS**（闲时，load 2.53；`fact_batched_ops_s` 22704 ops/s、
  `nested_txn_marginal_us` 18.67µs、批处理比 0.0489）；
- 清单：**577 文件**（+1 个新用例文件）。实测两份清单都**整体排除 `docs/audit/`**
  （该前缀条目数 0），所以审计文档与回归报告改多少次都不会牵动清单哈希；
  `SOURCE_MANIFEST.source_commit`
  仍钉 `a6604052`（v5.6.0 tag 提交），**未移 tag、未重建/重签 bundle**
  （`BUNDLE_MANIFEST.json` 重新生成后与磁盘逐字节相同，即 bundle 没被动过）、**未 push**；
- 提交：`70673c6`（CAD 功能）/ `2aa7c72`（清单重锚）/ `e880992`（证据回绑）。

### 本轮两处自伤（记在这里，免得下一个人以为是工具的错）

1. **证据绑错报告**：我第一次用 `--test-report docs/audit/pytest-report.json` 生成证据，
   把 `PROVENANCE.test_report` 绑到了本轮树的报告（`source_commit=70673c6`）；而门禁的
   freshness 判据在 `--tag v5.6.0` 下要求报告绑 **tag 指向的提交**（严格相等，无祖先豁免，
   见 `production_release_gate.py:454-472`），于是判 STALE 一项红。前几轮的口径是绑
   `pytest-report-v5.6.0.json`。已在 `e880992` 回绑；本轮 1494 的全量回归仍留在
   `docs/audit/pytest-report.json` 里当轮次记录，两份清单都排除它，因此回绑不再改清单哈希。
2. **heredoc 提交与 `&&` 链混写**：`git commit -F - <<MSG … MSG && … <<'PY' … PY` 让第一个
   heredoc 吞掉了后半段脚本，提交主题变成了那段 Python。树内容是对的
   （改前后 `HEAD^{tree}` 均为 `63aaef0…`），本地未 push，用 `--amend -F <消息文件>`
   只重写了主题。规矩：**提交消息先落成文件、单独一条命令**，不要把第二个 heredoc
   接在同一行链里。

