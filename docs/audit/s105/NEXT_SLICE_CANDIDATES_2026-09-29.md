# 第 105 片候选：两处量具口径缺口（本轮已量好分母，落笔前先复核）

写于 2026-09-29，第 104 片认证链在跑。本文不判任何东西，只把两条入口项的**现算读数**留在纸上，
免得下一轮重新摸。所有数字都带时点标签（2026-09-29 现读），落笔前必须重跑复算入口。

## A 生成物写的 `file::symbol` 指针免检（任务 #34a）

`scripts/doc_reference_census.py:70-77` 的面判定按目录：

- `LIVE_DIRS = ("docs/architecture", "docs/contracts", "references")`
- `HISTORY = ("CHANGELOG.md", "docs/audit")` ⇒ 目录在这两个里的，一律"只报不判"

问题是 `docs/audit/capability_matrix.md` 住在历史面，但它不是历史——它是每轮由 registry 字段
原样渲染出来的**现状描述物**。现读它带 4 条 `路径::符号`：

- `tests/test_cad_drawings2d.py::TestTangencyLimit`
- `tests/test_cli.py::cmd_intake` ← 载体写错：`cmd_intake` 实住在 `src/aipd_os/registry_data.py` 等 3 处
- `tests/test_release_manifest_eco_coverage.py::TestTheGateReadsIt`
- `tests/test_truth_propagate_cli.py::TestReworkHalfIsWiredAndItsBoundaryStaysVisible`

改法：分面按**生产者**而不是目录——加一份 `GENERATED` 名册（写全路径，逐条判红），这 4 条转判红档；
清零必须靠修渲染（渲染前校验 `::` 解析得到）或修 registry 数据，**不许靠把它们挪出 `GENERATED`**。
代价先说清：判红档从 0 变 4 ⇒ 常驻用例 `test_live_face_writes_symbol_anchors_not_bare_line_pins`
那类断言要扩一条"生成面也不许有指不回的象征"。

## B `resolve()` 基名解析撞同名（任务 #34b）

`decision_policy.py::should_ask_decision` 真身在 `src/aipd_os/execution/decision_policy.py`，
而 basename 解法先撞上 `scripts/decision_policy.py`（那台文件里没这个符号）⇒ 误判 `symbol-missing`。

改法：多同名一律落 `multi`（与裸文件名简写同档，只报不判），配一支开火控制——
造两个同名文件、符号只在其中一个，断言判 `multi` 而不是判"符号不存在"。
代价：现读 12 条 `symbol-missing` 里 1 条转 `multi` ⇒ 分档措辞（README 与本取证文档）要同步，
且 `multi` 档计数不得当成"新增缺陷"读。

## C README 量具名册盖不住带自测的尺（任务 #35）

现读：带 `--self-test` 的 `scripts/**.py` 共 **10** 台；README 里出现过的 `scripts/*.py` 共 **11** 条；
差集里**有自测却一个字都没出现在 README** 的 3 台：
`scripts/c6_coverage.py`、`scripts/doc_reference_census.py`（第 103 片）、
`scripts/changelog_commit_crosscheck.py`（第 104 片，本片自己就是漏网的最新一例）。

为什么不是文字病：README 的「复算入口」块是人之外的第三读者面。`doc_command_census` 面 ⑤
只管"写出来的入口要能解析"，看不见"该写的没写"——与第 104 片那条**整条缺席**同一形状，
所以判据也得按同一配方做：分母由 `grep -l -- '--self-test'` 现取（禁手写名册），差集非空即判红。

三件必须一起做的：① README 补三段（与既有两块同形：现算命令 + `--self-test` 命令 + 判什么）——
README 参与发布哈希，必须在取证件之前定稿；② 新尺配开火控制（临时造一台带 `--self-test` 的脚本，
断言它立刻进原告清单）；③ 反向不误伤：README 里出现但无自测的一次性取证脚本不算缺陷，只报数。

## 复算入口（三条命令，落笔前全跑一遍）

