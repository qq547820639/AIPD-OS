# Truth Architecture：三种状态维度与 Truth 演进（P1-3）

> 目标：明确「一个事实/结论的认知状态」如何表达，避免把 *epistemic status*、
> *lifecycle status* 与 *confidence* 混为一谈；并说明 Idea Truth → Product Truth →
> Engineering Truth 的同构复用。

## 1. 三种维度，互不替代

| 维度 | 取值 | 定义位置 | 语义 |
|---|---|---|---|
| **epistemic_status** | `V` / `S` / `C` / `E` / `A` / `P` / `T` / `R` / `U` | `state/db.py` `FACT_STATUSES` | 事实的**认知分类**（verified / simulation / constraint / estimate / assumption / plan / target / requirement / unknown 等）。它不是「新旧」，而是「这是什么类型的主张」。`U`=Unknown / 未验证（无证据或未确认）。 |
| **lifecycle_status** | `active` / `stale` / `expired` / `blocked` / `superseded` | `product_truth/models.py` `TRUTH_STATUS` | 记录的**生命周期**（当前是否仍被信任、是否需要返工/过期）。 |
| **confidence** | `[0, 1]` | `state/db.py` `add_fact(confidence=...)` | 连续**置信度**，用于排序/加权，不能单独决定可信级别。 |

> 注意：`FACT_STATUSES` 的 `S` 本义是 Simulation（模拟/仿真值）；`research/expiry.py`
> 历史复用 `S` 标记 stale（过期）。二者语义不同，已在该模块注释中警示，未来应引入
> 独立状态位区分。

关键区别：

- **UNKNOWN 不是 stale**。`stale` 表示「曾有效、现在因上游变化而过时，需返工」；
  「从未验证 / 无证据」应保持 `unverified` / `not_verified` / `U` 的 epistemic 状态，
  而不是标记为 stale。`product_truth/propagation.py` 的失效传播只把「受影响」
  的下游标 stale，绝不把「本来就没证据」的记录伪装成 stale 或 verified。
- **external evidence 必须经过适用性判断**。外部来源（论文/报告/供应商数据）
  到达后默认是 `unverified`/`low`；research 回写层写事实时默认 `E`（可靠外部
  证据），**绝不自动 `V`**（retrieval verified ≠ 命题 verified）。`assess_trust`
  的确定性规则（`product_truth/store.py`）只判断 provenance / lifecycle / 来源
  可用性：evidence 记录 → `high`（来源可信度，非 verified）、有上游链 → `medium`、
  无上游 → `low`；仅当显式 Owner/工程确认标记（metadata `confirm_by_owner=True`）
  才返回 `verified`。

## 2. Idea Truth → Product Truth → Engineering Truth 同构复用

三个阶段共享同一记录模型（`TruthRecord`：record_type / content / source /
trust_level / effective_at / expires_at / version / status / metadata），
区别仅在 `record_type` 与来源约束：

| 阶段 | record_type 示例 | 来源约束 |
|---|---|---|
| Idea Truth | assumption / ctq | 需求/构想陈述，低可信起步 |
| Product Truth | fact / requirement / evidence / risk / decision | 须有 evidence 或上游依赖才可 verified |
| Engineering Truth | artifact_version / verification 结果 | 绑定 CAD/BOM/验证产物（artifact_version + evidence） |

同构复用意味着：一套 `ProductTruthStore` + `LineageGraph` + `PropagationEngine`
即可服务三个阶段；跨阶段传播（Idea 变更 → Product 受影响 → Engineering 返工）
沿同一条血缘图计算。诚实性约束：没有执行器时不返回假成功
（`run_rework(rework_fn=None)` → `blocked`，绝不 bump 版本）。

