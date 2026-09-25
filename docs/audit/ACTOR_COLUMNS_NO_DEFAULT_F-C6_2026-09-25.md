# F-C6 第 35 片：三张表的 actor 列不再自带 `'system'`

日期：2026-09-25　范围：`state/migrations/{helpers,definitions}.py`（v22）、`state/db.py`、
`idea/evidence_relations.py`、`product_intelligence/snapshot.py`、
`tests/test_actor_columns_no_default.py`（新）、`tests/test_risk_ownership.py`（镜像对照改由链尾现算）、
`CHANGELOG.md`、`README.md`、`docs/architecture/state_inventory.md`。

## 一、这一格以前是什么状态

第 34 片收尾时把剩下的同族位点写成了「本片没审计」。这一片先补那次审计，
再决定做什么——结论和前两片**不一样**，所以定性也不一样。

去截断重跑 `grep -rn created_by`（含 `scripts/`、`tests/`）后的实测：

| 事实 | 证据 |
|------|------|
| 三根列自带机器默认值 | `claim_evidence_relations.created_by`、`product_definition_snapshots.created_by`、`product_definition_commits.actor` 都是 `TEXT NOT NULL DEFAULT 'system'`；声明文本两份（`migrations/definitions.py`、重建用的 `migrations/helpers.py`），参考 SCHEMA 一处（`state/db.py`） |
| 产品写入口都显式传 actor | `idea/evidence_relations.py:217,247`、`product_intelligence/snapshot.py:345`（构造时 `created_by=actor`）、`product_intelligence/gate.py:491`（INSERT 第 10 位绑 `actor`）、`execution/research_integration.py:265` |
| `from_dict` 今天够不到那条兜底 | 四个调用点喂的都是数据库行：`evidence_relations.py:169`、`evidence_graph.py:41`、`snapshot.py:382,391` ⇒ 列必然带着键 |
| 没有任何读者拿它做判定 | 全仓没有一处按 `created_by`/`actor` 过滤或分支；读者只有 `to_dict`/`to_public_dict`（`evidence_relations.py:107`、`snapshot.py:246`）这一类「往外发」 |
| 数据类自己还带一份默认值 | `evidence_relations.py:75`、`snapshot.py:188` 都是 `created_by: str = "system"`；`from_dict` 的兜底 `data.get("created_by", "system")` 同形 |

⇒ **这一族没有一条正在跑的假读数**。它的危害是时序性的：下一个漏传 actor 的写入口
会静默写出 `'system'`，而序列化会把这个戳当归属对外发出去。
这一片据此定性为「关掉将来那条路」，不写成「纠正了一条在跑的假账」。

## 二、修法与两个决定

migration **v22 `actor_columns_no_default`**：拷贝重建这三张表。

- 决定 A：**保留 `NOT NULL`，只摘掉 `DEFAULT`**。
  与前两片（v20/v21 放开可空）不同——那两列的语义里「没人」是合法状态；
  这三列的语义是「必须有归属，只是不许编一个」。摘掉 NOT NULL 会把
  fail-closed 一起丢掉，所以漏传必须撞 `IntegrityError`（有常驻用例钉这条报错）。
- 决定 B：**DDL 模板照 `sqlite_master` 的 HEAD 实形抄，不照当初声明它的那句迁移文本抄**。
  实测到一处既存漂移：`claim_evidence_relations.strength` 在 v6 的重建里掉了
  `NOT NULL DEFAULT 0.5`（HEAD 实形是裸 `strength REAL`）。照声明抄等于顺手把这条
  漂移往另一个方向改，那是另一件事，该单独测、单独登记。
- up/down 只差 `{actor_ddl}` 这一格，列清单两边共用一份常量 `_V22_ACTOR_TABLES`；
  两个方向都不改写历史值。
- 三张表实测**都没有具名索引**（只有 PK/UNIQUE 的隐式索引，随建表语句一起带走）
  ⇒ 重建不降级任何热查询。
- 同步改代码侧两处编造点：数据类字段 → `created_by: str | None = None`，
  `from_dict` → `data.get("created_by")`，出参保持原样 ⇒ 没归属就发 `None`。

## 三、动手与测试中被推翻/自抓的三条

1. **夹具自己先红了一次**：`claim_evidence_relations` 的 UNIQUE 不含 `relation_id`，
   造多行时只换主键当场撞 `UNIQUE constraint failed` ⇒ 加了 `_UNIQUE_BEARERS`
   把每张表参与 PK/UNIQUE 的列逐行错开。这条不是产品缺陷，是 fixture 的正确性。
