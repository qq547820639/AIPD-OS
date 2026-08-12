# AIPD-OS v5.8.2 Baseline（Commit 1：HEAD 基线 + 全套验证）

> 生成时间：2026-08-12（Principal Software Architect，v5.8.2 Commit 1）
> 本报告是 v5.8.2 的事实基线。所有数字均来自**真实执行**（仓库 `.venv`，
> Python 3.9.6）。未运行项明确标注 `NOT_RUN`，绝不虚构 PASS。

## 0. 基线元信息

| 字段 | 值 |
| --- | --- |
| git status | `main`，clean（审计产物重生成前） |
| HEAD SHA | `e15d5f451cae72a46cfaffa43df2e7040fa7bfc8` |
| HEAD 时间 | 2026-08-12 07:48:14 +0800（`Refresh release evidence bound to HEAD df74c08 (post v5.8.1 commits)`） |
| 上一版本基线（提示词 source_commit） | `df74c08984e8daa8b9a891beb4c132e135487b49`（v5.8.1，代码一致；e15d5f4 仅为 evidence refresh） |
| package version | `5.6.0`（pyproject.toml `[project].version`） |
| Python | 3.9.6（仓库 `.venv`） |
| pytest | 8.4.2 |
| ruff | 0.16.1 |
| mypy | 1.19.1 |
| CadQuery / OCP | 2.5.2 / OCP OK（真实内核可用） |

## 1. 测试执行记录

| 套件 | 命令 | collected | passed | failed | skipped | deselected | 结果 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| collect-only | `pytest --collect-only -q tests` | 808 | - | - | - | - | OK |
| 核心套件 | `pytest tests/ -m "not model_eval" -q` | 808 | **803** | **0** | 3 | 2 | PASS |
| integration | `pytest tests/ -m integration -q` | 808 | **15** | **0** | 2 | 791 | PASS |
| Manual E2E | `pytest tests/test_manual_chain_e2e.py` | - | **11** | **0** | 0 | - | PASS |
| Production Release Gate | `pytest tests/test_production_release_gate.py`（同上命令合并） | - | （并入上项） | 0 | 0 | - | PASS |
| CAD Golden Loop | `pytest tests/test_cad_golden_loop.py` | - | **21** | **0** | 0 | - | PASS |
| CAD Contract Unify | `pytest tests/test_cad_contract_unify.py`（同上命令合并） | - | （并入上项） | 0 | 0 | - | PASS |

skipped 明细：
- `test_mail_protocol.py:202/240`：`AIPD_MAILPIT_*` 未配置 → 走 HOLD 断言（环境依赖，非回归）；
- `test_researchstudio_provider.py:233`：integration 标记，需 `AIPD_RESEARCHSTUDIO_INTEGRATION=1`（真实联网）。

## 2. 静态质量

| 工具 | 结果 |
| --- | --- |
| `ruff check .` | **3112 errors**（历史债务，见 §4 ratchet 说明；新代码必须 0 error） |
| `mypy src/aipd_os` | **120 errors in 48 files**（历史债务；checked 152 source files） |

## 3. 审计脚本

| 脚本 | 结果 |
| --- | --- |
| `python scripts/audit_repo.py` | OK；`untracked_or_generated` 仅 3 条生成物提示（.venv/build/src egg-info）；`legacy_cad_conflicts: []`；has_sbom/has_release_signing/dependency_lock 均 true |
| `python scripts/capability_matrix.py --repo . --out docs/audit` | OK；written: repository_snapshot.json / capability_matrix.json / capability_matrix.md；分类计数（tail 可见）external_dependency=9；重生成后审计产物绑定新 HEAD（source_commit=e15d5f4） |
| `python -m aipd_os.scripts.schema_check` | OK（cad_contract / fact / manual_chain_state / project_checkpoint / supervisor_project 全部通过） |

## 4. 基线结论

1. **测试基线全绿**：核心 803 passed / 0 failed / 3 skipped；integration 15/0/2；Manual+Release 11/0/0；CAD 21/0/0。与 v5.8.1 release evidence（803/0/3）一致，无回归。
2. **ruff/mypy 存在历史债务**（3112 / 120）：v5.8.2 静态质量 ratchet —— 所有**新增/修改**代码必须通过 `ruff check` 与 `mypy`（仅针对改动文件），不要求全仓清零。
3. **审计产物已绑定当前 HEAD**（capability_matrix 重生成 diff = provenance 收口的起点，随 Commit 1 提交）。
4. v5.8.2 待修复项见 `docs/audit/V5_8_2_RE_AUDIT_MATRIX.md`（本 Commit 1 同步产出）。

---
*本文件由 v5.8.2 Commit 1 生成；后续 Commit 不得伪造本基线数字。*
