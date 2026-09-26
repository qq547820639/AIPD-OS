# F-CTQ-REVISION 第 59 片：`aipd ctq revise` / `aipd ctq deprecate`——链头第一次有带审计的改动入口

## 一、这一片从哪来

两条现成的引线，都不是凭空开的新面：

1. 第 56 片（`aipd ctq add`）在登记表里留的 `current_limitation` 原话：
   「**只有 add**：改一条已声明 CTQ 的限值（revise）与停用/取代（deprecate）今天都没有命令，
   限值变化只能走库层 `store.update` ⇒「谁在什么时候把 8.05 改成 8.10」**缺一个审计入口**；
   同一个图纸尺寸上已有 active CTQ 时新声明在门口被拒（不静默覆盖、也不按遍历顺序挑赢家），
   但**处置旧的那条还没有工具**」。本轮复核这条限制仍然成立：`src/` 侧写 `record_type="ctq"`
   的入口只有 `declare_ctq`（`src/aipd_os/product_truth/ctq.py:97`），改与停都只能人工进库。
2. 第 57/58 片把「改了 CTQ 会被看见」和「覆盖按记录号核对」都做完了，于是**改完之后的收口**
   只剩入口这一格：`superseded` 这个状态在门禁里已有确定语义
   （`src/aipd_os/release_manifest.py:95-99`：对 `superseded` 出**非阻断**点名
   `blocking=False`，其余状态 `blocking=True`），但没有任何公开命令会写它。

## 二、技术选型（本轮实读，四段齐全）

### 1. 候选清单（都带可打开出处）

| 候选 | 出处（本轮真打开） | 版本/日期（本轮现读） |
|---|---|---|
| A. dbt model versions（`versions` / `latest_version` / `deprecation_date`） | https://docs.getdbt.com/reference/resource-properties/latest_version 、 https://docs.getdbt.com/reference/resource-properties/deprecation_date | 两页均 200 取到正文 |
| B. django-simple-history | https://raw.githubusercontent.com/django-commons/django-simple-history/master/README.rst 、 https://pypi.org/pypi/django-simple-history/json | 最新发行 **3.13.0**，上传时间 2026-07-22；历史发行数 54 |
| C. sqlalchemy-continuum | https://pypi.org/pypi/sqlalchemy-continuum/json | 最新发行 **1.7.0**，上传时间 2026-07-03；历史发行数 103 |
| D. 自研：落本仓既有 `superseded` 状态 + `audit_log` 通道 | `src/aipd_os/state/db.py:1073`（`add_audit(actor, action, project_id, tenant_id, before, after)`） | 常驻，本轮读码确认签名 |

### 2. 六维对比（每维一句可核验的结论）

- **功能匹配度**：A 给的是「多版本共存 + 哪版是 canonical + 退役日期」这套**语义形状**，正对本案；
  B 给「每次改动自动落一行历史，带 user 与理由」，也对本案；C 与 A/B 的语义都能对，但它绑 SQLAlchemy
  的 unit-of-work；D 的匹配度取决于我自己写到什么程度。**本仓事实**：全仓（排除 `.venv/`）对
  `SQLAlchemy` 的检索是 **0 命中**（Grep `import sqlalchemy|from sqlalchemy|SQLAlchemy` →
  No matches found），truth 存储是裸 sqlite3（`src/aipd_os/state/db.py`）⇒ **C 的功能匹配度对本案为 0**，
  不是它不好，是没有它要吃的那套对象模型。
- **License 兼容性**：本项目 `pyproject.toml` 声明 MIT。B 的 README 原文 "This project is licensed
  under the BSD 3-Clause license"、C 的 PyPI `license_expression` 读到 `BSD-3-Clause`、A 是 dbt-core
  的文档（Apache-2.0）⇒ 三者与 MIT 都不冲突。
- **维护活跃度**：B 最近一次发行 2026-07-22（三个月内）、C 2026-07-03（三个月内）、A 是 dbt 主线文档
  当前页（`requires-python` 侧无版本要求，因为它是声明式属性）⇒ 三者都活着，没有"选它就得接手"的风险。
