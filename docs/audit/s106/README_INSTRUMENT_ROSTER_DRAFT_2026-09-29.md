# 第 106 片起草：README「复算入口」量具名册 + 分母配方

只读研究产物。本轮**未执行**任何量具、未跑 pytest/ruff/mypy、未动 git 写操作；
所有结论来自 Read/grep 的逐字读数，每条带 `file:line`。
落点：README.md 的 ```bash 栅栏（开 `README.md:180`、闭 `README.md:817`）之内。

## 一、名册（10 行：`scripts/` 下带 `--self-test` 的全部量具）

「自测旗标」列一律是 argparse 声明原文，旗标拼法都是 `--self-test`（dest 由 argparse
自动折成 `self_test`，各文件 `if args.self_test:` 那行即消费点）。「在 README 里吗」分三档：
**块**＝栅栏内有它自己的命令行；**自测行**＝另有 `<该脚本> --self-test` 那一行；**散文**＝只在
注释/正文里被提到。

| 量具 | 判什么（docstring 首行） | 自测旗标 | 在 README 里吗 |
| --- | --- | --- | --- |
| `scripts/absence_claim_census.py` | 登记表里「某样东西还没有」这类否定句必须配一个能证伪的锚点（F-STALE-ABSENCE 第 65 片）`scripts/absence_claim_census.py:1` | `add_argument("--self-test", action="store_true")` `scripts/absence_claim_census.py:1372`，消费 `:1374` | 块 `README.md:705`；无自测行 |
| `scripts/c6_coverage.py` | C6 生产图纸包交付物覆盖度普查（诊断档，不进发布门禁）`scripts/c6_coverage.py:2` | 同上形状 `scripts/c6_coverage.py:413`（带 help），消费 `:416` | 块 `README.md:461`（行尾挂内联注释）；**无自测行**，且它的 `#   ↑` 散文被插到别台之后 `README.md:473-480` |
| `scripts/changelog_commit_crosscheck.py` | CHANGELOG 条目 ↔ 提交历史：这一片的账落没落地（F-CHANGELOG-ENTRY-CROSSCHECK 第 104 片）`scripts/changelog_commit_crosscheck.py:2` | `add_argument("--self-test", action="store_true", help="跑合成语料")` `scripts/changelog_commit_crosscheck.py:300`，消费 `:303` | **完全没有**（README 零命中） |
| `scripts/ci_surface_census.py` | CI 上跑的门禁，本地收口链到底消费不消费？逐条对账（F-CI-SURFACE 第 91 片）`scripts/ci_surface_census.py:2` | `add_argument("--self-test", action="store_true")` `scripts/ci_surface_census.py:587`，消费 `:591` | 块 `README.md:564` + **自测行 `README.md:578`** |
| `scripts/closeout_verifier.py` | 收尾验签：把「这份报告测的确实是这棵树」做成常驻判据（F-CLOSEOUT-VERIFY 第 64 片）`scripts/closeout_verifier.py:2` | `add_argument("--self-test", action="store_true")` `scripts/closeout_verifier.py:802`，消费 `:805` | 块两处 `README.md:481`、`README.md:629`；自测只在散文里提 `README.md:493`，**无自测行** |
| `scripts/command_surface_census.py` | CLI 命令面「有没有被常驻用例真调过」普查（F-CLI-COV 第 39 片）`scripts/command_surface_census.py:2` | `add_argument("--self-test", action="store_true", help="注入反证：每条判据都必须能红/该不开的都不开")` `scripts/command_surface_census.py:431-432`，消费 `:436` | 只有散文 `README.md:908`（在「附：常用命令速查」节，`README.md:889` 起）——**栅栏内无命令行** |
| `scripts/dependency_license_gate.py` | 依赖许可证门禁：把「这个依赖的许可证我们能不能用」变成会红的判据（F-DEP-LICENSE 第 92 片）`scripts/dependency_license_gate.py:2` | `add_argument("--self-test", action="store_true")` `scripts/dependency_license_gate.py:953`，消费 `:955` | 块 `README.md:605`；无自测行 |
| `scripts/doc_command_census.py` | 文档/登记表点名的 `aipd` 命令必须真的注册着（F-DOC-CMD 第 60 片）`scripts/doc_command_census.py:1` | `add_argument("--self-test", action="store_true")` `scripts/doc_command_census.py:1606`，消费 `:1611` | 块 `README.md:520`；无自测行 |
| `scripts/doc_reference_census.py` | 文档里的代码引用 ↔ 代码事实：一条 `path[:line]` 还指得回东西吗（F-DOC-REF 第 41 片）`scripts/doc_reference_census.py:2` | `add_argument("--self-test", action="store_true")` `scripts/doc_reference_census.py:562`，消费 `:564` | **完全没有**（README 零命中） |
| `scripts/scripts_lint_ratchet.py` | `scripts/` 的 lint 面棘轮（F-SCRIPT-LINT 第 100 片）`scripts/scripts_lint_ratchet.py:1` | `add_argument("--self-test", action="store_true")` `scripts/scripts_lint_ratchet.py:369`，消费 `:372` | 块 `README.md:675` + **自测行 `README.md:695`** |

