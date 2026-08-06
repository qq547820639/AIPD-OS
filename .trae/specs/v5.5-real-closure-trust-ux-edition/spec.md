# AIPD-OS v5.5「真实闭环、发布可信度与用户体验收口版」Spec

## Why
v5.4 通过审计确认了 70 项能力（44 fully / 15 partial / 11 external），但存在真实可信度缺口：CI 的 Integration job 空转（0 测试）、RELEASE_MANIFEST 哈希与最终代码不同步、VisualAuditor 视觉待审仍可能 passed、fake provider 的 17/17 被误读为真实模型通过率、版本在多处未统一。这些缺口直接损害“可复现、可信、可发布”的承诺。本轮 v5.5 只做真实代码、真实测试、真实 CI 修复，并诚实保留所有外部依赖为 external_dependency/HOLD。

## What Changes
- **P0-1 修复 CI 与发布可信度**：修 RELEASE_MANIFEST 生成时序（最终代码提交后再生成）；Integration job 接入真实集成测试（不再空转）；升级 Actions 版本消除 Node20 弃用；发布门要求全部必要 job 成功。
- **P0-2 统一版本与文档**：全仓版本统一为 5.5.0；新增 `aipd doctor`、`aipd version --verbose`、Git tag/Release 流程；修复 QUICKSTART 失效命令；提供 5 分钟入门。
- **P0-3 修复手册视觉验收漏洞**：修正 VisualAuditor 布尔逻辑（`requiring_vision=true` → 顶层 HOLD/not_verified，绝不 passed）；将 VisualAuditor 与 GoldenGapEvaluator 接入 manual release gate；补回归测试。
- **P0-4 最终 HEAD 审计**：全部修改后重新生成 snapshot / matrix / manifest / SBOM / eval / release，记录最终 HEAD，工作区 clean，逐文件哈希一致。
- **P1 真实业务闭环**：Execution Router 进度/心跳/超时/取消/checkpoint/恢复/成本/token/写回；研究链真实摄取与净化；可替换 Image Generation Provider 接口（前批字节进入后批）；CAD C2 适配器契约（真实内核缺失时标记 external_dependency）；跨会话恢复；可插拔邮件连接器；Evals 重构（fake 只作 contract-test，不汇入模型通过率）。
- **P2 所有者 UX**：自然语言操作闭环、统一 Dashboard/CLI 输出、首次使用引导。

## Impact
- Affected specs/capabilities：supervisor.execution_router、research.*、manual.*、cad.*、state.*、supply_chain.*、experience.*、evals.*。
- Affected code：`src/aipd_os/`（execution/、research/、imaging/、cad/、state/、supply_chain/、experience/、evals_runner/、visual_audit/、cli/）、`scripts/`、`.github/workflows/ci.yml`、`pyproject.toml`、`README.md`、`CHANGELOG.md`、`QUICKSTART.md`、`SKILL.md`、`RELEASE_MANIFEST.json`。

## 诚实边界（最高原则）
- 无真实外部服务/凭据/物理测试/人工批准时，一律 external_dependency / external_pending / blocked_external / HOLD / not_verified，绝不伪造成功。
- fake provider 仅命名 contract-test / deterministic-fixture，其 17/17 不得描述为真实模型通过率。
- Faceted STEP 永远 ≤ C1；原生可编辑参数化 B-Rep 需真实内核（如 CadQuery）才可标 C2。
- 不通过降断言/删测试/放宽门禁/allow-failure 换取绿色 CI。

## ADDED Requirements
### Requirement: P0-1 发布门与 CI 可信度
系统 SHALL 在最终代码提交后重新生成 RELEASE_MANIFEST.json，确保逐文件 SHA-256 与磁盘一致；CI Integration job 必须运行真实集成测试（不得空转）；所有 Actions job 必须绿色；发布物仅在必要 job 全部成功后生成。

#### Scenario: 干净 clone 后 CI 全绿
- **WHEN** 从 origin/main 干净 clone 并推送到 CI
- **THEN** unit/integration/schema/maturity/secret/dependency/license/package/audit/skill 全部通过，且 RELEASE_MANIFEST 哈希与磁盘一致

### Requirement: P0-2 版本统一与 CLI 工具
系统 SHALL 在 pyproject、包版本、README、CHANGELOG、QUICKSTART、SKILL、RELEASE_MANIFEST、SBOM、eval report、release package、capability matrix、repository snapshot 中统一为同一版本；提供 `aipd doctor`、`aipd version --verbose`。