- **安全风险**：三者都不引入网络面；风险面是**新增依赖**本身（B 拉 Django，C 拉 SQLAlchemy，
  两个都是重量级框架，装进一个刻意保持最小安装的仓——`dependencies = ["jsonschema>=4.0"]` 是唯一硬依赖）。
- **代码质量**：B/C 都是老牌库（B 的 README 挂着 build/docs/coverage 徽章，C 有 103 次发行史），
  质量不是短板；短板在**接口形状**——B 的历史表由 Django Model 元编程生成，C 的历史表由 SQLAlchemy
  event listener 生成，两者都不接受"一条已经存在的 SQLite 表 + 我手工指定的元数据 JSON"这种写法。
- **适配成本**：**B 被两条硬事实堵死**——PyPI 读到 `requires_dist: ['django>=5.2']`，而其 README 的支持
  矩阵写 Django 5.2 对应 Python "3.10, 3.11, 3.12, 3.13, 3.14"；本项目 `requires-python = ">=3.9,<3.13"`
  且开发/CI 主解释器实测是 3.9（`.venv/bin/python`）⇒ 装不上。C 需要把 truth 存储整体迁到 SQLAlchemy
  ORM（`src/aipd_os/state/db.py` 是全仓状态层的底座，改动面覆盖所有读者）。A 不引包，只借语义，
  适配成本≈0；D 只写两个函数 + 两条命令，成本可估。

### 3. 择一决定：借语义，不引依赖

结论是 **借 A 的"版本落地/旧版留名单"+ 借 B 的"历史行带 user 与理由" + 用 D 落地**。
理由按上面两维收口：B/C 都在"适配成本"上被**本仓事实**（零 SQLAlchemy、Python 3.9 主解释器）挡住，
不是审美选择；A 本来就不是可安装的运行库（它是 dbt project.yml 的声明式属性），能借的只有形状。
借来的东西具体是什么，写死在这里以免变成空话：

- 借 A：**新版本落地、旧版留在名单里、"退役"不等于"删除"**。
  dbt 文档原文（本轮实读）：`latest_version` 的作用域是 "Resolving `ref()` calls to this model that are
  unpinned"——未固定引用自动指向最新，固定了版本号的引用**留在原版本**；`deprecation_date` 页原文
  "Deprecated models can continue to be built by producers and be selected by consumers until they are
  disabled or removed."，以及 "dbt doesn't allow deleting models with enforced contracts before their
  deprecation_date to protect downstream consumers."
  → 对应到本片：`revise` 不改写原文，另起 `version = 旧版 + 1` 的 active 新记录，旧记录标 `superseded`
  并留 `superseded_by`；引用它的下游（图纸声明）由第 57 片那侧**自己算出**"上游不在了"，
  而不是由这里替它删。dbt 的"不允许提前删除有契约的模型"落到本仓就是 `--replaced-by` 必须真存在。
- 借 B：**历史行带"谁"与"为什么"，且不覆盖原文**
  → 对应到本片：`audit_log` 一行带 `actor`（= `--by`）、`before_json`/`after_json` 两份快照，
  `deprecate` 强制 `--reason`。
- **没有借到的部分要写清**：B 的自动挂钩（每个模型保存都自动产历史行）刻意不仿——本仓的写入口很多，
  自动挂钩会把"谁改的"变成框架行为而不是命令契约；这里只在两条显式命令上写审计，
  所以「绕过命令直接 `store.update`」依然没有审计，这一格留作遗留（§九）。

### 4. 落地处（每条结论指到它实际改动的文件与位置）

