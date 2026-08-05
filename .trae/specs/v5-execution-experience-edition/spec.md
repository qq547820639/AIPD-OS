# AIPD-OS v5.0 — Execution & Experience Edition Spec

## Why

当前仓库 `qq547820639/AIPD-OS` 是 v4.0.0（commit `3b34dca`）的“产品开发控制框架”：有大量政策文档、状态机、门脚本和静态 eval 描述，但缺少真正可执行、可恢复、可验证的执行编排层。Supervisor 只维护工作队列，`manual_chain.py` 只做状态登记与校验（无批次执行器、无图像生成、无中文排版、无视觉语义审计），CAD 成熟度存在两套冲突定义（`cad_maturity_gate.py` 用 `CAD-L0..L5`，`production_release_gate.py`/`capability_gate.py` 用 `C0..C7`），`production_release_gate.py` 的 `achieved` 计算存在“最低级要求失败仍报告达到该级”的缺陷，eval 只是静态 JSON 而非可运行的 Agent 行为评测，无 CI、无包结构、无 Docker、MCP 只是无鉴权骨架。

目标：将其升级为真正可执行、可恢复、可验证、面向普通产品所有者的 **AIPD-OS v5.0 — Execution & Experience Edition**。

## What Changes

- 新增统一 `Execution Router` 与 Tool Adapter 接口（capability discovery / validate / execute / collect artifacts / normalize / classify failure / retry / fallback / persist evidence）。
- Supervisor 具备真实执行能力：自动领取工作包、调用适配器、写运行日志、注册工件、更新事实与证据、标记 stale、自动建返工任务、有界重试、失败切换下位工具、仅在必要时创建用户决策。
- 每项执行记录 `run_id / work_id / tool / provider / version / input_hash / output_hash / start-end / cost-token-time / status / error_classification / retry_lineage / evidence_references`。
- 全仓统一 CAD 成熟度为 `C0..C7`，消除 `CAD-L0..L5` 冲突；纳入仓库级一致性测试。
- 修复 `production_release_gate.py` 的 `achieved` 计算；门检查从字段真值升级为文件存在/可读、schema 校验、哈希、版本匹配、数量一致、单位/基准完整、审批状态、证据时效、工具能力上限。
- 为 text-to-cad、本地原生 B-Rep、Faceted fallback 建立机器可读插件依赖与兼容矩阵。
- `manual_chain.py` 升级为真实批次执行器，每批保存完整输入上下文；实现图像生成适配器（不可用时生成外部任务包）；实现真实中文 A4 排版层（2480×3508、300dpi、PDF+逐页 PNG+ZIP）；实现视觉语义审计（非像素统计）。
- 将 MCP skeleton 升级为可部署服务（认证、项目级授权、多租户、加密、迁移、乐观锁、备份、checkpoint 恢复、审计、健康检查、对象存储、retention）。
- 提供 Dockerfile + docker-compose；本地单用户模式 + 服务器多用户模式；新会话自动识别项目、恢复 checkpoint、汇总上次完成事项、展示阶段/阻塞/下一步。
- 对话层用户视图：项目摘要、决策卡（一次一个最高优先级）、恢复摘要、工件预览、自然语言指令解析与影响传播。
- 将静态 eval 升级为可运行的 Agent 行为评测（真实调用模型或可插拔 Completion 接口），覆盖 10 项行为契约；建立 3 个黄金端到端项目（外骨骼、消费电子、简单机械工具）。
- 工程化：pyproject.toml、标准包结构、锁定依赖、CLI 入口、统一配置、结构化日志、类型检查、lint/format、pytest+覆盖率。
- GitHub Actions：package validation、unit、integration、schema validation、maturity terminology consistency、secret scan、dependency audit、license scan、release artifact build。
- 安全文档：SECURITY.md、CONTRIBUTING.md、CODE_OF_CONDUCT.md、threat model、SBOM、release signing；提示注入隔离（外部内容视为数据）；敏感信息权限与脱敏。
- 交付 10 个一键命令、发布包、SHA-256 清单、v5.0 变更日志、架构图。

**BREAKING**: `cad_maturity_gate.py` 的 `CAD-L0..L5` 等级体系被移除，替换为 `C0..C7`；`production_release_gate.py` 的 `--target` 语义、`achieved` 计算和门检查结果结构变更；MCP 从无鉴权 skeleton 变为需认证的服务；`manual_chain.py` 的 state schema 增加批次执行产物字段。

