# AIPD-OS Architecture Boundary（v5.10）

> **Canonical Decision**: IdeaToLaunch 是唯一的 agent-facing orchestrator 入口。
> AIPD-OS 是执行后端（execution backend），提供 state management、execution routing、
> validation、issue tracking、readiness gate 等领域服务能力。

---

## 1. 职责划分

| 层级 | 组件 | 职责 | 不做什么 |
|---|---|---|---|
| Agent-facing | IdeaToLaunch | 用户对话入口、S0-S8 编排、决策卡片、agent orchestration | 不直接操作 AIPD-OS 内部 DB |
| Execution Backend | AIPD-OS | state management、execution routing、validation、issue tracking、readiness gate、BOM、cost | 不复制 IdeaToLaunch 的 S0-S8 方法论 |
| Contract | 文件/JSON | 版本化、可审计的数据交换 | 不通过 Python import 跨仓耦合 |

## 2. AIPD-OS 不是旗舰 Agent

AIPD-OS **不得**：

- 自称"AI全链路产品开发与交付主管"或类似旗舰 agent 定位；
- 声明 `allow_implicit_invocation: true`（agent metadata）；
- 在 `agents/openai.yaml` 或 `SKILL.md` 中重新声明自己是用户唯一对话入口；
- 复制 IdeaToLaunch 的 S0-S8 编排方法论；
- 引入对 IdeaToLaunch/Vencertia 的 Python import 或数据库读取依赖。

## 3. 互操作边界

- AIPD-OS ↔ IdeaToLaunch 的互操作**仅通过明确版本化的文件/JSON contract**；
- 不允许跨仓源码 import；
- 不允许直接读取对方数据库。

## 4. Invariant 检查

当 `project_boundary.md` 声明 AIPD-OS 不是主 agent-facing entry 时：

1. `agents/openai.yaml` 不得重新声明相反行为；
2. `SKILL.md` 不得宣传 AIPD-OS 是旗舰 agent 入口；
3. `README.md` 不得同时宣传 AIPD-OS 是独立旗舰 Agent。

违反任一 invariant 时，`tests/test_architecture_contracts.py` 应 FAIL。

## 5. 允许的能力

AIPD-OS 作为执行后端，允许提供：

- CLI 命令（`aipd <cmd>`）供人工或脚本调用；
- MCP server（`state_service/mcp_server.py`）供 agent 调用；
- 库 API（`import aipd_os`）供其他 Python 代码调用。

但这些能力的定位是**后端服务**，不是"agent 自主接管用户"。
