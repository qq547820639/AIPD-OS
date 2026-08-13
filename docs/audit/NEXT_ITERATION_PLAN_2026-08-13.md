# AIPD-OS 下一轮迭代实施计划（2026-08-13，自主裁决版）

> 基线 HEAD：f536dac（上一批次收口后）。目标：一次性迭代执行完本轮全部可执行项。

## 0. 总体裁决

| 项 | 裁决 | 理由 |
|---|---|---|
| 批次 1：全仓 lint/mypy 清债 | ✅ 本轮执行 | 机械性债务，一次清完，测试锁定 |
| 批次 2：CLI 命令面统一 + 文档对齐 | ✅ 本轮执行 | 对目标用户（非技术产品负责人）最可感知的 UX 短板 |
| Phase 2：v5.10 NPI（制造就绪） | 📋 列入路线图，不本轮执行 | 相当于一个完整 minor 版本（v5.9 用了 10+ change set），且含未决产品决策（Issue 独立表 or 复用 changes），单轮硬上质量不可控——诚实原则 |

## 1. 批次 1：全仓存量 lint/mypy 清债

### 1.1 现状（实测基线）

- ruff：**2299 条**（src/ + tests/）：E501×202、UP035×183、W292×86、F401×70、I001×41、UP007×20、UP037×17、F841×13、UP015×8、E702×6、SIM102/103/105/108/110/115/222/300×25、B017/B027/B904×8、F811×4、F541×2、F821×1、UP012/034×3、W291×1、E741×3。其中 239 条可 `ruff check --fix` 安全修复。
- mypy：**152 errors / 59 文件**（files = src + tests）。

### 1.2 执行策略

| 类别 | 处理方式 |
|---|---|
| 可自动 fix（239） | `ruff check --fix`（W292/F401/I001/UP015/UP012/UP034/F541/SIM300/UP037 等） |
| E501 长行（202） | 代码行手工折行；URL/长字符串/表格/中文 docstring 类加 `# noqa: E501` 合理豁免（registry_data.py 已有文件级豁免不动） |
| UP035 deprecated-import（183） | 手工改为新路径（如 `typing.*` → PEP 585；弃用模块 → 新位置） |
| UP007/UP034 等 | 手工；`X \| None` 需确认文件有 `from __future__ import annotations`（无则补） |
| B/SIM 类 | 逐条人工判断：行为等价的修；涉及行为的加 `# noqa` 并注释原因，**不得改变任何运行时行为** |
| F821 undefined-name | 逐条核实（可能是真实缺陷或测试桩——**若为真实缺陷须在 commit message 与报告中点名**） |
| mypy 152 条 | 逐条修：补注解/cast/断言；根因为复杂泛型的加 `# type: ignore[reason]`（带理由，总量 ≤15 条且记录） |

### 1.3 红线

- **零行为变更**：本批次是纯等价重构（语法升级/import 排序/注解），任何行为变化即失败
- 不触碰：README/pyproject/docs/migrations/迁移断言/`registry_data.py` 的 noqa 豁免/requirements-quality.txt
- `__init__.py` 中的 F401 需核实 re-export 意图（`__all__` 覆盖的保留）
- tests/ 同样清理（pyproject 的 ruff src 与 mypy files 均含 tests）

### 1.4 验收

- `ruff check src/ tests/` → **0 违规**；`mypy src/ tests/` → **0 errors**
- 全量回归 `.venv/bin/python -m pytest -m "not model_eval"` → **989 passed / 0 failed**（±0 净增，因纯重构）
- 重生成 RELEASE_MANIFEST/SOURCE_MANIFEST（哈希必然变化）

### 1.5 commit 策略（分批，便于 review）

- C1：ruff 自动修复（239 条安全 fix）
- C2：E501 折行 + noqa 豁免
- C3：UP035/UP007 等 import/注解升级
- C4：B/SIM/F821 人工判断项 + mypy 152 条
- C5：清单刷新 + 最终回归数字

## 2. 批次 2：CLI 命令面统一 + 文档对齐

### 2.1 现状

legacy 命令 10 个与 one-click 主线语义重叠：`init-project`→`init`、`restore-project`→`resume`、`run-supervisor`→`run`、`project-summary`→`status`、`submit-decision`→`decide`、`run-manual-chain`→`manual generate`、`run-cad-chain`→`cad build`、`run-tests`→`test`、`run-evals`→`eval`、`build-release`→`package`。legacy 命令缺 `--json`；`cli/main.py:3` docstring 自称"10 个一键子命令"（实际 30+）；README 与 QUICKSTART 命令集互相矛盾；SKILL.md 引用已迁移进包的脚本路径。

### 2.2 执行策略（自主裁决的 deprecation 方案）

- **不删除** legacy 命令（兼容优先）；执行时向 stderr 打印 `DeprecationWarning: 'aipd X' 已废弃，请使用 'aipd Y'`（走 `warnings.warn(..., DeprecationWarning)`）
- legacy 命令补齐 `--json` 输出（与 one-click 一致）
- `usage` 命令输出更新；`cli/main.py:3` docstring 修正为真实命令数
- README 快速上手/FAQ 保持 one-click 主线（首行 v5.6.0 不动——test_version_consistency 硬约束）；QUICKSTART 全部命令改写为 one-click 并注明 legacy 对照表；SKILL.md 的 scripts/*.py 路径更新为 `aipd` 命令
- 改 README/QUICKSTART/SKILL.md 后重生成清单（test_packaging 硬约束）

### 2.3 验收

- 10 个 legacy 命令：功能不变 + 每个触发 DeprecationWarning + `--json` 输出合法
- `aipd usage` 列出全部命令；README 每条命令真实跑通（test_command_coverage 硬约束）
- 全量回归 989 passed / 0 failed（含新增 deprecation/文档一致性测试，净增少量）

## 3. Phase 2 路线图（下一批，不在本轮执行）

### 3.1 v5.10 NPI（制造就绪）

| 接口 | 现状 | 工作量 |
|---|---|---|
| BOM 表 | NOT_STARTED | 迁移 v13 + models + service + CLI |
| Cost 表 | NOT_STARTED | 同上 |
| ValidationTest 独立表 | STUB（JSON 引用占位） | 同上 + 与 Requirement.verification_test_refs 打通 |
| Issue 表 | **决策未定**（独立表 or 复用 changes） | 需产品决策先行 |
| MMDProjection | NOT_STARTED（仅 crosswalk 文档） | 文档→实现 |
| Manufacturing Readiness 与 ProductTruth/NPI Gate 打通 | PARTIAL | gate 扩展 |

节奏建议：契约先行 → 确定性实现 → 测试锁定（沿用 v5.9 节奏）；Issue 决策由产品经理许清楚出方案后拍板。

### 3.2 其他候选

- 经验沉淀：把「走读审查 → P0/P1/P2 清单 → 小批量实施 → QA 独立验证 → 收口」流程固化为 skill
- 生产 LLM Provider 实测：配置真实 OpenAI 兼容端点跑一次端到端（N-1 已就绪，仅需真实凭据）

## 4. 质量门禁（两批次共用）

1. 全量回归：989+ 净增 / 0 failed（.venv，-m "not model_eval"，跑前清 __pycache__）
2. ruff/mypy 全仓 0（批次 1 后成为新基线，批次 2 不得新增）
3. 每批次 IS_PASS 全局一致性审查；QA 独立复现 + 行为抽查
4. commit 分批推送 origin/main；最终工作树 clean（docs/audit/*.md 可 untracked）
5. 完成后重生成全部发布清单（SOURCE/BUNDLE/RELEASE/PROVENANCE 如受影响）
