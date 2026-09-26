# F-DOC-CMD 第 60 片：一面判据——文档/登记表点名的 `aipd` 命令必须真的注册着

## 一、这一片从哪来（不是新想法，是上一片自己犯的错留下的口子）

第 59 片重写 `registry_data.py` 的能力行时，我在新的 `current_limitation` 里写了
「只能读库或看 `aipd truth show`」——**`aipd truth show` 是一条不存在的命令**（我从
`truth drift`/`truth sweep` 的命名类推出来的）。它被抓回来靠的是派出去的只读普查，
**不是机器**；当时核实过原因：`run_command` 这类字段只被 `scripts/capability_matrix.py:157`
原样渲染成 markdown，**没有任何常驻判据把文档面点名的命令与真实命令表对账**。
那条事实现在被写成第 59 片取证文档的 §九 遗留，本片就是去闭它。

同一轮普查顺手抓出的第二处，是**代码里的幻影**（比文档更糟，因为它会被复制进数据）：
- `src/aipd_os/product_truth/ctq.py:168` 把 `aipd truth ctq add` 烙进**每一条**由
  `aipd ctq add` 产出的记录的 `source.note`（真实命令是 `aipd ctq add`）；
- `src/aipd_os/cli/commands_truth.py:418` 的 `--json` payload 自报 `"command": "truth ctq add"`，
  与同一文件里我新写的 `"ctq revise"` / `"ctq deprecate"` 自相矛盾。
两处本轮都已改，并由常驻用例反证钉住（§五 组 8~9）。

## 二、技术选型（四段，本轮真打开/真跑过）

### 1. 候选清单

| 候选 | 出处（本轮打开） | 现读事实 |
|---|---|---|
| A. `sphinx-argparse-cli` | https://pypi.org/pypi/sphinx-argparse-cli/json | 1.23.0（2026-08-27）、`license_expression=MIT`、`requires-python >=3.11`、`sphinx>=9.0.4`，历史 39 版 |
| B. `sphinx-argparse` | https://pypi.org/pypi/sphinx-argparse/json | 0.6.1（2026-08-21）、MIT、`requires-python >=3.10`，历史 32 版 |
| C. `Linkspector` | https://raw.githubusercontent.com/UmbrellaDocs/linkspector/main/README.md（200，24897 B） | 自述 "checks for **dead hyperlinks** in your files"，Markdown/AsciiDoc |
| D. 本仓同族量具 | `scripts/doc_reference_census.py`（361 行）、`scripts/command_surface_census.py`（451 行） | 现成形状：`corpus/classify/audit/render/_self_test/main`、**LIVE 判红 / HISTORY 只报** 分档、0/2/4 退码 |

### 2. 六维对比（每维一句可核验的结论）

- **功能匹配度**：A/B 的方向是"从 argparse **生成**文档"，而这里的诉求是"已有的文档与登记表
  不许指向不存在的命令"——两者互为逆向；C 判的对象是超链接，不是命令名；D 与本诉求同族
  （第 39 片量 argv 位、第 41 片量 `path:line`，本片量命令名，是同一族的第三把尺子）。
- **License 兼容性**：A/B 均 MIT（与本项目 MIT 不冲突）；C 的 license 字段本轮**没读到**
  （npm registry 的 `latest` 文档结构未解析出来），不据记忆补 ⇒ 标未亲验；D 本仓自有。
- **维护活跃度**：A 最新发行 2026-08-27、B 2026-08-21、C 的 README 挂 GitHub Marketplace
  与 Releases 通道 ⇒ 三者都活着；活跃度不是否决项。
- **安全风险**：A/B 会把 Sphinx 全家桶拉进一个**唯一硬依赖是 `jsonschema`** 的仓
  （`pyproject.toml: dependencies`），扩大安装面与审计面；C 是 Node 工具链，还需另装运行时。
- **代码质量**：A/B 成熟（`tox-dev` 与社区老牌），质量不是短板；短板在方向与运行时要求。
- **适配成本**：**A 要求 Python ≥3.11、B 要求 ≥3.10，本仓主解释器实测 3.9**
  （`.venv/bin/python`，`requires-python = ">=3.9,<3.13"`）⇒ 两条路都装不上；
  本仓也没有 Sphinx 文档流（文档是手写 markdown + 生成脚本），A/B 没有可挂载的地方。

### 3. 择一决定：借 D 的形状自研，不引依赖

