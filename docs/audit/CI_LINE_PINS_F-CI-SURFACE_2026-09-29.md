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
- `ruff check` / `mypy` 对改动的测试文件各 0 错；`--self-test` 6 条合成读数照旧全对上。
- 一处夹具教训（本轮真的付了一次空跑）：折叠标量 `>-` **只折一行**时锚仍然成功
  （值与文件行逐字包含），要用两行才造得出"定不到"；第一版夹具因此读不到 `run_mark_unmatched`。

未做到 / 未证实：

- `lines_total` 与"该命令在 CI 里真的被执行了几次"没做交叉验证——GH 的 matrix 展开
  （`strategy.matrix`）会让一个 job 名代表多次运行，本片按 **job 名**记账，不按 matrix 分支记账；
  这是有意的口径（消费表的键是命令，不是运行实例），但要写清：本片的"23 处"是 23 个
  `(job, 行)` 对，不等于 23 次 CI 运行。
- `zizmor` 的规则集与输出 schema 未亲验，§二 的对比只用能核到的元数据下结论。
