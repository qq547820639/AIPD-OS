# 发布物签名（Release Signing）

AIPD-OS 发布物通过 `scripts/sign_release.py` 签名，确保交付链路完整性。

## 签名机制

对每个发布物文件计算：

1. **SHA-256 摘要**：`<hex>  <filename>`
2. **HMAC-SHA256 分离式签名**：以环境变量 `AIPD_RELEASE_SIGNING_KEY` 为密钥，
   对文件字节计算 HMAC-SHA256，输出十六进制签名。

产物：
- `<file>.sha256`：摘要文本
- `<file>.sig`：签名（十六进制）

实现只依赖标准库（`hashlib` / `hmac`），无第三方依赖，输出确定。

> 说明：HMAC 签名适合在封闭的发布管道中做完整性校验。若需要面向公众的
> 非对称验签，可在发布管道中改用 GPG/`minisign` 等工具对 `.sha256` 文件签名，
> 本脚本的 SHA-256 与 `.sig` 约定可无缝衔接。

## 如何运行

### 生成签名

```bash
export AIPD_RELEASE_SIGNING_KEY='your-secret-signing-key'
python3 scripts/sign_release.py dist/aipd-os-5.0.0.tar.gz
```

输出：
```
signed: dist/aipd-os-5.0.0.tar.gz
  sha256: <hex>
  signature: <hex>
```

同时生成 `dist/aipd-os-5.0.0.tar.gz.sha256` 与 `dist/aipd-os-5.0.0.tar.gz.sig`。

### 校验签名

```bash
AIPD_RELEASE_SIGNING_KEY='your-secret-signing-key' \
  python3 scripts/sign_release.py --verify dist/aipd-os-5.0.0.tar.gz
```

输出 `verified: ... -> OK`（退出码 0）或 `FAILED`（退出码 1）。

### 在 CI 中集成

```yaml
- name: Sign release
  env:
    AIPD_RELEASE_SIGNING_KEY: ${{ secrets.AIPD_RELEASE_SIGNING_KEY }}
  run: python3 scripts/sign_release.py dist/aipd-os-5.0.0.tar.gz
```

## 密钥管理

- 密钥通过环境变量注入，**不提交到仓库**。
- 生产发布使用独立、轮换的密钥；泄露后立即轮换并重新签名。
- 本地开发可用任意临时密钥。

## 测试

`tests/test_release_signing.py` 验证 SHA-256 稳定、签名可验、篡改检测、
缺少密钥时退出码为 2。
