# 第 26 片：ECR/ECO 工程变更单（生产者落地，C6 档位 13/1/1 → 14/0/1）

关联：C6 生产图纸包交付物「② 版本与ECR/ECO」｜日期：2026-09-25｜
落点：`src/aipd_os/change_orders/eco.py`、`src/aipd_os/cli/commands_eco.py`、
migration v19｜能力行 `industrialize.change_control`。

## 一、为什么补这一格

`scripts/c6_coverage.py` 的判据是「有没有产品侧生产者」，这一格长期停在 `checker_only`，
note 里明写着原因：**版本那一半有生产者（三份 manifest + 门禁真读），
变更单那一半零实现**。本仓有 `changes` 表，但它是**审计流水**（谁在什么时候改了什么），
不是**工程变更单**。两者差三件事：

1. 变更单要能回答「谁**批准**了这项变更」——审计流水里没有批准这个动作；
2. 要能回答「影响哪些件、改前是什么、改后是什么」——审计流水记的是事后事实，不是事前范围声明；
3. 要能回答「生效了没有、复验了没有」——这是闭合，不是又一条记录。

## 二、选型检索：为什么只能本地实现（访问日 2026-09-25）

**先说清楚检索是谁做的**：本节 OSS 仓库侧的清单由一个派出的研究子代理实读 GitHub API/raw
文件后回报；其中两条我**自己复核过**（frappe 的审批判据、NASA 接口大纲），
其余条目我没有二次打开，标为「子代理回报」。标准正文那一档**没有读到**，因此不引用其内容。

| 候选 | 它实际提供什么 | License | 活跃度 | 功能匹配度 | 安全风险 | 代码质量 | 适配成本 |
|---|---|---|---|---|---|---|---|
| **frappe/erpnext**（子代理回报：`git/trees/develop` 全树按 `change_note`/`eco`/`engineering` 检索 0 命中；tags v13/v14/v15 亦 0） | **没有 ECO/ECR doctype**。最贴近的是 `BOM Update Log`（Queued/In Progress/Completed/Failed/Cancelled）与 Quality Action/Non Conformance——都不是变更单 | GPL-3.0 | 活跃（2026-09-25 有推送） | 低：要装 MariaDB + Redis + bench 整套平台 | 低 | 高（553 测试文件、496 迁移） | 不可行：本仓是 Python 3.9 + stdlib + SQLite |
| **frappe 工作流引擎**（`frappe/model/workflow.py` 的 `has_approval_access`，**我已自行核到该函数**，判据原文 `user == "Administrator" or transition.get("allow_self_approval") or user != doc.get("owner")`） | 不是 ECO，是「状态机 + 不许自批」的**形状** | MIT | 活跃 | 中：借模型不借码 | 低 | 高 | 只借一条判据 |
| **Odoo `mrp_eco`**（子代理回报：odoo/odoo 16/17/18 公开树里**没有该模块** ⇒ 企业版；文档页读到 stages `New/In Progress/Validated/Effective`、`Apply on`=BOM/Product、Revision=归档的 BOM 副本、BoM/Operation Changes 差异页） | 完整 ECO：影响清单、版本副本、逐阶段审批人 | core LGPL-3.0，模块取不到 | — | 高（正是要的东西） | 低 | — | **不可得**：源码不在公开仓库 |
| **OmniaGit/odooplm 18.0**（子代理回报 `plm/models/plm_mixin.py`：`draft→confirmed→released→undermodify→obsoleted`、`PLM_NO_WRITE_STATE` 冻结写、un-release 需 admin 组） | 状态机 + **released 之后冻结写**；真正的 ECO 仍代理回企业版 `mrp.eco` | plm LGPL-3，相邻模块 AGPL-3（copyleft 传染性对本仓不友好） | 2026-09-24 有推送、156★ | 中：状态机与冻结规则可借 | 中（AGPL 混层） | 中（25 测试文件） | Odoo + Postgres 绑定 ⇒ 只能借形状 |
| **Microsoft Dynamics 365 ECM 文档**（子代理回报，公开页） | ECR/ECO 两个对象、`Impacted products` + 每行 change type、生命周期 **Approve → Process → Complete**、未批准不能 Process | 专有（只读文档） | 2026-06-22 更新 | 高：这是最干净的生命周期参照 | 低 | — | 借模型 |
| **PLM 开源横扫**（子代理回报：`topic:plm`、`"engineering change order" in:desc` ⇒ nanoPLM（MIT，2025-07 后停、无变更对象）、PLMore（GPL-3，main 树 404）、ArasLabs change-management（MIT，2018 死）、若干 0–1★ 且**无 LICENSE** 的 ECOFlow 克隆；Aras Innovator Community 免费**使用**但不开源；partcad（Apache-2.0）用 git/包做版本，无 ECO；PyPI 无 ECO 包） | — | 混合 | 多为停滞 | 低 | **高**：无 LICENSE 的仓库不可合法引入 | — | 不可行 |

