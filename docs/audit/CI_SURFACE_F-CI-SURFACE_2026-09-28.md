# 第 91 片：CI 门禁面 ↔ 本地收口链对账（F-CI-SURFACE）

量具：`scripts/ci_surface_census.py`；消费表：`docs/audit/CI_SURFACE_REGISTER.json`；
常驻面：`tests/test_ci_face_gates.py`（ruff / mypy / schema_check 三面）+
`tests/test_ci_surface_census.py`（这把尺自己的牙）。

## 一、起因与分母（现读，不是推测）

第 90 片顺手清掉一条 `E501` 时记下："认证链不跑 CI 的 lint 口径"。本片去补那道门之前，
先把这句话量成一张表——把 `.github/workflows/ci.yml` 的 `run:` 命令逐条抽出来
（命令与 job 都按 workflow 现读，见 `docs/audit/s91/build_ci_surface_register.py`），得：

| 读数 | 值 |
| --- | --- |
| CI 的 job 数 | **17** |
| 会被单独执行的 shell 命令（按文本去重后） | **32** |
| 其中"本地收口链有归宿"的（本轮之前） | **0** |
| 本机 `which gitleaks` / `which act` | 都无 |
| 本机 `find_spec('pip_licenses')` | False；`build`、`pip_audit`、`cadquery` 都在 |

两个具体后果，都是一手复现而不是推断：

1. `ruff check src tests state_service`：第 90 片在 HEAD 复现出 1 条 E501
   （`tests/test_release_evidence_preflight.py:344`，自第 84 片起就在）。
   全量那一跑每次都报 2700+ passed，**没有任何一格读这条命令的结果**。
2. `mypy`：`ci.yml:130` 的注释写着「本地硬基线（ruff 0 / mypy 0）此前在 CI 不设防；
   补 lint job 使之成为门禁」——第 91 片现读是 **24 errors / 20 files**
   （`python -m mypy` → `Found 24 errors in 20 files (checked 478 source files)`）。
   ⇒ 那句话当时可能真成立过，今天不成立；而"补 lint job 使之成为门禁"只对 CI 成立，
   对本仓的收口链不成立。这就是**假叙述住在没人读的位置**的标准形状。

## 二、选型（AGENTS.md 第三节，四段齐全，动手前展示）

要拍的问题是：**用什么机制保证"CI 判的东西"在本地也真被判**。

### 二之一、候选清单（每条带可打开出处与亲验状态）

| 候选 | 出处 | 亲验状态 |
| --- | --- | --- |
| nektos/act：把 GitHub Actions 的 workflow 在本地跑一遍 | https://github.com/nektos/act | 我本人打开该仓库主页：**MIT License**；正文说明它靠 **Docker API** 拉镜像、起隔离环境来复刻 runner |
| pre-commit：框架化管理多语言 pre-commit 钩子 | https://raw.githubusercontent.com/pre-commit/pre-commit/main/README.md | 我本人抓到那句 "A framework for managing and maintaining multi-language pre-commit hooks."；**许可证与安装命令未亲验**（先经 GitHub 页超时，README 现版只剩徽章与外链，没写到那两格）|
| 自研一把"以 workflow 为权威面"的结构对账尺 | 本仓 `scripts/ci_surface_census.py` | 本片实现，四格 `--self-test` 已跑 |
| 只把三条命令抄进常驻用例（不建对账面） | —— | 不需要外部项目；作为"最省事方案"进对比 |

未检索到第四个同类候选（"专门对账 CI job 与本地门禁覆盖面"的开源工具我没找到），
如实写"未检索到"，不补位。

### 二之二、六维对比（只写可核验的结论）

- **功能匹配度**：要的不是"把 CI 跑一遍"，而是"**CI 加了/撤了一道门，本地要知道**"。
  act 执行 workflow，但它不产出"哪些命令本地没人消费"这张表；把 CI 的 13 个 job 全跑一遍
  也要 30 分钟以上，而收口链只有 ~6 分钟。第四个候选（只抄三条命令）解决今天的红，
  解决不了下个月 CI 新加一条时的静默。
- **License 兼容性**：act 是 MIT（我本人读到的徽章与 LICENSE 文件名），与本仓 Apache-2.0 可并存，
  但它是**Go 二进制**，引进来要走"下载可执行文件"这条路——与 CI 里那条 `curl … gitleaks …`
  同一族（我把它判成结构性 CI-only 的理由在这里同样适用于自己）。pre-commit 许可证未亲验，
  不据以决策。自研零新依赖（只用已在 `full` 档声明的 `pyyaml`）。
- **维护活跃度**：act 与 pre-commit 都是活跃项目——**这一条本轮不作为决策依据**，
  因为我没读 release 页，不写具体版本号。
