# Tasks — AIPD-OS v5.4 可重复验证完成度审计与产品化深化版

> 目标：对真实 HEAD 做可重复验证的完成度审计，只修复真实缺口，深化产品化与所有者 UX；不重写已完整实现且有测试证据的能力。
> 收尾：全部任务完成后运行 `tests/` 全部测试、`aipd eval`、构建签名发布包，生成/刷新 `audit/` 产物，提交并推送 `origin/main`。

## Task 1: 阶段0 与 阶段1 —— 锁定真实版本 + 声明—实现—测试—证据矩阵
- [x] 复核并固化阶段0：确认 `scripts/` 生成的 `audit/repository_snapshot.json` 覆盖阶段0全部字段（仓库名/默认分支/HEAD SHA/提交时间/提交信息/版本/Tags/Release/文件树/子模块/LFS/CI 状态/工件+SHA-256/工作区干净）；复核 `docs/audit/capability_matrix.json|md` 每项的声明/实现/入口/运行命令/输入/输出/依赖/单测/集成/端到端证据/限制/普通用户可用性。
- 输入：真实 HEAD `651dfbc7`、`docs/audit/` 现有产物。
- 输出：刷新后的 `audit/repository_snapshot.json`、`capability_matrix.json`、`capability_matrix.md`。
- 验证：`tests/test_audit_repo.py`、`tests/test_capability_matrix.py` 通过；矩阵无“仅 README/模板/空适配器/TODO/模拟数据”当作证据。

## Task 2: 阶段2 —— 审计 AI 主管是否真实执行工作
- [x] 审计 Execution Router 是否真实调用工具完成“获取下一工作包→校验依赖/事实版本→发现/选择工具→检查能力地板→执行→监控超时→收集/校验工件→保存哈希/证据→更新 Product Truth→标记 stale→自动返工→推进生命周期→仅在真实决策点暂停”。检查幂等/有界重试/降级/取消/心跳/超时/错误分类/成本/Token/工件哈希/谱系/失败与中断恢复。
- 若主管仅创建/排序/标记工作项而未真实调用工具，相关能力只能标 `partially_implemented`。
- 验证：新增或复用端到端测试，证明有真实工具执行轨迹与工件。

## Task 3: 阶段3 —— 审计理论基础与研究链
- [x] 验证附件接管、多源学术检索、全文/摘要区分、去重排序、标准/法规/专利/竞品、证据可信度/时效、假设与事实隔离、引用、外部内容提示注入隔离、结果写回 Product Truth/Evidence Register；搜索或解析失败保持未验证，绝不补写虚构结论。
- 验证：`tests/` 研究链测试通过；无虚构结论路径。

## Task 4: 阶段4 —— 审计连续附件产品手册链
真实运行“理论基础→先规划→封面/原理/样板锚点→锚点获批→前批页面作为后批图像附件→分批生成剩余页→失败页局部返工→真实中文排版→语义视觉审核→PNG/PDF/ZIP”。验证图像工具真实调用、前批页面真实进入后批附件、Prompt Lineage、Anchor Registry、Visual Bible、人物/结构/模块/CMF/相机一致性、参数来自 Product Truth、禁止拼版/旧图复用/低清放大/伪文字、仅返工责任页、以 WBX-1 手册为黄金样本。
- 不得以白色像素比例/熵/边缘密度/感知哈希/分辨率判定视觉合格。
- 验证：连续附件继承与仅返工责任页的端到端测试；视觉审计诚实性（无视觉后端时 `requiring_vision` 且不假通过）。

## Task 5: 阶段5 —— 审计 CAD 与生产图纸链 + 成熟度一致性门
统一全仓成熟度（Mesh≤C0、Faceted BREP≤C1、原生参数化 B-Rep 进 C2、装配/标准件/连续运动进 C3、载荷强度疲劳进 C4、DFM/GD&T/公差链进 C5、模型/图纸/BOM/检验/审批一致进 C6、实体供应商/样机/DVT-PVT 闭环进 C7）。明确 Faceted 最高 C1。扫描并消除“Faceted 可达 CAD-L3”类冲突，新增 CI 成熟度一致性扫描测试。将发布门升级为真实证据门（文件存在/可读/Schema/SHA-256/图号修订一致/BOM 一致/单位基准/GD&T 覆盖/CTQ 检验/审批真实/证据属当前版本/工具能力支持声明成熟度）。
- 验证：新增 `tests/maturity_consistency_test` 扩展或新测试；CI 的 maturity-consistency job 通过。

