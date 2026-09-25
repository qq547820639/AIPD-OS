# F-C6 第 32 片：`gates.approved_by` 不再自带 `'AI-internal'`

日期：2026-09-25 ｜ 轮次：本轮（承第 31 片「门的要求表接回声明文件」之后）
登记的缺陷类别：**默认值把「没有这件事」写成「有这件事」**——同一族第 26 片已经在
ECO 三张表上修过一次，这一次修的是那个反面教材的本尊。

## 一、这一格以前为什么是假的

第 26 片建 ECO 时，本仓把这条规矩写进了 `src/aipd_os/change_orders/eco.py` 的模块
docstring（规矩 1）：

> 机器身份表 `NON_HUMAN_ACTORS` 不是装饰：本仓 `gates.approved_by` 的默认值是
> `'AI-internal'`，照抄那个形状就等于任何写入点不写审批人也算「已批准」。

ECO 那三张表照这条教训建了（`creator` / `approver` 分两列、`approver` 无默认值），
**而 `gates` 这张表本身一直没改**。实测到的现状（全部指到 `file:line`）：

| 面 | 事实 |
| --- | --- |
| 列的形状 | `approved_by TEXT NOT NULL DEFAULT 'AI-internal'`，同句 DDL 有**三份**：`state/migrations/schema.py:173`（V1 冻结文本）、`state/db.py:222`（参考 SCHEMA）、`scripts/aipd_store.py:135`（废弃旧库） |
| 写入口 | `AIPDStateDB.add_gate`（`state/db.py:1025`）形参 `approved_by: str = "AI-internal"` ⇒ 不写审批人 = 写了一个审批人 |
| 生产调用点 | 只有两个，都在 `supply_chain/writeback.py:129,154`，显式盖 `"supply-chain"` |
| 常驻用例 | `tests/test_golden_projects_e2e.py:262,440` 两处都没传审批人 ⇒ 权威表里被写进 `'AI-internal'` 的行是本仓测试自己产生的 |
| 读侧 | `list_gates`（`state/db.py:1043`）与快照导出（`state/db.py:1143`）原样带着这一列出去，**没有任何一处判断过它是不是人** |
| 词表 | ECO 的 `NON_HUMAN_ACTORS` 里**没有** `supply-chain` ⇒ 只复用那张表读数，唯一在产的两行会被读成「真人批的」 |

一句要澄清的：`product_intelligence/gate.py:161` 的 `record_gate` 与这张表无关，
它自己的注释明写「**不写** `gates` 表」。写入口叫 `add_gate`。

## 二、修法与四个决定

1. **migration v20 重建 `gates`**：`approved_by` 改可空、无默认值，历史值原样保留。
   决定：不改 V1 冻结文本。那段 DDL 在 `V1_INITIAL_SCHEMA` 里，被
   `V1_FROZEN_SHA256` 与 `tests/test_migration_freeze.py::test_frozen_v1_schema_does_not_drift`
   钉住——v1 当年确实带着这个默认值，回头改掉它正是冻结要防的事。
   重建照 `helpers.py` 里 v9（`claims.confidence`、`claim_evidence_relations.strength`）
   的既有先例；`gates` 上没有索引，`_V20_GATE_COLUMNS` 一份常量供 up/down 共用
   （各抄一遍列清单就是给下次改表留一个丢列的机会）。
2. **写入口默认 `None` ⇒ 落 NULL**；给了值就必须非空，纯空白串 `ValueError`。
   机器身份仍可以写（供应链回写就盖 `supply-chain`），但要**显式**写。
3. **机器身份词表搬到叶子模块 `src/aipd_os/actors.py`**，`supply-chain` 补进去，
   ECO 的本地 `_is_human` 删掉、改调 `is_human_actor`；
   归类是三态：`unattributed`（NULL，从来没填过）/ `non_human`（填了但是机器，
   含纯空白）/ `human`。读不到这一列 = `unattributed`，不折算成任何一态。
   搬家而不是复制：两处读者各留一份词表迟早漂，
   `test_eco_imports_rather_than_recopies_the_list` 用 AST 钉住这一点。
