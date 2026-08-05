# Checklist — AIPD-OS v5.3 所有者体验与技能质量深化版

## 确定性模块（Task 1）
- [x] `experience/risk_health.py` 存在，`risk_health` 返回确定性红/黄/绿判定与理由。
- [x] `experience/external_wait.py` 存在，将 `external_waiting` 归并为供应商/实验室待办清单。
- [x] `views.py` 的 `OwnerView.owner_update` 与 `render_markdown` 已接入 `risk_health` 与 `external_wait`，内部代号仅在 `<details>`。
- [x] `tests/test_risk_health.py`、`tests/test_external_wait.py` 通过。

## 确定性深化（Task 2）
- [x] `research/credibility.py` 存在，证据可信度 = 来源×时效×假设/事实分离，缺数据返回 `not_verifiable`。
- [x] `cad/anthropometry.py` 存在，人体尺寸百分位族取值 + 校验，不臆造尺寸。
- [x] `supply_chain/certification.py` 存在，认证状态生命周期 `pending/verified/expired`，仅真实证书可 `verified`。
- [x] `tests/test_credibility.py`、`tests/test_anthropometry.py`、`tests/test_certification.py` 通过。

## 视觉一致性审计诚实性护栏（Task 3）
- [x] 无 `vision_backend` 时 `character_consistency`/`cmf_consistency`/`product_structure_consistency` 均 `passed=False` 且 `requiring_vision=True`。
- [x] 对应回归测试通过。

## 命令—测试覆盖一致性 + 打包可复现（Task 4）
- [x] `tests/test_command_coverage.py` 断言声明命令 == 已注册命令 == 有测试，通过。
- [x] 打包可复现性校验通过。

## 技能质量自检 + SKILL.md（Task 5）
- [x] `scripts/skill_quality_audit.py` 存在并可在 CI 运行。
- [x] `SKILL.md` 标题为 v5.3，补全全部一键命令，专业细节已拆到 `references/`。
- [x] `README.md`、`QUICKSTART.md`、`CHANGELOG.md` 同步更新。

## 能力矩阵证据收紧 + CI（Task 6）
- [x] `partially_implemented` 项均含非空 `current_limitation`。
- [x] `docs/audit/` 下 `repository_snapshot.json`、`capability_matrix.json`、`capability_matrix.md` 重新生成。
- [x] `.github/workflows/ci.yml` 新增 skill-quality / 命令覆盖校验 job。

## 版本提升、发布构建与交付（Task 7）
- [x] `pyproject.toml` 版本为 `5.3.0`，版本断言同步。
- [x] 全部测试通过（`aipd test` / `pytest`）、`aipd eval` 通过、黄金项目回归通过。
- [x] `RELEASE_MANIFEST.json` 重新生成，`releases/5.3.0/aipd-os-5.3.0.zip` 构建并签名，SHA-256 清单生成。
- [x] 已提交并推送 `origin/main`。