借来的东西逐条写清（说不出借了什么的都要删）：
- 借 D 的 **LIVE/HISTORY 分档**：本片的对应物是"判红面 / 只报面"，理由不是审美而是实测——
  正文会**合法地**提到不存在的命令（§三 给了本轮的 FP 读数）；
- 借 D 的 **`--self-test` 合成读数**：新尺子第一遍先用来验自己，量不到就判红；
- 借 `command_surface_census.py` 的 **退码优先级**：0 干净 / 4 现状面违规 / 2 前提不成立
  （权威面建不起来、判红面为空、解析失败），**空读数一律不当通过**；
- 借第 39 片的 **AST 读实参位**思路：`run_command` 由 AST 取字典常量值，不靠 ±N 行文本窗口。

不引依赖的硬理由就是"适配成本"那一维的实测：A/B 的 `requires-python` 与本仓主解释器直接冲突。

### 4. 落地处

| 结论 | 落在哪 |
|---|---|
| 权威面＝argparse 声明树（契约 deprecated 别名改成活的前置，见 §六 B4） | `scripts/doc_command_census.py:valid_commands()`（实测 88 条路径、15 个组名、10 条别名） |
| 判红面 J1 登记表 `run_command` 每段 | `registry_run_commands()`（实测 84 段） |
| 判红面 J2 行首速查行 | `quickref_lines()`（实测 90 行） |
| 判红面 J3 生产代码里的非否定提及 | `production_code_mentions()` + `NEGATION_MARKERS`（实测 210 处判定 / 5 处同行带否定 / 判红 0） |
| 只报面 | `prose_mentions()`（实测 1200 处，含 `aipd ctq list`、`aipd truth show` 这类"记录缺口/记录错误"的写法） |
| 两处代码幻影的修法 | `src/aipd_os/product_truth/ctq.py:168`、`src/aipd_os/cli/commands_truth.py:418` |
| 常驻牙 | `tests/test_doc_command_census.py`（11 条：初版 10 条，第二轮补 1 条） |

## 三、命中率与假阳性（先量两档，再决定判到什么程度）

**这一步真的改变了实现。** 最初的设计只把"权威面"取成 `COMMAND_FUNCS`，两把尺子一对差异就露馅：

| 探针 | 读数 |
|---|---|
| `main(["usage"])` | **rc=0**，打出"支持的命令"清单（`cli/main.py:33` 注册 subparser、`_cmd_usage` 处理） |
| `"usage" in COMMAND_FUNCS` | **False** |
| argparse 树走出的路径数 | 88（含组名与 `usage`） |
| `COMMAND_FUNCS` 有而 parser 没有 | **[]**（派发表是声明树的真子集） |

⇒ 权威面若取派发表，第一版就会把 README 里合法的 `aipd usage` 判成幻影（速查行 1 处）。
**这就是"文档没错、尺子错"的那一类**，所以权威面改成 argparse 树。

判据分档同样是被读数逼出来的。**最终读数一律取量具自己报的六个分母**（先前用一次性脚本量的
336/45/291 那组数，在"登记表文件跳过代码档、去重改为与判决无关"两处改动之后就失效了，
不留进正文）：全仓 `aipd` 提及 **1214 处**，其中

- 判红面：登记表 `run_command` **84 段** + 文档行首速查行 **90 行** + 生产代码 **210 处**
  （另有 **5 处**同行带"没有/不存在/尚未…"否定标记 ⇒ 走只报；登记表限制句就是这种写法）；
- 只报面 **883 处**（＝全量扫描减去三档吃过的行，再加上那 5 处否定行）；
- 三档里点到未注册命令的名字只有 4 个：`aipd ctq list`（registry 限制句与历史取证）、
  `aipd truth show`（CHANGELOG 与取证文档里**引用我这次的错误本身**）、
  `aipd ctq listy`（本片测试自己的反向夹具）、`aipd truth ctq`（已修，只剩一条记录性引述）。

把这些一律判红＝惩罚"把缺口写下来"，下一轮就没人写 ⇒ 它们留在只报面。
⇒ **现状面今天 0 违规，而三档分母各自非空**：这是一把"会开火、但今天没人被它抓到"的尺子，
不是恒真判据（恒真与看不见在终端上同形，所以 §五/§六 每一面都配了必须开火的一侧）。

> 本节是**接线过程中**的读数。只报面的绝对数会随本轮继续往文档里写幻影名而涨
> （收口读数见 §七：只报面已从 883 涨到 908、未注册名从 4 个变成 5 个），
> 而判红面三档的分母不动——因为**判红面只吃登记表/速查行/生产代码，而取证文档属只报面**。
> 这正是分档要的效果：把缺口写下来不会让自己判红。

