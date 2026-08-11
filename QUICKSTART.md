# 快速开始（Quick Start）

AIPD-OS v5.6.0 —— AI 产品工程决策操作系统。从一行产品构想开始，逐步推进到
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
aipd build-release --version 5.6.0
AIPD_RELEASE_SIGNING_KEY=your-key python3 scripts/sign_release.py dist/aipd-os-5.6.0.tar.gz
aipd project-summary --db state.db --project p1   # 复核门禁与决策
```

## 11. v5.6 一键命令（简化入口）

17 个一键命令按工作流分组（核心流程 / 手册链 / CAD / 工业化 / 审计与发布）：

```bash
# 核心流程：项目接管驱动
aipd init --project p1 --name "外骨骼" --goal "助力" --db state.db   # 初始化项目
aipd intake --prompt "可单手调节的铝合金登山杖" --db state.db        # 一条需求初始化
aipd resume --db state.db --project p1                              # 恢复/续接项目
aipd status --db state.db --project p1                              # 所有者视图摘要
aipd run --db state.db --project p1 --until-decision                 # 运行到真实决策
aipd decide --db state.db --project p1 --decision D-001 --choice option_a   # 裁定决策

# 手册链 / CAD
aipd manual plan --db state.db --project p1                          # 手册批次计划
aipd manual generate --db state.db --project p1 --batch 1            # 生成手册批次
aipd cad preflight --manifest cad.json --target C2                   # CAD 运行时预检
aipd cad build --manifest cad.json --target C2                       # CAD 成熟度推进

# 工业化 / 审计与发布
aipd industrialize --db state.db --quote quotes.csv --stage dv       # 供应链 + 验证
aipd validate --manifest release.json --target C7                    # 生产发布证据门禁
aipd audit --repo . --out docs/audit                                 # 生成能力矩阵审计产物
aipd release check --target C7 --repo .                             # 发布就绪检查
aipd test                                                           # 运行测试套件
aipd eval --evals evals/evals.json                                  # 运行评估套件
aipd package --version 5.6.0 --no-tests                              # 构建发布包
```

## 12. 体检与版本于详细（v5.6）

```bash
aipd doctor                 # 一键体检：依赖、外部能力、数据库、对象存储、权限
aipd doctor --json          # 机器可读体检结果
aipd version                # 打印包版本
aipd version --verbose      # 打印版本 + Git HEAD + 构建时间 + 能力矩阵版本 + 发布清单哈希
```

## 更多

- 架构：`docs/architecture.md`
- 安全：`SECURITY.md` / `THREAT_MODEL.md`
- 供应链：`SBOM.md` / `RELEASE_SIGNING.md`
- 贡献：`CONTRIBUTING.md`
