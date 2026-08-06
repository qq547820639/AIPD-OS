# AIPD-OS 版本真实性审计报告（v5.1）

- 生成时间：`2026-08-06T18:03:29`
- 仓库根目录：`/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS`

## 1. 仓库基本信息

- 默认分支：`main`
- 最新提交 SHA：`0934f84d9d8cae26adfc8a088ba3af2dc58c999b`
- 最新提交时间：`2026-08-06 16:06:12 +0800`
- pyproject 版本：`5.6.0`
- Git 标签：`v5.5.0`, `v5.6.0`
- `releases/` 目录存在：是

## 2. 文件树概览

- 顶层条目数：`45`
- 顶层目录文件数（一层）：

| 目录 | 文件数 |
| --- | --- |
| `.git/` | 8 |
| `.github/` | 0 |
| `.pytest/` | 0 |
| `.pytest_cache/` | 3 |
| `.release_keys/` | 2 |
| `.ruff_cache/` | 2 |
| `.trae/` | 0 |
| `.venv/` | 1 |
| `.venv-ci/` | 1 |
| `agents/` | 1 |
| `assets/` | 0 |
| `build/` | 2 |
| `dist/` | 3 |
| `docs/` | 2 |
| `evals/` | 13 |
| `evals_out/` | 0 |
| `migrations/` | 2 |
| `references/` | 36 |
| `releases/` | 4 |
| `scripts/` | 34 |
| `src/` | 0 |
| `state_service/` | 3 |
| `templates/` | 3 |
| `tests/` | 67 |

## 3. CI 状态

- 检测到 Workflow：12 个 job
- Job 列表：`unit`, `integration`, `schema-validation`, `maturity-consistency`, `cad-golden-loop`, `secret-scan`, `dependency-audit`, `license-scan`, `package-build`, `audit`, `skill-quality-and-coverage`, `release-ready`

## 4. Release Manifest 校验

- Manifest 版本：`5.6.0`
- 文件条目总数：`384`
- 哈希匹配：`384` / `384`
- 哈希不匹配：`0`

## 5. 未跟踪 / 生成文件

- 共 `23` 项：
  - ` M BUNDLE_MANIFEST.json`
  - ` M PROVENANCE.json`
  - ` M RELEASE_MANIFEST.json`
  - ` M SOURCE_MANIFEST.json`
  - ` M docs/audit/audit.json`
  - ` M docs/audit/audit.md`
  - ` M docs/audit/capability_matrix.json`
  - ` M docs/audit/capability_matrix.md`
  - ` M docs/audit/pytest-report.json`
  - ` M docs/audit/repository_snapshot.json`
  - ` M releases/aipd-os-5.6.0.zip`
  - ` M releases/aipd-os-5.6.0.zip.ed25519.sig`
  - ` M releases/aipd-os-5.6.0.zip.sha256`
  - ` M releases/aipd-os-5.6.0.zip.sig`
  - ` M releases/golden-projects/A-manual-chain/manual.pdf`
  - ` M releases/golden-projects/A-manual-chain/manual.zip`
  - ` M releases/golden-projects/A-manual-chain/report.json`
  - ` M releases/golden-projects/B-cad-engineering-change/report.json`
  - ` M releases/golden-projects/C-supply-chain/report.json`
  - ` M scripts/capability_matrix.py`
  - `generated .venv/lib/python3.9/site-packages/numpy/distutils/__pycache__`
  - `generated build/bundle_stage/src/aipd_os.egg-info`
  - `generated src/aipd_os.egg-info`

## 6. 遗留 CAD 冲突

- 未发现 CAD-L 级联记号或过度声称模式。

## 7. 交付产物完整性

- SBOM.md 存在：是
- 发布签名（RELEASE_SIGNING.md + scripts/sign_release.py）完备：是
- 依赖锁文件存在：是（`requirements-quality.txt`）

