# AIPD MCP State Service

这是跨对话持久化的参考实现。它基于 **单库多租户** 的 `AIPDStateDB`
（`src/aipd_os/state/db.py`，`tenants` / `user_access` / 项目行级授权，
非「每项目一个 SQLite」），并通过 MCP 工具暴露初始化、摘要、事实、决策
和检查点操作。

## 本地运行

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export AIPD_DB_DIR=/persistent/path/aipd-projects
# MCP service principal 认证（v5.7：缺失/弱 token 时 fail-closed 拒绝启动）
export AIPD_MCP_USER=alice
export AIPD_MCP_TOKEN=<alice 在 StateService 签发的有效令牌>
# server 模式强制要求强 secret 与强 encryption key（否则拒绝启动）
export AIPD_SECRET=<>=16 字符的强 secret>
export AIPD_ENCRYPTION_KEY=<>=16 字符的强加密密钥>
python mcp_server.py
```

## 认证与多租户（v5.7 Commit 2）

- MCP Transport 是**认证边界**：每次工具调用都会解析 `AuthenticatedPrincipal`
  （`AIPD_MCP_USER` + `AIPD_MCP_TOKEN`，token 必须是该用户的有效令牌），
  并把 `actor=principal.user_id` 注入 StateService；`actor=None` 仅保留给
  可信内部代码路径，transport boundary 永远不可达。
- 所有 MCP 工具的目标租户恒取 `principal.tenant_id`（调用方不可指定/伪造），
  因此 tenant A principal 无法触达 tenant B 项目；项目级访问走 `user_access`
  授权表，无授权即拒绝。
- 工具调用失败以结构化 JSON（`{"ok": false, "tool": ..., "error": ...}`）
  返回，而不是让 traceback 冒泡进 MCP 协议。
- 未安装 `mcp` 时本模块仍可导入（`_MCP_AVAILABLE=False`），但 `run()` 会
  明确报错拒绝启动。

## 已实现的生产化能力（在 `src/aipd_os/state/`）

- 静态加密（`crypto.py`：Fernet 优先，dev 回退 fail-closed）与敏感字段加密（`db.py`）；
- 密钥管理（`AIPD_ENCRYPTION_KEY` canonical / 别名兼容）与审计日志（`audit.py` 追加式 JSONL + DB）；
- 备份（`backup.py`）与迁移（`migrations.py`，`AIPDStateDB` 初始化即全链迁移）；
- 健康检查（`health.py`）与检查点恢复（`checkpoint.py` / `recovery.py`）。

## 仍需外部完成

- 网络传输配置和限流；
- MCP 注册/Plugin 打包及 `agents/openai.yaml` 中的真实依赖信息。

本会话无法替你部署一个长期在线的外部服务，因此交付的是可运行骨架和本地持久状态实现；部署完成后再把服务 URL/注册名写入 Skill 的依赖配置。