补一条**不在 `scripts/` 却已在 README 占了自测行**的量具，名册按目录口径收它时须显式表态：
`docs/audit/s96/build_forensic_root_register.py`（`README.md:641` 现算 + `README.md:665` 自测行）。
它的旗标**不是 argparse 声明**，而是手写 argv 成员判断 `docs/audit/s96/build_forensic_root_register.py:515`
`if "--self-test" in argv:`（全文没有一个 `add_argument`）。

## 二、起草的 README 块（照抄既有形状）

形状取自现读：命令行**不带 venv 前缀、不带 `python3`**，形如 `python scripts/<name>.py`
（`README.md:605`、`README.md:629`、`README.md:675`）；紧接散文首行 `#   ↑ `（井号 + 3 空格 + ↑ + 空格），
续行 `#     `（井号 + 5 空格）；自测那一档单独成一行 `<path> --self-test`，其散文首句固定写
「上一行那把尺的……」（`README.md:578-579`、`README.md:665-666`、`README.md:695-696`）。
**绝对数一律不抄进正文**，这条是本栅栏自己立的规矩（`README.md:572`「分母由工具自报…别抄进正文」、
`README.md:696`「条数只认它自己那行自报，本文不抄」）。
建议落点：`README.md:733` 之后、`README.md:734`（`aipd truth propagate …`）之前，仍在同一栅栏内。

### 2.1 `scripts/doc_reference_census.py`（整块缺席，补两块）

```
python scripts/doc_reference_census.py
#   ↑ 文档代码引用普查（第 41 片，F-DOC-REF）。抓的是「写着像出处、代码侧根本没有」：
#     一条 `path[:line]` 必须解析得到，给了行号还必须落在那份文件的行数内；
#     六档恰好落一类 external / cli-operand / elided / shorthand / multi / repo，
#     第一版就是因为把 CLI 操作数、第三方内部路径、省略写法全算成缺陷而造出 514 条假数。
#     判与不判分两档面：现状面（README/SKILL/docs 非 audit）判红，历史面（CHANGELOG 与
#     docs/audit，逐轮记当时事实）只出错数不改写。第 103 片加了符号锚 `路径::符号`——
#     裸行号只在写下那一刻对，文件一长行号仍 ≤ 总行数，`line_beyond_eof` 永远不开火
#     （第 102 片实测：`docs/audit/v5.4/` 钉的 `manual_chain.py` 三个行号漂了约 47 行，四轮门禁全绿）。
#     退码 0 现状面干净 / 4 有缺陷或语料读不到、Σ 对不上（读数不可信）。
#     分母与档位由 `--json` 自报，本文不抄。取证与选型见
#     docs/audit/DOC_REFERENCE_CENSUS_F-DOC-REF_2026-09-26.md。
python scripts/doc_reference_census.py --self-test
#   ↑ 上一行那把尺的合成读数臂（条数只认它自己那行自报）。判据不在自己手里，
#     两极就直接喂给 `--self-test`：不平衡字典必须红、平衡字典必须绿，
#     外加扩展名切词的三个已知假阳性形状各配一支「加了这条护栏就不开火」的反例。
```

出处核对：六档 `scripts/doc_reference_census.py:13-20`；两档面 `:22-24`；退码 `:25`；
符号锚与其来由 `:55-59`；两极由 `--self-test` 直接喂 `:325`；自测落点 `:429`、`:562`、`:564`、自报行 `:554`。

### 2.2 `scripts/changelog_commit_crosscheck.py`（整块缺席，补两块）

