# AIPD MCP State Service

这是跨对话持久化的参考实现。它将每个项目存为独立 SQLite 数据库，并通过 MCP 工具暴露初始化、摘要、事实、决策和检查点操作。

## 本地运行

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export AIPD_DB_DIR=/persistent/path/aipd-projects
python mcp_server.py
```

## 生产化必须补充

- 身份认证与项目级授权；
- 多租户隔离；
- 加密、密钥管理和审计日志；
- 备份、迁移和高可用数据库；
- 网络传输配置和限流；
- MCP 注册/Plugin 打包及 `agents/openai.yaml` 中的真实依赖信息。

本会话无法替你部署一个长期在线的外部服务，因此交付的是可运行骨架和本地持久状态实现；部署完成后再把服务 URL/注册名写入 Skill 的依赖配置。
