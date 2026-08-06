# 发布物签名（Release Signing）

AIPD-OS 发布物通过 `scripts/sign_release.py` 签名，确保交付链路完整性。

## 签名机制

对每个发布物文件，区分三样东西（产物后缀清晰）：

1. **摘要（digest）**：文件 SHA-256，产物 `<file>.sha256`（文本 `<hex>  <filename>`）。
   仅证明内容指纹，不提供完整性密钥。
2. **MAC（HMAC-SHA256）**：产物 `<file>.sig`（十六进制），以环境变量
   `AIPD_RELEASE_SIGNING_KEY` 为密钥。**仅内部完整性校验**，对称密钥无法由第三方独立验证。
3. **数字签名（Ed25519）**：产物 `<file>.ed25519.sig`（Base64），依赖 `cryptography`。
   **公开密钥非对称签名**，持有公钥的任何人可独立验签。

摘要与 MAC 只依赖标准库（`hashlib` / `hmac`）；Ed25519 需 `cryptography`，若不可用，
`--sign/--verify` 会明确报错（退出码 3）而非伪造成功。

## 如何运行

### 生成 Ed25519 密钥对

```bash
python3 scripts/sign_release.py --keygen
```

密钥默认写入仓库 `.release_keys/`（私钥 `chmod 600`），也可用环境变量
`AIPD_RELEASE_PRIVATE_KEY` / `AIPD_RELEASE_PUBLIC_KEY` 覆盖路径。

### 生成数字签名（Ed25519）

```bash
python3 scripts/sign_release.py --sign dist/aipd-os-5.0.0.tar.gz
```

输出 `signed (Ed25519): ...`，生成 `dist/aipd-os-5.0.0.tar.gz.ed25519.sig`。

### 校验数字签名

```bash
python3 scripts/sign_release.py --verify dist/aipd-os-5.0.0.tar.gz
```

输出 `verified: ... -> OK`（退出码 0）或 `FAILED`（退出码 1）。

### 内部完整性（MAC）

```bash
export AIPD_RELEASE_SIGNING_KEY='your-secret-signing-key'
python3 scripts/sign_release.py dist/aipd-os-5.0.0.tar.gz       # 默认：MAC
python3 scripts/sign_release.py --hmac dist/aipd-os-5.0.0.tar.gz # 显式标注为 MAC
```

生成 `dist/aipd-os-5.0.0.tar.gz.sha256` 与 `dist/aipd-os-5.0.0.tar.gz.sig`。

## 密钥管理

- 私钥通过文件或环境变量注入，**不提交到仓库**（release-ready 门禁会扫描拒绝密钥模式）。
- 生产发布使用独立、轮换的密钥；泄露后立即轮换并重新签名。
- 本地开发可用任意临时密钥。

## 测试

- `tests/test_release_evidence.py`：Ed25519 签名往返与篡改检测、摘要/MAC/数字签名产物区分。
- 发布门禁 `scripts/production_release_gate.py --release-ready` 会验证 bundle 的
  Ed25519 签名可被公开密钥独立验证。
