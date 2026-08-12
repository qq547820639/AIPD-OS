# V5_9_1 Baseline（Product Definition Integrity & Runtime Closure）

生成日期：2026-08-12
阶段：v5.9.1 Change Set 1 —— 重新建立当前基线（未改任何代码）

## Source Identity

| 项 | 值 |
|---|---|
| git branch | `main` |
| HEAD | `3a985380a7acf4d883fcd119c45e17a6bdb723f8` |
| git describe | `v5.6.0-28-g3a98538`（package version 仍为 5.6.0；v5.8/v5.9/v5.9.1 均为 workstream 名，非 semver release） |
| working tree | clean |
| 与 origin/main | 同步（0 个领先 commit） |
| Python | .venv（项目 pyproject target py39；本机运行 3.13 venv） |
| package version | 5.6.0（pyproject.toml line 7） |
| PROVENANCE/SOURCE_MANIFEST | 绑定 `3a98538`（README 重写后刷新版） |

## 测试基线

| 项 | 值 |
|---|---|
| collected | 902 tests（`--collect-only -q`） |
| 核心回归 `-m "not model_eval"` | **897 passed / 0 failed / 3 skipped / 2 deselected** |
| skipped 明细 | test_mail_protocol.py ×2（AIPD_MAILPIT_* 未配置，HOLD 断言）；test_researchstudio_provider.py（integration: requires internet） |
| deselected | model_eval 2 项 |
| 命令 | `python -m pytest tests/ -m "not model_eval" -q`（189.05s） |

## 质量基线

| 项 | 值 |
|---|---|
| ruff | 历史债务（未清零；本轮约束：新代码 0 新增） |
| mypy | 历史债务（未清零；本轮约束：新代码 0 新增） |

## 与 v5.9（c662f65）基线差异

+2 tests（README 重写无功能变更；packaging/hygiene 类断言随 evidence 刷新同步）。

## 结论

基线真实、可复现。V5_9_1 工作开始于 HEAD `3a98538`。
