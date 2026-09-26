# Changelog

## [Unreleased] — 5.6.0 之后的连续迭代（v5.7 ~ v5.10 + 收口迭代）

> 说明：包版本暂保持 5.6.0（版本双轨制留待正式发布统一）；以下按 workstream
> 记录已交付能力。各批次的实现/审计证据见 `docs/audit/`。

- **v5.7 状态服务生产化**：单库多租户 `AIPDStateDB`（tenants / user_access 行级授权）、
  canonical decisions、多项目/租户作用域 Supervisor、迁移/备份/检查点/追加式审计、
  静态加密与健康检查；
- **v5.8 想法与证据运行时**：Idea 证据图（Claim / EvidenceRelation / 成熟度 I0-I2）、
  研究检索→写回链（诚实降级：检索到 ≠ 证实）、`aipd doctor` / `aipd version --verbose`；
- **v5.8.1 证据运行时**：统一 RuntimeContext bootstrap（唯一装配入口）、
  外部 Provider 接入（ResearchStudio）、能力四态探测（AVAILABLE / EXTERNAL_DEPENDENCY /
  NOT_IMPLEMENTED 等）；
- **v5.8.2 架构真实性**：层次泄漏反转（idea 域零 execution 依赖）、CLI 大文件拆分、
  门禁拆分与生成脚本幂等化、租户过滤修复、诚实标注升级；
- **v5.9 产品智能**：证据 → 洞察 → 机会 → 原则 → 需求 → 功能 全链转译
  （canonical lineage + 回溯验收）、Product Definition Gate（AI 不自批，Owner 批准）、
  Snapshot 冻结与失效传播；
- **v5.9.1 产品定义运行时**：product.* 动态四态探测、fail-closed 语义、
  Owner 批准 waiver 流程（P0-04/10/38/64）；
- **v5.9.2 快照运行时 + N-1 配置驱动 LLM**：Snapshot runtime commit 闭环、
  通用 `LlmClient`（OpenAI 兼容）与 LlmProductIntelligenceProvider /
  LlmIdeaDecompositionProvider 生产装配（`AIPD_MODEL_API_KEY` + `AIPD_MODEL_BASE_URL`），
  未配置时诚实 EXTERNAL_DEPENDENCY；
- **v5.10 制造就绪（BOM/Cost，2026-08-14 首项落地）**：结构化 BOM 域
  （层级/数量/材料/供应商/单位成本/关联图纸报价、乐观锁、父链防循环、审计），
  确定性成本核算（材料小计 + 模具摊销 + NRE + 毛利，缺数据不按 0 元假装），
  发布检查清单（开模可用物料清单与成本核算的确定性验收），CLI `aipd bom` /
  `aipd cost`，成本结果写回 Product Truth（status C）；
- **v5.10 二维工程图（`cad.2d_drawings` 由外部依赖转为本地实现，2026-09-24）**：
  `aipd drawing generate` 从 STEP/原生参数化模型出 DXF 工程图——六标准视图、
  可见线 + 隐藏线（逐点射线遮挡，实测本 OCCT 构建的 `HCompound()` 恒空）、
  尺寸与孔径全部由投影几何测量（Kåsa 圆拟合 + 角向覆盖判整圆），带标题栏与
  `<name>.evidence.json` 证据 sidecar；内核缺失时返回 HOLD 外部任务包不外推。
  边界与未实现项（**改前**：GD&T/尺寸链/剖视/爆炸图/装配图、相切轮廓单侧；前三项的后续进度见
  本文件 F-DRAW-01 第 1/2/3/4 片，剖视已交付但剖切符号 A-A/阶梯剖与局部放大/爆炸图/装配图仍未做）见
  `docs/audit/CAD_2D_DRAWINGS_HOLE_PATTERN_2026-09-24.md`；
- **v5.10 修复 F-CAD-01：孔阵参数未实现**：`Workplane.center()` 相对当前笔位偏移且
  `hole()` 不重置笔位，逐点循环使偏移累加——黄金件声明 `hole_count=4` 实测只钻出
  3 个孔位（两孔重合），`n=1` 时恰好正确故长期不可见。改为 `pushPoints` 批式下发 +
  `_hole_pattern()` 单源，并新增「声明参数 ↔ 实体几何」对账门
  （`geometry_validity_check` 的 `declared_features`，配 n=4 判红 / n=1 判绿双向反证）。
  体积/面数派生量受影响，故 BOM 与成本核算输入此前在多孔件上不可信；
- **v5.10 修复 F-STATE-05：store 建表把调用方事务静默提交**：五个 store
  （`Supervisor` / `RunStore` / `ClosureStore` / `ProductTruthStore` / `BomStore`）
  的 `__init__` 在 `ConnectionFactory.transaction()` 内调 `executescript()`，
  而它在执行前隐式 COMMIT——在同一库同一线程的外层事务里构造 store 时，
  外层尚未提交的写会被一起提交、回滚失效，DDL 脚本自身也不再原子。
  P2 曾把这条记为「当前不可达」，本轮用一个最小触发用例证伪（5 条先红后绿）。
  统一改走 `state/migrations/sqlsplit.exec_script()`（逐条 execute，不隐式提交），
  用例见 `tests/test_ddl_transaction_atomicity.py`（含 `executescript` 与
  `exec_script` 的配对对照）；
- **v5.10 修复 F-STATE-06：跨库事务串连接 + 事务登记表收敛为一**：
  `AIPDStateDB` 的活动事务放在模块级**单个** thread-local 槽里、不按库路径分键，
  因此「A 库事务中开 B 库事务」会把 A 的连接交给 B —— 本该写进 B 的语句落进 A，
  且不报任何错（多租户/多项目库面上的写错位置）。同时它与 `ConnectionFactory`
  的登记表互不可见，同库跨入口嵌套仍会与自己的写锁互等。
  现 `connect()/transaction()` 委托 `ConnectionFactory`，全状态层共用一张
  按 (库路径, 线程) 的登记表；回归
  `tests/test_connection_reentrancy.py::TestOneRegistryAcrossEntries`
  （修复前 3 条全红）。同库嵌套边际成本 18.9µs（P2 记 36–52µs），
  `state_perf_gate` 与全量回归均 PASS；
- **v5.10 修复 F-STATE-07：配了加密密钥仍然明文落库**：
  `build_runtime()` 用 `encryption_key is not None` 判断「调用方是否指定」，
  而本仓约定空串 = 未设置（`Settings` 与 server argparse 的默认值都是 `""`）；
  CLI 的 idea.decompose 路径硬传 `""` ⇒ 配置里的 `AIPD_ENCRYPTION_KEY` 被整个吞掉，
  敏感字段走 `_store_value` 的 fail-open 分支明文写入且不报错。
  改为按真值判断、调用点不再硬传该参数；回归
  `tests/test_runtime.py::TestEncryptionKeyResolution` 三条
  （配了密钥必须密文、显式密钥优先、未配置仍明文——末条为反向控制）；
- **v5.10 修复 F-STATE-08：字段加密改用带盐 PBKDF2 派生（migration v18）**：
  密钥派生原是 `sha256(口令)`——单轮无盐，库文件外泄后口令可离线穷举
  （server 模式只校验长度 ≥16 与三个字面弱值，不保证熵），同口令还可跨安装预计算。
  新格式 `f2:<iterations>:<b64salt>:<fernet token>`：PBKDF2-HMAC-SHA256、
  600k 轮（本机实测 129ms）、轮数与盐随密文存储；盐**每库一份**存于
  v18 新增的 `db_meta`，派生结果按 (口令,盐,轮数) 进程内缓存，
  避免把 129ms 摊进每次字段读写。低于 `MIN_KDF_ITERATIONS` 的 token 拒绝解密
  （防静默降级）；`f1:`/`x1:` 旧密文保持可读、不再新写。
  落选方案与实测：`hashlib.scrypt` 在本机 Python 3.9 不存在、
  `cryptography` 的 scrypt 挂在可选依赖上、Argon2 需新增 C 扩展；
  回归 `tests/test_crypto.py`（7 新）、`TestStateFieldEncryption`（e2e 盐稳定性）、
  `tests/test_migration.py::test_v18_db_meta_up_and_down`；
- **v5.10 修复 F-EXEC-01：外部副作用没有幂等键，重驱动会重复对外发送**：
  执行路由的去重只在调用方显式传 `idempotency_key` 时生效，而全仓唯一传 key 的是
  实验室数据入库；`side_effect_mode() == "EXTERNAL_SIDE_EFFECT"` 的 RFQ 邮件等
  从没给过 key ⇒ supervisor 重跑或用户再点一次就会再发一封（路由的 docstring
  本身声明要避免的正是这个）。现按内容自动派生键
  （`auto:` + `canonical_hash([capability, input − 易变字段])`，
  换供应商/换零件仍算新的一次发送），并把上一次"结果未知"的失败
  （`failed` 且分类不是 `external_blocked`）的重驱动挂起为 `unknown_outcome`
  等人工核对，与「UNKNOWN ≠ FAILED」的既有 doctrine 一致；
  用例 `tests/test_execution_idempotency.py` 第 7 组 5 条（实现前 2 红 3 绿）。
  未做（当时）：`OutboxDispatcher` 仍无产品调用点（机制齐备但未接线，属遗留清单）——该遗留已于同日被 F-EXEC-02 闭合，见下条；
- **v5.10 修复 F-GATE-01：Gate 评的是「项目里最后一个想法」而不是本快照的想法**：
  `gate_evaluations` 的 snapshot/hash 绑定本来就在，但**评的对象**是猜的——
  `create_snapshot()` 用 `ideas[-1].idea_id`（选中机会自带的 `Opportunity.idea_id`
  被忽略），四处判据（成熟度 / 关键 claim 评估 / contradiction / upstream basis）
  和 `is_stale()` 各自再取一次 `ideas[-1]`。单想法项目上看不出来；项目里出现
  第二个想法后，快照被归给不相干的想法，且**已 READY 的定义会凭空变 BLOCKED**
  （变异反证实测）。现统一按 `snap.idea_id` 解析（`_target_idea`），
  解析不到按「无法证明」判 FAIL（矛盾检查按既有 doctrine 记 n/a），不退回猜测；
  无需迁移（旧行的 idea 与 basis 是同一猜测写下的，读回自己即可自洽）。
  另修 `record_gate` docstring 不实：它只写 `gate_evaluations`，不写没有快照绑定的
  `gates` 台账；用例 `tests/test_snapshot_idea_lineage.py`（5 条）；
- **v5.10 修复 F-EXEC-02/03/04：外部副作用事件化接线（outbox → dispatcher → 台账）**：
  P2-M5 交付的 outbox 机制**产品侧零调用点**（实测 `src/`、`scripts/` grep 为 0，
  `external_operations` 更是无人写入——dispatcher 只 import 了仓储却从不调用），
  且带着三个会真咬人的洞：`max_attempts` 从未被读（一次 `drain()` 内毒事件实测被重试
  20/20 次）、handler 抛 `TimeoutError` 走的是「释放租约重投」而超时不证明没送达
  （⇒ 给同一供应商发第二封信）却自称 `UNKNOWN_OUTCOME`、`run_once()` 无条件 `commit()`
  会把调用方未提交的领域写一起提交（F-STATE-05 同形状）。现：RFQ 适配器带队列时
  **不再内联发送**，改为在状态库落事件（外层有事务则并入）；`aipd outbox drain` 显式驱动；
  handler 先占 `external_operations` 幂等键再投递，同内容重放只发一次（v16 部分唯一索引
  首次被用例经过），超时落 `UNKNOWN_OUTCOME` 并离开可领集合；claim 改为单条
  `WITH … UPDATE … RETURNING *`（带租约返回）；口令不入事件载荷。
  顺带：`industrialize.email_execution` 的登记入口原写 `mail_rfq_adapter.send`
  （该符号不存在）现指向真处理器；`SKILL.md` 的「主线共 38 个」在**本轮之前**就比契约
  少 1（实测 public=39），补为 40 并新增 `tests/test_skill_command_surface.py`
  做同源核对 + 两条注入反证（`skill_quality_audit` 只查「有没有声明」，不查总数）；
  证据与未证范围见 `docs/audit/EXEC_OUTBOX_WIRING_F-EXEC-02_2026-09-24.md`；
- **v5.10 修复 F-NET-02：响应体上限静默截断，半张 PNG 能过签名校验**：统一出口的
  `read(MAX_BODY_READ_BYTES)` 只保证「不超过」，超限时返回的是**前缀**而非错误 ⇒
  JSON 侧报「不是 JSON」（尺寸问题伪装成格式问题），图像下载侧 `PNG` 头部完好、
  尾部缺失，签名校验通过后半张图被当完整文件写盘并记进证据。改为 `read_capped()`：
  多读 1 字节判溢出（不信 `Content-Length`，可分块传输），超限直接 `HttpError`，
  绝不返回半截字节；非 2xx 正文同受此限，且 `except HttpError: raise` 必须排在
  兜底 `except Exception` 之前；上限改为**调用时**解析（绑在 `def` 行会让调常量静默无效）。
  5 条新用例（含「正好等于上限」与「差 1 字节」两个边界方向）；
- **v5.10 修复 F-EXEC-05：接线的后果自己也有洞——「结果未知」必须可见**：
  `mark_unknown` 给事件置 `completed_at`（必须如此，否则超时=可重投=两封信），代价是
  这些行从所有 `completed_at IS NULL` 查询里消失——实测一次超时后
  `sent=0 / deduped=0 / pending=0` 三个读数全部「正常」。台账一边有状态机、有
  `idx_ext_ops_status` 索引、有专用异常 `ExternalOperationUnknownError`，却**无人查询、
  无人 raise**。现补 `list_unresolved()` 与 `aipd outbox review`（有未收口项 ⇒ exit 4），
  `drain` 读数加 `needs_review`，同幂等键重放未知态改为拒发等人工核对；重试预算收敛为
  单点纯函数 `attempt_budget()`（此前事件表与台账各写一份，是 `src/` 第 4 份手写预算）；
  `execution_runs.duration_ms` 从 5 处硬编码 0 改为 `elapsed_ms()` 单点派生，并把恒真的
  `assert duration_ms >= 0` 收紧为 `> 0` + 50ms sleep 下界用例；`--db` 路径不存在时
  exit 2 并说明，绝不替用户建库；

- **v5.10 修复 F-SUPPLY-01 / F-BOM-01 / F-COST-01：询价 → 报价 → BOM → 成本这条商业主链从来没有闭合过**：
  接线前实测（`git grep HEAD`）——`SupplyChainStore.persist_quote` 全仓 **0 个产品调用点**
  （唯一调用者在 `tests/test_supply_chain.py:455`）；`set_bom_status` 同样 **0 个产品调用点**
  （只有 2 处测试）⇒ `release_checklist` 的 `bom_released` 在产品路径上永假；
  `bom show` 调 `release_checklist` 时不传 `cost_inputs`（HEAD `commands_manufacturing.py:60`）
  ⇒ `cost_calculated` 永假；全仓唯一写 `bom_lines.unit_cost` 的地方是 CLI 手填的
  `--unit-cost`。也就是说「开模可用物料清单」这个门禁既不可能满足、报价也从来没有
  变成过成本。现补 `aipd_os.supply_chain.apply`（只有 official 报价能改价、对不上行即
  `unmatched`、币种逐行核对、作废行不接受报价、重复应用不推高版本）+ 两条新命令
  `aipd quote apply`（解析→登记→落 `quote.*` 事实(V)→写 BOM 单价）与
  `aipd bom release`（清单未过即 exit 4 并点名未过项，过了才置 released）；
  `compute_bom_cost` 此前把 USD 与 CNY 直接相加、还把 `obsolete` 行算进材料小计，
  现分别改为多币种即 `CostCurrencyError` 与按 `OBSOLETE_STATUS` 排除（`rollup` 同口径）；
  `industrialize --quote` 增加自陈「仅解析、未落库、未改价」并指向 `quote apply`。
  接线后自己又量出一处（**F-SUPPLY-02**）：同文件二次 `quote apply` 崩在 `UNIQUE constraint failed: facts…key, facts.version`——版本号取自进程内注册表（每次从 v1 起）而事实按项目持久；state.db 与 bom.db 之间没有跨库原子性，「重放即修复」因此不是便利而是唯一收口手段。现版本号以库为准：内容相同即复用既有那版（零新事实、零改价），改价才出新版本且旧版 `V` 事实随即转 `R`。
  16 条新用例（全部走 `main(argv)` 真实入口，不手搓 args 副本）+ 4 组变异对照开火。
  证据与未证范围见 `docs/audit/QUOTE_BOM_COST_F-SUPPLY-01_2026-09-24.md`；
- **v5.10 修复 F-SUPPLY-03 / F-CLI-01：声明的影响传播不可达，且 8 条 PUBLIC 命令根本没接线**：
  `industrialize.physical_writeback` 自称「测试结果 → 事实主表更新 → BOM/CAD 影响传播」
  且 `current_limitation=None`，实测其唯一调用点把 `input["facts"]`/`input["bom"]`
  （调用方自带、实际不传）喂给 `propagate_impact`，而该适配器 id
  `validation.import-evt-dvt-pvt` 在全仓（含测试）除自身外**零引用**；产品侧唯一的
  capability 排产点 `supervisor/idea_capabilities.py` 只排 `idea.*`/`product.*`。
  顺着这条线量出更大一处：**`validation plan/list/show/import`、`issue list/show/resolve`、
  `readiness check` 这 8 条命令在契约、`COMMAND_FUNCS`、SKILL.md 三处都是 PUBLIC，
  但 CLI 解析器从未为它们建 subparser**——`aipd validation import` 在终端上是
  `invalid choice`。既有的"命令覆盖率"检查比的是三份内部副本互相对表，谁也不读解析器。
  现补 `supply_chain/impact.py`：失败项 → 归一化全等命中 BOM 行 → 关联 deliverable
  按 CAS 置 `stale`（`released`/`archived` 不回溯改写）→ 写 `impact.<项>` 事实（status P），
  由 `aipd validation import` 与 `aipd industrialize --lab-data` 两条真命令驱动，
  未收口即 exit 4；补 8 条命令的 parser 接线与 `industrialize --project`。
  17 条新用例（`--collect-only` 实测：11+4+2），变异对照 M1/M2/M3 分别判红 4/1/2 条——
  其中 M1 还暴露了我自己一条只断言"命令打印了什么"的弱用例，已按"必须读库"补强。
  证据与未证范围见 `docs/audit/LAB_IMPACT_PROPAGATION_F-SUPPLY-03_2026-09-24.md`；
- **v5.10 修复 F-REG-01：能力矩阵的「入口可调用」证据是装饰性的**：矩阵自称含运行时 probe
  证据，但 `entry_callable` 不参与任何判定、也没有门禁要求它为真 ⇒ 78 行里 **11 行**入口
  解析不到可调用对象，其中 `research.attachment_reading` 还被判成 `fully_implemented`。
  逐条诊断分三类：4 条**入口字符串本身写错**（`src/...py:cmd_drawing` 文件路径形态被
  `/` 候选分隔符拆碎、裸词 `cad_adapter`、少包名的 `imggen.adapter`、指向不存在函数的
  `research.search_papers.selftest`）、3 条是**探针假负**（`scripts/research/*.py` 用顶层
  `import _http_runtime`，探针只临时加了 `scripts/`）、5 条是有意留空的 external 能力。
  现：4 条改对、探针补 `scripts/research`、5 条由常驻门禁逐条声明；
  新增 `tests/test_capability_entry_surface.py`（含"正确写法必须读 true"的反证，防止把
  探针坏了当成数据错了）。矩阵重生成后 `entry_callable=false` 11 → **5**。
  变异对照：探针退回旧 path 列表 ⇒ 4 红；把一条入口改回路径形态 ⇒ 1 红。
  证据见 `docs/audit/CAPABILITY_ENTRY_SURFACE_F-REG-01_2026-09-24.md`；

- **v5.10 推进 F-DRAW-01 第 1 片：二维图纸补尺寸链，公差只允许来自声明**：改前图纸只有
  总体宽/高 + 孔径、**零公差**（registry 行内自陈「未实现尺寸链/公差叠加」）。现
  ① 链由实测孔心排出「左沿→孔心…→右沿」并核对**图上印出来的**各段之和 == 总体宽
  （闭合差进 `dimension_chain_check`，同 x 不去重就会画出零长段 ⇒ 少于两站宁可不给链）；
  ② 公差只从 `--spec` JSON 取（`features[].tolerance` / `global_tolerance`），无声明即
  整张图零公差，声明在图上找不到 ⇒ 点名 `spec_unmatched_features` 且命令判**未收口（退出码 4）**；
  ③ 特征名带视图前缀（`TOP.overall_width`）——同一零件 FRONT 的总宽是 100、RIGHT 是 10，
  不带前缀会把公差贴错尺寸。
  实测口径（ezdxf 1.4.2 源码 + 存盘读回）：`dimtm` 存的是**下偏差的相反数**，原样传 -0.05
  会打成 `+0.05` 的假公差；`dimtdec` 默认 2 位会把 0.005 截成 0.01；override 只有 `render()`
  时才落到实体（据此删掉了本轮一度加的冗余 `commit()`——变异台证明「必须 commit」是错的）。
  真实黄金件端到端：15 处尺寸 = 15 个 `DIMENSION` 实体、15 处带公差、TOP 链 5 段闭合差 0.0。
  新增 `tests/test_cad_drawings_chain_tolerance.py` 23 条（读数一律重新读回文件，渲染文字读块内
  MTEXT）；变异对照 7 条全部打破（含符号、去重、显示位数、命名顺序、CLI 判据），
  1 条幸存并反过来更正了本轮自己的说法。未做：公差叠加分析、GD&T 形位框（入口已验：
  ezdxf 有 `TOLERANCE` 实体但无 `add_tolerance` 工厂）、剖视/局部放大、`--spec` 与
  Product Truth 打通，故 **C6 生产图纸包仍不成立**。证据见
  `docs/audit/CAD_DRAWING_CHAIN_TOLERANCE_F-DRAW-01_2026-09-24.md`；

- **v5.10 修复 F-EVID-01：发布就绪门禁的 CTQ/GD&T 证据根本没有生产者**：
  `production_release_gate.py:256-286` 的 `gdt_covers_ctq` / `ctq_has_inspection` 早写成
  fail-closed，但实测全仓 `ctq`/`gdt` 两个数组**只出现在两处测试夹具里**（
  `tests/test_production_release_gate.py:44`、`tests/test_cli.py:336`），`src/` 内零命中
  ——C5/C6 的证据此前只能人手抄，抄什么过什么。现新增 `src/aipd_os/release_manifest.py` 与
  `aipd release manifest`：BOM 行数/版本现取 `BomStore`、CTQ 现取 Product Truth
  （`record_type="ctq"`）、图纸数与 sha256 现取 `.evidence.json`，版本三源独立
  （BOM 头修订 / 图纸标题栏修订 / 模型内容哈希）**不代为对齐**。
  防空真通过的关键：**`gdt` 只从图纸侧长出**——要求「真标了公差 + 显式 `ctq_ref` +
  偏差数值与 CTQ 上下限一致」三条同时成立，所以「登记了 CTQ 但没画上」必然判未覆盖；
  不做按名字模糊映射（F-REG-01 的装饰性接线），`approval_status` 缺省 `unapproved`（生产者不代批），
  模型读不到就不写 `model_part_count`（不折算成 0）。真机端到端：未给 `--model` 时
  `gdt_covers_ctq=True` 而 `drawing_cad_same_revision=False`（缺输入即判红）。
  10 条新用例（两条门禁断言直接跑真门禁读 `evidence_checks`，不复刻判据），8 条变异全部打破；
  `--model` 分支在首轮真机运行即判 `model_unreadable`——根因是
  `importStep().val()` 返回 cadquery 的 `Solid` 包装而非 `TopoDS_Shape`，改用
  `solids().size()` 并补「两个实体数出 2」的用例。证据见
  `docs/audit/RELEASE_EVIDENCE_PRODUCER_F-EVID-01_2026-09-24.md`；

- **v5.10 F-DRAW-01 第 2 片：一维公差叠加——把「图纸自相矛盾」变成机器判定**：上一片画出了
  链也标得出公差，但没人检查这些公差**能不能同时成立**。现新增 `src/aipd_os/cad/stackup.py`：
  每环公差带 ``band = upper - lower``（``0/0`` 算声明、没声明算 ``None``，**不按 0 折算**），
  ``worst_case = Σband``、``rss = √(Σband²)``，若各段带和超过封闭环自己声明的带 ⇒
  判 ``inconsistent`` 并给出超出量，``aipd drawing generate`` 随之判未收口（exit 4）。
  三种「不可判定」（无链 / 某环缺声明 / 封闭环缺声明）都**不是通过**。
  刻意不做：不猜功能限值（仓库里没有「间隙必须 ≤ X」这类外部要求，给数就是编判据）、
  不做三维/角度叠加、不做分布型统计公差（``rss`` 只按带宽平方和开根，是用量近似）。
  上游对照：读 ``tolerance-stackup-cli``（MIT、1 star）源码确认它对 tol 取 ``abs()``
  ⇒ **不支持非对称偏差**，也不计算封闭环（要人手动列一行），两条恰好都是本片的判据本体，
  故只借公式形状、判据自实现。真机读数（内置黄金件 TOP，5 段各 20.0，声明 ±0.05、
  总宽 ±0.2）：``worst_case=0.5 > closing_band=0.4`` ⇒ ``inconsistent``、超出 0.1、``rc=4``。
  12 条新用例、7 条变异全部打破；证据新增 ``stackup_check`` / ``stackup_inconsistent`` /
  ``stackup_undecidable``。证据见 `docs/audit/CAD_STACKUP_F-DRAW-01_2026-09-24.md`；

- **v5.10 F-DRAW-01 第 3 片：GD&T 特征控制框按声明绘制并可回读**：新增 `src/aipd_os/cad/gdt.py`
  与 `GDT` 图层——框画成分格矩形 + 每格一条 TEXT + 一条引线，**挂点取实测特征圆心**
  （`TOP.hole_2` 的引线终点就是投影量出来的 `[-10.0, 0.0]`，不是 spec 里写的坐标），
  证据里同时留下结构化框内容（特征/符号/公差带/基准链/挂点）供下游 CAD 重建语义实体。
  不画半截框：类型不认识、公差带 ≤0 或没给、该有基准却没给、基准字母解析不到、
  基准指向图上不存在的特征、声明特征在图上不存在 ⇒ 一律点名并判未收口（exit 4）。
  诚实边界（读源码 + 检索后的结论）：ezdxf **有** DXF ``TOLERANCE`` 实体
  （``AcDbFcf``，实测存盘读回 1 个、``audit()`` 0 错）但 ``Layout`` **无** ``add_tolerance`` 工厂
  （实测 ``hasattr(Layout, 'add_tolerance') is False``）；其 ``content`` 转义码本轮
  **没找到权威来源**核实（ezdxf 文档站 fetch failed，检索只命中厂商博客/培训文），
  所以只交付「可回读核验」的 drawn 几何那一半，**不宣称**在 AutoCAD 等查看器里渲染一致；
  符号表也明确标注为本仓选定码位，不认识的特征不猜近似符号。真机：GDT 层 9 个实体
  （4 框 + 4 文字 + 1 引线）、``gdt_issues=[]``；同次运行里 ``rc=4`` 来自叠加矛盾，
  两类门禁互不冒充。11 条新用例、8 条变异全部打破。证据见
  `docs/audit/CAD_GDT_FRAMES_F-DRAW-01_2026-09-24.md`；

- **v5.10 F-DRAW-01 第 4 片：剖视图真做布尔切割，剖面用真 `HATCH` 实体**：改前出图只有六个
  外部正视图，孔内壁被外壁挡住 ⇒ 一张图看不出孔是不是通孔、壁厚多少。新增
  `section_view()`：用 `cq.Solid.makeBox` 造半空间切刀做 `solid.cut()`，再走已有的射线遮挡投影，
  把切出来的材料面投影成闭合多边形并用 `msp.add_hatch()` +
  `paths.add_polyline_path(..., is_closed=True)` + `set_pattern_fill("ANSI31")` 填成**真 DXF 实体**。
  两道筛选缺一不可：只按法向平行筛面，会把 `y=10` 的后外壁（实测 100×10=1000mm²）当成剖面、
  凭空多出一块材料，所以再加「面心到剖切平面的距离 ≤ `SECTION_PLANE_TOL`」。
  三条不静默的口径：① 接不成闭合环就不填并点名（OCP 的 `wire.Edges()` **无序**，实测顺次拼接
  会得到自交折线、shoelace 面积算成 0 或半值，故 `_chain_loop` 按端点接环，接不上返回
  `(部分, False)`）；② 切不到材料 ⇒ `section_empty` + `section_issues` + 未收口（exit 4），
  不交空白剖视当成果；③「切到了面但边界全断」与「没切到材料」两套措辞分开，原因不能说反。
  含内环的材料区本轮只填外边界并明说面积会被高估（没做带孔净面积）。
  取证（本机实装包源码 + 实测，非记忆）：`set_pattern_fill` 实际定义在
  `ezdxf/entities/polygon.py:270`（`Hatch` 类自己**没有**这个方法）、`add_polyline_path` 在
  `entities/boundary_paths.py:212`、ANSI31 定义在 `tools/_iso_pattern.py:76`；最小文档实测
  存盘标签含 `2=ANSI31`、`70=0`、`91=1`、`93=4`、**`75=1`（pattern line 确实写入）**、
  `45=-2.2450640303` ⇒ 填的是图案线定义而不是一个图案名。检索到的 OCC HLR/布尔与 ezdxf
  资料均为博客级、ezdxf 文档页 fetch 返回 404，未作为实现依据；
  真机（黄金件 `--section Y=0 --section Z=50`）：`SECTION_Y` 材料区 5 个 / **676.0mm²**，
  DXF 读回 `HATCH` 5 个全为 ANSI31、边界面积逐条 `[120,120,120,158,158]` 与证据**逐字一致**、
  `recover` audit **0 错 0 修**；`Z=50` 那一刀打印「剖切平面 Z=50 没切到任何材料」并 `rc=4`。
  顺带把 GD&T 格宽公式收成一处（`compartment_width`，框证据新增 `width_mm`），
  并用例钉住「记录宽度 == 图上实际跨度」。12 + 1 条新用例、8 条变异全部打破。证据见
  `docs/audit/CAD_SECTION_VIEWS_F-DRAW-01_2026-09-24.md`；