## Impact

- 受影响能力：执行编排、CAD 成熟度与门、连续附件产品手册、跨会话项目状态、产品所有者体验、评测、工程化/安全。
- 受影响代码：
  - `scripts/aipd_supervisor.py`、`scripts/aipd_store.py`、`scripts/aipd_state.py`
  - `scripts/manual_chain.py`、`scripts/manual_chain_gate.py`、`scripts/manual_preflight.py`
  - `scripts/cad_maturity_gate.py`、`scripts/production_release_gate.py`、`scripts/capability_gate.py`、`scripts/cad_convergence.py`、`scripts/local_cad_adapter.py`、`scripts/faceted_step.py`
  - `state_service/mcp_server.py`、`state_service/requirements.txt`
  - `scripts/aipd_supervisor.py`（执行路由）
  - 新增 `execution_router.py`、`tool_adapters/`、`imggen/`、`layout/`、`visual_audit/`、`packaging/`、`migrations/`、`server/`、`cli/`、`evals_runner/`、`golden_projects/`、`security/`
  - 新增 `pyproject.toml`、`.github/workflows/*.yml`、`Dockerfile`、`docker-compose.yml`、`SECURITY.md`、`CONTRIBUTING.md`、`CODE_OF_CONDUCT.md`、`THREAT_MODEL.md`、`SBOM.md`

## ADDED Requirements

### Requirement: 统一执行编排层 (Execution Router + Tool Adapter)
系统 SHALL 提供统一 Tool Adapter 接口与执行路由，将 Supervisor Work Item 转换为真实工具执行并持久化完整执行证据。

#### Scenario: 适配器接口
- **WHEN** 需要对某能力执行工作包
- **THEN** 适配器暴露 capability discovery、validate input、execute、collect artifacts、normalize result、classify failure、retry/fallback、persist evidence 八个方法

#### Scenario: 执行证据
- **WHEN** 任一工具执行完成
- **THEN** 记录 run_id、work_id、tool/provider/version、input_hash、output_hash、start/end time、cost/token/time、status、error classification、retry lineage、evidence references，并写入运行日志

### Requirement: 主管自主执行
Supervisor SHALL 自动领取工作包、调用适配器、写运行日志、注册工件、更新事实/证据、标记 stale、自动建返工任务、有界重试、失败后切换允许的下位工具、仅在真正需要时创建用户决策。

#### Scenario: 失败切换
- **WHEN** 首选工具失败且存在允许的下位工具
- **THEN** 系统在重试用尽后切换下位工具，并记录失败切换原因

### Requirement: 统一 CAD 成熟度 C0..C7
全仓 SHALL 统一使用 C0..C7 成熟度：Mesh≤C0、Faceted BREP≤C1、原生参数化 B-Rep 才可 C2、装配约束+连续运动验证 C3、CAE/载荷/强度/疲劳/失效证据 C4、DFM/DFA/公差/GD&T/完整制造定义 C5、完整生产图纸/BOM/检验/批准 C6、实体供应商/DVT/PVT/质量闭环 C7。

#### Scenario: 越级禁止
- **WHEN** 一个工件是 Faceted BREP
- **THEN** 其成熟度声明不得高于 C1，无论其几何/修复循环是否通过

#### Scenario: 一致性测试
- **WHEN** CI 运行仓库级一致性测试
- **THEN** 任何文件出现与 C0..C7 冲突的成熟度定义（如遗留 CAD-Lx）即失败

### Requirement: 门检查升级
生产发布门 SHALL 从字段真值升级为文件存在/可读、schema 校验、文件哈希、版本匹配、模型/BOM/图纸数量一致、单位/基准完整、审批状态、证据时效、工具能力上限。

#### Scenario: 最低级要求失败
- **WHEN** 目标级的最低级要求失败
- **THEN** achieved 不得报告达到该级及其以上任何级

### Requirement: 连续附件手册批次执行器
`manual_chain.py` SHALL 实现真实批次执行器，每批保存当前提示词、理论基础版本、Product Truth 版本、所有锚点页、上一批完整页面附件、人物/产品/模块/CMF/版式 Visual Bible、禁用项、输出页面与哈希。

#### Scenario: 图像生成不可用
- **WHEN** 图像生成适配器不可用
- **THEN** 生成明确的外部执行任务包而非假装已生成