| 结论 | 落在哪 |
|---|---|
| 另起新版 + 旧版留链（借 A） | `src/aipd_os/product_truth/ctq.py:218` `revise_ctq`，链字段写在 `:304-309`，版本号 `:312` |
| 退役态选 `superseded`（门禁出口判据） | `src/aipd_os/product_truth/ctq.py:349`；判据读 `src/aipd_os/release_manifest.py:95-99` |
| 审计行带 actor 与前后值（借 B） | `src/aipd_os/cli/commands_truth.py:437` `_ctq_audit`，两个调用点 `:478` / `:523` |
| `--replaced-by` 必须真存在（借 A 的"不许提前删有契约的模型"） | `src/aipd_os/product_truth/ctq.py:341-348` |
| 不引依赖 | `pyproject.toml` 未改：`dependencies` 仍只有 `jsonschema>=4.0` |

## 三、实现形状

- `revise_ctq`（`src/aipd_os/product_truth/ctq.py:218`）：先 `_require_ctq` 认记录
  （不存在 / 不是 `ctq` 都退到命令层的 2），再要求状态 `active`；未给的旗子**沿用旧值**
  （`_limits_of`，`:185`），值逐项相同即判"没变"（不写库、不写审计）；否则调 `declare_ctq(..., supersedes=旧id)`
  另起一条，把旧那条标 `superseded` 并留四个链字段，最后把新记录 `version` 推到 `旧版 + 1`。
  `declare_ctq` 新增的 `supersedes` 参数只干一件事：把被修订的那条**从查重名单里摘掉**
  （不摘就永远修订不动自己），其余校验（标称在域内、下限<上限、同一图纸尺寸不重复认领）全部复用，
  **不在修订侧再抄一份**。
- `deprecate_ctq`（`:324`）：`--reason` 必填（`_clean` 拒空串）；状态只允许 `active`/`stale`，
  已退役的不许重复停用（那会把 `superseded_at` 刷成今天，掩盖第一次改动的时刻）；
  `--replaced-by` 给了就 `store.get` 验存在。
- 两条命令都走 `_ctq_audit` 写 `audit_log`；**审计写不进去不算干净成功**：退码 4，
  `--json` 的 `ok=false` 且带 `audit_error`，同时 `changed=true` 原样保留——数据确实已经改了，
  把它报成"什么都没发生"是另一种撒谎。
- 命令面四处镜像一次补齐：`command_contract.py:154,163`（`CommandStatus.PUBLIC`、`"5.20"`、
  `requires_args` 逐个点名必填旗子）、`commands.py:546-547`、`main.py:668,692` 的 argparse、
  README 的两段（`:458`、`:466`）。公开命令数 60 → 62，命令面分母 70 → 72（§六）。

## 四、两个实测冒出来的缺陷（都不是设计时想到的）

1. **同值修订会白另起一个版本**。首轮 smoke 实跑 `aipd ctq revise --upper 8.05 --nominal 8.000`
   （值与库里完全一样）读到的却是 `created: true` + 一条新记录。成因是 `supersedes` 把被修订的那条
   从查重名单里摘掉之后，"改回同一个值"在 `declare_ctq` 眼里成了一条**新声明**，它的幂等查重救不了这格。
   修法是在 `revise_ctq` 里先逐项比（数值按 float 比，所以 "8.000" 与 8.0 是同一个值），
   全同即返回 `changed: false`，**不另起版本也不写审计行**——否则审计次数会高于真实改动次数，
   而审计行数正是这格存在的理由。钉子：`tests/test_truth_ctq_revise.py::test_revise_to_the_same_values_creates_nothing`。
2. **返工执行器会把声明重写成空声明**。新写的探针（撤回最后一条 CTQ 后跑 `truth rework`）读到的是
   rc=0 且磁盘上那份声明变成 `features: []`。第 56 片把"空声明不是交付物"只修在**生产者**
   （`aipd drawing spec`）那一侧，`cad/spec_rework.py:91` 的重算路径没有同一半守卫：
   `spec_from_ctq` 在**一条 active CTQ 都没有**时返回的空 spec **不带 gap**（分母为 0 时无从缺起），
   于是执行器把它读成"重算成功、内容与旧值不同 ⇒ rewrote"。修法是补 `empty_declaration` 失败支
   （`src/aipd_os/cad/spec_rework.py:98`），与 gap 同档：文件与记录都不动，返工任务留在 pending，
   交给引擎的有界退避。这条守卫不是"更安全"的装饰——它挡住的是"要求被撤回"被读成"产物已完成"。