```
python scripts/changelog_commit_crosscheck.py
#   ↑ CHANGELOG ↔ 提交历史对账（第 104 片，F-CHANGELOG-ENTRY-CROSSCHECK）。
#     抓的是「整条条目缺席」：`tests/test_changelog_integrity.py` 那两把尺都是自洽型的，
#     条目少一条时记号数与口径数一起往下走、两边照样相等 ⇒ 门永绿；2026-09-29 一天撞两次
#     （第 102 片标题被吃、第 103 片 v5.64 整条从没写进去），两次四道文档门全绿，
#     最后靠 `git show --stat` 读出一笔 feat 提交对 CHANGELOG 只有 1 行增才现形。
#     判据不看文档自己，看另一张独立名册——提交主题行里的 `s<NN>`：凡主题出现过的片号，
#     CHANGELOG 必须有一行 `- **v…` 条目带着 `第 <NN> 片`。方向只有这一边，
#     条目侧多出来的片号一律不算原告（那是 `sNN` 约定之前的轮次，反向判据会全数误伤）。
#     另两档：`caliber-diverge`（宽松口径与严格口径在提交侧片号上读数不一致 ⇒ 判红并点名）、
#     一行点名 ≥2 片的回指写法**只报不判**（真语料实测 6 行这么写，判红等于禁一种合法记账写法）。
#     三态：git 读不到 / 提交侧一个片号都没读到 / CHANGELOG 读不到 ⇒ 前提塌退 2，
#     绝不折成「0 缺席 = 干净」。退码 0 干净 / 4 有缺陷 / 2 前提不成立。
#     分母由脚本自报，本文不抄。取证见 docs/audit/s104/CHANGELOG_COMMIT_CROSSCHECK_DESIGN_2026-09-29.md。
python scripts/changelog_commit_crosscheck.py --self-test
#   ↑ 上一行那把尺的合成语料臂（跑临时仓库里的合成提交主题，条数只认它自己那行自报）。
#     每道判决配开火与合规两极，含「前提塌」那一档——三态不许把看不见折算成任何一种判决。
```

出处核对：自洽型尺看不见缺席 `scripts/changelog_commit_crosscheck.py:4-9`；正向判据 `:13`；
反向不算与 102/52 `:14-15`；`caliber-diverge` `:16-18`；≥2 片只报与「取全部而非首枚」`:19-22`；
三态与退码 `:24-26`；片号正则的两条边界 `:41-45`；自测落点 `:239`、`:300`、`:303`。
**注意**：它的取证文档不在 `docs/audit/*F-*.md` 这一命名形状里（见第四节第 4 条）。

### 2.3 `scripts/command_surface_census.py`（栅栏内只有散文，补两块）

```
python scripts/command_surface_census.py
#   ↑ CLI 命令面真调普查（第 39 片，F-CLI-COV）。它只回答一句：
#     这条命令的 CLI 入口（argv → argparse → 分发）在常驻测试里被走过没有？
#     判据用 AST 读调用形态，不用子串——旧的 `tests/test_command_coverage.py` 把 tests/ 拼成
#     一个大串再 `cmd in blob`，两头都错：假未测 15 条（相邻两个字符串常量、`main(["eco", *argv])`
#     这种转发器看不见），假已测 7 条（`from ezdxf import recover` 顶了 `recover`、
#     dict 键顶了 `version`、两字符名 `ui` 撞在别的词中间）。
#     五档恰好落一档，Σ 档位 == 分母是硬断言：cli / alias（只被 deprecated 别名走过）/
#     handler（只直调处理函数，到不了 argparse 面）/ handler_ambiguous（处理函数被多命令共用，
#     直调分不清 verb）/ none。别名↔真名由 CLI 契约的 `replacement` 派生，不手抄。
#     读数与分母一律 `--json` 自报，本文不抄。取证见
#     docs/audit/COMMAND_SURFACE_CENSUS_F-CLI-COV_2026-09-26.md 与
#     docs/audit/COMMAND_SURFACE_CLOSURE_F-CLI-COV_2026-09-26.md。
#     这一面在「附：常用命令速查」已有一段散文描述（`README.md:908`），两块不许互相抄数——
#     那一段的数由同一把尺现读。
python scripts/command_surface_census.py --self-test
#   ↑ 上一行那把尺的注入读数臂（条数只认它自己那行自报）。每条判据都配两极：
#     该红的注入必须红、该不开的合规形状必须不开火，「该不开的都不开」这一半
#     正是旧子串判据造出 7 条假已测的地方。
```

