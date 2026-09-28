# F-RECOMPUTE-ENTRYPOINTS 第 87 片：文档里的"复算入口"第一次有人判它落不落得了地

## 一、入口：一次 worktree 分诊量出的不是"要不要清理"，而是一整类主张

第 86 片收口后清账，把 `docs/audit/*.md` + `CHANGELOG.md` + `README.md` 里所有
`tmp/sNN/...` 形态的路径片段做一次精确求差（正则 `tmp/s[0-9]+[A-Za-z0-9_./-]*`，
按整路径匹配而不是按基名——第一遍我按基名数，`__init__.py`/`out.md` 这类重名把读数撑歪）。
读数写在 `docs/audit/WORKTREE_INVENTORY_2026-09-28.md` §六，摘三行：

- 被引用的路径片段 **144** 个；磁盘上还在的 **5** 个，且这 5 个在仓库内都没有同名入库件；
- **122** 个指向的工件从没入过库、内容确已不可再生（第 30—64 片把电池脚本、探针日志、
  `state.db` 写在 `tmp/` 下；第 63 片那份验签脚本被宿主重启清掉是同一形状，
  见 `docs/audit/CLOSEOUT_VERIFIER_F-CLOSEOUT-VERIFY_2026-09-27.md:4-5`）；
- **6** 个是"文件没了但库内有同名件"——历轮自己迁过 `docs/audit/sNN/`，那是陈旧指针而不是内容丢失。

所以真正的缺口不是"磁盘占了多少"，而是：**"复算入口"这一类主张从来没有一面尺子看着**。
第 63 片造 `closeout_verifier` 只治了"验签脚本"那一种；文档正文里
`python /tmp/s46/battery.py  # 电池（10 条）` 这种句子——它是给下一个读者用的操作说明——
今天没人判它可不可执行。

## 一之二、选型（本轮真正要拍的是：引依赖、借语义，还是自研）

三个候选都是本轮**亲自打开**的来源，读数取自页面本身：

| 候选 | 功能匹配度 | License | 维护活跃度 | 安全风险 | 代码质量 | 适配成本 |
| --- | --- | --- | --- | --- | --- | --- |
| **lychee**（`github.com/lycheeverse/lychee`，raw README 实读） | 检的是**链接**（http/文件 URL），相对链接按 `--base-url` 解析；不解析代码块里的 shell 命令 | 双许可 "Apache License, Version 2.0" 或 "MIT license"（README 原文） | README 给出 `--exclude`、`--exclude-path`、`.lycheeignore` 三个成形的排除面 | 外部二进制 + 网络探测，本仓取证链不需要出网 | Rust 单一 CLI，配置面稳定 | 本机 `which lychee` → **lychee not found**，要先装 Rust 二进制 |
| **mdBook**（`rust-lang.github.io/mdBook/format/mdbook.html` 实读） | 唯一真正"跑文档里的例子"的先例：标记 `ignore` / `no_run` / `compile_fail`，`mdbook test` 编译但不执行 `no_run` | MPL（本项目不引依赖，未逐项核对——不影响判决） | mdBook 是 Rust 官方文档工具，长期维护 | 若真执行代码块，本仓的收口链会**再跑一次绑定/全量**，风险不可接受 | 成熟 | 文档不是 mdBook 目录结构（无 `SUMMARY.md`），要重排整个 `docs/` |
| **markdown-link-check**（`github.com/tcort/markdown-link-check` 实读） | 配置项 `ignorePatterns` / `replacementPatterns` / `aliveStatusCodes`；页面自述**只检 markdown 链接**，不含代码块命令 | ISC | 以 npm 包分发 | Node 依赖树进入一个以"发布证据"为产品物的仓库 | 单一用途，实现薄 | 本机无 Node 侧门禁；CI 只装 Python |

**择一决定：自研，借语义，不引依赖。** 理由两句：
① 三者判的对象都不是我要判的东西——我要判的是「文档给人抄的那行命令，其路径在干净签出里存不存在」，
链接器看不见它（它不是链接），mdBook 只在"真执行"的框架里看它（本仓一旦执行就会重跑绑定）；
② 关键谓词 `git ls-files`（"文件在本地但没入库"）是版本库状态，三个外部工具都没有这个概念。
借来的两样落到实现里：lychee 的"豁免是一份**显式配置文件**而不是行内注释"
（→ `docs/audit/RECOMPUTE_ENTRYPOINT_REGISTER.json`，面 ⑤ 只认这本册子）、
mdBook 的"不跑要**标出来**"（→ `placeholder` / `delegated` 两档只数不判，并在读数里点名），
`markdown-link-check` 的 `projectBase`（→ 解析根只有仓库根，不跟着 `cwd` 漂）。

