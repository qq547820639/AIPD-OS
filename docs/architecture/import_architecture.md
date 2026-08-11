# Import Architecture：依赖方向规范（P1-5）

> 目标：明确依赖方向（scripts → src 单向；src 不得静态依赖 scripts），
> 并给出现状与目标。

## 1. 规范

1. **scripts/ → src/ 单向依赖**：`scripts/*.py` 可以 `import aipd_os.*`；
   `src/aipd_os/**` **不得**静态 `import scripts.*`。
2. **src 内部分层**：`execution/`、`product_truth/`、`state/`、`web/`、
   `experience/`、`cad/`、`tool_adapters/` 之间只允许通过已声明的公共 API
   引用，禁止互相深度 import 实现细节。
3. **CLI 动态加载需收敛**：`src/aipd_os/cli/commands.py` 用
   `importlib.import_module("manual_chain")` 等方式动态加载 `scripts/` 下的
   命令模块。这是当前唯一合法的「src 引用 scripts」通道，但它绕过了静态
   依赖图，目标是把这些命令下沉为 `src/aipd_os/` 内的正式模块后再移除
   动态加载。

## 2. 现状

- `tests/test_import_cycles.py` 用 AST 静态扫描 `src/aipd_os` 全部 `.py` 的
  import 语句构建模块依赖图，断言**无环**（忽略 stdlib / 第三方 / 条件导入
  失败）。
- 已知的 scripts 动态加载点（CLI 命令）：
  - `manual_chain` / `manual_chain_gate` / `cad_maturity_gate` 等由
    `cli/commands.py` 通过 `_import_module` 动态导入。
  - `state_service/mcp_server.py` 是独立入口，只依赖 `src/aipd_os.state`，不
    反向依赖 scripts。

## 3. 目标

1. 把 scripts 中的命令实现逐步下沉到 `src/aipd_os/`（如 `commands` 已部分
   存在），`scripts/` 仅保留薄 CLI 包装。
2. 移除 `cli/commands.py` 对 scripts 的动态 importlib 加载，改为静态 import。
3. 保持 `src/aipd_os` 内部依赖图无环（由 `test_import_cycles.py` 持续门禁）。