**可达性现状（2026-09-25，F-TRUTH-PROP-01）**：传播这一半已从产品面走得到——
`aipd truth propagate --db <state.db> --project <p> --upstream <id>` 调
`on_upstream_changed`（标 stale + 生成 `rework_tasks` 有界任务 + 产出 owner 可读四段
变更说明），`aipd truth tasks` 只读列待办。**返工的执行也已接上（2026-09-26，F-REWORK 第 45 片）**：
`aipd truth rework --task RW-xxx | --all-pending` 调 `run_rework` 并交真实执行器
（`src/aipd_os/cad/spec_rework.py`）——按当前 active CTQ 重算图纸声明：哈希一致**且**磁盘产物
仍匹配就一个字节都不动产物（`unchanged`，但库里的版本与 stale 真的收口）；内容变了、或文件被删/
被手改，就重写并补血缘边（`rewrote` / `file_restored`）；重算出 gap 一律判失败，交给引擎的
有界退避与 `max_attempts`。执行器认 `metadata.artifact` 为 `drawing_spec`（重算声明）、`drawing_dxf`（第 47 片：按记录的输入集合重跑出图，先出到暂存目录，只有 `drawing generate` 退码 0 才替换正式图纸——判未收口的重跑既不覆盖现状也不记成功）、`bom`（第 53 片：按当前 BOM 行演进这一条版本记录）与 `bom_cost`（第 49 片：按记录里的 BOM 与口径五项重跑核算）；不认识的制品（今天只剩 `quote_batch`）在
**烧 attempts 之前**逐条点名拒掉——「这格没有执行器」不许被伪装成「返工失败了三次」。
接线前那句「产品侧无人调用」现在反过来钉（`tests/test_truth_propagate_cli.py::`
`TestReworkHalfIsWiredAndItsBoundaryStaysVisible` 要求产品侧真有调用点），
边界本身由 `tests/test_truth_rework_cli.py` 逐条钉住。

**发现与触发（2026-09-26 更新，F-DRIFT 第 51 片 / F-DRIFT-2 第 52 片 / F-SWEEP 第 54 片 /
F-DRIFT-5 第 57 片）**：
上面所有"再跑一次 propagate"的前提是**有人记得跑**。现在这一环有两条命令：
`aipd truth drift` 只读地把每条有效制品记录的键**按当前世界重算**再比对
（`src/aipd_os/product_truth/drift.py` 分四态：一致 / 漂移 / 不可判 / 没有可比对的键；
一条记录可以交**多个输入面**，每面各自与同一条已存基线比，优先级是
漂移 > 没有基线 > 算不出 > 一致——"不可判"不许跨面折叠；
五类制品各有 resolver：`drawing_spec` 交两面（文件面重读声明文件、源面按记录自己的
`ctq_refs` 重跑一次 `spec_from_ctq`，第 57 片）、`drawing_dxf` 重算出图输入签名、
`bom` 读当前 BOM 头与行、`bom_cost` 用记录里的口径五项重算、
`quote_batch` 用记录里 `quote_ids` 读回的**当前报价事实**重算——
键不靠报价文件，因为 `quote_id`/`version` 是 apply 时按库内版本号现铸的，文件里没有，
而"会变的"只有事实态（`retire_stale_officials` 把 `V` 改 `R`）），
整表逐字段不变是断言不是叙述；
`aipd truth sweep` 把发现接落到刀（`src/aipd_os/product_truth/sweep.py` +
`cmd_truth_sweep`）：同一次进程内对「漂移且还 active」的记录按 `truth_lineage` 边表找上游，
用与 `truth propagate` **同一个**入口 `on_upstream_changed` 标 stale 并建任务，
边表里找不到上游的逐条点名不办。形状取自本轮开过的两页官方文档
（OpenTofu plan/apply、dbt `state:modified`），但**不落 plan 工件**：本仓的只读检测已经是
`truth drift`，再存一份就是把同一个事实存两处，还会引入"工件比现实更旧"。
代价面有一条常驻用例钉住（`tests/test_truth_sweep_cli.py::`
`test_hand_edited_spec_sweeps_to_the_ctq_and_rework_writes_the_file_back`）：
人手工改生成出来的声明文件 ⇒ sweep 落刀到那条 CTQ ⇒ `truth rework` 按 CTQ 把人改的文件覆盖回去。
这条语义不是 sweep 造的（propagate + 第 45 片执行器一直如此），但"一条命令就会走到"是本轮开始的。

