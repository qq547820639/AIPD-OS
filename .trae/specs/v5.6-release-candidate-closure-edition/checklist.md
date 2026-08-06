# Checklist — AIPD-OS v5.6 Release Candidate 产品化收口版

## P0-1 发布证据体系
- [x] Source Manifest 与 Bundle Manifest 分离；Provenance 记录 source commit/构建环境/时间/依赖锁定/测试报告/bundle hash。
- [x] Capability Matrix 由 Capability Registry + 运行时探测 + 测试证据生成，非静态表；通过 schema/存在性/可调用/时效校验。
- [x] 公开密钥签名可用，明确区分摘要/MAC/数字签名；`sign_release.py` 支持 keygen/sign/verify。
- [x] release-ready 门禁：工作区 clean、tag→SHA、Source/Bundle 零差异、机器测试数字、签名可验证；篡改被保护文件→失败。
- [x] `aipd audit` 在干净 clone 与解压包中复现一致；hash_mismatch_count=0；所有报告 HEAD=最终 tag SHA。

## P0-2 CAD 黄金闭环
- [x] `CadQueryBackend.export_native` 无伪代码/pass/占位，产出真实可执行可重载源文件。
- [x] `load_native_model` 真正加载并恢复可编辑原生表示。
- [x] CadQuery 黄金项目全链路通过（参数/特征/改参/重生成/STEP/源导出/重载/几何校验/哈希/差异/写回）。
- [x] 容器 CI 真实安装运行 CadQuery/OpenCASCADE；STEP 往返断言实体数/面数/体积/包围盒/有效性。
- [x] C0–C3 成熟度定义明确；ContractBackend 不统计为真实 C2；无真实能力保持 external_dependency/partially。

## P0-3 Owner Web Console
- [x] `aipd ui` 提供首次向导/项目总览/决策中心/制品中心/运行控制/外部等待中心。
- [x] 窄屏适配、键盘操作、基础无障碍、中英文一致；默认不暴露内部 ID。
- [x] CLI/Web/JSON 共用同一应用服务；config.py 支持 model/image/vision/CAD/mail Provider 配置。

## P1-1 Product Truth 与失效传播
- [x] 结构化 Product Truth 模型（含来源/可信度/时效），非 steps_log 字符串。
- [x] 依赖图/血缘图；上游变化→stale→有界返工→新版本→验证→关闭 stale；防循环/风暴/无限重试。

## P1-2 真实邮件 Provider
- [x] 真实 SMTP 发送与 IMAP 收件/线程/附件/幂等同步；host 已配置不抛 external_dependency。
- [x] Mailpit/GreenMail 容器协议集成测试（TLS/认证失败/超时/退避/重复/附件过大/编码）。
- [x] 发信显式人工批准 + 审计；回信/报价/资质/证书写入状态服务。

## P1-3 真实图像/视觉 Provider
- [x] 真实图像 Provider 客户端真实请求并解析字节；后批以真实图像作附件/条件。
- [x] 失败页单页重建，未修改页哈希不变；Anchor/Visual Bible 可机器比较。
- [x] 真实多模态视觉审核客户端；无凭据输出外部任务包并 HOLD；凭据受控 job 跑真实端到端。

## P1-4 研究与真实模型评测
- [x] 全文获取/解析/缓存/去重/版权边界；结论绑定来源/段落/时间/适用范围/过期策略。
- [x] 真实评测记录 provider/model/网络/token/费用/延迟/重试/trace；fixture 不进真实通过率；无调用时样本数=0。
- [x] 预算上限与凭据保护的手动/定时评测 job。

## P2 平台化
- [x] Provider SDK、能力声明 schema、兼容测试、示例插件；多租户/RBAC/审批/敏感信息隔离。
- [x] migration/备份恢复兼容测试/升级指南；结构化日志/trace/指标/成本预算/可选匿名遥测。
- [x] 资源限制/并发/取消/断点恢复压力测试；凭据安全存储与日志脱敏；性能/包体积/启动预算。
- [x] 清理旧生成物、重复实现、过期规范、不可达代码。

## E2E 黄金项目
- [x] 三个黄金项目（手册 / CAD 工程变更 / RFQ-报价-实验-纠正）从一句需求到发布检查真实跑通。
- [x] 干净安装可运行；中断可恢复；上游变化触发正确 stale/返工；未配置外部能力不假成功；已配置本地内核/协议被真正调用；制品有哈希/来源/版本/证据；用户默认看不到内部代号；发布报告与最终 tag 一致。

## P0-4 最终审计与交付
- [x] 最终 tag SHA 上重新生成 Source/Bundle/Provenance/矩阵/audit/签名/包；工作区 clean；逐文件哈希一致；clone 与包复验一致。
- [x] 全量测试/集成/CAD 真实内核/协议/端到端/secret/pip-audit/license/version-truth 全绿。
- [x] tag v5.6.0（候选 Release）+ 签名/哈希/Provenance；升级迁移指南、CHANGELOG/Release Notes、UX 测试报告、完成度报告。
- [x] 输出最终发布判断 READY/CONDITIONAL/HOLD 及证据；未全过 P0 门禁不声称“全部实现”；提交并推送 origin/main。