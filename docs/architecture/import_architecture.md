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
4. **网络出口唯一**：`src/aipd_os/**` 发 HTTP 只能经 `aipd_os.net.http.request()`，
   除该模块自身外不得出现 `urllib.request.urlopen` 直调（超时口径、瞬态重试、
   scheme 白名单因此只实现一次）。由
   `tests/test_net_egress_convergence.py` 按 AST 持续门禁。
5. **optional extra 不得成为 src 的硬依赖**：默认安装只有 `jsonschema`
   （实测 `pyproject.toml` `[project.dependencies]`）。`requests`（`full`）、
   `cadquery`（`cad`）、`cryptography`（`server`）、`mcp`（`server-mcp`）
   只允许**惰性导入 + 缺失时诚实降级**（现状：`state/crypto.py`、`cad/backends.py`
   均在函数体内导入）。`scripts/research/` 的连接器直接用 `requests` 是合法的——
   它的职责是给第三方自有的 `requests.Session` 挂载超时与重试策略，标准库做不到，
   且脚本不属于产品安装面（F-NET-01 之前 `evals_runner/completion.py` 正是违反了
   本条，才需要 `full` 才跑得动）。

## 2. 现状

- `tests/test_import_cycles.py` 用 AST 静态扫描 `src/aipd_os` 全部 `.py` 的
  import 语句构建模块依赖图，断言**无环**（忽略 stdlib / 第三方 / 条件导入
  失败）。
- 规范 4/5 由 `tests/test_net_egress_convergence.py` 持续门禁（F-NET-01）：
  AST 扫描 src/ 全部 `.py`（实测分母 211，且与读数一起断言，防「扫到空目录」
  假绿），除 `net/http.py` 自身外零 `urlopen` 直调、零 `requests` 导入；
  另用 5 种绕过形态的合成源码证明探针会开火。
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
