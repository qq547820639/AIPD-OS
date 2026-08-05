# AIPD-OS v5.2 — 能力矩阵与真实性核验版 Spec

## Why

实际读取远端仓库 `qq547820639/AIPD-OS`（默认分支 `main`，HEAD `67fb368bdc56afc4e489f12dd8aaf80893b8490c`，2026-08-05T20:16:36Z，无 tag、无 release）并与本地确认一致后，对照本轮审计目标进行真实性核验。v5.1 已交付执行编排、CAD 成熟度 C0..C7、批次手册链、生产化状态服务、体验层、供应链执行器、15 项行为评测、16 个一键命令；本地 `172` 个测试（含 PIL/reportlab）全部通过。

但对照用户要求的最终交付物与“必须真实调用模型”等硬性规则，仍存在**真实缺口**：

- **缺少用户明确要求的审计交付物**：`audit/repository_snapshot.json`、`audit/capability_matrix.json`、`audit/capability_matrix.md` 均不存在；仓库没有任何把全部能力按 7 类（fully_implemented / partially_implemented / protocol_only / template_only / external_dependency / not_implemented / not_verifiable）分类的能力矩阵。
- **审计报告过期**：`docs/audit/audit.json` 记录 HEAD=`96fe3b5`，`docs/audit/v5.1-version-truth-audit.md` 记录 HEAD=`ead48605`，均不等于真实当前 HEAD；`RELEASE_MANIFEST.json` 中 3 个审计文档哈希不匹配（自指不一致）。
- **Agent 行为评测未真实调用模型**：`EnvCompletionProvider.complete()` 直接抛 `RuntimeError("未接入具体模型端点 SDK")`，评测仅使用脚本化假模型 `RecordedCompletionProvider`，违反“必须真实调用目标模型或可插拔 Completion 接口”。
- **干净环境安装/CI 缺陷**：`[full]` extra 含 `mcp`（Requires-Python >=3.10），而项目 `requires-python >=3.9` 且 CI 用 Python 3.9；CI unit job 只装 `.[dev]`（缺 PIL/reportlab），导致 `test_layout/test_visual_golden/test_manual_chain_e2e/test_behavior_contracts/test_golden_projects` 在收集期 ImportError，CI unit job 实际会红。

目标：只针对上述真实缺口增量补齐，不重写已实现且有测试证据的能力。

## What Changes

- 扩展 `scripts/audit_repo.py`（或新增 `scripts/capability_matrix.py`）在**当前真实 HEAD** 再生成审计，并新增能力矩阵生成器，产出：
  - `docs/audit/repository_snapshot.json`（默认分支/最新 SHA/时间/版本/文件树/tag/release/CI/manifest 哈希/未跟踪/冲突/依赖锁/SBOM/签名）
  - `docs/audit/capability_matrix.json`（对六大域全部能力逐项分类到 7 类，含声明文件/实现文件/类或函数入口/运行命令/输入输出/单元测试/集成测试/端到端证据/当前限制）
  - `docs/audit/capability_matrix.md`（同一矩阵的可读 Markdown）
- 修复 `RELEASE_MANIFEST.json` 中 3 个审计文档的哈希不匹配，使 manifest 与真实文件一致。
- 打通 Agent 评测的真实/可插拔 Completion：`EnvCompletionProvider` 接入 OpenAI 兼容 HTTP 端点（`AIPD_EVAL_MODEL_ENDPOINT/KEY/VERSION`），未配置时诚实标记为 `external_dependency` 而非假装调用；保留脚本化假模型用于离线（不伪造）。
- 修复打包/CI 安装缺陷：将 `mcp` 从 `[full]` 中移出或声明 `Requires-Python >=3.10` 的独立 extra，保证 Python 3.9 干净环境可安装；CI unit/integration job 安装完整 `[full,dev]`（或等价依赖），使全部测试可收集并通过。
- 版本提升至 `5.2.0`，重新生成 `RELEASE_MANIFEST.json`、构建发布包与 SHA-256 清单并签名。

## Impact

- 受影响能力：版本真实性审计、能力矩阵、Agent 行为评测（真实模型调用）、工程化/打包/CI。
- 受影响代码：
  - `scripts/audit_repo.py` / 新增 `scripts/capability_matrix.py`
  - `src/aipd_os/evals_runner/completion.py`（真实端点接入）
  - `pyproject.toml`（extras 修正）
  - `.github/workflows/ci.yml`（unit/integration 安装完整依赖）
  - `docs/audit/*`、`RELEASE_MANIFEST.json`、`CHANGELOG.md`、`README.md`、`QUICKSTART.md`
  - 新增 `tests/test_capability_matrix.py`、`tests/test_completion_endpoint.py`
- 新增能力域：能力矩阵（capability matrix）审计产物。

## ADDED Requirements

### Requirement: 能力矩阵审计产物
- 系统 SHALL 生成 `docs/audit/repository_snapshot.json`、`docs/audit/capability_matrix.json`、`docs/audit/capability_matrix.md`，对全部能力按 7 类分类并给出证据字段。
- **WHEN** 运行 `aipd audit` 或 `python scripts/capability_matrix.py`
- **THEN** 三份产物生成且 CI 校验其与仓库实际状态一致（HEAD/版本/文件树/哈希）。

### Requirement: 真实模型评测 Completion
- 系统 SHALL 提供一个可插拔 Completion 接口，在配置端点时真实调用 OpenAI 兼容模型；未配置时把该 case 诚实标记为 `external_dependency`，绝不返回伪造输出。
- **WHEN** 设置 `AIPD_EVAL_MODEL_ENDPOINT/KEY/VERSION` 并运行 `aipd eval`
- **THEN** 评测真实调用模型并记录模型版本/轨迹/输出/评分/成本/耗时。

### Requirement: 干净环境可安装
- 系统 SHALL 在 Python 3.9 干净环境可完整安装（含可选依赖），且 CI unit/integration job 安装全部依赖后所有测试可收集并通过。
- **WHEN** `pip install -e ".[full,dev]"`（Python 3.9）
- **THEN** 不因 `mcp` 等 Requires-Python 不符而失败，且 `pytest` 全绿。

## MODIFIED Requirements

### Requirement: 现有版本真实性审计
- 保留 `audit_repo.py` 再生成能力，在**当前真实 HEAD** 再生成 `docs/audit/*`，并修复 `RELEASE_MANIFEST.json` 哈希不一致。

### Requirement: 现有 Agent 行为评测
- 保留 15 项评测与脚本化假模型（离线），补齐真实/可插拔 Completion 端点以支持真实验证路径。

### Requirement: 现有工程化/打包
- 修正 `[full]` extras 对 Python 3.9 的不兼容，确保干净环境可安装、CI 可收集并跑通全部测试。

## REMOVED Requirements

### Requirement: 仅脚本化假模型的评测（作为唯一路径）
**Reason**: 违反“必须真实调用目标模型或可插拔 Completion 接口”。
**Migration**: 保留为离线回退，新增真实端点路径并诚实分类 external_dependency。

### Requirement: 指向过期 HEAD 的审计产物
**Reason**: 审计必须反映仓库当前真实状态。
**Migration**: 在 HEAD `67fb368`（及后续发布提交）重新生成并纳入 CI 校验。