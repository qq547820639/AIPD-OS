# F-CLI-COV 第 39 片：命令覆盖率这把尺子两头都在错

日期：2026-09-26 归属：命令面一致性（`aipd` CLI）
状态：已闭（量具与常驻棘轮），遗留 17 条按登记在册（见 §六）

## 一、结论

「哪条命令被测过」这件事，此前由 `tests/test_command_coverage.py` 的一行子串匹配代理：
`cmd in blob`（blob = 全部 `tests/test_*.py` 拼成的字符串）。它比的不是"命令被走过"，
而是"这个名字在测试目录里出现过"。实测读数两头错，且两错互相抵掉后总数仍像合理：

| 读数 | 旧探针 | 本片判据（AST 读调用形态） |
| --- | --- | --- |
| 已注册 | 66 | 66（不变） |
| 「被测」 | 47 | **49 走过 argv 位**（另 4 只被别名走过、1 只被直接调处理函数走过、2 处理函数共用分不清 verb） |
| 「未测」 | 19 | **17 低于 cli 档**（其中 10 条零证据）。旧探针那 19 条里 15 条是假未测，同时另有 7 条零证据被它算成已测 —— 22 条判错，占 66 的三分之一 |

- **假未测 15 条**：`main(["drawing", "dfm", "--step", ...])` 里 `"drawing"` 与 `"dfm"`
  是两个相邻字符串常量，子串 `"drawing dfm"` 匹配不上；`eco` 四条走
  `main(["eco", *argv, ...])` 这种转发器（verb 由实参带入），旧探针完全看不见。
  受影响清单：`bom release`、`drawing assembly-step(s)`、`drawing dfm`、
  `eco affected/create/show/transition`、`issue list/resolve/show`、`readiness check`、
  `validation list/plan/show`。
- **假已测 7 条**（零证据）：`from ezdxf import recover` 顶了 `recover`、dict 键
  `"version"` 顶了 `version`、`test_new_commands_registered` 里那张名字清单
  （`["init", "intake", …, "cad preflight", "test", "package"]`，它断言的是
  `name in PLANNED_COMMANDS`，不是调用）顶了 `cad preflight`、
  `owner_dashboard` / `onboarding` / `def _reset()` 顶了 `dashboard` / `onboard` / `reset`、
  `ui` 撞在 `builtin`、`build` 这些词的中间。这 7 条一次 CLI 都没走过。
- **另 6 条判对但理由错**：`cad build` / `package` / `resume` / `test` 只有 deprecated
  别名走过 argv 位；`doctor` 只有 `cmd_doctor(...)` 直调；`outbox drain` 调的 `cmd_outbox`
  与 `outbox review` 共用。旧探针给它们盖的"已测"章理由是错的，所以本片把它们**分档记账**
  而不是简单判红。（本文件初稿把这两类合起来写成"假已测 13 条"，属过度断言，已更正为
  7 + 6，并按排除量具自身后的 blob 复算——第一次复算忘了排除，`operate`/`product gate`
  被新登记基线里的同名字符串污染成了"旧探针已测"，那是一次自引用假读数。）

同文件的声明面更静：`_declared_commands()` 从**含「一键命令」的那一行**开始往后收集
反引号命令名，遇到第一个不含反引号的行 break。而 SKILL.md 里那一行是标题
`## 0. 一键命令`（第 13 行），下一行是空行 ⇒ 第一次迭代就退出，**解析结果恒为 0**。
`0 ⊆ 注册` 恒真，于是两条「声明 ⊆ 注册」/「注册 ⊇ 声明」断言长期绿着，报告同时印出
「声明命令数：0 / 已注册但未声明：66」这种自相矛盾的读数（复算：修复前跑
`pytest tests/test_command_coverage.py -s` 即见）。
CI 侧的 `scripts/skill_quality_audit.py` 一直是按小节边界取段（找 `## 0.`、止于下一个
`## `），能真读出 56 条 —— 一份坏副本与一份好副本并存，而读者信的是常驻用例那份。

## 二、判据设计（五档，Σ 档位 == 分母是硬断言）

`scripts/command_surface_census.py`：

