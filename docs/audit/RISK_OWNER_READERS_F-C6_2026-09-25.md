# F-C6 第 34 片：`risks.owner` 不再硬写 `'AI'`，并给这根列补上第一个真读者

日期：2026-09-25　范围：`src/aipd_os/state/db.py`、`state/migrations/{definitions,helpers}.py`、
`actors.py`、`experience/owner_dashboard.py`、`tests/test_risk_ownership.py`（新）与三处镜像文档。

## 一、这一格以前为什么是假的

第 32 片闭掉的是「读侧把没人批准读成 AI-internal 批准」；同一族的另一格在 `risks` 表，
而且比它更空。逐条实测（改前，2026-09-25）：

| 事实 | 证据（现算，非记忆） |
|------|----------------------|
| 列形状自带机器身份 | `owner TEXT NOT NULL DEFAULT 'AI',` 出现在 `state/migrations/schema.py:148`（V1 冻结文本，被 `V1_FROZEN_SHA256` 钉住）、`state/db.py:197`（参考 SCHEMA）、`scripts/aipd_store.py:114`（废弃旧库）三处 |
| 写入口根本没法表达「谁负责」 | `AIPDStateDB.add_risk`（`state/db.py:975`）形参列表里没有 `owner`，INSERT 第 9 位硬写字符串 `"AI"` ⇒ 任何一条自动开出来的风险都被记成 AI 负责 |
| 创建后反而允许改 | `update_risk` 的可改白名单里**有** `owner`（`state/db.py:1001`）：创建时不许说、创建后允许改，两半没有一条理由 |
| 从来没有人读 | `list_risks` 的四个调用点（`experience/owner_dashboard.py`、`experience/project_summary.py`、`state/views.py`、`state/checkpoint.py`）一个都不碰这一列 |
| 生产写入口没有一处能填 | 去截断重跑 `grep -rn "add_risk("`：`experience/onboarding.py:59,64`、`state/server.py:324`、`supply_chain/writeback.py:60,114`，加两处常驻用例与旧 CLI `scripts/aipd_state.py:56` |

⇒ 这是一根「一直在写、写的是假话、而且没有读者」的列。只修列形状会留下一根修好了仍然没人读的列，
所以这一片同时补第一个真读者。

## 二、修法与三个决定

1. **migration v21 `risks_owner_no_default`**（`helpers.py:740` 起）：拷贝重建 `risks`，
   列改为可空、无默认值，**历史值原样保留**（含库里已经躺着的 `'AI'`）。
   V1 冻结文本改不得 ⇒ 这一格只能以重建落地，与 v20 同一处置。
   - 决定 A：**down 方向 NULL 只落空串，不落 `'AI'`**（`helpers.py:756`）。
     降级时把「没人」写成「AI 负责」等于凭空给一批风险指派了负责人；
     空串在机器身份词表之外，读侧归到「填了但等于没填」，与 gates 那张表同一取舍。
   - 列清单常量 `_V21_RISK_COLUMNS`（`helpers.py:701`）由 up/down 共用，
     `trigger` 保持不加引号（本仓既有写法）。
2. **写入口**（`db.py:975`）：`add_risk(..., owner: str | None = None)`，
   `actor = None if owner is None else str(owner).strip()`，
   给了值但 strip 后为空 ⇒ `ValueError`（空白串不许冒充一个名字）；INSERT 落 `actor`。
3. **读侧**：`actors.py` 里那份机器身份词表通用化成 `summarize_actor_column(rows, column=…, id_field=…)`
   （三态计数 + `unassigned` 清单），gates 与 risks 共用一份词表但各自的投影留在各自模块；
   Owner Dashboard 新增「风险责任」块（`owner_dashboard.py:80` 起，视图键 `:129`），
   正文两档渲染各出一行（紧凑档 `:182`、完整档 `:209`）。
   - 决定 B：**默认视图只给人话与计数，风险编号只进 `<details>` 折叠区与 `--json`**——
     与既有契约 `test_owner_ux.py::test_dashboard_default_hides_internals` 同一口径，
     不新造一套「什么算内部代号」。
   - 决定 C：**只报不判**。这块读数今天不进发布门的放行条件：
     「这条风险该谁负责」是组织事实，代码里没有任何身份源可证某个字符串是某个人，
     拿它当门依据等于把署名当证据（与第 32 片 `gate_approval_attribution` 同一立场）。