## 五、常驻用例（`tests/test_truth_ctq_revise.py`，14 条）

五组：① 修订形状（另起新版、旧标 superseded、四个链字段、未给的旗子沿用旧值、版本号跟着走）；
② 审计（改了必有一行且含前后两个值、同值修订零审计、`--by` 无机器缺省值、审计写不进去判未收口）；
③ 门口就拒（记录不存在 / 不是 ctq / 已停用 / 上限不大于下限 / 标称不在域内 / 数值解析不出 /
`--reason` 空 / `--replaced-by` 指向不存在）且**一条都不写**；
④ 链条（revise → `truth drift` 点名 → `truth sweep` 落刀 → `truth rework` 按 8.1 重写 → drift 转绿
且声明的 `ctq_refs` 等于当前 active 集合；deprecate 探另一半：返工拒绝把声明自证为空）；
⑤ 命令面镜像（契约 / `COMMAND_FUNCS` / argparse 必填旗子 / README 四处，AST 读 `main.py`）。

写这批用例时踩到的一处测试自己的形状错值得记：辅助函数 `_deprecate(env, record, *flags, reason=...)`
起初把 `reason` 写成位置参数，于是调用处传 `"--replaced-by"` 时被 `reason` 吃掉，
argparse 报「`--reason`: expected one argument」并以 2 退出——**看着像被测产品拒得对，其实是测试
把参数塞错了位**。改成关键字参数后同一处才真的走到"取代记录不存在"那条分支。

## 六、连带改判与镜像

- 第 56 片那条端到端链测试的"改限值"从**直写库层**改成走公开命令 `aipd ctq revise`
  （`tests/test_truth_ctq_add.py::_change_upper_limit`）。机制换了一支，**且这一支与我原先写的不同**：
  我原本预计走 `ctq-gap`（缺口）那半支，配对实测读到的是
  `src/aipd_os/cli/commands_drift.py:99,108` 的 **lost 半支**——本夹具只有一条要求，撤回后 `present` 为空，
  `spec_from_ctq([])` 交不出 gap，源面 reason 是
  「N 条上游 CTQ 已不在 active 集合里：T-001」。两支都进 DRIFTED、退码都是 4，
  所以该文件三条断言一字未改（只换改法与注释）。对照读数（同副夹具，旧直写 vs 新命令）：

  | | CTQ 行 | `truth drift` 的 source 面 reason |
  |---|---|---|
  | 旧（`store.update` 直写） | `T-001 active 8.1` | `source面当前键与记录里那份不一致`（面级 reason 为空） |
  | 新（`aipd ctq revise`） | `T-001 superseded 8.05` + `T-003 active 8.1` | `…不一致（source面：1 条上游 CTQ 已不在 active 集合里：T-001）` |

  另一处语义位移要如实记下：`test_declared_ctq_feeds_spec_propagate_and_rework` 里
  「(旧 CTQ id, 声明记录) 这条边还在」从这一片起钉的是**返工不许抹掉历史上游边**
  （实测 `edges == [(T-001,T-002), (T-003,T-002)]`），
  而"新版本被接进上游名单"那一半由 `tests/test_truth_ctq_revise.py:271-274` 的 `refs == active` 钉。
- 登记表 `product_truth.ctq_declaration` 的 `current_limitation` 整段重写（原句"只有 add"已过期），
  `run_command`/`input_output`/`unit_test`/`e2e_evidence` 四格同步；
  `capability_matrix.{json,md}` 由 `scripts/capability_matrix.py --pin-commit` 重生成，不手抄。
