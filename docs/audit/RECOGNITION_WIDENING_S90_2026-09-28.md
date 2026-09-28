# 第 90 片：面 ⑤ 识别面加宽 —— 开工前的分母与择一记录

量具：`scripts/doc_command_census.py` 的判红面 ⑤（复算入口可解析性，第 87 片立、第 89 片补强）。
本篇管两件事：**加宽之前先量**（§一）、**加宽会新引入什么**（§二），
以及"举例/虚构名"这一族要不要给显式标记的选型（§三）。

## 一、分母：四族漏形各数一遍（探针 `docs/audit/s90/probe_recognition_widening.py`）

命令：`python docs/audit/s90/probe_recognition_widening.py .`（退 0，只读，不改任何文件）。
现行识别面的 `(文档, 行, 路径)` 三元组去重后 **121** 处（判决面自报 `corpus.entry_points=122`
是**提及数**，同一行两处引用同一脚本时会是两条——第 89 片把这两个面分开记，正是为了这件事）。

| 族 | 形状 | 新增位置 | 其中新死链候选 |
| --- | --- | --- | --- |
| A | 解释器带路径前缀（`/abs/x/.venv/bin/python foo.py` <!-- aipd-census:example foo.py -->） | 1 | 1 |
| B | 版本号解释器（`python3.11 foo.py` <!-- aipd-census:example foo.py -->） | 1 | 1（与 A 同一行） |
| C | 解释器与路径之间夹短旗（`python -u foo.py` <!-- aipd-census:example foo.py -->） | 3 | 3 |
| D | 路径含非 ASCII（`python 脚本/取数.py` <!-- aipd-census:example 脚本/取数.py -->） | **0** | 0 |

### 一之二、D 落地当场把本文判红一次（不是推测，是本轮的第一手读数）

上表的 D 行原本写成一行完整的命令形态示例（`python` 紧跟中文路径），
把字符集加宽之后 `--json` 立刻读出 `dead=21 / dead_registered=20`，
多的那一条就是**本篇自己那一行**：
`docs/audit/RECOGNITION_WIDENING_S90_2026-09-28.md:18  脚本/取数.py  入口不可解析`。
探针在 20:12 报的"D 族 0 命中"并没有错——它测的是**写这篇文档之前**的语料；
文档一落地，分母就往前走了一格。这件事把 §三 的择一从"最好有"顶成"必须同片做完"：
**加宽识别面之后，任何一篇解释这条判据的文档都必须能写"这条命令长什么样"而不被判红。**

处置（临时，且在账上标着）：那一个示例改成"`python` ＋ `中文路径`"两截写法，让树保持绿；
等 §三 选定的显式标记落地后，**把它改回真正的命令形态并加一条常驻用例**，
让"标记能免掉本文这一行"成为该机制自己的语料证据（而不是只靠合成夹具）。
→ **已兑现**：上表 D 行现在就是真正的命令形态，行内带点名式举例注释
（`aipd-census:example` 后面写 `脚本/取数.py`）；A/B/C 三行的 `foo.py` 同理。
这一篇文档因此同时是"记账"和"该机制的真语料"——它红过一次，才被修好的。
而且**这句说明本身也被判红过一次**：第一次把注释原样抄在这里时，
`举例标记失效` 那条判据当场报"这一行点不到 occurrence"（说明文字里没有命令形态），
于是改成现在这种不带注释定界符的写法。失效检查第一次上线就咬到了作者本人，
这是它能算作一条判据而不是一个装饰的证据。

**合计只多 4 个位置，而这 4 个位置里有 2 个是"描述这条判据自己的那句话"**：

- `RECOMPUTE_ENTRYPOINTS_…:250` 的 `scripts/x.py` 与 `/tmp/x.py`（A、B、C 三族都命中同一行）；
- `HANDOFF_COVERAGE_…:107` 的 `x.py`；
- `DRIFT_SCAN_COST_F-DRIFT-4_2026-09-26.md:142` 的 `/tmp/s55/battery.py` ——
  这一条是**真历史工件**（第 55 片写在宿主 `/tmp` 的电池），属"该在册而没在册"。