- **安全风险**：act 要求 Docker，而本机 `which docker` 有、`which act` 无；
  要跑得先引入一个能拉起容器的第三方执行面，且 CI 里那些 job 本身 `pip install` 联网装包。
  把联网安装放进认证路径＝给认证加一个不可控依赖面（第 81 片那条 pillow/CVE 的教训同族）。
  自研只读两个文件（workflow + 册子），不执行任何 CI 命令；真正执行的是三条常驻用例。
- **代码质量**：外部工具对 YAML/shell 的解析成熟度高于本尺（本尺的粒度是"一行一条命令"，
  且 `line` 恒 0——见 §四边界 1）。但它们都不表达"消费方是谁"这个概念，接进来仍要自建这张表。
- **适配成本**：act ⇒ 装二进制 + 起容器 + 改 job 以适配本地（`.[full,dev]` 那类安装要在容器里重跑）；
  pre-commit ⇒ 只在 **commit 那一刻**、且**只在装了钩子的那个克隆**里生效——
  本机实测 `.git/hooks/` 里没有 `pre-commit`（只有 `post-checkout`、`post-commit` 两个非 sample 钩子），
  而本仓的判定发生在 commit **之后**（清单/证据/门/验签），钩子跑不到那一层；
  自研 ⇒ 一个脚本 + 一份册子 + 一个常驻文件，与第 60 片那把尺同形状，成本已被验证过一次。

### 二之三、择一决定：**借语义自研**

选"自研结构对账尺 + 三条命令接进常驻"。**借的是 act 的一个观点**：
以 workflow 文件为唯一权威面，本地**不复制一份命令清单**（复制一份就会漂一次）。
这一点不是口号——消费表的键一律由 `ci_commands()` 从 ci.yml 现读生成，
生成脚本 `docs/audit/s91/build_ci_surface_register.py` 里只写**子串规则**；
任何一条命令没被唯一接住就整批不落盘（本轮它真的拦下一次：
`python -c "import cadquery as cq; …"` 一开始没有规则接它）。
不引 act 的理由如上；不用 pre-commit 的理由是**执行时机与 enforcement 面都不对**。

### 二之四、落地处（每条结论指到它实际改动的文件）

- "CI 每条命令都要有归宿" ⇒ `scripts/ci_surface_census.py:audit()` 的
  `CI面无人守` / `CI面空头委托` / `CI面免跑没理由` / `消费表该撤` 四档判决；