## 四、实现形状

`scripts/doc_command_census.py`：`valid_commands()`（永远取本仓的 argparse 树，不跟着 `--repo` 走，
避免临时目录里的 `src/aipd_os/` 遮蔽真包）→ 三档判红面 + 只报面 → `audit()` 自报六个分母
（`run_command_segments / quickref_lines / code_mentions / code_negated / prose_mentions /
report_only_mentions`）→ `render()` 逐条点名 `field 文件:行` → `main()` 退码 0/4/2
（2＝前提不成立：权威面建不起来、任一判红面为空、有文件读不动）。

**成本读数（不是契约，只回答"这把尺子贵不贵"）**：`/usr/bin/time -p` 跑完整普查三次
real = **2.44 / 2.18 / 1.73 s**；`pytest tests/test_doc_command_census.py` 整个文件
**3.11 s**（含一次 spawn `--self-test`）。
**同机同法量的对照组推翻了我先写下的一句 comparison**：我原以为"三档各读一遍文本"会让这把尺子
比第 41 片那把 `doc_reference_census` 贵，实测后者 real = **7.29 / 8.02 / 8.86 s**
（它要解析 4108 处 `path:line` 并逐个去文件里核行），本片这把 1.7~2.4 s —— **便宜约 3~4 倍**，
因为它只扫 `aipd` 一个词形、命中行才解析。绝对值随机器负载漂，不进门禁；常驻用例钉的是**分母下界**
（`>=50 / >=50 / >=100`、只报面 `>=500` 且 `< prose_mentions`），因为判红面一旦被静默收窄，
"0 违规"就什么都不是——这一条正是本轮我自己踩过的坑（§五 第 1 点）。

## 五、常驻用例（`tests/test_doc_command_census.py`，11 条）

| 组 | 用例 | 钉什么 |
|---|---|---|
| ① 尺子有人跑 | `test_instrument_self_test_is_actually_run_and_green` | **spawn** 子进程跑 `--self-test`（文本提到不算跑过）；还要看到 `✓立住` 与末行标记 |
| ② 现状面与分母 | `test_real_repo_clean_and_all_three_judging_faces_live` | 真仓库：`problems==[]`、`ok is True`，且三档分母各自非空（84 段 / 90 行 / 210 处），并断言 `report_only < prose`（去重真生效）与 `report_only >= 500` |
| ③ 开火/不开火对照 | `test_injected_phantoms_fire_on_all_three_judging_faces` | 三条假命令各落在自己那一档（速查行 / run_command 段 / 生产代码），且退码 4 |
| | `test_compliant_side_does_not_fire` | 合规侧同批存在：真命令、`aipd <命令>` 占位符、`aipd-os`/`aipd_os` 一律不开火；并断言 `prose==2 / report_only==0` |
| | `test_group_with_missing_subcommand_is_not_degraded_to_ok` | `aipd truth show`：组 `truth` 存在**不许**让整条放行（否则这是一把恒真的尺） |
| | `test_negation_in_production_code_is_reported_not_judged` | 代码里「没有 `aipd ctq list`」不判红，且 `code_negated==1`（判据不许惩罚写下缺口的人） |
| | `test_contract_alias_is_legal` | deprecated 别名（`aipd init-project` 等）是合法写法 |
| | `test_absence_written_in_prose_is_reported_not_judged` | 正文里的缺席陈述只报不红 |
| ④ 代码里的幻影 | `test_record_produced_by_the_command_names_a_real_command` | 跑公开命令 `aipd ctq add` 后**读那条记录的 `source.note`**，逐条解析必须在权威面上（本轮实测 `ctq.py` 曾往每条记录烙 `aipd truth ctq add`） |
| | `test_payload_command_labels_are_registered` | `--json` 的 `command` 标签＝注册名（`ctq add`，非 `truth ctq add`） |

写这批用例时**测试自己错过两次**，都记下来：
1. 作用域 fixture 起初是 `autouse`，于是真仓库那两条也被它扫窄成只剩 `docs/` ——
   **绿得毫无意义**（量具自指、`tests/` 里的反向夹具都看不见）。现在作用域只给临时语料用例，
   真仓库那条反过来断言三档分母下界，作用域再被收窄就会红。
