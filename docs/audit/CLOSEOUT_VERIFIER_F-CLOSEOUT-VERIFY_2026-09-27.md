# 收尾验签提为常驻量具（F-CLOSEOUT-VERIFY，第 64 片，2026-09-27）

产物：`scripts/closeout_verifier.py`（41 号常驻件）＋ `tests/test_closeout_verifier.py`（14 条常驻用例）。
本片**不加 `aipd` 命令**，所以 74 条注册命令、64 条 PUBLIC 契约、90 条 argparse 路径三张分母都不动；
动的是"每轮收尾时那台手写机器"。

## 一、起因：不是缺口，是成本

第 62 片与第 63 片的收尾验签都是**每轮现写**的脚本（`/tmp/s62/verify62.py`、`/tmp/s63/verify63.py`，
后者打出 25 条 `[OK]`）。`/tmp` 在宿主重启时被清掉，脚本连同"当初为什么这么判"一起没了；
下一轮就从轮次摘要里重推配方。第 63 片就是这么连踩两次**已有记录**的红：

| 踩的格 | 已有记录在哪 | 代价 |
| --- | --- | --- |
| 取证时 `AIPD_SOURCE_COMMIT` 传成本轮 HEAD（应为 tag 解析出的 SHA） | 项目记忆「每轮收口的重锚配方」① 段 | `production_release_gate` 判报告 STALE，`release_ready: false`，重跑一整套全量（约 4 分钟） |
| 跑 gate 没把 `.venv/bin` 放进 PATH | 同记忆 ⑤ 段（`shutil.which('pip-audit')` fail-closed） | 一次假红，又一轮全量 |

**判据**：凡是每轮都要重做、且做错一次就烧掉一轮全量的动作，不该存在于临时目录里。
所以这一片把这件事落成仓库里的机器＋仓库里的牙。

## 二、九格判决（退码 0 全绿 / 4 判红 / 2 前提不成立）

| 格 | 判什么 | 主线为什么看不见 |
| --- | --- | --- |
| C1 `report_bound_to_provenance` | 报告字节 sha256 == `PROVENANCE.test_report.sha256`（证据**还没绑**这份报告时读成前提塌，见 §四 第 4 条） | `release_evidence.py` → `_parse_pytest_report` 写入这条 sha，但**没有任何一处事后重算** |
| C2 `counts_counted_from_roster` | 汇总数由 `tests[]` 现数，再与 `summary` 与 `PROVENANCE` **两处副本**对账 | `production_release_gate._check_test_report`（`:503-542`）只读 provenance 里抄过去的三个数字；而那三个数字里的 `failed` 是 `total - passed - skipped` **推导**的 |
| C3 `terminal_clean` | `exitcode == 0` 且没有 `failed`/`error` 终态（setup/call/teardown 三相都查） | 门读的是"推导出来的 failed 数"，相位级 error 会被折进同一个数 |
| C4 `roster_covers_tree` | 树上测试文件 ↔ 名单文件**双向求差**为空；每文件「名单 ≥ 树上 def 数」；重复 nodeid 单列 | 没有任何常驻件把"报告里的名单"与"树上的 `def test_`"对上过——少跑一个文件今天读成 2512 条全绿 |
| C5 `pinned_source_binding` | 报告与 provenance 的 `source_commit` 都 == 给定锚点，**且锚点是工作树 HEAD 的祖先** | 门只做严格相等（无祖先那一支），而"锚点==HEAD"这一错法需要祖先那一支才说得清是"锚点漂了"还是"树不是那条线" |
| C6 `content_parity_measured` | 两条清单哈希用例在名单里且 passed | 「测的是这棵树」今天只是配方里的一句口头话；把它落到两条真用例上，跳过＝没证 |
| C7 `worktree_clean` | `git status --porcelain` 为空 | 与 gate 的 `workspace_clean` 同判据，但 gate 只在 `--release-ready` 那一次跑；收尾每轮都要跑 |
| C8 `plaintiffs_measured` | `--expect-test` 点名的本轮新用例确实在名单里并 passed | 这是"我写了 14 条用例、那一次签出到底跑没跑它们"的唯一机械答案 |
| C9 `size_ratchet` | `--min-tests` 下界（opt-in） | 借 `dorny/test-reporter` 的 `fail-on-empty`，但从"空就红"收紧成"低于下界就红"——本仓分母是 2 千量级，光"非空"挡不住截断 |