读数本身就是本片最重要的结论：**加宽的代价不在"新死链一片红"（只有 2 条真的），
而在"虚构假名会被当真死链判"**——那是第 89 片 §二 已经付过一次账的形状，
加宽一次就要再付一次，所以两件事必须同一片做，不能先加宽再把标记推到下一片。

D 族今天 0 命中：识别面加宽非 ASCII 不产生任何现红，但 `tracked_paths()` 那一侧已在
第 89 片修好（`-c core.quotePath=false`），所以字符集这一半是"补对称、防将来"，
配得上它自己的反证夹具（合成树里一条中文名入口）。

## 二、加宽之后必须当场处置的清单（预登记，逐条来自上面的读数）

1. `docs/audit/DRIFT_SCAN_COST_F-DRIFT-4_2026-09-26.md:142` `/tmp/s55/battery.py`
   ⇒ 真死链，进《死链登记册》并写清"第 55 片电池、宿主 /tmp、内容不可再生"。
2. `RECOMPUTE_ENTRYPOINTS_…:250`、`HANDOFF_COVERAGE_…:107` 两处**虚构名**
   ⇒ 由 §三的机制接管，不许靠"把整句改写成叙述"来躲（那是第 89 片 §二 记下的老路，
   每躲一次就少一处可核对的示例）。
3. 识别面加宽后 `delegated`/`placeholder` 两档的计数会动 ⇒ 电池与常驻用例的分档期望值要重算。

## 三、选型（AGENTS.md 第三节：这一片要拍的新机制是"怎么标'这是举例'"）

### 三之一、候选清单（每条都可打开；标注谁亲手读过）

| 候选 | 出处 | 粒度 | 亲验状态 |
| --- | --- | --- | --- |
| lychee 的 `--exclude` / `--exclude-path` / `.lycheeignore` | https://github.com/lycheeverse/lychee/blob/master/README.md | 按 URL 正则 / 按文件；豁免在**侧车文件**里 | 我本人抓 raw README 全文并检索：`lychee-ignore` 这一类**行内指令不存在** |
| mdBook 代码块属性 `rust,ignore` / `no_run` / `compile_fail` | https://rust-lang.github.io/mdBook/format/mdbook.html | 仅**围栏代码块**，属性不跨块传播 | 我本人打开该页确认属性表与"never propagate across blocks" |
| markdownlint 行内注释 `<!-- markdownlint-disable-line MDxxx -->`（另有 `-next-line`、`-file`、`-capture/-restore`） | https://github.com/DavidAnson/markdownlint#rules--aliases | **整行 / 整段**，官方明说不能指定单个 occurrence | 我本人打开该 README 确认四种形式与粒度 |
| Vale `<!-- vale Style.Rule["ACT test"] = NO -->` … `= YES` | https://docs.vale.sh/formats/markdown | 成对开合的**区间**，可点名到规则内某条匹配 | **未亲验**：研究件读的是这页；我本人只在自己抓的 Grafana 文档里见到同形写法（https://grafana.com/docs/writers-toolkit/review/doc-validator/），Vale 官方那页没打开 |
| doctest `# doctest: +SKIP` | https://docs.python.org/3/library/doctest.html#directives | **单个 example**（最接近逐跨），但语义是"文档里的示例不执行" | **未亲验**（研究件报告，我没打开） |

### 三之二、六维对比（只写可核验的结论）

- **功能匹配度**：`+SKIP` 与 Vale 的 `["匹配"]` 最接近"标一处"；markdownlint 只到整行；
  mdBook 只到块；lychee 只到 URL 正则/文件 ⇒ 只有"点名式行内注释 + 自家补一条不变量"能同时满足
  "不吞同行别的引用"与"豁免不会只涨不消"。