2. 期望值我按"应该是多少"写了两次（`quickref_lines==4`、`fields(...) == {"quickref","run_command","code"}`），
   两次都被实际读数推翻（真值 3；三条注入各落一档）。规矩改成本轮做法：**先把夹具喂给量具跑一遍读真值**，
   再把它写进断言——同一类"写进计划的数字要当场跑过"的错，见 `[[feedback-evidence-grading]]`。
3. 还有一处是量具自己的设计缺陷：只报面的去重原先只看**违规行**，
   于是"判红面已经吃过但判决合法"的行被只报面重复数了一遍（实测 report 少算 331 处 → 修正后 883）。
   现在按"判红面覆盖的**行**"去重，与判决无关。


## 六、变异电池（两轮：`/tmp/s60/battery.py` 八臂 + `/tmp/s60/battery2.py` 三臂复核）

第一轮对照臂（未注入）当时 10 条全绿；八臂各自"锚点唯一→落地（sha 变）→跑→复位（sha 回）"，
判决只看原告。**第一轮读数是 杀 5 / 活 2（B3、B4）/ 崩溃击杀 1（B5）——三条都不是产品结论，
逐条读原文后全部改判**，这轮真正的产出在这三处：

| 臂 | 撤掉的守卫 | 第一轮 | 读原文后的定案 |
|---|---|---|---|
| B1 | `resolve()` 里"组存在但子命令不存在要判红"那半支 | KILLED | KILLED（原告断言翻红） |
| B2 | 生产代码面的否定例外（把带"没有…"的行也判红） | KILLED | KILLED |
| B3 | `judging_face_empty` 三档非空前提 | **SURVIVED** | **原告选错了**：那副空语料同时踩了 `quickref_corpus_empty`，撤掉 B3 的守卫它照样退 2。补一条把两个原因分开的常驻用例（速查档非空、只有登记表与代码档空）⇒ 第二轮 **C1 KILLED**（`rc=1`，原告 = `test_a_single_empty_judging_face_reads_as_failure_not_green`） |
| B4 | 把契约 deprecated 别名并进权威面 | **SURVIVED** | **今天无法判**（不是缺牙）：实测 10 个别名全部仍注册在 argparse 树上（`aliases - paths == ∅`），撤掉并集 10 条全绿。已把该步改写成一条活的前置 `alias_unregistered`；第二轮 **C2 = UNDECIDABLE-BY-DATA**（明写"今天没有能红它的语料"，不当杀、也不当活） |
| B5 | 只报面与三档之间的去重 | **CRASH-KILL** | **分类器误标**：原告是 `AssertionError` 翻红（`report_only_mentions == 0` 被打破），不是异常崩溃。第二轮 **C3 KILLED**（同一条变异，驱动直接把原告错误行打出来定性：`FAILED …test_compliant_side_does_not_fire - AssertionError`） |
| B6 | 量具自指排除 `SELF_STEMS` | KILLED | KILLED（真仓库现状面立刻被自己的正文判红，原告 `test_real_repo_clean_…`） |
| B7 | 记录 `source.note` 里的命令名 | KILLED | KILLED（原告读到 `aipd truth ctq`） |
| B8 | payload 的 `command` 标签 | KILLED | KILLED（原告读到 `truth ctq add`） |

**两轮的合计（以定性后的判决计）：杀 7 / 不可判 1 / 活 0 / 注入无效 0**（`battery2` 合计行
`{"KILLED": 2, "UNDECIDABLE-BY-DATA": 1}`，与预期不符的臂：无）。

电池自己教到三件事，都进规则而不是只进这一页：
1. **原告必须"可区分"**——B3 那条撤守卫之所以读成没牙，是因为另有一条守卫先红；
   补的用例把两个原因切开（速查档非空 ⇒ 只剩 `judging_face_empty` 能救）。
2. **"撤掉一条今天不产生差别的守卫"不是缺牙**，是数据的性质；写进账的名字应该是
   `UNDECIDABLE-BY-DATA`，不能记成"有牙"也不能记成"没牙"。
3. **成因分类器不可外包**：第一轮把 `AssertionError` 标成 CRASH-KILL，是因为驱动按"这段文本里
   有没有异常词"判；第二轮改成把**原告那一行的首条错误文本原样打出来**再定性，误标就没了。