| 档 | 判据 | 为什么不是 `cli` |
| --- | --- | --- |
| `cli` | 列表/元组字面量首位是命令头（单 token 命令）或头+verb 相邻（双 token），或经转发器 `["eco", *argv, …]` 且实参带该 verb | — |
| `alias` | 只被 deprecated 别名走过 argv 位；别名↔真名由契约 `replacement` 现派生 | 用户能输入的公开名没走过 |
| `handler` | 只被直接调用 `cmd_*` 函数 | 到得了处理器，到不了 argparse 面（F-CLI-01 已证：解析器才是产品面） |
| `handler_ambiguous` | 调的是被多条命令共用的处理函数（`cmd_outbox` 同管 drain 与 review） | 分不清 verb ⇒ 不折算进任一侧 |
| `none` | 测试里一次都没真调过 | — |

三条反滥用前提，全部有常驻断言：空语料/解析失败 ⇒ 判「读数不可信」（rc=4），
不把"看不见"折成通过；量具自身与它的用例文件一律排除（写一条断言就会把自己算进分母）；
证据必须带 `文件:行号`，`--json` 落盘读数与内存读数同源。

## 三、候选方案对照（分析性，未做外部检索）

调研豁免与限度：本片是把一根已有的仓内探针换成另一根，不引新依赖、不改技术栈，
故未检索官方文档/GitHub 生态；下表是对**本机可跑的既有工具**按性质比较，
不是文献结论。

| 候选 | 功能匹配度 | License | 维护活跃度 | 安全风险 | 代码质量 | 适配成本 |
| --- | --- | --- | --- | --- | --- | --- |
| A 标准库 `ast` 读调用形态（**选它**） | 正好回答"源码里有没有 argv 位调用"，且能分档 | Python PSF | 语言内置 | 无新增面 | 与同仓 `ts_interface_shape.py` 同形 | 低（一个文件） |
| B `coverage.py`/`pytest-cov` 运行时轨迹 | 答的是"哪些行被执行"，与"命令面是否被走过"不同一层；`cmd_outbox` 一次执行两条命令都算过 ⇒ 歧义档反而丢失 | Apache-2.0 | 高 | 无 | 成熟 | 需全量单跑+产物排序，单跑一文件即假 0 |
| C 多模式正则（补两种写法） | 只能覆盖已知写法，转发器/别名/共用处理函数三档都表达不了 | MIT 级 | — | 判据不可证伪 | 旧病根 | 低但会再漂 |
| D tree-sitter AST | 与 A 同层，但给 Python 判据引入外部语法库 | MIT | 高 | 新依赖 | 好 | 中（无收益） |

选 A：分档需要区分"别名走过"与"真名走过"、"共用处理函数分不清"，这是**结构**判断，
运行时轨迹给不出（B 会把 `outbox drain`/`outbox review` 一并算成已测，恰好丢掉本片
最要紧的那条歧义）。

## 四、常驻侧接线

- `tests/test_command_surface_census.py`（9 条）：双向棘轮（新增缺口 ⇒ 红；
  登记里的命令补上真调用 ⇒ 也红，记录只减不增；档位漂移 ⇒ 红）、
  分母 66 与 Σ 档位、`files_read > 100` 与 cli 档 49 的非空转前提、
  空语料判"不可信"、`--self-test` 以子进程真 spawn、写盘 JSON 与内存读数一致、
  证据里不许出现量具自身、别名档必须能指回契约。
- `tests/test_command_coverage.py`（6 → 8 条）：删掉恒 0 的私有解析器，声明面改
  按契约双向核（`registered == PUBLIC ∪ DEPRECATED ∪ INTERNAL`）+
  与 `SKILL.md` 声明集合相等；新增 `test_skill_parser_can_fire`（正向读出
  `alpha`/`beta two`、反向：小节外的 `gamma` 不算、缺 `## 0.` 时为 0）——
  「解析器能不能匹配」这件事在过去六轮里一次都没被问过的，正是本片的根因。
- `scripts/skill_quality_audit.py`：真调探针改为共用 census 那一份（原来两处各写一份
  "同名子串即算测过"，读数会各自漂）；SKILL.md 解析抽出纯函数 `declared_from_skill`
  才可注入反证。CI 步骤不变（`ci.yml:230`），读数 **0 警告 / 0 失败、rc=0**，
  「测试文件覆盖」从 66-19=47 变成 **49**。

## 五、撤改电池（`/tmp/s39/battery.py`，7 条：杀 7 / 存活 0 / 注入无效 0 / 崩溃式红 0）

对照臂（未注入）rc=0 先立；每条注入后逐条还原并核 sha256 字节一致。

