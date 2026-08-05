# AIPD-OS v5.3 — 所有者体验与技能质量深化版 Spec

## Why

实际读取远端仓库 `qq547820639/AIPD-OS`（默认分支 `main`，HEAD `9cfec246f0966b9efba669dcb0b88edad4223a52`，v5.2.0，工作区干净，发布包 `releases/5.2.0/aipd-os-5.2.0.zip` SHA-256 `5048fbf9…7d5ed02`）并审计后确认：v5.2 已交付能力矩阵、真实/可插拔评测端点、干净环境安装修复，70 项能力中 52 项 fully_implemented，UX 层（project_summary / decision_card / resume_summary / artifact_preview / 自然语言审核 `instructions.py`）与三个黄金项目均已具备真实实现与测试。

但对照本轮审计目标，仍存在**真实缺口**（均不依赖外部服务，可用确定性代码 + 测试补全）：

- **SKILL.md 过期**：标题仍为 `5.0`，一键命令清单仍是 v5.0 的 10 个，缺失 v5.1/v5.2 命令（`init`/`run`/`audit`/`eval`/`package` 等）；违反“渐进披露”与“触发描述准确”的 Skill 质量要求。
- **缺少风险红黄绿视图**：`project_summary` 只有 `top_risk` 文本，无面向普通用户的红/黄/绿(健康)状态视图，也无“下一里程碑”与风险联动的可读呈现。
- **供应商/实验室等待未单独呈现**：`resume_summary.external_waiting` 存在但未在所有者视图独立成节，普通用户无法一眼看到“在等报价/样机/测试”。
- **部分实现能力可确定性深化**：`research.evidence_credibility`、`cad.anthropometric_families`、`industrialize.certification_status` 三项仅启发式/字段/登记，缺真实可测的确定性逻辑。
- **视觉一致性审计缺诚实性护栏回归**：`auditor.py` 的 character/CMF/product-structure 一致性维度在无视觉后端时返回 `passed=_vision()`，可能被误读为已做语义检查；需回归测试证明其“绝不假通过、诚实 requiring_vision”。
- **缺命令—测试覆盖一致性校验**：无测试保证“README/SKILL 声明命令 == 已注册命令 == 有测试”三者一致。

目标：只针对上述真实缺口增量补齐，不重写已完整实现且有测试证据的能力。

## What Changes

- **技能质量（SKILL.md）**：标题刷新至 v5.3，补全全部一键命令（含 `init`/`intake`/`resume`/`status`/`run`/`decide`/`manual plan`/`manual generate`/`cad preflight`/`cad build`/`industrialize`/`validate`/`audit`/`release check`/`test`/`eval`/`package`），确认专业细节已拆到 `references/`，消除需新会话猜测的隐含路径；新增 `scripts/skill_quality_audit.py` 做渐进披露与命令清单一致性自查。
- **所有者风险红黄绿 + 外部等待视图**：新增 `src/aipd_os/experience/risk_health.py`（确定性红/黄/绿健康状态，由风险影响 × 状态 × 外部等待推导）与 `src/aipd_os/experience/external_wait.py`（将 `external_waiting` 归并为供应商/实验室待办清单），接入 `views.py` 的 `OwnerView.owner_update` 与 `render_markdown`；普通用户默认只看到自然语言，内部代号仍在 `<details>`。
- **部分实现能力确定性深化**：
  - `research.evidence_credibility`：新增 `src/aipd_os/research/credibility.py`（证据可信度评分：来源可信度 × 时效衰减 × 假设/事实分离），带测试。
  - `cad.anthropometric_families`：新增 `src/aipd_os/cad/anthropometry.py`（人体尺寸百分位族数据表 + 按族/百分位取值 + 校验），带测试。
  - `industrialize.certification_status`：新增 `src/aipd_os/supply_chain/certification.py`（认证状态生命周期 pending/verified/expired，仅真实证书可 verified，绝不虚构），带测试。
