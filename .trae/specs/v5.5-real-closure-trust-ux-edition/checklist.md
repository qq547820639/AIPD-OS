# Checklist — AIPD-OS v5.5 真实闭环、发布可信度与用户体验收口版

## P0-1 CI 与发布可信度
- [ ] RELEASE_MANIFEST.json 在最终代码提交后生成，逐文件 SHA-256 与磁盘一致（`tests/test_packaging.py` 通过）。
- [ ] CI Integration job 运行真实集成测试，非空转；新增 `integration` 标记测试。
- [ ] Actions 版本已升级，无 Node 20 弃用警告。
- [ ] 发布门：仅必要 job 全部成功才生成正式发布物；依赖 CVE 已升级/替换或记录 CVE+范围+缓解+复审日期。
- [ ] 干净 clone 后各 CI job 本地等价复现全绿。

## P0-2 版本统一与文档
- [ ] 全仓版本统一为 5.5.0（pyproject/包/README/CHANGELOG/QUICKSTART/SKILL/RELEASE_MANIFEST/SBOM/eval/matrix/snapshot）。
- [ ] `aipd doctor` 与 `aipd version --verbose` 已实现并输出正确。
- [ ] QUICKSTART 失效命令/版本已修复，示例命令在干净环境实际运行。
- [ ] Git tag 与 GitHub Release 流程就绪；5 分钟真实入门项目可行。

## P0-3 手册视觉验收
- [ ] `requiring_vision=true` 时顶层 HOLD/not_verified，绝不 passed。
- [ ] VisualAuditor 与 GoldenGapEvaluator 已接入 manual release gate。
- [ ] 手册门校验页面结构/参数真实性/中文/结构/人物/模块/CMF/相机/光线/禁止旧图拼版/黄金样本差异。
- [ ] 回归测试断言视觉后端缺失时不能通过。

## P1-1 Execution Router
- [x] 进度事件/心跳/超时/取消/checkpoint/in-flight 恢复已实现。
- [x] duration/token/cost/工具调用记录；产物存在性/格式/哈希/语义验证；写回 Product Truth/Evidence。
- [x] stale 影响传播；有界自动返工状态机；防无限循环/重复生成。
- [x] 失败说明面向普通用户；能力地板校验真实 maturity ceiling。

## P1-2 研究链
- [ ] 附件摄取与净化；摘要/全文区分；可获取时下载解析全文。
- [ ] 标准法规/专利/竞品检索接口契约+本地测试；统一引用；可信度/时效/假设/冲突管理。
- [ ] 写回 Product Truth/Evidence；证据过期标记；检索失败保持 not_verified。

## P1-3 连续附件手册链
- [x] 可替换 ImageGen Provider 接口；前批以真实图片字节/文件对象传入后批（非路径字符串）。（`providers.py`）
- [x] 记录请求 ID/模型版本/种子/提示词/附件哈希/生成参数/成本/耗时/返回工件哈希；Anchor Registry 与 Visual Bible。（`providers.py`/`registry.py`）
- [x] 正文来自 Product Truth/内容模型；只重建责任页；仅重跑受影响页与门；前后差异预览。（`manual_chain.py`）
- [x] 无后端时生成外部任务包并 HOLD；端到端测试证明第二批接收第一批图片内容。（`tests/test_imggen_chain.py` 11 项通过）

## P1-4 CAD 成熟度
- [ ] C0/C1 faceted ≤ C1；可替换 CAD 后端适配器契约+本地测试。
- [ ] C2 真实可编辑参数化 B-Rep（真实内核可选）；未安装时标 external_dependency，不越级。
- [ ] C3–C7 到真实证据才标 fully；未实现标 external_dependency/not_implemented。
- [ ] CAD 变更到规格/BOM/手册/验证计划回写链路；maturity-consistency 通过。

## P1-5 跨会话恢复
- [ ] 批次/附件/Visual Bible/生成任务/返工计划入状态服务/对象存储；三者一起备份恢复。
- [ ] 恢复摘要含全部必需项；多项目按最近活动识别。
- [ ] 恢复后自动继续安全工作；不可逆/安全/成本/发布决策需显式批准；崩溃-重启-恢复-继续测试通过。

## P1-6 供应链与物理验证
- [x] 可插拔邮件连接器（SMTP/IMAP 契约+本地测试）；RFQ 草稿/批准/发送/Message-ID/收件箱读取/回复关联/附件下载/幂等/重试。（`src/aipd_os/supply_chain/mail.py`，测试 test_mail_*）
- [x] CSV/JSON/XLSX/PDF 报价解析；供应商/报价/资质/认证持久化；证书过期提醒；EVT/DVT/PVT 导入；失败根因/纠正/回归；写回。（quotes.py / persistence.py / certification.py / stages.py / writeback.py）
- [x] 真实报价/制造/测试/认证缺失时状态保持 HOLD/not_verified。（test_no_official_quote_and_no_executed_lab_not_passed / test_writeback_physical_missing_keeps_hold / test_lab_report_pdf_external_blocked）

## P1-7 Evals 重构
- [ ] fake provider 改名 contract-test/deterministic-fixture；不汇入模型行为通过率。
- [ ] 报告区分 provider/endpoint/model/model version/是否真实网络调用/prompt hash/token/cost/latency/retry/grader/trace。
- [ ] 真实模型 smoke job（有凭据）；无凭据标 external/skipped。
- [ ] 结构化输出/状态/工件/DB/judge 评分；验证真实副作用；重复试验/稳定性/回归/失败轨迹；fake 17/17 不标真实模型通过率。

## P2 所有者 UX
- [x] 自然语言操作闭环（意图→影响→制品→成本时间→预览→批准→返工→验收→摘要）；同义词/指代/多条件/纠错；只问一个关键问题。（`tests/test_owner_ux.py`）
- [x] CLI/Dashboard 默认只展示面向所有者的摘要，内部标识隐藏；`--json`/human 分离；紧凑移动端；进度事件；可取消；失败恢复；制品差异；成本耗时；无障碍/窄屏测试。
- [x] 首次使用引导：一句话建项→首结果→能力与外部配置→引导 Provider→示例项目→恢复/重置→CI 运行示例命令。

## P0-4 最终 HEAD 审计与发布
- [ ] 最终代码提交后重新生成 snapshot/matrix/manifest/SBOM/eval/release；记录最终 HEAD；工作区 clean；哈希一致。
- [ ] 全量 pytest/集成/Schema/成熟度/secret/pip-audit/license/package/version-truth 全绿。
- [ ] Git tag v5.5.0 与（可行时）GitHub Release；签名/哈希/SBOM 齐全。
- [ ] 输出最终发布判断 READY/CONDITIONAL/HOLD 及证据。