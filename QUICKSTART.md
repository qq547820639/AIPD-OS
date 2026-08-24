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
aipd init --project p1 --name "可调长度铝合金登山杖" --goal "可单手调节" --db state.db
# 或从一句自然语言直接初始化
aipd intake --prompt "可单手调节的铝合金登山杖" --db state.db
# 或首次使用引导（一步建项）
aipd onboard --db state.db --idea "可单手调节的铝合金登山杖"
```

## 3. 恢复已有项目

```bash
aipd resume --db state.db --project p1
```

## 4. 运行主管（Supervisor）

```bash
aipd run --project p1 --db state.db --until-decision
aipd status --db state.db --project p1
```

主管持续生成工作队列、决策包并推进 S0–S8 生命周期。

## 5. 提交决策

```bash
aipd decide --db state.db --project p1 --decision-id D-001 --choice option_a --comment "批准"
# 或用一句自然语言回复
aipd decide --db state.db --project p1 --natural "批准，选方案A"
```

## 6. 执行手册链（Manual Chain）

```bash
aipd manual plan --db state.db --project p1
aipd manual generate --db state.db --project p1 --batch 1 --prompt "封面与原理页" --output-dir out/pages
```

## 7. 执行 CAD 链（C0–C7）

```bash
aipd cad preflight --manifest cad.json --target C2
aipd cad build --manifest cad.json --target C2
```

## 8. 运行测试

```bash
aipd test
python3 -m pytest tests/ -q
```

## 9. 运行评估（Evals）

```bash
aipd eval --evals evals/evals.json --provider model --out evals_out  # fake/contract-test 仅测试用
```

## 10. 构建并签名发布物

```bash
aipd package --version 5.6.0
aipd status --db state.db --project p1   # 复核门禁与决策
```

## 11. 工业化 / 验证 / 发布就绪

```bash
aipd industrialize --db state.db --quote quotes.csv --stage dvt  # 供应链 + 验证
aipd validate --manifest release.json --target C7                # 生产发布证据门禁
aipd release check --target C7 --repo .                          # 发布就绪检查
```

## 12. 体检与界面（v5.6）

```bash
aipd doctor                 # 一键体检：依赖、外部能力、数据库、对象存储、权限
aipd doctor --json          # 机器可读体检结果
aipd version                # 打印包版本
aipd version --verbose      # 打印版本 + Git HEAD + 构建时间 + 能力矩阵版本 + 发布清单哈希
aipd ui --db state.db       # 启动本地 Owner Web Console（http://127.0.0.1:8080）
```

## 13. 验证、Issue 与制造就绪度（v5.10）

```bash
# 创建验证计划
aipd validation plan --db state.db --project p1 --stage EVT --title "EVT 验证计划"

# 导入验证数据（CSV/XLSX/JSON）
aipd validation import --db state.db --project p1 --file test_results.csv --stage EVT

# 列出验证计划/测试/结果
aipd validation list --db state.db --project p1 --what plans
aipd validation list --db state.db --project p1 --what tests
aipd validation list --db state.db --project p1 --what results

# 查看 Issue
aipd issue list --db state.db --project p1
aipd issue list --db state.db --project p1 --blocking  # 仅阻塞发布 Issue

# 解决 Issue
aipd issue resolve --db state.db --project p1 --id issue_xxx --disposition FIX

# 检查制造就绪度（确定性计算，缺数据默认 HOLD）
aipd readiness check --db state.db --project p1
aipd readiness check --db state.db --project p1 --json  # 机器可读 JSON
```

## 旧版命令对照表（deprecated）

以下 v5.0 旧命令**保留功能但已废弃**，执行时会打印 `DeprecationWarning`；
建议迁移到对应的一键主线命令（两者行为等价，主线命令额外支持 `--json`）：

| 旧命令 | 主线命令 |
|---|---|
| `aipd init-project` | `aipd init` |
| `aipd restore-project` | `aipd resume` |
| `aipd run-supervisor` | `aipd run` |
| `aipd project-summary` | `aipd status` |
| `aipd submit-decision` | `aipd decide` |
| `aipd run-manual-chain` | `aipd manual generate` |
| `aipd run-cad-chain` | `aipd cad build` |
| `aipd run-tests` | `aipd test` |
| `aipd run-evals` | `aipd eval` |
| `aipd build-release` | `aipd package` |

## 更多

- 架构：`docs/architecture.md`
- 安全：`SECURITY.md` / `THREAT_MODEL.md`
- 供应链：`SBOM.md` / `RELEASE_SIGNING.md`
- 贡献：`CONTRIBUTING.md`