- **v5.10 F-DRAW-01 第 5 片：公差声明改由产品从 CTQ 长出，并用实测值反查合格域**：
  前四片之后图纸侧能画、能量、能判叠加与剖视，但声明入口仍是「人手写 JSON、再手抄 `ctq_ref`」
  （能力行原话：「未与 Product Truth 打通」）——这意味着门禁 `gdt_covers_ctq` 的两条输入
  出自**同一个人手写的同一个文件**，考的是「抄得对不对」而不是「要求有没有传到图纸」。
  新增 `src/aipd_os/cad/spec_from_truth.py` 与 `aipd drawing spec`：读 `status="active"` 的
  CTQ `TruthRecord`，产出与 `--spec` 完全同形状的声明（`tolerance` 由
  ``upper_limit−nominal`` / ``lower_limit−nominal`` 换算、`ctq_ref` 由产品写）。
  四条不猜的口径：① 必须有显式 `metadata.drawing_feature`，**不按名字或直径相近猜映射**；
  ② 缺 `nominal` 不拿图纸实测值当标称、也不按 0 折算，直接点名缺口；③ `"6.0"` 这类脏值
  按「没给」处理，不硬 `float()`；④ 同一特征被两条 CTQ 认领 ⇒ **连先来的那条也撤回**
  （保留它等于按遍历顺序挑赢家），上下限颠倒只点名不调头。
  另加一条**不由需求侧自证**的判据：声明带绝对合格域 `limits{min,max}`，出图时拿
  **投影实测值**反查，落在域外判 `ctq_window_violation` 并进未收口（退出码 4）；
  手写 spec 不带 `limits` 时旧路径行为逐字不变，也**绝不**从总宽 CTQ 反推 `global_tolerance`
  （那会把一条要求贴满每条未声明尺寸）。有缺口时 `drawing spec` **不写文件**——
  一份「看着能用、其实漏标」的声明比没有声明更危险。`release_manifest` 的每条 gdt 回写
  `ctq_record_id`（只说「匹配上了」不可审计）。
  真机跑通时当场抓到一处真实不一致：黄金件孔实测 Ø8，演示 CTQ 写的合格域是 5.95–6.05 ⇒
  「合格域未收口：TOP.hole_1 实测 8 不在 CTQ 的 5.95–6.05 内」并 `rc=4`；改成 8.0/7.95–8.05
  后同一命令 `rc=0`、`tolerance_applied: 3`、三条尺寸各带 `ctq_ref`。
  链级用例把 DB 播种 → `drawing spec` → 出图 → `build_release_manifest` →
  **真跑**门禁 `--target C5` 接成一条，`gdt_covers_ctq` 判绿且全程无人手写声明。
  选型：借 QIF（ISO 23952）characteristic 的「标称＋上下限＋显式关联」形状，但本轮
  **未检索到可 pip 安装的 Python SDK**、官方 SDK 源码未读；STEP AP242 PMI 那条路要换产出物
  且本环境无法核验（检索命中的厂商帮助页 WebFetch 只取回 JS 壳，正文未获得），均不作依据。
  18 条新用例、8 条变异全部打破。证据见
  `docs/audit/DRAWING_SPEC_FROM_TRUTH_F-DRAW-01_2026-09-24.md`；

- **v5.10 F-DRAW-01 第 6 片：GD&T 框与基准方案也从 CTQ 长出，门禁按「画上去的框」计覆盖**：
  第 5 片只自动长**尺寸公差**声明，形位框与基准仍靠手写 JSON（`gdt` / `datums` 两块）。
  `spec_from_ctq` 现在认一条记录里的三种声明：尺寸合格域、`metadata.gdt` 列表、
  `metadata.datum_id` 基准字母，并且**同特征不同类别不算冲突**——
  「一条给孔径、一条给同孔位置度」是正常工程实践，合并成一条声明、
  各自带自己的 `ctq_ref`（形位引用写在 gdt 条目上，框才答得清是哪条需求）；
  只有**同类**重复才冲突（两条抢同一尺寸、两个字母抢同一基准、同特征重复同一几何特征），
  冲突时两条都撤回，不按遍历顺序挑赢家。画出来的框带 `ctq_ref`，
  `release_manifest` 据此把「真画上去 + 挂在实测特征上」的框计入 `gdt_covers_ctq` 覆盖，
  `covered_by` 明写 `dimension` 还是 `feature_control_frame`，
  同一条需求被两样同时命中时**只计一次**（重复计数正是覆盖类门禁最容易虚高的地方）。
  诚实边界：形位那一半只核「框在图上且挂实测特征」，**不**核形位偏差数值——本仓还不测形位偏差；
  把基准声明成一条不带任何合格域的纯 CTQ，会被门禁判「未覆盖 + 无检验方法」，
  今天判为正确行为（基准角色不是待检特性），要同时表达就把 `datum_id` 写在带公差的那条记录上。
  真机：演示库三条记录（`datum_id`＋尺寸、位置度、孔径）→ 一条合并声明
  「TOP.hole_1: +0.05/-0.05（合格域 7.95–8.05）；形位 position 带 0.05 ← CTQ T-002、T-003」
  ＋基准表「A → TOP.overall_width」，出图 `rc=0`，图上框读回 `⌖|⌀0.05|A` 挂在实测圆心
  `[-30.0, -0.0]`；证据里两条覆盖分别是 `covered_by=dimension`（T-003）与
  `covered_by=feature_control_frame`（T-002，带 `frame` 原文）。
  本片的一个判据空洞是**靠注入才发现**的：把「同一条需求尺寸与框各计一次」注入后
  全部常驻用例仍绿 ⇒ 补 `test_a_record_covered_by_both_a_dimension_and_a_frame_counts_once`，
  同一注入随即被杀。7 条变异全部打破；该文件累计 31 条用例。证据见
  `docs/audit/CAD_GDT_FROM_TRUTH_F-DRAW-01_2026-09-24.md`；

- **v5.10 F-DRAW-01 第 7 片：位置度偏差真拿实测圆心核对，超带的框不再当覆盖凭据**：
  第 6 片的形位覆盖只到「框画上去了 + 挂在实测特征上」，能力行当时明写「**不**核形位偏差数值」。
  缺的不是判据而是**输入**：位置度要成立，需要「理论精确位置」，
  它既不在图纸几何里（图纸只有实测位置），也不能从公差带反推（那是把要求当事实）。
  本片把理论位置作为声明的一部分接进来：``gdt`` 条目带 ``basic: [x, y]``
  （与挂点同一套视图坐标、同一单位，由 CTQ 的 ``spec_from_ctq`` 原样透传），于是
  偏差 = ``2 × 距离(实测圆心, 理论位置)``（直径带），**超带**判
  ``position_deviation_exceeded`` 并退出码 4，**偏差正好等于带**判合格
  （边界不判罚，容差是噪声级的 ``POSITION_DEV_TOL = 1e-6``），二维距离而不是只比 x
  （``basic=[-30.0, 0.04]`` 的纯 y 偏心同样开火），
  没给 ``basic`` 则点名 ``position_basic_missing``——不拿实测圆心当理论位置、
  不拿 (0,0) 兜底，那等于自己出题自己打勾；非位置度（平面度等）需要整面采样，
  本仓内核不做，一律 ``verified="presence_only"`` 且偏差列 ``None``，不伪造 0。
  `release_manifest` 同时改口：偏差超带的框**不给**计覆盖，并落一条阻断问题
  「位置度实测偏差 0.08 超出公差带 0.05（CTQ …）」，覆盖条目新增 ``verified``
  字段，明写这条覆盖是「已数值核对」还是「只证到存在」。
  真机（黄金件，理论位置故意给 -30.04 而实测是 -30.0）：
  出图 `rc=4`，图上框读回「⌖|⌀0.05|A（挂点 [-30.0, -0.0]，来自实测，位置度实测偏差
  0.08 / 带 0.05（超带））」；`release manifest` 亦 `rc=4`，
  `gdt=[]`（覆盖被拒）并阻断点名该 CTQ。判据两侧来源独立（需求 vs 模型几何），
  所以这一半不是自证。6 条变异全部被杀，其中「拿实测当理论」「忘记乘 2」
  「边界判罚」「只看 x」「形状类假称核过」「门禁照旧盖章」各对应一条常驻用例。
  13 条新用例（`tests/test_cad_gdt_deviation.py`）。证据见
  `docs/audit/CAD_GDT_DEVIATION_F-DRAW-01_2026-09-24.md`；

- **v5.10 F-DRAW-01 第 8 片：剖切符号与剖面标题 «A-A» 真画到图上，母视图才对得上那一刀**：
  第 4 片的剖视算对了却没被标出来——图上只有一张叫「SECTION_Y」的视图，
  母视图上没有剖切线、没有字母，看图人无法定位这一刀切在哪、往哪看；
  交付图纸里这是**歧义缺陷**，不是美观问题。
  新增 `assign_section_letters` + `_section_line_in_view`：剖切平面 ``p·n̂ = offset`` 在母视图
  投影面（正交基 ``right/up``）上就是直线 ``a·u + b·v = offset``（``a = right·n̂``、
  ``b = up·n̂``），于是符号位置是**算出来的**而不是摆出来的：视线与 ``n̂`` 平行
  （``a=b=0``）的视图不是母视图 ⇒ 不画；剖视图自己也不标（派生视图不当母视图是显式规则，
  不是几何副产品——另一刀的法向确实可能在剖视图里投出交线，用例
  `test_a_section_view_never_carries_another_sections_symbol` 就是钉这个）；
  **切到空气的剖视不编号也不标符号**——给一张什么都没有的剖视标 «B-B» 等于图纸声称它存在
  （这一条是真机跑出来才发现的：黄金件 ``--section Z=5`` 空剖视照样拿了 B 并画上 FRONT）。
  符号 = 剖切线（优先 PHANTOM 点划线，文档里没有就退回 DASHED，
  **绝不引用文档里不存在的线型**）+ 两端指向保留侧的短划 + 两端字母，
  外加剖面标题 «A-A»；端点/字母/保留侧方向全部进证据（不是只报「画了符号」）。
  真机（黄金件 ``--views FRONT,TOP --section Y=0 --section Z=5``）：
  ``section_letters = {SECTION_Y: A, SECTION_Z: B}``，TOP 上 A 落在 ``v=0``、
  FRONT 上 B 落在 ``v=5``，跨度 ``±54``（= 轮廓 50 + 两端余量 4），
  SECTION 层 6 条 LINE + 4 条 TEXT、线型 PHANTOM/BYLAYER，`recover.audit()` **0 错 0 修**；
  空剖视那一刀 ``rc=4`` 并明说「剖切平面 Z=5 没切到任何材料」。
  9 条变异全部打破（其中 R8「剖视图自己也标符号」**首轮幸存**，补派生视图用例后才被杀），
  11 条新用例 `tests/test_cad_section_symbols.py`。第 4 片审计文档已加带日期的更正指针。
  证据见 `docs/audit/CAD_SECTION_SYMBOLS_F-DRAW-01_2026-09-24.md`；

- **v5.10 F-DRAW-01 第 9 片：局部放大图（圆形裁剪 + «DETAIL n k:1»），紧公差那一处终于读得清**：
  第 7 片起位置度偏差已能数值核对，但 1:1 视图上一个 Ø8 孔旁边写 `±0.02`——标注存在而不可读，
  等于把判定推回人眼。新增 `--detail "TOP@(-30,0)/12=2"`（母视图 @ 圆心 / 半径 = 倍数）：
  圆心与半径用**母视图局部坐标与模型单位**（可直接抄证据里的孔心），倍数是相对母视图
  印出比例的放大（`<=1` 直接拒：那不叫放大）。
  **选型调研改了实现路线**：正规 CAD（FreeCAD TechDraw `DrawViewDetail.cpp`，本轮逐行读过）走的是
  `BRepPrimAPI_MakeCylinder` + `FCBRepAlgoAPI_Common` 把 3D 实体切成圆柱局部后**重新投影**
  （还得配 `m_fudge = 1.01` 兜边界碎屑）。本仓不走这条路：重投影会重新测量并重新命名特征
  （`DETAIL_1.hole_1`），而整条 CTQ 溯源是按视图前缀名匹配的（`cad/gdt.py:96,112`、
  `release_manifest.py:117-124`）——那样声明好的公差会整批落进 `spec_unmatched_features`；
  它还要重跑已知在相切处不可靠的遮挡判定。`shapely`（BSD-3，`>=3.7`）能裁线但返回无序
  `GeometryCollection`、且给 `cad` extra 添一个 GEOS 二进制依赖；`pyclipper` 只裁闭合多边形且
  整数坐标、`clipper2` 在 PyPI 无此名、`skia-pathops` 要求 `>=3.10`（与本仓 3.9 验证的 CAD
  内核冲突）。故取圆形局部的语义与裁剪意图，实现留解析式自研（零新依赖）。
  判据是闭式的：线段与圆的交集由一元二次方程给出，夹具里 `(-30,0)/R12` 裁出的外沿弦长
  精确等于 `2√44 = 13.266499…`，放大 2 倍后图上是 `26.532998…`mm（用例比到 `abs=1e-9`）；
  判别式 `<0` 那一支必须再看起点到圆心的距离，否则「整条都在内」的线会被整条丢掉。
  **放大图的尺寸只继承、不重量**：裁剪窗的宽/高是「窗」的尺寸，标成 `overall_width` 就是
  凭空造一条零件上不存在的尺寸（与「缺声明不折算成 0」同一条线）；以零件边缘为锚的链段同样
  不带入。继承保留母视图的特征名并加 `inherited_from`，所以 `--spec` 声明的公差与 `ctq_ref`
  一起带到放大图上；整圆在圈内仍认得出孔，被裁成开弧的**不许**继续报 Ø（开弧量不出圆心）。
  发布证据侧同步：`_collect_drawings` 跳过 `inherited_from` 的行——同一处测量在母视图与放大图
  各印一次只算**一条**覆盖凭据（否则画几张放大图就把 `gdt_covers_ctq` 的分子刷几倍）。
  空圈（圆内没有任何图线）判「放大未收口」并 `rc=4`、不编号、不画圈（与第 8 片空剖视同规矩）；
  母视图名写错是声明错误，直接 `ValueError`（`rc=2`），不静默少一张图。
  真机（黄金件默认模型，量出 4 个 Ø8 孔）：`DETAIL_1 16.0x16.0mm`（×2）与 `DETAIL_2 24.0x24.0mm`
  （×3）各继承 1 条尺寸，「声明 2 项、落到图上 3 处」`rc=0`，位置度框 `偏差 0 / 带 0.1（合格）`；
  空圈那一侧 `rc=4`。24 条新用例（`tests/test_cad_detail_views.py` 23 +
  `tests/test_release_manifest.py` 1 条去重凭据，后者自带「确实印了两处」的前提断言），
  **14 条变异全部被杀**（无幸存项，故本轮无需补断言）。
  顺带发现并补记一处**记账漂移**：第 8 片那次提交对 `registry_data.py` 只追加了 `unit_test`
  里的测试文件名，`input_output` / `current_limitation` 一字未动，于是能力声明连着整轮仍在说
  「剖切符号未做」——与同一行自己的测试清单矛盾（方向上是低报，不会假绿放行）。
  现有声明门禁只核文件可 import / 入口可解析 / 测试文件存在，**不核散文字段是否过期**；
  是否加「同一提交里 `unit_test` 变了而 `current_limitation` 没变即告警」的机检列为候选项，
  本轮未自行开工。同时更正上一轮收尾时「第 8 片已同步 limitation」这句记录——以 diff 为准。
  证据见 `docs/audit/CAD_DETAIL_VIEWS_F-DRAW-01_2026-09-24.md`；

- **v5.11 F-TRUTH-PROP-01：失效传播从产品面走得到，返工执行刻意仍不可达**：
  `PropagationEngine`（`product_truth/propagation.py:33`）写了很久但**产品侧 0 调用点**——
  9 处构造全在测试里，于是「上游需求变了 ⇒ 下游哪些产物要返工」这条链在软件上并不存在，
  而登记读起来像它存在。声明门禁看不见这类缺口：`registry.py:244` 只验入口字符串能解析成
  callable，`:287-290` 还明写「入口可调用性不作为降级门槛」，`run_command` 全程没人执行。
  新增 `aipd truth propagate --db --project --upstream [--reason] [--max-attempts]` 与只读的
  `aipd truth tasks`：沿血缘标 stale、生成 `rework_tasks` 有界任务、产出 owner 可读四段变更说明
  （改了什么/为何影响/修复计划/需要批准什么），有下游待返工即 `rc=4`。
  **`run_rework` 刻意不接**：本仓没有真实返工执行器，引擎在无执行器时唯一产出就是 `blocked`
  （其 "refusing fake success" 分支），一条永远不会成功的命令比没有命令更容易被读成
  「返工跑过了」；这一半缺口由 AST 级可达性断言钉住（扫代码引用而非子串——docstring 与
  `--help` 都要提到这个名字，子串扫描会把「写清楚了没接」误判成「已经接了」，而这两种情况
  的处置正好相反）。触发位置三选一时排除了「挂 `gate.commit_snapshot`」：它自己在产品侧也是
  0 调用点（`src/aipd_os/cli/` 命中 0），挂上去只是把不可达上移一层，而让它可从 CLI 触达要动
  「AI 不自批」那条批准不变量。外部只真读了一页（阿里云 Flink 物化表：刷新分 continuous /
  工作流定时 / 人工 Trigger Update，不谈 stale 标记），据此取「人工显式触发」那一档；
  另两轮检索（ECN affected items、OpenLineage 下游失效）只拿到术语表与营销页，无可复用实现，
  如实记下。
  「本次新置 stale」与「此前已 stale」分两栏报：引擎的 `stale` 只含新置的，第二次传播时空列表
  若原样转述就等于把「早就过期、还欠返工」说成「没影响」；`ok` 只对完全没有下游待返工为真。
  顺手量到并修掉引擎一个真实缺陷：`rework_tasks.task_id` 是全局主键，而 `_next_task_id` 原先按
  tenant/project 取 max ⇒ 两个项目各自算出同一个 `RW-001`，第二条插入撞 `UNIQUE constraint`
  （跨项目实跑撞到，正是作用域用例先发现的）；改为按整表分配，作用域隔离仍由两列负责。
  读-算-插之间没有加锁，多进程并发仍可能撞号——这一半没做，登记行的 `current_limitation`
  与本文件都写明「本仓按单写者假设运行」。
  18 条新用例 `tests/test_truth_propagate_cli.py`；12 条变异里 **T9 首轮幸存**
  （`truth tasks` 被改成顺手推进任务状态却测不出，因为断言写的是「列两次结果相同」——
  两次都读到被推进后的值），补成「库里绝对状态仍是 pending」后被杀；其余 11 条各由点名用例杀掉。
  同一趟把描述这件事的散文全部改完（第 9 片刚记下的教训）：登记新行
  `product_truth.impact_propagation`、改 `industrialize.physical_writeback` 里那句「仍是 0 调用点」、
  `docs/architecture/truth_architecture.md` 补可达性现状、两份审计加带日期的更正指针，并修掉
  `docs/audit/P0_VERIFICATION_MATRIX.md` 里指向已删除符号 `_default_rework` 的失效行号引用。
  同类缺口还剩一处本轮未动：`state/stale_propagation.py:43` 的 `StalePropagationService`
  依然 0 产品调用点（唯一使用者是 `scripts/state_perf_gate.py:237`）。
  证据见 `docs/audit/TRUTH_PROPAGATION_WIRED_F-TRUTH-PROP-01_2026-09-25.md`；

- **v5.10 F-DRAW-01 第 12 片：装配图（逐件投影 + 序号球标 + 明细表），图纸第一次能指认多个零件**：
  改前图纸侧只有单件图，`cad.2d_drawings` 的 limitation 明写「爆炸图、多零件装配图未做」。
  新增 `aipd drawing assembly --manifest assembly.json`：每零件一个 STEP + 作者声明的件号 +
  平移偏移，出一张带球标与明细表的 DXF 装配图并落证据 sidecar。三条判据决定画法与形状：
  ①**逐件投影**——本机实测两个 20×20×8 盒子，单盒 24 条 raw edge / 合并 compound 48 条，
  `classify_view` 投出 8 条 vs 16 条折线：一次投得完但孔会被全局重编号、包络被并成一个、
  重叠边被判不存在，归属只能靠事后聚类猜；②**编号只认作者声明**——缺号/重号/写 0/零件重名/
  STEP 读不到一律 rc=2 且不落半成品，与 FreeCAD TechDraw `DrawViewBalloon` 的语义一致
  （本轮真读上游 `src/Mod/TechDraw/App/DrawViewBalloon.h` 与 `.cpp:51-54,67`：气泡内容是可写的
  `Text` 属性、箭头落点是作者指的 `OriginX/OriginY`，**没有**按遍历顺序发号的机制；
  顺带纠正本轮初稿自己写错的「`DrawViewBalloon.ModelIndex`」引用——该属性经全仓检索并不存在）；
  ③**挂点是量出来的**——引线终点取该零件已投影折线的长度加权质心，断言落在自己包络内且不在
  别人的包络内。真跑命令行又抓到一个 19 条全绿用例看不见的缺陷：零件沿投影方向叠着时
  两个球标挂在同一个 `(0,0)`，几何没错但读图分不出归属 ⇒ 先写会红的用例，再让它**只作告警**
  （不改作者点的视图顺序），并给证据补 `balloon_view` 真值字段——否则「本视图故意不编号」与
  「发号那步坏了」在证据里同形（这条是新用例先失败逼出来的：原断言 `is None`，实读 `[]`）。
  明细表用 `ezdxf.addons.tablepainter.TablePainter`（MIT；本机实测 `text_cell`+`render` 产 TEXT+LINE，
  层 `TABLECONTENT`/`TABLEGRID`，`insert` 是左上角、表体向下长），**不用** DXF 原生 TABLE 实体
  （ezdxf 1.4.2 没有表实体写作 API：`Modelspace.add_table` 不存在、`ezdxf.entities` 无 `Table` 类）。
  候选 `cadquery.Assembly` 记为后续入口：本轮实测否掉了自己原先的理由（以为 `locate()` 会覆盖
  STEP 子实体自带 location，实测与 `BRepBuilderAPI_Transform` 都得 `[45,65]` ⇒ 两条路都正确叠加），
  真实差别是它的价值在约束求解而本轮不做约束，且迭代交回的 shape 不带摆放（PART_B 仍 `[-10,10]`），
  换成它要改既有投影入口的入参形状而收益为零。**未做且已在行内写明**：干涉检查（只报包络投影
  重叠面积）、球标↔BOM 行交叉核对与数量/材料列（`BomLine` 无件号字段，数量权威在 BOM，
  一个猜测值都不印）、爆炸图与装配约束、装配视图上的剖视/局部放大（rc=2 拒绝，裁剪会打散归属）。
  同一趟改完所有描述这件事的散文：`cad.2d_drawings` 行的实现文件/input_output/unit_test/
  e2e_evidence/current_limitation 五处、两行 B-Rep 能力里「装配…仍依赖外部工具」的歧义措辞、
  `drawings2d.py` 模块 docstring 的未实现清单、`drawing generate` 页脚、契约新增 1 条 PUBLIC
  （48 条）与 SKILL.md 47→48。守卫 `tests/test_cad_assembly_balloons.py`（初 27 条，重构后 28 条）+
  `tests/test_cad_drawings2d.py` 声明看守收紧（`implementation_file` 由「单个路径存在」改为
  「`;` 拆开逐个存在」，与本文件 `unit_test` 的写法及 `registry.probe_file_has_impl` 的形状对齐；
  未动那条公共 `any` 判据）。9 条变异全部被杀；变异器自身补了 baseline 前提，避免 node id 写错时
  「no tests ran」被误记成杀掉变异。
  **第二个由全量回归抓出来的问题**：局部用例全绿，`tests/test_import_cycles.py` 却判红
  （`assembly -> drawings2d -> assembly`）——「import 写在函数里就不算环」在这条门禁前不成立，
  它用 `ast.walk` 扫全文件、函数体内的 import 一样进图。没给它加白名单（那是 80 个能力行共用的
  架构判据），而是把方向反过来：视图带 `render_overlay` 回调、`write_dxf` 带 `layout_hook` +
  `extra_evidence`（装配侧画明细表并把要并进证据的键交回来），重叠文案在 `build_assembly_view`
  里算好随视图走，端到端入口改为装配模块自己的 `generate_assembly_drawing`，`generate_drawing`
  不再有 `assembly=` 分支。附带收紧：剖视/局部放大在装配函数面上**根本没有形参**
  （`test_assembly_drawing_does_not_expose_derived_view_flags` 用签名现算），防线不再只靠命令行
  不给 flag。钩子这种靠约定接线的形状补了三条变异（M10 回流再现、M11 钩子挂了但不调用
  ⇒ 球标静默消失、M12 钩子画了但证据被丢弃），用例增至 **28 条**、变异 **12/12 全部被杀**。
  证据见
  `docs/audit/CAD_ASSEMBLY_BALLOONS_F-DRAW-01_2026-09-25.md`；

- **v5.10 F-DRAW-01 第 13 片：球标 ↔ BOM 行交叉核对，数量只认 BOM**：补第 12 片明确欠下的
  那一半（当时写明「数量权威在 BOM，尚未接线」）。`aipd drawing assembly` 新增
  `--db/--bom/--tenant/--project`：给了就按 **manifest 里作者声明的 `bom_item`** 去核 BOM 行，
  明细表长出 QTY/UNIT 两列；不给就维持 `["ITEM","PART"]`，一个猜测值都不印。
  **不按零件名字自动映射**——沿用本仓两条既有纪律（`drawing spec` 的「全程不按名字自动映射」、
  `supply_chain/impact` 的「只认归一化全等，不做子串猜」），所以没声明 `bom_item` 的零件
  即使与某行 item 完全同名也不对上，这条由一条专门的反证用例钉住。
  标识归一从 `supply_chain/impact.py:37` 的私有 `_norm` **提成一处定义**
  `bom.models.norm_item`，impact 改为引用：两处各抄一份迟早各自漂，而它一漂就是
  「本该判歧义的被判成匹配」。数量与单位一律取自 BOM 行；解析器的白名单里没有 `quantity`，
  所以 manifest 写了也进不到零件数据（这条原本不显形，见下面的 N2）。
  四种情形判未收口（rc=4）：声明的行找不到 / 同一 item 在 BOM 里有多行（歧义时随便取一行
  就是猜数量）/ 零件没声明 `bom_item` / BOM 有行而图上没有球标指它（漏零件）。
  绑不上留空，**不折算成 0**：图纸上「没核到」与「数量为 0」差一个量级。
  真跑命令行又抓到一个缺陷：`--bom BOM-999`（编号写错）当时被当成空 BOM，逐条报
  「球标声明的行找不到」——听着像内容对不上，实际是根本没读到那张表；改成当场 rc=2，
  并把 `--db` 的 `is_file` 检查提到 `BomStore()` 构造**之前**（它会在给定路径上 mkdir 建表，
  命令行不许在写错的路径上凭空造一个数据库）。
  新增一条「数量真的画进 `TABLECONTENT` 层」的用例：证据里有数量不等于图纸上看得见数量。
  同一趟改完散文：`cad.2d_drawings` 行的 input_output 与 current_limitation、
  第 12 片审计里那条「球标↔BOM 未做」加同日更新指针、README 场景 4。
  守卫 `tests/test_cad_assembly_bom_link.py`（20 条）；变异 **14 条，首轮两条幸存**：
  N2「数量改从 manifest 取」是**等价变异**（解析器本就不读 quantity，使用点注入不进去），
  说明这条规矩不显形 ⇒ 改成对解析边界直接断言；N8「去掉库文件不存在检查」被新加的
  BOM 存在性检查**掩盖成同一个 rc=2**（副作用不同：那条分支会建出数据库文件）
  ⇒ 补 `assert not ghost.exists()`。补完后 14/14 被杀，第 12 片的 12 条不回归。
  仍未做：明细表材料列（`BomLine.material` 一直有值，本轮不顺手扩输出）、
  干涉检查、爆炸图与装配约束。证据见
  `docs/audit/CAD_ASSEMBLY_BOM_LINK_F-DRAW-01_2026-09-25.md`；