4. **"有牙"与"今天载不载重"是两件事**（B2 的补算，电池报告提出、我独立复算过）：
   那条例外的牙在**合成夹具**上（原告那条用例确实翻红 ⇒ KILLED 成立），但在真仓库上
   **今天不载重**——把 `production_code_mentions()` 返回的 5 条 negated 行逐条按同一个
   `resolve()` 判一遍，**新判红 0 行**；这 5 行点名的命令（`ctq deprecate`/`init-project`/
   `drawing spec`/`ctq add`/`ctq revise`）全都注册着，只是同行带了否定标记。
   也就是说它保护的是一类**尚未发生**的误伤（代码注释写「没有 `aipd X`」而 X 不存在）。
   记下来的理由：如果只写"B2 KILLED"，下一轮会以为这条例外在保护现存的真行，
   从而不敢动它——那是一句没有依据的保守。

另记一处**由电池报告抓到、但报告本身不是证据**的事：量具自己的 docstring 抄了一份
更早范围的分母读数（"336 提及 / 45 否定 / 291 命中"），与它现在打印的 210/5 不符。
修法**不是把数改对**，而是**把绝对数从文档面上删掉、改成指针**（现算值看 `--json` 的
`corpus.code_mentions / code_negated`，下界由常驻用例钉）——与第 55 片"12 个场景"那处同一族病。
我先用一把**不同正则**去复算这个差（只扫 `src`+`scripts`，漏了 `state_service/`），
读出 1122/1050 一类数，那不能用来解释 336 从哪来 ⇒ 放弃因果叙述，只删掉抄的数。


## 七、终读数

绑定链（每个数都从命令输出取，不从上一节抄）：

- **干净检出 attestation**：`git worktree add --detach /tmp/s60a HEAD` @ `2275e267310a`，
  `pytest --json-report` 读数 `2490 passed, 3 skipped`，`summary.collected == len(tests) == 2493`，
  `exitcode=0`，`root='/private/tmp/s60a'`，`duration=258.67 s`，
  `source_commit=a66040520139405095648461f7144d4f00629924`（由 `AIPD_SOURCE_COMMIT` 显式给，
  不是 `git rev-parse HEAD` 顺出来的）。
- **验签**：`/tmp/s60/verify_report.py` **26 条前提全 [OK]**（条数由 `grep -c "^\[OK\]"` 现算）。
  对第 59 片那份已提交报告的自测**仍然拒签：14 条不成立**，且这 14 条构成能点名
  （`collected=2482 ≠ 2493` 1 条、`root` 不含本片检出 1 条、11 条新用例逐条缺席、
  报告早于本片检出 1 条）——不是"随便什么都拒"，也不是"改严之后把真报告也拒了"。
  绑定前验签器自己被抓到一次假绿形状：注入探针原来只喂一行速查语料 ⇒ `judging_face_empty`
  先把退码定成 2，"注入到底开没开火"就看不见；改成三档都非空并补一条**合规侧必须退 0**的对照。
  这就是 §六 第 1、2 条教训长在我自己尺子上的样子。
- **发布门禁**：`production_release_gate.py --release-ready --tag v5.6.0` → **8/8、rc=0**、
  `release_ready: true`。逐条：`workspace_clean=clean`、`commit_matches_head`、
  两份清单 `zero diff`、`test_numbers_from_report=['passed=2490 failed=0 total=2493
  source_commit=a6604052…']`、`signature_verifiable=['Ed25519 signature verified']`、
  `no_secrets`、`no_unacknowledged_cve`。
  **`no_unacknowledged_cve` 本轮先红后绿**：承认集合 28 条 / 今天命中 30 条。逐条查 OSV 后
  分开处置（提交 `b5b0355`）——`PYSEC-2026-3625`（msgpack 1.1.2）与表里已有的
  `GHSA-6v7p-g79w-8964` 是**同一条** `CVE-2026-57585` 换了告警号，门禁按号承认所以读成"新增"；
  `PYSEC-2026-3721`（pip 26.0.1→26.2）是真新告警，修复版 `requires_python` 由 PyPI JSON
  一手实测为 `>=3.10` ⇒ 本仓 3.9 装不上，按"根因"节同一处置。
  顺带改掉该文档一句**没有实现支撑的承诺**（原文写门禁"校验本文件的哈希与 CVE 清单一致"，
  读 `documented_ids()` 后确认它只是把文档里的号逐条 `--ignore-vuln` 传入并要求 pip-audit 退 0）。
  这条与本片的病**同族**：文档承诺了代码没做的事——差别只在它是被**门禁变红**抓的，不是被我的尺子抓的。
- **仓库审计**：`audit_repo.py --strict` → **rc=1，唯一一条 ✗**
  `Provenance source commit mismatch: manifest=a66040520139… vs HEAD=8d742bd0299a…`（设计内：
  清单钉 tag SHA、不跟 HEAD 重锚）；两份清单 `hash_mismatch_count` 均为 **0**。
