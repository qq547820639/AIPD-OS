# 贡献指南（Contributing）

感谢您对 AIPD-OS 的关注！请遵循以下约定，以保证代码质量与协作顺畅。

## 环境准备

- Python 3.9+（当前开发环境 3.9.6）
- 安装依赖：

```bash
python3 -m pip install --upgrade pip setuptools wheel
python3 -m pip install -e ".[dev]"
```

## 常用命令

```bash
# 运行全部单元测试（排除集成）
python3 -m pytest tests/ -q

# 运行全部测试（含集成）
python3 -m pytest tests/ -q

# 只运行安全模块测试
python3 -m pytest tests/test_prompt_injection.py tests/test_masking.py \
  tests/test_sbom.py tests/test_release_signing.py -q

# 代码风格检查
python3 -m ruff check src tests

# 类型检查
python3 -m mypy src

# 生成 SBOM
python3 -c "from aipd_os.security.sbom import generate_sbom; generate_sbom('.', 'dist/sbom.json')"

# 发布物签名
AIPD_RELEASE_SIGNING_KEY=your-key python3 scripts/sign_release.py dist/aipd-os-5.0.0.tar.gz
```

## 目录结构

- `src/aipd_os/`：核心包（state / security / execution / tool_adapters /
  layout / imggen / visual_audit / cli 等）
- `tests/`：pytest 测试（`conftest.py` 自动将 `src` 加入 `sys.path`）
- `scripts/`：工程脚本（supervisor、门禁、签名等）
- `docs/`：架构文档
- `references/`：政策与规范文档

## 提交 PR 流程

1. 从 `main` 创建功能分支：`git checkout -b feat/your-change`
2. 编写/补充测试，确保 `python3 -m pytest tests/ -q` 通过。
3. 运行 `ruff check` 与 `mypy` 并保持干净。
4. 更新 `CHANGELOG.md`（新增条目）与相关文档。
5. 提交并推送，在 GitHub 创建 Pull Request，描述变更与验收方式。
6. 通过 CI（单元测试、集成测试、schema 校验、secret 扫描）后合并。

## 编码约定

- 遵循 `pyproject.toml` 中 `[tool.ruff]` 配置（line-length 100，E/F/I/W/UP/B/SIM）。
- 新模块使用 `from __future__ import annotations`。
- 安全相关代码必须有测试；敏感数据默认掩码、权限默认拒绝（fail-closed）。
- 提交信息使用简洁的“为什么”而非“改了什么”。

## 行为准则

请遵守 `CODE_OF_CONDUCT.md`。
