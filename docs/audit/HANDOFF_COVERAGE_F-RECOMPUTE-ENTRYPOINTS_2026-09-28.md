# HANDOFF-COVERAGE F-RECOMPUTE-ENTRYPOINTS 第 89 片：让渡要可核对、降级不许自己造红、跟踪面读树不读索引

派件来处：第 87 片 §九那张复核表里判为"真缺陷，必修"而第 88 片没动的四条——
#1 空头让渡、#2 降级自己造红、#7 `git ls-files` 读的是索引不是 HEAD、#8 三处"看着是牙其实咬不到"。
四条同一形状：**判据把某件事外包出去（给面 ④、给"存在即合规"的降级、给索引、给一条 `or` 短路），
但没人核对被外包的那一方到底做没做**。所以这一片不新增判据，只把四处外包改成可核对。

## 一、四条各自改了什么

| # | 改前的洞（第 87 片复核原话） | 改后 | 谁在判 |
| --- | --- | --- | --- |
| 1 | `scripts/…` 交给面 ④，而面 ④ 语料不含 `docs/audit/`、`SCRIPT_ROW_RE` 只认行首扁平 ⇒ 取证文档点名的脚本**两把尺都不判** | `audit()` 把面 ④ 的行集 `{(文档, 行号): 基名}` 交给面 ⑤；只有真被那一行收着、且 `path == scripts/<基名>.py` 逐字相等才 `delegated`，其余落回 tracked/untracked/dead | `test_placeholder_and_scripts_forms_are_counted_not_judged`（不免责那一极）＋`test_scripts_row_face4_can_see_is_delegated_not_double_judged`（免责那一极）＋`--self-test` 两条 mark |
| 2 | git 读不出时降级把"磁盘上有"记成 `tracked`，而反向臂的条件是"处处都是 `tracked`" ⇒ 判出「登记册该撤」并附一句从没证实的"文件已入库" | 那一半在 `git_unknown` 树上**只记读数**（`corpus.entry_register_stale_unjudged`）不判红；"再没被引用"那一半与 git 无关，照旧开火 | `test_git_unreadable_tree_does_not_fabricate_stale_removal`（两极同树）＋自测同形臂 |
| 7 | `tracked` 取索引 ⇒ `git add` 未 `commit` 的取证件被当成"干净签出也拿得到" | `tracked_paths()` 改读 `git ls-tree -r HEAD --name-only` | `test_staged_but_uncommitted_entrypoint_is_untracked`（同时把两把尺的差集钉成断言：`ls-files` 看得见、`ls-tree` 看不见）＋自测 |
| 8 | 三处假牙：真仓库用例 `untracked == 0` 没配 `git_unknown` 断言；`startswith("/") or not exists()` 对全绝对路径的册子短路；自测"五档之和 == 总读数"的标记文案声称能抓"把已登记的漏计" | (a) 加 `not st.get("git_unknown")` 与 `entry_git_unknown is False` 两根前提；(b) **删掉**那条短路断言，改由扫描侧的 `dead == dead_registered` 与「无该撤」承担（绝对/相对走同一条路），并把"相对路径那一支由谁负责"写明；(c) 标记文案改成"构造式恒等，真有牙的是逐档期望值与端到端那条" | 同一批真仓库用例；(b) 的相对分支由上面 #2 那条用例与 `test_register_entry_that_resolved_again_or_is_uncited_fires` 负责 |

另外补一条复核没提但同族的：**登记册自己必须在 HEAD 的树里**。它是判据消费的豁免名单，
只躺在工作树里等于"下一轮换一棵干净签出就变成一本空册、所有死链当场重开"——
这正是它要防的那件事发生在自己身上。已加进真仓库用例。

## 二、这条判据闭合后在真仓库开的第一枪，打的是描述它自己的那句话