- **v5.10 F-DRAW-01 第 14 片：发布证据分清单件图与装配图，并对未闭合的球标判阻断**：
  改前 `aipd release manifest` 只报 `drawing_count`，装配图与单件图在发布文档里长得一样，
  且装配图证据里的 `assembly_issues` 被整个忽略——真跑量到「一张漏了零件的装配图
  读起来是 `ok: true`、无问题项」。新增 `evidence.drawings[].kind`（`part`/`assembly`）
  与 `part_drawing_count` / `assembly_drawing_count` 两个细分计数（`drawing_count`
  的既有含义不动），以及三条判定：`assembly_unresolved`（球标↔BOM 未闭合 ⇒ 阻断）、
  `assembly_bom_mismatch`（图上数量取自另一张 BOM ⇒ 阻断，计数一致性不成立）、
  `assembly_bom_unverified`（出图没接 BOM ⇒ **非阻断**提示：图仍成立，但数量没核）。
  manifest 不重算绑定，只搬运图纸证据里的判定；分类看证据里的 `assembly` 字段而不是文件名。
  **同时修掉第 13 片我埋的更严重的坑**：`--db` 指的是状态库，BOM 按产品口径在同目录的
  `bom.db`（`bom/store.py:3-5` 明写「不给权威状态库加表，状态库迁移已冻结」），
  而我写成 `BomStore(args.db)`——`BomStore.__init__` 会建库建表，实测一次只读的
  「出装配图并核数量」把状态库的表从 **42 张加到 46 张**（boms/bom_lines/bom_changes/
  bom_id_sequences），而那条命令本身还返回了 rc=2：**命令失败，副作用留下**。
  修法是把换算收成一处 `bom/store.py:bom_store_path`，让 `aipd bom`、`release manifest`、
  `drawing assembly` 三处共用（后两处原本各抄了一份表达式），并规定只读方在构造
  `BomStore` 之前必须先确认文件存在——读不到就报 `bom_db_missing` / rc=2，
  **不凭空建一个空 BOM 库**（那会把「没接线」伪装成「接上但是空的」）。
  测试夹具也改成走同一个换算：路径口径一旦被改，测试会跟着红而不是继续绿。
  守卫：`tests/test_release_manifest.py` +11 条、`tests/test_cad_assembly_bom_link.py`
  +4 条（含「状态库表集不许变」「状态库路径写错即使同目录 bom.db 能读也拒绝」）；
  变异电池 R1-R8 **8/8 killed**，第 13 片复跑 **17/17 killed**——上一片幸存的 N8
  在这一片才被杀掉（去掉状态库存在性检查后，同目录恰好有 bom.db 时会照常出图）。
  R7 首轮把目标用例指错（单件图那条永远走不到 `_check_assembly`，等于空判），
  补了「未绑 BOM 的装配图」用例后才成立：targeting 本身也要被检。
  仍未判：明细表材料/供应商与 BOM 的一致性、一张 BOM 对多张装配图的去重、
  「C6 是否要求装配图必须绑 BOM」（要业务口径，先只留提示）。证据见
  `docs/audit/RELEASE_EVIDENCE_ASSEMBLY_F-DRAW-01_2026-09-25.md`；

- **v5.10 F-DRAW-01 第 15 片：明细表的材料只认 BOM 行，发布证据说得出「哪几行还没有材料」**：
  第 13 片接上了数量与单位，材料留在 BOM 行上没人取用；C6 的交付物清单
  （`references/production-cad-deliverables.md:3`）要的是「材料与工艺」，所以「这张装配图
  有没有把材料落到图上」必须是机器读得出的一格。三条裁决：
  (1) **材料只有一个来源**——`bind_bom` 那同一个绑定结果里的 `BomLine.material`：
  没声明 `bom_item`、声明找不到、有歧义、或那一行本身没填，一律 `None`；
  **不写 `-` 也不写「未指定」**（占位符会被读成图上真有这么个材料），不拿标题栏
  `--material` 回填（那是作者另填的一格），manifest 里的 `material` 与 `quantity`
  同遇——解析器两个都不读，所以零件数据里不存在第二个材料来源；
  (2) **供应商刻意不上图**（是裁决不是漏做）：明细表随图纸版本冻结，供应商是商务事实，
  本仓契约里它只叫「候选供应商」且归在供应链开发清单（`deliverable-contracts.md:9,17`）；
  裁决写在 `cad/assembly.py` 的模块 docstring，并用一条用例钉住「代码旁边得留着这句话」。
  (3) **列集合跟着接上的权威走，不跟着「有没有值」走**：`draw_parts_list` 的门槛从
  `any("qty" in row)` 改成 `bom is not None`，于是接上 BOM 恒有 QTY/UNIT/MATERIAL 三列，
  每格独立留空——「全部行都没材料」恰恰最需要看得见，用旧写法它会整列消失。
  发布证据加第四条判定 `material_missing`（已绑上而那一行没填 ⇒ **阻断**并逐图点名球标）：
  压根没绑上的行**不重复计入**（那是 `assembly_unresolved` 判住的事），出图时没接 BOM
  记 `drawings_without_bom` 这一格**盲区**而不是折成 `with_material: 0`；
  「哪几行缺」一律逐图读（多张装配图的球标都从 1 开始，拍平就分不清是谁家的 1 号），
  文档级 `material_coverage` 只聚合数得清的四项。
  调研如实记录：**没拿到 ISO 7200 / GB/T 10609.2 / ASME Y14.38 原文**——中文检索命中多是
  文档分享站转载，SolidWorks/DraftSight 两个帮助页抓取只返回 CSS 正文为空，xometry 403，
  GitHub 代码检索对 TechDraw PartList 三种查询式 0 命中；真正读到内容的只有 RoyMech 的
  条目清单（Item/Description/Quantity/Reference/Material，供货信息仅算「其他必要信息」），
  列集合因此按本仓两条既有契约裁剪。
  守卫：`tests/test_cad_assembly_bom_link.py` +10 条、`tests/test_release_manifest.py`
  +7 条（含「两张装配图各留各的球标号」「没有装配图就不写这一格」「从 TABLECONTENT
  读回 `6061-T6` 且不许出现 `-`/`未指定`/`None`」）；变异电池 **12/12 killed**，
  且每条红在哪几个用例是关掉 `-x` 重跑记下来的，不是推的。**M10 首轮存活**
  （`with_material = bound_rows` 这种「拿位置当计数」只在「有材料那行排在缺材料那行之后」
  才算错，而我两条混合用例都恰好把有材料的放前面）→ 把断言改成缺在前、有在后，
  并同时核 `(2, 1)` 与 `球标 [1]`（原本 `"1" in detail` 也偏松：句子开头就带「1 行」）。
  真命令行端到端：出图 rc=0、`TABLECONTENT` 含 `MATERIAL/6061-T6` 而第 2 行材料格为空、
  全图找不到供应商串 `ACME`；`release manifest` rc=4、`ok=false`、
  `evidence.drawings[0].material.missing_balloons=[2]`。
  补一处第 13 片的账：`tests/test_cad_assembly_bom_link.py` 当时没登记进
  `cad.2d_drawings.unit_test`（registry 里出现 0 次），声明面少一栏等于那片没有测试。
  顺带记一个工具坑：往 registry 那条超长字符串里塞带 ASCII 引号的 `"-"`，
  `ast.parse`/`py_compile` 全过（那是合法的字符串减法表达式）而 `import` 才 `TypeError`
  ⇒ 能力表静默变空，**改完字符串数据必须真 import 一次**。
  仍未做：工艺/表面处理列（「材料与工艺」只落了材料这一半）、行级材料与标题栏 MATL 的
  一致性（做判定得先说清谁权威）、爆炸图与装配约束。证据见
  `docs/audit/CAD_ASSEMBLY_MATERIAL_F-DRAW-01_2026-09-25.md`；

- **v5.10 F-DRAW-01 第 16 片：明细表的工艺列，覆盖判据分成「材料 / 工艺」两半**：
  第 15 片把材料落到图纸那一格时，行内自己写着「C6 的材料与工艺只落了材料一半」。
  本片收另一半，并且先把形状问清楚：**工艺该是 BOM 行上的一列，还是独立的工序对象？**
  真读到的两家成熟实现口径一致——Dynamics 365 Business Central 的生产 BOM 行只有
  Type / No. / Quantity per / Scrap % / **Routing Link Code**，工序在另一张 Routing 里；
  ERPNext v15 用 BOM 的子表 **BOM Operation** 存工位/工时/成本（靠 “With Operations” 开启）。
  于是本片选「行上一列」但**改掉了它的定义**：`BomLine.process` 只表示
  「明细表那一格要的那道主工艺」，**不是工序路线**——工序顺序/工时/工序成本不建模，
  这句话同时写进 `bom/models.py` 类 docstring、`cad/assembly.py` 模块 docstring 与能力表行内
  （多工序塞进一个字符串会被明细表读成一个工序）。上游 FreeCAD TechDraw 的 BOM 列定义
  依旧**没读到**（GitHub 代码检索三种查询式 0 命中、猜的文件路径不存在），不引用。
  实现：`bom_lines` 加 `process TEXT`；旧库靠 `BomStore._ensure_columns` 就地补列
  （仿 `ProductTruthStore` 先例；`tests/test_migration_freeze.py` 冻结的是状态库，
  bom.db 归本 store 自有），补出来的列**可空**、旧行读成 `None` 不给非空默认值；
  `aipd bom add --process` 真能填；`_material_of` 收成 `_bom_text(line, name)`
  让材料与工艺共用一处取值规矩；明细表列集合 `QTY/UNIT/MATERIAL/PROCESS`，
  绑不上的数量/材料/工艺一律留空（不写 `-`、不写 `str(None)`）。
  证据侧：`_check_assembly` 逐行读两格，**两半各一条**阻断判定
  （`material_missing` / `process_missing`）——合成一条「信息不全」就看不出还差哪一半；
  每图引用里的块与文档级字段从 `material` / `material_coverage` 改名为
  `bom_line_coverage`（一个装两半的容器不该叫材料），新增 `with_process`、
  `missing_process`、`missing_process_drawings`；没绑上的行不重复计入，没接 BOM 仍是盲区。
  命令行出图直接报「材料已填 2/2 行、工艺已填 1/2 行，缺的球标 [2]」。
  守卫：三个文件各 +7 条（净 +21，其中 1 条是第 15 片「满覆盖⇒无问题」在新世界不成立而改名改判）；
  两条通用不变量是新加的——**逐字段全量 round-trip**（漏在 INSERT 列表里的字段只有它抓得住）
  与**模型字段集合 == 表列集合**；变异电池 **13/13 killed**，其中上一轮同类幸存的
  「`with_* = bound_rows` 拿位置当计数」（P13）这次因为一开始就配了
  「缺的那行在前、有的那行在后」的排列，首轮即被杀掉。
  **补一处更大的账**：动手前查到 `tests/test_bom.py` 在能力表里出现 **0 次**，而且
  **没有任何一行的 `implementation_file` 指向 `src/aipd_os/bom/*`**——`aipd bom add/show/
  release/cost calc`（三条 5.10 PUBLIC 命令）在能力表里整域不可见。新增
  `industrialize.bom_model_cost` 行（能力总数 80→81，`capability_matrix.{json,md}` 与
  `repository_snapshot.json` 重新生成），并写明「成本齐备 ≠ 材料/工艺齐备」是刻意的分家：
  `release_checklist` 只判成本，材料/工艺是否落到图纸由 `release manifest` 逐图点名。
  端到端全走 `aipd` 可执行文件：`bom add`（一行有工艺一行没有）→ `drawing assembly` rc=0
  且六列齐、缺格为空 → `release manifest` rc=4、`process_missing` 点名球标 [2]、
  每图读数 `{bound_rows:2, with_material:2, with_process:1, missing_process:[2]}`；
  读回 DXF 的 `TABLECONTENT` 确认工艺值真在图上、没有 `-`/`None` 占位。
  仍未做：多工序路线、材料与工艺的**对不对**（只管有没有上图）、标题栏 MATL 与行级材料的一致性、
  `release_checklist` 与材料/工艺齐备的合并（要业务口径）。证据见
  `docs/audit/CAD_ASSEMBLY_PROCESS_F-DRAW-01_2026-09-25.md`；

- **C6 交付物覆盖度普查（新诊断量具 `scripts/c6_coverage.py`）**：连续三片在补 C6 的零碎项
  （分清单件图/装配图、材料列、工艺列），但从来没有一张表说明 C6 那 15 项各自到哪一步——
  继续做的顺序因此是凭感觉的。本片只产分母与档位，不产新功能。
  落点选择真比过两条：(A) 扩 `scripts/capability_matrix.py` 加 C6 维度——功能错配（它按能力行
  聚合四态，普查按契约项算档），且它的 JSON schema 已被用例与 `docs/audit/*` 消费，加维度等于改契约；
  (B) 新写独立诊断脚本——与仓内既有量具同形（`skill_quality_audit` / `state_perf_gate` /
  `audit_repo` 各自成档且都不挂能力行）。**选 B**，只从 A 借两点：读表走 `registry_data`
  （不另立第二份真相）、CLI 形状照 `--repo/--json`。普查**不落 JSON 快照**也**不挂能力行**：
  读数由常驻用例钉住，多存一份就是两处会各自漂的副本；量具不登记是跟随既有先例，不是遗漏。
  三档判据都可机器核：`producer`（`src/` 下真有生产者 + 测试文件里真数得出 `def test_`）/
  `checker_only`（`implementation_file` 只指向门禁脚本或模板——「手写 JSON 把门过去」就落这档，
  它不等于交付物存在）/ `absent`（零落点）。分母**逐字从
  `references/production-cad-deliverables.md` 现算**，改契约不改映射当场红。
  今天的实测：**15 项 = 10 producer / 2 checker_only（DFM-DFA、版本与ECR/ECO）/ 3 absent
  （爆炸图、ICD、装配/维护）**。
  顺带暴露三处声明缺口并登记给后续：**5 条能力行 `implementation_file` 与 `unit_test` 两栏皆空**
  （`research.standards_regulations`、`research.patents_competitors`、
  `cad.assembly_constraints`、`cad.continuous_kinematics`、`cad.cae_fatigue`）——一行不可核验的声明；
  **144 个产品模块没被任何行的 `implementation_file` 点名**（含 `cad/stackup.py`、`cad/gdt.py`
  这种真生产者，而 `cad.tolerance_chain` / `cad.gdt` 两行反倒只写门禁脚本）——是信号不是判决，
  没点名不等于没被测。
  自测：`--self-test` 注入 7 条（分母多一项 / 映射留旧项 / 生产者路径不存在 / 档位与所列矛盾 /
  能力行 id 不存在 / 用例文件零 test / 用例路径不存在），7/7 都开火，并由常驻用例直接跑它。
  本片自己踩的三个坑一并记下，因为它们都是判据的来源：映射键与契约原文差一个空格
  （「总装/单件 STEP」vs「总装/单件STEP」）被自家两条判据同时抓住；函数里复用 `caps` 变量名
  让能力表诊断拿到一串字符串（`cap.get` 才 `AttributeError`，函数作用域是平的）；
  `grep -i ECO` 命中 107 个 src 文件全是 `SECONDS`/`SECRET` 之类子串噪声，
  按词边界重查才是 0——「零实现」判定一律用精确路径与词边界，并把这件事写进判读。
  边界：普查**刻意不接进** `production_release_gate`（今天就有 3 项零实现，挂成阻断等于
  一个永远红的门），并由 `test_census_is_not_wired_into_the_release_gate` 钉住。
  守卫：`tests/test_c6_coverage.py` 10 条（含档位棘轮 10/2/3、三档定义互斥、注入全开火）。
  下一片顺序建议与理由见 `docs/audit/C6_COVERAGE_CENSUS_F-C6-01_2026-09-25.md` §九
  （爆炸图 → 装配步骤生产者 → ICD/ECR-ECO 先问属主）。

- **v5.10 F-DRAW-01 第 17 片：装配图爆炸视图，位移一律由作者声明**：C6 普查把「爆炸图」判成
  零实现，本片把它升到 producer（档位 10/2/3 → **11/2/2**，棘轮与缺席清单同步改）。
  形状问题先问过证据再定，不是先写代码：**自动求爆炸/拆卸方向**在文献里的作法
  （JCAD《智能装配规划中的拆卸方向计算》，摘要已读到）是「对装配约束做离散球面算法」+
  「为一件零件找到一条**无碰撞路径**后才定全局拆卸方向」，需要 ①装配约束/配合数据
  ②实体几何离散 ③干涉-路径校验三样前提；本仓 ① 没有（`cad.assembly_constraints` 那行
  implementation_file 与 unit_test 两栏皆空，是普查顺手照出来的），③ 也没有
  （只报包络投影重叠，明写不做实体求交）。上游也没有现成件可复用：本地实测
  CadQuery 2.5.2 的 `cq.Assembly` API 只有 `constrain/solve/toCompound/traverse/…`
  没有 explode 机制；FreeCAD 侧只检到博客与「exploded assembly 插件安装」文，不是可复用
  API 文档；SolidWorks 爆炸视图帮助页两次抓取**只返回 CSS**，正文一字未取到。
  于是选「**位移由 manifest 声明**」（每件 `"explode": [x,y,z]`），只借文献的
  「一步 = 零件 + 方向 + 距离」结构。理由不是「好做」，是**没证过的拆卸方向不能上图**。
  实现：`_explode` 解析（非三数即拒；缺项是 `None` 不是 `[0,0,0]`——
  「这一件不参与」与「它就在原位」在图上同形但含义不同）；`build_assembly_view(explode=True)`
  平行投影下把声明位移投到视图 2D 再平移折线（每件各自 HLR、件间不互相遮挡，
  与「先平移实体再投影」逐位等价，省一次内核投影且不引入新假设）；
  每件一条**装配位→爆炸位**连接线（EXPLODE 层，证据里 `exploded` + `connectors` 两头都带）；
  球标仍挂在**爆炸位**质心、编号仍只认作者写的 `balloon`（摆开之后按位置重发号
  等于图纸在说一个作者没说过的顺序）；位移与视线平行时**告警「看不出分离」**——图没错，
  但读者拿不到信息；`--explode` 而有任何零件缺声明 ⇒ 出图前整体校验拒（rc=2、不留半成品），
  视图内部还有一道兜底。发布证据加第五条装配判据 `explode_unconnected`（标了 exploded
  而连线少于零件数 ⇒ 阻断）：生产者不会产出不一致的证据，但 **sidecar 可能是手改的或
  旧版本留下的**，门禁吃的是证据文件。
  守卫：`tests/test_cad_assembly_explode.py` 19 个函数（参数化后 23 条）+
  `tests/test_release_manifest.py` +3 条；变异电池 **13/13 killed**
  （X1 位移当 0、X2 连线两头都在爆炸位、X3 球标挂回装配位、X4 按摆开位置重发号、
  X5 去掉出图前整体校验、X6/X7 --explode 透传与反向、X8 证据不写 exploded、
  X9 连线不画、X10 视线平行不告警、X11 缺声明折零位移、X12/X13 判据极性）。
  **两处反证自身的坑值得记**：X5 首轮差点当「两道检查互为冗余所以杀不掉」——
  把断言从「rc=2 且含爆炸字样」改成**点名出图前那道整体校验的措辞与缺失零件清单**才成立
  （冗余不冗余要看是不是同一道在拒）；普查那条「档位与所列文件矛盾」的注入原本钉死
  在「爆炸图」这一项上，它升档后就静默变成等价注入，已改成按当前档位动态挑
  （`_an_absent_item()`）。另外证据里视图名的键是 `view` 不是 `name`，
  取错键只会往判据文案里印 `None`，新加断言把视图名钉进去了。
  端到端（全走 `aipd` 可执行文件，临时目录）：`drawing assembly --explode` rc=0，
  DXF 里 `EXPLODE` 层 4 条线（2 视图 × 2 件）、`BALLOON` 层 2 圆 2 引线（仍只一个视图编号），
  明细表六列齐、材料与工艺都报「没有缺行」；`release manifest` 对这张图不再报任何爆炸问题。
  仍未做：爆炸位移的自动求解、装配约束/配合、爆炸图与剖视/局部放大的组合
  （装配视图上仍拒绝，折线按零件归属，裁剪会打散）。证据见
  `docs/audit/CAD_ASSEMBLY_EXPLODE_F-DRAW-01_2026-09-25.md`；

- **v5.10 F-DRAW-01 第 18 片：装配步骤文档的生产者，把 C6「装配/维护」的装配那一半落到地上**：
  `assembly_instructions` 这个键此前在 `cad/maturity.py:29`、`production_release_gate.py:39,53`
  （`FILE_KEYS`：值必须是真存在且哈希对得上的文件）、`cad_maturity_gate.py`、`selftest_v3.py`
  四处**被声明却没人生产**。新增 `src/aipd_os/cad/assembly_steps.py`：步骤序列走同一份装配清单
  多出来的 `"assembly_steps"` 段（`{"no":1,"action":"…","balloons":[1]}`），序号、动作原文、
  每步引用哪些球标都由作者声明；`aipd drawing assembly-steps` 出 Markdown + `.evidence.json`
  侧车，`aipd release manifest --steps-doc` 才写 `assembly_instructions = {path, sha256}`
  （**没交文档就不写这一格**，而不是写个空的）。五道拒绝都 rc=2：没写 `no`（不按遍历顺序代发）、
  重号、断档（1·2·4 ⇒ 点名缺 3）、引用清单里没声明的球标、写了不承载的字段
  （`torque` 是**拒**不是静默丢——丢掉就得到一份少了一格还自称完整的文档）。
  反向闭合不拒而是记未收口 + CLI 退 4 + manifest 阻断（`steps_balloons_uncovered`）：
  图纸编了号、说明书里没人装这一件，是缺陷不是崩。
  **为什么序号要求连续而 Odoo 不要求**：本机按 commit f254c797 取到
  `addons/mrp/models/mrp_routing.py` 全文读过——它的 `sequence`（默认 100）是**内部排序键**，
  故意留空档好插队，且工序是带 `workcenter_id`/工时算式/成本/依赖图 + 环检测的独立记录；
  本片不做那个对象（与第 16 片「不建 operations 表」同一裁决），印在受控文件里的
  「步骤 N」是正文本身，断档等于当着一线操作者的面少一页。
  **生成式方案检索后不用**：`Ayaan577/Assembly_Instruction_Generation-IITK`（T5 seq2seq，
  BoM→自然语言步骤）GitHub API 列出的根目录 7 项里**没有 LICENSE**、权重是一个 83 字节
  的 Google Drive 链接文件、只有硬编码路径的 notebook——不可复现的输出进不了发布证据链，
  无授权也不能复用；InvenTree 侧检到 6 个 0-star 微插件、其核心文档 URL 本次 404（**没读到就不引用**）；
  S1000D 只拿到一份中文导读（不含 FWA/CTA 细节），导读称「标准可在 s1000d.org 免费下载」
  而我抓该站失败，**这句未验证**，故只借「编号步骤 + 每步显式列件号」的结构、不声称按其实现。
  介质选 Markdown：PDF 不是不能做——本机实测 reportlab 5.0.0 + `UnicodeCIDFont("STSong-Light")`
  出中文成功（2374 字节 PDF），本轮不做的是排版与分页判据；`python-docx` 未装且本仓把 .docx
  当外部输入拒绝（`supply_chain/lab.py:26,113`）。侧车刻意**不复用** `drawings2d._finish_evidence`
  （它会盖 `hidden_line_method`，那是图纸的事实，写进步骤文档就是给读者一个不相干字段）。
  数量/单位/材料/工艺仍只来自绑上的 BOM 行（同一个 `bind_bom`、同一条「两格不许互相顶」）；
  顺带把装配图与步骤文档共用的 `--db/--bom` 读法抽成 `_bom_lines_or_none`（文案逐字保留），
  否则两条命令对「只给一半参数」「库不存在」「编号写错」会各自漂。
  守卫：`tests/test_cad_assembly_steps.py` 29 条（六组）+ 变异电池 **14/14 killed**。
  **M8 首轮存活值得记**：判据「材料缺了不许拿工艺顶」写在实现里，但样本库里两格要么都有
  要么都没有，注入成 `material or process` 后测试全绿——**判据存在不等于判据被验过**，
  缺的是那个「只缺一格」的样本；补 `test_material_and_process_never_cover_for_each_other` 后才开火。
  能力表新增 `cad.assembly_instructions`（81→82），普查 `装配/维护` 由 absent 升 producer
  （档位 **11/2/2 → 12/2/1**，零实现只剩 ICD；README 那行停在 10/2/3 的陈读数一并改），
  档位升的是**一半**这句话写在映射 note 与文档 `not_covered` 里，不靠档位表达。
  端到端（真 CadQuery 模型两件 + 真 bom.db + 真状态库一条 CTQ，全走 `aipd`、全在临时目录）：
  步骤文档 2 步、球标覆盖 2/2、压板那行 PROCESS 格留空；`assembly_instructions.sha256`
  与文档实测哈希逐位相同；删掉第 2 步 ⇒ CLI rc=4 且 manifest 报 `steps_balloons_uncovered`
  blocking、`ok=False`、`unreferenced:[2]`；五种坏声明各自文案不同（不存在号 / torque / 断档 /
  重号 / 整段没写）。仍未做：维护指引（要属主给）、工时与工序成本、扭矩值、逐步骤点检项、
  PDF/图框版式、顺序的自动求解。证据见
  `docs/audit/CAD_ASSEMBLY_STEPS_F-DRAW-01_2026-09-25.md`；
  该文档 §二 有六维对比表、§五 有变异表、§六 有端到端读数。

- **v5.10 F-DFM-01 第 19 片：DFM/DFA 分析的生产者（普查档位 12/2/1 → **13/1/1**，
  `DFM/DFA` 从 checker_only 升 producer，只有校验方只剩「版本与ECR/ECO」）**：
  `cad.dfm_dfa` 这行的 `implementation_file` 此前只写模板 + `scripts/production_release_gate.py`
  ——门判「声明了什么」，产品侧没量过零件。新增 `src/aipd_os/cad/dfm.py`：几何事实全部内核实测
  （三轴网格射线进→出配对的最小壁厚、整孔直径/深度/深径比、最小内圆角半径、同轴孔系、包络与体积），
  **孔与圆角靠拓扑区分**（圆柱面角向张角满一周才算孔：实测 Ø6×10 通孔 1.0000、R2 圆角 0.2500），
  同轴分组用**轴线位置**（`cyl.Axis().Location()`）而不是曲面上的点——一开始拿错点，
  两个同轴盲孔被判成两根轴，是 `test_coaxial_holes_group_by_axis_not_by_name` 当场抓的。
  **阈值一律带来源、本仓不发明数**：金属 0.8mm / 塑料 1.5mm 取自 HLH Rapid 与 Xometry 两页
  **各自独立**的同量级读数（后者 0.794mm = 1/32 英寸换算），深径比 4×（保守）与 10×（上限）、
  公差可达 0.025mm 取自 Xometry，ISO 2768-1 的 f/m/c/v 表来自 3ERP 页且来源里写明是**转述**；
  Fictiv 那篇抓到了正文但**一个数字都没有**，所以不能当来处；厂商给「内圆角 ≥ 腔深 1/3」这个比值，
  本仓没有可比的腔深定义 ⇒ 那条 `limit=None` 只报实测半径，不编一个毫米数冒充标准。
  **测不出来记盲区不折算合格**：材料认不出类别 ⇒ 两条壁厚都 `material_class_unknown`；
  没有整孔 / 没给 `--spec` / 单个平面量不出厚度各有原因代码，`min_mm` 是 `None` 而不是 0.0
  （用例专门钉住：一个平面的壳每条射线只命中一次，配对失败就是没量到）。
  `hold` 只给「超出厂商标称能力」的两条（深孔 >10×、公差严于 0.025），CLI 退 4；
  `advisory`（薄壁、深径比 >4）与 `dfm_unmeasured`（一条都没判成）都只提示不阻断——
  告警≠阻断这条纪律原样带过来。`aipd release manifest --dfm-doc` 才写 `dfm_dfa = {path, sha256}`
  与 `dfm_summary`（hold/advisory/blind/measured + 材料分类 + not_covered + 侧车哈希），
  没交就**不写这一格**；`dfm_evidence_missing`/`dfm_hold_findings` 阻断。
  选型是实检后的取舍：`ncc-uk/SmartDFM`（26 个根条目里**无 LICENSE**，实现是 GNN+CATIA 研究脚本）
  与 `ishaannsaini-sudo/DFMedusa`（README 取不到=读不到）都不可引入，只借它
  `fact_base` + `rule_base` 的「先抽事实、再判规则」分层；PCB 类 DFM 检查器领域不符；
  射线原语不新增依赖（`IntCurvesFace_ShapeIntersector` 本仓 `drawings2d.py:240` 已在用）。
  守卫：`tests/test_cad_dfm.py` 35 条（六组，条数由 `--collect-only` 现算）+ 变异电池
  **18/18 killed**。电池本身抓到两件事：D9（basis 与 source.kind 一致性检查）原本**没有用例覆盖**，
  不补 `test_a_rule_whose_basis_disagrees_with_its_source_is_refused` 就会像上片 M8 一样存活；
  D16/D18 两次锚点**凭记忆写错**（漏了行首 `+ `），被「命中必须恰好 1 次」判为注入无效而不是误报通过。
  端到端（真模型 5 个、全走 `aipd`、mktemp 目录）读数物理正确：Ø6 孔在 20 宽板里量出孔壁
  **7.0mm**（不是板厚 10）、Ø2×24 盲孔在 25 厚件里量出孔底留肉 **1.0mm** 且比值 12 ⇒ `hold` rc=4、
  塑料 1.0mm 件按 1.5 那条线判而金属那条进盲区、`sha256` 与文档逐位一致、删侧车 ⇒ `dfm_evidence_missing`。
  仍未做：DFA 装配力与紧固顺序、插入方向计数、模具侧抽芯与脱模、铸造圆角与收缩率、
  CAE 热变形/振动、工序工时与成本；斜置薄壁的壁厚要改成沿面法向射线才测得准（报告 caveat 里写明）。
  证据见 `docs/audit/DFM_DFA_PRODUCER_F-DFM-01_2026-09-25.md`（§二 六维对比与阈值来处、
  §五 变异表、§六 端到端读数）。