## 二、判据形状：五档归属，其中两档是"刻意不判"

`scripts/doc_command_census.py` 的面 ⑤（函数 `entry_points` / `entry_corpus` / `load_entry_register`）：

| 档 | 含义 | 判决 |
| --- | --- | --- |
| `tracked` | 路径在仓库内且 `git ls-files` 列它 | 合规 |
| `untracked` | 在仓库内、磁盘上就在，但没入库 | **判红**「入口未入库」 |
| `dead` | 绝对路径，或仓库内不存在 | 在册则只记；不在册 **判红**「入口不可解析」 |
| `delegated` | `scripts/…` | 只数不判——存在性与旗子归第 85 片的面 ④ |
| `placeholder` | `scripts/X.py`、`sNN`、`..`、尖括号、通配、`${}` | 只数不判 |

三条不那么显然的：

1. **绝对路径必须无条件算死链**。`Path(root) / "/tmp/x.py"` 在 pathlib 里会丢掉 `root`，
   于是"这台机器 `/tmp` 恰好还留着那个文件"会被读成可解析——判据要按**干净签出**说话。
   这一支第一版没有任何用例能证明它在做事（见 §五 X1 臂）。
2. **`git ls-files` 读不出时退成"存在即合规"并记 `git_unknown`**，不记 problem。
   写成 problem 会让合成语料与无 `.git` 的镜像整片 rc=2；把"不知道"折成违规或折成通过都错。
3. **`scripts/…` 交出去**：同一缺陷在两处各记一笔红会把"还剩几处"读歪
   （第 85 片那面已经把 `scripts/zzz_missing_tool.py` 判成「脚本缺失」了）。

登记册要**双向**对账：只核"引用的都在册"看不见"在册但已无用"。
两个反向判决各一条：条目现在处处可解析（文件已入库）⇒「该撤」；条目再没被任何文档引用 ⇒「该撤」。

## 三、立条前先量分母（这一格不是橡皮章，也不是自我伤害）

**立条当时的时点读数**（写本文与 README 说明之前，`python scripts/doc_command_census.py`）：
命令形态 **107** 处 ⇒ `tracked` 5 / `untracked` 0 / `dead` **18**（已登记 18）/
`placeholder` 5 / `delegated` 79；登记册 13 条（18 处引用按路径去重成 13 条）。

- **18 处死链全是** `/tmp/…battery.py`、`/tmp/mutate_*.py` 这类历轮写在宿主 `/tmp` 的电池与探针
  ⇒ 若不先量就直接上线，新尺第一跑就报 18 条红，而这些**修不了**（内容已不可再生），
  只能逐条登记并写明"为什么不再可复算"。
- **占位那一档是被自测逼出来的**：第一版没写免判分支时，`--self-test` 立刻把
  "描述判据自己的写法"（README 里那句 `python scripts/X.py`）读成缺陷。
  **新尺必须先证明它不咬自己的说明书。**

### 三之二、本节自己就是一次测量事故：本文属于它要判的语料

面 ⑤ 的语料含 `docs/audit/*.md`，而取证文档里有「复算入口」小节——
**写下上面这段读数的动作本身就会改动读数**。本轮实测到的漂移：
本文 §一 引了一句 `python /tmp/s46/battery.py`（该路径**早已在册**）⇒ `dead` 从 18 涨，
`dead_registered` 同步涨，违规仍是 **0**；§九 写了 `python docs/audit/s87/battery87.py`
（已提交）⇒ `tracked` 涨。写到本节末尾时重跑，总数与分档又变成
`113 / tracked 7 / dead 20 / placeholder 5`——**所以本文不再给"当前值"**，
要看现行读数就跑 §九 那条命令。

这不是判据的缺陷，是它的**用法约束**：任何把具体数字抄进 `docs/audit/*.md` 的做法，
对这一面都不成立。因此常驻用例钉的全是**关系**而非数：
`dead == dead_registered > 0`、`untracked == 0`、`tracked/delegated/placeholder > 0`、
四档之和 == 入口总读数、登记册每条都仍不可解析且都带 note。
其中"四档之和 == 总数"就是防漂移的那根：漏计任何一档（包括把已登记的漏掉）当场红。