- **License**：MIT（markdownlint、Vale）、MPL-2.0（mdBook）、Apache-2.0（lychee）、BSD-2（doctest/Sphinx）
  ——本方案**借语义不引代码**，四种许可都不进依赖闭包，许可面为零风险。
- **维护活跃度**：四者都是活跃项目（研究件报的版本/日期：lychee 0.24.2、mdBook 0.5.4、
  markdownlint v0.41.1、Vale 3.23.0）；这些是**未亲验**的二手读数，只作背景，不进判据。
- **安全风险**：本仓这条判据跑在收口链上，"引入外部 linter 作为依赖"会把网络安装面拉进认证路径；
  自研一条正则不新增执行面。
- **代码质量**：外部工具的规则表达力都强于本面，但它们判的对象不是"干净签出里这条入口能不能跑"，
  接进来也只能当第二把尺，取代不了 `git ls-tree` 那一层。
- **适配成本**：引 lychee ⇒ 要为"脚本路径"写一套 URL 映射；引 markdownlint/Vale ⇒ 要接 node/二进制
  并把它们的输出并进现有退码协议；借语义 ⇒ 一个 `ENTRY_EXAMPLE_RE` + 两个函数
  （`example_names_on` / `stale_example_markers`），已落在 `scripts/doc_command_census.py`。

### 三之三、择一决定：**借语义**——不引依赖，也不新造形状

采用"行内 HTML 注释 + 点名参数"的形状（markdownlint 的 ergonomics + Vale 的点名语义），
并**加上两者都没有的一条自家不变量**：点了名却在同一行找不到 occurrence ⇒ 判「举例标记失效」。
为什么不直接照抄任一家：markdownlint 吞整行（后来人往同一行加真死链会跟着免判）、
Vale 需要成对开合且要复述匹配文本、`+SKIP` 粒度对但语义是"不执行"而不是"这是虚构"、
lychee 的豁免在侧车文件里——那正是第 87 片选登记册时**已经付过一次账**的形状
（豁免越攒越长、没人知道哪条还在做事）。
"点名 + 点不到就红"是对那个已知病灶的直接回应，也是本片唯一真正自研的部分。

### 三之四、落地处

- `scripts/doc_command_census.py`：`ENTRY_EXAMPLE_RE`、`example_names_on()`、`stale_example_markers()`、
  `entry_points()` 的 `example` 档、`audit()` 的「举例标记失效」判决、`render()` 的
  `点名举例 / 失效标记` 读数、`REGISTER_RULE` 的六档措辞。
- 用例：`tests/test_doc_command_census.py::test_named_example_marker_spares_only_the_named_occurrence`、
  `--self-test` 里 doc.md 的第 8/9 行（同树两极）。
- 镜像：`README.md` 面 ⑤ 那一段（六档 + 加宽 + 点名注释）、CHANGELOG v5.51。
- 本文 §一之二 与 §五 的读数由这套机制吸收；被点名的 7 处虚构名全部保留命令形态。

## 四、生成件住在语料里这一格：择一已做（进语料），理由是现读的

第 87 片 §九#10 留的问题是"`docs/audit/capability_matrix.md` 由登记表生成，却又住在
面 ⑤ 的语料里 ⇒ 生成件参与被生成的语料"。两个候选处置：**把它踢出语料**，或
**留在语料、把漂移记成账**。择一取后者，依据是现读：

```
$ .venv/bin/python -c "…按 ENTRY_LINE_RE 扫 docs/audit/capability_matrix.md…"
entry hits in matrix: 7        # 第 49-56 行
  scripts/research/source_worker.py / search_papers.py / fetch_fulltexts.py
  scripts/research/postprocess.py（两行）/ scripts/claim_gate.py …
template-ish lines: 2          # 第 50 行的 `…_by_{arxiv,…}.py`、第 72 行的 `src/…/{composer,renderer}.py`
```