出处核对：只回答那一句 `scripts/command_surface_census.py:4-5`；两头都错的逐条来由 `:7-23`；
五档与 Σ==分母 `:25-35`；`replacement` 派生 `:29-30`；第 40 片闭合面由账与 argv 证据钉住 `:37-39`；
自测落点 `:324`、`:431-432`、`:436`、自报行 `:423`。

### 2.4 `scripts/c6_coverage.py`（不是补块，是**修形**：散文错挂 + 缺自测行）

现状：命令行在 `README.md:461`（行尾挂内联注释），它的 `#   ↑` 散文却在 `README.md:473-480`，
中间隔着 `scripts/research/fetch_fulltexts.py` 的命令行（`README.md:462`）与它那一段散文
（`README.md:463-472`）——按相邻配对读，473-480 会被读成 fetch_fulltexts 的尾巴。
改法：把 473-480 整体上移贴到 461 之后，并按既有形状去掉行尾内联注释、在块尾补自测行。

```
python scripts/c6_coverage.py
#   ↑ C6 交付物覆盖度普查（诊断档，刻意**没接进** `production_release_gate`）。
python scripts/c6_coverage.py --self-test
#   ↑ 上一行那把尺的注入反证臂（条数只认它自己那行自报）：注入四种坏读数并要求每一条都红——
#     判据不在自己手里时，先证明尺子能红再信它的绿。退码 0 一致 / 4 判未收口（口径漂移、映射自相矛盾）。
#     分母逐字取自 references/production-cad-deliverables.md 那一行（改契约不改映射会当场红）；
#     三档读数：有生产者且有常驻用例 / 只有校验方 / 零实现。取证见
#     docs/audit/C6_COVERAGE_CENSUS_F-C6-01_2026-09-25.md。
```

出处核对：诊断档不进门禁 `scripts/c6_coverage.py:2`；分母来源 `:4-6`、`:30-31`；三档 `:8-15`；
四种坏读数与「先证明能红」`:17`；退码 `:18`；自测落点 `:365`、`:413`、`:416`、自报行 `:405`；
「刻意没接进发布门」`README.md:480`。

### 2.5 附录：另外 5 台有命令行、没有自测行的（各补一行 + 一段散文首句）

按「带 `--self-test` 的量具必须在 README 有自测行」这条判据，今天缺的不是 3 行而是 8 行
（10 台里只有 `README.md:578`、`README.md:695` 两行）。已在本表内、只需补行的：
`python scripts/absence_claim_census.py --self-test`（`scripts/absence_claim_census.py:1372`）、
`python scripts/closeout_verifier.py --self-test`（`scripts/closeout_verifier.py:802`；
注意它现有的散文已用一整段讲 `--self-test` 的 22 臂 `README.md:493-499`，补行时把那段接上、别另起一份数）、
`python scripts/dependency_license_gate.py --self-test`（`scripts/dependency_license_gate.py:953`）、
`python scripts/doc_command_census.py --self-test`（`scripts/doc_command_census.py:1606`）、
`python scripts/c6_coverage.py --self-test`（`scripts/c6_coverage.py:413`，见 2.4）。
剩下 3 行由 2.1–2.3 三块自带。

## 三、守卫的分母配方与隐患

### 3.1 配方（分母 + 分子分开取，两侧都锚形状、不靠人记）

```sh
# 分母：仓内哪些脚本自测（递归，含 scripts/research/）
grep -rl --include='*.py' -e '--self-test' scripts | LC_ALL=C sort     # 现读 10 条
# 分子：README 栅栏内被写成可复算命令的量具行（行首锚定 + 词边界，排除散文提及；
# 必须允许操作数与行尾内联注释，理由见 H8）
grep -oE '^python (scripts|docs/audit)/[A-Za-z0-9_/.-]+\.py\b' README.md | LC_ALL=C sort -u
# 自测行分子：只取带 --self-test 的那几行
grep -E '^python .*--self-test$' README.md
```

两个写法坑（本轮实测）：`--` 之后的 `--include='*.py'` 会变成**位置参数**而不是选项，
于是过滤条件静默失效（BSD grep 另吐一行 `--include=*.py: No such file or directory`，
读数却仍是 10，看不出坏）——选项一律排在 `--` 之前，模式用 `-e` 起头；
分子用词边界 `\b` 而不是 `$` 收尾，见 H8。