**扫描成本现状（2026-09-26 量，F-DRIFT-4 第 55 片）**：`truth drift` / `truth sweep` 是这条链上
唯一会随交付物数量长期变大的读路径，所以它的成本形状被钉成两层。进程内实测：
5/20/100/300 条有效制品版本记录，`scan_drift` 走的 **SQL 条数不随记录数增长**（第 57 片前恒为 1 条，即一条 SELECT 取全集；第 57 片给 `drawing_spec` 补源面之后恒为 8 条：多出的 1 条 CTQ SELECT 与 6 条 schema 引导来自第二次 store 实例，都是每次扫描的固定开销），
声明文件**每条恰好读一次**，单条成本安静机器约 60~70 µs、同机负载 26 时读到 95~152 µs
（`scripts/state_perf_gate.py` 的两个 `drift_scan_*` 场景，趋势棘轮；
基线在负载下采到 131.24 µs 后已按安静读数重锚为 69.25 µs，方向是收紧）；两条线性度都由常驻用例钉死
（`tests/test_state_perf_gates.py::TestDriftScanScaling`，与机器无关，抓 N+1 与重复读）。
CLI 侧另测三档（4/13/33 条记录 × 两遍 × 7 次重复）：一趟命令墙钟 1.31~1.42 s，
**几乎全是解释器启动与 import**，扫描本体约 10 ms 量级、落在两遍读数的散布之内
（同机负载 5~11 时首趟还读到 4.2 s 的冷启动）。结论是不给产品面加 per-resolver 计时字段：
被启动开销淹没的读数没有读者，而"该不该担心扫描成本"这件事现在由门禁而不是由感觉回答。

