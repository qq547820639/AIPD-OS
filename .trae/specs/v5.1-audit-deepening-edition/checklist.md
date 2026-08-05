# Checklist

> 验收证据：每个 checkpoint 需有可重复运行的测试或审计输出。CI 通过为硬性要求。

- [ ] Task 1 版本真实性审计
  - [ ] `scripts/audit_repo.py` 存在且可运行，输出 JSON 与 Markdown 报告
  - [ ] 报告记录默认分支 main、最新 SHA `96fe3b5b0b8f4f40ce8894c01cc33d421a7ea470`、版本 5.0.0、文件树、无 Tag/releases、CI 状态
  - [ ] RELEASE_MANIFEST.json 哈希核验通过（与真实文件一致）
  - [ ] `tests/test_audit_repo.py` 通过，audit 纳入 CI

- [ ] Task 2 执行记录字段与执行循环
  - [ ] 统一运行记录含全部 19 字段并持久化（测试覆盖）
  - [ ] Supervisor 执行循环按用户给定顺序执行（测试覆盖）
  - [ ] `aipd run --project <id> --until-decision` 可用并在真实决策点暂停

- [ ] Task 3 CAD 成熟度与证据门
  - [ ] 全仓无 “Faceted BREP 可达 CAD-Lx”/越级冲突（扫描扩展至文档/脚本/模板/示例，CI 通过）
  - [ ] Faceted 路径成熟度 ≤ C1
  - [ ] production_release_gate 为证据门全项（文件存在/可打开/schema/hash/图号版本/BOM 数量一致/同修订/单位基准公差/GD&T 覆盖 CTQ 检验/工具能力/所有者审批/证据时效）
  - [ ] 证据门测试覆盖每项检查

- [ ] Task 4 WBX-1 黄金样本视觉差距评测
  - [ ] WBX-1 黄金样本固化，视觉差距评测输出页面级维度得分
  - [ ] 图像后端不可用时走外部任务包而非假装生成（回归测试通过）

- [ ] Task 5 供应链与验证执行器
  - [ ] 报价附件解析/归一化（MOQ/模具费/单价/交期）、报价版本、供应商资质证书
  - [ ] 实验室 CSV/XLSX/报告导入，EVT/DVT/PVT 结果分析
  - [ ] 失败项自动创建纠正任务、回归、事实主表更新、BOM/CAD 影响传播
  - [ ] Gmail/RFQ 适配与供应商信息导入（含外部任务包）
  - [ ] 禁止伪造报价/测试/认证（测试通过）

- [ ] Task 6 行为评测 15 项
  - [ ] `evals/evals.json` 含 15 项用例（含新增 3 项）
  - [ ] 每项保存输入/模型/模型版本/工具轨迹/输出/评分/失败类型/成本/耗时
  - [ ] 三个黄金项目可重复运行并通过阈值

- [ ] Task 7 一键命令 16 个
  - [ ] `init/intake/resume/status/run/decide/manual plan/manual generate/cad preflight/cad build/industrialize/validate/release check/test/eval/package` 全部可用
  - [ ] 每条含帮助、示例、错误提示、`--json` 输出模式
  - [ ] `tests/test_cli_new_commands.py` 覆盖每条命令且通过

- [ ] Task 8 工程化与安全
  - [ ] pyproject/py.typed、依赖锁定、类型/lint/format、pytest+覆盖率、结构化日志、config、secret 管理核对通过
  - [ ] GitHub Actions 含 unit/integration/schema/maturity/secret/dependency/license/package/audit job
  - [ ] SECURITY/CONTRIBUTING/CODE_OF_CONDUCT/THREAT_MODEL/SBOM/release signing 存在
  - [ ] 提示注入隔离测试通过（外部内容不改门/安全政策、不要求发敏感信息、高风险外部动作需人类批准）

- [ ] Task 9 最终验收与发布
  - [ ] 全量测试、15 项评测、三个黄金项目、审计报告全部通过
  - [ ] CHANGELOG/README/QUICKSTART 更新，发布包 + SHA-256 清单 + 签名生成
  - [ ] 已提交并推送至 `origin/main`