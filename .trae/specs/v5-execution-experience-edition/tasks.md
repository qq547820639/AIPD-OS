# Tasks

> 执行原则：每项任务必须产出可重复运行的测试与验收证据。先建包结构/测试骨架，再逐域实现。域之间尽量并行。

- [x] Task 1: 工程化基础（包结构、配置、日志、CI 骨架）
  - [x] 1.1 编写 `pyproject.toml`（标准包结构 `src/aipd_os/...`，依赖锁定，`[project.scripts]` CLI 入口）
  - [x] 1.2 建立统一配置模块（`src/aipd_os/config.py`，支持 env/file 覆盖）
  - [x] 1.3 建立结构化日志模块（`src/aipd_os/logging_utils.py`，JSON 行日志）
  - [x] 1.4 建立类型检查（mypy/pyright）、lint（ruff）、format（ruff format）配置与 `pytest`/coverage 配置
  - [x] 1.5 建立 `.github/workflows/ci.yml`（unit、integration、schema、maturity-consistency、secret-scan、dependency-audit、license-scan、package-build）
  - [x] 1.6 迁移现有 `scripts/*.py` 为可导入包（保留 `scripts/` 兼容入口）

- [x] Task 2: 统一 CAD 成熟度 C0..C7 与门修复
  - [x] 2.1 重写 `scripts/cad_maturity_gate.py` 为 C0..C7（移除 CAD-Lx），与 production_release_gate 合并要求
  - [x] 2.2 修复 `scripts/production_release_gate.py` 的 `achieved` 计算（最低级失败不得报告达到该级）
  - [x] 2.3 升级门检查为文件存在/可读、schema 校验、哈希、版本匹配、数量一致、单位/基准完整、审批状态、证据时效、工具能力上限
  - [x] 2.4 新增 `tests/maturity_consistency_test.py`：扫描全仓，发现冲突成熟度定义（CAD-Lx 或越级）即失败
  - [x] 2.5 为 text-to-cad、本地 B-Rep、Faceted fallback 建立机器可读插件依赖/兼容矩阵（`references/cad-plugin-matrix.json`）
  - [x] 2.6 更新 `scripts/capability_gate.py` 与所有引用方对齐 C0..C7

- [x] Task 3: 执行编排层（Execution Router + Tool Adapter）
  - [x] 3.1 定义 Tool Adapter 基类接口（discovery/validate/execute/collect/normalize/classify/retry/fallback/persist）
  - [x] 3.2 实现 `src/aipd_os/execution/execution_router.py`：run_id、input/output hash、start/end、cost/token/time、retry lineage、error classification、证据持久化
  - [x] 3.3 新增 `src/aipd_os/execution/runs.py`：运行记录存储（sqlite 表 `execution_runs`）
  - [x] 3.4 实现适配器注册表与 capability discovery
  - [x] 3.5 为下列能力提供适配器或正式接口：论文检索、文档生成、图像生成、手册排版打包、text-to-cad、本地 B-Rep、Faceted fallback、邮件/RFQ、供应商文件、EVT/DVT/PVT 数据导入
  - [x] 3.6 扩展 `scripts/aipd_supervisor.py`：next_work 返回运行上下文、complete/fail 关联 run_id、自动领取、写日志、注册工件、更新事实/证据、标记 stale、自动建返工任务、有界重试、失败切换下位工具、仅在必要时创建决策

- [x] Task 4: 连续附件产品手册执行链
  - [x] 4.1 在 `scripts/manual_chain.py` 增加真实批次执行器（每批保存提示词/理论版本/Truth 版本/锚点/上一批附件/Visual Bible/禁用项/输出页与哈希）
  - [x] 4.2 实现图像生成适配器 `src/aipd_os/imggen/`；不可用时不假装生成，改为生成外部执行任务包
  - [x] 4.3 实现中文排版层 `src/aipd_os/layout/`：A4 2480×3508、300dpi、标题/正文/图注/页码/参数表/曲线/图标/注释、PDF+逐页 PNG+ZIP
  - [x] 4.4 实现视觉语义审计 `src/aipd_os/visual_audit/`（黄金样本、结构/人物/CMF 一致性、角色完成度、叙事连续性、中文真文字、参数事实一致、禁伪文字/低清放大/旧图复用）；仅像素统计不得判定合格
  - [x] 4.5 视觉失败自动定位页面与维度，仅重建责任页面
  - [x] 4.6 提供 10 页以上黄金项目端到端回归测试

