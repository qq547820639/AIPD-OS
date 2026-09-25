# F-C6 第 36 片：迁移的「重建保真」常驻尺子

日期：2026-09-25　范围：`tests/test_migration_rebuild_fidelity.py`（新）、
`CHANGELOG.md`、本文件。产品代码零改动。

## 一、为什么要有这把尺子

这一族的修复（v20/v21/v22）全靠**拷贝重建**：V1 冻结文本改不得，SQLite 又没有
`ALTER COLUMN`。重建最容易出的事故不是「没改成」，而是**顺手动了别人**——
列清单少一根、某一列的 `NOT NULL` 或默认值在搬运中掉掉。这类事历史上真发生过一次：
`claim_evidence_relations.strength` 的 `NOT NULL DEFAULT 0.5` 不见了
（第 35 片的 §三.4 记录了我如何把它误读成「漂移」，实情是 v9 有意改成可空评分）。

今天链上「改变已有列形状」的迁移一共只有 6 处，全部是**有意的**、有据可查的：

| 版本 | 改动的列 | 理由 |
|------|----------|------|
| v9 `nullable_scores_and_legacy_sequences` | `claims.confidence`、`claim_evidence_relations.strength` | 评分不再自带 0.5 哨兵，None=未评分 |
| v20 `gates_approved_by_no_default` | `gates.approved_by` | 第 32 片：没人批不许读成 AI-internal 批了 |
| v21 `risks_owner_no_default` | `risks.owner` | 第 34 片：没人负责不许读成 AI 负责 |
| v22 `actor_columns_no_default` | `claim_evidence_relations.created_by`、`product_definition_snapshots.created_by`、`product_definition_commits.actor` | 第 35 片：摘掉自带的 `'system'` |

尺子做的事：把这 6 处写成**声明清单**，然后逐格重放并断言「这一格改的列集合 == 声明的集合」。
双向：多一处会红（新增漂移），声明的那一处不再发生也会红（清单变成摆设）。
新增列（建表、`ADD COLUMN`）不在射程内——那是链的常态，钉它只会制造噪音。

## 二、轴选错一次，尺子差点是自证的

第一版的基线取法是「建到 HEAD，再 `rollback(path, N-1)`」。**错**：
rollback 会执行第 N 格的 down，而 down 用的正是同一份重建模板 ⇒
拿到的「before」已经被这一格自己刷过一遍，与 after 比自然「零变化」。
这条轴上任何漂移都看不见，而且它**会绿**。

改成前进式：临时把 `runner.MIGRATIONS` 截到 `< N` 再建库（`runner.py:74` 按名字读模块全局，
所以可截），基线就与第 N 格无关了。实测：v20/v21/v22 各自只改声明的那几列，
`review_status` 等列在 v21 与 HEAD 上都是 `('TEXT', 1, "'pending'")`。

## 三、三处自抓

1. **反向对照第一次空放**：注入选的是「丢 `DEFAULT 'pending'`」，
   而这张表的默认值早被历史重建搬空 ⇒ 注入了等于没注入，断言照样「通过」。
   换成「丢 `NOT NULL`」（v21 基线上确实是 `notnull=1`）才真的开火，
   并把前提断言写成 `patched_body != body and "NOT NULL DEFAULT 'pending'" not in patched_body`。
2. **电池 L1 的锚点命中 3 次**：`review_status TEXT NOT NULL DEFAULT 'pending',`
   这一句在 v6/v9 那几份老重建里也有 ⇒ 按纪律记「注入无效」而不是杀掉，
   重锚到带 `{actor_ddl}` 占位的相邻行后才唯一。
3. **电池 L1 的 target 打错格子**：v22 本来就在声明清单里，
   所以「其它格不许改形状」那条按定义看不见它；那条判据的拥有者是
   `test_the_declared_versions_still_change_exactly_those_columns[22]`。
   打错时电池记的是「存活」（不是假绿），改打之后 4/4 杀掉。

## 四、这一片没做的事

1. **没有把「谁依赖某个默认值」写成判据**：尺子只管形状，不管语义。
   若某条产品路径确实依赖默认值（v9 之前的 0.5 哨兵就是这种历史），
   要靠各自的用例钉，不在这把尺子的射程内。
2. **`scripts/aipd_store.py` 那份废弃旧库 DDL 未纳入对账**（同前三片）。
3. **视图不在射程内**：今天链上没有视图；索引与触发器已在同一片内补成第二根轴（见 §二.1）。
4. **`sqlite_autoindex_*` 不在射程内**：那是 PK/UNIQUE 的隐式索引，`sql` 为 NULL，
   名字还会随重建顺序变，纳入只会制造噪音——列的对账已经覆盖了约束本身。

## 五、收口读数

| 项 | 读数 |
|----|------|
| 新增常驻用例 | **11 条**（`tests/test_migration_rebuild_fidelity.py`：形状轴 8 + 索引轴 3），全量 2227 → **2238**（工作树整跑 2233 passed / 2 failed / 3 skipped，两条红只有清单哈希锚点，属未重锚的预期） |
| 变异电池 | `/tmp/slice36-mutations.py` **4 条：杀 4 / 存活 0 / 注入无效 0 / 崩溃式红 0**，每条带未注入对照臂；已知无撤回案例 1（白名单存在性那条，撤回面已被逐格对账覆盖） |
| 静态检查 | `mypy src` 0 error；`ruff check src tests state_service` rc=0 |
| 产品代码 | 零改动（本片只加尺子与登记） |
| 索引轴实测 | 21 格逐格前进式重放：具名索引/触发器「被丢掉」0 处、「定义被改写」0 处；
  v20/v21/v22 三次重建都没有漏带回任何索引（`gates`/`risks` 在 HEAD 上没有具名索引，
  `claim_evidence_relations` 等三张表也没有）|
| 签出 attestation | `git worktree` 的 HEAD 干净签出 + `AIPD_SOURCE_COMMIT=<tag SHA>`：**2232 passed / 0 failed / 3 skipped**（2235 收集，3m41s），报告 `sha256` 前缀 `ec9defd49bc7` 已绑进 `PROVENANCE.test_report` |
| 发布门 | `production_release_gate --release-ready --tag v5.6.0`：**8/8、rc=0、`release_ready: true`**（带 venv PATH）|
| 仓库审计 | `audit_repo --strict` rc=1，唯一一条红仍是既有的 tag 锚点判定；两份清单 `hash_mismatch_count = 0`（新尺子入册后 628 条）|
| 电池重放 | 收尾时在最终树上重跑：第 34 片 **15/15**、第 35 片 **12/12**、第 36 片 **4/4**，全部 rc=0、字节复算干净 |
| 提交序列 | `b7e7adb`（尺子+登记）→ `47f7036`（清单重锚 628 条）→ `06cedb5`（证据绑签出那一跑）→ 本笔文档 |
