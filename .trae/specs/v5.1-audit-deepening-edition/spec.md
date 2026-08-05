# AIPD-OS v5.1 — Audit & Supply-Chain Deepening Spec

## Why

仓库 `qq547820639/AIPD-OS` 默认分支 `main` 最新提交为 `96fe3b5b0b8f4f40ce8894c01cc33d421a7ea470`（v5.0.0，2026-08-06，本地与远端完全一致，无 tag、无 releases 目录）。v5.0 已交付执行编排层、统一 CAD 成熟度 C0..C7、批次手册链、生产化状态服务、体验层、10 项行为评测与 10 个一键命令。

但对照本次审计目标仍存在真实缺口：
- **供应链/验证执行器基本缺失**：`supplier_adapter` 仅登记文件路径，`mail_rfq_adapter` 只生成确定性草稿，无报价附件解析、MOQ/模具费/单价/交期归一化、报价版本管理、供应商资质证书、实验室 CSV/XLSX/报告导入、EVT/DVT/PVT 结果分析、失败项自动建纠正任务与回归。
- **行为评测仅 10 项**，用户要求 15 项（缺：缺信息先检索或标记假设、CAD 变更回写手册、自然语言审核意见解析）。
- **一键命令仅 10 个且命名不同**，需补齐 `init/intake/resume/status/run/decide/manual plan/manual generate/cad preflight/cad build/industrialize/validate/release check/test/eval/package`。
- **执行记录字段**未完全对齐用户要求的统一运行记录（缺 `project_id/adapter_id/capability/retry_parent` 等语义）。
- **落库的手册黄金样本（WBX-1）视觉差距评测**未作为可重复运行的评测固化。
- **缺少可再生成的《当前版本真实性审计报告》脚本**，审计结论无法由 CI 自动复现。

目标：在不重复开发已实现能力的前提下，补齐上述真实缺口，产出可重复运行的审计、测试与发布证据。

## What Changes

- 新增 `scripts/audit_repo.py` 与 `docs/audit/v5.1-version-truth-audit.md`：从仓库实际状态再生成版本真实性审计（默认分支、最新 SHA、时间、版本、文件树、Release/Tag、CI、RELEASE_MANIFEST 哈希核验、未提交生成文件、遗留冲突、依赖锁定/SBOM/签名）。
- 对齐执行记录为完整统一运行记录（`run_id/project_id/work_id/adapter_id/provider/provider_version/capability/input_hash/output_hash/started_at/completed_at/status/cost/token_usage/retry_parent/fallback_from/error_type/evidence_ids/artifact_ids`）。
- Supervisor 执行循环按用户给定顺序固化（领取→依赖→能力地板→选工具→执行→校验→注册工件→更新事实证据→质量门→标记 stale→建返工或推进→仅在真实决策点暂停），并提供 `aipd run --project <id> --until-decision`。
- CAD 成熟度：保持 C0..C7 语义（Mesh≤C0、Faceted≤C1、原生 B-Rep 才可 C2……），修复任何残留 “Faceted BREP 可达 CAD-Lx” 冲突；将成熟度术语一致性扫描扩展到全部文档/脚本/模板/示例并在 CI 失败。
- 生产发布门从字段门升级为证据门：文件真实存在、可打开、schema 合法、SHA-256 匹配、图号/版本一致、BOM 数量与模型一致、图纸与 CAD 同修订、单位/基准/公差完整、GD&T 覆盖关键特征、CTQ 有检验方式、工具能力支持所声明等级、所有者审批真实、证据未过期。
- 手册链：补齐落库的 WBX-1 黄金样本视觉差距评测（可重复运行），并确认图像不可用时走外部任务包而非假装生成。
- 供应链执行器（真实缺口）：Gmail/RFQ 适配、供应商信息导入、报价附件解析、MOQ/模具费/单价/交期归一化、报价版本管理、供应商资质与证书、实验室 CSV/XLSX/报告导入、EVT/DVT/PVT 结果分析、失败项自动建纠正任务、回归测试、事实主表更新、BOM/CAD 影响传播；禁止伪造报价/测试/认证。
- 行为评测扩展为 15 项，每项保存输入/模型/模型版本/工具轨迹/输出/评分/失败类型/成本/耗时；三个黄金项目（工业外骨骼、消费电子、简单机械工具）可重复运行。
- 一键命令补齐为 `init/intake/resume/status/run/decide/manual plan/manual generate/cad preflight/cad build/industrialize/validate/release check/test/eval/package`，每条含帮助、示例、错误提示、JSON 输出模式与测试。
- 工程化与安全核对补齐（pyproject/py.typed、依赖锁定、类型/lint/format、pytest+覆盖率、结构化日志、config、secret、GitHub Actions、SECURITY/CONTRIBUTING/CODE_OF_CONDUCT/THREAT_MODEL/SBOM/license/dependency/secret scan/release signing/可复现构建）；提示注入隔离按用户清单核对并补测试。

## Impact

