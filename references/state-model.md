# 项目状态模型

## 推荐存储

默认使用 SQLite：`aipd_state.sqlite`。它适合本地/工作区原子更新、查询和导出。跨会话团队模式通过 MCP 服务访问同一数据库或将接口替换为托管数据库。

## 核心表

- `projects`：目标、当前 Gate、状态、版本、所有者策略。
- `facts`：参数与结论，含状态、置信度、条件和来源。
- `evidence`：论文、标准、测试、报价、证书和外部资料。
- `fact_evidence`：支持/反驳关系。
- `decisions`：提案、选项、推荐、用户选择和意见。
- `deliverables`：规格、BOM、报告、页面、CAD源码/STEP/图纸/检查包和版本。
- `dependencies`：事实/决策/交付物之间的影响边。
- `risks`：概率、影响、缓解、状态和触发条件。
- `changes`：每次变更和传播结果。
- `gates`：Gate 检查和批准记录。

## 变更传播

任何事实或决策变化时：

1. 查询依赖边；
2. 将受影响交付物标记为 `stale`；
3. 自动重新生成或更新；
4. 执行一致性检查；
5. 记录变更前后值和原因；
6. 只有影响核心目标、成本/周期阈值或安全接受时提交新决策。

## 状态迁移

项目状态：`active`、`awaiting_owner_decision`、`blocked_external`、`internal_rework`、`released`、`archived`。

`blocked_external` 只表示等待真实报价、样机、测试或认证数据。AI 应继续其他可执行任务。

## 恢复策略

每个 Gate 和重要决策后导出 `project_checkpoint.json`。检查点必须含项目、事实、证据、决策、风险、交付物、依赖和变更摘要。

## CAD 状态扩展

CAD 相关交付物在 `deliverables.metadata_json` 中至少记录：`cad_level`、`contract_id`、`spec_version`、`source_path`、`step_path`、`inspection_path`、`snapshot_path`、`release_hash` 和 `validation_status`。

将事实/决策到 CAD Contract、参数化源码、STEP、图纸和BOM建立依赖边。关键事实变化时，相关 CAD 交付物必须标记 `stale`，重新生成和回归检查后才能恢复 `complete/released`。