```
python scripts/doc_reference_census.py --json /tmp/drc.json
python scripts/changelog_commit_crosscheck.py
grep -l -- '--self-test' scripts/*.py scripts/research/*.py | wc -l
```

## 更正 A 段的前提（本轮认证跑完后现读，动手前复核抓出来的）

A 段原文写"这 4 条转判红档"。**数与性质都不对**，现读 `scripts/doc_reference_census.py --json /tmp/drc105.json`：

- 矩阵里解析不到的引用共 **6 条**，不是 4 条：`tests/test_cli.py::cmd_intake`（真缺陷：载体写错），
  另 **5 条是产物示例名** `papers.json`、`fulltexts.json`、`assy.step.evidence.json`、`assy.step`、`assy.dxf`。
- 那 5 条不是"指针指不回"，是**举例**：矩阵的产出列里写的是这台能力会生成什么文件，
  那些文件本来就不该在仓里。把它们转判红档＝重演第 41 片那次"514 条 missing 全是判据自造的假数"。
- 因此 GENERATED 面若真开，必须**只核带 `::` 的符号锚**，且举例名要有归属档
  （现读 `elided` 90 条、`cli-operand` 在代码块内那条规则已经存在；散文里的举例名需要一个显式"举例"标记，
  点不到标记即判失效——这是 `doc_command_census` 面 ⑤ 已经立的规矩，同一形状）。
- 全仓 `symbol-missing` 现读 **20 条**（第 103 片认当时是 12 条 ⇒ 会生长，抄数的地方都会漂，
  本节所有数字都按"2026-09-29 现读"读，落笔前重跑文末复算入口）。

真正要做的三件，代价重新排：① 修 registry 里那条写错的载体（1 处产品数据）；
② 给散文举例名一个可点名的标记档，否则任何"生成面转判红"的设想都开不了工；
③ `resolve()` 基名撞同名落 `multi`（B 段不变）。

## 更正 B 段的前提：「多同名一律落 multi」会把 188 个目标打成假原告（本轮现算）

B 段原写法是"简写且全仓同名 >1 ⇒ 一律判 `multi`"。动手前把半径量完，**这条不能这么落**：

- 现读：简写引用里全仓同名 >1 的共 **1323 条引用实例 / 188 个不同目标**——
  含 `README.md`（同名 9 处）、`CHANGELOG.md`（2）、`SKILL.md`（2）、`config.py`（11）、
  `__init__.py`（**519** 处同名）、`test_cli.py`（4）这类**散文明显指根目录那一份**的合法简写。
  把这一整片改判 `multi`，等于把 `resolved` 4708 条里的一大块搬进 `multi` 528 条，
  尺子当场失去分辨力——与第 41 片"514 条假 missing"是同一场病，只是方向相反。
- 真缺陷只在**符号锚那一条支路**上：`_classify_symbol` 拿 basename 解到的第一个文件去找符号，
  找不到就报 `symbol-missing`，而同符号其实在同名的另一份文件里
  （`decision_policy.py::should_ask_decision` 真身在 `src/aipd_os/execution/decision_policy.py`，
  先撞上的是 `scripts/decision_policy.py`；该目标全仓同名 5 处）。

改法收窄成"符号支路的精度修复"，不动文件级归属档：
对一个 `路径::符号` 引用，**把所有同名候选都查一遍符号**——
恰好一份里有 ⇒ `symbol-resolved`（并记下真正那一份）；多份里有 ⇒ 仍算 resolved 但 detail 记同名数；
一份都没有 ⇒ 才判 `symbol-missing`。开火控制两支各一极：
① 造两个同名文件、符号只在第二个 ⇒ 必须 `symbol-resolved`（今天会误判 missing）；
② 造两个同名文件、符号一个都没有 ⇒ 必须 `symbol-missing`（不许因"看了多份"而放过）。
现读全仓 `symbol-missing` 21 条（数字会生长，落笔前重跑），这是本次唯一允许的档间迁移来源。
