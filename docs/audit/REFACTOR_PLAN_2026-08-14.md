# AIPD-OS 重构批次实施计划（2026-08-14，自主裁决版）

> 基线 HEAD：`1a20899`（ruff/mypy 全仓 0、1011 passed / 0 failed / 3 skipped / 2 deselected）。
> 目标：回答「项目是否如预想」——清除审查遗留的 6 处结构性/诚实性债务，使架构纯度与诚实原则回到设计意图。一次性迭代执行完。

## 0. 现状 vs 预想（偏差清单）

| 项 | 预想 | 现状 | 判定 |
|---|---|---|---|
| 分层纯净 | idea（数据模型层）不依赖 execution | `idea/research_provider.py:38-39` 反向依赖 execution（Q-3）；research→idea→execution 跨层链（N-4） | 偏差，需重构 |
| 模块粒度 | 文件可读可维护 | commands.py 1630 行；gate.py 979 行（五职责混居） | 偏差，需拆分 |
| 测试诚实 | 每条断言真实有效 | `test_behavior_contracts.py:43` `assert c in LOGIC_CONTRACTS or True` 恒真假断言 | 偏差，需修复 |
| 多租户隔离 | 租户参数真实生效 | `state/recovery.py:144-147` `list_objects` 的 tenant_id 参数被忽略 | 安全缺陷，需修复 |
| 构建可复现 | 生成脚本重跑不丢数据 | `registry_data.py`「自动生成勿手改」+ 末尾 7 项手写 product.* 块，重跑生成即丢 | 隐患，需修复 |
| 诚实标注 | 未实现能力显式可辨 | research 五能力 probe 恒 UNAVAILABLE 但无「未实现」显式标注 | 需修复 |

## 1. 重构项（R-1 ~ R-8）

### R-1（P0）测试诚实性：`or True` 假断言
- 位置：`tests/test_behavior_contracts.py:40-44`
- 现状：`assert c in LOGIC_CONTRACTS or True`（恒真）+ `assert callable(semantic_check) is True`
- 目标：断言必须真实。工程师先诊断 `BEHAVIOR_CONTRACTS` 与 `LOGIC_CONTRACTS` 的实际覆盖差距；诚实方案二选一：①为未覆盖契约补语义检查器（若差距小）；②引入显式 `KNOWN_UNCOVERED` 清单（测试断言 `覆盖集 = 契约集 - 已知缺口`），缺口在测试 docstring 与清单中诚实列出，且 `assert callable(...) is True` 简化为 `assert callable(...)`。

### R-2（P0，安全）recovery.list_objects 租户过滤
- 位置：`src/aipd_os/state/recovery.py:144-147`
- 现状：`tenant_id` 参数被忽略，返回 project 全部 entries（跨租户暴露风险；当前生产调用链仅 test 使用，但属真实缺陷）
- 目标：`tenant = tenant_id or self.tenant_id`，过滤 `entry["tenant_id"] == tenant`；`_project_entries` 行为不变。新增跨租户隔离测试（两个 tenant 注册同 project 对象 → 各自 list 只见己方）。
- 红线：`register_object`/`get_object`/`delete_object` 的既有租户语义不动（它们已正确）。

### R-3（P1，架构）Q-3/N-4 层次泄漏消除
- 位置：`src/aipd_os/idea/research_provider.py:38-39`（import ToolAdapter/external_blocked_error/ExecutionRouter）；`src/aipd_os/research/providers/researchstudio.py:39-42`（import idea）形成 research→idea→execution 链
- 目标：`idea/` 域不再 import `execution`；消除反向依赖链（依赖方向收敛为 execution/tool_adapters → idea，research 可依赖 idea 但不得反向）
- 方案自由度：工程师先诊断 ExecutionRouter/ToolAdapter 在 research_provider.py 中的实际用途（推测是 ResearchIntegration 的 link_evidence_for_claim 经 router 执行）；最小改动优先：①把需要执行语义的部分下沉为 typing.Protocol 或回调注入；②或把 ResearchIntegration 的执行部分迁移至 execution/tool_adapters 侧。不得引入循环依赖；`test_import_cycles` 与全量回归锁定。
- 验收：`grep -rn "execution" src/aipd_os/idea/` 零命中（除注释）；依赖方向实测 idea→execution 为 0。