- **本轮自己犯的一处错（记下因为它没人拦）**：重写完 `current_limitation` 后，我在里面写了
  「只能读库或看 `aipd truth show`」——`aipd truth show` **是一条不存在的命令**（实测
  `COMMAND_FUNCS` 的 truth/ctq 面只有 `truth propagate/tasks/rework/drift/sweep` 与
  `ctq add/revise/deprecate`，全仓检索 `truth show` 只命中我自己刚写的那一句）。
  它是被本轮的只读普查发现的，不是被门禁发现的：`run_command` 只被
  `scripts/capability_matrix.py:157` 原样渲染进 markdown，**没有任何常驻判据核对登记文本里点名的命令是否真的存在**。
  已改为实测过的表述（`aipd release manifest` 的 `ctq` 数组只收 active、条目里不写 `drawing_feature`，
  所以按图纸尺寸问不出今天有效的是哪条）。这一格留作遗留（§九）。
- 命令面分母 `tests/test_command_surface_census.py` 70 → 72（两处绝对数 + 漂移报警历史一行）；
  新命令的 argv 位证据由本片的 `main(["ctq", "revise", ...])` 提供，**没有**把它们塞进
  `BASELINE`（塞进去等于放行缺口）。
- 架构文档 `docs/architecture/truth_architecture.md` 的链头一节补第 59 片段落（含两处 dbt 原文引用
  与"选 `superseded` 是因为它有出口"的判据）。

## 七、取证（改前 / 改后配对）

配对探针 `/tmp/s59/probe.py` 跑在**干净检出** `/tmp/s59a`（`git worktree add --detach … HEAD`）上，
两臂同副夹具（同库、同项目、同一条 CTQ 8.0/7.95/8.05、同新上限 8.10），只换"改限值"这一步的做法：

| 读数 | 臂 A：直写库层（第 56 片那时的做法） | 臂 B：`aipd ctq revise`（本片） |
|---|---|---|
| 改动这一步 rc | 0 | 0 |
| CTQ 行 `(id, status, version, superseded_by)` | `[('T-001','active',1,None)]` | `[('T-001','superseded',1,'T-003'), ('T-003','active',2,None)]` |
| `audit_log` 里 `ctq.*` 行数 | **0**（全表也 0 行） | **1**，动作 `ctq.revise`、actor `潘工` |
| `truth drift` 点名那条声明记录 | 是 | 是 |
| `truth drift` 的源面 reason | `source面当前键与记录里那份不一致` | `source面当前键与记录里那份不一致（source面：1 条上游 CTQ 已不在 active 集合里：T-001）` |
| `truth drift` 退码 | 4 | 4 |

这张表就是本片存在的理由，也是它没有把判决改宽的证明：**判决两臂相同（都 4、都点名），
多出来的是"谁、什么时候、从什么值改到什么值"这一列事实**（`superseded_by` 链 + 1 行审计 + 版本号 2）。
reason 的差别按实测落笔：B 臂走的是 `commands_drift.py:99,108` 的 lost 半支，
不是我一开始写的 `ctq-gap` 半支（§六）。

命令面读数由同一把尺子现算（不抄 SKILL/README 里的数字）：
`len(PUBLIC_COMMANDS)` = **62**（第 56 片起为 60，本片 +2）、`len(COMMAND_FUNCS)` = **72**、
`scripts/command_surface_census.py --repo /tmp/s59a --json` rc=0 且
`denominator=72 / cli 档=72 / 低于 cli 档=[]`。

参与发布哈希的文件数 **660 → 661**（只多一个 `tests/test_truth_ctq_revise.py`；
`docs/audit/` 整体在排除面内，所以本片新增的取证文档不进分母）。

## 八、变异电池（`/tmp/s59/battery.py`，工作副本 `/tmp/s59w`）

十条臂，每臂只撤一条守卫；`import` 先证过解析在工作副本里
（`/tmp/s59w/src/aipd_os/product_truth/ctq.py`），对照臂未注入先跑：**14 条全绿、rc=0**。
判定写死在脚本里：原告 node id 出现在 `FAILED`/`ERROR` 名单 ⇒ KILLED；
测试跑起来而原告不红 ⇒ SURVIVED；锚点命中数 ≠ 1、改后编译不过、或 pytest rc≥2 且无红 ⇒ INJECT-INVALID。