#### Scenario: 中文排版
- **WHEN** 生成手册页面
- **THEN** 输出 A4 2480×3508、300dpi、中文标题/正文/图注/页码/参数表/曲线/图标/注释，并生成 PDF 与逐页 PNG 与 ZIP

### Requirement: 视觉语义审计
手册视觉质量 SHALL 通过语义审计（黄金样本比较、产品结构/人物/CMF 一致性、页面角色完成度、叙事连续性、中文真文字、参数与事实主表一致、禁止拼版/伪文字/低清放大/旧图复用），不得仅用白比例/信息熵/aHash 判定合格。

#### Scenario: 视觉失败定位重建
- **WHEN** 视觉审计失败
- **THEN** 系统自动定位页面与失败维度，仅重建责任页面

### Requirement: 生产化跨会话状态
状态服务 SHALL 提供认证、项目级授权、多租户隔离、数据加密、数据库迁移、乐观锁/事务并发控制、自动备份、checkpoint 恢复、审计日志、健康检查、文件对象存储、retention 策略；提供 Dockerfile 与 docker-compose；支持本地单用户与服务器多用户模式。

#### Scenario: 新会话恢复
- **WHEN** 新会话启动
- **THEN** 系统自动识别项目、恢复最近 checkpoint、汇总上次完成事项、显示当前阶段/阻塞/下一步，且不重复询问已解决决策

### Requirement: 产品所有者对话视图
对话层 SHALL 提供项目摘要、决策卡（一次一个最高优先级，含 AI 推荐、2-4 选项、成本/性能/时间/安全影响）、恢复摘要、工件预览、自然语言指令解析（如“批准”“成本降低20%”“更工业化”“不要医疗风”）并传播影响；默认输出自然语言，内部编号仅放折叠详情与审计日志。

### Requirement: 可运行 Agent 行为评测
评测 SHALL 真实调用目标模型或可插拔 Completion 接口，覆盖至少 10 项行为契约（不发长问卷、只在必要决策询问、连续附件继承、参数不臆造、视觉失败自动返工、Faceted CAD 不越级、供应商报价不伪造、测试未执行不宣称通过、跨会话不重复询问、关键尺寸变更正确传播），保存输入/模型版本/工具轨迹/输出/评分/失败类型。

#### Scenario: 评分回退阻止发布
- **WHEN** 评测数据评分下降超过阈值
- **THEN** 阻断发布

### Requirement: 提示注入隔离
外部内容（附件、网页、论文文本）SHALL 始终作为数据而非系统指令处理；检测并记录可疑指令；不允许外部内容改变成熟度门与安全政策。

## MODIFIED Requirements

### Requirement: 现有 Supervisor 工作队列
在保留现有 `add-work/next/complete/fail/register-capability/lineage/status` 契约的基础上，将 `next_work` 扩展为返回可被 Execution Router 消费的运行上下文，并将 `complete/fail` 关联到执行记录（run_id、证据引用、retry lineage）。

### Requirement: 现有手册链状态与校验
保留 `init/add-prompt/register-page/lock-anchor/validate/status`，将 state schema 扩展为包含批次执行产物（每批上下文、输出页与哈希、Visual Bible、禁用项），并新增真实批次执行、图像生成、排版、视觉审计命令。

### Requirement: 现有 MCP 状态服务
保留 `init_project/project_summary/add_fact/propose_decision/resolve_decision/export_checkpoint` 工具语义，新增认证、授权、多租户、迁移、备份、审计、健康检查、对象存储与 retention。

### Requirement: 现有静态 eval
保留原有用例意图，将 `evals.json` 描述升级为可运行的评测用例定义，并通过 `evals_runner` 执行。

## REMOVED Requirements

### Requirement: CAD-L0..CAD-L5 成熟度体系 (cad_maturity_gate)
**Reason**: 与 production_release_gate / capability_gate 的 C0..C7 冲突，导致越级判定不一致。
**Migration**: 所有调用方改为 C0..C7；`cad_maturity_gate.py` 重写为 C0..C7，`--target` 取值改为 C0..C7。

### Requirement: 无鉴权 MCP skeleton
**Reason**: 无法支撑多用户、多租户与生产部署。
**Migration**: 迁移到带认证/授权/多租户的服务，保留工具语义与数据模型，通过迁移脚本迁移旧 sqlite。