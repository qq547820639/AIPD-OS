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
  边界与未实现项（GD&T/尺寸链/剖视/爆炸图/装配图、相切轮廓单侧）见
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
  5 条新用例（含「正好等于上限」与「差 1 字节」两个边界方向）；- **v5.10 修复 F-EXEC-05：接线的后果自己也有洞——「结果未知」必须可见**：
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
