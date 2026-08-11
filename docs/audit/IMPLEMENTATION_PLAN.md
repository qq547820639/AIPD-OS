# AIPD-OS Foundation Stabilization — 实施计划

**Date**: 2026-08-12 · **HEAD**: 2541be8 (v5.6.0)
**依据**: BASELINE_REPORT.md（基线全绿）+ P0_VERIFICATION_MATRIX.md（逐项核实）+ REPOSITORY_MAPS.md（五张地图）。
**原则**: 小 diff / 向后兼容 / 迁移安全 / 每 change set 真实跑测 / Gate 不过不进入下一阶段。

## 执行顺序（优先级从高到低，全部在 Foundation Gate 前完成）

| # | Change Set | 覆盖 P0/P1 | 涉及文件 | 规模 | 状态 |
|---|---|---|---|---|---|
| CS1 | 认证与授权边界（通配规范化 + 全量授权 + 管理员门控 + auth 引导 + audit 遮蔽） | P0-1, P0-2, P0-3 | state/db.py, auth.py, server.py + 新 test_authorization.py | 大 | ✅ 完成（含 CS1-FIX 冒充漏洞修复 + 403 语义） |
| CS2 | 默认 secret fail-closed + crypto 弱回退门控 | P0-4, P0-5 | state/server.py, auth.py, crypto.py, mcp_server.py + tests | 中 | ✅ 完成 |
| CS3 | Web 认证与批准修复 + 请求大小限制 | P0-13 | web/server.py, views.py + tests | 中 | ✅ 完成 |
| CS4 | Execution 幂等（side_effect_mode + idempotency_key） | P0-6 | execution/models.py, runs.py, execution_router.py, adapter.py + tests | 中 | ✅ 完成 |
| CS5 | Research honesty（真实 API + simulated 降级） | P0-7 | tool_adapters/research_adapter.py, execution_router.py + tests | 中 | ✅ 完成 |
| CS6 | ProductTruth 项目作用域 + metadata + 返工诚实 | P0-8, P0-9, P0-10 | product_truth/store.py, models.py, propagation.py, lineage.py + tests | 中 | ✅ 完成 |
| CS7 | Manual 外骨骼默认事实隔离（TBD + truth_gaps） | P0-11 | scripts/manual_chain.py + tests | 中 | ✅ 完成 |
| CS8 | Manual 状态统一（文档化决策） | P0-12 | docs（backup 集成列为后续） | 小 | ✅ 完成（文档化） |
| CS9 | CAD 参数契约单源 + semantic geometry hash | P0-15, P0-14 | cad/backends.py, evidence.py + tests | 小-中 | ✅ 完成 |
| CS10 | 版本单源 + 文档对齐 + truth/registry/import 文档 | P0-16, P1-3, P1-4, P1-5 | README/QUICKSTART/SECURITY/THREAT_MODEL/architecture/cli + 新测试 + docs/architecture/* | 小-中 | ✅ 完成 |
| CS11 | 异常处理治理（禁 `except: pass` 静默成功） | P1-6 | supervisor/recovery/execution_router + tests/test_exception_hygiene.py | 中 | ✅ 完成（19 处空 except 全处置） |
| CS12 | Supervisor package 化迁移 | P1-1 | scripts/aipd_supervisor.py → src/aipd_os/supervisor/ + wrapper | 大 | ✅ 完成（wrapper 兼容 + selftest_v4 exit 0） |
| CS13 | golden E2E 证据隔离 | 基线副作用 | tests/test_golden_projects_e2e.py + tests/test_golden_isolation.py | 小 | ✅ 完成（默认临时目录，pin 模式才写 tracked） |
| CS14 | ruff 增量清零 | 质量门 | 全部新增/修改 .py | 中 | 进行中（工程师） |

## 额外发现与处置
- **CS1-FIX（QA 独立复核发现，严重）**：`_inject_actor` setdefault 允许客户端 actor 覆盖认证身份（任意已认证用户可冒充管理员）→ 已修复（强制覆盖 + 403 语义 + 删除 server.py 本地重复 AuthError 类 + 4 个冒充向量测试）。
- **发布卫生**：BUNDLE_MANIFEST 曾打包 .venv-ci 的 5.5.0 dist-info 残留 → CS10 已修 regenerate_release_manifest.py 排除逻辑（不重建现有 bundle）。
- **清单 dev-sync**：按仓库惯例刷新 RELEASE/SOURCE/PROVENANCE 清单以同步代码哈希（未重建 bundle）。

## 依赖关系

```
CS1（state 层）→ CS2（同文件区，顺序）
CS3（web，独立文件区）→ 可与 CS2 并行
CS4/CS5（execution/tool_adapters，独立）→ 可与 CS1 并行（不同文件区）
CS6（product_truth，独立包）→ 可并行
CS7（scripts/manual_chain，独立）→ 可并行
CS9（cad，独立）→ 可并行
CS10（文档+测试，独立）→ 可并行
CS11（跨 scripts/execution/recovery）→ 依赖 CS1/CS4 完成后
CS12（supervisor 迁移）→ 依赖全部 P0 完成 + Gate 通过
```

## 每 Change Set 验收方式

1. 工程师按规格实现 + 自测（真实 pytest 输出）。
2. QA 独立复核（回归 + 边界/错误路径 + 诚实性检查）。
3. 主理人汇总运行结果，进入下一个 change set。
4. 全部完成后：Foundation Gate 全量回归（pytest 主套件 + ruff + mypy + audit_repo + capability_matrix + schema + doctor），输出 docs/audit/FOUNDATION_STABILIZATION_REPORT.md。

## Gate 判定

- Foundation Gate **PASS** 条件：主套件 0 fail（新增测试全部通过）；已修复项有回归测试；未破坏 CAD golden loop / manual E2E / production release gate / CLI 兼容；golden 测试写仓库副作用已处理。
- 不满足 → **HOLD**，修复后重跑，**不进入 Idea/Evidence 阶段**。

## 已知边界（本阶段不处理）
- ResearchStudio-Skills-All 不在工作区 → Phase 2 先定义 adapter/provider contract，不伪造实现。
- P1-2 状态合并不做大规模 DB 重写（用户禁止「为了统一架构一次性重写全部数据库」），先文档化 + 逐步收敛。
- ruff/mypy 存量 3298/140 errors 非 CI 门禁，仅对新增/修改代码保持新增零违规（不改存量欠债）。
