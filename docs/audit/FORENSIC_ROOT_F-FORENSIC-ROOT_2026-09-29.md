# F-FORENSIC-ROOT 第 96 片：取证脚本的根路径，以及一处被 `[:8]` 截半的读数

日期：2026-09-29。分支 HEAD 起点：`7b1f25c`（本片第 1 项）。

## 一、这一片问的两个问题

1. **读数串被自己截半**（`scripts/closeout_verifier.py` C5）。上一片把锚点改成"跑内实测"
   （`source_commit_measured`）之后，C5 的说明文案里那个标签是
   `f"…是 {anc_src} {anc_ref[:8]} 的祖先"`——`[:8]` 本意只截 commit，但 `anc_src`
   与 `anc_ref` 在同一 f-string 里，读的人分不清哪一段被截。更要紧的是**没有任何常驻用例
   直读这个字符串**：它是给人在门红时看的唯一线索，截错/丢标签在退码上一个字节都不动。
2. **取证脚本把仓库绝对路径写死**。`docs/audit/**.py` 是复算入口，收口之后没人再跑它们；
   一旦换机或换目录，那些 `Path("/Volumes/…/AIPD-OS")` 就指错树——而这件事**没有任何尺子看得见**。

## 二、技术选型（四段，按最高指令第三节）

### 候选清单

| 方案 | 出处（本轮真实打开） |
| --- | --- |
| A `mypy-baseline` 0.7.4 | PyPI JSON `https://pypi.org/pypi/mypy-baseline/json`：`Development Status :: 5 - Production/Stable`、`License :: OSI Approved :: MIT License`、`requires_dist` 里 mypy/pytest 全部挂在 extra 上、最近一次上传 `2026-04-13T08:01:52`；`Source` 指向 `https://github.com/orsinium-labs/mypy-baseline` |
| B `eslint-baseline` 0.4.0 | npm registry `https://registry.npmjs.org/eslint-baseline`：`license: MIT`、`dist-tags.latest = 0.4.0`、`time.modified = 2022-11-25` |
| C 本仓既有形状 `scripts/ci_surface_census.py` | `--emit` 生成名册 + 常驻用例双向对账（第 91 片立起，已在真仓库跑过 5 道判决） |

A 的 README 我按 `raw.githubusercontent.com/kdmurray-labs/...` 猜过一次 URL 得到 404，
按 PyPI JSON 里的 `Source` 字段纠正后只取到元数据；**未亲验其逐行判据实现**，
上表结论仅来自 PyPI/npm 一手元数据与 PyPI 页面摘要（"syncs errors to `mypy-baseline.txt`,
filtering new issues while tracking resolved ones via diffs"）。

### 六维对比

- **功能匹配度**：A/B 记录的是"每条错误一行"的文本基线，判据是**新错误数与已解决数**；
  本面要的是**逐文件布尔事实**（是否写死仓库内路径）+ **豁免类别** + **理由非空** +
  **名册与规则表同源**。A/B 都没有"类别/理由"这一维，也没有"文件消失 ⇒ 该撤"这一极。
- **License 兼容性**：A、B 都是 MIT（已证实，来自 registry 元数据），与本项目 v5.6.0
  自研发布链无冲突。
- **维护活跃度**：A 最近上传 2026-04-13（活跃）；B 最后一次改动 2022-11-25（三年多未动）。
- **安全风险**：A 要引入 mypy 输出解析链与一个外部基线文件；B 要引入 Node 工具链，
  本仓 CI 面没有 Node job。两者都是"为一条判据多带一个运行时"。
- **代码质量**：未亲验（只读了元数据，不据此打分）。
- **适配成本**：A/B 都需要把"取证脚本根路径"这条判据先做成某种 linter 的输出，
  而这条判据的输入是**整仓 `.py` 的字面量扫描 + resolve 比较**，没有现成 linter 产出它。
  自研侧本仓已有同形状件（C），照抄其 emit/对账/自测三段即可。

### 择一决定

**自研，借语义**：借 A/B 共同的核心思路——"基线只列已知项，判据只在新项与漂移项上开火"，
以及 C 的生成/对账双向形状；不引依赖（两条 MIT 工具都解决不了"豁免类别 + 理由 +
文件消失"这三格，引它们等于多带一个运行时换一条用不上的 diff）。
借了什么的落地处：`audit()` 里"未登记 ⇒ 判红 / 已登记但事实不再成立 ⇒ 该撤"这对判决，
就是 A/B 的 new-issue / resolved-issue 两格换了判据单位。

### 落地处

- 量具：`docs/audit/s96/build_forensic_root_register.py`（`facts/audit/emit/render/--self-test`）
- 名册：`docs/audit/FORENSIC_ROOT_REGISTER.json`（`--emit` 生成）
- 常驻牙：`tests/test_forensic_scripts_root.py`（8 条）
- 变异电池：`docs/audit/s96/battery96.py`（Z0 对照 + 14 支撤销臂）
- 第 1 项修复：`scripts/closeout_verifier.py` C5 分支 + `tests/test_closeout_verifier.py::test_c5_detail_names_the_label_and_a_short_head`

## 三、判据与口径

三档事实由 `facts()` 现扫（`docs/audit/**.py`，**排除量具自身**）：

