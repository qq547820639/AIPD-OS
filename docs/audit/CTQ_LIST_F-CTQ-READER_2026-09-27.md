# `aipd ctq list` 取证（F-CTQ-READER 第 62 片，2026-09-27）

本片做一件小事并顺带还三笔账：给 CTQ 链头补**第一个面向人的读面**，
并处理"把一个曾被当作假影的名字注册成真命令"撞出来的量具自身缺陷。

## 一、起点：这条缺席不是我觉得缺，是量具测出来缺的

第 60 片新量具 `scripts/doc_command_census.py` 把 registry 里那句限制原话登记成
"正文点到了一条未注册命令"，第 61 片又让它**只对量具自己隐身**（`SELF_STEMS` 四档全排除）。
于是这条缺口在只报面上一直可见：链头有**三个写者**
（`aipd ctq add` / `ctq revise` / `ctq deprecate`）与**四个读者**
（发布证据分母 `src/aipd_os/release_manifest.py:69`、图纸声明输入
`src/aipd_os/cli/commands_drawing.py:86`、出图返工 `src/aipd_os/cad/spec_rework.py:91`、
漂移扫描 `src/aipd_os/cli/commands_drift.py:78`，四处都是 `store.query(record_type="ctq", …)`，
本轮逐个 `sed -n 'Np'` 复核过），
**但没有一条命令能让人问出"这个图纸尺寸上现在有效的是哪几条、限值与版本各是几"**。
人能问的最近一件事是 `aipd release manifest` 的 `ctq` 数组——它只收 active、
条目里不带 `drawing_feature`，所以"按图纸尺寸问"问不出。

选型按最高指令的例外条款跳过（写进 CHANGELOG 同一格）：本片不引入新组件，
实现是一个作用域化 `SELECT` 加一份人类可读投影，无新依赖；
状态口径沿用第 59 片已比过的 `TRUTH_STATUS` 五态。

## 二、改了什么（实现面）

| 位置 | 改动 |
| --- | --- |
| `src/aipd_os/product_truth/ctq.py:363 list_ctq` | 新增读者：按 tenant/project 取 `record_type="ctq"`，默认只留 `active`，其余态**计数进 `excluded`**；投影直接调 `_snapshot`（审计行用的那份）；按 `feature → version → record_id` 定序 |
| `src/aipd_os/cli/commands_truth.py:543 cmd_truth_ctq_list` | 新增处理器：`payload = {"command": "ctq list", "ok": True, **result}`；prose 打作用域头、每条一行（限值/标称/版本/态/信任级/声明人）、`另有 N 条未列出（排除：…）`、口径注；读不出退 2；**不写 `audit_log`** |
| `src/aipd_os/cli/main.py` | `ctq` 组下新增 `list` 子解析器（`--db/--project/--tenant/--all/--json`，`set_defaults(func=…)`） |
| `src/aipd_os/cli/commands.py` | 派发表加 `"ctq list"` |
| `src/aipd_os/cli/command_contract.py` | 契约条目 `CommandEntry("ctq list", PUBLIC, PRODUCT, "5.23", requires_args={--db,--project})` |
| `README.md` / `SKILL.md` / `src/aipd_os/registry_data.py` | 命令面镜像：速查行、分组与"主线共 63 个"、能力行的 `run_command`/`input_output`/`unit_test`/`e2e_evidence`/`current_limitation` |
| `tests/test_truth_ctq_list.py` | 新增（见 §四） |
| `tests/test_command_surface_census.py` | 手抄分母随注册面挪（现算值见 §三） |

## 三、现算读数（本轮真仓库，三条命令可复算）

```
PYTHONPATH=src:scripts .venv/bin/python scripts/doc_command_census.py            # rc=0
PYTHONPATH=src:scripts .venv/bin/python scripts/command_surface_census.py        # rc=0
PYTHONPATH=src:scripts .venv/bin/python scripts/skill_quality_audit.py           # rc=0
```