- [x] Task 5: 生产化跨会话状态服务
  - [x] 5.1 升级 `state_service/` 为部署服务：认证、项目级授权、多租户隔离、数据加密、迁移、乐观锁/事务、自动备份、checkpoint 恢复、审计日志、健康检查、对象存储、retention
  - [x] 5.2 新增 `migrations/` 目录与 v4→v5 迁移脚本 + 回滚测试
  - [x] 5.3 提供 `Dockerfile` 与 `docker-compose.yml`
  - [x] 5.4 支持本地单用户模式与服务器多用户模式
  - [x] 5.5 新会话启动自动识别项目、恢复最近 checkpoint、汇总上次完成事项、显示阶段/阻塞/下一步、不重复询问已解决决策

- [x] Task 6: 产品所有者体验
  - [x] 6.1 对话层项目摘要（正在做/已完成/缺口/最大风险/下一里程碑）
  - [x] 6.2 决策卡（一次一个最高优先级、AI 推荐、2-4 选项、成本/性能/时间/安全影响、批准后自动执行什么）
  - [x] 6.3 恢复摘要（上次位置、新增/变更事实、stale 工件、外部等待）
  - [x] 6.4 工件预览（手册缩略图、CAD 版本变化、BOM/参数差异）
  - [x] 6.5 自然语言指令解析与影响传播（批准/成本降20%/更工业化/不要医疗风）
  - [x] 6.6 默认自然语言输出，内部编号仅放折叠详情与审计日志

- [x] Task 7: 可运行 Agent 行为评测
  - [x] 7.1 实现 `src/aipd_os/evals_runner/`：真实调用目标模型或可插拔 Completion 接口，保存输入/模型版本/工具轨迹/输出/评分/失败类型
  - [x] 7.2 将 `evals/evals.json` 升级为可运行用例，覆盖 10 项行为契约
  - [x] 7.3 建立 3 个黄金端到端项目（外骨骼、消费电子、简单机械工具）
  - [x] 7.4 评测数据版本管理；评分下降超阈值阻断发布
  - [x] 7.5 CI 执行确定性测试；模型评测可配置为夜间/发布前

- [x] Task 8: 安全与文档
  - [x] 8.1 提示注入隔离（外部内容视为数据、检测记录可疑指令、不允许改变门/安全政策）
  - [x] 8.2 敏感信息权限与脱敏（报价/联系人/实验数据）
  - [x] 8.3 新增 SECURITY.md、CONTRIBUTING.md、CODE_OF_CONDUCT.md、THREAT_MODEL.md、SBOM、release signing
  - [x] 8.4 更新 SKILL.md、README、快速开始、架构图、v5.0 变更日志

- [x] Task 9: CLI 一键命令与发布包
  - [x] 9.1 实现 CLI 入口：init-project、restore-project、run-supervisor、project-summary、submit-decision、run-manual-chain、run-cad-chain、run-tests、run-evals、build-release
  - [x] 9.2 实现 `build-release`：发布包 + SHA-256 清单 `RELEASE_MANIFEST.json` 更新
  - [x] 9.3 全量测试与端到端评测跑通

# Task Dependencies

- Task 1 无依赖（先建骨架）。
- Task 2 依赖 Task 1（测试骨架）。
- Task 3 依赖 Task 1（包结构、日志、配置）。
- Task 4 依赖 Task 1（包结构）。
- Task 5 依赖 Task 1（包结构、配置）。
- Task 6 依赖 Task 5（状态服务）与 Task 3（执行上下文）。
- Task 7 依赖 Task 1、Task 2、Task 4 的部分能力。
- Task 8 依赖 Task 1；8.4 依赖所有域完成。
- Task 9 依赖 Task 2—8。

可并行：Task 2、Task 3、Task 4、Task 5 在 Task 1 完成后可并行推进；Task 6 依赖其余部分。