- **静态门禁**：`ruff check src tests state_service` → All checks passed；
  `mypy src` → `Success: no issues found in 245 source files`。
- **量具终态读数**（`--json`，收口时重跑）：权威面 **88 条路径 / 15 个组名**；
  判红面 **84 段 / 90 行 / 210 处**（另 **5 处**带否定标记走只报）；
  只报面 **908 处**（全量扫描 **1239** 处）；只报面里点到未注册命令 **5 个名字**
  （`aipd ctq list` 21、`aipd truth show` 23、`aipd truth ctq` 7、`aipd ctq listy` 3、
  `aipd ghost cmd` 2）；**现状面缺陷 0 条**，退码 0。
  与 §三 的差（只报面 883→908、名字 4→5）就是"本轮自己往文档里写了幻影名的引述"造成的，
  已在那节末尾写明这是设计使然而非漂移。
- **同族尺子一起复算**：`doc_reference_census` 现状面 **0 缺陷**（文档 164 份、代码引用 4159 处），
  本轮新写的文本没有引入任何 `missing/line_beyond_eof`（19 条命中全在历史面与产物名上）；
  `command_surface_census` 仍是 **72 条 cli / 低于 cli 档 0 条**。
- **被哈希文件**：661 → **663**（本片新增 `scripts/doc_command_census.py` 与
  `tests/test_doc_command_census.py`；`RELEASE_MANIFEST.json 已刷新：663 个文件，version=5.6.0`）。
- **常驻用例**：2482 → **2493**（+11），全量 `passed=2490 / skipped=3 / failed=0`。
  3 条 skip 逐条点名（都不与本片相关，且各有明确前提缺失）：
  `tests/test_mail_protocol.py:201` 与 `:239`（`AIPD_MAILPIT_*` 未配置 ⇒ 走 HOLD 断言，
  需要本地 mailpit 实例）、`tests/test_researchstudio_provider.py:233`
  （`integration: requires internet`，需 `AIPD_RESEARCHSTUDIO_INTEGRATION=1`）。
  **记一处记账事故**：把这三条写进提交 `267223f` 的信息时，我把带反引号的路径放进了
  双引号的 `-m "…"` 里 ⇒ zsh 把反引号当命令替换执行掉，提交信息里那两个路径变成空白
  （读起来是"…逐条点名到 与 的前提"）。**文件本身没受影响**（上面就是完整读数），
  历史也不改写——与第 59 片"提交信息把 36 条前提抄成 30 条"同一处置：原位更正、不重铸提交。
  往后写提交信息一律用 `<<'EOF'` 引号型 heredoc，路径不用反引号包。

## 八、遗留

- 别名与真名**双向**只核了一向：文档写 `aipd init-project` 现在被放行（它是契约里的 deprecated），
  但"文档还在推荐已被取代的别名"这件事没有判据——那是另一面尺子（要不要留别名写法本身也是裁决项）。
- `--db/--project` 这类**旗子名**不在本片范围内：第 46 片那把"幻影参数"尺子管旗子，
  本片只管命令名；两面合起来才是一条完整命令。
- 只报面目前只有"人读"这一个读者（渲染 + JSON 落盘），没有棘轮。若要把 `aipd ctq list`
  这类名字钉成"只许减不许增"的账，需要先决定它归谁裁决。
- **量具族本身没有登记面**（本轮实测）：`grep -c census src/aipd_os/registry_data.py` = **0**，
  `docs/architecture/` 里也搜不到 `doc_reference_census`/`command_surface_census`。
  也就是说 `scripts/` 下这**三把**普查尺子（`command_surface_census`／`doc_reference_census`／
  `doc_command_census`，`ls scripts/ | grep -ci census` 现算 = 3；第 39-40 与 41 与 60 片各一把）
  在能力登记表与架构文档里**都不存在**，
  读者只能从 CHANGELOG 倒推它们存在。本片没有破坏这个性质（同族同形），但也不该假装它是对的：
  要么给"质量量具"开一档登记，要么在 `docs/architecture/` 立一张表，二选一都归后续裁决。