**前提档（退 2，不折算成"零违规"）**：provenance 读不出、**证据里还没绑这份报告**、报告读不出、
`tests` 为空、测试目录不存在、既没给 `--pinned-commit` 也没给 `--tag`。最后一条是刻意的：**没有基准就不判 STALE**，
因为"默认取 HEAD"正是第 62 片真犯的那个错（见 §五 A4）；倒数第三条同样是"没基准"（§四 第 4 条）。

## 三、选型四段（原件本轮重开，不是复述上一轮）

- 候选 (a) 扩写 `scripts/production_release_gate.py`；候选 (b) 新开同族件；
  候选 (c) `dorny/test-reporter`（MIT，README 本轮重开：输入 `fail-on-empty` 判"没有结果"，
  输出 `passed/failed/skipped` 三个计数）。
- 六维对比落在收尾提交里（功能匹配 / License / 维护活跃 / 安全 / 代码质量 / 适配成本）：
  (a) 的功能匹配是**零**——它连 `tests[]` 都不打开；(c) 是 GitHub Action，需要 Node 与 Actions 运行时，
  本仓的收尾复算跑在本地 detached 检出里，接不上。
- 择一：**自研 (b)，只借语义、不引依赖**。借两条：`fail-on-empty`（升成前提档）与计数词汇。
- 调研改变的东西：原计划把"镜像锚点（登记表 / 契约 / README / 代码四处都要有新命令的痕迹）"也塞进这台机器，
  读到 `doc_command_census.py`（三档判红面）与 `command_surface_census.py`（七档覆盖桶）已经把那两面占着，
  **删掉**——再加一份就是第三份手抄，正是这两把尺子要防的东西。
- 未检索到第三个同轴候选（搜"报告名单与树上 def 求差"只命中 pytest-json-report 本体、教程与
  coverage 类 `diff-cover`），如实记为未找到。

## 四、形状是被试跑教出来的，不是推的

合规对照臂第一轮就不绿，读数直接点名了判据自己的两处错；第二次（干净检出复算）又点名了
**用例**私藏的一条前提。

1. **名单文件面必须同时吃 `test_*.py` 与 `*_test.py`**。pytest 默认 `pythonFiles` 是两个模式，
   只 glob 前者时，`tests/maturity_consistency_test.py`（真仓库里唯一那个反向命名）被读成
   "报告里有个树上没有的文件"，而 C4 的判决看起来完全自洽。
2. **roster 的键要按 rootdir 相对**。nodeid 的 `::` 前面写的是 `tests/test_x.py`，
   按 tests 目录相对就得到 `test_x.py`，双向求差立刻**两边都非空**——
   这类"差集全非空"的读数比空读数更容易被当成"语料真的对不上"。
3. 附带一条旧账复发：`summary` 里 `failed`/`error` 键**计数为 0 时不存在**，必须读成 0。
   这条第 63 片记过一次，本轮在 C2 里又差点重犯（对照臂读成 `summary.skipped=None 而现数=0`）。
4. **常驻用例不许假设仓库处于"刚绑定"那一小段窗口**（第 64 片的新格）。
   第一次干净检出复算（`git worktree add --detach tmp/s64a HEAD`，HEAD 就是重锚那一提 `af1c6f4`）里，
   `tests/test_closeout_verifier.py` 有 **4 条**用例红：那一段 `PROVENANCE.test_report` 是
   `{"present": false}`（重锚与绑定之间本来就有这一步），量具便报两格判红，而用例把
   "除工作树干净外全绿"写成了断言。两边都错，各自修：
   - 量具侧：证据里没绑这份报告 ⇒ **前提档退 2**，`report_bound_to_provenance` 整个不进判红面，
     而 C2 里"报告内部 `summary` ↔ 名单"那一半照判（它不需要基准）；
   - 用例侧：凡拿真语料判绿的地方改成两种写法之一——① 先复制报告并就地绑定（`_bind_provenance`），
     使读数与"仓库正处在配方哪一步"无关；② 允许缺哪几格由 git 现算：
     `git log -1 --format=%H -- docs/audit/pytest-report-v5.6.0.json` 定位报告所在提交，
     再 `git diff --name-only --diff-filter=AM <该提交>..HEAD -- tests` 得到"合法缺席集"，
     与名单缺口求**等号**。写"差额为空"在途时必红，写"差额随便"就恒真，等号两边都自己算才两头能翻。