2. **逐列值往返保真**（第 34 片 J15 的教训直接复用）：只填最小列集时，
   「重建的列清单少一根」看不见（那一列本来就是 NULL）。
   `_full_row` 改为按 `PRAGMA table_info` 把**每一列**都填上值，
   往返后 `SELECT *` 整行相等；电池 K4 从列清单里删掉 `committed_truth_refs_json`
   就是这样被抓到的。
3. **上一片的镜像对照差点变成假绿**：`test_risk_ownership.py` 里那两条注入对照
   写死了 v21（`"| v21 | ... |"` 与 `"HEAD = **v21**"`），v22 进链后一条红在断言、
   一条开始看不见东西 ⇒ 改成由 `MIGRATIONS[-1]` 现算链尾，并加「链尾那一行在表里
   必须恰好一处」的前提断言。

调研豁免声明：本片沿用同族前三片（v20/v21）已确立的重建配方，无新技术选型空间，
按「影响范围明确的局部改动」豁免外部检索。

## 四、端到端实测

- 建库后三根列：`notnull=1`、`dflt=None`；`risks.owner`/`gates.approved_by` 仍是可空无默认（前两片的形状没被动）。
- 漏传 actor 的直接 INSERT ⇒ `sqlite3.IntegrityError: ... NOT NULL constraint failed`（三张表各自一条参数化用例）。
- 带 actor 的 INSERT ⇒ 照常落盘读回（合规侧，防「永远红」）。
- v21 老库升上来与新建库逐列同形；`up` 保住历史里的 `'system'`；`down` 还原 `DEFAULT 'system'` 且值不变；
  三行 × 三表全列往返后 `SELECT *` 完全相等。
- 全仓产品测试没有一条因为「写入口原先在靠默认值」而红 ⇒ 与 §一 的结论一致：
  这一族的默认值确实够不到（如果够得到，摘掉它就会当场炸）。

## 五、这一片没做的事

1. **`strength` 那条既存漂移没修**（v6 重建掉了 `NOT NULL DEFAULT 0.5`）：
   它是「声明文本与实形不一致」的另一族问题，需要单独测「谁在依赖那个默认值」再动，
   已记入 §二 决定 B。
2. **没把 `created_by`/`actor` 接进任何门禁或读侧视图**：今天没有读者拿它判定，
   接进门禁等于凭空造一条判据（与第 32 片「只报不判」同一立场）。
3. **`scripts/aipd_store.py` 那份废弃旧库 DDL 未动**（同前两片）。
4. **服务/HTTP 写面仍未暴露这些 actor 入参**：要真填进「谁建的」，
   得先定身份源，这不属于本族。

## 六、收口读数（已实测部分）

| 项 | 读数 |
|----|------|
| 全量用例 | 2205 → **2227**（+22，全在 `tests/test_actor_columns_no_default.py`）；工作树整跑 **2222 passed / 2 failed / 3 skipped**，两条红只有 `test_release_manifest_hashes_match_disk`、`test_source_manifest_hashes_match_disk`（清单尚未重锚，属预期） |
| 变异电池 | `/tmp/slice35-mutations.py` **12 条：杀 12 / 存活 0 / 注入无效 0 / 崩溃式红 0**，每条带未注入对照臂；已知无撤回案例 3（合规侧对照、V1 冻结文本那条、fixture 自身的唯一约束） |
| 静态检查 | `mypy src` 0 error；`ruff check src tests state_service` rc=0 |
| 文档镜像 | `state_inventory.md` 页眉/正文 HEAD 与版本清单三处同步到 v22；对账尺子 `TestTheDocMirrorMatchesTheChain` 已改为由链尾现算 |

| 签出 attestation | `git worktree` 的 HEAD 干净签出 + `AIPD_SOURCE_COMMIT=<tag SHA>`：**2224 passed / 0 failed / 3 skipped**（2227 收集），报告 `sha256` 前缀 `edaea5330b97` 已绑进 `PROVENANCE.test_report` |
| 发布门 | `production_release_gate --release-ready --tag v5.6.0`：**8/8、rc=0、`release_ready: true`**（带 venv PATH；第一次跑 7/8 只欠 `workspace_clean`，因为证据产物尚未提交，提交后归零） |
| 仓库审计 | `audit_repo --strict` rc=1，唯一一条红仍是既有的「Provenance source commit mismatch（锚点 = tag，HEAD 在后）」，两份清单 `hash_mismatch_count = 0` |
| 六片电池同树重放 | 第 30 **21/21**、31 **8/8**、32 **14/14**、33 **9 杀+2 已知无撤回**、34 **15/15**、35 **12/12**，全部 rc=0（每条带未注入对照臂） |
| 提交序列 | `d1f891d`（代码+用例+文档）→ `3fb32ad`（两份清单重锚，627 条）→ `7bc7354`（证据绑签出那一跑）→ 本笔文档 |