分子必须按**行首命令行**取而不是 basename 子串取，理由见 3.2 的 H4/H5；
必须收词边界后的整行前缀而不是要求行尾，理由见 H8。
判据形状照抄第 104 片那条纪律：只单向判「分母里有、分子里没有」⇒ 判红；分子多出来的一律不算原告
（`scripts/changelog_commit_crosscheck.py:14-15`），只报数——s105 的验收项里也是这么写的
（`docs/audit/s105/NEXT_SLICE_CANDIDATES_2026-09-29.md:49`）。
三态：README 读不到、或分母一个都不匹配 ⇒ 前提塌退 2，不折成「0 缺失 = 齐备」
（同 `scripts/changelog_commit_crosscheck.py:24-26`）。
开火控制（禁手写名册，s105 项 ② `docs/audit/s105/NEXT_SLICE_CANDIDATES_2026-09-29.md:48`）：
在临时根里造一台带 `--self-test` 的脚本 + 一份不含它的 README，断言它**立刻**进原告清单。

### 3.2 会让它静默错的四件事（每条按本轮实读代码定 live/not-live）

| # | 隐患 | 今天是否成立 | 一手出处 |
| --- | --- | --- | --- |
| H1 | 自测不是旗标而是**子命令**：`scripts/cad_convergence.py` 的自测是 `selftest` 子命令，`--self-test` 这条文本 grep 与 argparse 声明 grep 两档都看不见它 | **LIVE**（今天就少一台） | `scripts/cad_convergence.py:213`（`selftest()`）、`:263`（`sub.add_parser("selftest")`）、`:269-270`（分发） |
| H2 | 自测旗标**不经 argparse**，是手写 argv 成员判断：文本 grep 命中、AST/argparse 档漏；且它不住在 `scripts/` 而在 `docs/audit/`，按目录口径收分母时它整台消失，而 `README.md:665` 已经给它写了自测行 ⇒ 分母与分子作用域不一致 | **LIVE**（两问各中一条） | `docs/audit/s96/build_forensic_root_register.py:515`（`if "--self-test" in argv:`，全文无 `add_argument`）、`README.md:641`、`README.md:665` |
| H3 | 浅 glob `scripts/*.py` 看不见 `scripts/research/`；反过来 `scripts/research/selftest_*.py` 两支是「整支脚本即自测、根本没有旗标」的形状，任何按旗标取分母的配方都永久看不见它们 | 分母侧 **NOT LIVE**（本轮递归 grep：10 台带 `--self-test` 的全在 `scripts/` 顶层，`scripts/research/` 下零命中）；名册语义侧 **LIVE**（两支自测脚本不在任何名册里） | `scripts/research/selftest_postprocess.py:2-4`、`scripts/research/selftest_runtime.py:2-4`。顺带：这两个 docstring 的 `Run:` 行写的都是 `python3 scripts/selftest_*.py`，真身在 `scripts/research/` 下 ⇒ 现成的错路径，正是 `doc_reference_census` 那一面的原告 |
| H4 | README 侧按 **basename 子串**算「出现过」⇒ 散文提及被读成已立块，假绿 5 处 | **LIVE** | 散文-only：`README.md:364`（`scripts/quality_gate.py`）、`:379`（`e2e_acceptance.py`）、`:686`（`aipd_supervisor.py`）、`:892`+`:906`（`skill_quality_audit.py`）、`:908`（`command_surface_census.py`，栅栏内确实无命令行） |
| H5 | 占位模板 `scripts/X.py` 被当成一台量具计入读数 | **LIVE** | `README.md:521`、`README.md:554`（两处都在讲判据自己的写法，不是路径） |
| H6 | 用「命令行 + 紧邻的 `#   ↑`」配对来判块是否配套，会被散文错挂骗过：一台的命令行与它自己的散文之间夹着别台的整块，配对仍「各命中一次」 | **LIVE**（c6_coverage 就是现证） | `README.md:461`（命令行）↔ `README.md:473-480`（它的散文，中间隔着 `README.md:462-472`） |
| H7 | 新写的行会不会被自家门禁咬：`doc_command_census` 面 ④ 判「行首 `python scripts/X.py …` 的脚本必须存在、行内旗子必须在该脚本 argparse 声明里」 | **NOT LIVE**（本稿 8 行旗子全部是 `--self-test`，逐行见名册第三列的 `add_argument` 出处；脚本全部在盘上） | `README.md:521-523`（面 ④ 措辞）、`scripts/doc_command_census.py:40-44`（实现与「旗子集合静态不封闭则不判」那条例外） |
| H8 | 分子正则把「命令行」锚成**整行形状**（如 `^python scripts/X\.py( --[a-z-]+)*$`）就静默少收两台：带操作数的那行、行尾挂内联注释的那行 | **LIVE**（本轮实测：该形状现读 11 行＝8 个去重基名 + 3 条自测行，且丢 `README.md:461` 与 `README.md:481`；换词边界形状 `grep -oE '^python (scripts\|docs/audit)/[A-Za-z0-9_/.-]+\.py\b' README.md \| sort -u` 现读 10 条，含这两行） | `README.md:461`（`python scripts/c6_coverage.py          # C6 那 15 项…`）、`README.md:481`（`… closeout_verifier.py --tag v5.6.0 --expect-test tests/test_new_thing.py`） |