- **v5.10 F-DRAW-01 第 20 片：装配级 STEP 的导出（闭掉普查映射里明写的「装配级 STEP 未导出」）**：
  C6 的「总装/单件STEP」此前只有单件那一半（`backends.py exportType='STEP'`），
  装配那一半的 note 直接写着「assembly.py 只按 manifest 逐件 importStep 再投影，不产总装 STEP 文件」。
  现在 `export_assembly_step` 按清单逐件导入、用**声明的 offset** 摆放（与出图、爆炸视图同一个位置事实，
  不引入第二套），经 `cadquery.occ_impl.exporters.assembly.exportAssembly` 写出带产品层级的 STEP。
  **关键不是能写出来，是写完不许直接算完**：立刻重新导入，逐件把「源 STEP 自己量出的中心 + 偏移」与体积
  对回去（中心管位置、体积管大小，两个都对才算同一件——只比中心会把同位不同形的两件认成一件，
  只比体积会把摆错的放过去），**对不上就删掉刚写的文件并抛错**。
  多实体零件按件聚合体积与加权中心，不按「一零件=一实体」猜；两件同位照样合法但报 `coincident_placements`。
  **两条实测出来的边界**照实写进证据与能力行，不粉饰：① OCCT 把非 ASCII 零件名按单字节写进
  `PRODUCT('æ¯æ',…)` 成 mojibake ⇒ 件号↔几何的对应只由 `.evidence.json` 承载，
  `step_product_names_readable` 恒 False 并带原因（这是本机读出来的，不是推断）；
  ② XCAF 侧只稳定读到根产品名（`IsAssembly=True`、根名 `ASSY-1`），子件标签名在这版 OCP 上
  方法名对不上（`GetLabelName` 不存在、`GetComponents` 只回一个标签），我另写的一版 TDF 递归
  直接把解释器 segfault 掉 ⇒ **判据改用回读几何的多重集比对**，不假装会读 XCAF 子标签。
  选型检索（本机真实读取）：`cq.Assembly.save` 在本版本已标 deprecated（FutureWarning），
  故直接调 `exportAssembly`；`Assembly.add()` 无 `label` 参数、只有 `name`（实测 TypeError），
  非 ASCII 名正是走 `TDataStd_Name` 落盘的；`Workplane.center()` 只收 (x, y) 两个参数
  （第 12 片量过的那颗坑，夹具里再踩一次，改用 `translate()`）。
  守卫：`tests/test_cad_assembly_step_export.py` 18 条 + 变异电池 **16/16 killed**；
  电池又量到三件事——E3 的「偏 0.5mm」用例正好压在放宽后的容差边界上（相等判不过、也不报错），
  改成偏 0.2mm 才真正区分开 1e-6 与 0.5 两档；E2 的锚点第一次凭记忆写、命中 0 次，
  按「命中必须恰好 1 次」判为注入无效而不是通过；E16 最早那条「把聚合出来的最大体积偏差硬编码成 0」
  **活了下来**——成功路径上偏差本来就是 0，硬编码 0 与量出来 0 在证据里长得一样，
  于是把那个聚合值和 `volume_match` 布尔**一起从证据里删掉**（只留每件「源体积 / 回读体积」两个数，
  读者自己减），换上「校验拿期望值当实测值」这条真会开火的循环自证注入。
  写后校验这道新判据是**先补三条故障注入用例
  （少一个实体 / 体积被换 / 位置偏 0.2mm）再跑电池**的，吸取第 19 片 D9 的教训。
  能力行 `cad.local_native_brep` 的机器列与散文同批改（新增 assembly.py 与新用例、limitation 写明
  mojibake 与不做约束/子层级），普查映射该项 note 同步、档位仍 13/1/1。
  证据见 `docs/audit/CAD_ASSEMBLY_STEP_EXPORT_F-DRAW-01_2026-09-25.md`。

- **v5.10 修复 F-EVID-02 第 21 片：发布门 `FILE_KEYS` 的哈希核对对数组整条形同虚设**：
  门自己写着「这些键的值可能引用一个必须存在且哈希对得上的文件」，但 `resolve_path` 只认
  字符串与 `{path, sha256}` 字典——**而模板和生产者写出来的恰恰是数组**
  （`step_assemblies: []`、`drawings: []`、`cae_reports: []`…；`aipd release manifest` 的
  `evidence.drawings[]` 也是）。数组掉进最后一行返回 `(None, None)`，两条使用点
  （逐键判据与 `file_openable`）一起 `continue` ⇒ 一份图纸全删、全被改过的包照样读成
  「所有引用文件可打开」。以前没被发现是因为唯一钉这条的用例写的是**字符串**
  （`tests/test_production_release_gate.py:86`），生产者真正用的形状一次都没进过用例。
  修法是 `resolve_paths()` 把数组摊平（递归一层）后逐条核：每条都要在，各自核哈希，
  **没写哈希的只核存在**（现场算一个当期望值等于永不失配），失配文案补上文件名（多条时指得认）。
  常驻 11 条（新文件 9 条 + `test_release_manifest.py` 真产物反向对照 2 条：删掉图 ⇒ `file_openable`
  点名、改掉内容 ⇒ `missing` 出 `C6:drawings: sha256 mismatch`；门禁逐级止步，故先把与本题无关的
  C0..C5 各键填占位真值，`drawings` 一条不改）。变异电池 **8/8 killed**，其中 G4 是特意放的
  **反向**注入（把「没给哈希」也判成错）——收紧判据必须同时证明它不该开火的地方没开火。
  收紧后全量 **1865 passed / 0 failed**：没有任何一份现存包靠这条空判据蒙过去，
  也没有一份被这次收紧误伤。能力行 `cad.production_release_gate` 的 `e2e_evidence` 里那句
  「hash」此前对数组是虚的，与散文同批改；`current_limitation` 从 `None` 改成明写
  「哈希核对按级触发、missing 只列到第一个没满足的层级」。
  证据见 `docs/audit/RELEASE_GATE_FILE_LISTS_F-EVID-02_2026-09-25.md`。

- **v5.10 F-EVID-02 第 22 片：总装 STEP 接进发布就绪证据（`aipd release manifest --assembly-step`）**：
  第 20 片有了生产者、第 21 片把接它进门的那道核对修得有牙，这片补最后一截——发布就绪证据里
  此前**没有总装 STEP 这一格**，C6「总装/单件STEP」只停在普查表的 note 上。契约的理由逐字取自
  `references/production-cad-deliverables.md:4`「STEP 存在、网格闭合或快照好看均不能单独证明生产可用」，
  所以这一格不能只写「文件在、哈希对得上」。**做法是重算侧车自己的话**：每件两个体积数相减、
  每件源实体数相加对 `solid_count`、`declared_part_count` 对 `parts` 行数、侧车写的
  `document_sha256` 对眼前这份文件（**字段缺失也算不等**），任一条自相矛盾即点名阻断；
  核对方法不是「写完回读逐件对上」⇒ `assembly_step_unverified`。
  还跟装配图的球标↔件号对账：**只在一张装配图对一份总装 STEP 时才配**，
  多张记 `ambiguous_pairing` 不猜、没图记 `no_assembly_drawing` 当盲区而不是当通过
  （按名字在多图里猜配对就是 F-REG-01 那条装饰性接线的老路）。
  键名不新造：文件引用进门里早就当 FILE_KEYS 核的 `step_assemblies`，事实进 `assembly_model`
  ——不叫 `assembly_step`，因为 `assembly_steps` 那一格已经是**装配步骤文档**的汇总。
  没交参数两键都不出现（写个空数组会让门把「没做」读成「做了但是空的」）。
  23 条常驻用例（图与模型都走真生产者，不手写夹具几何；CLI 两条把基线做到真能就绪才比「0 变 4」）
  + 变异电池 **16/16 killed**；H12 第一次跑是**锚点命中 3 次**判注入无效（`"not_covered": list(...)`
  这句在步骤文档/DFM/总装三处都有）——同一个坑第三次踩，锚点必须落在判据读的那一段。
  端到端用金样品两件跑通：`compared/agree`、`47833.457334 → 47833.457334` 逐件对上，
  且这趟零件名是 ASCII ⇒ `name_readability.readable=true`，与第 20 片那趟中文的 `false` 对照，
  证明那条边界跟着文件事实走、不是一行永远为假的字。
  **同一次端到端撞出一个缺陷并另立一条**：`assy.step` 与 `assy.dxf` 的侧车都拼成
  `assy.evidence.json`（`with_suffix` 把后缀丢了）⇒ 出图把总装 STEP 的证据顶掉。
  本片改用不同干名绕开，**绕开不是修掉**，见
  `docs/audit/EVIDENCE_SIDECAR_PATH_COLLISION_F-EVID-03_2026-09-25.md`（含修法选项与消费方普查要求）。
  顺手把 README 里第 19 片落错位置的 `--dfm-doc` 注释挪回 `aipd release manifest` 名下。
  证据见 `docs/audit/RELEASE_EVIDENCE_ASSEMBLY_STEP_F-EVID-02_2026-09-25.md`。

- **v5.10 F-DFM-01 第 24 片：壁厚加第二条量法（沿面法向），并改掉一条被实测推翻的旧话**：
  动因是量出来的，不是设想——3mm 厚、绕 Y 转 45° 的板，三轴网格射线给出 **1.00mm**，
  而 `dfm.py` 的 docstring 与报告 caveat 都写着「斜置薄壁会**测厚不测薄**」。这句关于误差
  **方向**的话是错的：斜穿让弦变长，棱角附近擦过的弦比真实壁厚还短。一个方向性偏差挂在
  advisory 上，读报告的人恰好朝错误的方向放心。
  选型（本机真实读取 + 外部文档，访问 2026-09-25）：OCCT 只有 `BRepOffsetAPI_MakeThickSolid`
  且它是建模不是测量（`Intersection`/`SelfInter` 官方注明未实现完）；FreeCAD 的 Thickness
  同一层封装、没找到壁厚报告；**CATIA 壁厚分析同时有 Sphere（默认，最大内接球）与
  Ray（沿边界法向）两档**，且其文档明写 Ray 在尖边处误差可超容差并提供 "No Sharp Edge" 掩膜；
  网格侧标准定义是最大内接球/绕数 SDF（libigl `shape_diameter_function`、BoneJ）。
  ⇒ **不新增依赖**，借 CATIA 的「法向射线 + 尖边掩膜」与 SDF 那一路的「先判在不在材料内」，
  原语全用仓内已有的 OCP。三处实测到的坑改掉了实现：`Normal()` 非单位向量（先 `Normalize()`）、
  其符号跟面 `Orientation` 走而不是「朝外」（±两向都得走）、极点零法向会让 `Normalize()`
  抛 `Standard_ConstructionError`（先判 `Magnitude()`，退化即跳）。
  口径：**两法各量各的，`min_mm` 取较薄者**，`axis_min_mm`/`normal_min_mm` 都留在读数里。
  依据是实测对照表：斜板 @0.5 三轴 1.00 / 法向 3.00；同一块 @1.0/2.0/5.0 三轴 2.02/3.00/3.00
  而法向恒 3.00；**金样品 bracket 三轴 2.00 < 法向 3.73（法向会漏）**；1mm 球皮两法一致。
  （第 25 片复算更正：出厂默认是**每面 12×12** 上限，那条 3.73 是上限 6×6 的读数，
  出厂口径下金样品法向读 **2.24**；结论方向不变（法向仍偏厚 ⇒ 聚合取薄者），
  但这条数不是出厂读数，已把 `sample_cap_per_face` 与两个数一起交出去。）
  壁厚两条阈值（金属 0.8 / 塑料 1.5，来处 HLH Rapid）是 advisory，取较薄者只多问一次制造方，
  取较厚者会把墙说厚。另有一条独立判据：**封闭空腔的开口宽度不是壁厚**——20 见方块里
  挖 0.5mm 全封闭槽，裸取第一条命中会读出 0.5（那是空气），分类器两道验证挡掉后
  量到的是「槽端到块边」5.000mm 那段真肉。
  21 条常驻用例（全真几何）+ 变异电池 **9 条：杀 6 / 活 3**。三条存活逐个解释，不粉饰：
  W7（撤退化法向守卫）存活是因为本批夹具造不出零法向采样点，其价值是**防炸**
  （另有一条用例专证 `gp_Vec(0,0,0).Normalize()` 真抛异常）；W8/W9 存活说明
  两道材料验证**互为冗余**——单撤任一道读数不变，一起撤（W3）才变。
  顺手删掉一条永远开不了火的守卫（`run <= eps`，`Perform` 的参数域下限就是 eps），
  并把能力行 `cad.dfm_dfa` 的散文里那句错话换成实测表说的事。
  证据见 `docs/audit/DFM_WALL_NORMAL_RAY_F-DFM-01_2026-09-25.md`。

- **v5.10 F-DFM-01 第 25 片：孔周留肉（hole-to-edge land）+ 来处新增「借来的数」这一类**：
  DFM 只答「这堵墙薄不薄」，制造方挑的第二类问题是「这个孔离边/离邻居太近，钻完翻边」。
  量法：逐孔取**孔口圆**，找「法向平行孔轴且真含住这个口」的那个平面面片当开口面，
  面上除孔自己周边之外的每条边都是自由边（相邻孔的口边天然算进去），
  用 `BRepExtrema_DistShapeShape` 量精确极值距离。**逐口各给读数**（`rim_readings`），
  行取最薄口、聚合取最薄孔，`min_land_mm` 与中心距都能由读数复算。
  本机实测：单孔 Ø6@x=25 → 2.00；两孔孔心距 8 → 韧带 2.00；盲孔 → 顶口 2.00 + 底口 `rim_isolated`；
  Ø10 通孔 + Ø14×3 沉孔 → 两口分别 2.00 与 8.00，交出去的是 **2.00（沉孔底那圈环形韧带，
  壁厚两法在这里都读 7.00 看不见它）**；Ø6 穿过 Ø14 凸台 → 4.00；金样品 v1 2.00 / v2 4.00。
  **写量具时先量出一个旧错**：判「孔」只看圆柱面角向张角满一周，而 Ø20 圆棒的侧面同样满一周
  ⇒ 圆棒被报成一个 Ø20×深 20 的孔，深径比、同轴孔系数、留肉三条一起跟着错（垫片 Ø30+Ø8
  报成两个孔）。补一根正交判据：从面上一点**径向外移 1µm** 问 `BRepClass3d_SolidClassifier`，
  落进材料里才是孔；分不出（纯曲面输入）返回 `None` 并单独计数，不猜。
  选型（延续第 24 片那次检索，2026-09-25 实读）：HLH Rapid / Xometry 两页都**没有**机加件孔边距规则，
  3ERP 转述的 ISO 2768 只把 edge distance 当成「被一般公差覆盖的尺寸」，Protolabs 那两条是钣金、
  Eurocode 那套是螺栓边距 ⇒ **没有可引的阈值**。不新造数：新增第三类来处
  `borrowed_out_of_scope`，金属 0.8 / 塑料 1.5 这两个数**借自本表内真有页撑着的「最小壁厚」**，
  `source.stated_for` 指回去、报告里印「页内原述是给金属最小壁厚的」，只判 advisory。
  为什么不让它挂 `vendor_capability`（冒充厂商说过）或 `own_measure`（挂 URL 冒充有出处）：
  第一版就是错挂 `own_measure`，被常驻用例「本仓口径不许挂 URL」当场判红——闸确实长出来了。
  运行时 `_check_source_integrity` 逐格核：`stated_for` 必须在、被借那条必须真是厂商页的数、
  limit 必须一字不差、必须是同一页，**每种坏法各给各的报错文案**（只要求「抛 ValueError」会让
  limit 检查替 donor 检查背锅，电池里 R4/R5 因此一度假杀）。
  顺手一条：第 24 片文档里金样品「法向 3.73」在本机复算下是**每面 6×6 上限**的读数，
  出厂默认 12×12 读 2.24 ⇒ 给 `_face_normal_thickness` 的读数补 `sample_cap_per_face`
  并印进报告（随分辨率改口的数必须带着它的分辨率），文档追加 §八 更正，规则口径不变。
  常驻用例 **32 条**（`tests/test_cad_dfm_hole_land.py`）+ `test_cad_dfm.py` 来处不变量 3 条
  + `test_cad_dfm_wall_normal.py` 分辨率 3 条；变异电池 **28 条：杀 28 / 活 0 / 注入无效 0**。
  两处电池教自己的地方：首轮 5 条存活（L4/L6/L9/R4/R5）全是「用例看不见」而不是判据错，
  逐条把读数拆开交出去才杀得动；加**对照组**（未注入先跑同一批 node id）后立刻抓到 B1
  把用例挂错类名 —— pytest 用 rc=4 退出，旧版电池会把它记成「杀掉」（假绿的方向恰好是
  「以为有闸」）。全量用例数 1953 → 1961。证据见
  `docs/audit/DFM_HOLE_LAND_F-DFM-01_2026-09-25.md`。

- **v5.13 F-DRIFT-2 第 52 片：报价批次的漂移键改由「库里的事实」投影，出图漂移补真库端到端断言**：
  第 51 片 §六 自记两格，本轮各自读到证据再落笔。
  ① `quote_batch` 到底能不能接 resolver——**读到的代码事实否掉了最自然的那条路**：
  `quote apply` 喂进签名的 `quote_id`/`version` 是那时按库内当前官方版**现铸**的
  （`cli/commands_supply.py:64-74`），文件里根本没有；而文件态→事实态的映射
  `persistence.py:20` 配 `.get(status, "P")` 是**有损**的，反查会把「映射不一致」冒充成「漂了」。
  真正的问题是该问「哪一项会变」：文件里的 `official` 是解析观测，**永远不会自己变**，
  会变的只有 `apply.py:107-133` 的 `retire_stale_officials` 把 `V` 改成 `R`
  ⇒ **按文件态算键的那把尺子是恒真的**，第 50 片想抓的那一格在它下面永远读不出来。
  裁决：新增 `quote_applied_rows(facts, currency, quote_ids)` 作**唯一投影**（7 字段，
  status 用事实态字母），登记侧改为在落库与 retire 之后读回事实算键，扫描侧第五支
  `_quote_resolver` 用同一个函数重算 ⇒ 两侧同源（R2 那条注入因此才杀得动）。
  签名基准换了，旧记录不许换基准重算：新增 `metadata.rows_from`，缺这一格的落
  「不可判 + 点名」（与第 48 片「口径五项没记」同一处理方式）；登记侧再加一条前提，
  读回行数不等于本批 quote_id 数即判未收口（退 4、`ok=False`、不留少算的记录）。
  顺带修掉第 51 片两处：`build_resolvers` 的 BOM 两支硬写 `DEFAULT_TENANT`（`--tenant`
  传非默认值时归属读错），以及**只读扫描会顺手建库**——`BomStore.__init__` 建库建表，
  同目录没有 `bom.db` 时一次扫描就把「没接线」改成「接了但是空的」
  （`bom/store.py:87-89` 明写过这条约束），现在先 `is_file()`、缺库点名，
  用例并同时断言扫完之后那个文件仍然不存在。
  ② `drawing_dxf` 补上真库端到端断言：CTQ → `drawing spec` → `drawing generate`
  → 真记录判「一致」→ 改声明公差 → 判「漂移」。它同时是第 46 片「签名吃全出图输入」的
  独立回归（R6 注入实测两条一起红：本片的端到端 + 第 46 片的单位级）。
  真库读数（第 50 片 `/tmp/s50` 副本 `D50`，带齐 `state.db`+`bom.db`，两次 apply 再扫）：
  `扫描 5 条：一致 1、漂移 3、不可判 1、没有可比对的键 0`，
  `should_be_stale` 只有 `T-004`(quote_batch, active) `0eb6eaee62ee879f → 4ec59c5593f0ba23`，
  `T-003` 落「第 50 片按文件态算的键」那一格，**rc=4**。
  常驻用例 **2391 → 2398**（`test_quote_lineage.py` +5、`test_truth_drift.py` +2）；
  撤改电池 `/tmp/s52/battery.py` **7 条：杀 7 / 活 0 / 注入无效 0**（对照臂 rc=0，一臂一原告）。
  本轮**不做新的外部检索**：判据形状沿用第 46/48/50 片已定三条，唯一裁决由本轮读到的
  代码事实决定（跳过理由按诚信条款写明）。仍未接上：`artifact=bom` 无返工执行器；
  发现 ≠ 触发（漂移清单→建返工任务仍靠人）；本地开发库刻意没碰，存量漂移半径仍是未知数。
  证据见 `docs/audit/DRIFT_QUOTE_PROJECTION_F-DRIFT-2_2026-09-26.md`。

- **v5.12 F-DRIFT 第 51 片：新公开命令 `aipd truth drift`——发现「上游已变、下游还 active」不再靠人记得**：
  第 48/49/50 三轮的 §七 都留了同一句：传播的触发靠人给 `--upstream`。
  写侧（生产者）与执行侧（返工执行器）都接上了，缺的是**发现**那一半。
  新增 `src/aipd_os/product_truth/drift.py`（纯分类，四态
  `in_sync / drifted / undecidable / no_record_signature`）+
  `src/aipd_os/cli/commands_drift.py`（四类制品的 resolver：读声明文件、取模型摘要、
  开 `bom.db` 取当前行）+ `cli/main.py`/`commands.py`/`command_contract.py` 接线。
  技术选型这轮做了真实检索并**改变了设计**：读到 dbt《Node selector methods》
  （`state:*` 是「与上一份 manifest 比」，body/configs/relations/descriptions 算变更、
  tags/meta 刻意不算）与 Nx《Run Only Tasks Affected》（原文 "Nx uses the Git history
  and the project graph"，从真相源现算、不存基线），对比本仓第 46 片已实读的 Bazel action key，
  **选 B 的思路 + C 的键形状** ⇒ 不新建基线表、不做基线刷新策略，
  避开「基线工件自己会比现实更旧」那个坑（本仓记录里本来就存着上一份键，基线住在记录身上）。
  命令形状也对比过：给 `truth propagate` 加 `--scan` 要把它的 `--upstream`
  从 `required=True`（实测 `cli/main.py:578`）改松并新增「两个都不给」的退码语义，
  那是在改一条既有命令的契约 ⇒ 选新开一条只读命令。
  三条判据：**只读**（跑出漂移后整表逐字段不变，这条是断言不是叙述）；
  **不可判不折叠**（拿不齐输入的记录既不折成没漂也不折成漂了——第 48 片那批没存口径值的
  `bom_cost`、以及本轮没接 resolver 的 `quote_batch` 都落这一格，静默跳过会把覆盖率读成 100%）；
  **空库不算通过**（`clean=False`、退码 4）。
  键的两端**由各类制品自己交出**：`drawing_spec` 存的是 `spec_sha256` 而不是
  `input_signature`，用一个字段名兜两类记录会把「读不到键」与「键确实不同」混成同一种读数
  ——这是写第一版时被用例当场打红才改的。
  真实库读数（第 50 片留下的 `/tmp/s50/state.db`：改过报价、没重跑 cost calc）：
  `扫描 3 条有效制品记录：一致 0、漂移 2、不可判 1、没有可比对的键 0`，
  `T-001`(bom) 与 `T-002`(bom_cost) 都被点出、`T-003`(quote_batch) 落不可判，**rc=4**
  （第一次读成 0 是 `| tail` 的退码，本仓第三次踩这条，已去掉管道重测）。
  常驻用例 **13 条**（`tests/test_truth_drift.py`）；撤改电池 **7 条：杀 7 / 活 0 / 注入无效 0**
  （对照臂 rc=0；D2 把不可判折进一致→2 红、D5 未覆盖类型静默跳过→1 红、
  D6 扫描顺手标 stale→1 红、D1 空库算通过→1 红等）。
  新公开命令的镜像按「新增公开命令」那一档全套同步：契约、COMMAND_FUNCS、子解析器、
  `SKILL.md` 分组清单与「主线共 57 个」→58、README 速查、registry 三处、
  `tests/test_command_surface_census.py` 两处手写分母 67 → 68（新命令有 argv 位真调用用例，
  属合法增长；不改它它会红两次）。一处被门禁抓住的错写法：把新命令塞进 registry 的
  `entry_point`（`; ` 分隔两条点号路径）被 `test_capability_entry_surface` 判红——
  那个字段只接受单个可导入 callable，改放 `implementation_file` 与 `run_command`。
  全量收集数 2378 → 2391。仍未接上：**发现 ≠ 收口**（本命令只报不写，
  要收口仍得 propagate + rework）；`quote_batch` 没有 resolver；
  `drawing_dxf` 的 resolver 本轮没有真库端到端用例；扫描耗时未量；
  本地开发库刻意没碰，所以「存量库里到底漂着多少」仍是未知数。
  证据见 `docs/audit/TRUTH_DRIFT_F-DRIFT_2026-09-26.md`。

- **v5.12 F-LINEAGE-QUOTE 第 50 片：整条链上第一次有人往 BOM 版本记录**连入边****：
  新增 `src/aipd_os/supply_chain/quote_lineage.py` 与 `aipd quote apply --truth-lineage`：
  按「全部参与判定的报价事实（供应商/件号/版本号/状态/单价/行币种）+ 批次币种」写一条
  `artifact=quote_batch` 版本记录，连一条指向**当前** `artifact=bom` 记录的 `affects` 边。
  改前事实是普查出来的（全 `src` 按 `add_edge`/`add_fact`/`ProductTruthStore` 三符号交叉，
  不是按名字 grep）：`supply_chain/` 的写点**全是** `add_fact`（`persistence.py:46,83,118`、
  `writeback.py:47,78`、`impact.py:108`），一处 `add_edge` 都没有；
  而 `artifact=bom` 唯一写点在 `bom/cost_lineage.py` ⇒ 报价把单价就地写进 BOM 行之后，
  第 48 片登记过的那笔成本结论仍是 `active`，读的人看到「下游已处理」其实价已经换过。
  真实 CLI 读数（`/tmp/s50`）：`quote apply --truth-lineage` 写 `T-003` 并把边挂到 `T-001`；
  `truth propagate --upstream T-003` ⇒ `affected=[T-001, T-002]`、两条都标 stale、
  生成 `RW-001`/`RW-002`、退码 4——**从报价出发跨两跳打到了那笔成本结论**，
  这是 F-SUPPLY-03 那句「声明的影响传播 vs 只有 payload」第一次有了反向证据。
  三条刻意的形状：① **来源文件名不进签名**（同一批价换个路径重下载不是又一次工程变更，
  与第 46 片把 DXF 的 `$TDCREATE` 挡在签名外同理由；路径只写进 `metadata.source` 当观测）；
  ② 报价完全可以先于任何一次 `cost calc --truth-lineage` 发生，那时下游记录**还不存在** ⇒
  记录照写、`edges=0`、把原因点名（不算失败：常驻用例在「有 BOM 行、只缺版本记录」的形状下
  断言 `ok=true` 且退码 0）；③ 空报价什么都不写，不给旗子是明说的跳过，
  写不进去判未收口（退码 4 且 `ok` 同向）。
  签名怎么定出来的被用例逼过一次：初版把文件名吃了进去，两条数记录条数的用例当场翻红，
  顺着查出「同价换文件名会另起一版并把下游标 stale」这类假工程变更，才把 source 移出签名，
  并补正反对照（改单价/币种/版本/状态/加一行都要换签名，改文件名不要）。
  常驻用例 **10 条**（`tests/test_quote_lineage.py`）；撤改电池 **9 条：杀 9 / 活 0 / 注入无效 0**
  （对照臂 rc=0）。电池这轮教了自己三次，都记进取证文档：
  **还原禁止反向 `replace`**（一支注入串短到 `"}\n"`，反向替换命中全文，
  把另一处代码吃成一个只在空 metadata 才触发的 NameError，**10 条用例照样全绿**、
  是 `ruff` 的 F821 抓到的）；**恒真注入不算判决**（把 `"source": "x"` 加进签名对所有记录同值，
  读出 SURVIVED 会被误判成缺用例，得改成真能翻转行为的实现）；
  **一次存活是真缺陷**（撞键用例只改了批次币种、没改行币种，那一列本来零覆盖）。
  登记与镜像：`registry_data` 三处（生产者计数 四→五、第五处生产者叙述、
  `industrialize.quote_to_bom_cost` 那行的 run_command/input_output/unit_test）、
  `truth_architecture`、README 速查；生产者棘轮登记新文件。
  **只给既有命令加旗子、未新增命令** ⇒ 命令面计数与 census 分母不动；
  连带改判清单为空（`quote apply` 原有「同文件重放零新事实/零改价」等断言全部保持）。
  全量收集数 2368 → 2378。仍未接上：传播仍靠人给 `--upstream`（报价换了不会自动 propagate）；
  `artifact=bom` 自己仍没有执行器；CTQ 方向仍断，「改一条 CTQ 打到成本」不成立。
  证据见 `docs/audit/QUOTE_BOM_LINEAGE_F-LINEAGE-QUOTE_2026-09-26.md`。