- 权威面：`89` 条 argparse 路径 / `15` 个组名（第 61 片末是 88/15，多的那条就是 `ctq list`）。
- 判红面语料：`run_command 85 段 / 速查行 92 行 / 生产代码 214 处`（另 `6` 处同行带否定标记 ⇒ 只报）。
- 只报面 `964` 处（全量扫描 `1282`），**现状面缺陷 0 条**。
- 只报面点到未注册的命令 8 个名字：`aipd ctq listy`(4)、`aipd ghost cmd`(5)、
  `aipd ghostci check`(3)、`aipd ghostly cmd`(4)、`aipd ghostspec run`(3)、
  `aipd truth ctq`(8)、`aipd truth show`(13)、`aipd x`(1)。
  `aipd ctq list` **已不在这张清单里**——这就是本片干成的那件事。
  （清单里 `listy/ghost*` 那五个是夹具名的**引述**，见 §六末一条，那是下一片的账。）
- 命令面：已注册 `73` 条、低于 cli 档 `0` 条（满覆盖保持）、契约 PUBLIC `63` 条。
- lint/类型：`ruff check src tests state_service` → `All checks passed!`；
  `mypy src` → `Success: no issues found in 245 source files`。

## 四、常驻用例（`tests/test_truth_ctq_list.py`，10 条）

每条对着一个具体的说谎方式，不是"能跑通"：

| # | 用例 | 钉的是什么 |
| --- | --- | --- |
| 1 | `test_ctq_list_is_registered_on_the_argparse_tree` | 派发表里有而 parser 里没有＝幻影；沿声明树走一遍拿权威路径 |
| 2 | `test_default_view_lists_active_and_names_what_it_excluded` | 默认视图必须自报排除了几条，否则"1 条"被读成"库里 1 条" |
| 3 | `test_records_reuse_the_production_projection` | `records == _snapshot(活记录)` 等值断言；读面重抄字段就会静默漂开，且必须带 `drawing_feature` |
| 4 | `test_json_command_label_equals_the_registered_name` | `command` 标签等于注册名（第 60 片刚修过 `truth ctq add` 那类幻影标签） |
| 5 | `test_empty_scope_is_stated_not_silent` | 空作用域退 0 且明写「0 条 + 作用域」，与"没跑到"分开 |
| 6 | `test_other_statuses_show_verbatim_under_all` | `stale` 在 `--all` 里按库里原样出现；默认视图里 `excluded == {"stale": 1}` |
| 7 | `test_readme_quickref_lists_the_new_command` | README 有行首可执行那一行（第 60 片那把尺子正判这个面） |
| 8 | `test_unreadable_store_is_not_reported_as_zero_records` | 非 sqlite 文件 ⇒ 退 2 且不产出「0 条」（钉 `_open_store`） |
| 9 | `test_mid_read_failure_is_not_a_zero_reading` | 库打得开而 `list_ctq` 抛 ⇒ 同样退 2（钉命令里那段 try/except，见 §五臂 1） |
| 10 | `test_listing_writes_no_audit_row` | 一行审计都不写，同批用 `ctq deprecate` 做反向对照证明通道本来就通 |
| 11 | `test_limits_print_verbatim_not_six_significant_digits` | 合格域原样打（`:g` 会把 8.050001 印成 8.05）——见 §五之二 |
| 12 | `test_counts_are_self_consistent_across_the_two_views` | `total == returned + Σexcluded` 在两种视图各算一遍，`statuses` 跟着视图走 |
| 13 | `test_default_note_does_not_claim_superseded_is_the_only_retirement` | 口径注不许把例外说满（第一版写错，见 §五之二） |
| 14 | `test_failure_paths_emit_no_success_payload` | 两条读失败面都带 `--json` 复跑：退 2 且 stdout 上没有 `"ok": true` 的成功件 |

`PYTHONPATH=src:scripts .venv/bin/python -m pytest tests/test_truth_ctq_list.py -q`
→ `14 passed`。

## 五、变异电池（六臂）

先立对照组再判开火：锚点命中数必须恰好 1、`new` 在原文件里必须为 0（空改写永远绿）、
变异落地必须先证 sha 变了、每臂跑完立刻还原，最后整文件复绿且两份源 sha 各自复原
（`ctq.py a134b8bdf882→a134b8bdf882`、`commands_truth.py ce256c8f7192→ce256c8f7192`）。

