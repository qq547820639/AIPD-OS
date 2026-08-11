# AIPD-OS Repository Maps（仓库接管 · 第一版）

**Date**: 2026-08-12 · **HEAD**: 2541be8 (v5.6.0)
**来源**: 架构师探勘报告 + 主理人第一手源码核实 + 运行时实测。所有结论附 文件:行号。

---

## A. Package Map

| 区域 | 包/模块 | 角色 |
|---|---|---|
| runtime | `cad/` `execution/` `state/` `research/` `experience/` `supply_chain/` `product_truth/` `layout/` `security/` `web/` `evals_runner/` `mail/` `imggen/` `providers/` `tool_adapters/` `cli/` `config.py` | 真实实现 |
| compatibility/helper | `registry.py`（能力元数据 + 运行时 probe，registry.py:47-306）、`registry_data.py`（自动生成静态数据）、`scripts/`（schema_check）、`telemetry/` `logging_utils.py` | 辅助层 |
| registry 三级 | `CapabilityRegistry`（src/aipd_os/registry.py:88）✓；`AdapterRegistry`（execution/registry.py:10）✓；`ProviderRegistry` ✗（providers/ 为 SDK 包） | P1-4 部分收敛 |
| legacy | `scripts/aipd_state.py` → 旧 `aipd_store.py:AIPDStore`（独立遗留入口，非 src state） | 遗留 |
| 状态碎片 | AIPDStateDB（主 DB）· supervisor_work_items（Supervisor 表）· ProductTruthStore（独立库）· ClosureStore（execution/closure_core）· Manual JSON（scripts/manual_chain.py）· Object Store（LocalStateBackend）· RunStore（execution_runs） | P1-2 需梳理 |

**重复实现风险**：`decisions` 表同时存在于 state/db.py（复合主键含 tenant）与 scripts/aipd_supervisor.py:46-50（仅 decision_id 主键）——两处 CREATE TABLE IF NOT EXISTS 同表名不同 schema，以先建者为准，属隐藏耦合。

## B. Entry Point Map

| 入口 | 位置 | 调用方 |
|---|---|---|
| `aipd` CLI | pyproject.toml:56 → cli/main.py:326 → commands.py:1312-1353（34 命令） | 控制台/CI |
| Supervisor | scripts/aipd_supervisor.py:262 main（init/add-work/next/complete/fail/run/status） | tests、selftest_v4.py:8、CLI 动态加载（commands.py:118,164,455,541,570） |
| 状态服务 | `python -m aipd_os.state.server`（server.py:335 main → run_http） | HTTP/JSON RPC |
| MCP | state_service/mcp_server.py:25,109 → StateService 薄层 | MCP 客户端 |
| Web | `aipd ui`（commands.py:1293-1306）→ web/server.py:46 OwnerHandler + views.py WebConsole | 浏览器 |
| Evals | evals_runner/cli.py:87,107 | CI/脚本 |

## C. Dependency Graph

- **state 包无环**：health.py:10 `from . import migrations`、server.py:21-28 相对子模块导入；包内无 `from aipd_os.state import`（0 命中）。
- **re-export 偏重**：research/__init__.py（约 30 行 __all__）> state/__init__.py（38 名）> experience > supply_chain > execution。P1-5：内部 runtime 应改从子模块导入，__init__ 保留兼容 re-export。
- **高 fan-in**：`state/db.py AIPDStateDB`（cli/web/mcp/recovery 全依赖）；`execution/execution_router.py`（supervisor + closure.py:20）；`experience/views.py`。
- **依赖方向（关键）**：scripts→src 单向（8 个脚本）；src→scripts **动态反向依赖存在**：cli/commands.py:42-48 `_import_module` 加载 aipd_supervisor/manual_chain/cad_maturity_gate/production_release_gate/sign_release/audit_repo/capability_matrix；registry.py:252-258 probe 临时把 scripts 加入 sys.path。**P1-1 高危点**：核心 Supervisor 在 scripts，src CLI 反向动态依赖 scripts。

## D. State Ownership Map

