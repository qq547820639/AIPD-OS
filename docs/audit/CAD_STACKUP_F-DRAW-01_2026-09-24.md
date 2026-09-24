# F-DRAW-01 第 2 片：一维公差叠加——把「图纸自相矛盾」变成机器判定

日期：2026-09-24　范围：新增 `src/aipd_os/cad/stackup.py`、`src/aipd_os/cad/drawings2d.py`
（逐视图把叠加结果写进证据）、`src/aipd_os/cli/commands_drawing.py`（矛盾判未收口 exit 4）、
能力行 `cad.2d_drawings` 行内改写、新增常驻用例 `tests/test_cad_stackup.py`（12 条）。

一句话结论：上一片画出了尺寸链、也标得出公差，但**没人检查这些公差能不能同时成立**；
这一片补上唯一有确定答案的那部分——各组成环公差带之和超过封闭环公差带时，图纸自相矛盾，
机器判红并把命令卡在未收口。

## 一、这一片刻意不做的两件事（避免编判据）

1. **不猜功能限值。** 仓库里不存在「封闭间隙必须 ≤ X」这类外部要求；给一个数就是编造判据。
   所以只判「声明之间是否互相矛盾」这一件可确定的事。
2. **不做三维/角度叠加，不做统计分布（Cpk）。** `rss` 只按各环公差带的平方和开根给出，
   它是**带宽容量的近似**，不是分布意义上的统计公差；这一点写进用例名与模块 docstring，
   不让下一个人当成 6σ 用。

## 二、口径（全部闭式、可手算复核）

- 每环公差带 `band = upper - lower`（非负；`{"upper":0,"lower":0}` 是**声明**「不许偏」，
  与「没声明」严格区分——这正是 `band_of(None)` 返回 `None` 而不是 `0.0` 的原因）；
- 最坏值 `worst_case = Σ band_i`；统计近似 `rss = √(Σ band_i²)`；
- 判据：`worst_case > 封闭环 band` ⇒ `inconsistent`（并给出超出量 `excess`），
  否则 `consistent`（给出 `margin`）；
- fail-closed 的三种「不可判定」：链不存在 `no_chain`；任何一环缺声明 `insufficient_data`
  并逐环点名；封闭环缺声明 `no_closing_tolerance`（**不假设总宽是精确值**）。
  三种都不是通过。

手算对照（也是用例里的数）：5 段各 ±0.05 ⇒ 每段带 0.1、`worst=0.5`；封闭环 ±0.2 ⇒ 带 0.4
⇒ 0.5 > 0.4 判矛盾、超出 0.1；封闭环放宽到 ±0.5 ⇒ 带 1.0 ⇒ 一致、余量 0.5；
非对称 ±(0.10/−0.02) ⇒ 每段带 0.12、`worst=0.6`、`rss=√(5×0.12²)`。

## 三、候选方案与选型（六维）

已读源码的唯一上游候选：**GitHub `Avaneesh-19337/tolerance-stackup-cli`**
（MIT、1 star、单文件零依赖，2026-07 建）。读 `stackup.py` 的实测结论：

```
nominal_gap = sum(d["nominal"] * d["dir"] for d in dims)
wc_tol      = sum(d["tol"] for d in dims)
rss_tol     = math.sqrt(sum(d["tol"] ** 2 for d in dims))
```

其解析器把 tol 包在 `abs()` 里 ⇒ **不支持非对称偏差**；且**不计算封闭环**（要人把封闭环
当一行手动列进 CSV）。本仓的声明本来就允许非对称（`{"upper": 0.1, "lower": -0.02}`），
而「封闭环对照」正是这一片的判据本体 ⇒ 两条都用不上。

| 维度 | A 自实现判据 + 借公式形状（选定） | B 直接用 tolerance-stackup-cli | C 只出链不做叠加判定 |
|---|---|---|---|
| 功能匹配度 | 高：非对称带、封闭环对照、缺声明 fail-closed | 低：对称带假设，封闭环要人填 | 不做判定，缺口留在原处 |
| License 兼容 | 无新增依赖 | MIT（许可无障碍） | —— |
| 维护活跃度 | 与产品同生命周期，判据有常驻用例 | 1 star、单次 push（2026-07-12），样本量不足 | —— |
| 安全风险 | 纯函数、无 IO 无网络 | 引入外部代码即自建供应链信任 | 无 |
| 代码质量 | 103 行闭式纯函数、7 条变异全部打破 | 已读到的部分实现干净，但 `abs()` 是功能缺陷 | 无 |
| 适配成本 | 低（判据必须与我们的证据结构同形） | 要把链导出 CSV 再喂回来，仍得自己补非对称与封闭环 | 低但不解决问题 |