- **两处盲区：绑定之后由一次独立只读普查提出，我用我自己的夹具重跑证实**（都是本片这把尺子的
  **判据缺口**，不是今天的假绿；下一轮要补的是判据，不是文案）：
  1. **登记表里 `run_command` 之外的字段完全不可见**——三档的排除规则在这一行上叠加成双重盲：
     档 ① 只读 `run_command` 一个键；档 ③ 显式跳过 `REGISTRY_FILES`；只报面又按
     "该行已被判红面吃过"做减法。夹具（`/tmp/s60/probe_neg|pos|pos2`，三份只差
     `current_limitation` 的文案）读数：即便写成**正向断言**「先跑 `aipd ghostly cmd` 再导出结果」，
     仍是 `violations=[]`、`report_only_unmatched=[]`、`corpus={run_command:1, prose:3, report_only:0}`。
     registry 今天那一行是合法否定句（「没有 `aipd ctq list`」）⇒ **现状没有假绿**，
     但"登记表说：跑 X"这类错误可以藏在非 `run_command` 字段里而零信号。
     电池为什么没抓到：我没有"撤掉 registry 其余字段的判读"这一臂——**盲区不在设想的臂里，
     就不会被设想的臂打死**，这是本片电池覆盖面的真实边界。
     **→ 第 61 片已闭**（按名去重 + 4 条常驻用例钉住，读数见 §九）。
  2. **`.trae/specs/**` 与 `.github/workflows/*` 不在任何一档的遍历面上**：
     `REPORT_ONLY_DIRS = (docs, src, tests, scripts, state_service, templates, agents, evals)`，
     两个都不在其中（我把整份 JSON 报告序列化成字符串搜 `.trae` ⇒ False）。
     我亲手数 `.trae`：**46 处提及、21 个 md**。这两类文本是**会被真的执行**的
     （工程师/agent 照 spec 跑、CI 照 yml 跑），语义上恰恰最该判红；今天命中 0 个幻影，
     明天写错没人抓。附带一条：`git ls-files` 里没有 Makefile／`*.sh`／`*.html`（分母 0），
     而档 ③ 只 glob `*.py` ⇒ 将来引入 shell 脚本时它会落进只报面、永不判红。
     **→ 第 61 片把 `.trae`/`.github` 补进只报面**（可见性；要不要升成第四档判红面仍是裁决项），
     shell 那条未动，读数与理由见 §九。

## 九、第 61 片：把 §八 那两处盲区补成判据

调研跳过声明（按最高指令第三节要求写明理由）：本片**不选新组件**——改的是第 60 片那把自己研尺子的
去重键与遍历清单，候选面只有"按行减／按名减"与"要不要把某类文本升成判红面"两个内部取舍，
`sphinx-argparse*`/`linkspector` 在第 60 片已按六维比过并否决（方向相反、`requires-python >=3.10/3.11`
与本仓 3.9 冲突），本片没有引入新的外部可比对象。

### 1 动手前先量：三个数都是量出来的，不是推的

| 量 | 改前 | 改后 | 怎么量的 |
|---|---|---|---|
| 被"行级减法"吞掉的提及 | **27** 处 | 0 | 同一份 `prose` 分别按 `(doc,line)` 与 `(doc,line,名)` 减，取长度差 |
| `+ code_neg` 造成的**重复计数** | **5** 处 | 0 | `CODE_DIRS ⊂ REPORT_ONLY_DIRS` 都含 `src` ⇒ 那 5 条本就在 1256 的全量扫描里，逐条查成员命中 5/5 |
| 量具自身两份文件贡献的提及 | **68** 处（脚本 27 + 用例 41） | 0 | `prose_mentions()` 结果里按 `SELF_STEMS` 过滤计数 |
| `report_only_mentions`（真仓库） | 925 | **947**（升 `.trae`/`.github` 后再升到 **1002**） | 新旧两份实现同一棵树各跑一遍 `audit()`，并用手算分解核对 `920+5=925`、`947+0=947` |

**关键一条**：`+ code_neg` 那 5 处说明"只报面"这个数**一直多 5**——不是估计偏差，是公式重复。
证据是同树对账的两段分解：`按行减 920 + 5 = 925`（旧实现实际打印 925）、
`按名减 947 + 0 = 947`（新实现实际打印 947），两个等式都由 `prose_mentions() / production_code_mentions()`
的返回值现算，不是拟合。
（此处我一度写下"电池子代理测到的 903 恰好比打印值 908 少 5"当旁证——**重开那份日志后作废**：
`/tmp/s60/probe_b2_realrepo.log` 的 903 对应的全量扫描是 1234，而 908 那次是 1239，
**两个不同时刻的读数相差 5 是巧合**，不构成同刻对照。写旁证之前要先把两边读到同一棵树上。）
§三/§七 里那些数是当轮取证件，按规矩保留不追改。

