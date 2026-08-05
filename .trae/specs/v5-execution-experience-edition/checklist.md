# Checklist

> 验收证据：每个 checkpoint 需有可重复运行的测试或审计输出。CI 通过为硬性要求。

- [x] Task 1 工程化基础
  - [x] `pyproject.toml` 存在且 `pip install -e .` 成功，`aipd` CLI 可用
  - [x] lint/format/type-check 命令可运行且默认无错误
  - [x] `pytest` 可收集并运行测试，coverage 配置生效
  - [x] `.github/workflows/ci.yml` 定义 unit/integration/schema/maturity/secret/dependency/license/package 各 job

- [x] CAD 成熟度统一与门修复
  - [x] 全仓无 `CAD-Lx` 遗留定义（maturity consistency 测试通过）
  - [x] Faceted BREP 工件成熟度声明 ≤ C1（越级测试通过）
  - [x] `production_release_gate.py` 在最低级要求失败时 achieved 不报告达到该级（回归测试通过）
  - [x] 门检查对文件存在/可读、schema、哈希、版本、数量、单位/基准、审批、时效、能力上限均生效（测试覆盖）
  - [x] `references/cad-plugin-matrix.json` 存在且 schema 校验通过

- [x] 执行编排层
  - [x] Tool Adapter 接口方法齐全且有测试
  - [x] 执行记录包含全部字段（run_id/work_id/tool/provider/version/input_hash/output_hash/start-end/cost-token-time/status/error_classification/retry_lineage/evidence_references）
  - [x] 主管可自动领取工作包、调用适配器、写日志、注册工件、标记 stale、自动建返工、有界重试、失败切换下位工具
  - [x] 仅在必要时创建决策（决策触发测试通过）

- [x] 连续附件手册执行链
  - [x] 批次执行器保存每批完整上下文（提示词/理论版本/Truth 版本/锚点/上一批附件/Visual Bible/禁用项/输出页与哈希）
  - [x] 图像生成不可用时生成外部任务包而非假装（测试通过）
  - [x] 中文排版输出 A4 2480×3508、300dpi、PDF+逐页 PNG+ZIP（产物校验通过）
  - [x] 视觉语义审计覆盖全部维度且非仅像素统计；失败自动定位并仅重建责任页面
  - [x] 10 页以上黄金项目端到端回归测试通过

- [x] 生产化跨会话状态
  - [x] 认证/授权/多租户/加密/迁移/乐观锁/备份/checkpoint 恢复/审计/健康检查/对象存储/retention 均有实现与测试
  - [x] v4→v5 迁移脚本与回滚测试通过
  - [x] Dockerfile 与 docker-compose 可构建启动
  - [x] 新会话恢复测试通过（识别项目、恢复 checkpoint、汇总完成事项、显示阶段/阻塞/下一步、不重复询问）

- [x] 产品所有者体验
  - [x] 项目摘要/决策卡/恢复摘要/工件预览/自然语言指令解析均有测试
  - [x] 默认输出自然语言，内部编号仅出现在折叠详情与审计日志

- [x] 可运行 Agent 行为评测
  - [x] evals_runner 真实调用模型或可插拔 Completion 接口，保存全部评测字段
  - [x] 10 项行为契约用例全部可运行并保存评分
  - [x] 3 个黄金端到端项目存在且可运行
  - [x] 评分回退超过阈值阻断发布机制生效

- [x] 安全与文档
  - [x] 提示注入隔离与敏感信息脱敏测试通过
  - [x] SECURITY/CONTRIBUTING/CODE_OF_CONDUCT/THREAT_MODEL/SBOM/release signing 存在
  - [x] SKILL.md、README、快速开始、架构图、v5.0 变更日志已更新

- [x] 发布与验收
  - [x] 10 个一键命令可用
  - [x] 发布包与 SHA-256 清单生成成功
  - [x] 全量测试与端到端评测全部通过