- **视觉一致性审计诚实性护栏**：新增回归测试证明 `character_consistency`/`cmf_consistency`/`product_structure_consistency` 在无视觉后端时 `passed=False` 且 `requiring_vision=True`，绝不假通过；能力矩阵校验收紧：`partially_implemented` 项必须含非空 `current_limitation`。
- **干净环境验收一致性**：新增 `tests/test_command_coverage.py` 断言“README/SKILL 声明命令 == 已注册命令 == 有对应测试”，新增打包可复现性校验测试。
- 版本提升至 `5.3.0`，重新生成能力矩阵、`RELEASE_MANIFEST.json`、构建发布包与 SHA-256 清单并签名，提交并推送至 `origin/main`。

## Impact

- 受影响能力：UX（风险红黄绿、外部等待）、研究（证据可信度）、CAD（人体尺寸族）、工业化（认证状态）、Skill 质量、CI/打包。
- 受影响代码：
  - `SKILL.md`、`README.md`、`QUICKSTART.md`、`CHANGELOG.md`
  - `src/aipd_os/experience/`（新增 `risk_health.py`、`external_wait.py`；改 `views.py`）
  - `src/aipd_os/research/credibility.py`（新增）
  - `src/aipd_os/cad/anthropometry.py`（新增）
  - `src/aipd_os/supply_chain/certification.py`（新增）
  - `scripts/skill_quality_audit.py`（新增）、`scripts/capability_matrix.py`（证据收紧）
  - `tests/`（新增 `test_risk_health.py`、`test_external_wait.py`、`test_credibility.py`、`test_anthropometry.py`、`test_certification.py`、`test_command_coverage.py`、视觉护栏回归）
  - `.github/workflows/ci.yml`（增加 skill-quality 与命令覆盖校验 job）
- 新增能力域：所有者风险健康视图、外部等待视图。

## ADDED Requirements

### Requirement: 所有者风险红黄绿与外部等待视图
- 系统 SHALL 提供确定性风险健康状态（红/黄/绿）与供应商/实验室外部等待清单，供产品所有者无需内部代号即可阅读。
- **WHEN** 生成 `OwnerView.owner_update`
- **THEN** 输出含 `risk_health`（含红黄绿判定与理由）与 `external_wait`（供应商/实验室待办）的自然语言字段，且内部代号仅出现在 `details`。

### Requirement: 证据可信度 / 人体尺寸族 / 认证状态确定性深化
- 系统 SHALL 为证据可信度（来源×时效×假设/事实分离）、人体尺寸百分位族、认证状态生命周期提供确定性、可测试的实现。
- **WHEN** 调用对应模块
- **THEN** 返回结构化结果且绝不在缺真实证书/数据时虚构 `verified` 或尺寸值。

### Requirement: 视觉一致性审计诚实性护栏
- 系统 SHALL 保证无视觉后端时，character/CMF/product-structure 一致性维度绝不假通过，并明确 `requiring_vision`。
- **WHEN** 无 `vision_backend` 运行 `audit_page`
- **THEN** 三个维度 `passed=False` 且 `requiring_vision=True`。

### Requirement: 命令—测试覆盖一致性
- 系统 SHALL 保证 README/SKILL 声明命令、CLI 已注册命令、测试覆盖三方一致。
- **WHEN** 运行 `tests/test_command_coverage.py`
- **THEN** 验证每个声明命令均已注册且有对应测试，否则失败。

## MODIFIED Requirements

### Requirement: SKILL.md 渐进披露与准确性
- 刷新 SKILL.md 至 v5.3，补全全部一键命令，确认专业细节拆到 `references/`，消除隐含路径；以 `scripts/skill_quality_audit.py` 自检并入 CI。

### Requirement: 能力矩阵证据收紧
- `partially_implemented` 能力必须含非空 `current_limitation`；能力矩阵再生成后纳入 CI 校验。

## REMOVED Requirements

### Requirement: 指向 v5.0 的 SKILL.md 命令清单
**Reason**: 与当前 17 个已实现命令不符，违反触发描述准确性。
**Migration**: 由 `scripts/skill_quality_audit.py` 校验并与 `tests/test_command_coverage.py` 联动。