- **v5.12 F-REWORK-COST 第 49 片：成本结论这一支从「只有边」补成「边 + 执行器」**：
  第 48 片收尾那句「`bom` / `bom_cost` 两类制品没有返工执行器」本轮翻转一半——
  `bom_cost` 接上了，`artifact=bom` 那条仍没有。接之前先读码发现一条更硬的前提：
  `bom_cost` 记录的 metadata 里**只有输入签名的哈希、没有口径五项的值**，
  光加分派分支根本重算不出同一次核算 ⇒ 本片第一步是补生产者、第二步才是执行器。
  新增 `src/aipd_os/bom/cost_rework.py`（`rework_cost_artifact`）+
  `cli/commands_manufacturing.py` 的共用入口 `calc_current_cost`（`cmd_cost` 与重算器同一条路，
  不复制第二份「怎么取行、怎么装 CostInputs」）+ `truth rework` 的三类制品分派。
  两条纪律值得单列：① **执行器不走生产面的写版本路径**——`propagation.run_rework` 成功时是
  对**这一条**记录 `bump_version` 并关 stale，所以这里用 `store.update` 演进它本身；
  若改调 `record_cost_lineage`，BOM 真动时它会另起新版并把旧版标 superseded，
  引擎随后 bump 的就是那条被 superseded 的记录，收口等于没发生；
  ② **缺输入的旧记录点名拒，不猜口径**（第 48 片那批记录没有口径值，
  拿 `--tooling 0` 猜一遍会得到一条「按当前 BOM 重算过」的假结论）。
  另外三种「不算收口」也各自钉住：重算器抛异常、回得不全、核算不完整（缺供应商/单价），
  外加两条一致性拒绝——结论挂的 BOM 已不是当前那份、签名没变而金额变了。
  真实 CLI 全程走一遍：`unchanged` 一支 `total=63500.0`、任务 succeeded、记录仍是同一条
  （`T-002` v1→v2）；改 BOM 行后**不重跑 cost calc** 走 `recomputed` 一支，
  `total=69900.0`、边重挂到当前 BOM 记录、有效记录**仍是 2 条**（`T-002` v2→v3，
  正文变成 `bom_cost BOM-001 inputs=531cab84… total=69900.0`）。
  常驻用例 **15 条**（`tests/test_cost_rework.py`，每条拒绝用例都整表复读「拒跑不许写坏记录」）；
  撤改电池 **11 条：杀 11 / 活 0 / 注入无效 0**（对照臂 rc=0），其中 R9 特意写成
  「多 add 一条重复记录」这种能跑通的错实现，好让「返工不新增版本记录」那条断言真被打红
  而不是记成一次崩溃杀。
  一条常驻断言按新事实**改判**：第 47 片钉的「supported 清单只有两类」翻红后只改清单那一行，
  后半段（`artifact=bom` 仍点名拒、不烧 attempts、记录不许被打成 blocked）原样保留。
  参数面门禁自己被抓到一次 over-collection：`cli/main.py` 里 `cp` 被赋值过三次
  （cad preflight / cad build / cost calc），只按变量名收旗子会把 `--manifest`、`--target` 收进来；
  且 `ast.walk` 是广度优先，按源码顺序推状态机不成立 ⇒ 改成按赋值行号切范围，
  并补一条「坏旗子出现即判范围切错」的反向对照（原来的 `dests ⊇ {tooling,quantity}` 那种
  「好东西够多」式前提断言，塞进垃圾时照样成立）。
  登记与镜像：`registry_data` 四处、`truth_architecture` 两处、README 速查三类制品、
  第 48 片取证文档 §七 那句在原行内标注被推翻一半、生产者棘轮登记 `cost_rework.py`。
  未新增命令也未新增旗子 ⇒ 命令面计数与 census 分母不动。全量收集数 2353 → 2368。
  仍未接上：`artifact=bom` 那条版本记录没有执行器；没有任何生产者往它连**入边**
  （所以「改一条 CTQ 打到成本」仍不成立）；触发仍靠人给 `--upstream`；
  执行器不刷新 `facts.cost.total`，返工后会有「结论已收口、fact 还是旧数」的两态。
  证据见 `docs/audit/COST_REWORK_F-REWORK-COST_2026-09-26.md`。

- **v5.12 F-LINEAGE-COST 第 48 片：把「BOM 版本 → 成本结论」这一支接上血缘生产者**：
  第 47 片收尾那句「仍未接上：BOM / 成本那一支既没有血缘生产者也没有返工执行器」本轮**翻转一半**——
  生产者接上了，执行器仍没有。改前的断法是实证的：成本只写进 `facts.cost.total`，
  `conditions` 是一句 `bom=BOM-001 qty=… tooling=…` 的**拼串**（拼串不是键，改一行 BOM 就连不回去），
  且 AST 普查里 `bom/` 与 `supply_chain/` 两个目录**一处 `add_edge` 都没有**。
  新增 `src/aipd_os/bom/cost_lineage.py`（`record_cost_lineage`）并给 `aipd cost calc` 加旗子
  `--truth-lineage`：写两条 `artifact_version`（`bom` / `bom_cost`）+ 一条 `bom → cost` 的 `affects` 边。
  四条判据：① **身份按输入签名**，沿用第 46 片实读 Bazel action key 定下的取舍（本轮不做外部检索，
  理由与签名集合写在取证文档 §二：新的只是「BOM 与成本各自吃哪些输入」，答案在本仓 `CostInputs`/`BOMLine` 里）；
  ② **BOM 签名吃全行事实、成本签名再叠口径五项**（`tooling_fee`/`target_quantity`/`amortize_over`/`nre`/`margin_pct`），
  于是「只改毛利率」只另起成本版、BOM 版不动——这一条正是把「只记 bom_id 的实现」照出来的那一条；
  ③ **同作用域只留一版有效**，新版落下把旧版标 `superseded`，否则一次改 BOM 会把历史成本全打成待返工；
  ④ **空 BOM 什么都不写**，不给旗子是**明说的跳过**（`lineage_skipped` 说出不登记的缘由），
  给了却写不进去判**未收口**（退码 4 且 `--json` 的 `ok` 同向）。
  全程用真实 CLI 取一遍证（`.venv/bin/aipd`，可编辑安装确认跑的是本树 `src/`）：
  同输入两次 `cost calc` 命中 `T-001`/`T-002` 且 `created=false`；加一行 BOM 后另起 `T-003`/`T-004`；
  `truth propagate --upstream T-001` ⇒ `T-002` 转 **stale** 并生成任务 `RW-001`（rc=4、`pending_rework=true`）；
  `truth rework --task RW-001` ⇒ 按制品点名**拒**（`artifact_kind: bom_cost`，`supported_artifacts` 仍只有图纸两类）
  且 `attempts` 保持 0、任务仍 pending——登记里那句「保持 pending 或被拒」由此有了读数。
  常驻用例 **10 条**（`tests/test_cost_lineage.py`）；变异电池 **8 条：杀 8 / 活 0 / 注入无效 0**（对照臂 rc=0），
  其中 E1（命令面不调生产者）一注入打下 6 条，说明这 10 条几乎全挂在接线上而不是各自独立成立。
  两条电池/量具自己的收获：退码最初带 `| tail -3` 读成 rc=0，那是 `tail` 的退码不是 CLI 的（去掉管道重测为 4）；
  `truth_lineage` 只有 2 行而 `sqlite_sequence.seq=4`，成因是 `add_edge` 的 `INSERT OR IGNORE` 配 AUTOINCREMENT
  **被忽略的插入照样消耗序列号**，已用「行数不变、seq 随 calc 次数 1:1 递增」对上，不是丢边。
  登记与镜像：`registry_data` 三处（生产者计数三→四、`industrialize.quote_to_bom_cost` 的 limitation、
  unit_test 列表）、`truth_architecture` §二那句旧否定句就地更正、README 成本核算速查行；
  生产者棘轮登记 `bom/cost_lineage.py`（同一次普查 11 处 `add_edge` 全部在册）；
  第 47 片漏改的那句「BOM/成本那一支仍没有血缘生产者」在原行内清掉。
  **只给既有命令加旗子、未新增命令** ⇒ 命令面计数与 census 分母不动。
  全量收集数 2343 → 2353。仍未接上：`bom` / `bom_cost` 两类制品**没有返工执行器**；
  且没有任何生产者往 `artifact=bom` 那条记录**连入边**（`quote apply` 写的是 `quote.*` fact），
  所以「改一条 CTQ 会打到成本」仍不成立——本轮那条链是从 BOM 版本记录起算的，触发也仍靠人给 `--upstream`。
  证据见 `docs/audit/BOM_COST_LINEAGE_F-LINEAGE-COST_2026-09-26.md`。

- **v5.12 F-REWORK-DXF 第 47 片：图纸这一跳从「只有边」补成「边 + 执行器」**：
  第 46 片把 `声明 → 图纸` 的边接上之后，`truth propagate` 才真的开始生成 `drawing_dxf`
  的返工任务，而那些任务的处置是「在烧 attempts 之前逐条点名拒掉」——缺口从理论变成日常。
  本轮新增 `src/aipd_os/cad/dxf_rework.py`（`rework_dxf_artifact`）并把 `truth rework`
  改成按制品分派（`drawing_spec` 重算声明、`drawing_dxf` 重跑出图，其余仍点名拒），
  `--json` 的 `supported_artifact` 单值随之变 `supported_artifacts` 列表。四条判据：
  ① **重跑调的就是 `drawing generate` 那个 handler（`cmd_drawing`）**，不复制第二份投影代码
     （`render` 由调用面注入 ⇒ `cad` 层不 import CLI 层，执行器能拿假 renderer 单测；
     刻意不绕 `cli.main`：`main → commands → commands_truth → commands_drawing → main` 会成环，
     `tests/test_import_cycles.py` 在本轮全量里真翻过一次红）；
     代价是参数得手工还原成 `argparse.Namespace`，于是加了一道门禁：
     `TestRenderArgumentSurface` 按 AST 从 subparser 反查 `drawing generate` 的旗子清单，
     还原器漏一个就红——它第一轮还抓到提取器自己认错命令（按名字找 `generate` 会撞上
     `manual generate` 的 18 个旗子，分母非空照样成立），于是补了「分母必须含 --step/--views
     且不含 --prompt/--output-dir」这条前提断言；
     判据形状本轮实读 FreeCAD TechDraw 文档——视图靠 `Source` 挂在实体上，
     模型变了要显式 `doc.recompute()` 才更新，即"派生物 + 显式重算"这一步；
     「要不要重算按输入签名判」沿用第 46 片实读的 Bazel action key 取舍。
  ② **只认退码 0**：退码 4 的含义是「图出来了但判未收口」（合格域冲突等），
     把它记成返工成功等于让引擎替我们把一条未收口的事实 bump 成新版本；
  ③ **先出到暂存目录，确认收口才替换正式产物**——一次失败的返工不许顺手毁掉现状
     （②③ 各配一条注入臂：E7 放宽退码、E8 去掉暂存，两条都只打中同一条用例的 different 断言）；
  ④ **返工不新增版本记录**：引擎 bump 的是这一条，所以执行器演进它本身并把边改挂到
     **当前**那份声明记录上（生产面「换输入另起一版 + 旧版 superseded」的规则不适用，两边刻意不同）。
  还有一条防"猜一次重画"的纪律：第 46 片之前写的记录里没有 `model_*`/`material`/`sections`/`details`，
  那些记录**重建不出同一次出图**，执行器一律 `missing_inputs` 点名拒，而不是拿默认值猜——
  猜出来的图会被记成"按当前声明重算过"。
  常驻用例 **14 条**（`tests/test_dxf_rework.py`，其中 3 条真跑 CAD 出图）；
  变异电池 **9 条：杀 9 / 活 0 / 注入无效 0**（对照臂 rc=0）。
  电池又一次教自己：E9「rewrote 之后不把边连到当前声明记录」**首版存活**——
  补边这条事实当时只写在模块 docstring 里，没有任何用例的断言指向它；
  补上「边必须改挂新声明记录（并先断言声明记录确实有两条，免得前提塌了断言变空）」才杀得动。
  登记与镜像：`registry_data` 两行、`truth_architecture` §二/§七、README 出图例、
  生产者棘轮登记 `dxf_rework.py`、第 46 片取证文档 §七 那句现在时措辞就地更正。
  全量收集数 2329 → 2343。仍未接上：**BOM / 成本那一支既没有血缘生产者也没有返工执行器**。
  证据见 `docs/audit/DXF_REWORK_F-REWORK-DXF_2026-09-26.md`。

- **v5.12 F-LINEAGE-DXF 第 46 片：把血缘链的第三跳接上——「图纸声明 → DXF 制品」现在有生产者**：
  第 43 片接 CTQ→声明、第 45 片给声明接执行器之后，`truth propagate` 仍打不到那张图：
  改了 CTQ 只会把声明标 stale，按旧声明画出来的 DXF 不受影响，而读的人看到「下游已处理」
  就等于把图纸放过了。本轮新增 `src/aipd_os/cad/dxf_lineage.py` 并接进 `aipd drawing generate`
  （该命令补 `--db/--tenant/--project`）：出图成功后写一条 `artifact_version`
  （`metadata.artifact=drawing_dxf`）并连「声明记录 → 图纸记录」的 `affects` 边。四件被钉住的判据：
  ① **身份按输入签名不按 DXF 字节**——签名 = 模型摘要 + 声明内容哈希 + **全部**出图参数（part/revision/views/scale/sheet/material/剖切/放大）。
     「模型」那一半是收口前自己复现出来才补上的：同一 `--out`、同一参数分别用 `bracket.step` 与 `bracket_v2.step` 出图，修之前两次落在**同一条**版本记录上（`inputs=` 前缀一样、记录数 1），也就是两张图被记成一版；修之后记录数 2、两条签名不同（`/tmp/s46/sig_gap.py` 两遍实测）。
  这不是审美选择，是量出来的：同一输入连跑两次出图，两份 `.dxf` 的 **13170 行里只有 2 行不同**，
  差的是 `$TDCREATE` / `$TDUPDATE` 那一对儒略日时间戳（`/tmp/s46/bytes_probe.py` 实测），
  按字节哈希会把时间戳读成一次工程变更；DXF 自己的 sha256 仍写进 metadata 当**观测**，不当键。
  ② **同一产物路径只留一版有效**：新版落下时把旧版标 `superseded`（第 44 片之后 `superseded`
  在发布证据里是「可见但不算未收口」），否则一张图改十次就有十条永久下游，一次改 CTQ 会把
  那张图的历史版本全打成待返工。③ **连不上上游时记录照写、边数 0 且点名原因**——
  「没有可连的上游」与「上游没参与」不是一回事。④ **没给 `--db` 是明说的跳过**，
  写不进去则判未收口：`--json` 的 `ok=false` 与退码 4 同向（与第 43 片同一条纪律）。
  本轮自己踩到两处，都是量出来的：(a) 新用例的 CTQ 窗口 5.95–6.05 与 golden 支架几何不符
  （TOP 视图四个孔实测全部 **8.0mm**），于是每次出图都判「合格域未收口」退码 4——这条红差点
  让「血缘写失败 ⇒ 退码 4」那条用例**恒真通过**（rc 本来就 4），改成实测窗口后该用例的 4 才
  归因到 `lineage_error`；(b) `registry_data.py` 里「血缘边的生产者今天有两个」被上一轮拼接
  脚本写了两遍，本轮改这一行时一并清掉。常驻用例 **10 条**新增（`tests/test_drawing_dxf_lineage.py`），
  生产者棘轮登记补 `dxf_lineage.py`；变异电池 **10 条：杀 10 / 活 0 / 注入无效 0**（对照臂 rc=0），
  其中 E4「输入签名不吃声明内容」首版**存活**——原因是身份键里声明哈希被写了两遍
  （`inputs=<签名前 16 位>` 与 `← spec <声明哈希前 16 位>`），只断一处另一处仍会翻版，
  补齐两处的注入才杀得动；E8「把键换成按 DXF 字节」也确实翻红，反过来证明 ① 是条有牙的判据；
  E9/E10 是补漏之后新立的两支——把签名里的模型摘要或 material/剖切/放大单独抽掉，各自只打中一条用例（换模型另起一版 / 输入键适用域），说明这些输入是真在键上而不是碰巧一起变。
  全量收集数 2319 → 2329。仍未接上：**BOM/成本那一支没有血缘生产者**，DXF 这一跳只有边、
  **没有返工执行器**（落到图纸上的任务仍走「不认识的制品在烧 attempts 之前逐条点名拒掉」那条路）。
  证据见 `docs/audit/DRAWING_DXF_LINEAGE_F-LINEAGE-DXF_2026-09-26.md`。

- **v5.12 F-REWORK 第 45 片：`run_rework` 从「产品侧无人调用」变成有真实执行器**：
  第 31 片故意不接这一半——没有执行器时引擎只会判 `blocked`，而一条永远不可能成功的命令
  比没有命令更容易被读成「返工跑过了」；当时把缺口钉成断言并写明"接上执行器那一轮必须连同
  极性一起改判"。本轮兑现那句话：新增 `aipd truth rework --db --project (--task RW-xxx |
  --all-pending)`，执行器在 `src/aipd_os/cad/spec_rework.py`，三态判据借两条成熟实现的形状
  （**本轮实读文档**，非凭记忆）：dbt 的 `state:modified` 用"当前节点签名 vs 上一份 manifest"
  判变更、cosmetic 字段不算变更；BitBake 用输入校验和 + `STAMPS_DIR` 戳文件决定跳过还是重跑，
  上游签名变则下游连锁重算。落到本仓就是：
  ① `unchanged`——重算哈希与记录一致**且**磁盘产物重算后也一致 ⇒ 产物一个字节都不动，
  但库里的版本与 stale 真的收口（否则"没做"与"做了且证明未变"在库里同形）；
  ② `rewrote` / `file_restored`——内容变了，或内容没变但文件被删/被手改 ⇒ 用同一个
  renderer 重写、更新记录 content/metadata/source 并补 `ctq → 声明` 边；
  ③ `gap`——重算有缺口一律**失败**，交回引擎的有界退避与 `max_attempts`。
  还有一条防"把缺口伪装成配额用尽"的判据：**执行器不认识的制品（只认
  `metadata.artifact=drawing_spec`）必须在烧 attempts 之前逐条点名拒掉**，
  所以那类任务保持 pending 且 `attempts==0`，而不是被记成"返工失败三次"。
  同批改判（不删断言，只翻极性）：`tests/test_truth_propagate_cli.py::TestUnwiredHalfStaysVisible`
  → `::TestReworkHalfIsWiredAndItsBoundaryStaysVisible`（现在要求产品侧真有调用点，且必须落在
  CLI 那一层）、`registry_data` 两行、`docs/architecture/truth_architecture.md`、
  `commands_truth.py` 的模块说明与 `truth propagate` 的收口提示。
  第 43 片装的生产者棘轮**当场开火**：`spec_rework.py` 新增一处 `add_edge` 调用点被它拦住，
  按登记补进集合而不是放宽判据。常驻 `tests/test_truth_rework_cli.py`（8 条，含 `--json`
  的 `ok` 与退码同向、库不存在判 2 不判"没有待办"）+ 电池 `/tmp/s45/battery.py`
  **5 条：杀 5 / 存活 0 / 注入无效 0**（E1 跳过引擎伪造 succeeded→半径 5、E2 未变也去重写→1、
  E3 不认识的也照跑→2、E4 gap 记成成功→1、E5 只看记录哈希不看磁盘→1）。
  仍没接的那一半要说清：**DXF / BOM / 成本这几类制品今天没有执行器**，它们的任务正确地留在
  pending——"链路上还有几格没人跑"是读数，不是本轮的完成度。
  命令面同步：公开命令 56 → 57（`command_contract` 派生计数、SKILL 分组与计数、README 速查、
  命令面 argv 位棘轮的分母 66 → 67）。读数：全量 **2308 → 2316**（+8）。

- **v5.12 F-CTQ-STALE 第 44 片：把「要求被标陈旧」从"少一条要求"改判成"一条没收口"**：
  发布证据的 CTQ 分母来自 `_collect_ctq`，它按 `status="active"` 查——**非 active 的记录整条静默消失**。
  实测（两条 CTQ，一条标 stale）：`doc["ctq"]` 只剩一条，`issues` 里没有任何一句提到不见的那条。
  后果是一条 fail-open 通路：`gdt_covers_ctq` / `ctq_has_inspection` 的覆盖义务按分母算，
  两条里标陈旧一条就只剩一条要覆盖，**本来放行不了的发布反而能过**；只有全部掉光才由
  `no_ctq` 兜住。讽刺的是这个函数自己的 docstring 写着「缺 feature 的逐条点名（不静默少一条）」——
  它对"字段缺"守了这条纪律，对"状态不在 active"没守。
  改判：`stale / expired / blocked` 各出一条 **blocking** 点名，带上 record_id 与状态名
  （读者要能复核是哪一条，"有 N 条陈旧"不算点名）；枚举外的状态也走这一支，但那是兜底
  hardening——store 的 `update` 把状态核在 `TRUTH_STATUS` 内，今天没有生产者能写进去；
  `superseded`（被新版本合法取代）**不计入分母**
  但出一条非阻断点名，让读者看得见分母为什么小了。覆盖分母本身仍只含 active——
  本轮改的是"缩水必须可见"，不是把陈旧要求拿去和图纸硬核对。
  常驻 `tests/test_release_evidence_ctq_status.py`（6 条）里配了两条方向对照：
  全 active 时新判据**不许开火**（否则它只是永远抱怨），以及"非 active 混进分母"必须红
  （证明分母语义也被钉着，而不只是点名）；电池 `/tmp/s44/battery.py`
  **4 条：杀 4 / 存活 0 / 注入无效 0**（D1 降级成非阻断→2、D2 把 superseded 当缺陷→1、
  D3 点名不写记录号→3、D4 非 active 收进分母→5）。
  与第 43 片接上：那一轮之后 CTQ 真的会被 `aipd truth propagate` 打成 stale，
  所以这条通路从"理论存在"变成"按一次 propagate 就能踩到"——两片是同一件事的两半。
  登记行 `industrialize.release_evidence` 的 `current_limitation` 同步补这一段。
  读数：全量 **2302 → 2308**（+6）。

- **v5.12 F-LINEAGE-PROD 第 43 片：给「CTQ → 图纸声明」补血缘边生产者，`truth propagate` 的第二跳今天到得了**：
  前几轮登记里写着「血缘边只有 `product_intelligence/gate.commit_snapshot` 会写，
  CTQ/图纸/BOM 之间没有生产者，所以链条更长的那一段传播不到」——本轮先把这句**核实**了：
  `INTO truth_lineage` 全仓只有一个 SQL 写入口（`LineageGraph.add_edge`），
  而它的产品侧调用点确实只有 PI 那一处；`idea/decomposer.py`、`idea/evidence_relations.py`、
  `product_intelligence/service.py` 那三处 `add_edge` 写的是**另一张** canonical lineage 表
  （同名方法、不同存储），以前把它们算进"血缘生产者"就会高估传播面。
  新生产者：`aipd drawing spec` 成功落盘时，由 `src/aipd_os/cad/spec_lineage.py` 写一条
  `artifact_version` 记录（content 带声明正文的 sha256，所以"内容没变"重跑命中同一行、
  "CTQ 改了"自然另起一版）+ 给声明正文**实际引用到**的每条 `ctq_ref` 连一条 `affects` 边。
  三条刻意的取舍：**只连引用到的**（给没参与的 CTQ 连边＝让传播去打扰无关要求，
  而这一点在 CLI 面上打不出差别——未引用的 active CTQ 会先造成 gap 让整条命令 HOLD，
  所以选择性只能在函数级钉）；**HOLD 时文件与血缘都不写**（一份不存在的声明没有版本可言）；
  **信任上限 high**（正文哈希自证，生成过程没被独立复核，与第 42 片同一取舍）。
  自己写出来的失败面：血缘写不进去时原判 `rc=4` 却仍在 `--json` 里报 `"ok": true`——
  是那条红用例把这台"机器面与终端面各说一套"的裂缝抓出来的，现已同向改判。
  常驻 `tests/test_drawing_spec_lineage.py`（10 条，含一条"第二跳真的通"的传播用例——
  没有它其余各条只是在测自己写的表）+ 生产者集合按 AST **两向棘轮**；
  电池 `/tmp/s43/battery.py` **6 条：杀 6 / 存活 0 / 注入无效 0**
  （C1 撤调用→半径 5、C2 不改 ok→1、C3 改成连全部 active→1、C4 去幂等→1、
  C5 信任写 verified→1、C6 删 add_edge 循环→5 含棘轮）。
  `docs/architecture/truth_architecture.md` 与登记同步改判：第二跳通；
  **DXF/BOM/成本那一支仍没有血缘生产者**，返工的执行（`run_rework`）仍是 0 调用点。
  调研（真实检索）：写侧发边借 Apache Airflow 的 OpenLineage provider 形状
  （作业完成即由 emitter 发事件，事件带 job/run 与 inputs/outputs）；
  读侧重建是 dbt 的路子（解析 `run_results.json` / manifest 与上一份 state 比对再选目标）。
  选写侧：传播要在库里查图，而 spec JSON 会被改名搬走，靠解析文件重建等于把血缘
  挂在文件系统路径上。两者都不引依赖（OpenLineage 要额外服务与 HTTP 出口）。
  读数：全量 **2292 → 2302**（+10）。

- **v5.12 F-FACT-WB 第 42 片：主管的步骤标签 `update_facts_evidence` 从此对应一次真写回**：
  `run_supervisor` 的成功分支把这个名字追加进 `steps_log`，而那段代码实际只做
  `complete → _register_outputs → _quality_gate → _mark_stale`，**没有任何一句把事实/证据
  写回结构化表**——`steps_log` 是一串自述标签，读的人和能力登记都据此以为"事实写回已做"。
  同时登记里那句「全库无独立 product_truth/facts 表」**早就不成立**（`product_truth` 表
  自 v5.9 就在 store 的 SCHEMA 里），错话在登记里躺了几轮没人复核。
  现在 `_write_back_facts()` 真写一条 `record_type="evidence"` 的 `product_truth` 记录：
  作用域跟着工作项走（不写死 default）、content 由 run 标识 + 输出哈希决定因此同一 run
  重放不重复建行、`source.file` 取执行留下的首条证据引用（不新造字符串）；
  **信任分级由独立质量门推导且上限 high**——那道门只核"证据引用与输出哈希在不在"，
  把它读成 `verified` 就是第 32/34 片"机器默认值被读成权威"的同一族病；
  写回失败**不静默**：步骤标签改判 `fact_writeback_failed`（注入 B5 只被这一条用例抓住）。
  常驻 `tests/test_supervisor_fact_writeback.py`（7 条）+ 电池 `/tmp/s42/battery.py`
  **6 条：杀 6 / 存活 0 / 注入无效 0**（B1 伪造成功摘要→半径 5、B2 信任写成常量 verified→2、
  B3 去掉幂等预检→1、B4 作用域写死 default→4、B5 失败静默→1、B6 把旧错话抄回登记→1）。
  `registry_data` 该行与 `docs/audit/capability_matrix` 同步改判，能力分类**仍留**
  `partially_implemented`：本轮**没写 `truth_lineage` 边**（工作项与上游 truth 之间还没有映射），
  所以这条证据今天不会被 `aipd truth propagate` 传播到——那是下一片的入口。
  调研（真实检索，非杜撰）：Apache Airflow 的 OpenLineage provider 文档给出"执行完成即由
  emitter 发 COMPLETE 事件、事件带 job/run 标识与 inputs/outputs"的形状；dbt 用
  `run_results.json` 里的 `invocation_id` 做同一次运行的幂等键。两者都不接进依赖——前者要额外
  服务与 HTTP 出口，后者是文件工件而不是库内可查询的事实。本仓已有带 tenant/project 作用域、
  且与主管共用同一张连接登记表的 truth store，故**借它的事件形状、落自己的表**，零新依赖。
  读数：全量 **2285 → 2292**（+7）。

- **v5.12 F-DOC-REF 第 41 片：给「文档写出的 path:line 还指得回代码吗」装一把常驻尺子**：
  这根轴是被上一片自己喂出来的——收尾普查抓到我在第 39/40 片写进 CHANGELOG 的一句
  「与同仓 `ts_interface_shape.py`(tree-sitter) 同形」，**那个文件不在本仓**（真先例是
  `src/aipd_os/interface_contract.py` 与 `schema_binding.py`，全仓没用 tree-sitter）。
  新增 `scripts/doc_reference_census.py`：把全部文档里的代码引用切成六档
  （`resolved` / `missing` / `multi` / `external` / `elided` / `line_beyond_eof`，
  Σ 分类 == 分母是硬断言；**档位绝对数不进本文件**——这把尺子的语料包含记录它读数的文档本身，
  每编辑一次历史面文档绝对数就漂一次，快照只留在
  `docs/audit/DOC_REFERENCE_CENSUS_F-DOC-REF_2026-09-26.md`（不参与发布哈希），
  这里只钉树无关的那格：**两棵树的现状面都是 0**），**现状面**（README/SKILL/docs 架构面/references）判红、
  **历史面**（CHANGELOG 与 docs/audit，记的是当时的事实）只报不判——这条取舍借自同类工具
  dsh-doc-guard 的「现状核对时忽略历史 changelog 行」。今天现状面 **0 条**。
  判据本身被合成语料钉住 20 条（正反两向），三个退化匹配当场被抓并被这条轴自己咬到：
  ① 扩展名表里有 `dxf`，`ezdxf/…` 会被切成 `ezdxf` + `/entities/polygon.py` 两段
  （修法：整段必须以扩展名结尾 + 左边界）；② 表里有 `sql`，`aipd_state.sqlite`
  被读成一条 `aipd_state.sql` 引用；③ 点号前不限词，`.py`/`.manual.json` 这类**裸后缀提法**
  与 `<db>.manual.json` 这类**占位写法**都被当成路径。修完还造出两条假缺陷才看清：
  判据第一版更糟——它把 CLI 示例操作数、第三方内部路径、省略写法全算成缺陷，
  报「514 条 missing / 活文档 97 条」，那是尺子造的数，不是文档的数。
  文档侧一处真形改：`references/local-cad-fallback.md` 的 `cad/model.py` 是
  **用户项目里生成的文件**，改写成 `<项目目录>/cad/model.py`，让写法与含义一致。
  常驻 `tests/test_doc_reference_census.py`（7 条）钉四件事：现状面为 0、分母非空转
  （Σ 分类 == 引用总数、resolved > 2000）、**豁免名单不许把现状面文档划进历史**
  （注入 D3 专打这一格——把 README 加进 HISTORY 会让判红形同关闭）、
  历史面读数不许被静默清零；量具 `--self-test` 由本文件子进程真 spawn。
  性能一条教训：首版逐条引用去 `rglob` 找同名，常驻用例跑到 **99.6s**；
  换成整仓文件清单读一次缓存后 audit 1.8s、整个用例 2.5s（顺带把 `__pycache__`/`.pytest_cache`
  移出可解析集，历史面读数因此从 114 变 116，是收紧不是漂移）。
  读数：全量 **2278 → 2285**（+7）；电池 `/tmp/s41/battery.py`
  **5 条：杀 5 / 存活 0 / 注入无效 0 / 崩溃式红 0**（D5 第一次打在了 fence 的开块 continue 上、
  没打真正的 `if fence: continue`，于是"存活"其实是注入无效；给 fence 那一支补一条
  自己的最小对照——不以 `aipd ` 开头的代码块内容——重瞄后才真开火）。
  调研：已检索同类工具（dsh-doc-guard 核版本标记/目录树/指标但不核散文 `file:line`；
  GitLab 文档流水线用 lychee 只核链接与锚点、markdownlint 核结构、Vale 核文风；
  反向的「代码里指向文档的链接」另有作业）。没有现成件覆盖本轴，故自研薄判据并借鉴其取舍。

- **v5.12 F-CLI-COV 第 40 片：把在册 17 条命令补成走过 CLI 入口的真调用（读数和成 66/66）**：
  第 39 片修好量具后登记在册的 17 条——10 条零证据（`cad preflight` `dashboard` `onboard`
  `operate` `product show` `product gate` `recover` `reset` `ui` `version`）、4 条只被
  deprecated 别名走过（`cad build` `package` `resume` `test`）、1 条只被直调处理函数走过
  （`doctor`）、2 条调的是 `cmd_outbox` 这种共用处理函数（`outbox drain` / `outbox review`）——
  全部补成 `tests/test_cli_public_surface.py`（14 条）里的 `main([...])`：**走 argparse、走分发**，
  断言落在读数上而不是「rc 不为 0 就算跑过」。三处判定值得单记：
  ① `cad build` 在 faceted_brep 封顶 C1 时目标 C1 仍 rc=4 且 `reached_level is None`——
  这是门禁在拦，不是没接线，与 `cad preflight`（同一份 manifest 判「上限允许」⇒ rc=0）
  正好两问分开；② `outbox drain` 与 `outbox review` 各走一次并断言**两份读数不同**，
  否则共用处理函数那条歧义档永远关不掉；③ `ui` 只 mock `aipd_os.web.serve` 那一层，
  断言 db/host/port 三个参数原样交到位（起真服务会挂住套件，直接调 `cmd_ui` 又看不见接线）。
  棘轮随即按设计判红「已补真调用却没删格」17 条：`BASELINE` 清空、
  `cli` 档非空转前提从 49 改 66，并新增 `CLOSED` 闭合账（17 条 × 证据文件名 needle，
  断掉即红）——空基线本身是个空循环，这一面必须有东西接着。
  顺带修掉一处我自己上一轮写的**把现状当应然**的断言：`test_command_coverage.py` 的报告用例
  原先硬要求「必有未测缺口」，补满 66 条后它自己成了假红；缺口存在性归棘轮与闭合账管，
  报告只报。读数：全量 **2263 → 2278**（+15：新用例 14 条 + 闭合账 1 条；收集数 2266 → 2281）；
  电池 `/tmp/s40/battery.py`
  **5 条：杀 5 / 存活 0 / 注入无效 0 / 崩溃式红 0**（两条注入纪律现学：撤改要逐文件核还原，
  别拿全仓 sha 判本臂；注入用的 import 若落在被测文件里，必须让夹具自己带上，否则电池结束时
  留下一处"看着像用户改动"的泄漏）。
  调研豁免：本片只补测试与账，不改判据实现、不引新技术。

- **v5.12 F-CLI-COV 第 39 片：命令覆盖率那把尺子两头都在错（15 条假未测 + 7 条零证据假已测）**：
  轴换到「常驻测试到底有没有走过这条命令的 CLI 入口」。`tests/test_command_coverage.py`
  把 `tests/` 拼成一个大字符串再用 `cmd in blob` 判「被测」，同一个命令名在测试里有
  毫不相干的出现方式，于是读数两头错：`main(["drawing", "dfm", ...])` 是两个相邻字符串
  常量，子串 `"drawing dfm"` 匹配不上（假未测 **15** 条，含 `bom release`/`issue list`/
  `readiness check`/`validation plan` 等）；`eco` 四条走 `main(["eco", *argv, ...])`
  这种转发器，更是完全看不见。反过来 `from ezdxf import recover` 顶了 `recover`、
  dict 键 `"version"` 顶了 `version`、`cmd_doctor` 这个 import 顶了 `doctor`、
  `test_new_commands_registered` 里那张名字清单顶了 `cad preflight`/`test`/`package`
  （假已测 **7** 条：`cad preflight` `dashboard` `onboard` `recover` `reset` `ui` `version`；
  另 6 条判对但理由错——`cad build`/`package`/`resume`/`test` 只被别名走过、`doctor` 只被
  直接调处理函数走过、`outbox drain` 调的是与 `outbox review` 共用的 `cmd_outbox`）。
  旧读数 66 注册 / 47 已测 / 19 未测，真读数是 **49 条走过 argv 位**、
  4 条只被 deprecated 别名走过、1 条只被直接调处理函数走过、2 条处理函数被两条命令共用
  分不清 verb、**10 条一次都没走过**——两个方向的错互相抵掉，总数看着还挺合理。

  同一个文件里的声明面更静：`_declared_commands()` 从**含「一键命令」的那一行**往后收集，
  而 SKILL.md 里那一行是标题 `## 0. 一键命令`、下一行是空行 ⇒ 循环第一次就 break，
  **解析结果恒为 0**；`0 ⊆ 注册` 恒真，于是「声明 ⊆ 注册」与「注册 ⊇ 声明」两条断言
  一直绿着，报告却同时印出「声明 0 / 已注册但未声明 66」。CI 侧那份
  `scripts/skill_quality_audit.py` 早就是按小节边界取段、能真读出 56 条——
  一份坏副本与一份好副本并存，而读者信的是常驻用例那份。

  修法是把判据收成一处 + 让它自己可证伪：新增 `scripts/command_surface_census.py`
  （AST 读调用形态，五档 `cli`/`alias`/`handler`/`handler_ambiguous`/`none`，
  别名↔真名由契约的 `replacement` 现派生不手抄，量具自身文件一律排除，
  空语料与解析失败判「读数不可信」而非绿），`--self-test` **10 条合成语料注入**
  正反两向全立住；`skill_quality_audit.py` 的真调探针与 SKILL.md 解析改为共用这一份
  （并抽出纯函数 `declared_from_skill` 才谈得上注入反证）。常驻侧新增
  `tests/test_command_surface_census.py`（9 条）把「低于 cli 档」钉成**双向棘轮**：
  新注册命令没有 argv 位用例 ⇒ 红，登记里的命令补上了真调用 ⇒ 也红（记录只减不增），
  档位自己漂移同样红，外加 Σ 档位 == 分母 66、写盘 JSON 与内存读数同源、
  证据里不许出现量具自身。`test_command_coverage.py` 删掉那份恒 0 的解析器，
  声明面改按契约双向核（`registered == PUBLIC ∪ DEPRECATED ∪ INTERNAL`）、
  并补上「解析器能红」的注入反证——原来 6 条现 8 条。
  读数：全量 **2252 → 2263**（+11，2266 收集），连跑四趟：第一趟只红在两条清单哈希
  （新量具与镜像未入册，预期），第二趟清单转绿但红在 `test_state_perf_gates.py:146`
  那条 5× 比值门（load 28 下实测 4.28×，隔离复跑 0.53s 绿 ⇒ 并发噪声，**不放宽门**），
  第三趟 0 failed，第四趟（收口补记落盘后的树）同样 0 failed、报告
  sha256 前缀 `9a9629f2c3f4` 绑进 `PROVENANCE`；电池 `/tmp/s39/battery.py`
  **7 条：杀 7 / 存活 0 / 注入无效 0 / 崩溃式红 0**（第一条注入把「丢掉 argv 位置要求」
  写成了「取第一个字符串元素」，与未注入形态等价 ⇒ 是注入无效不是判据弱，改成逐元素记账后
  才真开火），逐条点名见 `docs/audit/COMMAND_SURFACE_CENSUS_F-CLI-COV_2026-09-26.md`。
  下一步（未做，本轮只修量具）：登记在册的 10 条 `none` 与 4 条 `alias`-only 命令
  要补真 argv 位用例，按棘轮规则只能"补了才删格"。
  调研豁免：本片不改技术选型——AST 判据用标准库 `ast`，与 `src/aipd_os/interface_contract.py`、
  `src/aipd_os/schema_binding.py` 用同一套语言内置能力，无新依赖引入。
  **该处原文误引了一个不在本仓的文件名 `ts_interface_shape.py`，由第 41 片的文档引用普查查后
  当场更正**（同一条误引在第 39 片审计文档里也已更正并留痕）。

