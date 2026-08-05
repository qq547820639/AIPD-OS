# AIPD-OS v5.4 — 可重复验证完成度审计与产品化深化版 Spec

## Why
仓库在 v5.3 已具备完整能力矩阵与所有者体验层，但缺少一次**可重复验证的完成度审计**：现有 `docs/audit/` 产物多为本地生成，未在干净环境逐命令复跑；AI 主管是否真实调用工具、连续附件手册链是否真实继承前批页面、CAD 成熟度声明是否与工具能力严格一致、发布门是否验证真实工件等核心承诺缺少端到端运行证据。阶段0已锁定的真实状态（见下）表明仅有提交内 zip 工件、无 GitHub Release 与 tag，需在审计中判定其是否构成可交付形态。

## 阶段0 已锁定真实状态（当前 HEAD）
- 仓库：`qq547820639/AIPD-OS`；默认分支 `main`
- HEAD：`651dfbc76fc4b5cd3abea07a90740cedf3d0ca76`（2026-08-06 05:59:43 +0800，`docs(spec): mark v5.3 task 7 release & delivery complete`）
- 源码版本：`5.3.0`（`pyproject.toml`）；Tags：无；GitHub Releases：无（`/releases/latest` 404）
- 子模块：无；Git LFS：无；工作区：干净；跟踪文件：319
- CI：10 个 job（unit / integration / schema-validation / maturity-consistency / secret-scan / dependency-audit / license-scan / package-build / audit / skill-quality-and-coverage）
- 发布工件：`releases/5.1.0`、`5.2.0`、`5.3.0`（zip + RELEASE_MANIFEST.json + sbom + sha256 + sig），已提交但**未发布为 GitHub Release，无 tag**

## What Changes
- **阶段0 锁定**：将此环节固化为可复跑脚本，输出 `audit/repository_snapshot.json`（当前脚本在 `docs/audit/`，需确认路径与字段覆盖阶段0全部要求）。
- **阶段1 矩阵**：复核 `capability_matrix.json/md`，确保每项含声明/实现/入口/运行命令/输入/输出/依赖/单测/集成/端到端证据/限制/普通用户可用性；禁止以 README/模板/空适配器/抽象接口/TODO/模拟数据代替证据。
- **阶段2 执行循环**：审计 Execution Router 是否真实调用工具（获取下一工作包→选工具→执行→收集/校验工件→哈希→写回→stale→返工→生命周期→仅在真实决策点暂停），而非仅创建/排序/标记工作项。
- **阶段3 研究链**：审计附件接管、多源检索、全文/摘要、去重排序、标准/专利/竞品、可信度/时效、假设/事实隔离、引用、提示注入隔离、写回 Product Truth/Evidence Register；解析失败保持未验证，不虚构结论。
- **阶段4 连续附件手册链**：真实运行“规划→封面/原理/锚点→前批页面作为后批附件→分批生成→失败页局部返工→真实中文排版→语义视觉审核→PNG/PDF/ZIP”；验证图像工具真实调用、附件真实进入后批、Prompt Lineage、Anchor Registry、Visual Bible、人物/结构/模块/CMF/相机一致性、参数来自 Product Truth、禁止拼版/旧图复用/低清放大/伪文字；不以白色像素比例/熵/边缘密度/感知哈希/分辨率判定合格；以 WBX-1 手册为黄金样本。
- **阶段5 CAD 链**：全仓统一成熟度（Mesh≤C0、Faceted BREP≤C1、原生参数化 B-Rep 才进 C2、装配/标准件/连续运动进 C3、载荷强度疲劳进 C4、DFM/GD&T/公差链进 C5、模型/图纸/BOM/检验/审批一致进 C6、实体供应商/样机/DVT-PVT 闭环进 C7）；**明确 Faceted 最高只能 C1**；扫描并消除“Faceted 可达 CAD-L3”类冲突，新增 CI 一致性与证据门扫描测试；将发布门从“字段非空”升级为“真实证据门”。
- **阶段6 跨会话恢复**：审计新会话是否自动识别项目、恢复 checkpoint/Product Truth/Evidence/决策/手册附件链/CAD-BOM 修订/外部等待、不重复询问、给出恢复摘要、自动继续；检查状态服务认证/权限/多租户/加密/对象存储/迁移/并发事务/备份恢复/审计日志/retention/healthcheck/指标/密钥管理；仅 SQLite/JSON/MCP skeleton 不得判定为生产级。
- **阶段7 供应链与物理验证**：审计 Gmail/邮件适配器、RFQ 生成发送、报价解析、MOQ/模具费/单价/交期/修订、资质/材料证明、EVT/DVT/PVT 导入、CSV/XLSX/PDF 解析、失败根因/纠正包/回归、实体结果回写；严格禁止未报价/未制造/未测试/未认证/未获批准却声明完成。
- **阶段8 所有者 UX**：默认隐藏 S0–S8/C0–C7/manifest/lineage/work item/checkpoint/stale/capability ceiling 等内部术语；只展示项目摘要（目标/已完成/AI 执行中/最大风险/外部等待/下一里程碑）与单一决策卡（AI 推荐/理由/2–4 选项/成本/性能/时间/安全影响/批准后自动执行）；支持自然语言审批（批准/选A/成本降低20%/更工业化/不要医疗器械风/保留模块化/暂不进入实体制造）并自动传播到 Product Truth/手册/CAD/BOM/供应链/验证计划；评估一句话启动/恢复、首次成果时间、配置步数、不必要问题数、决策数、返工率、迭代数、错误恢复率、移动端可读性、版本差异预览、外部等待展示。
- **阶段9 Agent 行为 Evals**：用真实目标模型或可插拔 Completion 接口评测 15 项行为（不先发长问卷/只在必要决策暂停/不重复询问/先检索或显式假设/不臆造参数/附件真实继承/视觉失败只返工责任页/Faceted 不越级/未报价不伪造/未测试不声明/参数变化传播/CAD 回写手册/新会话恢复/自然语言审批/物理未完成保持 HOLD）；维护三个黄金项目（工业外骨骼/消费电子/简单机械工具），每项保存输入/模型工具版本/轨迹/工件/哈希/决策/证据/错误修复/成本/Token/耗时/验收。
- **阶段10 只修复真实缺口**：对每个缺口记录 problem/evidence/root_cause/user_impact/proposed_change/affected_files/acceptance_test/migration/rollback/priority（P0 错误声明/安全/数据丢失/无法执行；P1 全链路执行缺口；P2 UX/性能/成本；P3 生态/高级）；已完整实现且有测试证据者不重写。
- **阶段11 工程化**：核对 pyproject/src 结构/CLI/依赖锁定/类型检查/lint/format/pytest/覆盖率/结构化日志/配置/Dockerfile/docker-compose/迁移/GitHub Actions/SECURITY.md/CONTRIBUTING.md/threat model/SBOM/secret scan/dependency audit/license scan/release signing/可复现构建；所有外部网页/论文/附件/供应商文件/实验报告视为数据，不得改变安全规则/决策闸门/CAD 成熟度/发布政策/权限/敏感信息处理。