改完 #1 的当场读数：`✗ 入口不可解析 docs/audit/RECOMPUTE_ENTRYPOINTS_…:246 让人跑 scripts/gone.py`。
那一行是第 87 片复核表里**描述这个洞**的证据格——里面写的是一个虚构假名。
处置取"把该行改成叙述形态"（`python` 与路径不再相邻），不取"登记进死链册"：
登记册的语义是"真有其物、内容不可再生"，把假名登记进去等于往豁免名单里注水，
下一位读者会去找一个从没存在过的文件。

代价要写明，不粉饰：**这条修复让"在文档里举一个虚构的脚本名"变成会被判红的动作**。
现成的逃逸口是有的（`ENTRY_PLACEHOLDER_RE` 认 `X.py`/`NN`/`<>`/`{}` 这类模板形状，
描述判据自己时就该用它们），但它只覆盖模板形状，不覆盖"举个看起来像真名的假名"。
要不要给面 ⑤ 加一个显式的"举例"标记（像 lychee 的 ignore 那样是一处配置而不是一行注释），
排在第 90 片与识别面加宽一起量——加宽识别面本来就会动分母，两件事同一次量才不重复。

## 三、老控制被自己改动打成等价臂（本轮最值得记的一次数）

第 87 片那把电池按"改了 `doc_command_census.py` 就要重跑"的纪律重跑，**X7 SURVIVED**：
它的锚 `if path.startswith("scripts/"):` 在我改完之后命中的是新的**空分支**（`pass`），
"改成 `if False:`" 改不了任何可观察输出 ⇒ 等价臂。
它当时报的"撤掉这档判决没人发现"是**我的改动**造成的，不是判决被撤了没人管——
这两种红在终端上完全同形，只有读变异体的语义才分得开。
修法：把 X7 重定锚到免责的**前提**上（`stem4 = (face4 or {}).get(...)` → `stem4 = None`），
它撤的仍是"回到两处各记一笔红"那个原意 ⇒ 重跑 7/7。
这条正是记忆里"加/改一条在册判据后必须重跑以该文件为靶的老控制"的又一次兑现，
并且补一个它没写的形状：**重跑老控制不只可能红，还可能从"红"退化成"绿得没有理由"**。

## 四、牙与读数（**第一代**：`e2173f8`/`7d2cc22` 那一刻，认证未跑；本轮终局见 §八之二）
- `--self-test`：14 → **17 条 mark**（新增让渡可核对、`git add` 未 commit、降级不造红三条），
  且让渡那两条是**同树两极**（README 行首免责 / 取证文档同名行判红），
  避免"干脆谁都不免责"这种单边改法蒙绿。
- 常驻用例：+4 条（`tests/test_doc_command_census.py` 由 33 → 37 个 `def test_`，
  真仓库那条另加两根前提断言与登记册入库断言）。
- 电池 `docs/audit/s89/battery89.py`：**KILLED 6 / 6**（Y1 索引回退、Y2 不传行集、
  Y3 无条件免责、Y4 去掉降级抑制、Y5 去掉存在即合规、Y6 撤 `core.quotePath=false`），
  对照臂 Y0 原样全绿，
  被改文件收尾复算 sha 与开局一致（`d8f036319303`）。
  Y4/Y5 是同一条例外的两个方向（防漏判 / 防多判），两臂都必须红——缺一半就说明那条纪律只是单边洁癖。
- 真仓库现读（第 89 片这一代）：命令形态 **122** 处 ⇒ 入库可解析 **89** / 未入库 **0** /
  死链 **20**（已登记 20）/ 占位 **8**；`doc_command_census.py` 退码 0、`--self-test` 0。
  与第 88 片那一次的 119 差 3：其中 1 处是本轮新增用例文件里的命令形态、
  2 处是 README 与文档新增的说明行——**分母仍在自己往前走，所以这里只给带轮次的读数**。

## 五、换命令时顺手挖出来的一条假红源：git 会转义非 ASCII 路径

