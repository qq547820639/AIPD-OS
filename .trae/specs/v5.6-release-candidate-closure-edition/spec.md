# AIPD-OS v5.6 — Release Candidate 产品化收口 Spec

## Why

v5.5 已把 AIPD-OS 推进为“可靠的 Beta 编排内核”，但发布物仍存在生成物自引用、
签名仅为 MAC（不可独立验证）、CAD 原生导出含占位伪代码、无真实 Web 控制台、
外部 Provider 未真正接通等真实缺口。本迭代目标：把项目从 Beta 内核推进为
**可复现、可实际操作、对产品所有者友好、证据自洽的 Release Candidate**。

## 原则（延续用户设定）

1. README/checklist/commit message/测试名不视为实现证据。
2. mock/fake/fixture/静态示例/路径登记不得计入真实外部能力。
3. 不得为通过测试而降低断言、删失败用例、吞异常、改 skipped。
4. 无运行证据的真实外部能力保持 `external_dependency`/`HOLD`。
5. 所有能力结论必须含：声明入口、实现文件、调用路径、测试类型、运行产物、
   Provider/工具/模型版本、输入输出哈希、当前限制。
6. 全部 P0 门禁未过、审计非零差异、真实能力被 fixture 冒充前，不得声称全部实现、
   不得创建正式 RC。

## What Changes

- **P0 发布可信度**：拆分 Source Manifest / Bundle Manifest / Provenance；能力矩阵改由
  Capability Registry + 运行时探测 + 测试证据生成（废除静态判断表）；发布门禁验证
  工作区 clean、tag→SHA、零差异、机器测试报告、签名；把 HMAC 签名升级为可独立验证的
  公开密钥签名（并明确区分摘要/MAC/数字签名）。
- **P0 CAD 黄金闭环**：修复所有不可执行的原生导出/占位伪代码；`load_native_model`
  真正支持可编辑原生表示加载与恢复；建立 CadQuery/OpenCASCADE 黄金项目（参数/特征/
  改参/重生成/STEP/可编辑源导出/重载/几何校验/哈希/差异/Product Truth 写回）；
  容器 CI 真实安装并运行 CadQuery；STEP 往返实体数/面数/体积/包围盒/有效性断言；
  明确 C0–C3 成熟度定义。
- **P0 Owner Web Console**：新增 `aipd ui`，复用 StateService + 标准库 HTTP 服务，
  提供首次向导、项目总览、决策中心、制品中心、运行控制、外部等待中心；CLI/Web/JSON
  共用同一应用服务。
- **P1 Product Truth + 失效传播 + 自动返工**：结构化事实/假设/需求/CTQ/证据/决策/风险/
  版本/来源/可信度/时效；依赖与血缘图；上游变化自动标 stale 并生成有界返工任务。
- **P1 真实 Provider**：SMTP/IMAP 真实客户端 + Mailpit 容器协议集成测试；图像/视觉
  真实 Provider 客户端（凭据受控 job 运行，无凭据 HOLD + 外部任务包）；研究全文获取；
  真实模型评测（凭据门控，无调用时报告 0 样本）。
- **P2 平台化**：Provider SDK、多租户 RBAC、migration/备份/升级、结构化日志/trace/指标/
  成本预算、凭据安全存储与日志脱敏、资源限制/并发/取消/断点恢复。
- **端到端**：三个黄金项目（连续附件手册 / 参数化 CAD 工程变更 / RFQ-报价-实验-纠正）。
- **最终交付**：真实代码、测试、最新矩阵、审计、Manifest/Provenance、黄金产物、
  UX 测试报告、升级指南、CHANGELOG/Release Notes、完成度报告（fully/partially/external/
  not_implemented/not_verifiable）。

## Impact

- 受影响能力：发布可信度、CAD、Owner UX、状态/恢复、供应链、研究、Evals、平台化。
- 受影响代码：`scripts/`（sign_release/regenerate_release_manifest/capability_matrix/
  production_release_gate/audit_repo）、`src/aipd_os/cad/`、`src/aipd_os/imggen/`、
  `src/aipd_os/supply_chain/mail.py`、`src/aipd_os/experience/`、`src/aipd_os/visual_audit/`、
  `src/aipd_os/config.py`、`src/aipd_os/state/`、`src/aipd_os/cli/`、`.github/workflows/ci.yml`、
  `Dockerfile`、`docs/`。

## ADDED Requirements

### Requirement: 发布证据体系（Source / Bundle / Provenance）

系统 SHALL 将“源代码清单”与“发布包清单”分离：
- Source Manifest 只覆盖确定的源文件集合，不包含会在生成后改变自身的文件；
- Bundle Manifest 对最终压缩包内容计算哈希；
- Provenance 记录 source commit、构建环境、构建时间、依赖锁定、测试报告与 bundle hash。
所有发布证据 SHALL 指向最终 tag SHA，而非父提交。