**链头（2026-09-26 起，F-CTQ-PRODUCER 第 56 片）**：上面每一段都默认"库里已经有 CTQ"，
而本轮复核的结果是：`record_type="ctq"` 在 `src/` 侧**只有读者没有写者**
（`release_manifest.py:69`、`cad/spec_from_truth.py:55`、`cli/commands_drawing.py:86`、
`cad/spec_rework.py:91`（这条指针第 62 片按现码复核过：原来写的 84 已被后续插入推到 91——
指针不是取证件，写错就得改）），PI gate 只写 `requirement`/`feature` 且 Feature 模型里没有任何公差字段，
所以第二跳的输入此前只能由测试种出来。现在由 `aipd ctq add`
（`src/aipd_os/product_truth/ctq.py:declare_ctq`）补上：属主自述，七个必填项一次校验后才落库，
信任级复用 `product_intelligence/gate_criteria._derive_trust`——**没有 `--test-ref` 就是
`unverified`**，"有人提了要求"不等于"要求被验证过"（与 P0-08 同一条规则）。
两处形状值得记：① 同一个图纸尺寸上已有 active CTQ 时**点名拒**，因为
`spec_from_truth` 对两条抢一个尺寸的处理是把两条一起撤回，出图那天才发现更坏；
② `drawing spec` 在 0 条 active CTQ 时旧行为是"写一份 `features: []` + 落一条无引用血缘 +
退 0"，本轮改成判未收口（退 4，文件与血缘都不写，payload 多一格 `empty_declaration`）——
空声明不是交付物，"还没有人声明要求"不能被读成"声明已完成"。
第 56 片那条"钉缺席"的边界已在**第 57 片闭掉**（`tests/test_truth_ctq_add.py::`
`test_ctq_change_is_visible_to_drift_and_sweep`，同一条用例从"看不见"反成"必须看见"）：
改了 CTQ 限值 ⇒ `truth drift` 点名那条声明记录（理由写 `source面`）、`truth sweep` 落刀标 stale
并建返工任务 ⇒ `truth rework` 按新限值重写文件。判据形状借 Argo CD 实读的
"compares the current, live state against the desired target state"（两侧都现算、基线只存一份），
所以**没有新增 metadata 列、存量记录不需要迁移**：`spec_sha256` 本来就是声明正文的
canonical 哈希（`cad/spec_lineage.py:41`），文件面与源面各自与它比。
源面刻意**只吃记录自己声明的 `ctq_refs`**，不吃全作用域 CTQ——否则新增一条无关要求会把
每条既有声明都读成漂移；"声明是否覆盖了当前全部要求"归发布门禁 `gdt_covers_ctq` 那一格，
由 `tests/test_truth_spec_faces.py::test_unrelated_new_ctq_is_not_drift` 钉住不越界。
那一条门也在第 58 片从"按特征名求差"改成**按记录号求差**：两条 CTQ 可以共用同一个 `feature` 标签（`aipd ctq add` 只拦「同一图纸尺寸重复」，不拦标签撞车），名字的集合差会把"其中一条没上图"掩盖成 `all ctq features covered`；缺 `record_id` 一律判不可核，不退回按名字猜。钉子见 `tests/test_production_release_gate.py::test_two_ctq_records_sharing_a_feature_label_are_not_masked` 与链上真数据的 `tests/test_cad_spec_from_truth.py::TestCliProducerAndGate::test_a_requirement_arriving_after_the_declaration_is_not_masked`。
上游 CTQ 被停用/删除算**漂移**而不是不可判（输入读得到、算得出，只是算出来的东西说这份声明
立不住）；重算出缺口时用一个确定性的 `ctq-gap:` 键，不折进"算不出"。
**链头的改动入口（2026-09-27 起，F-CTQ-REVISION 第 59 片）**：第 56 片只给了 `add`，
于是"属主改了要求"此前只有两条路——人工按记录号 `store.update`（**不留审计**），或者改完之后
让第 57 片的源面把它读成漂移。现在补 `aipd ctq revise` 与 `aipd ctq deprecate`
（`src/aipd_os/product_truth/ctq.py:revise_ctq` / `:deprecate_ctq`）：修订**不改写原文**，
另起一条 active 新版本（`version = 被修订那条 + 1`），旧的标 `superseded` 并在 metadata 留
`superseded_by` / `superseded_at` / `superseded_by_actor` / `superseded_reason` 四个链字段，
两条命令都往 `audit_log` 落一行（actor 取 `--by`，before/after 是限值与检验方法的快照）。
退役态选 `superseded` 而不是 `expired` 是**出口判据**：`release_manifest.py:95-99` 对
`superseded` 只出非阻断点名（`blocking=False`，提醒"确认取代它的那条在名单里"），
而 `expired`/`stale`/`blocked` 走的是 `blocking=True` 那一支，会把这条要求永久留在阻断名单里。
形状借本轮实读的 dbt model versions（`latest_version` 决定未固定 `ref()` 指向哪一版；
`deprecation_date` 原文 "Deprecated models can continue to be built by producers and be selected
by consumers until they are disabled or removed."）与 django-simple-history 3.13.0 的
"历史行带 user 与改动理由"，**两个候选都只借语义、不引依赖**：本仓对 SQLAlchemy 是 0 引用
（全仓检索无命中），continuum 那条路前提就不在；而 Django 侧要求 3.10+，与本项目
`requires-python = ">=3.9,<3.13"` 的验证矩阵相撞。三处判据值得记：① 同值修订判"没变"
（不另起版本、不写审计行），否则审计次数会虚高于真实改动——这条是首轮 smoke 实测出来的；
② 审计写不进去判未收口（退 4 且 `--json` 的 `ok` 同向、`changed` 保持真），
"数据改了但没人知道是谁改的"不是干净成功；③ `--replaced-by` 给了就得真存在，
指向不存在的记录会骗过门禁那句"确认取代它的那条在名单里"。新用例还顺手抓出返工执行器缺
第 56 片的另一半守卫：撤回最后一条 CTQ 后 `aipd truth rework` 会把磁盘上那份声明重写成
`features: []` 并退 0，现在 `cad/spec_rework.py` 与生产者同形地判 `empty_declaration` 失败
（退 4，文件与记录都不动、返工任务留在 pending）。钉子见 `tests/test_truth_ctq_revise.py`
（14 条：修订形状 / 审计 / 门口就拒 / 链条 / 命令面镜像）。
**链头的读面（2026-09-27 起，F-CTQ-READER 第 62 片）**：上面两片给链头配了三个写者与四个读者，
但"这个图纸尺寸上现在有效的是哪几条、限值与版本各是几"只能读库——那条缺席正是第 60 片那把
`doc_command_census` 登记在 registry 限制句里、由只报面持续可见化的东西。现在补
`aipd ctq list`（`src/aipd_os/product_truth/ctq.py:363 list_ctq`、
`src/aipd_os/cli/commands_truth.py:543 cmd_truth_ctq_list`）。三处形状值得记：① 默认只列
`active`（与发布分母**的 active 过滤**同口径——分母还额外要求 `metadata.feature`，缺它的
active 记录门口判 `ctq_missing_feature` 阻断、这里照样列出），但**必须同时自报排除了几条、
各是什么态**（`excluded` 那格）——只报"1 条"会被读成"库里只有 1 条"，而
`aipd release manifest` 的 `ctq` 数组正是那个不说的形状，偏偏
"要求被撤了几条"是属主最该看见的；② 投影**复用**审计行用的那份 `_snapshot`，不在 CLI 里
重抄字段（等值断言 `records == _snapshot(活记录)` 是这条的钉子），所以生产面加列时读面跟着长，
不会出现"库里有、列不出"；③ 只读不写，一行 `audit_log` 都不落——那条通道要回答"谁改了事实"，
把每次查看都写进去它就答不出了（写侧的门是 `AIPDStateDB.add_audit`，`state/db.py:1073`）。
退码：读不出 2、成功 0；空作用域退 0 且明写「0 条 + 作用域」，与"没跑到"分开——
这一档跟的是 `cmd_truth_tasks` 那个纯列表面的先例（它同样退 0，并且专门打一行
"空列表不代表没有 stale 记录"），而不是 `truth drift` 那种扫描面的 `0/4`：
把"存在被合法停用的要求"和"有要求今天没收口"折进同一个退码是新的谎。
本轮电池留下一条排障账，记在这里因为它不是本项目独有的：给"读失败"写的**第一条**用例
（`--db` 指到一个不是 sqlite 库的文件）在变异对照下**活了下来**——那个输入在
`_open_store`（`commands_truth.py:24`）就被接住，命令里那段 try/except 根本没执行到，
于是"把读失败读成空清单"这个改动没让任何用例变红。补了第二条（让 `list_ctq` 真的抛在手里）
之后三臂全 KILLED，还原后复绿、文件 sha 复原；同一轮独立复核又抓出两处**读数说谎**并已修：
合格域原先用 `f"{low:g}"` 打（实测 `format(8.050001, 'g') == '8.05'`，限值被格式化改了数），
口径注原先写"superseded 是唯一能让一条要求退出分母的态"（重开 `release_manifest.py:67-103`：
退出分母的是**全部**非 active 态，superseded 特殊的只是不阻断）——两处各补一条常驻用例加一支
变异臂，终局 `6 KILLED / 0 SURVIVED`；复核提的第三项"有非 active 记录却退 0 不一致"经重开
先例判为**不成立**，理由见上一段。另有一条镜像卫生账：`aipd ctq list` 这个名字
被第 60/61 片当过夹具里"仍然没有"的那个幻影，注册它的那一轮两处用例当场报错、一处**静默空转**
（否定例外那一支——那行仍带"没有"标记，只是标记指向的命令已经存在），现在量具与用例的幻影名
统一由 `ghost()` 与 `zzz-` 前缀生成，`scripts/doc_command_census.py --self-test` 复绿。
命令面镜像：契约 `cli/command_contract.py`（PUBLIC / 5.23）、README 速查行、SKILL 分组与
"主线共 63 个"、registry 那一行、`tests/test_command_surface_census.py` 分母 72 → 73
（数字一律现算，别抄这里）。钉子见 `tests/test_truth_ctq_list.py`（14 条：注册面 / 默认视图自报排除 / 投影同源 / `--json` 标签 / 空作用域 / 其他态按原样 / README 镜像 / 两层读失败 / 审计不写含反向对照 / 限值原样 / 计数守恒 / 口径注不说满 / 失败面不出成功件）。
另一处现状（2026-09-26 更新，F-LINEAGE-DXF 第 46 片；2026-09-27 第 66 片把计数改成现读）：血缘边有** 9 个**生产者（AST 现读，判据是 `scripts/absence_claim_census.py` 账本里的 PRODUCER-COUNT-ARCH 那一格；本节下面展开其中三处 —— gate / spec_lineage / dxf_lineage，另外六处见 cost_lineage、quote_lineage、supervisor/fact_lineage.py（第 70 片：执行证据 → 已批准的定义）与三处返工补边的执行器）——
`product_intelligence/gate.commit_snapshot`（PI 需求 / Feature → truth 记录）、
`aipd drawing spec`（`src/aipd_os/cad/spec_lineage.py`：按声明正文**实际引用到**的
`ctq_ref` 写一条 `artifact_version` 记录，并给每条参与 CTQ 连一条 `affects` 边；
有 gap 时文件与血缘都不写），以及 `aipd drawing generate --db`
（`src/aipd_os/cad/dxf_lineage.py`：按**输入签名**——模型摘要 + 声明内容哈希 + 全部出图参数（part/revision/views/scale/sheet/material/剖切/放大）——写图纸的 `artifact_version`，并连「声明记录 → 图纸记录」的边）。
于是链条的**第二跳 CTQ → 图纸声明**与**第三跳 图纸声明 → DXF 制品**今天都传播得到：
改一条 CTQ 再跑 `aipd truth propagate`，那份声明**和按它画出来的那张图**一起被标 stale
并各自生成返工任务。身份取输入签名而不取 DXF 字节是实测决定的：同输入连跑两次，两份 `.dxf` 的 13170 行里
只有 2 行不同，差的是 `$TDCREATE` / `$TDUPDATE` 那一对儒略日时间戳——按字节哈希会把
时间戳读成一次工程变更；DXF 自己的 sha256 仍作为**观测**留在 metadata 里。同一产物路径
只留一版有效，新版落下时把旧版标 `superseded`，否则一张图改十次就有十条永久的下游。
BOM / 成本那一支的血缘生产者已在第 48 片接上（`aipd cost calc --truth-lineage` → `src/aipd_os/bom/cost_lineage.py`：按「BOM 身份 + 参与行集合」写 `artifact=bom` 版本记录，按「BOM 签名 + 口径五项（tooling_fee/target_quantity/amortize_over/nre/margin_pct）」写 `artifact=bom_cost` 成本结论记录，连 `bom → cost` 的 `affects` 边；同作用域只留一版有效、旧版标 `superseded`；BOM 为空什么都不写），于是改一行 BOM 再跑 `aipd truth propagate` 就能把那笔成本结论标 stale；成本结论那一条已在第 49 片接上返工执行器（`src/aipd_os/bom/cost_rework.py`：按记录里的 BOM 与口径五项重跑核算，把**这一条**记录演进到新结果并补回边）。两条纪律值得单独写：① 执行器**不**走生产面的写版本路径（引擎 `run_rework` 成功时是对这一条 bump 版本、关 stale，所以这里用 `store.update` 演进它本身；「换输入另起一版 + 旧版 superseded」是生产面 `cost calc --truth-lineage` 的规则，两边刻意不同）；② 第 48 片那批记录没把口径五项的**值**存进 metadata（只存了哈希），那些记录重建不出同一次核算，执行器一律 `missing_inputs` 点名拒——拿默认口径猜一遍会得到一条「按当前 BOM 重算过」的假结论。上游方向在第 50 片接上了一跳：`aipd quote apply --truth-lineage`（`src/aipd_os/supply_chain/quote_lineage.py`）按「全部参与判定的报价事实 + 批次币种」写一条 `artifact=quote_batch` 版本记录，并连一条 `quote_batch → 当前 artifact=bom` 的边——这是整条链上第一个往 BOM 版本记录**连入边**的生产者，于是「改了报价」第一次能经 `truth propagate` 把 BOM 版本与那笔成本结论一起打成 stale。两个刻意的取舍：① **来源文件名不进签名**（同一批价换个路径重下载不是又一次工程变更，与第 46 片把 DXF 时间戳挡在签名外同一个理由，常驻用例正反各钉一条）；② 报价完全可以先于任何一次 `cost calc --truth-lineage` 发生，那时下游记录**还不存在**——记录照写、边数 0、把原因点名说出来，不算失败也不算连上。**BOM 版本记录已在第 53 片接上返工执行器**（`src/aipd_os/bom/bom_rework.py`：按当前 BOM 行
把**这一条**版本记录演进到新键，正文与 metadata 走生产面那份投影 `bom_version_fields`；
「当前 BOM 没有行」「这张 BOM 已不是记录那张」「签名没变而 revision/version_no 变了」
三种都不算收口）。今天没有执行器的那一类只剩 `quote_batch`——它的"返工"是重新 apply 一次报价，
属生产面动作，不该由返工执行器代做。图纸这一跳在第 47 片两头都接上了：`aipd truth rework` 会按记录里的输入集合重跑出图，并且**不新增版本记录**——引擎 bump 的是这一条；「换输入另起一版 + 旧版标 superseded」只是生产面（`aipd drawing generate`）的规则。
生产者集合由
`tests/test_drawing_spec_lineage.py::TestProducerRatchet` 按 AST 两向钉住——
多一个未登记的 `add_edge` 调用点要红，把本轮这个删掉也要红。