- **v5.12 F-C6 第 38 片：服务写面与库层的形参对账（CTQ 的公差与条件从前录不进去）**：
  普查量具换成一根新的轴——`inspect.signature` 逐对比较 `AIPDStateDB` 与 `StateService`
  **两层同名**的 `add_*`（不截断，实测共享写入口共 4 个）。三处真缺口：
  库层 `add_fact` 收 `tolerance`/`conditions`/`version` 而服务面不收 ⇒
  多租户这条路上**录不进**公差与条件，而 CTQ 的语义正是「目标值 + 公差 + 条件」，
  第 18/20 片还拿它生成图纸公差——「Product Truth 可经多租户服务录入」这句只有一半是真的；
  `add_evidence` 不转 `accessed_at` ⇒ 「什么时候拿到的」静默变成「什么时候建的记录」
  （库里写 `accessed_at or ts`）；`add_risk` 不转 `trigger`（第 37 片刚接上 `owner`，差同一格）。
  顺手量到两处**不是**缺口并记档，免得下次再查：`add_deliverable` 的 `dtype` 与
  `update_deliverable` 白名单里的 `type` 只是形参名与列名不同；
  `id_sequences` 的播种名覆盖也不缺（`next_sequence` 走 UPSERT 自行建行）。

  补法与一把常驻尺子：三个方法补齐形参并按关键字转发（`actor` 仍在末位，向后兼容）；
  新增 `tests/test_service_write_surface_parity.py`（12 条）分两面钉——
  **行为面**每格给不同值、逐列断言落盘（`N1` 那种「签名收下却不转发」只有这面看得见）、
  **签名面**库层每个形参都要在服务面可见（`N2`/`N5` 那种「根本没这个形参」只有这面看得见），
  外加「对账面本身不许只覆盖我点名的那几个」——两层同名的写入口数量一变就红。
  每面还各自配了「抽掉转发 ⇒ 该列读回来是 NULL / 不等于那个值」的最小对照。

  读侧对称面同批查过：两层同名的读接口 5 个，库层能按的筛选项服务面**全都能按**
  （零缺口），于是把「零」钉成常驻断言（含「分母必须是 5」这条前提，防没有可比对象的
  空循环永远绿）。读数：全量 **2243 → 2255**（+12）；电池 `/tmp/slice38-mutations.py`
  **6 条：杀 6 / 存活 0 / 注入无效 0 / 崩溃式红 0**（第一条注入先做成「服务面新增一个
  只对库层不存在的方法」，结果存活——那不是漏，这条尺子的射程本来就是两层同名；
  换成「库层加新形参而服务面没跟上」才是真漂移形状）；`mypy src` 0 error、
  CI 口径 ruff rc=0。证据见 `docs/audit/SERVICE_WRITE_SURFACE_F-C6_2026-09-26.md`。
  调研豁免：沿用第 37 片刚确立的转发写法与既有 RPC 泛化派发，无新技术选型。

- **v5.12 F-C6 第 37 片：`owner` 能从服务写面进来了，并且 actor ≠ 责任人**：
  第 35 片把「服务/HTTP 写面不暴露 `owner`」标成需要产品裁决，重判之后它不是：
  **接收一个 owner 字段不需要身份源**，身份源只在「拿归属当放行依据」时才需要
  （那正是第 34 片决定 C 拒绝做的事）。改的是 `StateService.add_risk`：
  它原先收下 `actor` 用于授权与审计，却在往下调 `db.add_risk` 时把尾参整个丢掉
  ⇒ 第 34 片给库层加的 `owner` 谁都够不到。现在加 `owner: str | None = None` 并转发，
  审计 `after` 同时记 `owner` 与写它的 `actor`；RPC 是泛化派发
  （`service.call(method, **params)`），签名加了参数就自动可达，不必另开路由。
  **决定：不许把 `actor` 当 `owner` 转发**——前者是「谁在调用」，后者是「谁负责这条风险」，
  混起来等于用调用者身份替所有人认领，正是 v20/v21/v22 三格在清的同一类假归属。
  两处自抓：服务层夹具先用用户名直调被真授权拦下（`_authorize` 要的是注册过的 user id），
  「actor 不渗入 owner」那条第一次红也是夹具没注册用户——两次都修夹具，不放宽断言。
  读数：全量 **2238 → 2243**（+5，全在服务写面这一类）；
  电池 `/tmp/slice37-mutations.py` **4 条全杀**（actor 当 owner／收下不转发／
  审计不落 owner／签名退回旧形状）；`test_authorization.py` + `test_mcp_authorization.py`
  共 20 条 rc=0；`mypy src` 0 error、CI 口径 ruff rc=0。证据见
  `docs/audit/RISK_OWNER_SERVICE_SURFACE_F-C6_2026-09-26.md`。
  调研豁免：同族第 34-36 片已确立写法，且本片只补一个形参与一条转发。

- **v5.12 F-C6 第 36 片：给「拷贝重建的迁移会不会顺手改了别的列」装一把常驻尺子**：
  这一族的修复全靠拷贝重建（V1 冻结文本改不得、SQLite 没有 `ALTER COLUMN`），
  而重建最容易出的事故不是「没改成」，是**顺手动了别人**——列清单少一根、
  某一列的 `NOT NULL` 或默认值在搬运中掉掉。第 35 片写 v22 的 DDL 模板时，
  我先用「HEAD 实形 vs 当初声明它的那句迁移文本」对账，结果造出一条**假缺陷**
  （把 v9 有意把 `strength` 改成可空 REAL，读成「v6 重建掉了默认值」），
  过程与更正记在 `docs/audit/ACTOR_COLUMNS_NO_DEFAULT_F-C6_2026-09-25.md` §三.4。
  那趟排查里真正有用的轴是另一条：**把每一格迁移单独重放，比较它前后全表的列形状**。

  同一片里还接上了**第二根轴**：拷贝重建最容易漏带回来的，是别人留在同一张表上的
  具名索引/触发器。实测整条链今天一处都没有（21 格逐格前进式重放，
  「丢掉」与「改写定义」都为 0）⇒ 这条判据不需要白名单，只钉「不许丢、不许偷改」。

  新增 `tests/test_migration_rebuild_fidelity.py` 把这条轴变成常驻断言：
  链上除白名单声明过的 6 处（v9 两根评分列、v20 `gates.approved_by`、
  `v21 risks.owner`、v22 三根 actor 列）以外，**任何一格都不许改变或删掉已有列的形状**；
  新增列（建表与 `ADD COLUMN`）不在射程内——那是常态。白名单是双向对账的：
  多一处改动会红，声明过的那一处不再发生**也会红**（免得清单变成摆设）。

  这把尺子自己也交了两轮学费：
  ① 第一版的基线用「建到 HEAD 再 rollback 到 N-1」拿——rollback 会跑这一格的 down，
  而 down 用的正是同一份重建模板 ⇒ 基线被这一格自己刷过，比出「零变化」是自证不是实测；
  改成**前进式建库**（临时把 `runner.MIGRATIONS` 截到 N-1 再建）才有独立基线。
  ② 反向对照第一次打在「丢默认值」上，而这张表的默认值早被历史重建搬空了 ⇒ 空放；
  换成丢 `NOT NULL` 才真的开火。③ 电池 L1 的 target 先打在
  「其它格不许改形状」那条上——v22 本来就在声明清单里，那条按定义看不见它，
  于是记成「存活」；改打到逐格对账那条才杀掉。

  读数：全量 **2227 → 2238**（+11，其中索引轴 3 条）；索引轴自带一对最小对照（`DROP INDEX` 必须开火、只 `CREATE INDEX` 必须静默）；变异电池 `/tmp/slice36-mutations.py`
  **4 条：杀 4 / 存活 0 / 注入无效 0 / 崩溃式红 0**（每条带未注入对照臂；
  L1 首轮因锚点在老重建里命中 3 次被判「注入无效」而不是硬算杀掉，重锚到带
  `{actor_ddl}` 占位的那一处后生效）；`mypy src` 0 error、CI 口径 ruff rc=0。
  签出 attestation 与两道发布门的读数见 `docs/audit/MIGRATION_REBUILD_FIDELITY_F-C6_2026-09-25.md`。
  调研豁免：尺子只读仓库自己的迁移链，无外部选型空间。

- **v5.12 F-C6 第 35 片：三张表的 actor 列不再自带 `'system'`（把「漏传」从静默写戳改成报错）**：
  接着第 34 片 §五.1 留下的那一族。实测前提（去截断重跑 `grep -rn created_by`）：
  `claim_evidence_relations.created_by`、`product_definition_snapshots.created_by`、
  `product_definition_commits.actor` 三根列都是 `TEXT NOT NULL DEFAULT 'system'`，
  声明文本各两份（`migrations/definitions.py` 与重建用的 `migrations/helpers.py`），
  参考 SCHEMA 另有一处（`state/db.py`）。
  **但这一族与前两片不一样：没有一条正在跑的假读数**——产品写入口实测都显式传 actor
  （`idea/evidence_relations.py:217,247`、`product_intelligence/snapshot.py:345`、
  `product_intelligence/gate.py:491`、`execution/research_integration.py:265`），
  四个 `from_dict` 调用点喂的都是数据库行（列必然带着键）⇒ 默认值今天够不到。
  所以本片按「防将来」定性：危害是**下一个**漏传 actor 的写入口会静默写出 `'system'`，
  而 `to_dict`/`to_public_dict` 把这个戳当归属对外发。

  改法：migration **v22** `actor_columns_no_default` 重建这三张表——
  **保留 NOT NULL、只摘掉 DEFAULT**（不放开可空，否则连 fail-closed 一起丢）；
  漏传退化为 `IntegrityError` 而不是一个看起来像归属的字符串；
  两个方向都不改写历史值；数据类字段与 `from_dict` 兜底同步改为 `None`
  （`idea/evidence_relations.py`、`product_intelligence/snapshot.py`）。
  三张表实测都没有具名索引（只有 PK/UNIQUE 的隐式索引，随建表语句一起带走），
  重建不降级任何热查询。
  一处顺手钉住的方法：v22 的 DDL 模板照 **sqlite_master 的 HEAD 实形**抄，
  不照当初声明它的那句迁移文本抄——`claim_evidence_relations.strength` 从
  `REAL NOT NULL DEFAULT 0.5` 变成裸 `strength REAL` 是 **v9
  `nullable_scores_and_legacy_sequences` 有意的改动**（模型侧「None=未评分」，
  参考 SCHEMA `state/db.py:294` 早已跟着改），照 v4 的声明抄等于把一条有意的
  形状改动倒回去。第一版登记里这句话被写成「v6 的重建掉了默认值的既存漂移」，
  那是我自己的对账量具拿「首次声明」当真值造出来的**假缺陷**，已复核更正并记入
  审计文档 §三.4；换成对单格迁移做隔离重放之后实测：
  v20/v21/v22 各自只动了宣称要改的那几列，行数不变。

  常驻用例 **22 条**（`tests/test_actor_columns_no_default.py`）：形状两半分开钉
  （默认值没了 *并且* NOT NULL 还在）、三张表逐张参数化、
  漏传必须 `IntegrityError` / 带 actor 必须照常往返（合规侧）、
  up 保历史值、down 还原默认值、逐列值往返保真、
  数据类默认值与 `from_dict`/`to_dict` 三处都不许再编造 `'system'`、
  参考 SCHEMA 与 V1/声明文本各钉一侧。
  顺带把第 34 片那条文档镜像对照改成由链尾现算（写死 v21 的对照在加进 v22 后当场假红）。
  读侧普查留档：全仓没有任何一处按 `created_by`/`actor` 做过滤或判定，
  读者只有「序列化往外发」这一类。

  读数：全量 **2205 → 2227**（+22）；签出 attestation（HEAD 干净签出 +
  `AIPD_SOURCE_COMMIT=<tag SHA>`）**0 failed**；`production_release_gate --release-ready
  --tag v5.6.0` 带 venv PATH 后 **8/8 rc=0**；`audit_repo --strict` 仍只剩那一条
  按既有裁决永远红的 tag 锚点判定；`mypy src` 0 error、CI 口径 ruff rc=0。
  变异电池 `/tmp/slice35-mutations.py` **12 条：杀 12 / 存活 0 / 注入无效 0 / 崩溃式红 0 /
  已知无撤回案例 3**；同树复跑第 34 片 **15/15**、第 32 片 **14/14**、第 30/31/33 片
  **21/21、8/8、9 杀+2 已知**。调研按「影响范围明确的局部改动」豁免：
  沿用本片前三片已确立的重建配方，无新技术选型空间。证据见
  `docs/audit/ACTOR_COLUMNS_NO_DEFAULT_F-C6_2026-09-25.md`。

- **v5.12 F-C6 第 34 片：`risks.owner` 不再硬写 `'AI'`，并给这根列补上第一个真读者**：
  同第 32 片那一族的另一半，但更糟一层。列形状是 `owner TEXT NOT NULL DEFAULT 'AI'`
  （`state/migrations/schema.py:148` 冻结文本、`state/db.py:197` 参考 SCHEMA、
  `scripts/aipd_store.py:114` 废弃旧库），而写入口 `AIPDStateDB.add_risk`
  （`state/db.py:975`）**连 `owner` 形参都没有**、INSERT 里直接硬写 `"AI"` ⇒
  「这条风险谁负责」在创建时无法表达，库里每一条都是 AI 负责；偏偏
  `update_risk` 的可改白名单里**有** `owner`（`state/db.py:1001`）：创建时不许说、
  创建后允许改。第 32 片的读侧普查在这里给出更空的结论——`list_risks` 的四个调用点
  （`experience/owner_dashboard.py`、`project_summary.py`、`views.py`、`state/checkpoint.py`）
  **一个都不碰这一列**：一直在写、从来没人读、而且写的是假话。

  改法三件：migration **v21** `risks_owner_no_default` 重建 `risks`（列可空、无默认值、
  历史值原样保留，V1 冻结文本改不得所以只能以重建落地，与 v20 同一处置；
  down 方向 NULL 落**空串**而不落 `'AI'`，降级不许凭空指派负责人）；
  写入口加 `owner: str | None = None`（空白串 `ValueError`、给了值 trim）；
  读侧把 `actors.py` 那份机器身份词表通用化成 `summarize_actor_column`，
  并给这根列补上第一个真读者——Owner Dashboard 的「风险责任」块：正文（完整档与紧凑档）
  只给人话与计数，风险编号留在 `<details>` 折叠区与 `--json` 里，
  与既有契约 `test_owner_ux.py::test_dashboard_default_hides_internals` 同一口径。

  三处被实测/电池教的地方：①「老库升到 HEAD 后与新建库同形」是**相对**断言，
  把 v21 的 up 撤掉时两边一起变、永远不红——每处相对断言都得配一条对着权威事实的
  绝对断言（新库里这一列没有默认值），否则等于没闸；②电池 J15 第一轮被记成「杀掉」，
  实际 rc=4：用例挂错了类、node id 根本没被收集 ⇒ 电池从此加**未注入对照臂**，
  并把退出码分档（rc=1 才算断言红，rc≥2 记「崩溃式红/挂错目标」且脚本非零退出）；
  ③新加的 Dashboard 块一开始只进了 `--json`，两档文本渲染都没落地——
  是「在视图 dict 里加了个键」被当成了「有读者」。补的两条常驻判据：
  逐列值往返保真（少一列时 `INSERT INTO new(cols) SELECT` 照样成功、值静默变 NULL）、
  空账本不许写成「都有真人认领」（对空集下断言）。

  读数：全量用例 **2182 → 2205**（+23，全在 `tests/test_risk_ownership.py`）；
  签出 attestation（`git worktree` 的 HEAD 干净签出 + `AIPD_SOURCE_COMMIT=<tag SHA>`）
  **2202 passed / 0 failed / 3 skipped**，同一份报告绑进 `PROVENANCE.test_report`；
  第一跑只红在 `test_batched_transaction_outranks_per_statement_writes` 那格 5× 比值门
  （与并发 agent 抢 CPU，同条单跑 0.29s 过）⇒ 整跑重放，不放宽比值门也不把红绑进证据。
  `production_release_gate --release-ready --tag v5.6.0` 带 venv PATH 后 **8/8 rc=0**
  （默认 PATH 下 `no_unacknowledged_cve` fail-closed 假红，是环境缺位不是代码回归）；
  `audit_repo --strict` 仍只剩那一条按既有裁决永远红的 tag 锚点判定，两份清单
  `hash_mismatch_count = 0`；`mypy src` 0 error、CI 口径 ruff（`src tests state_service`）rc=0。
  变异电池 `/tmp/slice34-mutations.py` **15 条：杀 15 / 存活 0 / 注入无效 0 / 崩溃式红 0 /
  已知无撤回案例 2**；同树复跑第 32 片 **14/14**（其 I4 锚点因本片给 `add_risk` 加了同形守卫
  而命中 2 次，重锚到 `approved_by` 那句报错文案）、第 30 片 **21/21**、
  第 31 片 **8/8**、第 33 片 **9 杀 / 0 存活 / 2 已知无撤回**。证据见
  `docs/audit/RISK_OWNER_READERS_F-C6_2026-09-25.md`。

- **v5.12 F-C6 第 33 片：把「门没人跑」这一族闭掉，并给自检补合规侧**：
  `references/end-to-end-closure-model.md:10` 把 `scripts/e2e_acceptance.py` 写成
  「数字全链路已打通」的**唯一**判据（`references/local-cad-fallback.md:25` 第 8 步要求跑它，
  `scripts/runtime_preflight.py:46` 也明写 preflight 不宣布闭环、闭环要它），
  而第 31 片登记过的事实是：**全仓没有任何 CI 或用例调用** `e2e_acceptance.py`、
  `selftest_quality.py`、`selftest_v4.py`（去掉 `| head` 截断重跑 `grep -rn` 才敢说这句）。
  另一处更阴的：旧 `selftest_quality.py` 两条判据**都只断言子进程 `rc != 0`**，
  一支合规侧对照都没有 ⇒ 把 `outcome_acceptance.py` 或 `cad_maturity_gate.py` 改成
  「任何输入都退 1」，这份自检照样绿。第三条是文案越界：`outcome_acceptance.py` 走
  `schema_binding.validate_artifact_file` 报 `missing` 时那句
  `["标了交付，但文件不在"]`，对**空目录**也照样回同一句（实测）——那个函数拿不到交付清单，
  「标了交付」是它无从知道的前提。

  改法：`scripts/selftest_quality.py` 重写成**四支两两对照**
  （A1 只有产物 ⇒ communication 不放行，且断言落在 `communication_accepted=false` 这一格；
  A2 全链路 + 验收字段达标 ⇒ 放行，这是 A1 的开火前提；B1 `faceted_brep` 达不到 C7；
  B2 `native_brep` 填满 C0..C7 要求项 ⇒ C7 放行，这是 B1 的开火前提），
  少跑到任何一支都退 7（不是退 0），证据字典改为 `importlib` 取 `REQUIREMENTS` 而不是
  `runpy.run_path` 执行脚本顶页；新增 `tests/test_gate_runners.py` 把三件事变成常驻断言：
  ①**普查**——每台门都要有「spawn 形态」的真读者（`subprocess.run/call/check_call/Popen`），
  只被文本提到不算跑过，普查面只排除脚本自身；②包装器的四个行为（绿档 rc=0、
  撤一样东西⇒rc=5、`--require-full` 映射 `production`、`--json-out` 真落盘）；
  ③三台自检/门脚本子进程真跑（`selftest_v4.py` 也在内）。
  `validate_artifact_file` 的 `missing` 只说「文件不在盘上」，
  「该项已标 complete」由**知道交付清单**的 `scripts/quality_gate.py` 自己补上。

  读数：全量 **2170 → 2182**（+12，全在新用例）；今天真跑的三台门状态是
  `e2e_acceptance` 在完整数字链上 rc=0/`classification=communication_accepted`、
  撤掉验收分数后 rc=5、`--require-full` rc=5，`selftest_quality.py` 四支全绿 rc=0，
  `selftest_v4.py` rc=0。变异电池 `/tmp/slice33-mutations.py` **11 条：杀 9 / 存活 0 /
  注入无效 0 / 已知无撤回案例 2**（J8「字段照读但不参与判定」、J11「普查判据放宽成提到过名字」
  ——这两条只有在真读者消失时才观测得到，而真读者就是本用例，删它不等于证明判据有牙；
  写进 KNOWN_SURVIVORS 而不是假装杀得动）。CI 不必改：这三台门现在经**常驻用例**在 CI 里跑。
  ruff（CI 范围）全过，mypy `Success: no issues found in 425 source files`。证据见
  `docs/audit/GATE_RUNNERS_WIRED_F-C6_2026-09-25.md`。

  **没做**：`selftest_quality.py` 的 `len(results) != 4 → rc=7` 只护住「少跑」，
  护不住「少判」（见 J8）；`outcome_acceptance.py` 仍是 1 空格压缩风格的老脚本，
  本轮只改它消费的那句话，没顺手重排。

