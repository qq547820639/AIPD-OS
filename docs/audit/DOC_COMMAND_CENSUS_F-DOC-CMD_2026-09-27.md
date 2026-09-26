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
| B4 | 把契约 deprecated 别名并进权威面 | **SURVIVED** | **今天无法判**（不是缺牙）：实测 10 个别名全部仍注册在 argparse 树上（`aliases - paths == ∅`），撤掉并集 11 条全绿。已把该步改写成一条活的前置 `alias_unregistered`；第二轮 **C2 = UNDECIDABLE-BY-DATA**（明写"今天没有能红它的语料"，不当杀、也不当活） |
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


## 七、终读数

@FINAL@

## 八、遗留

- 别名与真名**双向**只核了一向：文档写 `aipd init-project` 现在被放行（它是契约里的 deprecated），
  但"文档还在推荐已被取代的别名"这件事没有判据——那是另一面尺子（要不要留别名写法本身也是裁决项）。
- `--db/--project` 这类**旗子名**不在本片范围内：第 46 片那把"幻影参数"尺子管旗子，
  本片只管命令名；两面合起来才是一条完整命令。
- 只报面目前只有"人读"这一个读者（渲染 + JSON 落盘），没有棘轮。若要把 `aipd ctq list`
  这类名字钉成"只许减不许增"的账，需要先决定它归谁裁决。
