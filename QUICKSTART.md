# 快速开始（Quick Start）

AIPD-OS v5.0 —— AI 产品工程决策操作系统。从一行产品构想开始，逐步推进到
工程基线、CAD、工业化、验证与生产发布。

## 0. 准备

```bash
python3 -m pip install -e ".[dev]"
python3 -m pytest tests/ -q   # 运行自测
```

## 1. 一行产品构想

在对话中给出产品构想，例如：
> “为户外徒步设计一款可单手调节的铝合金登山杖，目标重量 < 300g，
> 载人测试 200kg，卖点：快速展开 + 可调长度。”

## 2. 初始化项目

```bash
aipd init-project --goal "可调长度铝合金登山杖" --db state.db --tenant acme
```

## 3. 恢复已有项目

```bash
aipd restore-project --db state.db --checkpoint <id> --project p1
```

## 4. 运行主管（Supervisor）

```bash
aipd run-supervisor --db state.db --project p1
aipd project-summary --db state.db --project p1
```

主管持续生成工作队列、决策包并推进 S0–S8 生命周期。

## 5. 提交决策

```bash
aipd submit-decision --db state.db --project p1 --decision D-001 --choice option_a --comment "批准"
```

## 6. 执行手册链（Manual Chain）

```bash
aipd run-manual-chain --db state.db --project p1 --batch 1
```

## 7. 执行 CAD 链（C0–C7）

```bash
aipd run-cad-chain --db state.db --project p1 --target C7
```

## 8. 运行测试

```bash
aipd run-tests
python3 -m pytest tests/ -q
```

## 9. 运行评估（Evals）

```bash
aipd run-evals
```

## 10. 构建并签名发布物

```bash
aipd build-release --version 5.0.0
AIPD_RELEASE_SIGNING_KEY=your-key python3 scripts/sign_release.py dist/aipd-os-5.0.0.tar.gz
aipd project-summary --db state.db --project p1   # 复核门禁与决策
```

## 更多

- 架构：`docs/architecture.md`
- 安全：`SECURITY.md` / `THREAT_MODEL.md`
- 供应链：`SBOM.md` / `RELEASE_SIGNING.md`
- 贡献：`CONTRIBUTING.md`
