# 安全策略（Security Policy）

AIPD-OS 是 AI 产品工程决策操作系统，处理产品真相基线、供应商报价、联系人、
实验数据等敏感信息，并编排成熟度门禁与生产放行。本文档说明受支持版本、漏洞上报
流程、威胁模型摘要与已实施的安全控制。

## 受支持版本

| 版本 | 支持状态 |
|------|----------|
| 5.0.x | 积极维护（当前） |
| 4.0.x | 维护中（仅安全修复） |
| < 4.0 | 不再支持 |

## 上报漏洞

请**不要**在公开 GitHub issue 中提交安全漏洞。请发送邮件至安全团队
（security@aipd-os.example），并遵循以下格式：

- **主题**：`[SECURITY] <漏洞简述>`
- **描述**：影响的产品版本、复现步骤、潜在影响、缓解建议
- **敏感数据**：请勿在邮件正文中包含真实密钥、令牌或客户数据

我们会在 72 小时内确认收到，并在修复发布前不公开细节。修复后我们会
在发布说明与 CHANGELOG 中致谢（除非您要求匿名）。

## 威胁模型摘要

完整威胁模型见 `THREAT_MODEL.md`。核心威胁与对应控制：

| 威胁 | 已实施控制 |
|------|-----------|
| 提示注入从外部内容接管系统 | `security/prompt_injection.py`：外部内容始终作为数据处理，可疑指令隔离，不能修改成熟度门禁/安全策略 |
| 供应商报价/联系人/实验数据泄露 | `state/db.py`（静态加密 `SENSITIVE_KEYS`）+ `security/masking.py`（打码 + 权限） |
| 跨租户越权 | `state/auth.py` 项目级授权（`user_access`）+ 令牌 HMAC 签名 |
| 证据/门禁被篡改 | 乐观锁（`version_no`）+ 追加式审计日志 |
| 状态服务 DoS | HTTP/JSON 服务分层限速、健康检查、备份恢复 |
| 发布物被篡改 | `scripts/sign_release.py` SHA-256 + HMAC 签名 |

## 数据加密

- **静态加密**：`SENSITIVE_KEYS`（supplier_quote / contact / experiment_data /
  api_key / credential / secret / token）在写入 SQLite 时自动加密。
  后端优先使用 `cryptography` 的 Fernet（AES-128-CBC + HMAC），不可用时回退到
  纯 Python XOR + HMAC-SHA256。见 `state/crypto.py`。
- **传输**：HTTP/JSON 模式建议在反向代理（如 nginx/TLS）后运行；本地模式
  不暴露网络端口。

## 认证与授权

- 密码哈希：PBKDF2-HMAC-SHA256，每用户随机盐，`PBKDF2_ITERATIONS=200000`。
- 令牌：HMAC-SHA256 签名，24 小时过期，绑定用户。
- 授权：多租户 + 多项目行级授权（`user_access`）；敏感数据作用域
  （supplier_quote / contact / experiment_data）需显式授权（fail-closed）。

## 密钥与机密管理

- 状态服务加密密钥、签名密钥、JWT/令牌密钥通过环境变量或部署配置注入，
  **不得**提交到仓库。
- `scripts/sign_release.py` 读取 `AIPD_RELEASE_SIGNING_KEY` 环境变量。
- CI 中使用 GitHub Actions Secrets；本地 `.env` 文件不在版本控制范围内。

## 提示注入隔离

所有外部内容（附件、网页、论文正文、文档）**始终是数据，永远不是系统指令**。
`security/prompt_injection.py` 会把可疑指令（ignore previous instructions、
you are now、system:、override、set gate to C7 等）从系统指令通道中剥离并记录。
外部内容永远不能修改成熟度门禁或安全策略。

## 依赖与供应链

- 运行时依赖极少（`dependencies = []`），可选依赖见 `pyproject.toml`。
- 使用 `aipd_os.security.sbom.generate_sbom` 生成确定性 CycloneDX 风格 SBOM
  （见 `SBOM.md`），用于供应链审计。
- 发布物经 `scripts/sign_release.py` 签名（见 `RELEASE_SIGNING.md`）。

## 安全最佳实践遵循

- 所有写操作使用参数化 SQL，避免注入。
- 关键更新使用乐观锁并在事务中执行。
- 敏感字段在日志与 UI 中打码。