**没读到、因此不引用的**：MIL-STD-31000 / MIL-STD-973 / ISO 10007 / GJB 与 DoD 手册正文
（子代理回报 quicksearch.dla.mil DNS 失败、assist.dla.mil 抓取失败、everyspec.com 403、iso.org 403；
`cmii.org` 是停放页）。另注：它检索 `EIA-812` 时只命中安全帽标准 ⇒ **那条是错的线索**，
本仓不引用。NASA 侧我自行取到的是《SE Handbook》**附录 L 接口大纲**（属 ICD 议题，见 §七），
与变更单只沾「§1.3 Responsibility and Change Authority」这一条边。

**选定：本地实现，只借模型。** 单一最强理由：**可依赖形态的 ECO 实现在开源世界里不存在**
——真正有 ECO 实体的两家（Odoo、Dynamics）分别在企业版与专有云里，唯一活跃的开源 PLM
自己把 ECO 代理回企业版模块。本仓的约束（Python 3.9 + stdlib + SQLite、不引重依赖）
下，「引入依赖」这条路根本不通。借来的三件事：Approve→Process→Complete 的生命周期、
released 之后冻结影响清单、`user != owner` 的不许自批。

## 三、实现落位

**migration v19（`state/migrations/{helpers,definitions}.py`）** 建三张表 + 三条索引：

- `eco_records`：`creator` 与 `approver` 是**两列**，`approver` 无默认值。
  这一条是刻意的：本仓 `gates.approved_by TEXT NOT NULL DEFAULT 'AI-internal'`
  （`state/migrations/schema.py:173`，`scripts/aipd_store.py:135` 同形）意味着
  **任何写入点不写审批人，读出来也像「AI 批过了」**。ECO 不抄这个形状；
  那个既有缺陷另记（§七）。
- `eco_affected`：`(object_type, object_id, change_type, before_sha256, after_sha256)`，
  `ADD` 要改后、`REMOVE` 要改前、`UPDATE` 两头都要；**任何给了值的哈希必须像 sha256**
  （64 位小写十六进制，入库前归一化大小写）。
- `eco_transitions`：只追加。仓储层不提供任何 `update_*/delete/remove/set_*` 入口
  （有一条用例按方法名扫 `dir(store)`，防以后有人顺手加一个「修正历史」的口子）。

**`change_orders/eco.py`** 的状态机：

```
DRAFT → PENDING_REVIEW → APPROVED → IMPLEMENTED → VERIFIED
      ↘                      ↘            ↘
        REJECTED / SUPERSEDED（各阶段可分支；SUPERSEDED 必须指出替代它的那张单）
```

守卫（全部在写之前判，判不过就抛，不留半成品）：转移必须查表合法；**决策类转移
（APPROVED/REJECTED）要求 actor 是真人且 ≠ creator**；机器身份表
`NON_HUMAN_ACTORS`（含空串与 `AI-internal`）在**建单作者**与**审批人**两处都用；
空影响清单不许批准；`IMPLEMENTED` 要 `evidence_ref` + 可解析的 `effective_at`，
`VERIFIED` 要自己的复验凭据；`SUPERSEDED` 的 `evidence_ref` 必须指向同作用域内
**另一张已存在**的单；离开 `DRAFT` 后影响清单冻结。写库走带 `version=?` 的 CAS，
撞空 ⇒ `ConcurrentModificationError`（不是静默覆盖）。

**CLI（4 个公开命令，51 → 55）**：`eco create` / `eco affected` / `eco transition` /
`eco show`。退出码：0 成功｜1 单据不存在｜2 输入不合法｜**4 状态机拒绝**。
4 单独占一档是必要的：被拒的批准如果退 0，脚本就会把「张三批了自己的单」读成成功。