**选定 A**：借它的公式形状（`Σband` / `√Σband²`，也是教科书写法），判据自己实现。
另两侧检索（WebSearch）命中的是商业软件（DTAS3D、Guthrie QA-CAD）与 SaaS 软文，无可复用实现；
`steputils` 已在前片核实只做 ISO 配合查表。**未读** in-toto / CycloneDX 规范源码，不评价。

## 四、落点

| 位置 | 作用 |
|---|---|
| `src/aipd_os/cad/stackup.py:27` | `band_of`：`upper-lower`；`None` ≠ 0；上下界颠倒直接 `ValueError` |
| `:45` | `view_stackup`：链/封闭环/缺声明三态判定，附 `formula` 字段自述算法 |
| `src/aipd_os/cad/drawings2d.py:553` | `write_dxf` 逐视图算叠加，证据新增 `stackup_check` / `stackup_inconsistent` / `stackup_undecidable` |
| `src/aipd_os/cli/commands_drawing.py:123` | prose 打印一致/矛盾/不可判定三态；矛盾 ⇒ 未收口 exit 4 |
| `src/aipd_os/registry_data.py` | `cad.2d_drawings` 行内：叠加做到哪一步、没做什么逐项写明 |

## 五、用例与变异对照

12 条：闭式算术 5、fail-closed 语义 3、证据集成 2、CLI 判住 2。
CLI 两条用 `cmd_drawing` 真跑（默认黄金件 TOP 视图恰好是 5 段 20/20/20/20/20），
断言退出码与打印，不只断 payload。

变异 7 条，全部打破：

| 变异 | 打破 |
|---|---|
| M1 缺声明按 0 折算 | `one_undeclared_link_kills_the_arithmetic_and_is_named` |
| M2 带取 `abs(upper)`（上游的形状） | 7 条（含非对称与全部判定） |
| M3 判定方向反 | 5 条（含 CLI 两条） |
| M4 封闭环缺声明当精确值 | `missing_closing_tolerance_is_not_treated_as_exact` |
| M5 rss 写成线性求和 | `rss_is_the_root_sum_of_squares_and_smaller`、非对称条 |
| M6 CLI 无视矛盾 | `contradictory_declarations_hold_the_command` |
| M7 段名义长当成公差带 | 缺声明条（缺声明不再被点名） |

自我更正一处：接线时我先把 `_emit` 写成了 `_emit(...) if False else None`（照例会**永远不输出**），
在跑用例前自查发现并改回；教训与上一轮同类——不要在记账脚本/补丁里塞条件表达式凑数。

## 六、边界

- 叠加只覆盖**一条水平链 vs 总体宽**这一种环组合；竖直方向、多环系、角度、
  分布型统计公差都未做（也未被声称）；
- 不参与 `release manifest` 的 CTQ 判据（那边核的是单特征声明与 CTQ 限值一致，
  不是链级叠加），两边不互相冒充；
- `releases/golden-projects/**` 既有产物未重生成；未 push、未动 tag、未重签 bundle。

## 七、真机端到端读数

内置黄金件（`model_source=golden_default`，TOP 视图 4 个 Ø8 孔）配
「5 段各 ±0.05 + 总宽 ±0.2」的声明：链实测 `[20.0, 20.0, 20.0, 20.0, 20.0]`、
`chain_check.delta=0.0`、叠加 `worst_case=0.5` / `closing_band=0.4` /
`verdict=inconsistent` / `excess=0.1`，`stackup_inconsistent=true`，
**`cmd_drawing` 返回 4**。放宽封闭环到 ±0.5 的同一份用例判 `consistent`、`rc=0`。

## 八、复算

```bash
export PATH="$PWD/.venv/bin:$PATH"
python -m pytest tests/test_cad_stackup.py -q
# 真机：让 5 段各 ±0.05、总宽 ±0.2，命令应判 4
python -m aipd_os.cli.main drawing generate --out /tmp/s.dxf --part bracket \
  --views TOP --spec /tmp/contradiction.json ; echo $?
```