- **v5.12 F-C6 第 32 片：`gates.approved_by` 不再自带 `'AI-internal'`（没人批不许读成 AI 批了）**：
  第 26 片建 ECO 三张表时，本仓已经把这条写成反面教材（`change_orders/eco.py` 的规矩 1：
  「本仓 `gates.approved_by` 的默认值是 `'AI-internal'`，照抄那个形状就等于任何写入点
  不写审批人也算已批准」），但 **`gates` 这张表本身一直没改**。实测到的形状：
  ① 同一句 DDL 有三份拷贝（`state/migrations/schema.py:173` 的 V1 冻结文本、
  `state/db.py:222` 的参考 SCHEMA、`scripts/aipd_store.py:135` 的废弃旧库）；
  ② 写入口 `AIPDStateDB.add_gate`（`state/db.py:1025`）的形参默认值同样是
  `"AI-internal"` ⇒ 不写审批人=写了一个审批人；③ **常驻用例自己就是受害者**：
  `tests/test_golden_projects_e2e.py:262,440` 两处都没传审批人，过去一直在往权威表里
  写 `'AI-internal'`。全仓仅有的两个生产写入口（`supply_chain/writeback.py:129,154`）
  显式盖 `supply-chain`，而这词**不在**机器身份表里 ⇒ 只复用 ECO 那张表读数，
  这两行会被读成「真人批的」。

  改法：migration **v20** 重建 `gates`，`approved_by` 改成可空、无默认值；
  写入口默认 `None` ⇒ 落 NULL，给了值就必须非空（空白串 `ValueError`，不许拿空格冒充署名）；
  历史值**原样保留**（up 不改写任何一行）；机器身份词表从 `eco.py` 搬到叶子模块
  `src/aipd_os/actors.py`（两处读者共用一份，`"supply-chain"` 补进去），ECO 的
  `_is_human` 删掉、改调 `is_human_actor`；读侧新增 `src/aipd_os/gate_attribution.py`，
  三态 `human / non_human / unattributed`（读不到这一列 = unattributed，不折成任何一态），
  `scripts/quality_gate.py` 输出多一段 `gate_approval_attribution`，**只报不判**。

  这一片被实测更正的四处（原计划是照旧登记写的）：写入口叫 `add_gate` 不是 `record_gate`
  （后者是 `product_intelligence/gate.py` 的另一台机器，注释明写「不写 gates 表」）；
  `schema.py:173` 在 `V1_INITIAL_SCHEMA` 里、被 `V1_FROZEN_SHA256` 与
  `test_migration_freeze.py` 钉住 ⇒ **不能改**，「同步改两处 DDL」这条只成立一半；
  还有第三份 DDL（废弃旧库）与两个 v4→v5 搬运脚本（`migrations/v4_to_v5.py:201`、
  `rollback_v5.py:132`）是首轮 `| head -30` 的 grep 漏掉的，重跑不加截断才看见 ——
  它们**只搬不造**（原样带 `g["approved_by"]`），已补一条常驻断言把这句话钉住；
  降级方向上 NULL 无法在 v19 的 `NOT NULL` 列里表达，落**空串**而不是 `'AI-internal'`，
  否则一次回滚就凭空造出一批「AI 批过」的台账。

  常驻用例 **31 条**（`tests/test_gate_attribution.py`）+ `tests/test_migration.py`
  里那条搬运工断言；全量 **2139 → 2170**。变异电池 `/tmp/slice32-mutations.py`
  **14 条：杀 14 / 活 0 / 注入无效 0**（含「默认值留在 DDL 里」「签名干净但落盘补戳」
  「词表漏掉在产的戳」「up 改写历史」「down 不还原 / down 造批准」「门把归属当判决」），
  同树复跑第 31 片 **8/8**、第 30 片 **21/21**。ruff（CI 范围）全过，
  mypy `Success: no issues found in 424 source files`。证据见
  `docs/audit/GATE_APPROVED_BY_F-C6_2026-09-25.md`。

  **没做（登记为待裁）**：这段归属要不要进发布门（现在只报不判；进了就是收紧共享门禁）；
  「这个 actor 真是某个人」没有身份源，`owner` 这类角色占位符仍算 human。
  同批仍开着的：那 9 项 CAD 阶梯交付物无产者、`experience/` 三份 G 名表漂 5 格、
  `interfaces` 的 verdict 进不进发布门。

- **v5.12 F-C6 第 31 片：G 表只许有一个来源（声明 50 项、门只要求 40 项）**：
  `scripts/quality_gate.py` 的注释写着「requirements mirror `gate_requirements.yaml`」，
  实测是假的——YAML 声明 **50** 个交付物类型、脚本内联 `REQ` 只强制 **40** 个，
  漂移单边（没有「门要求但没声明」的），缺的 10 项全在 CAD 阶梯上
  （`cad_contract` `cad_primary_step` `cad_inspection_report` `cad_bom_mapping`
  `cad_l1_functional_layout` `cad_l4_dfm_drawings` `cad_l5_release_package`
  `cad_parametric_source` `cad_snapshot_packet` `evt_cad_configuration`）；
  而**全仓没有任何解析器读过那份 YAML**——它的名字只出现在那句注释里。
  `requires_owner_approval` 那一轴两份一直一致 ⇒ 漂的只有交付物轴，如实分开记。
  改法：新增 `src/aipd_os/gate_requirements.py`，用 `yaml.safe_load` 把声明文件读成唯一权威
  （`pyyaml` 是核心依赖 ⇒ 零新依赖；没有为此再引入声明文件的 schema 化工具），
  `REQ`/`OWNER` 全部派生，脚本里不再出现内联 `'G3': [...]`（常驻用例用正则钉）；
  **每次运行现读**而不是 import 期缓存，YAML 缺失/解析坏/顶层不是映射 ⇒ 门打
  `unreadable` 并退 3，**不给** `pass=false` 这类可被误读的判决，也不退回旧副本。
  今天升进强制集的是 `cad_contract`（有 schema、有模板、`production_release_gate` 的
  `schema_valid` 真在核它，不是名字像就收）；它同时因为「有同名契约」进了第 30 片那侧的
  形状门。剩下 9 项**逐项具名**在 `UNPRODUCED` 里并写理由：本仓没有产这些类型的代码，
  硬接进门只会把 G3-G8 变成永久红灯（那只会训练人忽略门）。常驻用例钉
  `声明 − 强制 == UNPRODUCED` 且等于那 9 个名字，另两条钉住自动行为：
  加一项声明 ⇒ 立刻成要求；从豁免里删一项 ⇒ 立刻升进强制集。
  端到端（真子进程，G3）：缺 ⇒ `pass=false missing=['cad_contract']`；
  补齐 ⇒ `pass=true`（must-not-fire 的一侧，否则「收紧」只是多报）；
  标完成却不填 path ⇒ 单独一条 `('cad_contract','path_missing')`。
  **本片自己也被抓住一次自引用**：判「九项没有产者」的字面量探针第一版把
  `gate_requirements.py` 自己也当被扫文本——九个名字就写在那份豁免表里，
  于是九个负向读数全被点亮成假阴性；修法是排除本模块 + 名单改从声明文件现取 +
  正向对照常驻（`project_brief`、`cad_contract` 必须探得到）。同时删掉一条
  **永不为真**的 `unclassified()`：`enforced_table()` 丢的就是 `UNPRODUCED`，
  那一格恒空，留着只会让人以为有闸。登记未做：`experience/` 里三份 `G0-G9 中文名`
  已漂 5 格（短标签 vs 长描述，统一方向是属主裁决）；`selftest_quality.py`、
  `e2e_acceptance.py`、`selftest_v4.py` 今天仍无人调用。
  全量 2121 → **2139** 条。证据见 `docs/audit/GATE_REQUIREMENTS_TABLE_F-C6_2026-09-25.md`。

- **v5.12 F-C6 第 30 片：契约绑定判据修正 + 把形状校验接到产物落点**：这一片起于**第 29 片
  自己的一条假阳性**。那片的 `scan_consumers` 按**文件名字面量**反查消费者，报「三份 schema 没人
  引用 ⇒ 没人校验的契约」；而 `src/aipd_os/scripts/schema_check.py` 其实按**命名约定**
  （`stem.removesuffix('.schema')` + `DATA_DIRS`）绑实例并真跑 `jsonschema.validate`，
  还挂在 `.github/workflows/ci.yml:45,58` 的 `schema-validation` job 上——那句文件名在它的代码里
  一个字都没出现，按名字反查必然读不到。现算：五份 schema 里 **4 份有人按约定校验**，只有
  `fact.schema.json` 落 `INFO …（跳过数据校验）` ⇒ 孤儿 3 → 1，理由换成「没有实例被按它校验过」。
  **同一次核对翻出两条比那条假阳性重的**：
  ① `project_checkpoint.schema.json` 的 `$defs.fact` 是 `fact.schema.json` 的**内联副本**且已漂移到
  互相矛盾——副本的 `status.enum` **缺 `U`**，而权威 `src/aipd_os/state/db.py:48 FACT_STATUSES` 含 `U`
  （`research/models.py:38`、`idea/evidence_graph.py:188`、
  `product_intelligence/gate_criteria.py:145,372` 都在产 `U`）⇒ 含一条 `U` 事实的真实 checkpoint
  **在本仓自己的契约下非法**。修法是把形状**单源化**：`$defs.fact` 换成
  `allOf: [$ref → fact.schema.json]` 并在 checkpoint 侧**保留**自己多出来的 `fact_id` 要求。
  三档判据对同一份重建文档实测：内联档拦 `U`；裸 `$ref` 档放 `U` 但**丢掉** `fact_id`（这一档就是
  "单源化顺手放宽"的样子）；采用档收 `U`、保住 `fact_id`、并继承 `key.minLength`。今天真语料
  **0 条** fact 文档 ⇒ **0 处翻转**，登记里明写「无差」而**不是**「等价」，必开火对照交给合成实例。
  ② **落点只判存在**：`scripts/outcome_acceptance.py:22` 的 `exists()` 只要求 `size>0`，
  `quality_gate.py` 的 G9 只看 deliverable **类型**在不在。旧码签出实测：形状坏掉的 checkpoint 与
  **文件根本不存在的** checkpoint，旧门都返回 `pass=true`。现在两处都按同名词干的契约核形状，
  五态分开（`valid` / `invalid` / `unreadable` / `no_schema` / `missing`，外加 `path_missing`），
  **都不折成通过**；G9 加 `--root` 让 `deliverables.path` 有相对根，哪些类型该核由
  `REQ` 的类型名 ∩ 盘上契约**现算**（今天 40 类里只有 1 类有契约 ⇒ 爆炸半径就是 1）。
  判据收成**新模块 `src/aipd_os/schema_binding.py`**：绑定目录与权威枚举都用 AST 从真出处现抽
  （抄常量=第二个会漂移的镜像；抽不到单列 `binding_blind` / `authority_readable=False`，
  盲区既不折成"有绑定"也不折成"一致"）；跨文件 `$ref` 用 `referencing` 0.36.2 解析
  （`jsonschema` 4.25.1 自带，零新依赖；`RefResolver` 自 4.18 弃用，实测本机警告，不用）。
  `schema_check` 从今天起把「没有实例被按它校验」报成 **UNBOUND 并计失败**（旧行为 INFO 后 rc=0），
  要留空白必须进 `UNBOUND_EXEMPT` **具名写理由**；元校验改按各文件自己声明的方言——现役五份
  两档都 ok（今天 0 处翻红），但**不等价**：`prefixItems`/`unevaluatedProperties` 两类缺陷只有
  新方言抓得到，两条都进了常驻用例。`schema_check.py` 的 `DATA_DIRS` 是绑定约定的**唯一权威**，
  清单侧从这里现抽。**量具不进自己的分母**（三个面都被实测咬过）：`PROVES` 文案里写了
  `aipd_os.net.http` ⇒ 模块自己被数成出网消费者；补一条断言之后**分母从 11 涨到 12**（用例正文
  也算一次引用）；同一文件点了某张契约的名字 ⇒ 那张契约被算成"已被消费方取证"。三者统一由
  `INSTRUMENT_FILES` 排除，并配一条"表里每个路径必须真在盘上、且正好是模块+它的用例"的用例防改名。
  **清单判定新增三轴并拆成 `verdict_of()` 逐轴钉**：`contracts_without_instance` /
  `binding_blind` / `landing_existence_only`（再加形状 `divergent`/`blind`）。拆逐轴的原因写进文档：
  前两版判定是 `build()` 里一长串 `or`，电池把「删掉其中一格」的两条注入**放过去了**
  （别的轴本来就脏，整体断 `incomplete` 永远绿）。顺手闭掉 `command_contract.py` 那句停在
  「当前为 29」的过期注释——改成说明**为什么不写死数字**。
  验证：全量 2074 → **2121** 条（`2118 passed / 0 failed / 3 skipped`，提交后的树上跑）；
  ruff 全绿；mypy 419 files 无问题；本片电池 **21 条全杀**，同树复跑第 29 片 **12/12**
  （其 C6 锚因判定改形重指）、第 27 片 **17/17**、第 28 片 **15/15**；C6 普查 15/0/0 且
  `--self-test` 7/7；发布门 8/8 绿。证据见
  `docs/audit/CONTRACT_BINDING_F-C6_2026-09-25.md`。

- **v5.12 F-C6 第 29 片：接口清单与契约证据（C6 最后一格零实现，只闭可自查的那一半）**：
  「ICD」这一项从第 26 片起一直挂 absent，note 早写好该做什么：**可自查的那一半**
  （接口清单、数据形状、每个接口的定义件版本 + sha256、逐接口用例证据），
  而且**不叫 ICD**——NASA 附录 L 的 §1.3「责任与变更授权」与 §3.1.2「接口职责」只能由对侧给，
  本仓单方产一份叫 ICD 的文件等于伪造签署。落点 `src/aipd_os/interface_contract.py` +
  公开命令 `aipd interfaces`（55 → 56 个），kind=`aipd.interface_contract.v1` + 同名侧车
  （拼法仍走 `cad/evidence.sidecar_path` 那唯一一处）。今天真跑 **85 条接口**：
  CLI 56、MCP 工具 6、JSON Schema 5、文件格式契约 5、HTTP 提供面 2、出网消费者 11。
  三条形状规矩：**① 分母一律重算**（`PUBLIC_COMMANDS`、`mcp_server.py` 的 `def mcp_*` AST、
  `assets/schemas/` 目录实况、`aipd_os.net.http` 的 import 反查）——抄计数会在改名那天静默漏项；
  **② 「被引用」不等于「被验证」**：`verified_by` 要 AST 解析到「文件在 + 符号在 + 真收得到 test」，
  自制解析另配一条与 `pytest --collect-only` 真读数对齐的复核用例 + must-not-fire 一侧
  （真被引用的 `cad_contract.schema.json` 不许一起躺进孤儿清单，否则反查坏掉时孤儿栏整栏膨胀）；
  **③ 判定三态**：定义件不在盘上 ⇒ 与 `--strict` 无关必退 4；有孤儿契约/未取证行 ⇒ incomplete，
  默认只写进文档、`--strict` 才拦；不把今天的 3 个孤儿做成永久红门（那只会训练人忽略门）。
  **清单读出来的事实**（本片只登记不顺手修）：`project_checkpoint.schema.json` 的处境最坏——
  `quality_gate.py:33` 的 G9 要求那个交付物**在**、`outcome_acceptance.py:22` 只 `exists(...)`，
  即**存在性有门、内容不合形没人管**；`manual_chain_state` 与 `supervisor_project` 在
  `src/`、`scripts/`、`tests/`、`state_service/` 里连名字都没出现。
  选型只引真打开过的页面（2026-09-25）：Pact（Apache-2.0，契约由消费者测试生成、
  验证=对 provider 公布过的结果）借「两侧点名 + 未验证≠已验证」；OpenAPI v3.2.1（Apache-2.0，
  自述只描述接口、不断言服务端实现）借那句边界；check-jsonschema（页面标 NOASSERTION 且无机器
  可读报告）不引入。⇒ 本地实现、零新依赖。

  > **收口更正（同日，全部现算）**：上面那句「`manual_chain_state` 与 `supervisor_project`
  > 连名字都没出现」是真的，但由它推「没人校验」是**错的**——
  > `src/aipd_os/scripts/schema_check.py` 按**命名约定**
  > （`stem.removesuffix('.schema')` + `DATA_DIRS=('templates','assets/templates')`）
  > 绑实例并真跑 `jsonschema.validate`，而且挂在 `.github/workflows/ci.yml:45,58` 的 job 上；
  > 实测五份 schema 里 **4 份有约定绑定的实例并被校验**，只有 `fact.schema.json` 落
  > `INFO …（跳过数据校验）` ⇒ 孤儿 **3 份 → 1 份**，理由换成「没有实例被按它校验过」。
  > 同一次核对翻出更重的一条：`project_checkpoint.schema.json` 的**内联** `$defs.fact`
  > 的 `status.enum` 缺 `U`，而权威枚举 `src/aipd_os/state/db.py:48 FACT_STATUSES` 含 `U`
  > （`research/models.py:38`、`idea/evidence_graph.py:188`、
  > `product_intelligence/gate_criteria.py:145,372` 都在按 `U` 判定）⇒ 含一条 `U` 事实的
  > 真实 checkpoint 在本仓自己的契约下非法。两处闭在第 30 片。
  > 另有两处量具自引用：提交后重跑 `aipd interfaces` 得 **86 条 / 出网消费者 12**（不是这里的
  > 85 / 11），多的那 1 条正是 `interface_contract.py` **自己**——它 `PROVES` 文案里写了
  > `aipd_os.net.http`，而排除条件只有 `endswith("net/http.py")`；12 条里还有 3 条是 `tests/…`，
  > 与 9 条生产模块混在同一个 kind 里数。
  > **本片还有一次命令面漏提交**：`3ab466a` 少带了 `commands.py` 的 `COMMAND_FUNCS` 注册行，
  > 而同一提交的 `main.py:385` 要读它 ⇒ 在 `3ab466a` 的干净签出里 `build_parser()` 直接
  > `KeyError: 'interfaces'`，三个 CLI 用例文件 **28 failed / 25 passed**。之前那次全量绿是
  > 在带修复的工作树上跑的。修向前进 `3d096c4`；收口读数因此一律改从 HEAD 的签出取。

  18 条常驻用例 + 变异电池 **12 条：杀 12 / 活 0 / 注入无效 0**。
  顺手立住一件副产品：普查那把尺子自己的注入 `_an_absent_item()` 会因「今天的仓恰好没有 absent 项」
  而 StopIteration——改成**没有就当场造一个**，否则反证静默失去可红性；
  档位棘轮 14/0/1 → **15/0/0**（升的是可自查的一半，与「装配/维护只升装配那一半」同形状）。
  全量用例数 2056 → 2074（+18）；公开命令面 55 → 56。
  证据见 `docs/audit/INTERFACE_CONTRACT_F-C6_2026-09-25.md`。

- **v5.12 F-C6-ECO 第 28 片：上一版交付物清单当基线（把「没单提到」拆成两种结论）**：
  第 27 片留下的半句是「只证明内容与某张闭合单一致，不证明自上次发布以来只改了这些」。
  之所以证不了，是因为**两种完全不同的事实在字节层面同形**：这条交付物「没动过」（本来就不需要单）
  与「动了没提单」（最该拦的那种）——手里没有「上一版」时，任何一侧的断言都是编的。
  新增 `src/aipd_os/delivery_baseline.py`：`--write-baseline` 把**本次交出去的带哈希交付物**
  落成 `aipd.delivery_baseline.v1`，下一版 `--baseline` 指回它，于是那一栏一分为三——
  `unchanged_since_baseline`（基线证明语义未变 ⇒ **不需要单**，实测零张单也能 `coverage=complete`）、
  `since_baseline.added/modified`（没闭合单即**阻断**）、
  `removed`（基线有而这版没交 ⇒ 必须有一张 `VERIFIED` 的 `REMOVE` 行认领，
  否则 `eco_deliverable_removed_uncovered` 阻断；这一支单独存在是因为**它不在 uncovered 里**——
  文件已经不交了，按「交付物逐条核」根本看不见它，只有跟上一版比才看得见）。
  比对用**语义摘要**而不是原始哈希：本仓实测同一份金样品重跑 DFM，报告体字节确定、
  **侧车不确定**（带 `generated_at`，重跑后 `6fa5b891…`），按原始字节比会把「又跑了一遍」
  凭空读成一次工程变更。易变字段是**按整名的白名单**（四个时间类键 `VOLATILE_FIELDS`），
  不是 ignore 列表——能吞任意键的列表就是关掉判据的开关；两侧都有常驻用例（只换时间戳 ⇒ 摘要不变、
  改一条真结论 ⇒ 必须变、`created` 这种没声明过的近似名 ⇒ 一律算内容），剔掉的位置逐条写进
  `volatile_dropped`，非 JSON 交付物（Markdown/STEP/DXF）**不省任何东西**。
  三条 fail-closed 取向：基线文件读坏 ⇒ `eco_baseline_unreadable` 阻断，**不**退回「没有基线」
  （否则删掉基线就是关掉差集的手段）；证据还有阻断项时 `--write-baseline` **拒绝且不留文件**（退 2），
  要落盘必须 `--acknowledge-not-ready` 写理由，落下来的文件里留着 `release_ready: false`
  ——「没人放行过的一次运行」不该变成下一版的比对基准；门那一侧把未认领下线读成**不通过**。
  刻意**不**做两件事：① 没有基线时不新增要求（门维持第 27 片判据，只在 detail 写明
  「无基线 ⇒ 不声称只改了这些」）；② **整仓范围的差集不做**——现算过：tag 上的
  `SOURCE_MANIFEST`（520 条）与今天的（612 条）差 **101 增 / 9 删 / 82 改**，而 v19 之后
  一张单都没有，接成硬门唯一的变绿办法是补写一百多张事后变更单，那是造证据。
  选型只引**真打开过**的两页（2026-09-25 实读）：SLSA provenance 把「构建期需要的既有制品」
  （`resolvedDependencies`，每条 name + 摘要表）与产物 `subject` 分两栏 ⇒ 借两栏形状；
  Apache Maven `artifact:compare` 把 `<ignore>` 做成一等参数、`<fail>` 默认 true ⇒
  借「每次必变的东西要显式声明」与「差集默认拦」两条判断，**不引依赖**。
  28 条常驻用例（新模块 11 + 判据 15 + 门 2）+ 变异电池 **15 条：杀 15 / 活 0 / 注入无效 0**。
  电池第一轮放走了一条：B8（把下线认领放宽成「单里提过就行」）全绿——原判据用例只测了
  「有 REMOVE 单 ⇒ 放行」与「什么都没提 ⇒ 拦」，**没测「提过但不是 REMOVE／不是 VERIFIED」**；
  补 `test_only_a_verified_removal_endorses_a_vanished_delivery` 之后 B8 与新加的 B15 一起开火。
  端到端真命令行走完六步（拒绝落盘 → 承认后才落 → 读回全没改 → 重跑一次仍算没改 →
  真改一行就拦 → 补一张单放行），逐字见审计文档 §六。
  全量用例数 2028 → 2056；被哈希面 612 → 614。
  收口读数：两轮全量各 `2053 passed / 0 failed / 3 skipped`（第二轮带 `AIPD_SOURCE_COMMIT=tag`，
  进 `PROVENANCE`）；被哈希面 612 → 614；`production_release_gate --release-ready --tag` 8/8 绿；
  `audit_repo --strict` 仍只有「锚点停在 tag」那条既有红。
  另记一条**电池会腐**：同树复跑第 27 片的 17 条得 15 杀 + 2 条「注入无效」——本片改 `_collect_eco`
  把 E3/E4 的锚改掉了形状（判据与用例都还在，是注入打不进去），重指锚点后回到 17/17。
  规矩：改形一条判据就复跑上一片的电池，否则登记里的「N 条全杀」会变成没人能复现的历史数字。
  证据见 `docs/audit/ECO_DELIVERY_BASELINE_F-C6-ECO_2026-09-25.md`。

- **v5.12 F-C6-ECO 第 27 片：发布证据读 ECO——带哈希的交付物必须有**闭合**变更单覆盖**：
  第 26 片收尾写着「发布门没有『manifest 哈希有差却没有一笔闭合 ECO』这条 fail-closed 判据
  （下一片）」，这片把它接上。`_hashed_artifacts()` 递归走整份证据文档，凡同时带 `path` 与
  `sha256` 的节点都算一条交付物（先 `\`→`/` 再 `posixpath.normpath`，`./x//y.md` 与 `x/y.md`
  认成同一个）——**不硬编码**「报告 + 侧车」那两条：判据读的东西必须由文档自己声明，
  否则明天多一类产物就悄悄落在闸外。对每条四处置，**刻意不合成一个百分比**：
  `covered`（某张 `VERIFIED` 单的那行 `after_sha256` 与实际哈希一致）／
  `eco_change_uncovered`（阻断：有单提到但没有一张**有效**单对得上——被否的、被替代的、
  还没批的都不背书，哈希恰好对上只说明「当初有人这么想过」）／
  `eco_change_unverified`（阻断：对得上但单还活着没走到 `VERIFIED`，**批了不等于复验了**，
  `open_orders` 点名到 eco_id 与现状态）／`undetermined`（**不**阻断，只交清单：本仓没有
  上一版基线可比，判合格是假绿，判违规是把「没登记」当成「改了没提单」）。`coverage` 三档
  `complete`/`partial`/`incomplete`：有单却没全覆盖只敢说 partial。分档写成
  `VERIFICATION_PENDING`/`DEAD_STATUSES` 两个常量，并由
  `TestTheEndorsementBucketsAreExhaustive` 钉住**四桶互不相交且并起来 == `ECO_STATUSES`**
  ⇒ 以后加一档状态不归类即判红。
  **门那一侧读的是同一格，但口径刻意不同**：`production_release_gate` 新增
  `change_control_closes_deliverables`（C6），把「一张单都没有」的盲区读成**不通过**——
  生产者的 rc 管「这份证据有没有说错话」，门管「这句话够不够格用来签字」。
  收紧代价是**现算**的：这道门本就「任何一档判据失败即整体 rc=2，不看 `--target`」
  （`production_release_gate.py:751-753`），所以 3 个夹具文件 4 处清单补齐 + 全量首跑 4 条红
  （2 条属预期：产物清单还没重锚）。`aipd release manifest` 的人读输出多一行 `eco 覆盖=…`。
  端到端真命令行走完**红→绿→红→绿**六步（§六逐字）：零单 ⇒ `undetermined`；单里哈希写错 ⇒
  逐条点名 `uncovered` 且 `covered=1` 同时成立（判据看的是这条内容的这个哈希，不看有没有单）；
  只推到 `APPROVED` ⇒ `eco_change_unverified`；推到 `VERIFIED` ⇒ `complete`；复验后追加一行 ⇒
  又 `uncovered`（detail 把两张单各声称什么全印出来）；补一张覆盖新哈希的单 ⇒ 真 `aipd validate`
  的子进程读数从 `false` 翻成 `true` 并给出 `2/2`。
  **不读过头**：那一步里 `aipd release manifest` 仍 `rc=4`、`aipd validate` 的 `passed` 仍 `false`
  （临时文档本来就缺图纸/CTQ/BOM，四条判据各自都红）——本片只主张「这一条判据的读数跟着
  `eco` 段动了」，不主张「这份文档可以放行」。
  25 条常驻用例（生产者 20 + 门 5，其中 3 条用子进程真过门）+ 变异电池
  **17 条：杀 17 / 活 0 / 注入无效 0**。电池自己也被修过一次：原 E2 的锚点还写着上一版的
  `not in DEAD_STATUSES`，判据改形后命中 0 次 ⇒ 电池报「注入无效」而不是「杀掉」（这正是
  把 `rc∈{4,5}` 且无失败行判成无效的用处）；门侧另两条候选注入（`'complete' in str(coverage)`、
  短路缺键分支）审下来**行为等价**，属化妆，按第 26 片 G19 的教训丢掉，换成四条真会翻转读数的。
  没做：没有上一版产物清单当基线 ⇒ 只证明「内容与某张闭合单一致」，不证明「自上次发布以来
  只改了这些」；`undetermined` 不区分「新文件」与「老文件动了没提单」；门只信生产者写进文档的
  读数、不重算哈希；署名仍无身份源（第 26 片记着）；ECO 不联动失效传播。
  全量用例数 2003 → 2028。证据见 `docs/audit/ECO_RELEASE_COVERAGE_F-C6-ECO_2026-09-25.md`。
  收口读数：被哈希面 611 → 612；`production_release_gate --release-ready --tag` 8/8 绿
  （第一次因外层 shell 没把 `.venv/bin` 放进 `PATH`、`shutil.which('pip-audit')` 查不到而报过一条假红，
  修法是补 `PATH` 不是放宽判据）；`audit_repo --strict` 仍只有那条「锚点停在 tag」的既有裁决红。