### 2 改了什么（三处判据形状，都不动判决）

- `audit()`：去重键 `(doc,line)` → `(doc,line,写法)`；只报面由"并集"改"补集"
  （`kept + [r for r in code_neg if r not in set(kept)]`）。
- `prose_mentions()`：`SELF_STEMS` 的排除从"只有判红面 ③"扩到**四档全排**（含只报面）。
  这条不是洁癖：不改的话，本片新写的夹具名 `aipd ghostspec run`／`aipd ghostci check`／
  `aipd ghostly cmd` 会全部出现在"正文点到未注册命令"那张名单里（实测一度到 8 个名字），
  **报表把测试当成仓库的缺口**——与第 60 片修的两处代码幻影同一族病，只是这次谎主是尺子自己。
- `REPORT_ONLY_DIRS` 增 `.trae`、`.github`；升不升成判红面留作裁决项（两边今天都 0 幻影）。

### 3 常驻用例 +5（同文件现 16 条），以及一条"看着有牙其实没牙"

四条新用例先写先跑红（对着 `git show HEAD:scripts/doc_command_census.py` 换进同一棵树复算）：

```
改前那份 sha 77a458df3c18： 4 failed, 12 passed
  ✗ test_other_registry_fields_on_a_judged_line_are_still_reported     ← §八 缺口 1
  ✗ test_report_only_face_counts_each_mention_once                     ← 重复计数
  ✗ test_the_instruments_own_files_are_out_of_all_four_faces           ← 夹具名污染名单
  ✗ test_those_two_dirs_are_actually_walked_in_the_real_repo           ← §八 缺口 2
还原后 sha 7c47a43541e9： 16 passed
```

**但 `test_spec_and_ci_writers_are_watched_by_the_report_face` 在改前那份上也绿**——
因为它写的是 tmp 语料，而 `tmp_scope` 把 `REPORT_ONLY_DIRS` 一并 monkeypatch 成了含
`.trae/.github` 的值：**夹具替生产常量做了决定**。真正判别"生产清单里有没有这两个目录"的
是下一条（它跑真仓库、用模块自己的常量）。记进规则：*用 monkeypatch 扩大的作用域，
不能同时用来证明该作用域已被写进生产清单*——要么断言常量的字面值，要么走真仓库分母。
这条与第 60 片"autouse 把真仓库用例静默收窄成只剩 docs/"是同族病，方向相反（那次是收窄，这次是放大）。

### 4 现状面判决：没变

`violations=0`、`problems=[]`、退码 0——**三处改动一处都没让今天的仓库多红或少红**，
它们改的是"下一次谁会先知道"。这正是本片要的效果：盲区从"看不见"变成"看得见但不误伤"。

### 5 变异电池：每支改动配**自己的**原告（`/tmp/s61/battery.py`，5 臂全杀）

"整份换回改前实现"那次复算只给得出**合起来**的证据；按"复合门禁的每一支都要自己的最小对"，
这里逐支撤，原告只看各自那条（`[control] rc=0 红=（无）` 先证明不注入时 5 条全绿）：

| 臂 | 撤掉的守卫 | 原告 | 判决 |
|---|---|---|---|
| A1 | 只报面去重键退回**按行**（=第 60 片的双重盲） | `test_other_registry_fields_on_a_judged_line_are_still_reported` | KILLED（`rc=1`，原告翻红） |
| A2 | 只报面从**补集**退回**并集**（恢复 `+ code_neg` 的重复计数） | `test_report_only_face_counts_each_mention_once` | KILLED |
| A3 | 撤掉只报面里的 `SELF_STEMS` 排除 | `test_the_instruments_own_files_are_out_of_all_four_faces` | KILLED |
| A4 | `REPORT_ONLY_DIRS` 去掉 `.trae`/`.github` | `test_those_two_dirs_are_actually_walked_in_the_real_repo` | KILLED |
| A5 | **对照**：撤掉第 60 片的三档非空前提 | `test_a_single_empty_judging_face_reads_as_failure_not_green` | KILLED（旧牙还在 ⇒ 本片没把它改松） |

合计 `{"KILLED": 5}`、与预期不符的臂：无；每臂都过"锚点唯一 → sha 变 → 复位 sha 回 → 复跑回绿"。
A4 与 §九 3 那条"tmp 夹具在改前也绿"互为提醒：**判别生产清单的是走真仓库的那条用例**，
不是把作用域 monkeypatch 放大的那条。