## 四、自测与常驻的两极

- `--self-test` 的运行时标记从 **9** 条加到 **14** 条（`git show HEAD:… | --self-test` 现读的 9，
  与本版 14 各跑一次；新增 5 条都是面 ⑤ 的）——
  六格归属各落一位、端到端"未入库开火／未登记死链开火／已登记的不开火／两条『该撤』各按自己的理由开火／
  `scripts/` 不重复判"、分母自证（四档之和 == 入口总读数，登记的另记一格）、
  `git` 读不出时降级、没有登记册＝空册即全判红。
  合成语料里的 `git init` + 只提交一半是**真跑 `git ls-files`**，不是测试注入的集合。
- 常驻用例 `tests/test_doc_command_census.py` 从 23 条加到 **30** 条（+7）：
  `test_dead_entrypoint_without_register_fires`（必开火）、
  `test_register_is_load_bearing_for_the_same_line`（同树两趟：先证红，再登记，证它承重）、
  `test_register_entry_that_resolved_again_or_is_uncited_fires`（两条「该撤」各有理由）、
  `test_untracked_entrypoint_fires_only_when_git_is_readable`（降级与开火两极）、
  `test_placeholder_and_scripts_forms_are_counted_not_judged`、
  `test_absolute_path_is_dead_even_when_that_file_exists`（X1 的唯一反证）、
  `test_real_repo_entry_face_is_live_and_every_dead_link_is_registered`（真仓库：`dead == dead_registered > 0`、
  0 条未登记、每条登记都写了 note 且确实不可解析，外加一把**比判据更宽的独立尺**
  ——不看有没有解释器前缀的 `/tmp/*.py` 全文匹配——要求登记册落在它的真子集里且真子集非空）。

## 五、电池：7 臂，其中一臂第一版真的没牙

`docs/audit/s87/battery87.py`（每臂锚点唯一、变异后可编译的体检先跑；落地证明用 sha；归因打用例名）：

```
原文件 sha=2a43da69dd24
[CONTROL OK] X0 原样全绿
[KILLED]   X1-absolute-not-dead（绝对路径不再算死链）被抓住：tests/test_doc_command_census.py::test_absolute_path_is_dead_even_when_that_file_exists
[KILLED]   X2-register-not-consumed（登记册不再被消费（豁免成空转））被抓住：…self_test…; …real_repo_clean…
[KILLED]   X3-no-stale-register-check（登记册单向：撤掉「该撤」那一半）被抓住：…self_test…; …register_entry_that_resolved…
[KILLED]   X4-placeholder-check-dropped（模板形态不再免判）被抓住：…self_test…; …placeholder_and_scripts_forms…
[KILLED]   X5-untracked-not-judged（「没入库」这一档被撤）被抓住：…self_test…; …untracked_entrypoint_fires…
[KILLED]   X6-git-unknown-becomes-guilty（git 读不出时折成违规）被抓住：…self_test…; …untracked_entrypoint_fires…
[KILLED]   X7-scripts-delegated-dropped（`scripts/…` 又回到两处各记一笔红）被抓住：…self_test…; …script_rows_fire…
合计 KILLED 7 / 7；其余按判决分类：无
收尾复算 sha=2a43da69dd24（应等于 2a43da69dd24）
```

**X1 第一版是 SURVIVED**，而且这不是"测试没写好"那么简单：撤掉那三支 `if path.startswith("/")`
后判决**不变**，因为 pathlib 的 `/` 组合会把绝对路径顶掉根，而夹具里的 `/tmp/zzz_*.py`
本来就不存在，两条路径都落进 `dead`。也就是说这支臂测的是一台"`/tmp` 里还留着那个文件"的机器，
而我的夹具里没有那种机器。补的 fixture 是**在 tmp 目录下真造一个文件**再用它的绝对路径引用，
于是"存在即合规（错）"与"绝对路径一律死链（对）"第一次在行为上分叉，X1 才由存活转成被杀。
这与第 84 片记过的"注入必须落在守卫的时钟框里"是同一类：变异臂开不开火取决于夹具能不能造出那条分支的存在条件。

## 六、本轮我自己的三个操作错误（现场留在原处，不在这里粉饰）