- "权威面只有一个" ⇒ `docs/audit/s91/build_ci_surface_register.py`（现读生成）+
  `tests/test_ci_surface_census.py::test_commands_are_read_from_the_workflow_not_from_a_copy`
  （册子里每条命令必须逐字出现在 ci.yml 里，且比较前同样折 `\` 续行）；
- "免跑不许变成后门" ⇒ `kind: ci-only` 必须带 `why`，否则判红
  （`tests/test_ci_face_gates.py::test_register_points_here_and_only_here` 与
  `--self-test` 第三格各钉一端）；
- "登记面 ↔ 执行面也要互点" ⇒ `tests/test_ci_face_gates.py`（量具只核到文件级，
  "这个文件到底跑了哪几条命令"只能在这里钉）；
- 三条命令真跑 ⇒ `tests/test_ci_face_gates.py` 的 `test_ruff_face_is_clean` /
  `test_mypy_face_is_clean` / `test_schema_check_face_is_clean`（缺工具 `pytest.skip`，
  不把"未覆盖"报成绿）。

## 三、分类依据（13 条"结构性免跑"逐条给因）

* 安装与解包（`python -m pip install --upgrade …`、六种 `pip install -e ".[…]"`、
  `pip install pip-audit/pip-licenses/build`、`curl … gitleaks …`、`tar -xzf …`）：
  要联网装包或往 `/usr/local/bin` 写文件。后者是**共享状态动作**，不属自决范围，
  所以不是"我没想到"，是"我不该在收口链里做"。
* `gitleaks detect`：本机无该二进制（实测 `which gitleaks`），且它扫提交历史，
  而收口链跑在 detached worktree 上——历史面不在这一格。
* `python -m build`：会往 `dist/` 落产物，而收口链硬要求工作树干净
  （`closeout_verifier` 的 `worktree_clean` 无豁免路径）。打包一致性另由
  `tests/test_packaging.py` 在本地判，那一格已登记。
* `pip-licenses`：**这条最值钱**——它根本没有可失败的断言（只把许可证打印出来，退出码恒 0），
  把它当门禁是假承诺。登记成免跑并写明理由，比假装它被覆盖了诚实。

19 条"已接住"里，`-m pytest` 系（10 条）一律记在 `scripts/closeout_verifier.py` 名下，
理由是现读的：本地全量那一跑是**无标记的超集**（collected 2726，`integration` 打标的
21 条都在名单里，5 条 skipped 是 smtp/imap/arxiv/pmc 这类真网络项，不是 CAD——
`cadquery` 本机在盘且 28 条 CAD 用例都真跑了）。"谁跑遍了整棵树"由
`roster_covers_tree` 那一格证，不是由我在文档里说。

## 四、已知边界（写清是哪一种）

1. `line` 恒为 0：PyYAML 的 `safe_load` 不带行号，判据要靠 `compose` 才拿得到标记。
   违规行因此按 **job 名 + 命令文本**定位（消息里带 `CI 的 'lint' job`）。
   属"本轮没做"，不是机制限制。
2. 命令文本按"一行一条"切，不看 shell 的 `&&`/`||` 与 `for` 循环：
   `a && b` 会被当成一条。今天 CI 里没有这种写法（实测 32 条里 0 条含 `&&`），
   所以不咬现状；CI 若改用 `&&`，本尺会把它当一个整体命令要求登记，不会静默漏判。
3. "consumed" 的判据是**归宿存在且有效**（文件在、`tests/` 下的还要求真有用例），
   不是"逐字复现 CI 的执行环境"。例：`python scripts/audit_repo.py --json-out …`
   记给 `tests/test_audit_repo.py`——同一份判据在进程内跑，落盘那一份不是新判据。
   这一格是刻意的粒度选择，写在这里以免下一轮把它读成"等价执行"。
4. CI 是否真的在跑、跑成什么颜色：未验证。本机 `gh auth status` 报
   "You are not logged into any GitHub hosts" ⇒ 拿不到 Actions 的历史。
   属**机制限制 + 线下项**（要真人登录）；本片的判据不依赖那一面——
   我以本地逐字复现 CI 命令代替（ruff/mypy/schema_check 三条都亲手跑过，读数见 §一）。

## 五、电池首跑 6/8：两支存活都换成了真改进（不是"臂没用地摘掉"）

`docs/audit/s91/battery91.py` 第一跑 `KILLED 6 / 8`，两支 SURVIVED。
按第 81 片那条规矩——**臂存活先问"这个变异改得了任何可观察输出吗"**——两支的答法不同，
而且都不是"用例太弱"：

1. **A6（撤 `_norm` 里的 `\` 续行折叠）存活的原因：那是一条永不达到的路径。**
   续行折叠其实在 `_split_shell()` 里已经做过（逐行读块标量、看到上一行以 `\` 结尾就并进来），
   所以交给 `_norm` 的串**永远不含换行**，那句 `replace("\n", " ")` 是死代码。
   处置：**删掉它**，并把 A6 改指真正的折叠点（`_split_shell` 里那个 `endswith("\")` 分支）；
   改完 A6 由**真语料**开火——那条 `curl … gitleaks …` 折成两条 ⇒ 与册子的键对不上 ⇒
   「无人守」+「该撤」各一笔。
   记这一条是因为它的形状很坑：一个"看起来在做规范化"的调用完全可以是空转的，
   而**只有撤销臂**能把它照出来（`--self-test` 与常驻用例都照不出，它们对空转不敏感）。
2. **A8（`consumer_alive` 不核文件是否存在）存活的原因：夹具只造了一极。**
   同一格判据有两种失效——"文件在但一条用例都没有"与"文件压根不在树里"——
   而 `--self-test` 的语料只有前者。处置：**补第二极**（在册命令挂一个不存在的消费方文件），
   并要求两条的**理由文本不同**（"一个 `def test_` 都没有" vs "文件不在树里"），
   否则两极会退化成同一格。补完 A8 被抓住；`--self-test` 的**格数没变（仍是 4 格）**，
   变的是第一格内部——从"一极"变成"两极"，这也是为什么"格数"不是覆盖度。

改完 `KILLED 8 / 8`、退 0，收尾复算 sha 与开局一致。

## 六、委派账：mypy 24→0 交给子代理，判据与验收都是我写的

派件理由：24 条类型错误分散在 20 个文件、修法基本机械，属于"小修小补、可拆分、低风险"；
主理人这一侧的时间要花在**判据设计**（面 ⑤/消费表/三面接进常驻）上。
交出去的判据（原文在派发提示里）：**不许 `# type: ignore`、不许改 `[tool.mypy]`、
不许用 `cast(Any, …)` 或把参数标成 `Any` 糊弄、不许加 assert 或改运行时行为、
不许动测试断言强度、生产代码里要改语义的一律报回不动**；并要求回报带命令＋读数。

我亲手复算的四项（子代理回报只当导航档，不当结论）：

| 复核项 | 手法 | 读数 |
| --- | --- | --- |
| 类型面真的干净了 | 我自己跑 `python -m mypy` | `Success: no issues found in 480 source files`（480 = 原 478 + 本轮两个新测试文件） |
| 有没有偷删断言 | `git diff -U0 \| grep '^-' \| grep -c 'assert '` | **0** |
| 三处 `cast(...)` 是不是糊弄 | 逐个打开看被 cast 的表达式 | `cast(str, …)`/`cast(SourceRef, …)`/`cast(dict[str, Any], …)` 都是**收窄到生产侧真实形状**，不是收成 `Any`；其中一处附了理由"加断言就动了运行时行为" |
| lint 面没被弄坏 | `ruff check src tests state_service` + `--fix` 后的复跑 | RC=0，`All checks passed!`（`--fix` 只对我本轮新加的文件跑） |

一处要**点名交回**的偏差：它动了我本轮自己写的 `tests/test_doc_command_census.py`
（一条 `union-attr`：`TruthRecord.source` 类型上是 `SourceRef | None`）。
复核结论是语义未变——读的还是同一条 `.source.note`，只是把收窄从"隐式"改成 `cast`——
但它改的确实是我这一轮刚写完并测过的文件，所以我在收口前**重跑了那个文件的全部 52 条用例**
（`73 passed`，与本轮另三个新文件同跑），而不是只看它的回报。

顺带记一条委派时的环境事实：派发时 `mypy` 的报错数在我这一侧从 24 变到 21 又变到 0，
中途我自己复跑会读到**半成品状态**的读数（478→479→480 文件数也在动）。
所以"复核件的读数"必须写清是**哪一刻**的，否则下一轮会把中间态当成结论。

## 七、认证读数（有效代）

| 项 | 读数 |
| --- | --- |
| 干净全量（worktree `.wt-s91` @ `e4dddfe`） | **2731 passed / 5 skipped / collected 2736**，453.5s，`exitcode=0` |
| 报告自记清单指纹 | `25e395e2b788…` == 磁盘 `SOURCE_MANIFEST.json`（`release_fingerprint.py` 现读，绑定前后各核一次） |
| 锚点 | `a66040520139405095648461f7144d4f00629924`（`git rev-parse v5.6.0^{commit}`） |
| 跳过面 | 与上一代逐条相同（5 条，都是真网络项：smtp/imap/arxiv/pmc/researchstudio） |
| 发布门 | 8/8、`release_ready=True`、退 0（`PATH` 带 `.venv/bin`，否则 `pip-audit` 那格 fail-closed 假红） |
| 收尾验签 | 11/11 全绿、`CV_RC=0`，`--min-tests 2736` 由报告 `summary.collected` 现取，`--expect-test` 点名**两条**新原告 |
| 回收 worktree 后复算 | `-b2`：11/11、退 0 |
| 被哈希文件数 | 685 → **688**（差集恰为 `scripts/ci_surface_census.py` + 两个新常驻测试文件） |
| 判据本身 | 面 ⑤：命令形态 133 ⇒ 入库 90 / 未入库 0 / 死链 22（全在册）/ 占位 6 / 交面 ④ 5 / 点名举例 10，退 0；CI 面：32 条命令 ⇒ 19 已接住 / 13 免跑有据 / 0 无人守，退 0 |

### 七之一、本轮自己付账的两次流程红（都记下来，不覆盖）

1. **在一跑进行中补写取证文档，被自家门判红。** 全量在跑的时候我把 §五/§六 追加进本文并留在工作树里；
   随后 `production_release_gate` 的 `workspace_clean` 与 `closeout_verifier` 的 `worktree_clean`
   同时读到那一处未提交改动 ⇒ `GATE_RC=2`、`CV_RC=4`（其余 10 格全绿）。
   因为 `docs/audit/**` 不参与清单哈希，报告自记指纹仍然同源 ⇒ 正确处置是
   **"把补记入库 → 复跑门与验签"**，而不是重跑 7 分钟全量，也不是绕闸或放宽判据。
2. **`-b` 复算的第一跑被我自己的 cp 顺序弄红，而我把一条错结论写进了提交信息。**
   我先 `cp docs/audit/s91/report-s91.json`（未跟踪）再跑 `-b` ⇒
   `worktree_clean：工作树有 1 处未提交改动：['?? docs/audit/s91/report-s91.json']`，`CV_RC=4`；
   但当时提交的说明写的是"（-b 仍 11/11）"——**那句话与同批入库的读数文件互相矛盾**，
   本行就是它的更正。修法是第 60 片那条的老形状：工具/报告的产物**先落树外、复算、再 cp 并入库**；
   复算读的是"跑的那一刻"的树，不是"提交之后"的树。
   干净重跑（`closeout-s91-b2.*`）才是 11/11、退 0。

顺带一条对尺子的观察：`docs/audit/sN/gate.json` 住在被它检查的树里，所以**同一轮里
"跑门"这件事本身会把工作树弄脏一次**——第一跑必红、把读数入库后第二跑才可能绿。
这不是 bug（它就是要工作树干净），但下一轮若把"第一跑红"误读成代码回归就会白改一轮。
