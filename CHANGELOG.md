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