4. **降级方向落空串而不是 `'AI-internal'`**：v19 的列是 `NOT NULL`，NULL 放不下，
   必须选一个非空串。落 `'AI-internal'` 等于一次回滚凭空造出一批
   「AI 批过」的台账；空串在词表里，读侧仍算「不是人批的」。
   已知的不对称（有用例钉住）：`NULL → down → '' → up` 之后仍是 `''`，
   up 不猜——**过一趟降级，归类不变，原值不变**。

读侧新落点 `src/aipd_os/gate_attribution.py`；`scripts/quality_gate.py` 输出多一段
`gate_approval_attribution`，**只报不判**：把「有没有人批」接进 `pass` 就是收紧共享
门禁，那是属主裁决（§五）。

## 三、原计划被实测更正的四处

动手前的登记写的是「同步改两处 DDL（db.py 基线 + migrations/schema.py）」，
实测把它改掉了：

1. 写入口是 `add_gate` 不是 `record_gate`（后者另有其人，见 §一末尾）。
2. `schema.py:173` **不能改**：它在 V1 冻结文本里（§二.1）。这条如果照原计划做了，
   `test_frozen_v1_schema_does_not_drift` 当场红。
3. 还有**第三份** DDL（`scripts/aipd_store.py:135`）与**两个** v4→v5 搬运脚本
   （`migrations/v4_to_v5.py:201`、`migrations/rollback_v5.py:132`）——它们是第一轮
   `grep | head -30` 截断掉的。重跑不加截断才看见。旧库那份不改（它就是历史，
   而且正是 v20 要修的那个输入形状）；两个搬运脚本**只搬不造**
   （原样带 `g["approved_by"]`），已在 `tests/test_migration.py` 补一条断言把这句话钉住：
   老库那条没写审批人的 INSERT 确实带着 `'AI-internal'` 迁上来，
   而读侧把它归成 `non_human`——升级不会把「没人批的历史」洗成「有人批了」。
4. 「复用 ECO 的机器身份表」这句原话不够：那张表漏着本仓唯一在产的戳
   （§一最后一行）。补进去之前，读侧会把生产数据读成真人批准。

## 四、端到端实测

| 场景 | 读数 |
| --- | --- |
| 新建库 | `PRAGMA table_info(gates)` 的 `approved_by`：`notnull=0`、`dflt_value=None`；链尾 `current_version=20` |
| 不写审批人 | 盘上 `approved_by IS NULL` 为真（直读 SQL 复核，不只看接口返回） |
| 写空白串 | `ValueError: approved_by 给了就必须是名字…`，且**没有**落行 |
| 供应链回写 | `PhysicalWriteback.write_release_gate` 之后 `project_gates` 读数 `non_human=1、human=0` |
| 历史行 | v20 之后仍有 `'AI-internal'` 的行：`human=0、non_human=1` |
| up 不改写历史 | 从 v19 世界种 `'AI-internal'` 与 `'wang'` 两行，升 v20 后两值原样在，归类 `non_human` / `human` 各一条 |
| down 不造批准 | 过 v19 之后两行是 `('')` 与 `('zhang')`，列的默认值还原成 `'AI-internal'` |
| 主键稳定 | up→down→up 之后 `gate_record_id` 不变，新写的行接着往后走（AUTOINCREMENT 序列没被重建打回） |
| 门只报不判 | 同一个 G3 绿世界两档只差 `approved_by`：两档 `pass` 都是 `True`，只有 `gate_approval_attribution` 差一条（合规侧先证绿，配对才有意义） |

## 五、这一片没做的事（登记为待裁）

1. **归属要不要进发布门**。现在只报不判。要判，得先定「谁算人」的口径：
   本仓没有身份源，`zhang` 是真人署名还是随手填的串，机器分不出来；
   `mail/client.py:609` 还有一处 `approver or meta.get("approved_by", "owner")` 的
   角色占位符，按现词表算 human。把它也算 non_human 会改动 ECO 的判据，
   属主没拍之前不动。