## 2.1 Idea Truth 是 projection，不是第二 Store（v5.8 Commit 14）

`src/aipd_os/idea/projections.py` 的 `IdeaTruthProjection` 是**查询组合**，
不创建新 DB/表：

- 输入：idea + claims + evidence relations（`claim_evidence_relations` 复用
  canonical evidence 表）+ lineage 概念；
- 输出 auditable projection：known（有 supports 证据）/ assumption（A）/
  evidence（有 relation）/ contradicted（contradicts）/ unknown（U）/
  gaps（无 relation 的 claim）/ maturity（I0/I1/I2）；
- `IdeaTruthSnapshot`：可选不可变快照（JSON 可序列化，仅快照语义；生成后
  修改源数据不影响 snapshot）。

Maturity 确定性判定（`idea/maturity.py`，v5.8.2 Commit 6）：I0=raw 无 claims；
I1=claims 已创建但未满足 I2；I2=**required key claim types 全覆盖**
（`IdeaMaturityPolicy`：problem/user/mechanism/technology 全部存在且
已检索/评审，ClaimAssessment 非 NOT_SEARCHED，无 fake evidence）；
I3 只定义 contract。只有部分 key claims 被调查 → I1 + Evidence Gap。

## 2.2 CAD artifact identity contract（v5.8.2 Commit 9）

