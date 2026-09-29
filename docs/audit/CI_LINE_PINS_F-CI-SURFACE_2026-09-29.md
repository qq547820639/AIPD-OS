# F-CI-SURFACE 第 98 片：行钉从"每命令一行"改成"每 (job, 行) 一处"

日期：2026-09-29。上一片收口提交：`8aa126e`。

## 一、这一片问什么

第 91 片立的账是"CI 每条门禁在本地收口链里有没有归宿"；第 94 片把 `line` 从恒 0 补成
`ci.yml:NNN`。但两格叠起来留下一处没对上的：**`job` 列与 `line` 列不同源**。
`ci_commands()` 按命令文本去重（同一条命令在 13 个 job 里跑只算一格账），
行号取的是**第一个命中它的 job** 的那一行（`scripts/ci_surface_census.py` 里
`setdefault(...)` 一次性写死），于是读的人看到 `job='audit,package-build,…'` 与
`line=208` 会以为"那一行跑的是这一串 job"。现读（本片改动前）：

```
CI 命令 32 条（17 个 job），消费表 32 条
python -m pip install --upgrade pip setuptools wheel  job_count 13  line 208
pip install -e ".[full,dev]"                          job_count  8  line 159
pip install -e ".[dev]"                               job_count  2  line 209
```

⇒ 三条命令共 23 处执行点，只有一个行号被钉住，其余 20 处的"这一行确实在跑这条命令"
从没被任何判据核过。

## 二、技术选型（四段）

### 候选清单

| 方案 | 出处（本轮真实打开） |
| --- | --- |
| A 引入 `zizmor` 作为另一把尺，消费它的输出 | PyPI JSON `https://pypi.org/pypi/zizmor/json` 现读：`zizmor 1.30.1`、`license MIT`、`summary "Static analysis for GitHub Actions"`、`Homepage/Documentation https://docs.zizmor.sh`、`Source Code https://github.com/zizmorcore/zizmor` |
| B 扩写本仓既有尺（PyYAML `compose` 的 `Mark` 锚 + 名册双向对账） | `scripts/ci_surface_census.py`（第 91/94 片立起，本仓 `ci.yml` 现读 32 条命令、17 个 job 都在它账上） |

**未亲验** `zizmor` 的规则集与输出 schema（只读了 PyPI 元数据与它的自述），
所以下面的对比不声称它"没有某条规则"，只按能核到的事实判。

### 六维对比

- **功能匹配度**：本面要的不是"workflow 写得安不安全"，而是
  "每条会被单独执行的 shell 命令 ↔ 本地收口链读不读它"，且行号要与 `(job, 行)` 同源。
  A 是 security findings 尺（其自述即 "static analysis for GitHub Actions"），
  这张账不在它的产出面上；B 的账就是这张。
- **License 兼容性**：A MIT，与发布链无冲突；B 本仓自研，无第三方。
- **维护活跃度**：A 版本 1.30.1 且有自己的文档站（活跃度可见，但我只读了元数据）；
  B 由本仓每片带着常驻用例与电池演进。
- **安全风险**：A 要在 CI/收口机上加一个可执行（Rust 发行包，非纯 Python），
  等于给认证链多一个供应链面；B 只用已在 `full` 档声明的 pyyaml。
- **代码质量**：未亲验（不因未读源码而打分）。
- **适配成本**：引 A 之后**仍然**要写"它的输出 ↔ 消费表"的对账尺 —— 那把对账尺本来就是 B；
  也就是说 A 只能加一层，不能省掉任何一层。

### 择一决定

**继续自研（B），不引入 A**：决定性判据是覆盖面 —— 本面的账只有 B 有，A 换不来这一格。
借了 A 的一点语义：把"位置"当一等问题处理（它的输出以 `文件:行` 报位，
本片的 `occurrences` 就是把这一维补进 `line`）。落地处即 §三。

### 落地处

`scripts/ci_surface_census.py`（记账 + 两条判决 + render）、
`tests/test_ci_surface_census.py`（12 → 15 条）、`docs/audit/s98/battery98.py`。

## 三、改了什么形状

1. `ci_commands()` 里每命令多一本 `occurrences: {job: [line, …]}` 与 `lines_total`；
   **定不到行号的 job 也要以空列表露头**，否则"穷举"这件事没有可核对的对象。
   同一 job 内不做 `set()` 去重：两次出现的行号天然不同，那个去重是够不到的防御。