#### Scenario: 版本一致性检查
- **WHEN** 用户运行 `aipd version --verbose` 与 `aipd doctor`
- **THEN** 输出包版本、Git HEAD、构建时间、矩阵版本、发布清单哈希，并报告外部能力就绪状态

### Requirement: P0-3 视觉验收门
系统 SHALL 在 `requiring_vision=true`（无视觉后端）时返回顶层 HOLD/not_verified，绝不返回 passed；VisualAuditor 与 GoldenGapEvaluator 必须接入 manual release gate。

#### Scenario: 无视觉后端不通过
- **WHEN** 视觉后端缺失且页面存在视觉待审维度
- **THEN** 手册发布门判定 not_verified/HOLD 并给出原因，绝不 passed

### Requirement: P1 Evals 诚实报告
系统 SHALL 将 fake provider 命名为 contract-test/deterministic-fixture，其结果不得汇入“模型行为通过率”；报告必须区分 provider/endpoint/model/model version/是否真实网络调用/prompt hash/token/cost/latency/retry/grader/trace。

#### Scenario: 报告区分 fake 与真实模型
- **WHEN** 以 fake provider 运行 eval
- **THEN** 报告明确标注 deterministic-fixture，且不显示为真实模型通过率

## MODIFIED Requirements
### Requirement: Execution Router 真实执行
在保留现有路由与幂等/重试/降级基础上，补充真实进度事件、心跳、执行超时、用户取消、可恢复 checkpoint、in-flight 中断恢复、duration/token/cost/工具调用记录、产物存在性/格式/哈希/语义验证、写回 Product Truth 与 Evidence Register、stale 影响传播、有界自动返工状态机、防无限循环与重复生成、失败时面向普通用户的明确说明。

### Requirement: 研究链
在现有检索/证据接口基础上，补齐真实附件摄取与净化、摘要/全文区分、可获取时下载解析全文、标准法规/专利/竞品检索接口契约、统一引用、来源/时间/可信度/假设/冲突管理、写回 Product Truth 与 Evidence Register、证据过期自动标记、检索失败保持 not_verified。

### Requirement: 连续附件手册链
在现有批处理基础上，实现可替换 Image Generation Provider 接口：前批页面以真实图片字节/后端文件对象传入下一批（非路径字符串）；记录请求 ID/模型版本/种子/提示词/附件哈希/生成参数/成本/耗时/返回工件哈希；建立 Anchor Registry 与 Visual Bible；正文来自 Product Truth 与内容模型；支持只重建责任页；无后端时生成外部任务包并 HOLD。

### Requirement: CAD 能力按成熟度
C0/C1 保持 faceted 实现（≤C1）；C2 及以上需真实可编辑 B-Rep 内核（如 CadQuery），未安装时标记 external_dependency，绝不越级。实现 CAD 变更到规格/BOM/手册/验证计划的回写链路。

### Requirement: 跨会话恢复
手册批次、附件、Visual Bible、生成任务、返工计划移入统一状态服务/对象存储；DB、对象存储、附件索引一起备份恢复；恢复摘要含 Product Truth/Evidence/未解决决策/已解决决策/CAD-BOM 修订/附件链/外部等待/失败任务/下一步；多项目按最近活动/显式上下文识别；恢复后自动继续安全工作；不可逆/安全/成本/发布决策仍需显式批准。

### Requirement: 供应链与物理验证
实现可插拔邮件连接器（SMTP/IMAP 契约 + 本地测试服务）：RFQ 草稿/显式批准/发送/Message-ID 线程追踪/收件箱读取/供应商回复关联/附件下载/幂等/重试。补齐 CSV/JSON/XLSX/PDF 报价解析、供应商/报价/资质/认证持久化、证书过期提醒、EVT/DVT/PVT 导入、失败根因/纠正/回归、物理结果写回。真实报价/制造/测试/认证缺失时保持 HOLD。

### Requirement: 所有者 UX
自然语言指令→意图解析→影响分析→受影响制品→预计成本/时间→可撤销预览→批准→自动返工→自动验收→更新摘要；支持同义词/上下文指代/多条件/纠错，无法确定时只问一个最关键问题。CLI/Dashboard 默认只展示目标/执行/完成/缺口/风险/外部等待/唯一决策/里程碑/变化/可撤销操作，内部标识隐藏；提供 `--json` 与 human 分离、紧凑移动端输出、进度事件、失败恢复命令、制品差异、成本耗时变化、无障碍与窄屏测试。

## REMOVED Requirements
无删除；仅将“fake 结果作为模型通过率”的表述从发布口径中移除（改为 contract-test 语义）。

**Migration**：eval 报告新增 provider 分类字段；旧消费方需按 provider 过滤“模型行为通过率”。