## 五、电池

**合成电池（量具自己，`--self-test` 18 臂）**：一支分母前提 + 一支合规对照 + 12 支逐格注入 +
4 支前提退 2（空名单 / 报告读不出 / **证据没绑报告** / 没给锚点）。每支注入都断言
"**开火的判据集合恰好等于该开的那一格**"，这是第 61 片量到的规矩：一次注入点亮三格时，
分不清是判据强还是夹具脏。实跑 `18 条合成读数全部对上`，rc=0。
三支夹具自己的错在这一层被抓出来：
① 证据文件当初写在夹具工作树**里面**，对照臂先红在 C7 上；
② C8 那一支没复位上一臂留下的 `failed` 终态，读成两格同火（同一个坑第三次露头）；
③ `tree_roster` 的键形状（§四 第 2 条）也是对照臂读出来的，不是看代码看出来的。

**变异电池（常驻用例，7 臂，脚本 `tmp/s64/battery64.py`）**：先立对照组（未注入 `16 passed`），
每臂落地前证明源文件 sha 变了、跑完立刻还原并验 sha 复原（`58d9d0ef23ee → 58d9d0ef23ee`）。
下表是**重写常驻用例之后再跑一遍**的读数（第一轮在 14 条用例上跑过，判决同为 7 KILLED；
改了用例就必须重跑电池，否则"杀掉"记的是一件已经不存在的事）：

| 臂 | 改坏的是什么 | 判定 | 常驻用例侧读数 |
| --- | --- | --- | --- |
| A1 | 名单只吃 `test_*.py`（丢 `*_test.py` 那半边） | **KILLED** | `2 failed / 14 passed`（真语料的 `maturity_consistency_test.py` 立刻被读成幻影文件） |
| A2 | `summary` 缺键不读成 0 | **KILLED** | `10 failed / 6 passed`（缺键即 None，把每一处对账都掀了） |
| A3 | 去掉"锚点是 HEAD 祖先"那一支 | **KILLED** | `1 failed / 15 passed`（只有 self-test 那一臂在管——单点原告，别删） |
| A4 | 没给锚点时默认取 HEAD（第 62 片的真错） | **KILLED** | `2 failed / 14 passed` |
| A5 | C1 改成无条件绿 | **KILLED** | `2 failed / 14 passed` |
| A6 | `--expect-test` 分支整个不执行 | **KILLED** | `2 failed / 14 passed` |
| A7 | 空名单不再算前提塌 | **KILLED** | `2 failed / 14 passed`（退 2 变退 4，"空读数"被读成"有判决"） |

合计 **7 KILLED / 0 SURVIVED / 0 注入无效**，终局还原复跑 rc=0。

两支脚本（`battery64.py` / `terminal64.py`）**都没入库**，宿主重启即没——
这正是本片要把验签提为常驻件的理由。可重放的最小事实都写死在本篇里：
七臂的 old/new 文本对上表即可原地重建（改的全在 `scripts/closeout_verifier.py` 一处，
每支命中数必须恰好 1、新文本原本必须为 0），终局读数按 §八 的命令形状逐条现跑。
电池自己也错过一次：A4 的锚点缩进写错、命中 0 条，脚本在写盘**之前**就 assert 崩——
源文件未被改动（sha 复原证明），改锚点后重跑，七臂全绿。

## 六、常驻牙（`tests/test_closeout_verifier.py`，16 条）