2. 新纯函数 `line_pin_defects(cmds, file_lines)` 两条判决：
   - `CI面行钉不穷举`：某个 job 有命令却没有钉；
   - `CI面行钉指错行`：钉上的那一行原文不含这条命令的内容首行（= 锚法与解析面不同源）。
   写成**纯函数**（调用方递行表）而不是只挂在 `audit()` 里，是因为第二查在正常解析下
   天然自洽——不这么拆，就只能靠"写个坏 YAML 碰运气"，而那一格读不到就等于没牙
   （同形状见第 96 片"≥2 规则"那一臂）。
3. `--emit-register` 另存一列 `lines_per_job_at_emit_time`（emit 时刻的元数据，判据不读它，
   与 `cited_by_at_emit_time` 同档次，避免名册里出现第二份事实）。
4. `render()` 现读加一行：`行钉：跨 job 命令 N 条共 M 处（line 只给首处，穷举看 occurrences）；
   行钉缺陷 K 处`；`buckets` 多一档 `line-defect`（它是**位置轴**，不与消费档位求和比对）。

## 四、读数

- 改动前真语料：32 条命令 / 17 个 job / 3 条跨 job / 23 处执行点 / 只有 3 个钉。
- 改动后：`行钉：跨 job 命令 3 条共 23 处（`line` 只给首处，穷举看 `occurrences`）；行钉缺陷 0 处`，
  `归属：已接住 19 / 免跑有理由 13 / 无人守 0 / 被声明为可失败 0`，退 0。
- 常驻：`tests/test_ci_surface_census.py` 12 → **15 条**（`grep -c '^def test_'` 现读），
  `15 passed`；升级的是原有那条"每命令都有行号且那行确实含它"——现在逐 `(job, line)` 对账。
- 电池 `docs/audit/s98/battery98.py`：V0 对照绿 + 4 支撤销臂，**KILLED 4/4**
  （V1 被 2 条抓住、V2 被 2 条、V3/V4 各 1 条），收尾 sha 与开局相等。
- `ruff check` / `mypy` 对改动的测试文件各 0 错；`--self-test` 6 条合成读数照旧全对上
  （**第 98 片当时的读数**；第 99 片把两条行钉判决接进自测后涨到 8 条，见 §七）。
- 一处夹具教训（本轮真的付了一次空跑）：折叠标量 `>-` **只折一行**时锚仍然成功
  （值与文件行逐字包含），要用两行才造得出"定不到"；第一版夹具因此读不到 `run_mark_unmatched`。

未做到 / 未证实：

- `lines_total` 与"该命令在 CI 里真的被执行了几次"没做交叉验证——GH 的 matrix 展开
  （`strategy.matrix`）会让一个 job 名代表多次运行，本片按 **job 名**记账，不按 matrix 分支记账；
  这是有意的口径（消费表的键是命令，不是运行实例），但要写清：本片的"23 处"是 23 个
  `(job, 行)` 对，不等于 23 次 CI 运行。
- `zizmor` 的规则集与输出 schema 未亲验，§二 的对比只用能核到的元数据下结论。

## 五、认证读数（一代跑通）

- `PRECHECK OK: 2778 passed / 5 skipped / collected 2783 / 347.5s / fp ae82a8dce495`
- `MIN_TESTS=2783`（上一代下界 2780，由脚本从本轮报告现读后传入并硬断严格大于）
- `SKIP 面逐条相同：5 条`；`BIND_RC=0`；回读 `test_report=2778p/0f/2783t`、`fp=ae82a8dce495`
- 发布门 `GATE_RC=0`、`release_ready: True`、`未过: 无`、`项数: 8`
- 收尾验签 `CV_RC=0` 11 格全绿；回收签出后 `-b` 复算 `checks 11 red []`
- `roster_covers_tree`：树 224 文件 / 2688 个 `def` ↔ 报告 224 文件 / 2783 条，双向差集为空
- `pinned_source_binding`：「…且它是 **报告实测 HEAD** `b48cce83` 的祖先」
- `plaintiffs_measured`：2 条本轮原告（`tests/test_ci_surface_census.py`、
  `tests/test_forensic_scripts_parse.py`）都在名单里且 passed
- 被哈希文件数 `693 → 693`（本轮只改内容不改文件集：`scripts/ci_surface_census.py`），
  这个数字本身就是"有没有误纳文件"的探针
- 提交链（`git log --format="%h %s" 1a90a7c..HEAD` 现读，倒序）：`a644b2e` 验签读数 →
  `f5ba4fd` 门读数 → `0292d1c` 绑定 → `b48cce8` 重刷清单 → `1a90a7c` 本片实现