| 注入 | 半径（判红的用例） |
| --- | --- |
| A1 双 token 相邻判据摘掉 | `test_below_cli_set_matches_the_record_exactly`、`test_reading_is_not_vacuous`、`test_census_self_test_runs_and_is_green` |
| A2 单 token 命令丢掉 argv 位置要求 | `test_below_cli_set_matches_the_record_exactly`、`test_each_recorded_tier_is_the_measured_one`、`test_reading_is_not_vacuous` |
| A3 转发器不再登记 | 同 A1 三条 |
| A4 别名当成真名 CLI | 4 条（含档位漂移与自测） |
| A5 直接调处理函数当成走过 CLI | 4 条 |
| A6 空语料不再报「读数不可信」 | `test_empty_corpus_is_reported_as_unreadable` |
| A7 声明解析器退回只看标题下一行 | `test_declared_commands_are_registered`、`test_declared_set_equals_public_contract`、`test_skill_parser_can_fire` |

过程记录（防下次重踩）：A2 第一次写成「取列表里第一个字符串元素」，与未注入形态**等价**
⇒ 那是注入无效，不是判据弱；改成"逐元素记账"（丢掉位置要求）后才开火。
另外 `test_census_self_test_runs_and_is_green` 是子进程真跑 `--self-test`，
所以 A1/A3/A4/A5 四条也同时被量具自己的 10 条合成注入抓住——两把尺子各自独立。

## 六、登记在册的缺口（本片不修，只让它看得见）

`none`（10）：`cad preflight` `dashboard` `onboard` `operate` `product show`
`product gate` `recover` `reset` `ui` `version`。
`alias`-only（4）：`cad build`（只有 `run-cad-chain` 走过）、`package`（`build-release`）、
`resume`（`restore-project`）、`test`（`run-tests`）。
`handler`（1）：`doctor`。`handler_ambiguous`（2）：`outbox drain` / `outbox review`。

补法按棘轮只有一种：往 `tests/` 里加真 `main(["<命令>", …])` 调用，然后**删掉登记那一格**。
不许为把它绿掉而放宽判据或把新命令塞进基线。

## 七、全量与门禁读数（三跑，全部在 `git worktree` 的干净 HEAD 签出里）

| 跑 | 树 | collected | passed | failed | 说明 |
| --- | --- | --- | --- | --- | --- |
| A | `84b800c` + `a836810`（代码与镜像，清单未刷） | 2266 | 2261 | 2 | 只红在 `test_release_manifest_hashes_match_disk` 与 `test_source_manifest_hashes_match_disk`——新量具与改过的 README/CHANGELOG 还没进清单，属预期 |
| B | `677f60f`（清单已重锚） | 2266 | 2262 | 1 | 清单两条转绿；红的是 `test_state_perf_gates.py:146` 那条 **5× 比值门**：load 28 下实测批处理 311.9ms / 逐条 1334.1ms = 4.28×。隔离复跑 0.53s 绿 ⇒ 并发噪声，不放宽门、不改比值 |
| C | 同 B（`--json-report` 那份） | 2266 | **2263** | **0** | 报告里 `source_commit = a660405…`（v5.6.0 tag 提交），同一份既作本轮记录 `pytest-report.json`，也作锚定用的 `pytest-report-v5.6.0.json` |

- 全量用例数：上一片 2252 → 本片 **2263**（+11：`test_command_surface_census.py` 9 条、
  `test_command_coverage.py` 6→8 条）。
- `skill_quality_audit`：0 警告 / 0 失败，rc=0；「测试文件覆盖」从 47（子串）变成 49（argv 位）。
- 两道发布门禁（`production_release_gate --release-ready --tag v5.6.0` 与
  `audit_repo --strict`）必须在工作树干净时跑，所以它们的终读数写在**下一次提交**里
  （gate 自身会写 `docs/audit/repository_snapshot.json`，跑完再补一次提交是常态）。

## 八、复算入口

```
.venv/bin/python scripts/command_surface_census.py            # 读数（rc=0 可信）
.venv/bin/python scripts/command_surface_census.py --self-test # 10 条合成注入
.venv/bin/python -m pytest tests/test_command_surface_census.py tests/test_command_coverage.py \
    tests/test_skill_command_surface.py -q
export PATH="$PWD/.venv/bin:$PATH" && .venv/bin/python scripts/skill_quality_audit.py
```
