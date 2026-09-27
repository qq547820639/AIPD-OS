# 第 82 片：文档里"续行接另一条命令"的常驻判据（F-DOC-CONTINUATION）

日期：2026-09-28。承接第 81 片取证文档 §七.3（那条已把代价量成数，本轮接成机器判据）。

## 一、技术选型（先检索，再决定自研还是引外部）

**为什么触发检索**：这不是改一句话，是给共享门禁加一档新判据（`doc_command_census` 的判红面），
会影响后续每一份文档的写法，所以按规矩先查成熟实现。

### 候选清单（都有可打开的出处）

| # | 方案 | 出处（本轮真实打开过） |
|---|---|---|
| A | markdownlint（JavaScript，60 条规则的官方全表） | `https://raw.githubusercontent.com/DavidAnson/markdownlint/main/doc/Rules.md`（本轮抓取并逐条读表）；仓库元数据 `https://api.github.com/repos/DavidAnson/markdownlint` |
| B | remark-lint（unified/remark 的规则集，约 70 条） | `https://raw.githubusercontent.com/remarkjs/remark-lint/main/readme.md`（本轮抓取并读规则清单）；仓库元数据 `https://api.github.com/repos/remarkjs/remark-lint` |
| C | 外部候选第三个：**未检索到** | 我按"markdown shell linter / code block command validator"这条线找过，没有落进"能判续行断裂"的现成工具，故如实记为未找到，不补位 |

### 六维对比

- **功能匹配度**：A **无此规则**——抓来的规则全表里与命令最相关的只有 `MD014`（`$` 前缀用法）与
  `MD031/MD040/MD046/MD048`（围栏的空白/语言标记/风格），没有一条看 shell 语义；B 同样
  **无此规则**，且文档明说这些插件**inspect mdast**（判语法树节点，不解析代码块里的字符串）。
  两家的判据对象都不是"这一行能不能照抄执行"。
- **License 兼容性**：两家仓库元数据都是 `license.spdx_id = MIT`，与本仓（MIT）相容——这一维**不构成淘汰理由**。
- **维护活跃度**：A `pushed_at = 2026-09-26`（本轮抓取时刻的前一天）、6359 star、82 open issues、未归档；
  B `pushed_at = 2026-09-05` 之前（实测 `2026-01-05T19:25:40Z`）、1043 star、9 open issues、未归档。
  两边都活着，A 更活跃。
- **安全风险**：引入 A/B 都要在 CI 里跑 Node；本仓 CI 现状是 Python-only（`Makefile`/workflow 里没有 node 步骤），
  为一个判据加装 Node 运行时是新攻击面与新的版本漂移源。
- **代码质量**：两家质量都没有可指摘处；A 的规则文档逐条带正例/反例，这一维反倒是我借鉴的对象。
- **适配成本**：本仓要判的语料是**行首可执行速查行**这一档（README/SKILL/QUICKSTART/`docs/architecture`/
  `docs/contracts`/`references`），而"命令名是否注册"必须拿 argparse 树来判——A/B 都不读 CLI 契约，
  接进来也只能管格式，权威面对它们不可见。也就是说：即便有这条规则，它也无法在我真正需要的语料上做判决。

### 择一决定：**自研**，并借 A 的两条实现思路

理由不是"找不到现成的"这一句空话，而是三条可核验的事实：
① 两家的规则都不解析 shell 语义（A 全表无、B 明说只 inspect mdast）；
② 本机实验证明**连 shell 自己都看不见**这个缺陷——把 `3784a0a:README.md:271/272` 两行原样喂给
   `bash -n`，**退码 0**：反斜杠续行把两行拼成**一条**命令，第二条命令的词全变成第一条的参数，
   语法合法、语义才是错的（读数：`bash -n joined.sh; echo $?` → `0`）；
③ 权威面（哪些 `aipd …` 真的存在）只有本仓 argparse 树知道，外部 linter 接进来也判不了这一档。
借的东西写清楚：借 A 的**规则文档形状**（一条规则一个 `field`、带可核验的正反例）与
"一行一条判决"的粒度；没有借它的实现，也没引 Node 依赖。