### R-4（P1，结构）commands.py 拆分（1630 行）
- 现状：`src/aipd_os/cli/commands.py` 1630 行（deprecation 化后增长）；30+ cmd_* 函数 + legacy + helper 混居
- 目标：按域拆 `cli/commands_manual.py`（manual 相关）、`cli/commands_cad.py`（cad/validate/industrialize 相关）、`cli/commands_release.py`（release/test/eval/package/audit 相关）；`commands.py` 保留 intake/status/decide/init/resume/onboard/doctor/operate 等核心 + legacy 函数 + `COMMAND_FUNCS` 聚合
- 兼容：`commands.py` 内 re-export 全部被拆函数（`from .commands_manual import cmd_manual_*`），`aipd_os.cli.commands.<name>` 引用路径不变；`main.py` 无需改动（COMMAND_FUNCS 仍从 commands 导入）
- 验收：`cli/` 各文件均 < 700 行；全量回归 + `test_cli*` 全绿

### R-5（P1，结构）gate.py 拆分（979 行）
- 现状：`product_intelligence/gate.py` 承载 criteria 定义/评估/授权/eligibility/commit 事务/trust 推导
- 目标：静态 criteria 定义与纯函数抽至 `gate_criteria.py`（criteria 表、_criterion、severity 常量、_derive_trust/_json/_head_sha 等纯函数）；`gate.py` 保留 `GateEvaluation/ProductDefinitionGate` 主体并 re-export
- 验收：两文件均 < 700 行；`from aipd_os.product_intelligence.gate import *` 语义不变（__all__ 更新但导出集不变）；全量回归

### R-6（P1，构建）registry_data.py 手写块保护
- 现状：文件头「自动生成勿手改」，末尾 7 项 product.* 手写块（单引号）；重跑 `scripts/migrate_capability_registry.py` 丢块
- 目标：手写块并入生成源（migrate_capability_registry.py 的数据源）或独立文件被生成脚本合并；重跑生成脚本后 77 项完整（70+7）；文件头 docstring 同步更新
- 验收：新增测试或脚本校验：重跑生成脚本 → 输出与提交版本一致（含 product.* 7 项）；`load_default_registry` 仍 77 项

### R-7（P2，诚实/UX）N-3 显式标注 + doctor 可操作引导
- `registry`/`runtime.probe`：对 `research.fulltext/related_work/novelty_check/idea_spark/asset_extract` 五能力，probe 结果加 `"implementation_status": "not_implemented"` 字段（区别于外部依赖未配置）；doctor 输出对「未实现」与「外部依赖」分别给出可操作下一步（如「配置 AIPD_MODEL_API_KEY/BASE_URL 可启用产品智能转译」）
- 验收：doctor --json 与 prose 输出含引导；probe 测试锁定

### R-8（P2，文档）docstring 漂移清理
- `idea/__init__.py:5-11`（"Commit 12 填充"过时描述）、`idea/research_provider.py:3-4`（"只实现骨架"与实际不符）等——更新为当前事实

## 2. 执行顺序与 commit 策略

诊断先行（R-1/R-3 需先诊断）→ 按风险从低到高实施：
1. R-2（安全修复，独立 commit，行为变化需测试锁定）
2. R-1（测试诚实性）
3. R-8 + R-7（小改动）
4. R-6（构建）
5. R-4（commands 拆分）
6. R-5（gate 拆分）
7. R-3（层次泄漏，最后做，架构风险最高）

每项独立 commit + 相关测试；全部完成后全量回归 + 清单刷新 + 推送。

## 3. 质量门禁

1. 全量回归：1011+ 净增 / 0 failed（.venv，-m "not model_eval"，跑前清 __pycache__）
2. ruff/mypy 全仓保持 0（上一轮新基线，任何新代码不得破坏）
3. R-3 完成后依赖方向实测：idea→execution 为 0；无新增环
4. QA 独立复现 + 行为矩阵验证（重点 R-2 租户隔离、R-1 断言真实性）
5. 全部 commit 推送 origin/main；工作树 clean
6. 收口报告落盘 docs/audit/

## 4. 不在本轮（决策留待后续）

- **版本号双轨制**（pyproject 5.6.0 vs 功能 5.9.x）：属发布工程决策（升版需 README 首行/SKILL 声明/CHANGELOG 联动），建议正式 release 前单独处理
- v5.10 NPI（BOM/Cost/ValidationTest/Issue/MMDProjection）：Phase 2 路线图，Issue 表方案需产品决策
