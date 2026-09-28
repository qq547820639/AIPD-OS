# WORKTREE-INVENTORY 2026-09-28：`tmp/` 下 16 个 worktree 登记的分诊（先清点，后按判据回收）

派这一趟的原因：第 85 片收口时我自己建又自己删了一个 worktree（`.wt-s85`），
顺手 `git worktree list` 才看见仓库里挂着 **16 条**登记。`git worktree prune` 报 0 条失效
（15 个链接树的目录**都还在**），所以它们不是残骸，不能当 prune 对象。
本篇第一版把删除判成"不在自决范围"、只出清单与判据 —— **那个归类是错的，本轮改正**：
这些树是我自己历轮建的本地预演件（不共享、远端无对应物），要回收的只是"树"本身，
而它们唯一不可再生的内容（11 份逐例报告）已经被摘要化并入库，
于是这件事变成"自有 + 可加 + 内容留存"的自决动作，不是一次属主裁决。
判据与执行读数见 §五、§六。

## 一、方法与一条本轮踩到的取数错

逐路径读：`rev-parse --short HEAD`、`status --porcelain`（总数与 `??` 数分列）、
`merge-base --is-ancestor <head> <主树HEAD>`、`stat` mtime、`du -sh`、
以及在 `docs/audit/` + `CHANGELOG.md` + `README.md` 里 grep 该路径/基名的引用数。

**踩到的坑（值得单记）**：第一遍我自己核对时把工作树路径写成 `AIPD-OS/tmp/sNN/final`
（真实位置是仓库**同级**的 `AI全链路自研/tmp/...`），于是每条 `git -C` 都失败，
而 `status --porcelain | wc -l` 在失败时输出 **0** ——`0` 与"这棵树干净"**完全同形**。
那一遍读出来的是"5 个 worktree 全部干净、HEAD 全部为空"，看上去像一条结论。
判别法：**HEAD 为空就是命令失败，不是"没有提交"**；核对循环里必须
`2>&1` 收下 stderr 并显式区分"目录不存在 / git 失败 / 真的干净"三态。
下面这张表的 5 行抽查是改正路径后重跑的，与表内数字一致。

## 二、清单（主树 HEAD = `277c60b`）

| worktree | HEAD | 与主树关系 | porcelain / 其中未跟踪 | mtime | 大小 | 被取证文档引用 |
| --- | --- | --- | --- | --- | --- | --- |
| `tmp/s70/final` | `5efd9f2` | ancestor | 1 / 1（`?? report.json`） | 2026-09-27 | 40M | 3 处 |
| `tmp/s71/final` | `4a61945` | ancestor | 1 / 1（`?? report.json`） | 2026-09-27 | 40M | 3 处 |
| `tmp/s72/final` | `981c71c` | ancestor | 1 / 1 | 2026-09-27 | 40M | 3 处 |
| `tmp/s73/final` | `9dddab2` | ancestor | 1 / 1 | 2026-09-27 | 40M | 3 处 |
| `tmp/s74/final` | `feaf9e5` | ancestor | 1 / 1 | 2026-09-27 | 40M | 3 处 |
| `tmp/s75/final` | `34a545a` | ancestor | 1 / 1 | 2026-09-27 | 40M | 3 处 |
| `tmp/s76/final` | `000d093` | ancestor | 1 / 1 | 2026-09-27 | 40M | 3 处 |
| `tmp/s77/final` | `ab1389b` | ancestor | 1 / 1 | 2026-09-27 | 40M | 3 处 |
| `tmp/s78/final` | `f97997f` | ancestor | 1 / 1 | 2026-09-27 | 40M | 3 处 |
| `tmp/s79/final` | `4f0779c` | ancestor | 1 / 1 | 2026-09-27 | 40M | 3 处 |
| `tmp/s80/final` | `8160e17` | ancestor | 1 / 1 | 2026-09-27 | 40M | 3 处 |
| `tmp/s81/final` | `6ca9c41` | ancestor | **0 / 0** | 2026-09-28 | 38M | **0** |
| `tmp/s81/final2` | `6843350` | ancestor | 0 / 0 | 2026-09-28 | 38M | 3 处 |
| `tmp/s83/final` | `7acaced` | ancestor | **0 / 0** | 2026-09-28 | 38M | **0** |
| `tmp/s83/final2` | `1f46a21` | ancestor | 0 / 0 | 2026-09-28 | 38M | 2 处 |

（`tmp/s81/final2` 的 HEAD 提交是 `chore(s82) …`——路径写 s81、内容是 s82 那一步，
第 82 片复用了第 81 片的树名。这类"路径与轮次不一致"本身就是引用风险，见 §四。）

## 三、分档

- **A. 机制上三条门槛都过（干净 + 是祖先 + 零引用）**：`tmp/s81/final`、`tmp/s83/final`。
  但**同轮的 `final2` 才是被引用那棵**（取证文档写"读数来处（两棵树不许互换引用）"），
  所以删 `final` 会不会让某个读者去找它，我没有证据能排除——留给属主判。
