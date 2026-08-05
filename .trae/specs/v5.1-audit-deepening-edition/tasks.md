# Tasks

> 执行原则：每项任务产出可重复运行的测试与验收证据。先核对已有实现避免重复开发，再补齐真实缺口。多数任务在保留既有能力基础上增量实现。

- [ ] Task 1: 版本真实性审计可再生成
  - [ ] 1.1 实现 `scripts/audit_repo.py`：从仓库实际状态读取默认分支、最新 SHA、时间、版本、文件树、Tag/Release、CI 状态、RELEASE_MANIFEST 哈希核验、未提交生成文件、遗留语义冲突、依赖锁定/SBOM/签名。
  - [ ] 1.2 输出机器可读 JSON 与 Markdown 报告，写入 `docs/audit/v5.1-version-truth-audit.md`。
  - [ ] 1.3 新增 `tests/test_audit_repo.py`：校验报告内容与仓库实际状态一致（SHA/版本/文件树/哈希）。
  - [ ] 1.4 将审计纳入 CI（audit job），并核对 RELEASE_MANIFEST/Hash 与真实文件一致。

- [ ] Task 2: 执行记录字段对齐与 Supervisor 执行循环
  - [ ] 2.1 在 `src/aipd_os/execution/models.py`/`runs.py` 补齐统一运行记录字段（project_id/adapter_id/capability/retry_parent 等）。
  - [ ] 2.2 `execution_router.py` 写入完整字段并迁移 `execution_runs` 表。
  - [ ] 2.3 固化 `scripts/aipd_supervisor.py` 执行循环顺序（领取→依赖→能力地板→选工具→执行→校验→注册工件→更新事实证据→质量门→标记 stale→建返工/推进→仅真实决策点暂停）。
  - [ ] 2.4 提供 `aipd run --project <id> --until-decision` 并加测试。

- [ ] Task 3: CAD 成熟度一致性扫描与证据门升级
  - [ ] 3.1 扩展 `tests/maturity_consistency_test.py` 扫描全部文档/脚本/模板/示例，任何 “Faceted BREP 可达 CAD-Lx” 或越级即失败。
  - [ ] 3.2 修复残留冲突（若有），确认 Faceted 路径最高 C1。
  - [ ] 3.3 升级 `scripts/production_release_gate.py` 为证据门全项（文件存在/可打开/schema/hash/图号版本/BOM 数量一致/图纸 CAD 同修订/单位基准公差/GD&T 覆盖 CTQ 检验/工具能力/所有者审批/证据时效）。
  - [ ] 3.4 新增门证据门测试覆盖上述每项。

- [ ] Task 4: WBX-1 黄金样本视觉差距评测
  - [ ] 4.1 将 WBX-1 手册固化为黄金样本（`references/`），实现 `src/aipd_os/visual_audit/` 页面级差距评测（结构/人物/模块/CMF/场景/角色完成度/叙事连续性/文案来源/参数来源/中文真文字/拼版/旧图复用/低清放大/伪文字/参数臆造）。
  - [ ] 4.2 提供黄金样本评测命令（并入 `aipd manual generate`/`aipd eval`）与测试。
  - [ ] 4.3 确认图像后端不可用时走外部任务包而非假装生成（回归测试）。

- [ ] Task 5: 供应链与验证执行器（真实缺口）
  - [ ] 5.1 报价附件解析与归一化：MOQ/模具费/单价/交期解析、报价版本管理、供应商资质与证书登记。
  - [ ] 5.2 实验室 CSV/XLSX/报告导入：EVT/DVT/PVT 结果读取与归一化。
  - [ ] 5.3 EVT/DVT/PVT 结果分析：失败项自动创建纠正任务、回归测试、事实主表更新、BOM/CAD 影响传播。
  - [ ] 5.4 Gmail/RFQ 适配与供应商信息导入（含真实工具不可用时的外部任务包）。
  - [ ] 5.5 新增 `tests/test_supply_chain.py`：禁止伪造报价/测试/认证。

- [ ] Task 6: Agent 行为评测扩展为 15 项
  - [ ] 6.1 在 `evals/evals.json` 新增 3 项：缺信息先检索或标记假设、CAD 变更回写手册、自然语言审核意见解析。
  - [ ] 6.2 每项保存输入/模型/模型版本/工具轨迹/输出/评分/失败类型/成本/耗时。
  - [ ] 6.3 校验三个黄金项目（工业外骨骼、消费电子、简单机械工具）可重复运行并通过阈值。

- [ ] Task 7: 一键命令补齐（16 个）
  - [ ] 7.1 在 `src/aipd_os/cli/{main,commands}.py` 新增 `intake/resume/status/run/decide/manual plan/manual generate/cad preflight/cad build/industrialize/validate/release check/eval/package`（保留并映射现有实现）。
  - [ ] 7.2 每条命令含帮助、示例、错误提示与 `--json` 输出模式。
  - [ ] 7.3 新增 `tests/test_cli_new_commands.py` 覆盖每条命令。

- [ ] Task 8: 工程化与安全核对补齐
  - [ ] 8.1 核对 pyproject.py.typed、依赖锁定、类型/lint/format、pytest+覆盖率、结构化日志、config、secret 管理。
  - [ ] 8.2 核对 GitHub Actions（unit/integration/schema/maturity/secret/dependency/license/package/audit）与 SECURITY/CONTRIBUTING/CODE_OF_CONDUCT/THREAT_MODEL/SBOM/release signing。
  - [ ] 8.3 提示注入隔离按用户清单核对并补测试（外部内容不改门/安全政策、不要求发敏感信息、高风险外部动作需人类批准）。

- [ ] Task 9: 最终验收与发布
  - [ ] 9.1 全量测试、15 项评测、三个黄金项目、审计报告全部跑通。
  - [ ] 9.2 更新 CHANGELOG/README/QUICKSTART，构建发布包、SHA-256 清单并签名。
  - [ ] 9.3 提交并推送至 `origin/main`。

# Task Dependencies

- Task 1 无依赖（审计）。
- Task 2 依赖 Task 1（基线）。
- Task 3 依赖 Task 1（一致性基线）。
- Task 4 依赖 Task 1（手册链基线）。
- Task 5 依赖 Task 2（执行记录）与 Task 1。
- Task 6 依赖 Task 1、Task 4（黄金样本）。
- Task 7 依赖 Task 2、Task 5、Task 4、Task 6（命令映射到真实能力）。
- Task 8 依赖 Task 1；8.3 依赖 Task 5。
- Task 9 依赖 Task 1—8。

可并行：Task 1、Task 3、Task 4 可并行；Task 2 随后；Task 5、Task 6 在 Task 1/2 后可并行；Task 7 依赖多数域完成。