## 三、动手前被实测推翻的三条

1. **「升到 HEAD 后与新建库同形」是相对断言，撤掉 v21 的 up 它照样绿**——
   新建库也走同一条被撤掉的迁移，两边一起变。真凶是绝对断言那条
   （新库里这一列没有默认值）。凡「A == B」式的判据都要问一句「A、B 同时错会怎样」。
2. **新加的 Dashboard 块一开始只有 `--json` 看得见**：我只在视图 dict 里加了键，
   两档文本渲染都没落地。「加了个键」≠「有读者」，直到第一条断言改去整段渲染文本里找措辞才暴露。
3. **电池 J15 第一轮是被记成「杀掉」的假杀**：用例当时挂在了别的类里，
   node id 没被收集，pytest 退 4，而旧记分法把 `rc != 0` 一律算杀掉。
   ⇒ 电池加**未注入对照臂**（先跑同一 target 要求 rc==0），退出码分档：
   rc=1 记「断言红」，rc≥2 记「崩溃式红/挂错目标」且脚本非零退出。
   这一轮之后才是真的 15/15。

被这条教训反过来咬了一口的还有镜像文档：`state_inventory.md` 的页眉（`schema HEAD = v19`）
与正文（`HEAD = **v20**`）从第 32 片起就已经互相打脸，而没有任何尺子看得见——
本片补 `tests/test_risk_ownership.py::TestTheDocMirrorMatchesTheChain`，
拿 `MIGRATIONS` 当真值双向对账（版本清单表逐行、页眉与正文两处 HEAD 声明），
并自带两条注入对照（删一行 / 把 HEAD 写旧）。

## 四、端到端实测

- 三态读数（真人 / 机器代签 / 没人）：`_seed_mixed` 造 `li` / `NULL` / 历史 `'AI'` 各一条，
  `summarize_actor_column(..., column="owner")` → `{human: 1, non_human: 1, unattributed: 1}`，
  `unassigned == ["RISK-002", "RISK-900"]`；
  Dashboard 块 `waiting_for_owner == 2`，正文句子实测是
  「3 条风险里 2 条还没有真人负责（含机器代签）」——`_seed_mixed` 共三条（真人 `li`、`NULL`、历史 `'AI'`）。
- 全认领侧（配对）：两条都是真人 ⇒ 「2 条风险都有真人认领」；
  空账本侧（第三档）：0 条 ⇒ 「暂无风险条目」，不写成对空集的断言。
- 生产路径：`PhysicalWriteback.write_stage` 自动开出的风险 `owner is None`
  （以前每条都是 `'AI'`）。
- 迁移往返：v20 老库升上来与新建库同形；`up` 逐列保真（12 列全部有值的行，
  down→up 后整行字典相等）；`down` 把 NULL 落成 `''` 且列形状还原 `DEFAULT 'AI'`。

## 五、这一片没做的事

1. **`created_by` / `actor` 那一族还带着 `'system'` 默认值**（未截断普查，四处）：
   `state/db.py:299`（`claim_evidence_relations`）、`state/migrations/definitions.py:131`（同表）、
   `state/migrations/helpers.py:106,150`（该表的重建 SQL 两份）、
   `state/migrations/helpers.py:257`（`product_definition_snapshots`）、
   `state/migrations/helpers.py:348`（`product_definition_commits.actor`）。
   它们有没有读者、写入口能不能表达，**本片没审计**，是下一片的前提测量而不是本片的结论。
2. **没把归属接进发布门**（决定 C）；`state/server.py` 与 HTTP 写面也仍未暴露 `owner`——
   服务侧要能填这一列，得先定「谁的身份源」。
3. **`scripts/aipd_store.py:114` 那份旧库 DDL 原样保留**：废弃路径，
   与第 32 片对它的处置一致（不改、不假装改得动）。
4. **`update_risk` 的 owner 白名单没动**：本片没引入新判据，也就没有可杀的撤回案例
   （进电池的 `KNOWN_SURVIVORS`）。

## 六、收口读数

