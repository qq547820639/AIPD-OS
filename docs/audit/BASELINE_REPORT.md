# AIPD-OS Baseline Report

**Date**: 2026-08-12 (JST/UTC+8)
**Prepared by**: AIPD-OS Principal Engineering 团队（仓库接管第一阶段）
**Scope**: 在**任何代码修改之前**，对 AIPD-OS v5.6.0 的真实质量基线进行记录。
本报告不美化、不修码；先真实记录现状，作为后续 Foundation Stabilization 的对照基准。

---

## 1. 环境与版本

| 项目 | 值 |
|---|---|
| 仓库路径 | `/Volumes/Extra/CodeProj/AI全链路自研/AIPD-OS` |
| git branch | `main` |
| git commit (HEAD) | `2541be86444ad10a7f8a75c28daa43b1c785b4bd` |
| git tag 对照 | `v5.6.0` |
| 包版本 (pyproject.toml) | `5.6.0` |
| 包版本 (src/aipd_os/__init__.py) | `5.6.0` |
| 包版本 (src/aipd_os/state/__init__.py) | `5.6.0` |
| Python (venv) | 3.9.6（`.venv`，包已 editable 安装） |
| CadQuery | 2.5.2（`.[cad]` 已安装，真实 B-Rep 内核可用） |
| 工作树状态 | 基线采集前 clean；采集后已恢复 clean（见 §7） |

> 注意：README.md / QUICKSTART.md / SECURITY.md 仍宣称 v5.5.0，与代码 5.6.0 存在**版本漂移**（P0-16 CONFIRMED，详见核实矩阵）。

## 2. 测试基线（pytest）

命令均用 `.venv/bin/python -m pytest`，与 CI `release-ready` 同款参数。

| 套件 | 命令 | 结果 |
|---|---|---|
| 收集 | `pytest tests/ --collect-only -q` | **522 tests collected** |
| 主套件（CI 同款） | `pytest tests/ -m "not model_eval" -q` | **518 passed, 0 failed, 2 skipped, 2 deselected, 295 warnings** (215.95s) |
| 集成套件 | `pytest tests/ -m integration -q` | **15 passed, 0 failed, 2 skipped** (12.44s) |
| CAD golden loop | `pytest tests/test_cad_golden_loop.py -q` | **11 passed**（真实 CadQuery 内核） |
| Manual E2E | `pytest tests/test_manual_chain_e2e.py -q` | **1 passed** |
| Production release gate | `pytest tests/test_production_release_gate.py -q` | **10 passed** |
| Integration smoke | `pytest tests/test_integration_smoke.py -q` | **4 passed** |

**跳过项原因**：2 skipped（mailpit 未配置，HOLD）；2 deselected（`model_eval`，需真实外部模型端点）。

**Warnings (295)**：主要来自依赖库弃用告警（pyparsing / urllib3 / jsonschema 类），非业务代码失败。

## 3. 静态质量（非 CI 门禁）

> ci.yml 未配置 lint / typecheck job，以下为存量现状，**不代表 CI 门禁状态**。

| 工具 | 命令 | 结果 |
|---|---|---|
| ruff | `ruff check .` | **FAIL — 3298 errors**（337 fixable；大量为存量风格问题，如 tests/test_visual_honesty_guardrail.py:78 缺尾换行） |
| mypy | `mypy` | **FAIL — 140 errors in 51 files**（checked 199；样例：evals_runner/golden_projects.py:193 Path/str 类型冲突；tests/test_golden_projects_e2e.py:549 Optional 索引） |

## 4. 仓库审计与能力矩阵

| 工具 | 命令 | 结果 |
|---|---|---|
| repo audit | `python scripts/audit_repo.py` | **PASS** — has_sbom=true, has_release_signing=true, dependency_lock=true, mismatches=[], legacy_cad_conflicts=[]；untracked_or_generated 3 项为预存在产物 |
| capability matrix | `python scripts/capability_matrix.py --repo . --out /tmp/aipd_matrix` | **PASS** — fully_implemented=35 / partially_implemented=26 / external_dependency=9 / 其余=0 |
| schema check | `python -m aipd_os.scripts.schema_check` | **PASS** — 5 个 JSON schema 全部 OK |
| `aipd doctor` | `.venv/bin/aipd doctor` | **1 项硬失败** — `security.credentials`：本机环境存在未登记敏感 env（CODEBUDDY_GATEWAY_AUTH / CODEBUDDY_GATEWAY_PASSWORD / WORKBUDDY_PAC_RPC_TOKEN）；vision/model/image/mail 外部能力未配置（external_dependency 提示级）；cad_kernel=available |

## 5. 安全基线

| 项 | 状态 |
|---|---|
| gitleaks / pip-audit / license scan | CI 独立 job（本机未安装对应工具，未本地执行）；CI 侧历史配置见 `.github/workflows/ci.yml` |
| SBOM / 发布签名 | audit_repo 确认 has_sbom=true、has_release_signing=true |
| 已知安全注意项（本阶段核实，不改码） | P0-1 授权缺口 / P0-2 auth 引导循环 / P0-3 audit 遮蔽 / P0-4 默认 secret / P0-5 crypto 弱回退（详见核实矩阵） |

## 6. 已知能力限制（诚实声明）

| 能力 | 状态 |
|---|---|
| model_eval | 需外部模型端点 → CI 默认 deselected，绝不伪造输出 |
| mailpit / 邮件 | 未配置 → 2 tests skip（HOLD） |
| vision / image / mail 外部服务 | doctor 报 external_dependency |
| CAD | cadquery 2.5.2 可用（C2 全链路真实）；无内核时 ContractBackend 诚实封顶 C1 |
| research.search_papers | **配置 AIPD_RESEARCH_API_KEY 时仍返回 simulated 占位源**（P0-7 CONFIRMED，见核实矩阵） |

## 7. 基线采集副作用（重要）

运行测试套件会改写 **5 个 tracked 发布证据文件**（golden 测试副作用）：

```
releases/golden-projects/A-manual-chain/manual.pdf
releases/golden-projects/A-manual-chain/manual.zip
releases/golden-projects/A-manual-chain/report.json
releases/golden-projects/B-cad-engineering-change/report.json
releases/golden-projects/C-supply-chain/report.json
```

内容变化：`report.json` 的 `source_commit` 刷新为当前 HEAD、`generated_at` 更新；manual.pdf/zip 重新生成。
**影响**：golden 测试在跑测时写入 tracked 目录，污染基线与发布证据（发布证据应 pin 到已测 commit `d58ab14`）。
**本阶段处理**：已 `git checkout --` 恢复为 HEAD 状态，工作树恢复 clean。
**后续建议**：CI/预提交增加只读校验或在跑后还原；此问题列入 Foundation 阶段待办（golden E2E 证据隔离）。

## 8. 基线结论

- **测试：全绿**（主套件 518 passed / 0 failed / 2 skipped），是可靠的回归基线。
- **静态质量：存量欠债大**（ruff 3298 / mypy 140），但均非 CI 门禁，不阻塞现有发布流程。
- **安全：1 项环境级硬失败**（未登记敏感 env）；另有 6 项 P0 安全/诚实性审计问题已核实待修（见核实矩阵，不改本报告所依赖的现状）。
- **副作用：golden 测试写仓库**，须在后续修复。