两个 hash 语义严格区分，**禁止混用**：

| hash | 用途 | 性质 |
|---|---|---|
| `artifact_byte_hash`（sha256） | 文件完整性 / tamper detection | 同一磁盘工件 → 字节稳定；任何字节改动 → 变化 |
| `semantic_geometry_hash` | 几何身份 | 同参数 → 稳定；改参数 → 变化；**与序列化字节无关** |

- 测试契约（`tests/test_cad_contract_unify.py`）：同参数两次导出 →
  semantic hash 相同；改参数 → semantic hash 变化；保存后
  `artifact_byte_hash` verify 通过；篡改 → FAIL；契约后端（无真实几何测量）
  不伪造 semantic hash。
- **byte_reproducibility_profile**：除非固定 CadQuery / OpenCASCADE / Python
  writer 环境（版本 + 平台 + 依赖集），**不承诺**两次独立 STEP 序列化字节
  一致（STEP 序/元数据可能因环境不同而变化）。需要字节级复现时，必须显式
  声明环境 profile（cadquery 版本、OCP 构建、Python 版本、平台），
  `artifact_byte_hash` 只保证「同一工件」的完整性，不保证「跨环境重生成」。

## 3. 作用域

所有 truth 记录与血缘/返工任务都带 `tenant_id` / `project_id`
（`product_truth/store.py`），查询一律按 scope 过滤；`find_id_by_type_and_content`
也按 scope 去重，防止跨项目误合并。这是「canonical truth 归属哪个项目」的存储基础。