见 `docs/audit/WORKTREE_INVENTORY_2026-09-28.md` §六末尾：
① 抢救 `tmp/` 取证件时按基名压平目的位且没比 `git ls-files`，覆盖 15 个已入库脚本；
② 拿 `Path.glob("docs/audit/**/<基名>")` 当"是否已入库"的尺，把"6 个有同名件"读成"一个都没有"；
③ 回退时按 `git status` 的未跟踪状态整片删，连带删掉刚写的摘要件（源已回收，只能重建窄一点的版本）。
面 ⑤ 的 `untracked` 那一档正是②③的可执行版本：以后写完取证件没提交，尺子会自己说。

## 七、镜像清单（本轮实际改到的每一处）

| 位置 | 改了什么 |
| --- | --- |
| `scripts/doc_command_census.py` | 面 ⑤ 的四个函数、`audit()` 接线与 `entry_states` 读数、`render()` 三行判决文案、`--emit-register` |
| `scripts/doc_command_census.py` 模块 docstring | 补上第 85 片漏写的面 ④，新增面 ⑤ 段；把两处**抄在文中的旧分母**（"88 条路径"、"1389/1012/73%"）改成"由 `--json` 现读"并标所属轮次 |
| `tests/test_doc_command_census.py` | +7 条常驻用例（含一把比判据宽的独立尺）；补 `import re` |
| `docs/audit/RECOMPUTE_ENTRYPOINT_REGISTER.json` | 新建，13 条死链逐条带 `cited_by` 与 note |
| `README.md` | 量具目录里 `doc_command_census` 那块加面 ⑤ 的说明与分母口径 |
| `CHANGELOG.md` | v5.48 条目 |
| `docs/audit/s87/battery87.py` + `battery87.log` | 电池与执行读数（`.log` 被 `.gitignore` 第 43 行挡着 ⇒ 入库要 `git add -f`） |
| 项目记忆 `project-aipd-command-surface-mirrors.md` | 第 87 片入口项闭合、复算入口普查读数 |

## 八、遗留（开着，不在本轮顺手做）

0. **CHANGELOG v5.48 里那句"真仓库现读：命令形态 107 处"要改措辞**：那是**立条时点**的读数，
   本文 §三之二 证明了这类数字会随本文自身改动而漂。README 那块写的是"上线前量的分母"，
   措辞已经正确；CHANGELOG 这格得改成"立条时点读数"。
   本轮没改是因为 `CHANGELOG.md` 参与发布哈希，而收口链的全量正在跑——
   改它会让刚测完那份报告与清单不同源（第 84 片为此烧过一整个全量）。
   **下一轮动 hashed 文件时顺手改这一格**，并与 §三之二 一起读。
