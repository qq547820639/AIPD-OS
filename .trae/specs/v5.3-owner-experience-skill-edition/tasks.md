# Tasks — AIPD-OS v5.3 所有者体验与技能质量深化版

> 目标：只针对 v5.2 审计出的真实缺口增量补齐，不重写已完整实现且有测试证据的能力。
> 所有任务完成后需通过 `tests/` 全部测试、`scripts/capability_matrix.py` 重新生成矩阵、`scripts/skill_quality_audit.py` 自检、构建签名发布包并提交推送 `origin/main`。

## Task 1: 确定性模块——风险红黄绿 + 外部等待视图 ✅
实现 `src/aipd_os/experience/risk_health.py`（由风险影响 × 状态 × 外部等待推导红/黄/绿健康状态）与 `src/aipd_os/experience/external_wait.py`（将 `external_waiting` 归并为供应商/实验室待办清单），并接入 `OwnerView.owner_update` 与 `render_markdown`；普通用户默认只看到自然语言，内部代号仅在 `<details>`。
- 输入：`project_summary`/`resume_summary` 中的 `top_risk`、`risks`、`external_waiting` 等字段。
- 输出：`risk_health`（`traffic_light`∈{red,yellow,green} + `summary` + `reason`）与 `external_wait`（`supplier`/`lab` 待办的自然语言清单）。
- 验证：新增 `tests/test_risk_health.py`、`tests/test_external_wait.py`；`tests/test_experience.py` 通过。

## Task 2: 确定性深化——证据可信度 / 人体尺寸族 / 认证状态
为三项部分实现能力补确定性、可测试的逻辑：
- `src/aipd_os/research/credibility.py`：证据可信度评分 = 来源可信度 × 时效衰减 × 假设/事实分离，缺数据时返回 `not_verifiable` 而非虚构分数。
- `src/aipd_os/cad/anthropometry.py`：人体尺寸百分位族数据表 + 按族/百分位取值 + 校验，缺数据时绝不臆造尺寸值。
- `src/aipd_os/supply_chain/certification.py`：认证状态生命周期 `pending/verified/expired`，仅真实证书可 `verified`，绝不虚构。
- 验证：新增 `tests/test_credibility.py`、`tests/test_anthropometry.py`、`tests/test_certification.py`。

## Task 3: 视觉一致性审计诚实性护栏回归
确认 `visual_audit/auditor.py` 的 `character_consistency`/`cmf_consistency`/`product_structure_consistency` 在无视觉后端时 `passed=False` 且 `requiring_vision=True`，绝不假通过。
- 验证：新增回归测试（可并入 `tests/test_visual_golden.py` 或独立文件），断言三个维度在无 `vision_backend` 时诚实 `requiring_vision`。

## Task 4: 命令—测试覆盖一致性 + 打包可复现校验
- 新增 `tests/test_command_coverage.py`：断言“README/SKILL 声明命令 == CLI 已注册命令 == 有对应测试”三方一致。
- 新增打包可复现性校验（复用 `tests/test_packaging.py` 或新增断言）。

## Task 5: 技能质量自检脚本 + SKILL.md 刷新
- 新增 `scripts/skill_quality_audit.py`：渐进披露与命令清单一致性自查，并入 CI。
- 刷新 `SKILL.md` 标题至 v5.3，补全全部一键命令（`init`/`intake`/`resume`/`status`/`run`/`decide`/`manual plan`/`manual generate`/`cad preflight`/`cad build`/`industrialize`/`validate`/`audit`/`release check`/`test`/`eval`/`package`），确认专业细节已拆到 `references/`，消除隐含路径。
- 同步更新 `README.md`、`QUICKSTART.md`、`CHANGELOG.md`。

## Task 6: 能力矩阵证据收紧 + CI 更新 ✅
- 收紧 `scripts/capability_matrix.py`：`partially_implemented` 项必须含非空 `current_limitation`，否则失败。
- 重新生成 `docs/audit/repository_snapshot.json`、`capability_matrix.json`、`capability_matrix.md`。
- 更新 `.github/workflows/ci.yml`：新增 skill-quality 与命令覆盖校验 job。

## Task 7: 版本提升、发布构建与交付 ✅
- 版本提升至 `5.3.0`（`pyproject.toml` 及版本断言）。
- 运行全部测试（`aipd test` / `pytest`）、`aipd eval`、黄金项目回归。
- 重新生成 `RELEASE_MANIFEST.json`，构建签名发布包 `releases/5.3.0/aipd-os-5.3.0.zip` 并生成 SHA-256 清单。
- 提交并推送 `origin/main`。

# Task Dependencies
- Task 1、2、3、4 相互独立，可并行。
- Task 5 依赖 Task 4（命令清单一致性以 Task 4 的注册/测试清单为准）。
- Task 6 依赖 Task 2、3（能力实现状态影响矩阵证据）与 Task 5（SKILL 命令清单）。
- Task 7 依赖 Task 1–6。