## 二、判据形状与两极

`scripts/doc_command_census.py` 新增判红面 **②b**：

- 谓词：一行 `rstrip()` 后以 `\` 收尾，且**下一行**去掉行首注释符/列表符/反引号与缩进之后以 `aipd ` 开头；
- 语料：与判红面 ② **同一份遍历**（新增 `quickref_corpus()`，`quickref_lines()` 改为消费它）——
  两档各写一遍 rglob 是本仓记过的老坑，排除档一漂就出现"一档看得见、一档看不见"；
- 判决：直接进 `violations`（`field="续行"`），不经过 `record()` 的名字去重——它判的是
  "能不能照抄"，不是"名字存不存在"；`corpus.continuation_breaks` 自报分母。

两极各有一条常驻用例，且**必开火的夹具从 git 现取**，不手写相似片段：

- `test_broken_continuation_fires_on_the_real_historical_shape`：从
  `git show 3784a0a:README.md` 里取"以 `\` 收尾 + 下一行另起命令"那对**逐字**相邻行；
- `test_legal_continuation_does_not_fire`：从 `HEAD` 的 README 取合法那一型
  （下一行是 `  --db state.db --bom BOM-1` 这种旗子）；
- 真仓库侧另有一条：`test_real_repo_clean_and_all_three_judging_faces_live` 现在钉
  `continuation_breaks == 0`——"0"与"看不见"的区别由上面那条必开火用例负责。

## 三、牙齿实测（单变量变异）

`scripts/doc_command_census.py` 是**未提交状态**被改的，所以备份用 `cp` 而不是 `git checkout`
（后者会把本轮实现一起清掉）。变异内容：`continuation_breaks()` 照样扫语料、结果一律返回空表。

| 变异 | 结果 |
|---|---|
| 清空 `continuation_breaks` 的返回 | **两条红**：`--self-test`（`expect` 集合少了那一格）＋ `test_broken_continuation_fires_on_the_real_historical_shape` |
| 还原 | `sha256` 前后 `ddbe33b84b0e` → `ddbe33b84b0e` 一致；`tests/test_doc_command_census.py` **19 passed**、`--self-test` 8 条合成读数全对上 |

一处要如实记的不对称：合规侧那条（`test_legal_continuation_does_not_fire`）在变异下**仍然绿**——
清空判据只会让它更容易通过。反向对照天生没有这个方向的牙，别把"它照绿"读成判据没牙，
也别拿它当变异检测器用。

## 四、读数（命令 + 实际输出）

- `scripts/doc_command_census.py --repo .`：`rc=0`；"速查语料里断掉的续行 **0** 处"；
  `--json` 的 `corpus.continuation_breaks = 0`、`violations = []`、`ok = true`。
- `scripts/doc_command_census.py --self-test`：`--self-test：8 条合成读数全部对上`（分母从 7 涨到 8，
  新增的两条标记分别是"断续行抓到历史原件那一行"与"合法续行不开火"）。
- `pytest tests/test_doc_command_census.py -q`：**19 passed**（本轮新增 2 条常驻用例）。
- 历史原件取证：`git show 3784a0a:README.md` 的 `:271` 以 `\\` 收尾、`:272` 是
  `aipd drawing assembly-steps … --pdf   # 顺带出 A4 图框矢量 PDF（中文可抽取）\`。

## 五、这一格闭合与新的入口

- 第 81 片取证文档 §七.3 就地标注为已闭（它的分母那次已经量准：`224 个 .md / 27,915 行 / 61 处以 `\` 收尾`，
  判据只做形状 a；形状 b 只报不判的理由沿用那一版）。
- 新入口：**形状 b 是否要判**仍是开放项。今天它 0 处，但它是词法巧合面
  （任何合法的"`--flag  # 注 \`"都会红），第 81 片已论证"今天 n=0 不足以证明长期安静"——
  要做就得先把"下一行是注释/尾注"与"续行本身就是注释"区分开，那是另一条谓词，不在本片范围内。
