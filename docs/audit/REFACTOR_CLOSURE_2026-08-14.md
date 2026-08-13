# AIPD-OS 重构批次收口报告（R-1~R-8，2026-08-14）

> 基线 `1a20899` → 交付 HEAD `e245555`（11 commit 已推送 origin/main）。
> 执行依据：docs/audit/REFACTOR_PLAN_2026-08-14.md。QA 独立验收 9 项全 PASS、无源码 Bug。

## TL;DR

审查遗留的 6 处结构性/诚实性债务**一次性全部清除**：层次泄漏已做依赖方向真反转（非延迟 import 掩盖）、租户过滤安全缺陷修复、假断言移除并证明断言灵敏度、两大 979/1630 行文件拆分至每文件 <700 行且导出集逐项兼容、生成脚本重写为幂等、probe/doctor 诚实标注升级。最终回归 **1014 passed / 0 failed**，ruff/mypy 全仓 0 基线保持。

## 交付明细

| R 项 | commit | 结果 |
|---|---|---|
| R-2 租户过滤 | 49b158e | `list_objects` 按 `tenant_id or self.tenant_id` 过滤；QA 独立复现跨租户不泄漏 |
| R-1 测试诚实 | a2c76a4 | `or True` 恒真断言替换为 `c in semantic_checks` + 分层完备断言；QA 灵敏度证明（删映射则测试失败） |
| R-8 docstring | f17762d | Commit 12 时代描述清理 |
| R-7 标注+doctor | 02a2979 | probe 新增 `research_impl` 并列键（字符串值保留零破坏）；doctor 输出配置引导 |
| R-6 生成脚本 | 0ef89e7 | migrate 脚本重写（原数据源已删）；重跑 byte-identical，77=70+7 |
| R-4 commands 拆分 | a1494aa+82d8fd4 | 1630→520（拆 6 文件）；COMMAND_FUNCS=37 不变；main.py 未动 |
| R-5 gate 拆分 | d317e06 | 979→580+485；`__all__` 32 项与基线顺序一致 |
| R-3 层次泄漏 | 07a151d | ResearchToolAdapter/ResearchIntegration 下沉 `execution/research_integration.py`；idea 域零 execution import（AST 实测 85 条 import 边） |
| 清单刷新 | d2d9e1d、e245555 | SOURCE/RELEASE/PROVENANCE 刷新 |

## QA 独立验证要点（严过关）

- 独立全量回归 1014/0/3/2（11 分钟实跑，与实现方一致）
- R-3 AST 级实测：idea/*.py 全部 import（含函数体内）对外仅 providers/state 两包，EXECUTION VIOLATIONS: NONE
- R-2 独立脚本复现：default 租户只见 file_alpha、显式 tenantB 只见 file_beta
- R-1 灵敏度证明：模拟删除检查器映射 → missing 非空 → 测试真实失败
- R-6 重跑脚本 `git diff` 空（byte-identical）
- 唯一口径差异：commit 实为 11 个（工程师按 R 批次计数少计 1），非代码缺陷

## 与"预想"的对齐结论

| 设计意图 | 现状 |
|---|---|
| 分层纯净（idea 不依赖 execution） | ✅ 已达成（依赖方向真反转） |
| 模块粒度可控 | ✅ cli/ 与 PI 全部 <700 行 |
| 测试诚实 | ✅ 无恒真断言，灵敏度可证 |
| 多租户隔离 | ✅ 参数语义生效 |
| 构建可复现 | ✅ 生成脚本幂等 |
| 诚实标注 | ✅ probe/doctor 显式区分「未实现」与「外部依赖」 |

## 遗留（决策留待后续）

- 版本号双轨制（pyproject 5.6.0 vs 功能 5.9.x）：发布工程决策
- v5.10 NPI：Phase 2 路线图
- BOM 差异/风险视图等 capabilities 的「fully/partial」classification 由 probe 动态推导（既有机制）