补一条给守卫自己：**别把「10」写进任何文档**。s105 的原文就是把 10 与 11 抄进正文，
于是同一件事在两处各漂一次（`docs/audit/s105/NEXT_SLICE_CANDIDATES_2026-09-29.md:38-41`）；
本仓既有规矩也是这条（`README.md:572`、`README.md:696`）。

## 四、我与你给的前提不一致的地方

1. **差集是 2 不是 3**（按你写的「README 里一个字都没出现」这条字面判据）。
   `scripts/c6_coverage.py` **在 README 里**：`README.md:461` 就是它的命令行，
   且这行在 HEAD 的 README 里同样存在（`git show HEAD:README.md | grep -n c6_coverage` → `461:python scripts/c6_coverage.py          # C6 那 15 项交付物各自做到哪一步了（诊断档）`）；
   `git status --short README.md` 空，不是本地未提交改动造成的。真正零命中的只有 2 台：
   `scripts/doc_reference_census.py`、`scripts/changelog_commit_crosscheck.py`。
2. **按「栅栏内有没有它自己的复算块」判，缺的是另外一组 3 台**：
   `scripts/command_surface_census.py`（只在 `README.md:908` 的散文里出现）、
   `scripts/doc_reference_census.py`、`scripts/changelog_commit_crosscheck.py`。
   也就是说你点名的 3 台里有 1 台（c6_coverage）判据口径不同才成立，同时漏了 1 台（command_surface_census）。
   本稿第二节因此按这个口径起草，并把 c6_coverage 归到「修形」而非「补缺」。
3. **「README 提到 11 条 `scripts/*.py`」这个数我用能复现的任何配方都没得到**。
   `grep -oE 'scripts/[A-Za-z0-9_/.-]*\.py' README.md | sort | uniq -c` 现读：12 条真实顶层脚本 +
   `scripts/research/fetch_fulltexts.py` + 占位 `scripts/X.py`（2 次）。少的那一格大概率就是没剔占位、
   或多算了一条（H5）。这一条不影响判据，只影响任何抄这个数的文档。
4. **`--self-test` 行只有 2 行，不是 9 行的缺口被低估了**：README 现读带 `--self-test` 的命令行 3 条
   （`README.md:578`、`README.md:665`、`README.md:695`），其中 `README.md:665` 那台不在 `scripts/`
   （H2）。若守卫按「带自测的量具必须有自测行」判，今天一次就报 8 台（见 2.5），不只是 3 台。
   落笔前得先拍这条判据的强度：只要求「有块」还是要求「有块且带自测行」。
5. **`changelog_commit_crosscheck` 的取证文档不是 `docs/audit/*F-*.md` 形状**：
   F 号 `F-CHANGELOG-ENTRY-CROSSCHECK` 全仓只出现在三处（`grep -rl` 读数）：
   `CHANGELOG.md`、`tests/test_changelog_commit_crosscheck.py`、`scripts/changelog_commit_crosscheck.py`；
   真正的取证/设计文档是 `docs/audit/s104/CHANGELOG_COMMIT_CROSSCHECK_DESIGN_2026-09-29.md:1`
   （标题「第 104 片设计：拿 `git log` 当第四源，把"整条条目缺席"判红」）。
   起草块里我引的是后者，别按 `*F-*.md` 的通配去找——找不到会误报「取证文档缺失」。
6. 其余核对结果与你一致：带 `--self-test` 的 `scripts/` 脚本确实 10 台（名册表逐行给了
   `add_argument` 出处），旗标拼法 10 台全同（无 dest 覆盖、无单破折号或短旗别名变体）。