#### Scenario: 干净复现
- **WHEN** 在干净 clone 与解压后的发布包中分别运行 `aipd audit`
- **THEN** 两者结果一致，且报告记录的 HEAD 等于最终 tag SHA。

### Requirement: Capability Registry 驱动的能力矩阵

系统 SHALL 从统一 Capability Registry、运行时探测和测试证据生成能力矩阵，
禁止维护一份与代码脱节的静态判断表。矩阵 SHALL 通过 schema 校验、实现文件存在性校验、
入口可调用校验和证据时效校验。

#### Scenario: 修改被保护文件
- **WHEN** 修改任意被保护文件后运行 release-ready 门禁
- **THEN** `release-ready` 必须失败；不得通过忽略生成文件错误来达到零差异。

### Requirement: 可独立验证的发布签名

系统 SHALL 提供公开密钥签名（或等价可独立验证机制），并明确区分摘要、MAC 与数字签名。

### Requirement: CAD 黄金闭环

`CadQueryBackend` SHALL 支持：加载可编辑原生表示、列出/编辑参数、重新生成、STEP 导出、
可编辑源文件导出、重载、几何有效性检查、产物哈希与工具版本、修改前后差异、Product Truth
写回。所有不可执行的原生导出脚本、省略循环、`pass`、伪代码、占位导出必须被修复或移除。
容器 CI SHALL 真实安装并运行 CadQuery/OpenCASCADE，不得仅 mock import。

#### Scenario: 黄金项目
- **WHEN** 运行 CadQuery 黄金项目（多参数 + 孔/圆角/倒角）
- **THEN** 参数修改→重新生成→STEP 导出→可编辑源导出→重载→有效性检查→差异→写回全部成功，
  并断言实体数、面数、体积、包围盒与几何有效性。

### Requirement: Owner Web Console（`aipd ui`）

系统 SHALL 提供 `aipd ui` 本地命令，复用 StateService + 标准库 HTTP 服务，包含首次向导、
项目总览、决策中心、制品中心、运行控制、外部等待中心。默认不暴露内部 ID。适配窄屏、
支持键盘操作、基础无障碍与中英文一致。CLI/Web/JSON SHALL 使用同一应用服务。

### Requirement: Product Truth 模型与失效传播

系统 SHALL 建立结构化 Product Truth（事实/假设/需求/CTQ/证据/决策/风险/制品版本/来源/
可信度/生效与过期时间），维护依赖与血缘图。上游事实变化后 SHALL 自动计算下游受影响项、
标记 stale、生成有次数上限的返工任务；返工产生新版本、执行验证、成功后关闭 stale。
系统 SHALL 防止循环依赖、返工风暴与无限重试。

### Requirement: 真实邮件 Provider（SMTP/IMAP）

系统 SHALL 提供真实 SMTP 发送与 IMAP 收件/线程关联/附件下载/幂等同步，且在 host 已配置时
不得直接抛 external_dependency。SHALL 使用 Mailpit/GreenMail 容器完成真实协议集成测试，
覆盖 TLS、认证失败、超时、退避、重复发送、附件过大与字符编码。发信 SHALL 经显式人工批准
并保留审计。

### Requirement: 真实图像/视觉 Provider（凭据门控）

系统 SHALL 提供真实图像 Provider 客户端（OpenAI-compatible / ComfyUI 或等价协议），
真实发送请求并解析图像字节；后一批以真实图像作为附件/条件。SHALL 提供失败页单页重建，
并证明未修改页面哈希不变。无凭据时输出外部任务包并 HOLD；有凭据的受控 job 中运行真实
端到端测试。视觉审核 SHALL 提供真实多模态审查客户端。

## MODIFIED Requirements

### Requirement: 能力矩阵生成（MODIFIED）
从静态表改为 Capability Registry 驱动，并附加四类校验（schema/存在性/可调用/时效）。

### Requirement: 发布签名（MODIFIED）
从 HMAC-MAC 升级为公开密钥签名，并区分摘要/MAC/数字签名。

### Requirement: CAD 成熟度定义（MODIFIED）
明确 C0/C1/C2/C3 定义；ContractBackend 仅作降级后端，不得统计为真实 C2；
二维图纸/装配/运动/CAE/DFM/GD&T 无真实能力时保持 external_dependency/partially。

## REMOVED Requirements

### Requirement: 静态能力矩阵表
**Reason**: 与代码脱节、易过期、无法自证时效。
**Migration**: 由 Capability Registry + 运行时探测 + 测试证据自动生成。

### Requirement: HMAC 发布签名作为唯一签名机制
**Reason**: MAC 不可由第三方独立验证，不满足发布可信度要求。
**Migration**: 升级为公开密钥签名，HMAC 仅作内部完整性校验（明确标注为 MAC）。