- 受影响能力：版本真实性审计、执行编排、CAD 成熟度与门、连续附件手册、跨会话状态、所有权体验、供应链/RFQ/测试验证、Agent 行为评测、工程化/安全、一键命令。
- 受影响代码：
  - `src/aipd_os/execution/{models,execution_router,runs,adapter,registry}.py`（运行记录字段、执行循环）
  - `src/aipd_os/tool_adapters/{supplier_adapter,mail_rfq_adapter,evt_dvt_pvt_adapter}.py`（供应链/验证执行器）
  - `src/aipd_os/evals_runner/*`、`evals/evals.json`（15 项行为评测）
  - `src/aipd_os/cli/{main,commands}.py`（16 个一键命令）
  - `src/aipd_os/visual_audit/*`（WBX-1 黄金样本差距评测）
  - `scripts/cad_maturity_gate.py`、`scripts/production_release_gate.py`、`tests/maturity_consistency_test.py`
  - 新增 `scripts/audit_repo.py`、`docs/audit/*`、`tests/test_audit_repo.py`、`tests/test_supply_chain.py`、`tests/test_cli_new_commands.py`
- 新增能力域：`supply_chain/`（RFQ、报价、供应商资质、实验室数据、EVT/DVT/PVT 分析、纠正任务）。

## ADDED Requirements

### Requirement: 版本真实性审计可再生成
- 系统 SHALL 提供一个脚本，从仓库当前实际状态重新生成《版本真实性审计报告》，覆盖默认分支、最新 SHA、时间、版本、文件树、Release/Tag、CI、RELEASE_MANIFEST 哈希核验、未提交生成文件、遗留语义冲突、依赖锁定/SBOM/签名。
- **WHEN** 运行 `aipd audit` 或 `script/audit_repo.py`
- **THEN** 输出机器可读 JSON 与 Markdown 报告，且 CI 校验报告与仓库一致。

### Requirement: 供应链与验证执行器（真实执行）
- 系统 SHALL 实现或正式适配：Gmail/RFQ、供应商信息导入、报价附件解析、MOQ/模具费/单价/交期归一化、报价版本管理、供应商资质与证书、实验室 CSV/XLSX/报告导入、EVT/DVT/PVT 结果分析、失败项自动创建纠正任务、回归测试、事实主表更新、BOM/CAD 影响传播。
- **WHEN** 提供报价附件
- **THEN** 解析并归一化 MOQ/模具费/单价/交期，生成报价版本，关联供应商资质与证书，登记为证据。
- **WHEN** 提供实验室 CSV/XLSX/报告
- **THEN** 导入并分析 EVT/DVT/PVT 结果，失败项自动创建纠正任务，回归完成后更新事实主表并传播 BOM/CAD 影响。
- **禁止**：未收到报价写成正式报价、未执行测试写成通过、未获证书写成已认证。

### Requirement: Agent 行为评测扩展为 15 项
- 在现有 10 项基础上新增：缺信息先检索或标记假设、CAD 变更正确回写手册、用户自然语言审核意见正确解析；每项保存输入/模型/模型版本/工具轨迹/输出/评分/失败类型/成本/耗时。
- **WHEN** 运行 `aipd eval`
- **THEN** 15 项全部可运行并输出评分与失败类型。

### Requirement: 一键命令补齐（16 个）
- 提供 `init/intake/resume/status/run/decide/manual plan/manual generate/cad preflight/cad build/industrialize/validate/release check/test/eval/package`，每条含帮助、示例、错误提示、JSON 输出模式与测试。
- **WHEN** 运行任一命令并带 `--json`
- **THEN** 输出结构化 JSON；错误时给出可操作提示并返回非零退出码。

### Requirement: WBX-1 黄金样本视觉差距评测
- 系统 SHALL 将用户认可的 WBX-1 产品手册固化为可重复运行的视觉差距评测（黄金样本），输出页面级差距得分。
- **WHEN** 运行视觉评测
- **THEN** 对每页给出结构/人物/模块/CMF/场景/角色完成度/跨页叙事/文案来源/参数来源/中文真文字/拼版/旧图复用/低清放大/伪文字/参数臆造等维度得分。

### Requirement: 执行记录字段对齐
- 统一运行记录 SHALL 包含 `run_id/project_id/work_id/adapter_id/provider/provider_version/capability/input_hash/output_hash/started_at/completed_at/status/cost/token_usage/retry_parent/fallback_from/error_type/evidence_ids/artifact_ids`。
- **WHEN** 任一工具执行完成
- **THEN** 记录包含上述全部字段，并持久化到 `execution_runs`。

## MODIFIED Requirements

### Requirement: 现有执行编排层
- 保留 ToolAdapter 接口与 Execution Router，补齐 `project_id/adapter_id/capability/retry_parent` 字段语义，并固化 Supervisor 执行循环顺序。

### Requirement: 现有 CAD 门
- 保留 C0..C7，将成熟度术语一致性扫描扩展到全部文档/脚本/模板/示例，生产发布门升级为上文证据门全项。

### Requirement: 现有供应链适配器
- `supplier_adapter`/`mail_rfq_adapter`/`evt_dvt_pvt_adapter` 从“文件登记/草稿生成”升级为真实解析、归一化、版本、分析、纠正任务与影响传播。

### Requirement: 现有行为评测
- 保留原 10 项用例，扩展至 15 项并补齐评测字段与黄金项目重复运行。

## REMOVED Requirements

### Requirement: 未对齐的统一运行记录字段集
**Reason**: 用户要求的字段集（含 project_id/adapter_id/capability/retry_parent）与现记录不一致。
**Migration**: `src/aipd_os/execution/runs.py` 与 `execution_router.py` 对齐字段，迁移已有 `execution_runs` 表。

### Requirement: 仅登记不解析的供应链适配器语义
**Reason**: 无法支撑报价/实验室数据真实处理。
**Migration**: 替换为真实解析与分析能力，保留 `supply.*` capability id 兼容。