`--self-test` 被真 spawn / 九格名字面 / 真语料上**与阶段无关的六格**必须全绿 /
名单缺口 == 报告所在提交以来被增改的测试文件（§四 第 4 条那条等号）/
`git status --porcelain` 与 C7 逐次同向 / 锚点传 HEAD 只多点亮那一格 /
整文件抽掉一条常驻用例只点亮名单格而**不**牵连汇总格（显式断言 `counts_counted_from_roster` 仍绿）/
两条替身 nodeid 还长在 `tests/test_packaging.py` 上（AST 反查——替身被删则 C6 永不开火）/
默认从 PROVENANCE 取报告路径那条面（`--self-test` 每臂都显式传 `--report`，不另开用例它就是死码）/
空名单、缺锚点、缺目录、**证据没绑报告**四种都退 2 / 缺席原告 / `--min-tests` 是 opt-in /
退 2 与退 4 不互相折算 / 被绑的那份才是权威（字节不同的未绑副本必须红）/ README 行首镜像。

## 七、量具自己的读数：只报面的 10 个未注册名里，今天 0 条是活缺口

`aipd ctq list` 与 `aipd truth history` 注册之后，`doc_command_census.py` 的只报面仍点到 10 个未注册名字，
逐条查下来全是两类**合法**缺席（不是缺口）：

- 夹具名（8 个）：`aipd ctq zzz-quickref`、`aipd ctq zzz-listy`、`aipd ctq listy`、`aipd ghost cmd`、
  `aipd ghostly cmd`、`aipd ghostspec run`、`aipd ghostci check`、`aipd x`——来自
  `tests/test_doc_command_census.py` 自己生成的幻影（第 62 片那次"注册真名会撞夹具"之后统一改成 `zzz-`/`ghost`）。
- 记录性引述（2 个）：`aipd truth show`（`CHANGELOG.md:1073`、`scripts/doc_command_census.py:4`、
  `docs/audit/DOC_COMMAND_CENSUS_F-DOC-CMD_2026-09-27.md:6`）、`aipd truth ctq`
  （`CHANGELOG.md:1094` 等，记的是"曾经烙进每条记录、已修"的那处幻影）。

**下一步那件小活因此被精确化了**：只报面该把 `tests/` 挡在语料外（夹具名不是文档），
并把"记录性引述"另开一桶；这两件事都是**呈现**问题，不是判据漏了什么。
`aipd truth show` 仍是不存在的命令——这一条被 `doc_command_census.py` 自己当"活例"写在 docstring 里，
不许为了让清单变干净而把它改掉。

## 八、终局读数（由 `tmp/s64/terminal64.py` 从原件现跑生成，不手抄）

跑在绑定提交那棵干净检出 `s64d`（`git rev-parse HEAD` = `41c4b5a5a3ad`，
主树 HEAD = `41c4b5a5a3ad`）；`git status --porcelain` 当时为空，所以 C7 是在**没有自造脏**的树上判的。

- **收尾验签（本片的主角，第一次在自己该绿的树上跑）**：`rc=0`，
  `9 / 9` 格绿、判红 0、前提塌 0；
  读数 `report_entries=2540`、
  `tree_files=207`、`tree_defs=2457`、
  锚点 `a66040520139` ← HEAD `41c4b5a5a3ad`（祖先那一支同向），
  `provenance_binds_report=True`，
  `--expect-test tests/test_closeout_verifier.py` 命中且 passed（报告里那批用例
  **16 条**，与常驻用例数一致）。`--min-tests 2500` 也过了。
  这一行是本片真正的验收：一台每轮替我签字的机器，先要能在签出树上退 0。
- **发布门禁**：`production_release_gate --release-ready --tag v5.6.0` → `rc=0`、
  `release_ready: true`、逐项 `8 / 8` 通过。
- **`audit_repo --strict`**：`rc=1`，恰 **1** 条 ✗（`✗ Provenance source commit mismatch: manifest=a66040520139… …`），
  这条按设计不修——发布锚点不许重锚到 HEAD（见项目记忆「每轮收口的重锚配方」）。
