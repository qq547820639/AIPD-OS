# Checklist — AIPD-OS v5.4 可重复验证完成度审计与产品化深化版

## 阶段0/1：锁定真实版本 + 完成度矩阵
- [x] `audit/repository_snapshot.json` 覆盖阶段0全部字段，且基于真实 HEAD `651dfbc7` 而非旧记录/旧 ZIP/README。
- [x] `audit/capability_matrix.json|md` 每项含声明/实现/入口/运行命令/输入/输出/依赖/单测/集成/端到端证据/限制/普通用户可用性。
- [x] 矩阵无“仅 README/模板/空适配器/抽象接口/TODO/模拟数据/预留目录”当作证据；`tests/test_audit_repo.py`、`tests/test_capability_matrix.py` 通过。

## 阶段2：AI 主管真实执行
- [x] Execution Router 有真实工具调用轨迹（非仅创建/排序/标记工作项）。
- [x] 幂等/有界重试/降级/取消/心跳/超时/错误分类/成本/Token/工件哈希/谱系/失败与中断恢复均有实现与测试证据。
- [x] 若仅做工作项编排而未真实调用工具，相关能力正确标为 `partially_implemented`。

## 阶段3：理论基础与研究链
- [x] 附件接管/多源检索/全文摘要/去重排序/标准专利竞品/可信度时效/假设事实隔离/引用/提示注入隔离/写回均有实现与测试。
- [x] 搜索或解析失败保持未验证，无虚构结论路径。

## 阶段4：连续附件产品手册链
- [x] 图像工具真实调用；前批页面真实作为后批图像附件（非仅登记路径）。
- [x] Prompt Lineage / Anchor Registry / Visual Bible / 人物·结构·模块·CMF·相机一致性存在。
- [x] 中文为真实文字，参数来自 Product Truth；禁止拼版/旧图复用/低清放大/伪文字。
- [x] 支持仅返工责任页面；以 WBX-1 手册为黄金样本。
- [x] 不以白色像素比例/熵/边缘密度/感知哈希/分辨率判定视觉合格；无视觉后端时不假通过（`requiring_vision`）。

## 阶段5：CAD 链 + 成熟度一致性门
- [x] 全仓统一：Mesh≤C0、Faceted BREP≤C1、原生参数化 B-Rep 进 C2、装配/标准件/连续运动进 C3、载荷强度疲劳进 C4、DFM/GD&T/公差链进 C5、模型/图纸/BOM/检验/审批一致进 C6、实体供应商/样机/DVT-PVT 进 C7。
- [x] 明确 Faceted 最高 C1；无“Faceted 可达 CAD-L3”类冲突。
- [x] 新增 CI 成熟度一致性扫描测试并纳入 workflow。
- [x] 发布门升级为真实证据门（文件存在/可读/Schema/SHA-256/图号修订一致/BOM 一致/单位基准/GD&T 覆盖/CTQ 检验/审批真实/证据属当前版本/工具能力支持声明成熟度）。

## 阶段6：跨会话恢复
- [x] 新会话自动识别项目、恢复 checkpoint/Product Truth/Evidence/决策/手册附件链/CAD-BOM 修订/外部等待、不重复询问、给恢复摘要、自动继续。
- [x] 状态服务能力（认证/权限/多租户/加密/对象存储/迁移/并发事务/备份恢复/审计日志/retention/healthcheck/指标/密钥管理）如实记录实现程度；仅 SQLite/JSON/MCP skeleton 不得判定为生产级。

## 阶段7：供应链与物理验证链
- [x] 邮件适配/RFQ/报价解析/MOQ·模具费·单价·交期·修订/资质/材料证明/EVT-DVT-PVT 导入/CSV·XLSX·PDF 解析/失败根因/纠正包/回归/实体结果回写均有实现与测试。
- [x] 未报价/未制造/未测试/未认证/未获批准时绝不声明完成（状态保持未验证/HOLD）。

## 阶段8：产品所有者 UX
- [x] 默认界面完全隐藏 S0–S8/C0–C7/manifest/lineage/work item/checkpoint/stale/capability ceiling，只展示项目摘要与单一决策卡。
- [x] 支持自然语言审批（批准/选A/成本降低20%/更工业化/不要医疗器械风/保留模块化/暂不进入实体制造）并自动传播到 Product Truth/手册/CAD/BOM/供应链/验证计划。
- [x] 一句话启动/恢复、首次成果时间、配置步数、决策数、返工率、移动端可读性、版本差异预览、外部等待展示等真实缺口已补齐；`tests/test_experience.py` 通过。

## 阶段9：Agent 行为 Evals + 黄金项目
- [x] 15 项行为评测用真实目标模型或可插拔 Completion 接口实现并达到阈值。
- [x] 工业外骨骼/消费电子/简单机械工具三黄金项目可重复运行并保存完整元数据（输入/模型工具版本/轨迹/工件/哈希/决策/证据/错误修复/成本/Token/耗时/验收）。

## 阶段10/11：只修复真实缺口 + 工程化
- [x] 每个已修复缺口记录 problem/evidence/root_cause/user_impact/proposed_change/affected_files/acceptance_test/migration/rollback/priority；未重写已实现且有测试者。
- [x] 工程化核对齐全（pyproject/src/CLI/依赖锁定/类型检查/lint/format/pytest/覆盖率/日志/配置/Dockerfile/compose/迁移/GitHub Actions/SECURITY/CONTRIBUTING/threat model/SBOM/secret scan/dependency audit/license scan/release signing/可复现构建）。
- [x] 外部网页/论文/附件/供应商文件/实验报告作为数据，不改变安全规则/决策闸门/CAD 成熟度/发布政策/权限/敏感信息处理。

## 收尾：版本提升、最终判定、发布与交付
- [x] 版本已提升（默认 5.4.0）；全部测试/`aipd eval`/黄金项目/发布构建通过；`aipd release check` 通过。
- [x] `audit/` 产物与 `RELEASE_MANIFEST.json` 刷新；`releases/5.4.0/` 发布包构建并签名，SHA-256 生成。
- [x] 输出最终判定（fully/substantially/partially/not_met/not_verifiable）与 13 项最终报告。
- [x] 已提交并推送 `origin/main`。