| 臂 | 改坏的是什么（对着哪条常驻用例） | 首轮判定 | 终局判定 |
| --- | --- | --- | --- |
| 1 | 读失败不退 2，改成"0 条"空清单继续走到成功（用例 9） | **SURVIVED** —— 当时没有用例 9，臂只喂"非 sqlite 文件"，异常在 `_open_store` 就被接住，命令里那段 try/except 没执行到 | **KILLED**（补用例 9 后 `pytest_rc=1`） |
| 2 | `_open_store` 的读不出退码 2 → 0（用例 8） | 未测 | **KILLED** |
| 3 | 读面往 `audit_log` 落一行（用例 10） | 未测 | **KILLED** |
| 4 | 合格域退回 `f"{low:g}"` 格式化（用例 11） | 未测（§五之二那条缺陷带来的） | **KILLED** |
| 5 | 口径注改回"superseded 是唯一退出分母的态"（用例 13） | 未测 | **KILLED** |
| 6 | 非 active 记录既计数又列出（破坏 `total == returned + Σexcluded`，用例 12） | 未测 | **KILLED** |

六臂 `py_compile` 全 0（变异自身语法成立，不是 INJECT-INVALID），终局
`6 KILLED / 0 SURVIVED / 0 INJECT-INVALID`，还原后 `14 passed`。
臂 1 那一次存活是本片最值钱的读数：它说明"我给读失败写了用例"和"读失败真的被钉住了"
是两件事，前者可以完全空转。

电池脚本本身**未入库**（宿主重启即没），但六个改动点写死在这里，按表可原地重放：
臂 1 改 `cli/commands_truth.py` 里 `cmd_truth_ctq_list` 的 `except Exception` 那支 `return 2`；
臂 2 改同文件 `_open_store` 里 Product Truth 读取失败那支的 `return None, 2`；
臂 3 在 `_emit(args, payload, prose)` 之前插一次 `AIPDStateDB(...).add_audit(...)`；
臂 4 把合格域那行的 `[{lower}, {upper}]` 改回带 `:g` 的写法；
臂 5 把"注："那三行改回第一版的"superseded 是唯一能让一条要求退出分母的态"；
臂 6 在 `product_truth/ctq.py:list_ctq` 的 `else` 分支里既 `excluded[...] += 1` 又
`kept.append(_snapshot(rec))`。

## 五之二、独立复核抓出的三处（都在实现落地之后、绑定之前）

派了一个只读复核（禁改文件、禁跑套件），交回一份缺陷清单。逐条亲手重开源码后：
**两处成立并已修**，**一处不成立**，按最高指令第四档如实分开记。

1. **合格域被格式化改了数**（成立）。原写法 `f"[{low:g}, {high:g}]"`，实测
   `format(8.050001, 'g') == '8.05'`、`format(1234567.8, 'g') == '1.23457e+06'`——
   一条读面的存在理由就是把限值说准，它却把 8.050001 印成 8.05。
   顺带 `format(10**400, 'g')` 会 `OverflowError`；但那条**不可达**：
   `declare_ctq` 在 `ctq.py:70` 就把 inf/NaN 拒了，超大整数走不进生产者，
   所以本轮没为它造用例（不为打不到的分支写测试）。
   修：原样打印，并删掉那个从不生效的 `isinstance` 分支；用例 11 + 臂 4 钉住。
2. **口径注把例外说满了**（成立）。原句"superseded 是唯一能让一条要求退出分母的态"。
   重开 `release_manifest.py:67-103`：`by_id` 只收 active，**全部**非 active 态都退出分母，
   superseded 特殊的只有一点——对它只出**非阻断**点名；另外缺 `metadata.feature` 的
   active 记录门口判 `ctq_missing_feature` 阻断，而本视图照样列出。
   修：注释句改成两差别都点明；`README.md:473`、`command_contract.py:173`、
   `registry_data.py` 那行里"与发布分母同口径"的措辞一并收窄成"与发布分母的 active 过滤同口径"
   （三处镜像同源同错，一处错就会三处传）；用例 13 + 臂 5 钉住。