**能力行与散文同批改**：`registry_data.py` 新增 `industrialize.change_control`
（含 `current_limitation` 里的三条边界）；`scripts/c6_coverage.py` 的
「版本与ECR/ECO」升到 `producer`（14/0/1），note 里明写「发布门还没读 ECO」；
`tests/test_c6_coverage.py` 的棘轮同批重算；`SKILL.md`/`README.md` 补命令名；
`docs/architecture/state_inventory.md` 的 HEAD 从 v18 改 v19 并登记 v19 行。

## 四、常驻用例（`tests/test_change_order_eco.py`，42 条）

开单与作者（5）、影响清单带哈希（7）、状态机拒非法转移（4，含 CAS 注入）、
不许自批（4，含「被拒的转移不留任何痕迹」、「approver 在真人批之前恒为空」）、
凭据（5）、只追加流水（4）、读侧与作用域（3）、表形与查询计划（2）、
CLI 面（6）、migration v19 up/down 与新库/老库收敛（2 条在 `TestMigrationV19`）。

一处口径值得单说：`test_a_concurrent_writer_is_a_conflict_not_a_silent_overwrite`
要在「读单据」与「带版本写」之间塞进另一个写者才能开火；它用 monkeypatch 注入，
并**自己作证注入发生过**（`bumped` 断言），否则这条会静默退化成空转。

## 五、变异电池（`/tmp/slice26-mutations.py`，19 条：**杀 19 / 活 0 / 注入无效 0**）

每条注入先跑对照组（未注入的同一批 node id 必须绿）再记账——第 25 片就是这么抓到
「pytest rc=4 被当成杀掉」的。两处电池教自己的地方：

1. **G19 第一轮是个化妆注入**：它只把索引改名，列序不变 ⇒ 查询计划不变 ⇒ 行为等价，
   「存活」不代表没闸。换成**删掉**服务热查询的 `idx_eco_affected_object` 之后，
   新加的两条用例（索引列序 + `EXPLAIN QUERY PLAN` 必须走这条索引）立刻开火。
2. **G5 第一轮存活是真缺口**：可选那一格（`ADD` 的 `before_sha256`）没人查，
   「给了个不像哈希的东西」会被存下来。补 `test_the_optional_side_still_has_to_look_like_a_hash`
   之后开火。

其余 17 条逐条开火：摘掉不许自批（G1）、决策不要求真人（G2）、机器身份可当作者（G3）、
不要求前后哈希（G4）、送审后仍可改清单（G6）、空清单可批准（G7）、无凭据算已实施（G8）、
生效时间不解析（G9）、复验不交凭据（G10）、SUPERSEDED 指向不存在的单（G11）、
转移表不拦（G12）、CAS 撞空不报（G13）、流水 actor 抄成 system（G14）、
approver 预写成 `AI-internal`（G15）、未闭合过滤摘掉（G16）、
CLI 把被拒的转移退成 2/把缺哈希退成 0（G17/G18）。

## 六、端到端实测（命令行，一次真实走通）

```
$ aipd eco create --db /tmp/eco26/state.db --project C6 \
    --title "Ø8 孔从 x=25 移到 x=30" --creator 张三 --reason "装配干涉"
ECO-001｜ECO｜DRAFT｜Ø8 孔从 x=25 移到 x=30（创建人 张三）                                    rc=0
$ aipd eco affected --db ... --id ECO-001 --object-type drawing --object-id BRK-1.dxf \
    --change UPDATE --before-sha256 aaaa…(64) --after-sha256 bbbb…(64)                        rc=0
$ aipd eco transition --db ... --id ECO-001 --to PENDING_REVIEW --actor 张三                   rc=0
$ aipd eco transition --db ... --id ECO-001 --to APPROVED --actor 张三
eco transition：ECO-001：创建人 张三 不能自己批准自己开的单（不许自批）                          rc=4
$ aipd eco transition --db ... --id ECO-001 --to APPROVED --actor 李四
ECO-001 → APPROVED（批准人 李四）                                                             rc=0
$ aipd eco transition --db ... --id ECO-001 --to IMPLEMENTED --actor 李四
eco transition：ECO-001：进 IMPLEMENTED 要交落地凭据 evidence_ref（改了哪一版/哪次发布），
没有凭据就是自称已实施                                                                          rc=4
$ aipd eco show --db ... --id ECO-001
ECO-001｜ECO｜APPROVED｜Ø8 孔从 x=25 移到 x=30
  创建 张三 @ 2026-09-25T05:29:07+00:00｜批准 李四 @ 2026-09-25T05:29:08+00:00｜凭据 —｜复验 —
  影响 [UPDATE] drawing/BRK-1.dxf  aaaaaaaa→bbbbbbbb
  (建单)→DRAFT by 张三 @ 2026-09-25T05:29:07+00:00：建单
  DRAFT→PENDING_REVIEW by 张三 @ 2026-09-25T05:29:07+00:00
  PENDING_REVIEW→APPROVED by 李四 @ 2026-09-25T05:29:08+00:00                                  rc=0
```