1. **叙述型指针：量过了，结论是不做门**（本轮从"先量再说"推进到"量完定案"）。
   把 `CHANGELOG.md` + `docs/**` + `references/**` 里所有像文件路径的 token
   （正则 `[A-Za-z0-9_.\-/]+\.(py|sh|json|db|log|md|csv|txt)`，前后加边界）按归属分桶：

   | 桶 | 处数 | 说明 |
   | --- | --- | --- |
   | 仓库内可解析 | 2569 | 绝大多数指针本来就是对的 |
   | `scripts/…` | 462 | 归面 ④ |
   | 裸文件名／生成物（如 `.evidence.json`） | 2292 | 说明这条正则**本身就太宽** |
   | `tmp/`、`/tmp/` 形态 | 190 | 本轮普查那一批；面 ⑤ 只登记了其中的命令形态 |
   | 带仓库前缀却解析不到 | 15 | 其中模板／区间形态 4 处（`src/...py`、`docs/audit/sNN/batteryNN.py`）， |
   | | | 剩下 **11 处逐条读过，全部是合法写法** |

   那 11 处为什么一条都不能判红（逐例，带 `文件:行`）：
   `docs/audit/C6_COVERAGE_CENSUS_F-C6-01_2026-09-25.md:22` 写
   `docs/audit/c6_coverage.json` 正是为了说"这份 JSON **故意不存**，存了就有两处会各自漂"；
   `docs/audit/PRODUCER_COUNT_F-PRODUCER-COUNT_2026-09-27.md:77`、
   `docs/audit/CLOSEOUT_VERIFIER_F-CLOSEOUT-VERIFY_2026-09-27.md:62`、
   `docs/audit/ASSEMBLY_PDF_IMAGE_F-ASSEMBLY-PDF-IMAGE_2026-09-27.md:390` 与 `CHANGELOG.md:1261` 里的
   `docs/x.md`、`tests/test_x.py`、`tests/test_a.py` 是**用例夹具的假想名**；
   `docs/audit/TRUTH_DRIFT_F-DRIFT_2026-09-26.md:99` 的 `src/nope/gone.py` 是反证臂的注入路径；
   `docs/audit/SPEC_FACES_F-DRIFT-5_2026-09-27.md:24` 的 `docs/operator-manual/architecture.md`
   属于 **Argo CD 上游仓库**，不是本仓；`src/state/db.py`
   （`IMPRESSION_POST_REFACTOR_2026-08-14.md:60`、`RELEASE_FIX_CLOSURE_2026-08-14.md:22`）与
   `CHANGELOG.md:3292` 的 `tests/test_visual_audit.py` 是**当时那次审计/那次交付的原文**；
   `docs/audit/GATE_REQUIREMENTS_TABLE_F-C6_2026-09-25.md:112` 那句整段就在讲
   "一个不存在的路径把一次全量整体打断"这个缺陷。
   ⇒ 判红面会 100% 打在"把设计、夹具名、上游路径和历史现场写下来"这件事上，
   与第 85 片那条"宽判据 40 处假阳性 ⇒ 不做门并登记度量"是同一种判决。
   **留作度量的部分**：那 190 处 `tmp/` 形态里，命令形态 18 处已由登记册管住，
   叙述形态仍无人管——真要治，形状不是"路径必须存在"，而是
   **给历轮取证文档的「复算入口」小节加一份 machine-readable 的入口清单**
   （每条：小节、命令、落位），让"这一节还能不能照跑"变成对清单的核对，而不是对全文正则的猜测。
2. ~~**登记册的 note 目前是同一句话**~~ —— **本轮已闭合**（`0c75c42`）：
   13 条各写成「哪一片的什么量具 / 当时判决读数 / 抄在哪篇文档哪一行」三件齐，
   内容取自本轮普查从那些文档原文读出的数字（12、14、8、6、6、4、5、10、9、21 条臂，
   DXF 字节漂移 13170 行仅 2 行不同，撞键修前 1 条修后 2 条等），并加了 `note_semantics`
   说明为什么"非空"不等于"有信息量"。**残留的那点弱**：常驻用例仍只钉 `assert e["note"]`
   这一根非空牙——它管不住 note 退化成占位文本。要钉住信息量得判"note 里有没有
   `F-…`/文件名/数字"这类结构，本轮没做（做了就得先量它对措辞的过敏度，收益不明显）。
3. **`--emit-register` 不做幂等合并**：它整体覆盖目标文件，重跑会丢掉人工写的 note。
   本轮用法是"先生成草案、再由人填 note"，没打算让它长期当同步器；要做成增量合并得先定
   键与冲突语义（同一 path 被不同文档引用多次时的取舍）。
4. **面 ⑤ 的语料只有 `.md`**：`QUICKREF_DIRS` 里的 `.rst`/`.txt` 与 `templates/` 没进
   `ENTRY_DIRS`。今天没有那种写法，所以登记不建档。
5. **登记册的 `cited_by` 是一列会自证的过期快照**——本轮实测到：登记后我又写了本文两行
   引用 `/tmp/s46/battery.py`（`:18`、`:82`），那一列就没跟上。已在 `a42549c` 刷新数据并
   在文件里写明"权威是判据现读，常驻用例只核『在册/仍不可解析/仍被引用』，不读这一列"。
   **永久修法要动 `scripts/`**（参与发布哈希，正在跑的认证会被作废）：要么把这列改名
   `cited_by_at_emit_time`，要么整列删掉，让"引用位置"只能由现读得到。排在第 88 片。

## 九、复算入口

```bash
cd AIPD-OS
.venv/bin/python scripts/doc_command_census.py                      # rc 0；看"判红面 ⑤"那一行
.venv/bin/python scripts/doc_command_census.py --self-test          # 14 条标记
PYTHONPATH=$PWD/src .venv/bin/python -m pytest -q tests/test_doc_command_census.py
.venv/bin/python docs/audit/s87/battery87.py                        # 7/7 KILLED
```