| 项 | 读数 |
|----|------|
| 全量用例 | 2182 → **2205**（+23，全在 `tests/test_risk_ownership.py`；HEAD 侧用 `git worktree` 干净签出实测 collected 数，不用记忆） |
| 签出 attestation | `/tmp/anchor34` 的 HEAD 干净签出 + `AIPD_SOURCE_COMMIT=<tag SHA>`：**2202 passed / 0 failed / 3 skipped**，报告 `source_commit = a66040520139405095648461f7144d4f00629924`，同一份绑进 `PROVENANCE.test_report`（`sha256` 记在证据里） |
| 第一跑的一格红 | 同一棵签出第一跑只红 `test_state_perf_gates.py::TestConnectionAndTransactionGates::test_batched_transaction_outranks_per_statement_writes`（断 5× 比值，与并发 agent 抢 CPU）；同条在干净树单跑 0.29s 过 ⇒ 按配方**整跑重放**拿 0 failed，不放宽比值门、不把这一红绑进证据 |
| 发布门 | `production_release_gate --release-ready --tag v5.6.0`：默认 PATH 下 `no_unacknowledged_cve` fail-closed 假红（rc=2，7/8）；`export PATH="$PWD/.venv/bin:$PATH"` 后 **8/8、rc=0、`release_ready: true`** |
| 仓库审计 | `audit_repo --strict` rc=1，唯一一条红是既有的「Provenance source commit mismatch（锚点 = tag，HEAD 在后）」；两份清单 `hash_mismatch_count = 0` |
| 变异电池（本片） | `/tmp/slice34-mutations.py` **15 条：杀 15 / 存活 0 / 注入无效 0 / 崩溃式红 0 / 已知无撤回案例 2**（带未注入对照臂） |
| 同树复跑 | 第 32 片 **14/14**（I4 锚点因本片新增同形守卫命中 2 次，重锚到 `approved_by` 那句报错文案）；第 30 片 **21/21**；第 31 片 **8/8**；第 33 片 **9 杀 / 0 存活 / 0 注入无效 / 2 已知无撤回**——五片都在**最终代码树**上重跑（`86f1617` 时点，其后两笔只动文档与清单），全部 rc=0 |
| 静态检查 | `mypy src` 0 error；`ruff check src tests state_service`（CI 口径）rc=0；`ruff check .` 的 693 条是 CI 范围外目录，不在本片范围也未动 |
| 提交序列 | `99b808a`（代码+用例）→ `833e8dd`（文档）→ `86f1617`（两份清单重锚，626 条）→ `b400f1c`（本轮记录改绑签出那一跑）→ `2bd0170`（收口补记进 CHANGELOG）→ 最后一笔证据重绑（`PROVENANCE.test_report` = 最终 HEAD 那一跑：`2202 passed / 0 failed`，`sha256` 前缀 `046c65036ef8`） |
| 又踩了一次的那条顺序 | `CHANGELOG.md` **在**清单里、`docs/audit/` 不在：把收口补记写进 CHANGELOG 之后，两份清单立刻与盘面对不上（`tests/test_packaging.py` 两条哈希断言当场判红，实测 2 failed）⇒ 再刷一轮清单与证据、并在最终 HEAD 上重跑一次签出全量。既有配方写着「补记必须在最后一次 `release_evidence.py` 之前」，本轮仍然先写了补记，代价是一整轮额外重放 |

| 文档镜像 | `docs/architecture/state_inventory.md` 页眉与正文 HEAD、版本清单表三处同步到 v21，并由 `TestTheDocMirrorMatchesTheChain` 与 `MIGRATIONS` 对账 |

## 七、几处自己抓自己的读数

1. 「只有两个写入口」这类结论必须由**不截断**的 grep 给出——本片沿用第 33 片的教训，
   `add_risk(` 的普查跑了全文（含 `scripts/`），才没把旧 CLI 那一处漏掉。
2. 新建的常驻用例一度用 `sqlite3.connect(...).execute(INSERT)` 而没有提交：
   Python 的 sqlite3 对 DML 开隐式事务，夹具写完没落盘 ⇒ 断言读到的是自己没提交的东西。
   统一改成 `with sqlite3.connect(...) as raw:`。
3. 「默认视图不泄漏内部编号」这条判据一开始写成「整段渲染文本里没有 `RISK-`」，
   与既有契约的口径（`<details>` 之前的正文）不一致，会把折叠区里本该出现的编号判成泄漏。
   改成按折叠边界切两段，两侧各断一边：正文不许有编号，折叠区必须还有编号。
4. 收尾复算不用 `git diff` 当哨兵——工作树本来就带着本片未提交的改动，
   那是「干净」的反面而不是残留。电池改为开跑前快照、收跑后逐字节比对。