- **v5.12 F-C6-ECO 第 26 片：ECR/ECO 工程变更单有了生产者（C6 档位 13/1/1 → 14/0/1）**：
  普查里「版本与ECR/ECO」长期停在 checker_only，note 写着原因：版本那一半有生产者，
  **变更单这一半零实现**。本仓 `changes` 表是审计流水（谁在什么时候改了什么），
  答不了「谁批准了这项变更、影响哪些件、生效复验了没有」这三件事。
  选型（2026-09-25；OSS 仓库侧由派出的研究子代理实读，frappe 审批判据与 NASA 接口大纲
  两条我已自行复核；MIL-STD/ISO/ECSS 正文**没读到，因此不引用**）：
  ERPNext 全树按 `change_note`/`eco`/`engineering` 检索 **0 命中**（只有 BOM Update Log 与
  Quality Action），Odoo 的 `mrp_eco` 在**企业版**（公开仓库 16/17/18 树里没有该模块），
  唯一活跃的开源 PLM（odooplm，plm LGPL-3 / 相邻模块 AGPL-3）自己把 ECO 代理回 `mrp.eco`，
  Aras Community 免费使用但不开源，若干 ECOFlow 克隆**没有 LICENSE** ⇒ 不可合法引入。
  ⇒ **可依赖形态的 ECO 实现在开源世界不存在**，只能本地实现借模型：
  借 Dynamics 365 ECM 的 Approve→Process→Complete、odooplm 的 released 冻结写、
  frappe `has_approval_access()` 的 `user != doc.get("owner")`（原文判据已核到）。
  落点：migration **v19** 建 `eco_records` / `eco_affected` / `eco_transitions` 三张表
  （+3 条索引），`change_orders/eco.py` 一台查表的状态机，CLI 四个公开命令（51 → 55）：
  `eco create` / `eco affected` / `eco transition` / `eco show`。三条不打折的形状规矩：
  ①**不许自批**——`APPROVED`/`REJECTED` 的 actor 必须是真人且 ≠ 创建人，机器身份表
  `NON_HUMAN_ACTORS` 连空串都算；`creator` 与 `approver` 分两列且 `approver` **无默认值**，
  因为本仓 `gates.approved_by DEFAULT 'AI-internal'` 那个形状等于「不写审批人也算 AI 批过」
  （那个既有缺陷只记录、不在本片改，属主裁）；②**影响清单必须带 sha256**——UPDATE 要前后两头，
  ADD/REMOVE 要各自那一头，给了值的第三头也必须像哈希，送审即冻结；
  ③**「已实施/已复验」不是给自己盖章**——要交落地凭据 + 可解析的生效时间 / 复验凭据，
  `SUPERSEDED` 必须指向另一张真存在的单；转移流水只追加，仓储层不提供任何 update/delete 入口。
  被状态机拒 ⇒ **退 4**（不是 0 也不是 2）：否则脚本会把「张三批了自己的单」读成成功。
  42 条常驻用例 + 变异电池 **19 条：杀 19 / 活 0**。两条电池教自己的：G19 第一轮只**改索引名**
  （列序不变 ⇒ 查询计划不变）那是行为等价的化妆注入，「存活」不等于没闸——换成**删掉**热查询
  那条索引后，新加的「索引列序 + EXPLAIN QUERY PLAN 必须走它」两条立刻开火；
  G5 第一轮真存活是缺口：可选那一格（`ADD` 的 `before_sha256`）没人查，补一条用例才杀得动。
  没做：**发布门还不读 ECO**（「manifest 哈希有差却没有一笔闭合 ECO」这条 fail-closed 判据
  是下一片），署名没有身份源（是声明不是证据），ECO 不联动尺寸链/成本/Product Truth 失效传播。
  全量用例数 1961 → 2003；被哈希面 607 → 611。
  证据见 `docs/audit/ECO_CHANGE_ORDER_F-C6-ECO_2026-09-25.md`。

- **v5.10 修复 F-EVID-03 第 23 片：证据侧车按「干名」拼，同干名的两个产物互相顶掉**：
  四个写入点各自 `path.with_suffix(".evidence.json")`，而换后缀会把 `.step` / `.dxf` 一起换掉 ⇒
  `assy.step` 与 `assy.dxf` 的侧车是**同一个文件名**，出完图再读模型，读到的是那张图的凭据
  ——侧车是这一路唯一的机器可读凭据（回读核对结论、双哈希、球标↔BOM 绑定都在里面），
  顶掉的后果不是报错而是**拿 A 的凭据给 B 盖章**；字段名恰好不重合时才发现（第 22 片端到端
  就是撞上的这一次），重合时读到的就是一套自洽但属于别人的证据。
  修法选了「侧车名 = **产物全名** + `.evidence.json`」而不是「先拒绝顶掉」：动手前数过消费方——
  全仓跟踪在案的 `.evidence.json` 文件 **0 个**（`git ls-files` 现算），所以不存在老侧车读不到的
  迁移问题，止血方案要防的风险在这里根本不存在；产品侧只有 4 个写入点 + 3 个读取点在拼这个名字，
  全部收进 `cad/evidence.sidecar_path()` 一处即可；测试侧 20 处跟着改（4 处是硬写文件名的字面量）。
  止血方案反而更贵：它不消除「两个产物不许同干名」这条用法限制。**不留兼容分支**。
  9 条常驻用例（`tests/test_evidence_sidecar_paths.py`）：拼法用**字面量**钉住（不跟着助手函数一起错）、
  真导出 + 真出图证明两份侧车并存且**各自哈希对得上自己那份产物**、外加一条
  「全仓 `src/` 里再不许出现第二处侧车拼法」的 grep 守卫防复发。
  变异电池 **8/8 killed**，其中 S5/S6 打在 DFM 与步骤文档**各自文件的既有用例**上
  ——证明这次改名不是只有新文件看得见。全量用例数 1893 → 1902。
  一处过程教训值得记进规矩：批量替换第一版用「任意表达式 + `.with_suffix(...)`」的正则，
  把 `json.loads(out.with_suffix(...).read_text(...))` 这类嵌套调用改成语法不通的残骸，
  12 个文件里 8 处中招；整批 revert 后改用「只匹配裸标识符」的严格式，并**写盘前逐文件
  `ast.parse`**，之后才谈得上跑测试。批量改写的底线是「改完必须能被解析」。
  证据见 `docs/audit/EVIDENCE_SIDECAR_PATH_COLLISION_F-EVID-03_2026-09-25.md`。

- **v5.10 修复 F-NET-01：HTTP 出口收敛为单一标准库客户端**：迁移前 src/ 有
  **9 个出口调用点 / 7 个模块**各写一遍（7 处 `urlopen` + 2 处 `requests.post`），
  超时默认值 3 种（60/30/20 秒）、9 处出口**一处都不重试**（会处理 429 与
  `Retry-After` 的只有脚本连接器那一套 urllib3 策略）、scheme 白名单靠 3 处 `# noqa: S310` 写成
  约定，且 `requests`（本仓 `full` **optional extra**）泄漏进两条 eval 真实端点路径
  ——最小安装下只能以「缺少 requests 依赖」报错兜底。现统一走
  `aipd_os.net.http`（发请求前拒非 http/https、只重试 429/5xx、`Retry-After`
  双形态、退避封顶、默认 `max_attempts=1` 使付费端点不重复计费、非 2xx 带正文返回）。
  守卫：`tests/test_net_egress_convergence.py`（AST 扫描 + 分母前提 + 5 形态注入反证）。
  顺带修三处假绿：打桩 `requests.post` 的用例迁移后成为空操作（实测把请求发到开发者
  机器代理），改本地真 HTTP 服务；两处 `FakeResp` 缺 `getcode()/headers`；新客户端
  自身被本仓异常卫生门禁判红。`scripts/research/_http_runtime.py` 保留 requests——
  它要给第三方自有的 `requests.Session` 挂策略，标准库做不到；
- **v5.10 修复 F-REL-01：发布证据读的是每轮都会被覆盖的可变路径**：
  `PROVENANCE.test_report` 记录的是 `docs/audit/pytest-report.json`，而这份文件自
  v5.6.0 之后每轮重跑都被覆盖。本轮按流程重生成证据后，发布门从 8/8 掉到 7/8，红项
  `test_numbers_from_report: report STALE`——「v5.6.0 的发布证据」实际指向一棵比 tag
  更新的树。修法不动门禁、不动 tag、不重签名：从 git 历史取回与旧 `PROVENANCE` 所记
  sha256 逐字节相同的 tag 时代报告（1096 passed / `source_commit=a660405`）归档为
  `docs/audit/pytest-report-v5.6.0.json`，`--test-report` 改指该归档件；轮级报告继续
  单独存在。读法同时更正：`--release-ready --tag` 的 8/8 认证的是 **tag 那棵树**的测试
  结果，本轮这棵树的证据是 1385 passed / ruff 0 / mypy 0 / 性能门 PASS，两者不可互换
  引用；也不得用 `AIPD_SOURCE_COMMIT` 把报告钉到 tag 上（那等于用未发布的树冒充已发布提交）；
- **经验回灌（定位修正）**：成功轨迹/黄金样本从「评测资产」升级为「运行时
  提示资产」——`llm/experience.py` 把内置黄金经验注入两个 LLM Provider 的系统
  消息（确定性、带指纹可审计，`AIPD_EXPERIENCE_FEEDBACK=0` 可关闭），回归
  「规则喂养 AI 而非替代 AI」的原初定位；
- **演示模式撤出产品（商业化决策）**：内置示例/演示项目不进入产品面——
  `aipd onboard` 与 Web 首次向导移除「示例项目/导入示例项目」；黄金演示数据
  （evals/golden_projects、assets/examples）移入 tests/fixtures（仅测试用）；
  `aipd eval`/`run-evals` 默认 Provider 由 fake 改为 model（真实端点，未配置
  诚实报错），fake/contract-test 仅供开发测试显式选择；
- **v5.10 Canonical Validation / Issue / Readiness（2026-08-24）**：
  - **Canonical Validation Domain**（migration v13）：ValidationPlan / ValidationTest /
    ValidationRun / ValidationResult 四张表，全含 tenant_id + project_id 作用域；
    ValidationService 提供 CRUD + stale propagation（artifact revision 变化自动标记
    stale，stale PASS 不计入有效结果）；
  - **Canonical Issue / Corrective Action**：Issue + CorrectiveAction 表，close 语义
    防绕过（disposition 必须记录、revalidation 必须存在、blocking condition 必须解除、
    audit trail 完整）；idempotent creation（相同 validation_result_ref 不重复创建）；
  - **EVT/DVT/PVT Ingestion Canonicalization**：IngestionService 实现
    CSV/XLSX/JSON → parser → DTO → schema validation → ValidationService → IssueService
    完整链路（不再把临时 dict 当最终真相）；
  - **Manufacturing Readiness Gate**：ReadinessService 确定性计算 8 个维度
    （product_definition / CAD / BOM / cost / validation / issues / supply_chain / lineage），
    缺数据默认 HOLD 不是 PASS，LLM 可解释但不决定 PASS/FAIL；
  - **CLI 命令**：`aipd validation plan/list/show/import`、`aipd issue list/show/resolve`、
    `aipd readiness check`，全部支持 `--json`；
  - **Command Truth Single Source of Truth**：`src/aipd_os/cli/command_contract.py` 集中
    管理所有命令元数据（status / category / introduced_in），skill_quality_audit.py
    消费 canonical contract 不再硬编码；
  - **Audit Repo Strict Mode**：`scripts/audit_repo.py --strict` 在 manifest hash
    mismatch / version inconsistency / provenance commit mismatch 时 exit 1；
  - **Agent Boundary Enforcement**：`docs/architecture/project_boundary.md` 声明 AIPD-OS
    是执行后端（IdeaToLaunch 是唯一 agent-facing 入口），`agents/openai.yaml`
    `allow_implicit_invocation: false`，架构回归测试覆盖；
  - 91 新测试（1099 → 1190），ruff 全通过，mypy 194 文件无错误；
- **收口迭代（2026-08-14+）**：P1×4 缺陷修复（视觉审核诚实降级 / 认证时区 /
  邮件附件 / 状态双重维护标注）+ 发布证据门禁全绿；随后一批代码质量与 UX 收口
  （详见 `docs/audit/IMPRESSION_*` 与本迭代的修复清单）：
  - 修复 closure fact↔evidence 证据自链、决策中心影响列渲染、PDF 假全文、
    视觉审核 `passed` 非布尔假通过、lab .xlsx 断链、Gmail XOAUTH2 认证、
    时间戳时区三态、Gate maturity 字符串比较等正确性问题；
  - 发布门禁 fail-closed（CVE/证据缺失/git 不可用不再空真通过）、
    rollback_v5 按 project 过滤防多项目数据污染；
  - UX：`aipd doctor` 不再因无关敏感环境变量硬失败、CLI 状态去 emoji 纯文本、
    provider 配置提示与实现真实环境变量对齐、`--json` 输出纯净、skip-link 可聚焦、
    `aipd operate` 打印进度事件；
  - 卫生：三套 token 估算口径统一、三套 LLM JSON 解析助手收敛、废弃
    `aipd_store` 自检切换 AIPDStateDB、一次性补丁脚本归档、SKILL/state_service
    文档刷新、CI 增加 lint（ruff/mypy）job。

- **P2 状态归属收敛（2026-08-24 ~ 2026-09-24，M1–M10 全部关闭）**：
  - **M1–M9**：统一状态基础设施（`state/connection.py` ConnectionFactory +
    `state/transaction.py` + 8 类错误语义）、ClosureStore/ExecutionRuns 的
    tenant+project scope（含 10 条跨租户负例）、5 个 domain store 迁移到
    工厂、Manual JSON 收敛进 canonical DB（`ManualStateRepository`）、
    Outbox + External Operation ledger（v14，含 lease 与 dispatcher runtime）、
    统一 stale 传播服务（v15/M6）、Readiness snapshot + ruleset 版本化（M7）、
    migrations 模块化（schema/helpers/definitions/runner）、Issue 乐观并发（M9）；
  - **M8 收口修复（F8）**：模块化留下 `definitions → helpers → runner →
    definitions` 导入环（helpers 以函数内 import 取 `runner._exec_script`），
    工具下沉为叶子模块 `migrations/sqlsplit.py` 后断环；
  - **F5（Critical）重入事务自死锁**：`ConnectionFactory.transaction()`
    每次另开连接并 `BEGIN IMMEDIATE`，同线程嵌套时与自己的写锁互等，
    `busy_timeout` 到点抛 `database is locked`——`run_supervisor` 的 execute
    阶段因此整体退化为 `internal_rework`（`add_lineage → project_id → connect`
    即触发）。改为按 **(解析后库路径, 线程)** 登记活动事务：重入复用同一连接
    并以 `SAVEPOINT` 提供内层原子性，与 v5.9.1 起 `AIPDStateDB` 已在用的形状收敛
    一致。新增 `tests/test_connection_reentrancy.py`（8 例，反向验证：旧实现下
    6 例失败、耗时 31.8s 全是等锁）；
  - **F6 stale 传播写坏列**：`_mark_downstream_stale` 的 cost_snapshot 分支
    向 `changes` 写 `entity_type/entity_id/change_type/change_data`——这些列
    不存在，一旦依赖图非空即 `OperationalError`。原有 P2-M6 用例全部跑在
    「零依赖」图上，因此从未执行到该分支。修列名并补齐 3 条非空依赖路径用例
    （BOM→cost 写 changes、CAD→validation_result 标 stale 且不改 PASS 语义、
    零依赖合法路径）；
  - **F7 热读路径缺索引 → migration v17**：`EXPLAIN QUERY PLAN` 显示
    `changes` 按 (tenant, project) 取最近 N 条是全表 `SCAN` + 临时 B-tree，
    outbox `claim_available` 对全量候选做 `ORDER BY available_at` 排序。
    新增 `idx_changes_scope_time` 与 partial 索引 `idx_outbox_due`；
    实测（同机 A/B）审计取最近 100 条 5.57ms → 1.36ms，claim 批处理
    2.62ms → 2.32ms（纯候选读取 0.29ms → 0.01ms，排序项随积压消失），
    outbox 追加写放大不可测出（129.6k vs 139.7k ops/s，落在噪声内）；
  - **M10 性能验证量具**：`scripts/state_perf_gate.py`（12 场景 × N 轮，
    min/median/mean/max/stdev，与 `docs/audit/state_perf_baseline.json` 比**相对**
    劣化，另含轮内比值门禁「单事务批处理 ≥3x 逐条自提交」；实测批处理
    18.4k–22.2k ops/s vs 逐条 277–300 ops/s）+
    `tests/test_state_perf_gates.py`（机器无关硬门禁：查询计划、连接复用计数、
    claim 互斥、传播语句数线性度）；量具本身做过两组反向验证（人为收紧基线、
    真实删除 v17 索引）均能判红；
  - **文档诚实性修正**：`state_infrastructure.md` 原记载的
    `PRAGMA timeout = 10000` 在 SQLite 中不存在（实测被静默忽略），已删除；
    连接等待改记为 `sqlite3.connect(timeout=...)`；
  - 收口前基线为 **6 failed / 1262 passed**（HEAD 1d0f84f，工作区干净），
    收口后全量回归 0 失败；详见
    `docs/audit/P2_M10_STATE_PERF_CLOSURE_2026-09-24.md`。

## [5.6.0] — 2026-08-06

AIPD-OS v5.6「Release Candidate 产品化收口版」—— 从“可靠的 Beta 编排内核”推进为“可复现、可实际操作、对产品所有者友好的 Release Candidate”。

- **P0-1 发布证据体系重构**：
  - 拆分 `SOURCE_MANIFEST.json`（只覆盖确定源文件，不含会自变的清单自身）与 `BUNDLE_MANIFEST.json`（对最终压缩包逐条哈希），新增 `PROVENANCE.json`（source commit / 构建环境 / 构建时间 / 依赖锁定 / 测试报告 / bundle hash）；三份证据互不自引用，均指向最终 tag SHA；
  - 能力矩阵改为 **Capability Registry**（`src/aipd_os/registry.py` + `registry_data.py`）驱动，分类由运行时证据动态推导（schema / 实现文件存在性 / 入口可调用 / 证据时效四类校验），废除与代码脱节的静态判断表；
  - 签名升级为 **Ed25519 公开密钥数字签名**（`cryptography`），`sign_release.py` 支持 `--keygen/--sign/--verify`，明确区分摘要(.sha256)/MAC(.sig)/数字签名(.ed25519.sig)；
  - release-ready 门禁新增：工作区 clean、tag→SHA、Source/Bundle 零差异、机器测试数字、签名可验证、无未承认 CVE/许可证/secret；篡改被保护文件即失败；
  - `aipd audit` 在干净 clone 与解压包中可复现一致。
- **P0-2 真实 CAD 黄金闭环**：`CadQueryBackend` 重写为真实可编辑参数化 B-Rep 内核（`export_native` 产出可独立执行的原生源、`load_native_model` 真正恢复可编辑表示、`regenerate`/`geometry_validity_check`）；黄金闭环测试用真实 CadQuery 2.5.2 / OCP 7.7.2 跑通参数→特征→改参→重生成→STEP→源导出→重载→几何校验→哈希→差异→Product Truth 写回；明确 C0–C3 成熟度定义，ContractBackend 仅作降级后端不计真实 C2；CI 新增 `cad-golden-loop` job 真实安装并运行内核。
- **P0-3 Owner Web Console**：新增 `aipd ui` 本地界面（标准库 HTTP 服务，CLI/Web/JSON 共用同一应用服务），含首次向导、项目总览、决策中心（默认一个真决策、不暴露内部 ID）、制品中心、运行控制、外部等待中心；窄屏适配、键盘操作、基础无障碍、中英文一致。
- **P1-1 Product Truth + 失效传播 + 自动返工**：结构化 Product Truth 数据模型（事实/假设/需求/CTQ/证据/决策/风险/制品版本/来源/可信度/时效，sqlite 存储，非 steps_log 字符串）；显式依赖图与血缘图；上游变化→下游 stale→有界返工→新版本→验证→关闭 stale；防循环依赖/返工风暴/无限重试；Owner 可读变更说明。
- **P1-2 真实邮件 Provider**：真实 SMTP 发送与 IMAP 收件/线程关联/附件下载/幂等同步（标准库 smtplib/imaplib），host 已配置即真实发送；显式人工批准 + 审计；Mailpit 协议集成测试（未配置容器时诚实 HOLD）；可选 Gmail OAuth Provider（无凭据不冒充已完成）。
- **P1-3 真实图像/视觉 Provider**：OpenAI-compatible 真实图像 Provider 客户端（凭据门控，真实发请求解析图像字节，拒绝 PIL 冒充）；失败页单页重建入口（未修改页哈希不变）；Anchor Registry / Visual Bible 可机器比较特征；真实多模态视觉审核客户端；无凭据输出外部任务包并 HOLD。
- **P1-4 研究与真实模型评测**：区分 metadata/abstract/full text/OCR/引用片段；全文获取/解析/缓存/去重/版权边界；结论绑定来源/段落/时间/适用范围/过期策略；真实模型评测记录 provider/model/网络/token/费用/延迟/重试/trace，fixture 永不进入真实通过率，无凭据报告 0 样本。
- **P2 平台化与长期质量**：Provider SDK + 能力声明 schema + 示例插件；凭据安全存储与日志脱敏；结构化日志/trace/指标/成本预算；长任务资源限制/并发/取消/断点恢复；DB migration/备份恢复兼容测试/升级指南（`docs/UPGRADING.md`）。
- **E2E 三个黄金项目**：连续附件产品手册、参数化 CAD 与工程变更、RFQ-报价-实验-纠正，均从一句需求到真实状态写回/恢复/决策/制品生成/发布检查，产物落盘 `releases/golden-projects/`。

## [5.5.0] — 2026-08-06

- **P0-2 版本统一 5.5.0**：`pyproject.toml`、`src/aipd_os/__init__.py`、`src/aipd_os/state/__init__.py`、`scripts/regenerate_release_manifest.py`、`tests/test_packaging.py`、README / CHANGELOG / QUICKSTART / SKILL 全部对齐到 5.5.0；
- **`aipd doctor`**：新增一键体检命令，报告包版本、依赖可用性、配置、外部能力（视觉后端 / 模型端点 / 图像后端 / CAD 内核 / 邮件）、数据库、对象存储与权限，支持 `--json` 机器可读输出；
- **`aipd version --verbose`**：新增 `version` 子命令，`--verbose` 打印包版本、Git HEAD（`git rev-parse HEAD`）、构建时间、能力矩阵版本与发布清单 SHA-256；
- **P0-1 CI 加固**：`.github/workflows/ci.yml` 将 `actions/checkout` / `actions/setup-python` 升级到 v5（消除 Node 20 弃用告警）；`integration` job 运行真实 `@pytest.mark.integration` 端到端测试；新增 `release-ready` 门禁 job，在所有 CI job 成功后校验测试与发布清单有效性；
- **P0-3 视觉发布门**：将 `VisualAuditor` 与 `GoldenGapEvaluator` 接入手工发布门禁（`scripts/manual_chain.py check-release` 与 `scripts/manual_chain_gate.py`），门禁覆盖页面结构、参数真实性、中文文本、产品/模块/人物一致性、CMF、相机、光照、禁旧图复用/拼版与黄金样本差距；无视觉后端时门禁返回 HOLD / `not_verified`，绝不假通过；
- **回归测试**：新增 `tests/test_visual_audit.py`、`tests/test_integration_smoke.py`，扩展诚实性断言，确保无视觉后端时页面/批次不得通过、手工发布门禁在需视觉但不可用时返回 HOLD。

## 5.3.0 — 2026-08-06

- **风险 RYG / 外部等待所有者视图**：Supervisor 增加风险红黄绿（RYG）分级与外部等待（blocked_external）的所有者视图，等待外部报价/样机/测试期间继续其他独立工作；
- **确定性可信度 / 人体测量 / 认证模块**：新增 `credibility`、`anthropometry`、`certification` 三个确定性模块，事实与认知一律可追溯、不虚构；
- **视觉审计诚实护栏**：视觉落差评估拒绝为“看起来像”背书，防止视觉意图覆盖安全；
- **命令覆盖一致性测试**：新增 `tests/test_command_coverage.py`，对声明 / 注册 / 测试三向命令集合做一致性校验；
- **SKILL.md v5.3 刷新**：按工作流分组声明 17 个一键命令（`init` / `intake` / `resume` / `status` / `run` / `decide` / `manual plan` / `manual generate` / `cad preflight` / `cad build` / `industrialize` / `validate` / `audit` / `release check` / `test` / `eval` / `package`），专业细节集中到 `references/`，并新增 `scripts/skill_quality_audit.py` 自审脚本。

## 5.2.0 — 2026-08-06

- **能力矩阵审计产物**：新增 `scripts/capability_matrix.py` 与 `aipd audit` 命令，产出 `docs/audit/repository_snapshot.json`（默认分支/HEAD SHA/时间/版本/文件树/tag/release/CI/manifest 哈希/未跟踪/冲突/依赖锁/SBOM/签名）、`docs/audit/capability_matrix.json` / `.md`（六大域全部能力按 7 类分类，含声明/实现/入口/运行命令/输入输出/测试/端到端证据/当前限制）；
- **真实/可插拔模型评测**：`EnvCompletionProvider.complete()` 接入 OpenAI 兼容 HTTP 端点（`AIPD_EVAL_MODEL_ENDPOINT/KEY/VERSION`）真实调用；未配置时抛 `ModelNotConfiguredError` 并诚实标记 `external_dependency`，绝不返回伪造输出；保留脚本化假模型作为离线回退；
- **干净环境安装修复**：将 `mcp`（Requires-Python >=3.10）移出 `[full]` 至独立 `server-mcp` extra，保证 Python 3.9 下 `pip install -e ".[full,dev]"` 可成功；CI unit/integration job 安装完整依赖，全部测试可收集并通过；
- **CI audit job 扩展**：增加能力矩阵生成与 `test_capability_matrix.py` 校验；
- **能力矩阵真实性核验**：70 项能力分类（fully_implemented 52 / partially_implemented 7 / external_dependency 11），全部结论可追溯到证据。

## 5.1.0 — 2026-08-06

- **可再生成的版本真实性审计**：`scripts/audit_repo.py` + `docs/audit/`，读取 git 提交、pyproject 版本、Release Manifest 哈希、CI job 与遗留 CAD 冲突，输出机器可读 JSON 报告；
- **统一执行记录字段集**（`unified_record`）：`provider_version` / `token_usage` / `started_at` / `completed_at` / `error_type` / `evidence_ids` / `artifact_ids` 别名，`fallback_from` 降级来源，`project_id` / `capability` / `retry_parent` 持久化；
- **CAD 成熟度术语扫描扩展**至 docs/scripts/templates/examples，并加入 faceted 过度声称防护；
- **生产发布门禁升级为证据门禁**（`evidence_checks`）：`gdt_covers_ctq`、`ctq_has_inspection`、`drawing_cad_same_revision` 等；
- **WBX-1 黄金样本视觉落差评估**（`visual_audit/golden.py`）；
- **供应链与验证执行器**（`supply_chain/`）：quotes / suppliers / lab / analysis，并升级 supplier / mail_rfq / evt_dvt_pvt 适配器；
- **行为评估扩展至 15 项**（`evals.json` v1.2）；
- **16 个一键命令**（init / intake / resume / status / run / decide / manual plan / manual generate / cad preflight / cad build / industrialize / validate / release check / test / eval / package），支持 `--json` 模式；
- **py.typed**：类型标注标记；
- **提示注入隔离增强**：高风险动作需人工批准。

## 5.0.0 — 2026-08-05

- 新增统一执行层（Execution Router / Tool Adapters），按能力选择适配器、重试与降级切换、持久化执行记录与证据；
- 统一 CAD C0–C7 成熟度推进，配合 maturity / capability / production release 门禁；
- 新增手册链自主执行（连续附件手册 + 独立视觉审计）；
- 状态服务生产化：多租户授权、迁移、备份、检查点、追加式审计、健康检查、对象存储与静态加密；
- 新增 Owner Experience 层：决策卡片、所有者自然语言视图与一键命令；
- 新增 Evals Runner：生命周期门禁与质量回归评估；
- 新增安全：提示注入隔离、敏感数据打码与显式权限、确定性 SBOM、发布物签名；
- 工程化：CI 流水线、`SECURITY.md` / `THREAT_MODEL.md` / `SBOM.md` / `RELEASE_SIGNING.md` / `CONTRIBUTING.md` / `CODE_OF_CONDUCT.md` / `QUICKSTART.md` / `docs/architecture.md`。

## 4.0.0 — 2026-08-05

- 从“产品手册+CAD主管”升级为AI全链路产品开发与交付主管；
- 新增S0—S8生命周期、工作队列、能力注册、决策策略和声明门；
- 将用户成功提示词轨迹与合格手册纳入黄金样本；
- 保留并统一编排理论研究、连续附件手册、CAD、工业化和验证子系统；
- 强制变更传播与证据化成熟度声明。