## Impact
- Affected specs：AI主管执行、理论基础与研究、连续附件产品手册、CAD与生产图纸、供应链与实体闭环、跨会话能力、所有者体验、Agent行为Evals、工程化。
- Affected code：`src/aipd_os/execution/`、`tool_adapters/`、`research/`、`imggen/`、`layout/`、`visual_audit/`、`cad/`、`supply_chain/`、`state/`、`experience/`、`evals_runner/`、`cli/`；`scripts/`（matrix/audit/skill_quality）；`.github/workflows/ci.yml`；`docs/audit/`。

## ADDED Requirements
### Requirement: 可重复验证的完成度审计
系统 SHALL 提供一次性脚本，从真实 HEAD 生成 `audit/repository_snapshot.json`，覆盖全部阶段0字段；任何分析不得使用旧聊天记录/旧 ZIP/README 声明/历史版本代替当前源码。

#### Scenario: 干净环境复跑
- **WHEN** 在全新环境克隆并执行全部安装/lint/类型检查/单测/集成/行为Evals/黄金项目/发布构建
- **THEN** 结果与本地一致，且 `audit/capability_matrix.json` 每项证据均可追溯到真实文件与运行命令。

### Requirement: CAD 成熟度一致性门
系统 SHALL 全仓统一成熟度定义，Faceted 工具链最大只可声明 C1；任何“Faceted 可达 CAD-L3”类冲突 SHALL 在 CI 中被扫描并失败。

#### Scenario: 冲突检测
- **WHEN** 仓库中存在 Faceted 能力声明超过 C1 的表述
- **THEN** CI 的成熟度一致性 job 失败并指出冲突文件。

### Requirement: 真实证据发布门
系统 SHALL 将发布门校验升级为真实证据门：文件存在、可读、Schema 合法、SHA-256 匹配、图号与修订一致、BOM 与模型一致、单位与基准完整、GD&T 覆盖关键特征、CTQ 有检验方法、审批真实、证据属于当前版本、工具能力支持声明成熟度。

#### Scenario: 无证据不通过
- **WHEN** 某能力仅声明“已实现”但无对应真实工件与证据
- **THEN** 发布门不通过，不得宣布完成。

### Requirement: Agent 行为 Evals
系统 SHALL 提供基于真实目标模型或可插拔 Completion 接口的 15 项行为评测与阈值，并维护三个可重复运行且保存完整元数据的黄金项目。

#### Scenario: 行为达标
- **WHEN** 运行 `aipd eval`，15 项行为与三个黄金项目全部达到设定阈值
- **THEN** 判定为通过并记录轨迹/成本/Token/耗时/验收。

## MODIFIED Requirements
### Requirement: 所有者体验层
在 v5.3 基础上，进一步确保默认界面完全隐藏内部术语，仅展示项目摘要与单一决策卡，并支持自然语言审批的自动传播到全部下游工件。

### Requirement: 发布交付
将提交内 zip 工件与 `audit/` 产物纳入可复现验证；判定是否需补 tag 与 GitHub Release 以构成可交付形态。

## REMOVED Requirements
### Requirement: 无
**Reason**: 本版为审计深化，不删除既有能力。
**Migration**: 不适用。

---

**最终判定选项**：`expectation_fully_met` / `expectation_substantially_met` / `expectation_partially_met` / `expectation_not_met` / `not_verifiable`。仅当阶段0可安装、一句话建项、真实工具执行工作包、自主跑到真实决策点、无缝恢复、不重复询问、手册真实继承附件并通过语义视觉审核、CAD 能力与成熟度一致、Faceted≤C1、发布门验证真实工件、声明可追溯、关键变化自动传播、未发生的物理工作绝不声明完成、CI 全过、Agent Evals 达标、三黄金项目可复现、发布包可复现、用户只在关键决策介入时才可选 `expectation_fully_met`。