2. 那 9 项 CAD 阶梯交付物仍无产者（第 31 片 §五.1 原样开着）；
   `experience/` 三份 `G0..G9 → 中文名` 漂 5 格；`interfaces` 的 verdict 进不进发布门。
3. `migrations/v4_to_v5.py`、`rollback_v5.py` 里 `g["approved_by"]` 是硬取键：
   老库那一列若为 NULL（本次之后新建的老库不会有）会 `KeyError`。
   这是搬运脚本自身的健壮性问题，与本片判据无关，没顺手改。

## 六、收口读数

（本节数字全部由命令输出抄，见每格括号里的取数方式。）

| 项 | 读数 |
| --- | --- |
| 全量用例 | 2139 → **2170**（+31，全在新增的 `tests/test_gate_attribution.py`）。取数顺序：先提交代码（`99540e3`）⇒ 在**工作树**跑 tag 锚定那一遍（`AIPD_SOURCE_COMMIT=<tag SHA>`，948.52s，**`2167 passed / 0 failed / 3 skipped`**，这一跑就是 PROVENANCE 绑的那份）⇒ 提交工件（`de73f15`）⇒ 再在 `git worktree add /tmp/s32head HEAD` 的干净签出里跑一遍（`PYTHONPATH` 指签出树，并先断 `aipd_os.state.db.__file__` 落在签出上）作为本轮记录与签出 attestation。**一处不完美照实写**：tag 那一跑跑在带着三个未提交清单外工件（`SOURCE_MANIFEST` 等）的工作树上，代码部分与 HEAD 相同，但「工件也一致」这一格只有干净签出那一跑能证；重锚之前拿不到干净的工件一致树，这是这套 tag 锚点方案的固有顺序（见项目记忆的收口配方）。
| 被哈希面 | 621 → **624**（新增 `actors.py`、`gate_attribution.py`、`test_gate_attribution.py`）。两份清单都不含 `PROVENANCE.json` / 两份清单自身（实测 `contains=False`），`docs/audit/` 前缀条目数为 **0** ⇒ 审计文档与报告不参与哈希，这条闭环没有自引用 |
| 词表搬家 | ECO 判决不变：`tests/test_change_order_eco.py` 全量复跑仍绿（机器身份既不能开单也不能批单）；`supply-chain` 进表后 ECO 也拒它。误伤普查 0（不带截断重跑 `grep -rn`，共 10 处）：两处是 `writeback.py:135,160` 自己盖的戳、两处 `actors.py`（词表 + 注释）、一处 `db.py:1031` 的 docstring、四处在本片新用例里，另有一处 `test_golden_projects_e2e.py:629` 是**项目 id** `"C-supply-chain"`，不是 actor |
| `PROVENANCE.test_report` | `2167 passed / 0 failed / 总 2170`，报告 `docs/audit/pytest-report-v5.6.0.json`（`sha256=55b287d17512…`），`source_commit = a66040520139…`（tag，按既有裁决不重锚到 HEAD）|
| 清单不自引用 | `SOURCE_MANIFEST` / `RELEASE_MANIFEST` 各 624 条里**都不含** `PROVENANCE.json` 与两份清单自身，`docs/audit/` 前缀条目 0 ⇒ 最后一次全量之后生成一次证据就够，不需要「生成→再刷一轮防自引用」|
| 发布门 `production_release_gate --release-ready --tag v5.6.0` | **8/8 绿、`release_ready: true`、rc=0**（`workspace_clean=clean`、`commit_matches_head`、两份清单 `zero diff`、`test_numbers_from_report = passed=2167 failed=0 total=2170 source_commit=a660405…`、Ed25519 可验、无密钥、`no_unacknowledged_cve = pip-audit: no unacknowledged CVE`）。**但同一棵树第一次跑是 rc=2**：唯一红的那条是 `no_unacknowledged_cve` 的 fail-closed 分支——判据用 `shutil.which('pip-audit')` 找可执行文件（`scripts/production_release_gate.py:600`），而 `.venv/bin/pip-audit` 明明在盘上，只是那条 shell 的 `PATH` 里没有 venv 的 `bin`。把 `.venv/bin` 放进 `PATH` 重跑才是上面这个 8/8。**这不是本片的回归**（该检查自 `24227f6` 就在），但它是一条会骗人的读数：见 §七.4 |
| `audit_repo --strict` | rc=1，唯一 ✗ 仍是既有裁决那条 tag 锚点红：`Provenance source commit mismatch: manifest=a66040520139… vs HEAD=de73f156be72…`；两份清单 `hash_matches=624/624`、`hash_mismatch_count=0` |
| C6 普查 | 15 项 = **15 / 0 / 0**，`--self-test` 7/7 |
| 镜像 | 本片**没有**新增公开命令、也没有新增能力行 ⇒ `registry_data` / `scripts/c6_coverage.py` 的行未动；判据不是「我觉得不用改」，而是全量 2170 条里`test_capability_matrix`、`test_registry_export`、`test_command_coverage` 等镜像用例全绿（tag 那一跑 0 红）。动的镜像只有 `docs/architecture/state_inventory.md`（HEAD schema 段 + 迁移清单表行）、`README.md` 门那一段、`CHANGELOG.md` 条目|
| ruff / mypy | ruff（CI 范围 `src tests state_service`）`All checks passed!`；mypy `Success: no issues found in 424 source files`（+3）|
| 变异电池 | 本片 `/tmp/slice32-mutations.py` **14 条：杀 14 / 活 0 / 注入无效 0**。同树复跑第 31 片 **8/8**、第 30 片 **21/21**（两片都含 `quality_gate.py` 的锚点，本片在该文件里加了 5 行——不改形也要复跑才算数）|

