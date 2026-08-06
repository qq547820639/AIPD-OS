# Tasks — AIPD-OS v5.6 Release Candidate 产品化收口版

> 原则：只做真实代码/测试/CI 修复；外部依赖诚实标 external_dependency/HOLD；fake 只作 contract-test；最终判定依据证据。
> 收尾：全部任务完成后，在最终 tag HEAD 上重新生成 Source/Bundle/Provenance、capability matrix、audit、签名，运行全量与 CI 等价检查，提交并推送 origin/main，打 tag。

## Task 1: P0-1 发布证据体系重构（Source/Bundle/Provenance + Registry 矩阵 + 签名）
- [x] 拆分 `Source Manifest`（只覆盖确定源文件，不含会自变的清单自身）与 `Bundle Manifest`（对最终压缩包内容哈希）；新增 `Provenance`（source commit / 构建环境 / 构建时间 / 依赖锁定 / 测试报告 / bundle hash）。
- [x] Capability Matrix 改由统一 `Capability Registry` + 运行时探测 + 测试证据生成，废除静态判断表；附加 schema / 实现文件存在性 / 入口可调用 / 证据时效四类校验。
- [x] 升级签名：新增公开密钥签名（RSA/Ed25519 或 Sigstore 等价），明确区分摘要 / MAC(HMAC，仅内部完整性) / 数字签名；`sign_release.py` 支持 `--keygen/--sign/--verify`。
- [x] release-ready 门禁增加：工作区 clean、tag→SHA 指向被测试提交、Source/Bundle 零差异、测试数字来自机器报告、签名可验证；修改任意被保护文件后必须失败。
- [x] 修正文档版本跳跃、旧标题、旧 SHA、旧命令与测试数字不一致；`aipd audit` 在干净 clone 与解压包中复现一致。
- 验证：hash_mismatch_count=0；所有报告 HEAD=最终 tag SHA；clean clone 与包复验一致；篡改被保护文件→release-ready 失败。

## Task 2: P0-2 CAD 黄金闭环（真实 CadQuery 内核）
- [x] 修复 `CadQueryBackend.export_native` 的伪代码/`pass`/占位，产出真实可执行、可重载的可编辑原生源文件。
- [x] `load_native_model` 真正加载并恢复可编辑原生表示（含特征/参数），而非仅读 JSON 重建默认示例。
- [x] 建立 CadQuery/OpenCASCADE 黄金项目：多参数 + 孔/圆角/倒角 → 改参 → 重生成 → STEP 导出 → 可编辑源导出 → 重载 → 几何有效性 → 产物哈希/工具版本 → 修改前后差异 → Product Truth 写回。
- [x] 容器 CI 真实安装并运行 CadQuery/OpenCASCADE（Dockerfile/ci.yml），不得仅 mock import；STEP 往返断言实体数/面数/体积/包围盒/有效性。
- [x] 明确 C0/C1/C2/C3 成熟度定义；ContractBackend 仅作降级后端，不得统计为真实 C2；二维图纸/装配/运动/CAE/DFM/GD&T 无真实能力保持 external_dependency/partially。
- 验证：`tests/test_cad_golden_loop.py`（真实内核时运行）通过；无内核时 C2 标 external_dependency 不越级。

## Task 3: P0-3 Owner Web Console（`aipd ui`）
- [x] 新增 `aipd ui`（复用 StateService + 标准库 HTTP 服务），提供首次向导（建项/导入、环境检测、Provider 配置、一键修复、凭据步骤）、项目总览、决策中心（默认一个真决策、AI 推荐/备选/影响/证据/批准动作、不暴露内部 ID）、制品中心（PNG/PDF/表格/文本预览、CAD 缩略、before/after、版本历史、下载/批准/退回/局部返工）、运行控制（实时进度/心跳/暂停/取消/恢复/重试/可理解失败原因）、外部等待中心。
- [x] 窄屏适配、键盘操作、基础无障碍、中英文术语一致；CLI/Web/JSON 共用同一应用服务（不搞三套业务逻辑）。
- [x] 首次向导 Provider 配置：config.py 增加 model/image/vision/CAD/mail 配置项并在向导中引导。
- 验证：`tests/test_owner_web_console.py` 通过（各中心端点、只读不暴露内部 ID、窄屏/键盘/无障碍断言）；`aipd ui` 可启动并完成核心任务。

## Task 4: P1-1 Product Truth + 失效传播 + 自动返工
- [x] 结构化 Product Truth 数据模型（事实/假设/需求/CTQ/证据/决策/风险/制品版本/来源/可信度/生效与过期时间），不写进 steps_log 字符串。
- [x] 显式依赖图与血缘图；上游事实变化自动计算下游受影响项，标 stale，生成有次数上限的返工任务；返工产生新版本、执行验证、成功后关闭 stale。
- [x] 防循环依赖/返工风暴/无限重试；Owner 能看到“改了什么/为何影响这些/系统如何修复/需批准什么”。
- 验证：`tests/test_product_truth_propagation.py` 通过（上游变化→stale→有界返工→关闭）。