- **两张普查**：`doc_command_census` `rc=0`（现状面 0 缺陷），
  `command_surface_census` `rc=0`。现读的分母：
  `权威面：90 条 argparse 路径（契约 deprecated 别名不并进权威面，由 alias_unregistered 单独核），15 个组名`；`[cli] 74 条`；`低于 cli 档合计：0 条`。
- **签出那一跑的原件**：`exitcode=0`、`collected=2540`、
  `passed=2537`、`skipped=3`、
  其余终态 `{}`、
  用时 `332.5s`、`root=/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS/tmp/s64b`、
  `source_commit=a66040520139`。
- **内容一致性的替身**（C6 依赖的两条）：`[('tests/test_packaging.py::test_release_manifest_hashes_match_disk', 'passed'), ('tests/test_packaging.py::test_source_manifest_hashes_match_disk', 'passed')]` —— 两条都在名单里且 passed，
  这就是"测的就是这棵树"那句话目前的机械形状。

**补记（同一格在最终 HEAD 上重取一次）**：上面那些读数取自绑定提交 `41c4b5a`；
之后本文件又落了两个**只在 `docs/audit/` 内**的提交（不牵动清单哈希），最终 HEAD = `5326bf1`。
在新检出 `tmp/s64e`（`git status --porcelain` 为空）上重跑：
`closeout_verifier --tag v5.6.0 --expect-test tests/test_closeout_verifier.py --min-tests 2500`
→ **rc=0，九格全绿**（`报告 2540 条 / 207 个文件，树 207 个文件 / 2457 个 def`，
`report sha256=a4af8ba0b318` 与证据一致，锚点 `a66040520139` 是 HEAD `5326bf13` 的祖先）；
`pytest tests/test_closeout_verifier.py` → `16 passed`；`--self-test` → `18 条合成读数全部对上`；
`production_release_gate --release-ready --tag v5.6.0` → `rc=0`、`release_ready: true`、
`"passed": true` 计 8 条；`audit_repo --strict` → `rc=1`，恰 1 条 ✗
（`Provenance source commit mismatch: manifest=a66040520139… vs HEAD=5326bf134249…`）。
顺序按 §八 那条纪律：验签先跑，门禁后跑。


## 九、记账脚本自己的一处错（按不 amend 的规矩记在这里）

生成 §八 的那支 `tmp/s64/terminal64.py` 第一版把锚点只钉在**占位句**那一行，
没吃掉它上面那行占位标题 `## 八、终局读数`，于是替换之后文档里出现**两个** §八 标题。
写后的读回断言抓到了"异常"，但那条断言本身也是一处假红：它数的是**子串出现次数**，而我这段正文里用 backtick 引述了那个标题两次，于是 `count == 3`——结构上（按行首数）标题其实只有一个。**标题要按行首数，不能按子串数**（`text-face-gate-forms` 那一族的又一实例）。另一处流程病：这一提的 `git add && git commit` 与写盘脚本之间我用**换行**而不是 `&&` 串起来，于是断言非零退出也没能拦住提交——检查失败与提交动作之间必须有硬门。
定稿改法两条，都是本仓既有纪律的重述而非新规矩：
① 锚点吃掉**整块**占位（标题 + 占位句）；
② 断言移到**写盘之前**，对内存里算好的 `merged` 判，而不是对已落盘的字节判。并且判据形状改成**按行首数标题**（`sum(1 for ln in text.splitlines() if ln.startswith("## 八、")) == 1`），不按子串数——否则文档复述自己一次就把自己判红。
（见技能 `anchor-scripted-doc-patch` 与 `ledger-splice-hygiene`：闸门必须在写之前。）

另记一件与本篇同类但更贵的事：本轮三次把"允许缺哪几格"写死（写成"差额为空"、
写成"除 C7 外全绿"），三次都被**换一棵树**打回（工作树 → 干净签出）。
教训是本片 §四 第 4 条：这类每轮跑一次的机器，输入在配方中途是不变量最少的时刻，
所以"允许缺什么"必须由版本控制现算，或把输入自造到终态形状。