## 七、三处自己抓自己的读数

1. **一份「看不见」的 grep 把「只有两个写入口」说得像已证实。**
   第一轮命令都带 `| head -30`，返回恰好打满 30 行，而 `migrations/v4_to_v5.py:201`、
   `migrations/rollback_v5.py:132`、`scripts/aipd_store.py:135` 都在第 30 行之后。
   去掉截断重跑才发现第三份 DDL 与两个搬运脚本。规矩：写「全仓仅有 N 处」之前，
   同一命令必须有一次不带 `head`，并核 `grep -c` 的总数与列出的行数是否相等。
2. **一条常驻用例自己就踩了默认值。** `tests/test_golden_projects_e2e.py:262,440`
   两处 `add_gate` 都没传审批人 ⇒ 权威表里那些 `'AI-internal'` 行是本仓测试写的。
   「谁污染了台账」这类问题先查自己的夹具，别先假设是外部数据。
3. **配对的第一版两侧同红，等于什么都没测。** 为了证「归属只报不判」，最初两档只差
   `approved_by`，但夹具只登记了 2 项交付物（G3 要 5 项）⇒ 两档 `pass` 都是 `False`，
   把归属接进判决也不会让断言变红。补齐成绿的一侧之后，注入 I14（门要求 human>0）
   才当场开火。另外这类种子用例要注意：Python 的 `sqlite3` 对 **DML 开隐式事务**
   （DDL 不开），所以旁路 `INSERT` 必须显式 commit，否则「历史行读成 non_human」
   那条断言会因为**表里根本没行**而假绿。
4. **一条 fail-closed 的门禁检查会因 `PATH` 缺 venv 而假红。** 同一棵树第一次跑
   `production_release_gate` 得 rc=2，唯一红是 `no_unacknowledged_cve`，理由写的是
   「pip-audit not available」——可 `.venv/bin/pip-audit` 就在盘上，判据是
   `shutil.which('pip-audit')`（`scripts/production_release_gate.py:600`），而那次调用的
   shell 没把 `.venv/bin` 放进 `PATH`。把 `PATH` 补上后同一棵树 8/8 绿、真跑了审计且
   「no unacknowledged CVE」。**读门禁的红要先问它拿什么当证据**：fail-closed 是对
   「看不见」的正确处置，但把它记成「有 CVE」或记成「本片改坏了」都是假归因。