- **B. 有未提交内容，别动**：`tmp/s70..s80/final` 共 11 棵，脏项都是一个
  `?? report.json`（当年全量报告直接落在树里）。没有一棵有已跟踪文件的修改。
  这些 `report.json` 是**未入库的一次性产物**，不在任何清单里（`docs/audit/` 整体被排除，
  而它在树根不在 `docs/audit/`——实际是被 `git ls-files` 未跟踪所排除）。
- **C. 被取证文档引用**：13 条（含 B 里的 11 条）。典型原句
  「签出那一跑（`tmp/s70/final`，报告产出于提交 `5efd9f2`，主树当时 HEAD `7fe4407`）」
  ——删掉这些目录，文档里那句"去这棵树复核"就成死链。
- **D. 判不准**：0 条（16 个 HEAD 全是主树 HEAD 的祖先或相等，无命令失败）。

## 四、结论与不做的事

1. **不删、不 prune**：`prune` 在这台机器上是 no-op（15 个链接目录都在），
   而真删会同时打掉 B 档的 11 份 `report.json` 与 C 档 13 条引用指向的位置。
2. 要回收空间，正确顺序是先**改文档**再删树：把 C 档那句"去这棵树复核"改成
   "读数在本文 §X，原树已回收"，并先把 B 档的 `report.json` 收进 `docs/audit/sNN/`（那里不参与发布哈希）。
   这是一轮的活，不是顺手动作。
3. 顺带发现：`tmp/` 下还有 `s63/s65/s66/s67/s68/s69/s84` 这些**未登记**的目录
   （没有对应 worktree），以及**没有** `s82` 目录。它们不在本次清点范围内（不是 worktree），
   属于同一类"历轮留痕无人回收"的问题。
4. 以后每片收口自建 worktree 时，**用与轮次一致的目录名**并在删之前 `grep` 一次引用；
   第 85 片用的 `.wt-s85`（仓库同级、带前导点、不落在 `tmp/sNN/` 惯例里）
   是一个新形状——它避免了与历史 `final/final2` 混淆，代价是不再符合"路径含轮次"的老约定。

## 五、回收判据（本轮据以执行的四条）

1. **树本身可再生**：15 个 `tmp/sNN/...` 的 HEAD 全是主树 HEAD 的祖先（§二表"ancestor"列，
   实测 0 棵带已跟踪文件修改），提交对象仍在共享库里——回收后 `git cat-file -t 5efd9f2`
   与 `git cat-file -t 1f46a21` 都回 `commit`。所以"删树"不等于"丢历史"，
   再要那棵树只需 `git worktree add --detach <原路径> <原 SHA>`。
2. **唯一不可再生的内容是那 11 份逐例报告**（`tmp/s70..s80/final/report.json`，每份 2.3 MB）。
   已按 §四.2 的顺序先摘要化再回收：`docs/audit/round-reports-s70-s80-digest.json`
   （**5,279 B 重建件**，11 轮，每轮记 passed/skipped/total、`len(tests)`、
   `files_in_report`、duration、created、锚点、原文件字节数，以及
   "summary 无 failed 键 ⇒ 推导 0 failed"这个口径）。
   11 轮 skipped 合计 **40**、passed 合计 28,573，无 failed。
   **这个摘要件不是第一版**：第一版（10,672 B）还含 40 条跳过用例的 nodeid 与逐份 sha256，
   它在本轮一次范围过宽的回车里被连带删掉，而源 `report.json` 已随 worktree 回收，
   所以那两栏不可再生——细看 `provenance.fields_unrecoverable` 与 §六 错误 3。
3. **`closeout_verifier` 不要求取证那棵树还存在**：`report_root` 只在
   `scripts/closeout_verifier.py:225` 记成读数、`:439` 打印，从不 `exists()` 判定；
   `--worktree` 默认取主树（`:769`）。所以回收不会把后续验签打成前提塌。
4. **`tmp/sNN/final` 这类引用从来不参与仓库内指针尺**：路径在仓库**同级**，
   干净签出里根本解析不到——本轮回收前后 `production_release_gate` 的
   `doc_reference` 相关项读数不变（回收前那次门是 8/8 全过）。
   因此删目录不会新造出硬档红；反过来说，这些"去这棵树复核"的入口**早就跑不了**，
   见 §六.2。

## 六、执行读数与一条比回收本身更值的发现

回收前 `git worktree list` = **17** 行（主树 + 16），`du -sh tmp` = **622M**。
逐棵 `git worktree remove --force`（16 次全部 `removed`，0 次 `FAILED`）→
`git worktree prune -v` 无输出 → 回收后 `git worktree list` = **1** 行、
`.git/worktrees` 目录条目 **0**、`du -sh tmp` = **28M**。
`.s86-outside/` 三个日志（`gate.log`/`closeout.log`/`closeout-recheck.log`）
先落 `docs/audit/s86/` 再删目录；`.wt-s86/run.log`（260 行）同样入库；
`report-s86.json` 与 `docs/audit/pytest-report-v5.6.0.json`、`docs/audit/pytest-report.json`
三者 sha256 全是 `3d3e3800cff1…`（同一份字节已在库内两份），所以 `--force` 没带走任何东西。

