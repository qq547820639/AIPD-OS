# 发布证据体系（Source / Bundle / Provenance）说明

> P0-1 发布证据体系重构。本文件说明三份独立证据的含义、生成方式与发布门禁，
> 以及「摘要 / MAC / 数字签名」三者的区别。实现见
> `scripts/release_evidence.py`、`scripts/sign_release.py`、`scripts/production_release_gate.py`。

## 1. 三份证据

生成入口：`scripts/release_evidence.py`。三份证据都以**最终 tag SHA**
（`git rev-parse HEAD`）为锚点，互不依赖、互不自引用。

| 证据文件 | 覆盖范围 | 关键字段 |
| --- | --- | --- |
| `SOURCE_MANIFEST.json` | 只覆盖「确定的源文件集合」（`git ls-files` 已跟踪文件），逐文件记录 `path/size/sha256` | `source_commit`、`version`、`coverage` |
| `BUNDLE_MANIFEST.json` | 对最终发布压缩包逐条计算 `sha256`，并记录 bundle 自身摘要 | `bundle_sha256`、`entries[]`、`entry_count` |
| `PROVENANCE.json` | 构建上下文与来源 | `source_commit`、`build_environment`、`build_time`、`dependency_lock`、`test_report`、`bundle_hash` |

### 排除规则（避免自引用/自变）

`SOURCE_MANIFEST` 通过 `SOURCE_EXCLUDE` / `SOURCE_EXCLUDE_PREFIXES` /
`SOURCE_EXCLUDE_SUFFIXES` 排除所有「生成后自身改变」的文件，包括本证据自身、
`BUNDLE_MANIFEST.json`、`PROVENANCE.json`、`RELEASE_MANIFEST.json`、`releases/`、
`build/`、`dist/`、`.venv/`、`__pycache__/`、`*.zip`、`*.step`、`*.sig`、`*.sha256` 等。
因此证据清单与磁盘不会因生成动作而互相漂移。

### 两轮生成

1. 第一轮：写 `SOURCE_MANIFEST.json` 与 `PROVENANCE.json`（此时尚无 bundle）。
2. 打包后第二轮：写 `BUNDLE_MANIFEST.json`，并把 `bundle_hash` 回填进 `PROVENANCE.json`。

测试中这两轮生成已覆盖（见 `tests/test_release_evidence.py` 的 `_make_repo`）。

## 2. 摘要 / MAC / 数字签名的区别

实现：`scripts/sign_release.py`。产物后缀区分清晰：

- **摘要（digest）**：文件 SHA-256，产物 `<file>.sha256`（文本 `<hex>  <filename>`）。
  仅证明内容指纹，不提供完整性密钥。
- **MAC（HMAC-SHA256）**：产物 `<file>.sig`（十六进制），密钥来自环境变量
  `AIPD_RELEASE_SIGNING_KEY`。**仅内部完整性校验**，对称密钥无法由第三方独立验证。
- **数字签名（Ed25519）**：产物 `<file>.ed25519.sig`（Base64），依赖 `cryptography`。
  **公开密钥非对称签名**，持有公钥的任何人可独立验签。

### CLI 用法

```bash
python scripts/sign_release.py --keygen                # 生成 Ed25519 密钥对
python scripts/sign_release.py --sign  aipd-os-5.6.0.zip   # Ed25519 数字签名
python scripts/sign_release.py --verify aipd-os-5.6.0.zip  # 用公钥验签
python scripts/sign_release.py aipd-os-5.6.0.zip           # 默认：MAC（HMAC-SHA256）
```

密钥默认存于仓库 `.release_keys/`（私钥 `chmod 600`），也可通过环境变量注入：
`AIPD_RELEASE_PRIVATE_KEY` / `AIPD_RELEASE_PUBLIC_KEY`。若 `cryptography` 不可用，
`--sign/--verify` 会**明确报错（退出码 3）**而非伪造成功。

## 3. 发布门禁：`--release-ready`

入口：`scripts/production_release_gate.py --release-ready`。一次性校验并全部通过才返回
`release_ready: true`（退出码 0），否则退出码 2。校验维度：

1. **工作区 clean**：`git status --porcelain` 为空。
2. **commit 一致性**：tag→SHA 与 PROVENANCE `source_commit` 均指向 HEAD。
3. **Source Manifest 零差异**：用与 `release_evidence` 相同逻辑重新生成，与磁盘逐条比对 `path+sha256`。
4. **Bundle Manifest 零差异**：重新生成与磁盘比对 `bundle_sha256` 与 `entries`。
5. **测试数字来自机器报告**：测试 passed/failed/total 必须从 pytest JSON 报告解析，不得硬编码。
6. **签名可验证**：用公开密钥验证 bundle 的 Ed25519 签名。
7. **安全扫描**：密钥模式扫描（`no_secrets`）、pip-audit CVE（尽力而为，`no_unacknowledged_cve`）。

> 修改任意被 SOURCE_MANIFEST 保护的文件后，`source_manifest_zero_diff` 与 `workspace_clean`
> 均会失败，门禁整体返回 `release_ready: false`。

## 4. `aipd audit` 可复现性

`scripts/audit_repo.py` 新增 `source_manifest_verification`：读取 `SOURCE_MANIFEST.json`，
逐文件核对磁盘 `sha256`，输出 `hash_mismatch_count`。「干净 clone」与「解压后的发布包」两种
场景的复现一致性由 `tests/test_release_evidence.py` 覆盖，断言 `hash_mismatch_count=0` 且
报告 HEAD 等于最终 tag SHA。

## 5. 测试

- `tests/test_release_evidence.py`：三份证据字段/互不引用、`BUNDLE_MANIFEST` 与解压内容一致、
  Ed25519 签名往返与篡改检测、摘要/MAC/数字签名产物区分、release-ready 通过/篡改失败/
  函数级集成、干净 clone 与解压包审计可复现。
- `tests/test_packaging.py`：`RELEASE_MANIFEST.json` 与 `SOURCE_MANIFEST.json` 内部一致性与
  磁盘哈希一致性（发布物齐全时执行；无清单时跳过）。