3. **"有非 active 记录还退 0 是不一致"**（不成立，记理由）。复核引 `truth drift` 的
   `return 0 if report["clean"] else 4` 作对照。但 `ctq list` 对着的是另一个先例：
   `cmd_truth_tasks`（同为纯列表面）读失败退 2、其余一律退 0，且它专门打一行
   "空列表只说明本作用域没有**任务**行，不代表没有 stale 记录"。
   列表面把"存在被停用的要求"（正常事件）与"有要求没收口"（异常事件）混进同一个退码，
   反而是新的谎；本片照 `truth tasks` 的形状办，并把那句"空 ≠ 不存在"的告警补进
   0 条读数（拼错 `--project` 也会读到 0 条）。

同一批复核还指出四条测试空洞（弱断言 `"1" in text`、`total/returned/excluded` 守恒未钉、
`isinstance` 兜底分支从不执行、失败面未带 `--json` 复跑），四条分别由用例 2 收紧、
用例 12、修 1 顺带删除、用例 14 闭合。

## 六、量具自己的三笔账（注册一个曾被当幻影的名字会撞出什么）

`aipd ctq list` 这个名字在第 60/61 片被当过**三处夹具**里"仍然没有"的那个幻影。注册它之后：

1. `scripts/doc_command_census.py --self-test` 直接崩（`assert (got is not None) is want`
   里那条 `("ctq list", False)` 前提不再成立）；
2. `tests/test_doc_command_census.py::test_absence_written_in_prose_is_reported_not_judged`
   与 `…::test_the_instruments_own_files_are_out_of_all_four_faces` 当场报错——
   且报错形状是"判据把合法名判红了"，**排查方向正好反了**；
3. `…::test_negation_in_production_code_is_reported_not_judged` **静默空转**：
   那行仍带"没有"标记所以 `code_negated` 照样为 1，只是标记指向的命令已经存在，
   否定例外这一支再没有被任何东西验过。这一条是最坏的，因为它全绿。

处置：
- 量具与用例的夹具幻影名统一改成 `zzz-` 前缀（`ctq zzz-phantom` / `ctq zzz-unlisted` /
  `ctq zzz-quickref` / `ctq zzz-listy` / `ctq zzz-show`），并由
  `tests/test_doc_command_census.py:78 ghost()` 与自测里的两行前提断言把
  "`ctq` 必须是组、这个子命令必须仍缺"钉成会说话的失败；
- 注入面与只报面**必须不同名**（否则"只报面不判红"那条断言会被判红面上的同名违规先判红，
  两档病因混成一条读数）；
- 顺手量了一件事并写进度量具 docstring：**今天真语料上已无"带否定标记且指向未注册命令"的
  代码行**。两档对照（把 `NEGATION_MARKERS` 置空再 `audit(ROOT)`）：违规数不变（0），
  只有 `code_negated` 与非否定计数互相挪。所以那条例外目前**只由夹具保持有牙**，
  §五的控制臂就是它的存在证明（KEEP 绿 / CUT 恰在那条幻影上翻红）。

## 七、未证实与下一步

- **未证实（机制限制，不是本轮没做完）**：`ctq list` 在**存量开发者库**上的读数。
  `data/state.db` 含属主数据，本项目每条切片都不打开它，所以"真实存量 CTQ 有多少条、
  字段是否有空值/异常态"这一面本轮只能由临时库外推。
- **未接的相邻两格**（registry 那行 `current_limitation` 仍如实保留）：
  `aipd release manifest` 的 `ctq` 数组仍只收 active 且不写 `drawing_feature`；
  `AIPDStateDB.list_audit` 仍不分 tenant/project 作用域，所以"谁在什么时候把 8.05 改成 8.10"
  问得出但要自己按 before/after 筛。
- **下一片的第一条**：只报面那张"未注册名"清单里，`ctq listy` / `ghost cmd` / `ghostly` /
  `ghostspec` / `ghostci` 五个是**夹具名的引述**（文档在记录量具自己写了什么），
  读起来与真缺口同形——把 `zzz-` 前缀与 `ghost*` 单列一档（不计入缺口数）即可，
  代价是给报表加一个分组，判决不变。
- **旧取证文档不追改**：`docs/audit/CTQ_REVISION_*.md:235`、`DOC_COMMAND_CENSUS_*.md` §三/§七/§十
  里"没有 `aipd ctq list`"是当轮取证件，按本仓规矩保留原文；当前读法以本文件与
  registry 那一行为准。