| 臂 | 撤掉的守卫 | 判决 | 实际开火 |
|---|---|---|---|
| M1 | 返工执行器的空声明守卫（`if not spec["features"] …` → `if False:`） | KILLED | `test_deprecating_the_last_ctq_does_not_empty_the_declaration` |
| M2 | 修订不落取代链（去掉 `superseded_by`） | KILLED | `test_revise_supersedes_the_old_record_and_chains_to_the_new` |
| M3 | 修订不退役旧记录（`store.update(old, status=…)` 去掉 status） | KILLED | 上述 + `test_revise_is_visible_to_drift_sweep_and_rework` |
| M4 | 新版本号不跟着走（`+1` 去掉） | KILLED | `test_revise_supersedes_the_old_record_and_chains_to_the_new` |
| M5 | 允许修订已停用的 CTQ（状态门 → `if False:`） | KILLED | `test_revise_refuses_missing_inactive_and_foreign_records` |
| M6 | 接受指向不存在的 `--replaced-by`（存在性校验 → `if False:`） | KILLED | `test_deprecate_requires_reason_and_a_real_successor` |
| M7 | 修订不写审计行（调用点替成 `None`） | KILLED | `test_revise_writes_one_audit_row_with_both_values` + `test_unwritable_audit_is_not_a_clean_success` |
| M8 | 同值幂等判据反向（`==` → `!=`） | KILLED | `test_revise_to_the_same_values_creates_nothing` |
| M9 | 停用可重复（状态集合门 → `if False:`） | KILLED | `test_deprecate_is_audited_once_and_not_repeatable` |
| M10 | 停用不写审计行（调用点替成 `None`） | KILLED | `test_deprecate_is_audited_once_and_not_repeatable` |

合计：**杀 10 / 活 0 / 注入无效 0 / 崩溃击杀 0**。

两处电池自己要被教的地方（都不是产品缺陷）：
1. 第一版电池把 node id 键拼成 `tests/test_truth_ctq_revise::名`（`SUITE[:-3]` 把 `.py` 削掉了），
   于是十条臂全部落到 `KILLED-OTHER` 这一档——原告其实都开火了，是我把匹配串写错。
   修法不是"人工看一眼算过"，而是**改脚本重跑一遍**（第二版读数即上表），
   并把这条档留在脚本里：原告在名单内才叫 KILLED，否则一律降级报告。
2. M3 的注入（去掉 `status="superseded"`）让旧记录留在 active，于是链条那条用例也一起红——
   这不是"一臂多原告"的失败，而是这条守卫同时被两支用例看着；按纪律仍只把
   `test_revise_supersedes_…` 记成本臂原告，多开火的那条如实列出但不改判。

## 九、遗留

- **绕过命令直接写库仍然没有审计**：这是"借 B 不借满"的取舍（§二·3），
  要闭得靠给 `ProductTruthStore.update` 加写侧钩子或加一条"CTQ 行不许被库层直接改"的门禁，
  两者都会牵动其他 record_type，本片没做。
- `aipd ctq list` 仍然没有：`--record` 与 `--replaced-by` 都按记录号点名，
  人要问"这个图纸尺寸今天有效的是哪条"只能读库。
- `AIPDStateDB.list_audit`（`src/aipd_os/state/db.py:1082`）不分 tenant/project 且默认 `limit=100`，
  所以这格审计的**读者**目前只有测试与人工翻表；链上真数据能不能问出"谁改的"取决于翻页。
  这也是本片坚持在 metadata 里留 `superseded_by_actor` 的原因——两份留痕各有各的读者。
- 真实存量库 `data/state.db` 是属主数据，本轮仍未打开（刻意不动），所以"存量 CTQ 记录里
  有多少条从来没有 `record_id`/`superseded_*`"未测；本片所有读数来自隔离夹具。