- 与上一片对照：这一次**一代就绿**（`GATE_RC=0`、`CV_RC=0` 都是第一跑），
  差别就在启动门之前把全部改动（含 `docs/audit/s98/` 两份日志）先入了库——
  第 91/96 片那两次"第一跑必红在 `workspace_clean`"不是必然，是工序顺序问题。

未做到：`.wt-s98b` 这个名字沿用了上一片的"第二代带 b"约定，但本轮其实只有一代 ⇒
名字与代次不符。不改（改 `WT=` 会让派生件与已提交脚本不一致），在此点名以免下一位读者
以为漏了一代；下一片的派生已按 `.wt-sNN` 起。

## 七、第 99 片：两条行钉判决接进 `--self-test`（上一片只上了常驻牙）

第 98 片的形状是"判据 + 常驻牙 + 电池"，`scripts/ci_surface_census.py --self-test` 那 6 条臂里
**没有一条碰行钉**——也就是说这把尺自己的合成电池看不见这一格，判据退化时只有常驻用例会展红。
本片补两条读数进去（6 → **8**）：

- **`CI面行钉不穷举` 走真 YAML**：两个 job 跑同一条命令，其中 `beta` 用 `run: >-` 把
  `pytest` 与 `-q` **分两行**写——折叠标量把两者折回 `pytest -q`，于是命令文本与 `alpha`
  那条完全相同（去重键撞上），而行号定不到。现读：`occurrences == {'alpha': [7], 'beta': []}`，
  `problems` 里同时有 `run_mark_unmatched`。这一支不只验判决，还验**接线**：
  `audit()` 真调 `line_pin_defects()`、`buckets["line-defect"]` 真进档。
  夹具形状的一处口径边界（第 98 片也踩过）：`>-` **只折一行**时锚仍成功——
  `run: >-\n  pytest -q` 现读 `occurrences = {'alpha': [7], 'beta': [12]}`、`problems` 为空。
- **`CI面行钉指错行` 按纯函数喂**：正常解析下行号与原文天然自洽，只能递假行表。
  两档各一火（行号越界、行号处原文不含命令），合规侧（行号与命令同源）不开火。
  越界那一档顺带是**防崩**的那道界：去掉 `ln > len(file_lines)` 守卫，读数以 IndexError 冒出来
  而不是以判决冒出来。

### 这一格是被自己的电池教出来的

常驻用例原先只写 `assert "条合成读数全部对上" in stdout`，本片先加的是 `marks >= 8`
（数 `✓立住` 的打印行数）。电池臂 **Y1** 把 `ci_surface_census.py` 里 `marks.append(text)`
改成 `pass` ⇒ **SURVIVED**：`_mark()` 的 `print` 是无条件的，8 行照印，而工具自报的那句
`--self-test：N 条…` 里的 `N = len(marks)` 掉到 0。两格分家在终端上读成"8 条全过"。
补成**两格同源**（`re` 抽自报数，断 `stated == marks`）后 Y1 被 `test_instrument_self_test_*`
抓住。取证面同格一并补（Y2，镜像臂），`tests/test_forensic_scripts_root.py` 的
`marks >= 18` 同样加了同源那一格。

**已知边界（不装作闭了）**：常驻层看得见"自测报了几条"与"逐条打了几行"是否相等，
**看不见自测内部单条断言的强度**——把 `buckets["line-defect"] >= 1` 放宽成 `>= 0`
在常驻层上不可观察。因此这类臂不收录（收了只会以 SURVIVED 出现而凑数）；
判决强度由 `tests/test_ci_surface_census.py` 那 15 条常驻用例守着。

### 现读与复算

```
python scripts/ci_surface_census.py --self-test        # --self-test：8 条合成读数全部对上，rc 0
python scripts/ci_surface_census.py --repo .           # 行钉：跨 job 命令 3 条共 23 处；行钉缺陷 0 处
python -B docs/audit/s99/battery99.py                  # X0 对照 + 7 支臂 KILLED 7/7，收尾 sha 逐文件相等
```
CI 面分母未变（32 条命令 / 17 个 job / 消费表 32 条），本片的改动全在判据侧的自测与常驻断言形状。
电池对 CI 靶只跑 `tests/test_ci_surface_census.py` 一个文件（15 条，约 6 秒），
不跑全量——这条臂要验的是"自测条数这格有没有人守"，不是 CI 判据的全部行为。