## Task 5: P1-2 真实邮件 Provider（SMTP/IMAP + Mailpit）
- [x] 真实 SMTP 发送与 IMAP 收件/线程关联/附件下载/幂等同步；host 已配置时不得直接抛 external_dependency。
- [x] Mailpit（或 GreenMail）容器真实协议集成测试：TLS/认证失败/超时/退避/重复发送/附件过大/字符编码。
- [x] 发信经显式人工批准并保留审计；真实回信/报价附件/供应商资质/证书写入统一状态服务。
- 验证：`tests/test_mail_protocol.py`（integration，Mailpit 容器）通过；无容器时对外部依赖诚实标注。

## Task 6: P1-3 真实图像/视觉 Provider（凭据门控）
- [x] 真实图像 Provider 客户端（OpenAI-compatible/ComfyUI 等价协议）：真实请求与解析图像字节；后一批以真实图像作为附件/条件。
- [x] 失败页单页重建入口，只重跑失败页并证明未修改页面哈希不变；Anchor Registry / Visual Bible 可机器比较特征。
- [x] 真实多模态视觉审核 Provider 客户端；无凭据时输出完整外部任务包并 HOLD；有凭据的受控 job 运行真实端到端测试。
- 验证：`tests/test_imggen_real_provider.py`（凭据门控，无凭据断言 HOLD 与外部任务包）通过；PIL 仅作 contract-test 不冒充真实文生图。

## Task 7: P1-4 研究与真实模型评测（凭据门控）
- [x] 区分 metadata/abstract/full text/OCR/引用片段；合法来源全文获取/解析/缓存/去重/版权边界；每条结论绑定来源/段落/获取时间/适用范围/过期策略。
- [x] 真实模型评测记录 provider/model version/网络调用/token/费用/延迟/重试/trace；fixture/contract 永不进入真实通过率；无调用时报告 0 样本。
- [x] 配置有预算上限与凭据保护的手动/定时真实评测 job。
- 验证：`tests/test_research_fulltext.py`、`tests/test_model_evals_honesty.py` 通过；无凭据时样本数=0。

## Task 8: P2 平台化与长期质量
- [x] Provider SDK、能力声明 schema、兼容性测试套件与示例插件；多租户/角色权限/审批权限/敏感信息隔离。
- [x] DB migration/备份恢复兼容测试/版本升级指南；结构化日志/trace/指标/成本预算/可选匿名遥测。
- [x] 长任务资源限制/并发控制/取消传播/断点恢复压力测试；安全凭据存储与日志脱敏（复用 masking）；性能/包体积/启动耗时预算。
- [x] 清理旧版本生成物、重复实现、过期规范与不可达代码。
- 验证：`tests/test_platform_quality.py` 通过；`aipd doctor` 报告凭据保护与脱敏状态。

## Task 9: E2E 三个黄金项目 + 强制验收
- [x] 黄金项目 A（连续附件产品手册）、B（参数化 CAD 工程变更）、C（RFQ-报价-实验-纠正），各从一句自然语言需求开始，经真实状态写回/恢复/决策/制品生成/发布检查。
- [x] 验收证明：干净安装可运行；中断可恢复；上游参数变化触发正确 stale/返工；未配置外部能力不假成功；已配置本地真实内核/协议服务被真正调用；制品有哈希/来源/版本/证据；用户默认看不到内部代号；发布报告与最终 tag 一致。
- 验证：`tests/test_golden_projects_e2e.py` 通过（3 passed）；产出三个黄金项目真实运行产物（`releases/golden-projects/`）。

## Task 10: P0-4 最终 HEAD 审计、发布与交付
- [x] 在最终代码提交后重新生成 Source/Bundle/Provenance、capability matrix、audit、签名、release package；记录最终 tag SHA；工作区 clean；逐文件哈希一致；`aipd audit` 在 clone 与包中复现一致。
- [x] 运行全量 pytest/集成/CAD 真实内核/协议/端到端/secret/pip-audit/license/version-truth 全绿。
- [x] 打 Git tag v5.6.0 并创建（候选）Release；输出签名/哈希/Provenance；升级与迁移指南、CHANGELOG/Release Notes、UX 测试报告、完成度报告（fully/partially/external/not_implemented/not_verifiable）。
- [x] 输出最终发布判断 READY/CONDITIONAL/HOLD 及证据；未全过 P0 门禁不得声称“全部实现”。
- 验证：最终 tag SHA 上所有检查全绿；manifest 哈希与磁盘一致；洁净复现一致；工作区 clean；提交并推送 origin/main，tag 指向最终 HEAD。

# Task Dependencies
- Task 1（P0-1）与 Task 2（P0-2）独立可并行。
- Task 3（P0-3 Web Console）依赖 Task 1 的 Registry（供向导能力展示）与现有 StateService；可并行。
- Task 4（P1-1）独立；Task 6 依赖 Task 4 的 Product Truth 写回。
- Task 5/6/7（P1 真实 Provider）相互独立，可并行；均凭据/容器门控。
- Task 8（P2）部分独立，依赖 Task 1 元能力。
- Task 9（E2E）依赖 Task 2/4/5/6。
- Task 10（P0-4）依赖全部前序任务，最后执行。