- **登记文本里点名的命令没有对账判据**（本轮实测：`run_command` 只被
  `scripts/capability_matrix.py:157` 原样渲染，注册表与 README 正文里写的命令名不与
  `COMMAND_FUNCS` 对账；我自己在 §六 那条被拒的编造命令就是这么漏出去又被只读普查抓回的）。
  要闭得靠一条"把登记/文档里 `aipd <verb>` 全部解析出来与公开命令表求差"的常驻门禁——
  那是新的**一面判据**（与第 39/41 片同族），不在本片范围内，本片只把它记在这里。
- 电池只覆盖了"撤掉守卫就红"这一面，没有覆盖"两条守卫互相遮蔽"的组合
  （例如同时撤 `supersedes` 摘名单与同值幂等判据）——那是另一格，未做。

@FINAL@

## 十、终读数（收尾链，2026-09-27）

全部由本轮真实跑过的命令取得，每条给命令与实际读数；跑序：代码提交 → 重锚 → 干净检出复算 → 验签 → 绑定 → 门禁/审计。

| 项 | 命令 | 实际读数 |
|---|---|---|
| 提交序列 | `git log --oneline` | `d026b16`（feat：命令+执行器守卫+14 用例）→ `fea0ab2`（重锚矩阵与清单）→ `f7fd119`（绑定 attestation）→ `528d673`（本文 §七/§八）→ 本条 |
| 干净检出复算 | `git worktree add --detach /tmp/s59a HEAD` @ `fea0ab2200bb`，`PYTHONPATH=/tmp/s59a/src:/tmp/s59a/scripts AIPD_SOURCE_COMMIT=<tag SHA> pytest tests -q --json-report` | **2479 passed, 3 skipped**（collected 2482）in 235.43s，rc=0；跳过那条是 `test_researchstudio_provider.py:233`（要联网） |
| 收集数增长 | 同上 vs 第 58 片绑定值 | 2468 → **2482**（+14，恰为本片新用例数；参数化那条按 3 次计） |
| 验签器 | `/tmp/s59/verify_report.py --report /tmp/s59/report.json` | **36 条 [OK] / 0 条 [FAIL]**，rc=0，末行「全部前提成立，可以绑定」 |
| 验签器会开火 | 同一把尺子 `--self-test`（喂仓库里那份第 58 片报告） | 「拒签成立：**16 条前提不成立**」——它没把旧报告放行 |
| 发布就绪门 | `scripts/production_release_gate.py --release-ready --tag v5.6.0` | rc=**0**，`"passed": true` 共 **8** 条、`false` 0 条（含 `source_manifest_zero_diff: zero diff`、`no_secrets`、`no_unacknowledged_cve`） |
| 仓库审计 | `scripts/audit_repo.py --strict` | rc=**1**，✗ **恰好 1 条**：`Provenance source commit mismatch: manifest=a66040520139… vs HEAD=…` ⇒ **设计如此**（清单绑 tag，不跟 HEAD 重锚） |
| lint / 类型 | `ruff check src tests state_service`；`mypy src` | `All checks passed!`；`Success: no issues found in 245 source files` |
| 命令面 | `scripts/command_surface_census.py --repo /tmp/s59a --json` | rc=0，`denominator=72`、cli 档 72、低于 cli 档 `[]`；`len(PUBLIC_COMMANDS)=62` |
| 参与发布哈希的文件数 | `scripts/regenerate_release_manifest.py` | 660 → **661**（新增 `tests/test_truth_ctq_revise.py`） |
| 变异电池 | `/tmp/s59/battery.py`（副本 `/tmp/s59w`） | 对照臂先全绿；**杀 10 / 活 0 / 注入无效 0 / 崩溃击杀 0**（§八） |

一处要按实读数更正的面：**绑定那条提交说明（`f7fd119`）里写的「30 条前提全 [OK]」是错的**，
实际由脚本现数得 **36 条 [OK] / 0 条 [FAIL]**（`grep -c '^\[OK\]' /tmp/s59/verify.log` = 36）。
提交说明已落 git、按纪律不改历史，以本节为准；根因是我照上一片脚本的输出行数写的数字，
没在本轮数过——同一类"抄一个没数的数"的错，见 `[[feedback-doc-edit-anchoring]]`。