**发现的缺陷（不在原任务范围里，量出来才发现）**：把 `docs/audit/*.md` + `CHANGELOG.md` +
`README.md` 里所有 `tmp/sNN/...` 形态的路径片段做一次精确求差（正则
`tmp/s[0-9]+[A-Za-z0-9_./-]*`，按整路径而不是按基名匹配——我第一遍按基名数，
`__init__.py`/`out.md` 这类重名把读数撑歪了）：

- 被引用的 **144** 个不同路径片段；
- 磁盘上**还存在**的 **5** 个，且这 5 个在仓库内**都没有同名入库件**，属唯一可迁的一档：
  `tmp/s63/verify63.py`、`tmp/s81/e2e/`、`tmp/s81/e2echeck.py`、`tmp/s81/probe6.py`、
  `tmp/s83/s83b.sh` ⇒ 本轮已按原相对结构迁入 `docs/audit/sNN/`（合计 **19** 个文件、
  **37,329 B**，含 `s81/e2e/` 子树 15 个文本件）；
- **139** 个不在磁盘上，其中 **17** 条是 worktree 形态（`tmp/sNN/final`、`final2`、
  以及本文 §三 那条区间记法 `tmp/s70..s80/final`），其报告内容已被 §五.2 的摘要件覆盖；
  其余 **122** 条是历轮写在 `tmp/` 下的工件（电池脚本、探针日志、`state.db`、逐例报告），
  **内容确已不可再生**——`s30head`…`s64e` 这一整段轮次都属此类，
  第 63 片那份验签脚本被宿主重启清掉就是同一形状（
  见 `docs/audit/CLOSEOUT_VERIFIER_F-CLOSEOUT-VERIFY_2026-09-27.md:4-5`）；
- 另有 **6** 条引用的磁盘件已消失、但仓库内有同名入库件（历轮自己迁过）⇒
  那是**陈旧指针而不是内容丢失**，属"改指针"档，不是"抢救"档。

也就是说：**"复算入口"这一整类主张，历史上约 122/144 处是"当时那台机器上才跑得动"**。
第 81 片起改用 `docs/audit/sNN/`（入库、不参与发布哈希）才是可复算的形状。
立尺（"文档里的复算入口必须仓库内可解析、或显式登记为已失效"）已记为第 87 片的入口，
本轮只完成清点、抢救与记账。

**本轮自己犯的两个错，留在这里当反例（不删）**：

1. 第一次迁移动手前**没查目的位是否已被 git 跟踪**，并且用 `dst_dir / rel.name`
   把嵌套路径**按基名压平**。后果两项：`docs/audit/s66..s80/` 里 **15 个已入库脚本**
   被 `tmp/` 的旧副本覆盖（`git status` 报 ` M`），以及 `s81` 那 464 文件树里
   31 个同名 `__init__.py` 之类的件在目的目录互相覆盖。
   补救：先把被覆盖的版本挪到 `.s87-clobber-backup/`，`git checkout -- <那 15 个显式路径>`
   回退，再按 `git status -uall` 的**权威未跟踪清单**删掉本轮全部 185 个迁入件与空目录；
   回退后抽查 `s66/battery66.py`、`s77/battery77.py`、`s80/battery80.py` 三件
   `git show HEAD:… | shasum` 与磁盘逐字节 `SAME`。第二次迁移改成
   "先比 `git ls-files`、目的位已有不同内容就不写、按原相对路径建目录"。
2. 我先前那句"**142 个里没有一个在仓库内有同名入库件**"是**用错的尺读出来的**：
   它拿 `Path.glob("docs/audit/**/<基名>")` 在工作树里找，而文档对历轮脚本的引用形式是
   `docs/audit/sNN/batteryNN.py`（库内相对路径），于是"引用面"与"查找面"根本不是同一批 token。
   改用 `git ls-files` 建跟踪面权威集合后，读数从"0 个有同名件"变成 **6 个**。
   这是"入门禁档的读数必须换一把独立尺复核"的现行版本——第一遍的 `无` 全列，
   恰是我自己那把 glob 尺恒不命中。
3. **回退范围按"未跟踪"划，而不是按"本轮我写过的清单"划**。撤回那次误迁时，我按
   `git status --porcelain -uall` 里 `docs/audit/` 下的全部 `??` 逐件删除（185 件）——
   清单里确实全是我当天写的，但**其中一件是 §五.2 那份摘要**，它不属于误迁产物、
   而且是当时唯一还留着那 40 条跳过 nodeid 与逐份 sha256 的文件；
   而它的源（11 份 `report.json`）已在更早一步随 worktree 回收。
   后果：摘要只能从 16:28 那两次一手读数的打印件重建，字段集比第一版窄。
   纪律：**回退要按"本轮写入清单"逐件删，不能按"未跟踪状态"整片删**——
   未跟踪只说明"没入库"，不说明"是谁、为哪件事写的"。
   第二次迁移因此加了"目的位已有不同内容就不写、先比 `git ls-files`"两道闸，
   并只用 19 件（37,329 B）的范围把 C 档抢救回来。