| 档 | 判据 | 处置 |
| --- | --- | --- |
| 仓库内绝对字面量 | `ABS_RE` 抓到引号内的整串绝对路径，`Path.resolve()` 后落在仓库根之内 | 必须被**恰好一条**点名规则接住并登记，否则判红 |
| 仓库外绝对字面量 | 同一批字面量里不落在仓库内、且命中 `HOST_RE`（`/Volumes`、`/Users`、`/home`、`/tmp` 等真挂载根） | **只报不红**：那些路径本身就是当轮读数的来处 |
| `tempfile.*` | 自己造临时目录 | 不算缺陷，也不进只报档（它可重放） |

判决（每一支都在 `--self-test` 里有对应注入臂）：`根路径未点名`、`名册该撤`（两极：
文件还在但已不写死 / 文件没了）、`点名规则不唯一`、`名册缺条目`、`名册规则过期`、
`豁免理由空缺`；前提：`register_missing` ⇒ 退 2，`corpus_empty` ⇒ 退 2。
档位求和恒等于分母（`exempt + derived + unwatched == py_files`）由常驻用例断，
不靠人记数字。

点名规则三条一律带 `/` 左边界，`--emit` 与 `audit()` 共用同一把 `facts()` ⇒
名册不可能被"重新生成一次"洗成比规则表更宽。

## 四、本轮真实踩到的四格（都已按它行动，不是推测）