| 状态对象 | 存储 | Canonical Owner | 租户/项目列 |
|---|---|---|---|
| Project/Fact/Evidence/Decision/Risk/Deliverable/Gate/Change/Checkpoint | AIPDStateDB（state/db.py，复合主键含 tenant_id+project_id） | StateService | ✓ |
| user_access/sessions | AIPDStateDB | AuthManager | ✓（user_access 含 tenant/project） |
| supervisor_work_items/phase_runs/capabilities/reviews/lineage/claims | Supervisor 表（scripts/aipd_supervisor.py:17-51） | Supervisor | 仅 project_id，**无 tenant_id** |
| product_truth/truth_lineage/rework_tasks | ProductTruthStore（product_truth/store.py:19-52） | ProductTruthStore | **无 tenant/project（P0-8）** |
| execution_runs | RunStore（execution/runs.py:20-47） | ExecutionRouter | 有 project_id，无 tenant_id |
| 附件/manual_batch/visual_bible 对象 | ObjectStore/LocalStateBackend + attachment index | UnifiedStateService | ✓ |
| Manual 状态（pages/prompts/batches） | `.manual.json`（scripts/manual_chain.py，独立 JSON） | ManualChain | 仅 project_id 字段 |
| 闭包运行 | ClosureStore（execution/closure_core.py） | ClosureEngine | 待查 |

**回答「一个 project 的 canonical truth 在哪里」**：主事实在 `AIPDStateDB.facts`（epistemic 状态 V/S/C/E/A/P/T/R + confidence + source）；但 Product Truth 级对象、Supervisor 工作项、Manual 状态、执行记录**分散在多个独立存储**，互不统一 → P1-2「统一状态 Ownership」是真实架构债务。registry_data.py:17 自述「全库无独立 product_truth/facts 表」，印证 ProductTruthStore 与主库割裂。

## E. Execution Map（主链）

```
Owner → CLI `aipd run`（commands.py:445）
  → Supervisor.run_supervisor（aipd_supervisor.py:169-247）
      next_work（领取+依赖，95-107）
      → decision_policy.should_ask_decision（decision_policy.py:45-80）/ build_decision_package（87-138）
      → capability floor 检查（217-222）
  → ExecutionRouter.run（execution_router.py:67-155）
      discover（能力可用性）→ validate_input → RunStore.create_run（runs.py:97）
      → 退避重试（129-134，无幂等保护 → P0-6）
      → _try_fallback（195-240）→ _finalize_success（161-193）
          adapter.execute → normalize → collect_artifacts → persist_evidence → canonical_hash
      → status: succeeded / fallback / blocked_external / failed
  → ToolAdapter ABC（adapter.py:100；external_blocked 写外部任务包 adapter.py:86-97）
  → 内置 10 适配器（tool_adapters/builtin.py:25-38）
  → RunStore.execution_runs 持久化（runs.py:20-47）
  → Supervisor 侧：_register_outputs（capabilities+lineage，143-146）；_quality_gate（仅查 evidence/output_hash，147-159）
  → Gate 链：cad_maturity_gate.py:63（C0-C7 累积阶梯，RUNTIME_MAX 封顶 37-42）
            → production_release_gate.py:99 check_requirement + :167 run_evidence_checks（167-302）
            → claims（cad_maturity_gate.py:108-116）→ CLI validate/release check（commands.py:895-944）
```

**注意**：Web/operate 路径（experience/operations.py run_operation_loop）**不经过 Router/Supervisor**，仅状态机推进（views.py:537-539 以 approved=True 调用）→ P0-13。

**执行链风险点**：
1. `_finalize_success` 无条件标 succeeded（execution_router.py:115-117）——对 simulated 结果零感知（P0-7，research_adapter.py:41-66 配置 key 后仍返回 simulated 占位源且不抛错）。
2. 重试循环直接重复 `adapter.execute()`（execution_router.py:112-134），无 side_effect_mode/幂等保护（P0-6）。
3. Supervisor 把 status=succeeded 的执行注册为 capability available + lineage executed_via（aipd_supervisor.py:227-232），quality gate 不过滤 simulated（147-159）。

## 后续说明
- ResearchStudio-Skills-All **不在当前工作区**（maxdepth 4 搜索无命中）→ Phase 2 按「先定义 adapter/provider contract，不伪造实现」处理。
- 本地图基于静态走读 + 单次运行核实；随重构推进需持续更新。