「凭据 —」那一格在 `rc=4` 之后仍为空，是这条链最重要的证据：**被拒的转移没留下任何痕迹**。

## 七、这一片没做的事

- **发布门还没读它**：`production_release_gate.py` 不检查「自上次锚定发布以来 manifest
  哈希有差，却没有一笔闭合的 ECO」。这才是这张表真正的牙齿所在，做成下一片
  （需要在 gate 里读 state.db 或读一份由产品侧写出的 ECO 摘要，选路要先想清楚）。
- **署名是声明，不是证据**：本仓没有身份源（谁真的是「李四」），`actor` 只是字符串。
  「不许自批」能机器保证，「这个 actor 真有本人授权」不能——写进能力行的 limitation。
- **`gates.approved_by` 的 `DEFAULT 'AI-internal'` 仍在那个形状上**（两处 DDL +
  `supply_chain/writeback.py` 传的是 `"supply-chain"`，即程序自证）。这片只保证
  **ECO 不复用**它；改它涉及既有读侧与「AI 不自批」这条属主规矩的落点范围，属主裁。
- ECR 与 ECO 共用一张表一台状态机（只靠 `kind` 区分），没有独立的评审记录/签名页/会议；
  没有「变更影响分析」的定量计算（尺寸链重算、成本重算都不联动）。
- 没有变更单的可视化产物（PDF/表格），也没有回写 Product Truth 的失效传播
  （`truth propagate` 那条链不认识 ECO 这个对象类型）。
- 未接 `release_manifest`：`aipd release manifest` 不看 ECO 是否存在或闭合。

## 八、收尾读数（落盘后由量具复算，不是计划）

提交：`eb2304c`（代码 + 用例 + 文档）→ `ce6f9a2` / `5aff2f6` / `3b20cef`（发布工件重锚三步）。

| 量具 | 读数 |
|---|---|
| 全量 pytest（`docs/audit/pytest-report-v5.6.0.json`） | **2000 passed / 0 failed / 3 skipped**（共 2003；上一片收尾 1958/0/3=1961，本片 +42 条） |
| `PROVENANCE.json` | `test_report.{passed:2000, failed:0, total:2003, source_commit:a66040520139…}` |
| `SOURCE_MANIFEST.json` | 被哈希面 **607 → 611**（新增 4 个：`change_orders/{__init__,eco}.py`、`cli/commands_eco.py`、`tests/test_change_order_eco.py`） |
| `production_release_gate --release-ready --tag v5.6.0` | rc=0，`release_ready: true`，8/8 |
| `ruff check src tests state_service` / `mypy` | 均 rc=0 |
| `scripts/c6_coverage.py --self-test` | 7/7；档位 **14 / 0 / 1**（本片把「版本与ECR/ECO」升 producer，`checker_only` 归零；`absent` 只剩 ICD，理由写在它自己的 note 里） |
| 变异电池 `/tmp/slice26-mutations.py` | **19 条：杀 19 / 活 0 / 注入无效 0**（两条过程读数见 §五） |

一处闸真的咬到了人的读数：第一次重锚时，报告是在「RELEASE_MANIFEST 已刷新、
SOURCE_MANIFEST 还没重写」的窗口里跑的，那条 `test_source_manifest_hashes_match_disk`
红了并被如实写进 `PROVENANCE.test_report`；gate 于是**拒绝放行**
（`test_numbers_from_report`：`test_report has 1 failed`，rc=2）。
没有把这格当噪声绕过去，而是等工件一致之后重跑一遍报告与 `release_evidence`，
再放行 —— 这正是 `failed>0` 这一格存在的意义：**锚点窗口内的红也算红**。