1. **ASCII 白名单字符类把全部原告漏掉**。第一版 `ABS_RE` 是
   `["'](/(?:Volumes|Users)/[^"']*?)/?["']`；改成通用类时我又写成
   `[A-Za-z0-9_.+~/:-]` —— 本仓根含中文（`AI全链路自研`），于是真语料读数
   `.py 66 个（写死仓库内 0、写死仓库外 0）` **且 `ok: true`**。
   这是第 90 片"识别面漏非 ASCII 路径"同一格的**第二次**。
   修法：`["'](/[^\s"'`\\]{3,})["']`，并新增常驻用例
   `test_the_abs_probe_reaches_a_non_ascii_repo_path`——它先断前提
   （`assert not str(ROOT).isascii()`，仓库根哪天变成纯 ASCII 就响亮报错而不是静默失效），
   再把真根当字面量塞进夹具断"必须判成仓库内"，并断真语料 `inside_hardcoded > 0`。
   电池臂 Z10 就是这条回归（退回 ASCII 白名单 ⇒ 应被抓住）。
2. **点名规则不许用词形猜**——`battery\d+\.py$` 没有左边界时，
   `docs/audit/s84/after_battery84.py`（等电池退出、做三道到货检验的**接收脚本**，
   不是电池）被同一形状吞成豁免。加 `/` 左边界之后它落回"未点名"，于是本轮把它和
   另外三个同类脚本（`s81/e2echeck.py`、`s81/probe6.py`、`s90/probe_z10_survival.py`）
   的仓库根字面量改成 `Path(__file__).resolve().parents[3]`。
   常驻用例 `test_a_name_shape_rule_can_mis_bucket_a_file` 钉这一格，电池臂 Z? 无（
   形状由规则表本身承担，靠 `after_battery1.py` 夹具开火）。
3. **f-string 里嵌同族引号在 py3.9 会吃掉尾引号**。`f'R = Path("{hard / "src"}")\n'`
   在本仓 venv（Python 3.9.6，`.venv/bin/python -V` 现读）上生成的字节是
   `R = Path("/var/…/hard/src)` —— 收尾引号没了，于是那支"必须开火"的臂读到 0 条判决，
   与"量具没牙"在终端上完全同形。修法：注入文本一律由 `json.dumps` 生成引号
   （`_lit()`），并且 `_write()` 落盘前先 `ast.parse`——夹具必须是合法 Python。
4. **自测臂之间不许留残留**。第 5、6 支臂注入的 `s2/terminal2.py` 没清掉，
   第 8 支"只报不红"的对照臂当场读到它的原告。`_clean()` 改成整片
   `shutil.rmtree(docs/audit)` 再重建，并把这条写进函数 docstring。

## 四之二、电池层的一处污染（`derived 0` 那一红逼出来的）

`derive_closeout96.py` 落盘后再跑 `--repo .`，读数从 `derived 17` 变成 `derived 0`
而 `py_files` 是 68、`exempt` 是 50 ⇒ 18 个文件哪一档都没进。常驻用例里那条
**档位求和 == 分母** 的断言当场翻红，于是顺着查：

- 源码是对的（`inspect.getsource` 读到 `buckets["derived"] += 1`）；
- `sys.settrace` 显示那一行**执行了 18 次**，可结果仍是 0 ⇒ 执行的语句不是屏幕上那句；
- 真因：`sys.pycache_prefix = /Users/panhao/Library/Caches/com.apple.python`（macOS 默认），
  电池每支臂用 `python -m py_compile` 做语法检查，于是**变异体**的字节码落进那个目录；
  CPython 的缓存有效性判据是 `(源 mtime 的整秒, 源字节数)`，而 Z14 那支臂把 `+= 1`
  改成 `+= 0` —— 字节数不变、`write_bytes(original)` 又与 `py_compile` 落在同一秒 ⇒
  缓存被判"仍然有效"，之后每一次 import 该文件读的都是那个变异体。
  一手读数：`pyc 记录 mtime/size: 1790646957 20515 / 磁盘源: 1790646957 20515 / 判为有效: True`。

三处修（都已落盘并复跑）：

1. 电池：语法检查改 `ast.parse`（不落字节码）、pytest 子进程带 `-B` 与
   `PYTHONDONTWRITEBYTECODE=1`、开局与每臂复位后各清一次
   `importlib.util.cache_from_source(TOOL)` 与 `__pycache__` 两份路径（`_drop_cache()`）。
2. 常驻用例：`_mod()` 改成 `compile(TOOL.read_text(), …)` + `exec` 载入，
   **不经过任何缓存**——判据读的必须是盘上那份源码。
3. 复位判据从"源文件 sha 相等"补成"电池跑完立刻复算真语料读数"：
   `--repo .` 现读 `exempt 50 / derived 18 / unwatched 0`、`py_files 68`，退 0。

对以往几片的连带判断（**推断，未逐片复验**）：s93/s94 的电池同样用过 `py_compile`，
但那些臂的编辑多数改变了字节数，且常驻用例走 `import`（`scripts/` 下的量具也吃同一套缓存规则）；
只有"同长度 + 同秒还原"这一组合才会静默，因此不声称历轮读数被污染，只把这一格的
防护按上面的形状关掉。

## 四之三、第一次干净签出那一跑的 5 条红：尺子把"仓库内"判成了目录前缀

按配方在 `.wt-s96`（`git worktree add` 出去的 detached HEAD 签出）里跑全量，
`5 failed` —— **红的全是这把新尺自己**：

- `test_register_on_disk_matches_the_rules_table`：名册 50 条，`inside` 算出 0 条；
- `test_real_repo_face_is_live…` / `test_the_abs_probe…` / `test_outside_repo…`：跟着翻；
- `test_ci_face_gates::test_mypy_face_is_clean`：另一处独立缺陷（`spec_from_loader` 返回
  `Optional[ModuleSpec]`，`module_from_spec` 的实参位不收 `None`）——它是我把 `_mod()`
  改成"从源码文本现编译"时引进的，全量是唯一能看见它的地方。

根因不是环境，是**判据的口径**：`repo_inside(root, lit)` 拿"当前这棵树"做前缀比较，
而历轮取证脚本里的字面量指的都是同一座仓库的主工作树 ⇒ 在签出树里它们全都"逃出了仓库",
`facts()` 于是报 0 个原告，而名册那 50 条同时全判「该撤」——一棵合法签出读出一片不存在的缺陷。
这正是记忆里那一族（复算绿线要同时换树和换环境）的又一格：**换树会改变判据的分母**。

修法（`build_forensic_root_register.py`）：新增 `repo_roots(tree)`，用
`git worktree list --porcelain` 取同一座仓库的全部落点（主工作树 + 每个签出），
"仓库内"按**仓库身份**判；git 不在场（合成语料、无 `.git` 的镜像）就退回只认这棵树。
牙齿：常驻用例 `test_a_worktree_checkout_of_the_same_repo_still_counts_as_repo_inside`
真做一次 `git init` + `git worktree add`，既断"主树字面量在另一签出仍算仓库内、
名册零红"，也断反极"`/tmp/other-repo` 这种陌生目录不算"（少了反极，把判据放宽成
"任何绝对路径都算仓库内"也能骗过这一条——电池臂 Z9 就是那一支）。
撤销臂 Z15 把这行改回前缀判 ⇒ 现读 `1 failed`（`退回前缀判 ⇒ 1 failed, 9 deselected`），
复位后文件逐字相等。

一条夹具教训同时记：清理签出用 `git worktree remove` 会被"工作树脏"拒（本条故意往签出里
写了反极那个文件），要 `--force`；这不是判据的事，但少了它用例会在 `finally` 里炸红。

## 五、读数

见 §六（认证那一节由收口脚本回填）。尺子侧现读：

- `--self-test`：15 条臂全部立住（第 15 条是给电池 Z8 存活补的「名册重复 ⇒ 退 2」），退 0。
- 真仓库（`--repo .`，见 `docs/audit/s96/audit-repo.log` 与复跑后的现读）：
  `.py 68 / 写死仓库内 50 / 写死仓库外 21 / 用 tempfile 2`，名册 50 条
  （`battery` 30 条、`terminal` 20 条，`closeout` 规则**现读 0 条命中**——
  历轮的 `derive_closeoutNN.py` 都不带仓库内绝对字面量，所以这一档今天是空词表，
  留着它的理由只有一条：将来真有这种脚本时必须先归类才进得了册），
  `exempt 50 + derived 18 == py_files 68`，`unwatched 0`，退 0。
- 门禁自己抓到的第一笔真原告：新增 `docs/audit/s96/battery96.py` 之后
  `--repo .` 当场退 4、点名 `名册缺条目 docs/audit/s96/battery96.py:40`（现读），
  再 `--emit` 才归零——这条不是合成的，是本片过程中自然发生的。
- `tests/test_forensic_scripts_root.py`：10 passed；`ruff check` 与 `mypy` 各自 0 错
  （mypy 那一处 `Optional[ModuleSpec]` 是第一次干净签出全量抓出来的，见 §四之三）。
- 变异电池 `docs/audit/s96/battery96.py`：Z0 对照绿 + 14 支撤销臂，**KILLED 14/14**
  （第一轮 Z8 存活 ⇒ 补判据与自测各一臂后复跑），收尾 `sha` 与开局相等。
  读数见 `docs/audit/s96/battery96-run.log`（硬化前的那一份）与本轮复跑输出。


## 六、认证读数（两代）

代际命名按"实测树 sha + 报告自记清单指纹"两把键，两代读数不许互换引用。

| 代 | 签出 | 实测 HEAD | 结果 | 自记指纹 | 处置 |
| --- | --- | --- | --- | --- | --- |
| 第一代 | `.wt-s96` | `311be8e` | `5 failed / 2761 passed / 5 skipped`（collected 2771） | `9cffce278e94` | **作废**，留在树里：`docs/audit/s96/report-s96-VOID-tree-311be8e-fp-9cffce278e94.json`；红因见 §四之三（尺子把"仓库内"判成目录前缀）+ mypy 那处 `Optional[ModuleSpec]` |
| 第二代 | `.wt-s96b` | `8ff78f7` | `2767 passed / 0 failed / 5 skipped`，collected **2772**，471.8s | `6df360f50ace` | 有效代，绑进 `PROVENANCE.test_report` |

链上读数（全部为当场所跑，非转述）：

- `PRECHECK OK: 2767 passed / 5 skipped / collected 2772 / 471.8s / fp 6df360f50ace`
- `SKIP 面逐条相同：5 条`（与上一代双向差集为空）
- `BIND_RC=0`，回读 `source_commit=a66040520139`、`test_report=2767p/0f/2772t`、`fp=6df360f50ace`
- 发布门：第一跑 `GATE_RC=2`，未过项只有 `workspace_clean`（两处未提交的收口链派生件文本）；
  按配方"把补记入库 → 只复跑门与验签"处置，复跑 `GATE_RC=0`、`release_ready: True`、`8/8`
  （`docs/audit/s96/gate.json`）
- 收尾验签：第一跑 `CV_RC=4`，唯一红格 `worktree_clean`（同一处未提交件）；复跑 `CV_RC=0`、
  11 格全绿；回收签出后再复算 `-b` 仍 `CV_RC=0`、`checks 11 red []`
- `pinned_source_binding` 那一格的现读文案（就是本片第 1 项修的那条串）：
  「报告与 PROVENANCE 都绑在 a66040520139405095648461f7144d4f00629924，且它是
  **报告实测 HEAD** 8ff78f74 的祖先」⇒ 标签完整、commit 截 8 位、没退到"工作树 HEAD"那一档；
  这条修复不只被合成用例钉住，在生产收口路径上也走通了一次
- 本轮量具侧读数：`--self-test` 15 条臂全立住；电池 Z0 对照绿 + **KILLED 15/15**
  （`docs/audit/s96/battery96-run.log`）；`--repo .` 现读 `.py 68 / 仓库内 50 / 仓库外 21 /
  tempfile 2`，`exempt 50 + derived 18 == 68`、`unwatched 0`（`docs/audit/s96/audit-repo.log`）
- 提交链（`git log --format="%h %s" 29cdb55..HEAD` 现读，倒序）：
  `9426cab` 验签读数入库 → `29c603f` 复跑门读数 → `40e757d` 派生件汉字锚 → `89a4f68` 验签(第一跑)
  → `7cc1ba7` 门(第一跑) → `20ae681` 绑定 → `8ff78f7` 重刷清单 → `b4da2cb` 仓库身份判据
  → `311be8e` 重刷清单(第一代) → `9b7315e` SIM105 → `cb78ba9` 字节码缓存 → `c755e74` 派生件
  → `2a60c5c` 新尺与 9 条牙 → `bff261b` C5 用例修复 → `7b1f25c` C5 标签修复
- 哈希面文件数：`691 → 692`（新增被哈希的文件只有 `tests/test_forensic_scripts_root.py`；
  取证件全部住在被排除的 `docs/audit/`），第二代重刷仍是 692 ⇒ 没有误纳

一处自伤，按原样留着当证据：提交 `40e757d` 的**正文**首行丢了半句——我把 commit message
放在双引号里，而正文写了 `` `s95`→`s96` `` 这样的反引号片段，shell 当场执行它并吐
`command not found: s95`。subject 完整、正文从那一行起被截断。这是记忆里那条
「双引号里的反引号/`$?` 会执行或展开」在同一天第三次命中；不 amend（该提交本身就是这一格的证据），
改用 heredoc 写 message。

未做到 / 未证实（不洗成已做）：

- casadi 的 LGPL 台账仍是 `needs-review` ⇒ 许可证门禁对 `--repo .` 退 4 是**有意的红**，
  发布门不消费它的退码；要转绿得由属主拍板并同步改那条常驻用例（不许放宽判据）。
- "报告整体仍可伪造"这一面未闭合：认证链内部自洽（指纹、锚点、终态、名单、跳过面都对得上），
  但缺**外部见证**（签名/时间戳/第三方存档），属属主侧线下项。
- 第一代那一跑的红只证明了"尺子在签出树里会读错"，**未**验证是否有其它判据也带同类
  目录前缀假设（本仓已知同族：`tests/test_forensic_scripts_parse.py` 走目录枚举、
  历轮电池写死 `REPO` 常量）；这一格留作下一片电池缓存核查时顺带穷举。

## 七、第 99 片：这把尺第一次看见 `.sh`（同一片里 CI 自测补的那两格也记在这）

### 现读的前提（改动前，逐文件打印那一版）

| 读数 | 值 | 怎么来的 |
| --- | --- | --- |
| `docs/audit/**/*.sh` 文件数 | **17** | 目录枚举（不走 `git ls-files`，电池要在无 .git 的副本里也读得出同样的数） |
| 其中带**仓库内**绝对字面量的 | **16** | 全是 `closeoutNN.sh` 的 `R=/Volumes/…`；剩一个 `s83b.sh` 当时带的是引号写法 |
| 只用引号分支（`shell=False`）能读到的 | **0 个文件** | 与两分支那一档同一把 `literals()`，只换参数 |
| 改动前名册 | 52 条（`.py` 面） | `--emit` 前读 |

第 96 片落地时这条尺的枚举面写的是 `*.py`，所以这 16 个文件从未进过分母——
不是"CI 侧只有 1 处"，是**测量工具看不见那种写法**（`R=` 右侧是裸路径，没有引号可锚）。

**同一格里我自己写进仓库的一句读数也一并更正**：工具注释与用例 docstring 都写过
"第一版普查把 17 个 `.sh` 读成 1 个"。那是**去硬编码之前**的现场——当时唯一的引号写法来自
`s83b.sh:5`；把它改成从 `BASH_SOURCE` 推根之后，引号分支在这一面命中 **0** 个文件。
两种说法在终端上长得一样（都叫"看不见"），但"读到 1"会让人以为还剩一条能被引号分支接住，
而真相是这一整面全靠裸赋值分支。按"写下存在性否定前分两侧各数一遍"重跑了一遍逐文件打印的扫描，
两处措辞已同步改。

### 落法（四个面同时改，缺一个就会出现"分母涨了但没人点名"）

1. `SHELL_ABS_RE`：`` (?:^|[\s=(])(/[^\s"'`\\)$]{4,}) ``，多行模式。字符类同样**不用 ASCII 白名单**
   （本仓根含中文，第 90 片那一格在 shell 面上会重犯）。
2. `literals(text, shell=True)` 并跑两条分支并按 (行号, 字面量) 去重。
3. `facts()` 枚举 `*.py` + `*.sh`，每行带 `shell` 标；读数拆 `py_files` / `sh_files` / `script_files`。
4. `closeout` 点名规则 `\.(py)$` → `\.(py|sh)$`；`corpus_empty` 前提文案改 `.py/.sh`。
5. `docs/audit/s83/s83b.sh:5` 去硬编码：`R="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"`，
   `bash -n` rc 0。

### 电池：`docs/audit/s99/battery99.py`，X0 对照 + 7 支臂 KILLED 7/7

| 臂 | 撤掉的东西 | 被抓住 |
| --- | --- | --- |
| X1 | 裸路径分支永不成立 | 6 条 |
| X2 | 分母退回纯 `.py` | 5 条 |
| X3 | 点名规则不再接住 `.sh` | 4 条 |
| X4 | 语料拆档把 `.py` 记成 0 | 1 条 |
| X5 | 把 `s83b.sh` 的仓库根**重新写死** | 4 条 |
| Y1 | CI 量具自报条数不再随注入增长 | 1 条 |
| Y2 | 取证量具同一格（镜像臂） | 1 条 |

- **X5 是本片唯一一支改"被量的树"而不是改尺子的臂**：它同时证明 `.sh` 面不是整片豁免掉、
  以及这轮对 `s83b.sh` 的去硬编码是承重的（改回去门就红）。
- **Y1 是先 SURVIVED 之后补出来的**：第一版常驻断言写成 `marks >= 8`，数的是 `✓立住` 的打印行数；
  而打印在 `_mark()` 里是**无条件**的，工具自报的 `N 条…全部对上` 才跟着注入走。把
  `marks.append(text)` 改成 `pass` ⇒ 自报 0 条、照印 8 行、`marks >= 8` 照绿。补成
  "自报数 == 打印行数"两格同源后 Y1/Y2 各被抓 1 条。取证面同格一并补（Y2 是它的镜像臂）。
- **一支等价变异如实记录、不收录**：`literals()` 里 `if item not in out` 的去重。摘掉它不改变
  任何判决与读数——`inside_hardcoded` 数的是布尔（有没有原告）、名册每文件只取首个行号、
  `audit()` 里 `ins = set(inside)` 本就去重、自测那条断言用集合比。按"臂存活先问变异改得了
  任何可观察输出吗"判为等价变异，不塞进电池凑数。
- **本片已知弱点（用探针实证，不靠推断）**：shell 那条分支**不分注释行**。
  把 `# 见 /Volumes/…/AIPD-OS/docs/audit 这棵树` 这样整行注释直接喂 `literals(text, shell=True)`，
  现读 `[('/Volumes/…/AIPD-OS/docs/audit', 1)]` 且 `repo_inside` 判真 ⇒ 会被算成"写死仓库内"的原告。
  今天语料里 **0 例**（16 个 `.sh` 原告全是真 `R=` 赋值，门是绿的），但第一个在注释里写仓库路径的
  `.sh` 就会假红——引号那一分支天然不会（注释里没有配对引号就匹配不上），所以这是**两条分支作用域不同源**。
  **【第 101 片行内更正】** 上面这句后半是错的：引号分支同样会读注释行，只要那条注释里恰好带配对引号
  （合成反证 `# q = "/Volumes/aa/只在注释里"` 现读命中第 1 行）。所以门加在**两条分支的公共出口**上，
  而不是只补 shell 那一支；"作用域不同源"这一判断成立，错的是我把它当成了"引号分支免疫"。
  修法形状与为什么本轮不改：见任务清单入口「取证门禁 shell 分支会读注释行」。一句话成本账：
  `tests/**` 是被哈希的面，第二代那一跑已在飞，此时补常驻用例等于再开一代（多一次重锚 + 8 分钟全量）；
  只改判据不改用例则违反"判据改动必须带常驻断言"，所以宁可留成带读数的入口项。
  **【第 101 片已按这条入口做完】** 常驻用例 + 电池 + 自测臂一起补，认证见 §八；那条成本账
  当时是真的（第二代在飞），不是拖延的托辞。
- `.sh` 靶的语法门是 `bash -n`（`ast.parse` 只适用 `.py` 靶）；其余沿用第 96/97 片的硬化形状
  （锚点先数、任一 ≠1 整批不跑退 7；sha 落地证明；`-B` + `PYTHONDONTWRITEBYTECODE`；每臂复位清缓存）。

### 技术选型（`.sh` 的赋值右侧怎么读，四段）

候选清单（一手读 PyPI JSON，`https://pypi.org/pypi/<pkg>/json`，2026-09-29 现读）：

1. `tree-sitter-bash` **0.25.1**，`License :: OSI Approved :: MIT License`，`requires_python >=3.10`。
2. `shellcheck-py` **0.11.0.1**，license 字段 MIT，`requires_python >=3.9`，
   summary 自述 "Python wrapper around invoking shellcheck (https://www.shellcheck.net/)"，
   发布物按平台分 wheel：`macosx_10_9_x86_64` / `macosx_11_0_arm64` / `manylinux…` / `win_amd64`。
3. `pygments` **2.20.0**（本机 venv 已装，`pip show` 现读 `Required-by: pytest, rich`）。

六维（只写能核到的）：

| 维度 | tree-sitter-bash | shellcheck-py | pygments | 自研一条正则 |
| --- | --- | --- | --- | --- |
| 功能匹配度 | 高（真解析赋值节点） | 低：它报的是 shell 写法缺陷，不含"绝对路径落在仓库内"这一格 | 中：Bash lexer 给 Token，仍要自己挑赋值右侧 | 中：只覆盖赋值右侧裸路径这一种写法 |
| License | MIT，与本项目 Apache-2.0 兼容 | MIT | BSD-2 | 无新增 |
| 维护活跃度 | 0.23.3 → 0.25.0 → 0.25.1（近期有发版） | 0.9.0.x → 0.11.0.1（跟 shellcheck 版本走） | 活跃 | n/a |
| 安全风险 | 原生扩展（C 语法库） | 携带上游 Haskell 二进制，版本随包锁死 | 纯 Python | 纯 Python |
| 代码质量 | 语法绑定层，需另装 `tree-sitter` 核心 | 薄壳，逻辑在 shellcheck 里 | 成熟库 | 与既有 `ABS_RE` 同形状，一套读法 |
| 适配成本 | **不可用**：本仓 `requires-python = ">=3.9,<3.13"`、venv 实为 3.9.6，包要求 ≥3.10 | 要为 CI 与每台机器装平台 wheel；本机 `lib` 无 shellcheck | 判据会依赖一个**没写进 `[project].dependencies`** 的传递包（默认依赖只有 `jsonschema`） | 一次正则 + 一支反例用例 |

择一决定：**自研那条裸赋值分支（借语义）**——借的是 shell 赋值的语法形状（`NAME=` 右侧无引号、
以空白或 `)` 收尾），不是借实现。三条外部候选各有决定性障碍：tree-sitter-bash 被版本门直接挡死，
shellcheck-py 判的不是这一格且要引原生二进制，pygments 会把门禁接到没声明的传递依赖上
（与"一个配置值只认一个来源"同族的病）。

未亲验：`shellcheck` 自己的规则集没有逐条对官方文档核实，这一维只按 PyPI 的 summary 与
发布物形状（平台分 wheel ⇒ 二进制分发）下结论；`tree-sitter-bash` 的解析能力未实测装跑。

### 读数（改动后现读）

```
取证脚本 90 个（.py 73 / .sh 17；写死仓库内 69、写死仓库外 38、用 tempfile 2），名册 69 条
归属：已豁免 69 / 按 __file__ 推根 21 / 无人守 0
现状面缺陷 0 条
```
档位求和 69 + 21 + 0 = 90 = `corpus.script_files`（常驻用例断这个等式，也断 `sh_files > 0`）。
名册里 `.sh` 16 条、全部走 `closeout` 规则，非 closeout 命名的 `.sh` 原告 **0** 个。

**上面是干净签出那一跑的读数；入库后复算成另一组**——本轮的收口件本身是新原告：
`closeout` 规则扩到 `\.(py|sh)$` 之后，`docs/audit/s99/closeout99.sh` 里那句
`R=/Volumes/…` 立刻被认成"写死仓库内"，尺子判红「名册缺条目 closeout99.sh:10」，
跑一次 `--emit` 才补上登记。现读（收口件在场）：
**92 个**（`.py` 74 / `.sh` 18；写死仓库内 **70**、仓库外 39、tempfile 2），名册 **70** 条，
归属 已豁免 70 / 推根 22 / 无人守 0，求和 70+22+0=92。
⇒ 这一片给尺子加的面，第一次开火开在自己这一轮的产物上——这正是"面加宽必须连自己一起量"
该有的样子，也说明 90/69 与 92/70 不是矛盾而是**同一把尺在两个树状态下的两个真读数**。
（抄在正文里的数只到本轮为止；下一轮以 `--repo .` 的自报行为准。）

`--self-test`：18 条判据读数全部对上，rc 0。
常驻 `tests/test_forensic_scripts_root.py` 10 → **12** 条；`tests/test_ci_surface_census.py` 15 条
（条数未涨，但那第一条自测 spawn 用例加了"自报数 == 打印行数"这一格）。

### 认证读数

（本轮干净签出全量 + 绑定 + 发布门 + 收尾验签的读数在收口后填，见
`docs/audit/s99/closeout99.log`、`docs/audit/s99/gate99.log`、`docs/audit/s99/closeout99.json`。）

### 认证读数（第 99 片自己是两代）

| 代次 | 树（`source_commit_measured`） | 全量 | collected | 清单指纹 | 判定 |
| --- | --- | --- | --- | --- | --- |
| 第一代 `.wt-s99` | `51023121…` | **2780 passed / 0 failed / 5 skipped**（476.0s） | 2785 | `21085171c58e` | 报告本身干净、绑定成功（`BIND_RC=0`），**但收口链判红** |
| 第二代 `.wt-s99b` | `6dcf8bfe…` | **2780 passed / 0 failed / 5 skipped**（423.2s） | 2785 | `a60d80997661` | **认证通过**：绑定 `BIND_RC=0`、发布门 `GATE_RC=0 / release_ready True / 8 项全过`、收尾验签 `CV_RC=0`（11 格全绿），收树后 `-b` 复跑同样 `rc=0 / 11 格全绿` |

两代的 collected 与终态逐字相同（同一份内容重跑），只有清单指纹与实测 HEAD 变了——
这正是"红因是我动了树、不是判据变了"的证据形状。`--expect-test` 三条原告在第二代报告里
逐条 `passed`：`test_forensic_scripts_root.py` 12 条、`test_ci_surface_census.py` 15 条、
`test_forensic_scripts_parse.py` 4 条（第一代报告里也是同样的 12/15/4，用
`report-s99-VOID-…json` 现数核对过）。

第一代那一跑之后我又改了两处**被哈希的面**（`CHANGELOG.md`：把名册 69/语料 90 那组数补成
"收口件入库后 92/70"），于是：

- 发布门 `workspace_clean` 先红（未提交的收口件与文档改动在场）→ 把文档全部入库后复跑，
  红因换成 `source_manifest_zero_diff`；
- 逐条对磁盘复算确认漂移**只有 1 条**（693 条里 CHANGELOG 磁盘 `dcd8c66fa15b` vs 清单
  `ae013542b14d`），其余 692 条一致 ⇒ 不是清单错了，是**跑完之后又动了树**；
- 这时候不能"只重生成清单再绑旧报告"：报告的自记指纹 `21085171c58e` 是对着旧清单算的，
  `release_evidence` 的绑定前预检会按第 84 片那条拒绑（这正是那道闸存在的理由，
  也是它第一次在**我自己这一轮**而不是历史轮上开火）。

⇒ 唯一正确的路是**重锚清单 + 重跑一遍干净全量**，第一代报告按惯例留档
`docs/audit/s99/report-s99-VOID-tree-51023121-fp-21085171c58e.json`（文件名两个键：那一跑的
实测 HEAD 与它自记的清单指纹），并另存那一跑的 stdout `run-s99-gen1.log`。

**这一格真正的教训是工序顺序，不是判据**：第 91/96 片各红过一次同一形状，当时写成
"第一跑必红"；本轮把它读成可修的顺序问题——**所有会被哈希的镜像面（`README.md`、
`CHANGELOG.md`、`scripts/`、`tests/`、`src/`、`docs/security/`）必须在"生成清单 → 全量 → 绑定"
这条链开始之前全部定稿**，认证之后再改这些面就等于开了下一代。本轮把"认证读数写进
CHANGELOG"这一步放在了链中间，所以付了一次 8 分钟重跑。

尺子在这一点上仍持续开火（都开在自己产物上，符合预期）：
`closeout99.sh` 入库 → 92/70；`closeout99b.sh` + `derive_closeout99b.py` 入库 →
**94 个（`.py` 75 / `.sh` 19）、写死仓库内 71、仓库外 40、tempfile 2、名册 71 条，
归属 已豁免 71 / 推根 23 / 无人守 0（71+23+0=94）**，`--emit` 后 0 缺陷、
常驻 16 条（`test_forensic_scripts_root.py` 12 + `test_forensic_scripts_parse.py` 4）全绿。
CHANGELOG 里那组 92/70 是"只含第一代收口件"那个时点的复算，最终入库态以本段的 94/71 为准。

**一处记录面的自我更正**：提交 `3b0fdc2` 的正文把归属拆档写成"71+22…=94"，实际读数是
已豁免 **71** / 推根 **23** / 无人守 0。提交信息按规矩不改（不 amend 已落地提交），
在此以本段为准；这也说明"抄数进正文"这一格无论落在文档还是落在提交信息都会漂——
下一轮起提交信息里不再抄档位拆分，只写工具自报的入口。

## 八、第 101 片：把"注释行不算原告"做成一条门（两条分支一起）

**先更正本片 §七 里我自己写错的一句**（那句是这一片的立项前提，所以先把它改对再动手）：
§七 写的是"引号那一分支天然不会（注释里没有配对引号就匹配不上）"。这句只在
"那条注释里**没有**配对引号"时成立。一手反证（合成串直接喂工具）：

```
literals('# q = "/Volumes/aa/只在注释里"\np = "/Volumes/aa/代码里"\n')
  ⇒ [(1, '/Volumes/aa/只在注释里'), (2, '/Volumes/aa/代码里')]
```

⇒ 两条分支都会把注释行读成原告，**不是只有 shell 分支的盲区**。门因此加在两条分支的公共出口上
（`_scan()` 里对已合并的候选逐条判行首），而不是只补 shell 那一支。

### 选型四段（按最高指令第三节；触发理由：这条门改的是判据的识别面，不是文案）

1. **候选清单**
   - A 文本行首判（自研）：合并候选后按 `^\s*#` 丢，并**把丢掉的条数记进读数**。
   - B 词法权威判：`.py` 用标准库 `tokenize` 的 `COMMENT` token 跨度（[Python `shlex`/`tokenize` 文档](https://docs.python.org/3/library/shlex.html)），
     `.sh` 用 `shlex.shlex(posix=True)` + `commenters="#"`。
   - C 外部 shell 解析器：PyPI `tree-sitter` + `tree-sitter-bash`（MIT）。
2. **六维对比**（功能匹配度／License／维护活跃度／安全／代码质量／适配成本，全部给可核验读数）
   - A：功能刚好覆盖本片要挡的形状；零依赖（License 不新增面）；不涉外部维护；
     无输入执行面（纯文本判）；代码 6 行；适配成本＝0 条读数迁移（现算真语料 `comment_skipped` 合计 **0**）。
   - B：`tokenize` 侧 79/79 个 `.py` 都能解析（0 失败），**但"按行丢"是错的用法**——
     合成例 `p = "/Volumes/a/y"  # "/Volumes/a/z"` 里 `tokenize` 把整行第 2 行标成注释行，
     按行丢会把真赋值一起丢掉（这正是电池 X2 那一臂的形状）；要用对必须按 token 跨度判，成本高于本片需要。
     `shlex` 侧实测**与本尺读数不同的文件 20 个 / 共 20 个 `.sh`** ⇒ 采用 B 等于整体重基线：
     名册 74 条要全部重推，且"测量换写法就换读数"这一格会在同一轮里既改判据又改分母。
     License（PSF/Python stdlib）与安全无问题；适配成本是这里的决定项。
   - C：功能最准（真解析 heredoc、引号、词边界），但要为一条注释门引入原生扩展；
     本仓 `[project].dependencies` 目前只有 `jsonschema>=4.0`（`pygments` 是 pytest/rich 的传递依赖），
     新增编译型依赖会同时动打包面与许可证面（第 92/93 片那两条门禁正是管这个的）⇒ 不成比例。
3. **择一决定：A（自研），借 B 的语义**。借来的是"注释的起点是**词法位置**而不是'这行有没有 `#`'"这一条，
   它直接决定了门的形状是"行首才丢"而不是"整行丢"，并由 X2 那一臂反过来钉住。
   没采用 B 的理由写在上面第二维的实测数上（20/20 不同 ⇒ 重基线），不是偏好。
4. **落地处**：`docs/audit/s96/build_forensic_root_register.py` 的 `COMMENT_LINE_RE`、`_scan()`（新增）、
   `literals()`（改为 `_scan` 的薄包装，签名与旧行为一致，只是不再返回注释行）、
   `facts()` 行读数 `comment_skipped`、`audit()` 的 `corpus["comment_skipped"]`、`render()` 自报那行；
   常驻牙 `tests/test_forensic_scripts_root.py::test_a_line_leading_comment_is_not_a_plaintiff`；
   自测第 19 条 `_mark`；电池 `docs/audit/s101/battery101.py`。

### 读数（一手，2026-09-29）

| 问的东西 | 现算读数 |
| --- | --- |
| 门有没有改变今天任何一条原告 | 全语料 `comment_skipped` 合计 **0**（含 heredoc 体，门按文本判行首）⇒ 0 条被带走 |
| 尾注释那一格今天有没有原告 | **0 处**（量法：`.py` 取 `tokenize` 的 `COMMENT` 起始列、`.sh` 用带引号状态机找第一个词首 `#`，再判字面量起点是否在其后） |
| 名册 | 73 → **74** 条（新增的是本片自己的 `docs/audit/s101/battery101.py`，`battery` 规则接住） |
| 语料 | 99 个文件（`.py` 79 / `.sh` 20），写死仓库内 74、仓库外 41、tempfile 2；归属 74+25+0=99，`--self-test` 19 条、`audit` rc=0 |
| 常驻 | `tests/test_forensic_scripts_root.py` + `tests/test_forensic_scripts_parse.py` **17 passed** |
| 电池 | A0 对照绿 + **KILLED 6 / 6**，无 SURVIVED／BAD-ANCHOR／WRONG-REASON，收尾 sha 与开跑前相同（`e7cfacf91e40`） |

**电池这一轮多出来的一档：判决理由门。** 靶文件就在它自己的语料里，某支臂完全可能把
「名册该撤／根路径未点名」这类**别的判决**弄红——那种红不证明注释门这一格被看见了。
所以本电池除 rc≠0 外还要求"红点落在本片那一臂上"（自测输出里 `行首注释不算原告` 这条标记消失，
或 FAILED 点名 `test_a_line_leading_comment`），并在 A0 阶段先断言这条标记确实在场上——
不先断言，理由门就是恒真的空门（这条正是记忆里"同型正臂"那一格的实例）。

### 还没闭的

- **尾注释那格只量了现实、没改判据**：今天 0 处，所以本轮不动门；下一刀的形状是"按跨度丢"
  （`.py` 走 `tokenize` 的 COMMENT token 区间，`.sh` 至少要带引号状态机找词首 `#`），
  成本是 shell 面的重基线（B 那 20/20）。这一格不进判据、不登记为缺陷，只在 §八 挂着。
- **heredoc 让渡**：`#` 在 heredoc 体里是正文，本门会把它当注释。今天因合计 0 而不成立，
  日后若 `comment_skipped > 0`，必须逐条读原文再判"是注释还是 heredoc 体"，不许按数字放行。
- 认证读数：见本片 `docs/audit/s101/`（收口后填）。


