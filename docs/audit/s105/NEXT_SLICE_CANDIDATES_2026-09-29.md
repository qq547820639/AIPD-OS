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
