# V5_9_2 Baseline（Snapshot-Closed Runtime & Commit Integrity Closure）

生成日期：2026-08-12
阶段：v5.9.2 Change Set 1 —— 重新建立当前基线（未改任何代码）

## Source Identity

| 项 | 值 |
|---|---|
| git branch | `main` |
| HEAD | `4a0ac2261d8306b71cb83e8ed4b3d41afe8a46b6` |
| git describe | `v5.6.0-37-g4a0ac22` |
| working tree | clean；与 origin/main 同步 |
| PROVENANCE.source_commit | `ef190cd...`（tested commit；release evidence refresh commit 为 4a0ac22） |
| package version | 5.6.0 |
| Python | .venv（pyproject `>=3.9,<3.13`） |

## 测试基线（fresh）

| 项 | 值 |
|---|---|
| collected | 952 tests（用户独立收集一致） |
| 核心回归 `-m "not model_eval"` | 后台运行中（预期 944 passed / 3 failed = release evidence hash 需最终刷新） |

## 质量基线

- ruff/mypy：历史债务（未清零；本轮新代码 0 新增约束）。
- archive hygiene：用户 zip 0 pycache/0 pyc；测试运行自身 `__pycache__` 不得误判（P0-hygiene 处理见 CS11）。

## 结论

基线 HEAD `4a0ac22` 与用户 `AIPD-OS-main (5).zip` 的 archive comment 一致。v5.9.2 工作开始。
