# Capability Registry：三级职责划分（P1-4）

> 目标：明确 CapabilityCatalog → AdapterRegistry → ProviderRegistry 的三级职责，
> 以及兼容别名政策。

## 1. 三级职责

| 层 | 模块（现状/未来） | 职责 | 数据/对象 |
|---|---|---|---|
| **CapabilityCatalog** | `src/aipd_os/registry.py`（现状） | 能力矩阵的唯一事实来源：声明每项能力的 id/name/domain/declaration_file/implementation_file/entry_point/run_command/unit_test/integration_test/e2e_evidence/current_limitation；classification 由 `probe_classification` 运行时按证据推导，不静态写死 | 声明式能力条目 + 校验子（schema/存在性/入口可调用/证据时效） |
| **AdapterRegistry** | `src/aipd_os/execution/registry.py`（现状） | 把能力标识绑定到可执行适配器：register/get/all/discover_all；一个 capability_id 只允许一个 adapter（重复注册抛错） | `ToolAdapter` 实例（capability_id → adapter） |
| **ProviderRegistry** | `src/aipd_os/providers/sdk.py`（现状实现，Commit 7E） | 把 adapter 绑定到具体 provider/后端实例（模型端点、文生图、CAD 内核、邮件 SMTP 等），负责凭据/端点解析与真实调用；未配置时诚实标记 external_dependency | provider 实例（adapter → provider） |

职责边界：Catalog 回答「有哪些能力、证据是否齐备」；AdapterRegistry 回答
「这个能力由哪个适配器执行」；ProviderRegistry 回答「这个适配器背后用哪个
真实后端」。三者单向依赖：Catalog → AdapterRegistry → ProviderRegistry，
禁止反向。

## 2. 兼容别名政策

- 能力标识是稳定契约；重命名必须保留旧 id 作为别名映射到新实现，至少一个
  发布周期内 `AdapterRegistry.get(old_id)` 仍可解析。
- `ToolAdapter.capability_id()` 是唯一注册键；`execution/models.py`
  `ExecutionRecord.adapter_id` 优先取 capability，缺省回退 `tool`，保证新旧
  记录字段兼容（`from_db_row` 对缺失列取默认值）。
- Catalog 中 entry_point/run_command 与 AdapterRegistry 的 capability_id 若
  不一致，以 `probe_classification` 的运行时证据为准并记录 warning，不静默。