## Task 6: 阶段6 —— 审计跨会话恢复
验证新会话自动识别项目、取最新 checkpoint、恢复 Product Truth/Evidence/决策/手册附件链/CAD-BOM 修订/外部等待、不重复询问、给恢复摘要、自动继续。检查状态服务认证/权限/多租户/加密/对象存储/迁移/并发事务/备份恢复/审计日志/retention/healthcheck/指标/密钥管理。仅 SQLite/JSON/MCP skeleton 不得判定为生产级。
- 验证：跨会话恢复端到端测试；状态服务能力清单如实记录实现程度。

## Task 7: 阶段7 —— 审计供应链与物理验证链
验证 Gmail/邮件适配、RFQ 生成发送、报价附件解析、MOQ/模具费/单价/交期/修订、资质/材料证明、EVT/DVT/PVT 导入、CSV/XLSX/PDF 解析、失败根因/纠正包/回归、实体结果回写。严格禁止未报价/未制造/未测试/未认证/未获批准却声明完成。
- 验证：供应链链测试；未真实发生物理环节时相关状态保持 HOLD/未验证。

## Task 8: 阶段8 —— 审计并深化产品所有者 UX
确保默认界面完全隐藏 S0–S8/C0–C7/manifest/lineage/work item/checkpoint/stale/capability ceiling，只展示项目摘要与单一决策卡；支持自然语言审批（批准/选A/成本降低20%/更工业化/不要医疗器械风/保留模块化/暂不进入实体制造）并自动传播到 Product Truth/手册/CAD/BOM/供应链/验证计划。评估一句话启动/恢复、首次成果时间、配置步数、不必要问题数、决策数、返工率、迭代数、错误恢复率、移动端可读性、版本差异预览、外部等待展示，补齐真实缺口。
- 验证：`tests/test_experience.py`、自然语言审批解析测试通过。

## Task 9: 阶段9 —— 真实 Agent 行为 Evals + 三个黄金项目
用真实目标模型或可插拔 Completion 接口实现/复核 15 项行为评测与阈值；维护工业外骨骼/消费电子/简单机械工具三黄金项目，每项保存输入/模型工具版本/轨迹/工件/哈希/决策/证据/错误修复/成本/Token/耗时/验收。
- 验证：`aipd eval` 15 项达标；三个黄金项目可重复运行（`tests/test_golden_projects.py`）。

## Task 10: 阶段10+11 —— 只修复真实缺口 + 工程化核对
对确认的每个真实缺口记录 problem/evidence/root_cause/user_impact/proposed_change/affected_files/acceptance_test/migration/rollback/priority（P0/P1/P2/P3），只修 P0/P1 及关键 P2，不重写已实现且有测试者。核对 pyproject/src 结构/CLI/依赖锁定/类型检查/lint/format/pytest/覆盖率/结构化日志/配置/Dockerfile/docker-compose/迁移/GitHub Actions/SECURITY/CONTRIBUTING/threat model/SBOM/secret scan/dependency audit/license scan/release signing/可复现构建；确认外部网页/论文/附件/供应商文件/实验报告作为数据，不得改变安全规则/决策闸门/CAD 成熟度/发布政策/权限/敏感信息处理。
- 验证：CI 全绿；发布包可复现；`aipd release check` 通过。

## Task 11: 收尾 —— 版本提升、最终判定、发布构建与交付
- 依据审计结果决定是否版本提升（默认 5.4.0）；运行全部测试/`aipd eval`/黄金项目/发布构建。
- 刷新 `audit/` 产物与 `RELEASE_MANIFEST.json`；构建并签名发布包 `releases/5.4.0/`，生成 SHA-256。
- 输出最终判定（见 spec 判定选项）与 13 项最终报告。
- 提交并推送 `origin/main`。

# Task Dependencies
- Task 1 为基线，先行；Task 2–8 相互独立，可并行。
- Task 9 依赖 Task 2（执行链证据）与 Task 8（UX 行为）。
- Task 10 依赖 Task 2–8 的缺口清单。
- Task 11 依赖全部前序任务。