那 7 处命中里有 **6 处指向真存在的脚本**，也就是说这本生成册目前**正在为分母供内容**：
把它踢出语料不会让判据更干净，只会让这 6 条入口少一个读者
（它们改名的时候就没人判红了）。漂移的代价反过来是可承受的：登记表加一行 ⇒
生成册多一行 ⇒ `corpus.entry_points` 往前走一格，而这正是判据想要的方向。
第 50 行那个 `{arxiv,…}` 模板形态**不产生任何读数**（既不计占位也不判），
那是 §九#6"placeholder 分支不可达"的证据，归 §二 第 3 条一起修，
不在这一格里靠"排除文件"混过去。

配套口径：生成件与语料同体这件事，镜像清单已经记在
`~/.qoder-cn/projects/.../memory/project-aipd-command-surface-mirrors.md`，
每轮改登记表要同批改的清单以那份为准；本节只负责"面 ⑤ 这一面留不留它"这一问。

## 五、placeholder 那一档的可达性复测（并更正第 87 片 §九#6 的一处归因）

同一把探针（`ENTRY_PLACEHOLDER_RE` 的 7 个分支逐个喂它自己需要的最小样本，
再看捕获类 `ENTRY_PATH_CHARS` 容不容得下）：

| 分支 | 需要的样本 | 能被捕获吗 | 可达性 |
| --- | --- | --- | --- |
| `X\.(py\|sh)$` | `fooX.py` | 是 | 可达 |
| `NN` | `aNNb.py` | 是 | 可达 |
| `\.\.` | `a/../b.py` | 是 | 可达 |
| `…` | `a…b.py` | **否** | 不可达 |
| `[<>{}*]` | `a{b}.py` | **否** | 不可达 |
| `\$\{` | `${A}.py` | **否** | 不可达 |
| `s\d+\.\.s` | `s11..s12.py` | 是 | 可达 |

⇒ 不可达的是 **3 个分支键**（`…`、`[<>{}*]`、`\$\{`）。第 87 片原记"4 个不可达"
按的是符号个数（`…` / `<` / `}` / `${` / `*` 里数出四个），不是分支键个数——
两种数法都还能自圆，但**登记行里的"4"没有指明数的是哪一个**，
本轮按"3 个分支键"更正并写明口径。

同一份复测里更值钱的一条**归因更正**：§九#6 说
"`capability_matrix.md:50` 那个 `{arxiv,…}` 模板形态连一行读数都不产生，
因为捕获类容不下这些字符"。前半句是真（该行确实 0 行），**后半句的因果是错的**：
把捕获类加宽成含 `{ } $ < > * …` 之后再扫全仓，新增命中 **0** 处——
那一行之所以不出行，是因为能力矩阵表格里那一格写的是**裸路径**（没有解释器前缀），
而面 ⑤ 的识别形状要求 `<解释器> 空格 路径`。裸路径列不在这一面的射程内，
这是**设计边界**，不是字符集缺陷；修捕获类不会让它出行。
处置：字符集仍然加宽（让那 3 个分支变成真可达、并为将来"带解释器的模板写法"预备），
但把"矩阵表格里那一列没人读"另记为一条事实（它归第 60 片那条命令面镜像清单管）。

`..` 那一支的复测：今天 8 条 placeholder 读数里有 **2 条**是同一行
（`RECOMPUTE_ENTRYPOINTS_…:251`，一行两处），路径是 `scripts/a/../gone.py`——
**归一化**（`posixpath.normpath`）之后它是 `scripts/gone.py`，仓库里没有，
也就是说这一条现在正被 `..` 这个"消音开关"免判着。
把它改成"先归一化再判存在性"是严格的改进，但代价当场可见：
那一句正是**描述这个洞的原文**里的虚构假名 ⇒ 与 §一之二 同一族，
必须等 §三 的标记机制落地才能一起做，否则就是把树改红。