`tracked_paths()` 从 `ls-files` 换成 `ls-tree` 之后，我让复核件专门去问"两条命令的输出形状
在**非 ASCII 路径**上会不会不一样"。我自己建的临时仓库实测（命令＋实际读数）：

```
$ mkdir -p "中文 目录" && : > "中文 目录/x.py" && : > "with space.py" && git add -A && git commit -qm s
$ git ls-tree -r --name-only HEAD
with space.py
"\344\270\255\346\226\207 \347\233\256\345\275\225/x.py"
$ git ls-files                     # 完全一样
with space.py
"\344\270\255\346\226\207 \347\233\256\345\275\225/x.py"
```

三点结论：① **不是换命令带来的**——两条都转义，所以这不是回归，是一个本来就埋着的假红源；
② 空格不触发转义（`with space.py` 原样输出），只有非 ASCII／控制字符会；
③ 本仓当前 1049 条跟踪路径**全是 ASCII**（同一支脚本数出来：non-ascii 0、spaced/quote 0），
所以这格今天不咬人。修法很便宜：加 `-c core.quotePath=false`，
并配一条常驻用例 `test_tracked_face_reads_non_ascii_paths_unescaped`（钉"原样出现"且
"没有任何一条以 `"` 开头"）＋电池臂 Y6（撤掉那个参数就被这条抓住）。

**顺带一条识别面的漏**：面 ⑤ 的正则要求路径字符属于 `[A-Za-z0-9_./-]`，
所以它**根本看不见**非 ASCII 命名的入口文件——这条不在本片修，它属于"识别面加宽"那一批（下一片）。
上面那条用例因此是**直接验 `tracked_paths()`**（修复所在那一层），不绕识别器，
免得读者以为面 ⑤ 已经能判中文文件名。

## 六、老控制的锚点被自己的改动挪掉，这一轮发生两次

同一类事实在同一轮里出现两种表现，都值得记：

1. **退化型**：第 87 片电池 X7 的锚 `if path.startswith("scripts/"):` 在我把该处改成
   "有条件免责 + 一条 `pass` 空分支"之后，命中的是那条空分支 ⇒ 变异改不出任何可观察输出
   ⇒ 报 **SURVIVED**。这不是"判决没牙"，是**臂与判决脱钩**。重定锚到 `stem4` 之后回到 7/7。
2. **作废型**：本轮自己的电池 Y1（`ls-tree` 退回 `ls-files`）在我给同一条调用加
   `-c core.quotePath=false` 之后锚点命中 0 ⇒ 报 **BAD-ANCHOR**（第一次跑就是 4/6 + 1 BAD-ANCHOR），
   重定锚后 6/6。

两者的共同纪律：**改了某条判据所在的代码行，就要重跑所有以该行为锚的控制**——
红的可能是控制本身失效，而不是判决失效；这两种红在电池输出里长得一模一样，
只有读变异体的语义才分得开。（对应记忆：`same-file control revalidation`。）

## 七、未做与下一片

1. **识别面加宽**（§九#5：`/abs/…/.venv/bin/python`、`python3.11`、`python -u x.py`、续行折叠）<!-- aipd-census:example x.py -->
   与 **placeholder 的四个不可达分支 + `..` 消音开关**（§九#6）没做：
   它们改的是"看得见多少"，会直接动死链分母与登记册内容，必须与第二§二那条"举例标记"一起量，
   否则每加一类识别就要当场处理一批新红——那是下一片的正题，不是本片的顺手事。
2. `docs/audit/capability_matrix.md` 仍住在面 ⑤ 的语料里（生成件参与被生成的语料，§九#10 的另一半）。
3. 第 87 片 §九#3（"再没被引用"keyed 在判据自己的可见性上）**本片只写了缓解，没改判决**：
   现在虚构名/叙述改写都会被判红，登记成 §二的代价；真正的修法仍是把那一半降成读数。
4. `--min-tests` 与验签名册要在收尾时按本轮 collected 现读重设（每个 `def test_` 都算一条）。

## 八、认证起跑前的第二轮只读复核（7 笔，全部亲手重验）

派件仍是"只读复核交回的缺陷我逐条重验"，但这一轮多了一条纪律：**复核要在干净签出认证
起跑之前派**，因为它会动 `scripts/` 与 `tests/`（两张 hashed 面），跑完再改就要重跑一整代。
下列每一笔都先自己复现，再改，再让电池或 `--self-test` 反证。

| # | 缺陷 | 一手复现读数 | 落点 |
| --- | --- | --- | --- |
| R1 | 修正片把"在不在 HEAD"补回让渡行时补过头：磁盘上根本没有的脚本也被叫成 `untracked` ⇒ 同一个缺陷被面 ④「脚本缺失」与面 ⑤「入口未入库」各记一笔，且解释文案是假的 | `--self-test` 当场 `AssertionError`：期望 `delegated`、实读 `untracked`（`scripts/zzz_missing_tool.py` 在合成树里不存在） | 条件收窄成"真在磁盘上 ∧ 不在 HEAD"；两极各一支（Y8 撤整格、Y15 只看状态） |
| R2 | 登记册反向臂只看状态名 ⇒ `delegated` 永不等于 `tracked` ⇒ 被面 ④ 收着的在册入口**结构性撤不掉**，与 `REGISTER_RULE` 自己那句"现在又能解析了会反向开火"打架 | 读码：`elif all(s == "tracked" for s in states)`；夹具里那条 `scripts/…` 入库后 `states == ["delegated"]` ⇒ 两条判决都不开火 | 改成问磁盘与 HEAD 的事实；"磁盘上就没有"不许撤（同一条用例的两极） |
| R3 | 面 ⑤ 读到 0 处命令形态时，反向臂把整本册判成「再没被引用」——与 §九#2 同一类"把没读到当没发生" | 合成树（README 无入口、册里两条）⇒ 旧实现两条「该撤」＋`ok=False`＋退 4 | `entry_face_empty` 前提问题 + 整臂免判，退码 2 |
| R4 | 生成侧把缺席信号丢进 `_`：某个 `.md` 读不出时草案删掉那条登记还退 0，同树判决退 2 | `docs/audit/bad.md` 写非 UTF-8 ⇒ `refused == ""`、`written` 少一条、目标文件被改写 | `emit_register` 一并拒写并回填 `problems`/`git_unknown` |
| R5 | `violations` 不去重：一行两处引用同一死链记两笔（"红了几条"≠"要改几处"） | `entry_points` 一手读数：`[("README.md",3,"/tmp/zzz_dup.py","dead"),("README.md",3,"/tmp/zzz_dup.py","dead")]` ⇒ 两条逐字相同的判决 | 按（面,文档,行,写法,**位点**）去重；次数留 `citations` 并进文本面；位点取语料记录序号 ⇒ 登记表一行两条记录仍是两笔 |
| R6 | 一支新用例把一极记在自己账上，而那极它结构上看不见（夹具无 git ⇒ `tracked is None` 短路，删掉 `is_file()` 也照样绿） | 读码即见：`test_scripts_row…` 那棵树没有 `.git` | docstring 改写明该极由 `--self-test` + Y15 负责；电池补 Y15 |
| R7 | 两处"把现状抄成常数"：测试注释里钉着 `1049 条`（现读 1053）、`emit_register` 的说明漏了它现在也走 `script_rows`→`quickref_corpus` | `git ls-tree -r HEAD \| wc -l` = 1053 | 计数改指现读入口；说明按调用链重写 |

### 八之二、第二轮的牙与读数（认证前的最后一组盘上证据）

- `--self-test`：**19 条 mark**（17 → 19：让渡行的入库面、去重与次数各一条）。
- 常驻：`tests/test_doc_command_census.py` **44 个 `def test_`**（HEAD 是 37）。
  HEAD 之后新增 7 条，逐条对应上表：让渡行的入库面（R1）、同一行两处引用记一笔（R5）、
  草案与判决同走一次让渡（§一 #2 的生成侧）、被面 ④ 收着的在册入口仍可撤且**两极**（R2）、
  读到 0 处是前提而不是 N 条「该撤」且**两极**（R3）、一行两条记录是两处要改（R5 的另一极）、
  语料读不全时草案拒写（R4）。
- 电池 `docs/audit/s89/battery89.py`：**KILLED 15 / 15**，Y0 对照全绿，
  被改文件收尾复算 sha 一致（`20f1a0c346c7`）；这一轮新增五臂
  Y11/Y12（反向臂的两极）、Y13（缺席被折成判决）、Y14（生成侧照落盘）、Y15（只看状态名）。
- 老电池 `docs/audit/s87/battery87.py`：第一次重跑 **5/7 + 2 BAD-ANCHOR**，
  重定锚后 **7/7**（sha 同为 `20f1a0c346c7`）——同一文件同一轮第三次被自己挪掉锚点。
- 真仓库现读（`scripts/doc_command_census.py`，退码 0）：命令形态 **122** 处 ⇒
  入库可解析 89 / 未入库 0 / 死链 20（已登记 20）/ 占位 8 / 交给面 ④ 5；登记册 13 条、该撤 0 条；
  三档判红面 86 段 / 97 行 / 220 处。
- 便宜的门全绿后才起跑认证：六把量具 `--self-test` 各退 0；
  `pytest tests/test_changelog_integrity.py tests/test_doc_reference_census.py
  tests/test_absence_claim_census.py tests/test_command_surface_census.py
  tests/test_forensic_scripts_parse.py` ⇒ **60 passed**。

### 八之三、顺手补上的一类空白读者：取证脚本自己没人读

写 R 系列的过程中，`docs/audit/s89/battery89.py` 有一段时间是**语法死**的
（中文字符串里嵌了半角引号 ⇒ `SyntaxError: invalid syntax`），而全套件对此完全绿：

1. `docs/audit/**` 既不 import 也不 collect；
2. `tests/test_exception_hygiene.py` 只扫 `src/aipd_os` 与 `scripts/*.py`，
   且它对 `SyntaxError` 是 `continue`（那把尺问的是空 except，本来就不该被解析失败干扰）。

一份跑不起来的取证脚本比没有更贵——它会以"已配电池"的身份被登记册与 CHANGELOG 引用。
处置：`tests/test_forensic_scripts_parse.py`（`ast.parse` 全部取证 `.py`、`bash -n` 全部 `.sh`，
外加"这两把尺自己会开火"的注入对照与"语料真的递归到了子目录"的前提断言）。
本轮不把它扩成"每条取证脚本都要跑一遍"——那需要给全部脚本逐一建可重放前提
（当时现读 51 个 `.py`、8 个 `.sh`），是独立一轮的活（已记进第 90 片候选）。


## 九、干净签出那一跑（本轮唯一被绑进证件的读数）

| 项 | 读数 |
| --- | --- |
| 树 | detached worktree @ `6696864`（两份清单重锚那一提），路径 `/Volumes/…/.wt-s89`（**在仓库外**） |
| 命令 | `PYTHONPATH=$PWD/src PATH=<repo>/.venv/bin:$PATH AIPD_SOURCE_COMMIT=$(git rev-parse 'v5.6.0^{commit}') .venv/bin/python -m pytest -q --json-report --json-report-file=report-s89.json` |
| 判决 | `2713 passed, 5 skipped`，`exitcode=0`，`summary.collected == len(tests) == 2718`，465.31s |
| 锚点自证 | 报告 `source_commit` == tag 提交 `a660405201394050…`（不是 HEAD）；`source_manifest_fingerprint` = `8956ec96dafe…`，与主树和签出树两份 `SOURCE_MANIFEST.json` 由 `release_fingerprint.py` 现算的值逐字相同（绑定前的探针就是这两个数） |
| 覆盖面 | 跳过面 5 条与上一代**逐条相同**（双向差集为空）：`test_mail_protocol.py` 2 条、`test_research_fulltext_live.py` 2 条、`test_researchstudio_provider.py` 1 条，全是要联网那一类 |
| 本轮原告 | `tests/test_doc_command_census.py` 44 条、`tests/test_forensic_scripts_parse.py` 4 条，全部 collected 且 passed |
| 环境 | `host_load` 起跑 3.99 → 中段邻居会话顶到 26.00（5 s 采样落树外 `.s88-outside/load89-r2.csv`）；`host_cpus=10`。这一跑没有时延类断言红（`tests/test_state_perf_gates.py` 的 5× 比值门在该负载下照绿），所以不需要挪到安静窗口重放 |

两条**只在当场成立、别当成本轮证件**的记录：

1. worktree 第一次是**手敲相对路径**建的，`git worktree add .wt-s89 HEAD` 按 CWD 解析 ⇒
   落在 `AIPD-OS/.wt-s89`，而 `.wt-*` 不在 `.gitignore` 里 ⇒ `git status --short` 立刻出
   `?? .wt-s89/`。它在仓库里的话既进清单遍历又进 `workspace_clean`，两道都会红。
   处置：`git worktree remove --force` 后按绝对路径 `../.wt-s89` 重建，并在此后每一步之前
   `git status --short` 确认主树为空。上表那一跑读的是重建后的树。
2. 第二轮复核之前的第一代那一跑（worktree @ `7d2cc22`，`2702 passed / 5 skipped`）
   因复核交回的 7 笔全落在 hashed 面而**当场过期**：未绑定、未提交，报告随工作树回收消失。
   这里记下它的身份，是为了让"本轮只花了一代认证"这件事可核对——
   派复核件在起跑之前，是这一步省下来的（约 8 分钟一跑）。

## 十、绑定之后的三段读数（一次绑定；两代只有一代存在）

| 段 | 命令形状 | 读数 |
| --- | --- | --- |
| 绑定 | `release_evidence.py --repo . --out . --version 5.6.0 --source-commit <tag SHA> --test-report docs/audit/pytest-report-v5.6.0.json` | `BIND_RC=0`；回读 `source_commit=a66040520139…`、`test_report=2713p/0f/2718t`、`fp=8956ec96dafe`（提交 `8bc6e36`） |
| 发布门 | `production_release_gate.py --release-ready --tag v5.6.0 --test-report … --json-out docs/audit/s89/gate.json`（PATH 带 `.venv/bin`） | `GATE_RC=0`，`release_ready: True`，8/8 项无未过（读数入库于 `3ff6013`） |
| 收尾验签 | `closeout_verifier.py --tag v5.6.0 --expect-test <两条原告> --min-tests 2718` | `CV_RC=0`，11 格全绿：`roster_covers_tree` 树 219 文件 / 2623 个 def ↔ 报告 219 文件 / 2718 条，双向差集为空；`size_ratchet` 2718 ≥ 2718；`worktree_clean` ✓（读数入库于 `2a04794`） |
| 回收签出树后复算 | 同上两条门再各跑一次（`-b` 后缀另起文件，不覆盖绑定那一代） | 发布门 `GATE_B_RC=0`（8/8），验签 `CV_B_RC=0`（11 格全绿，含 `report_fingerprint_matches_disk 8956ec96dafe`）——证明"证件绿"不依赖那棵 worktree 还在 |

三条口径：① `--min-tests` 由脚本从本轮报告现读 `collected=2718` 再传给验签器，
上一代下界 2703 只用作"必须严格大于"的硬断，不当地沿用的数字；
② 跳过面在绑定前逐条比过（5 条双向差集为空），所以 `FAIL=0` 这里不等于覆盖面变了；
③ 本轮**没有**第二代认证：第二轮复核全部在起跑之前落完，那一代（`7d2cc22`，2702/5）
从未绑定，身份只记在 §九 第 2 条。
