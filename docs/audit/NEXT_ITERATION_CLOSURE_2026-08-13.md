# AIPD-OS 下一轮迭代收口报告：全仓清债 + CLI 统一（2026-08-13）

> 基线 f536dac → 交付 HEAD `1a20899`（9 commit 已推送 origin/main）。
> 执行依据：docs/audit/NEXT_ITERATION_PLAN_2026-08-13.md（自主裁决版）。

## TL;DR

两个批次一次迭代全部落地：**ruff 2299→0、mypy 152→0（296 文件）**，10 个 legacy 命令完成 deprecation 化（功能保留 + `--json` 补齐 + 入口可见废弃提示），文档对齐 one-click 主线。最终回归 **1011 passed / 0 failed / 3 skipped / 2 deselected**（989 → 1010 批次净增 21 → 1011 修复净增 1），QA 独立验证两轮全 PASS，「零行为变更」经 15 文件抽审 + C4a 全量 438 行 diff 逐条审读确认成立。

## 交付 commit（9 个）

| commit | 内容 |
|---|---|
| daa148c | C1 ruff 自动安全修复（253 条） |
| 086423b | C3 注解/import 现代化（PEP 585/604，实测 ~1800 条，为计划 10 倍——UP006×1100+UP045×509+UP035×171+UP007×20，机械等价升级） |
| d94c46a | C2 E501 长行清理（折行 + 187 条合理 noqa 豁免） |
| a647f74 | C4a B/SIM/F/E 人工判断项（438 行 diff 逐条等价重构或 noqa 保留） |
| ba6f27c | C4b mypy 152→0（补注解/cast/断言，新增 4 处带理由 type: ignore） |
| b17db5d | C5 清单刷新 + 回归 |
| 311ef14 | 批次2 legacy deprecation + `--json` + 21 条测试 |
| dd050e8 | 批次2 文档对齐（QUICKSTART 全量 one-click + legacy 对照表） |
| 1a20899 | DeprecationWarning 在 aipd 入口可见（main() 首行 simplefilter + subprocess 回归测试） |

## 关键成果

1. **F821 真实缺陷修复并点名**：`supply_chain/certification.py:115` 未导入 Union（惰性注解掩盖 NameError 隐患）→ `str | Path`。
2. **零行为变更实证**：全量回归在 py3.9.6 实跑 1011 passed；QA 对 15 个文件做非注解行过滤 = 0 逻辑行变更；无 future 的 7 个 `__init__.py` 零 PEP604 注解。
3. **legacy→主线对照**（10 条，均保留功能 + DeprecationWarning + `--json`）：init-project→init、restore-project→resume、run-supervisor→run、project-summary→status、submit-decision→decide、run-manual-chain→manual generate、run-cad-chain→cad build、run-tests→test、run-evals→eval、build-release→package。
4. **观察点 1 修复**：DeprecationWarning 在 `aipd` console-script 入口下被默认 filter 抑制（QA 发现）→ `main()` 首行 `warnings.simplefilter("default", DeprecationWarning)`；新增 subprocess 测试经真实入口进程验证。

## QA 验证（严过关，两轮）

- 第一轮：6 项验收全 PASS（git 真实性 / 独立回归 1010 / 零行为变更抽审 / legacy 实测 / 静态门禁双 0 / 文档对齐），发现观察点 1（入口可见性）与观察点 2（汇报口径偏差）
- 第二轮（修复后）：独立回归 **1011 / 0 / 3 / 2** 与实现方一致；实测 `.venv/bin/aipd project-summary --db <tmp>` stderr 可见"已废弃"且顺序正确；test_packaging 8 passed
- 最终判定：**QA PASS，无源码 Bug，全链路放行**

## 遗留记录（非阻塞）

- **观察点 2**：工程师汇报"13 个补 future import"无 git 证据（实际基线 282/295 已具备）——口径偏差，非代码缺陷
- **mypy type: ignore 新增 4 处**（均带理由）：evals/runner.py:170、evals_runner/completion.py:147（requests 无 stub）、supply_chain/mail.py:307（override 签名收窄）、state/crypto.py:30（cryptography 缺失回退）
- **5 处疑似缺陷记录未修**（零行为变更红线）：state/recovery.py list_objects tenant 过滤疑似缺失、test_behavior_contracts.py `or True` 恒真、state/server.py run_http 补死代码 return、test_execution_router.py 重复定义已删、evals_runner/scoring.py 注解与实现不符已修注解

## 当前仓库状态

- ruff / mypy：全仓 0（新基线——后续任何新代码必须保持 0）
- 回归：1011 passed / 0 failed / 3 skipped / 2 deselected
- 工作树 clean（docs/audit/*.md 未跟踪），HEAD=origin/main

## 下一步（Phase 2 路线图，见 NEXT_ITERATION_PLAN §3）

1. v5.10 NPI（BOM/Cost/ValidationTest/Issue/MMDProjection/Manufacturing Readiness）——Issue 独立表 or 复用 changes 需产品决策先行
2. 生产 LLM Provider 实测（N-1 已就绪，仅需真实凭据）
3. 5 处疑似缺陷评估立项
