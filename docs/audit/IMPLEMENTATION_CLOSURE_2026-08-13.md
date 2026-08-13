# AIPD-OS 实施收口报告：Q-1/Q-2 P0 修复 + N-1 配置驱动 LLM Provider 装配（2026-08-13）

> 基线 HEAD `744960c` → 交付 HEAD 3 commit（已推送 origin/main）。
> 依据：走读审查（REPO_WALKTHROUGH_2026-08-13.md 的 Q-1/Q-2 + REPO_DEEP_WALKTHROUGH_2026-08-13.md 的 N-1）。

## 1. 批次目标

审查结论中价值最高、成本最低的组合：清掉两个 P0（公开 API 卫生），并实施 N-1——把「AI 智能推理 0% 接线」这一核心缺口以**最小改造成本**点亮为「配置即可用」。

## 2. 交付 commit（3 个，已 push origin/main）

| commit | 内容 |
|---|---|
| `b974141` | Q-1 `registry.py:310` `_all__`→`__all__`（import * 静默失效修复）+ Q-2 `logging_utils.py` 按 name 装配重构（抽 `_attach_handlers`、修正 `_configured_loggers` 判定语义）+ 防回归测试 |
| `4f33f91` | N-1：新增 `src/aipd_os/llm/`（`client.py` LlmClient 纯 urllib 零新依赖 + `product_intelligence_provider.py` + `idea_decomposer_provider.py`）+ `config.py` 三字段（AIPD_MODEL_API_KEY/BASE_URL/NAME）+ `runtime.py` `_register_external_providers` 配置驱动装配 |
| `f536dac` | LLM Provider 契约/装配测试（净增 31 条）+ 重生成 RELEASE_MANIFEST.json / SOURCE_MANIFEST.json（源码哈希变化的必须动作） |

## 3. 验证结果（QA 独立复现，非实现方数字）

- **全量回归：989 passed / 0 failed / 3 skipped / 2 deselected**（基线 958，净增 31；实现方与 QA 两方独立数字一致）
- test_packaging 8 passed；release evidence/signing/gate 26 passed
- ruff：新文件与新增测试**零违规**；mypy：llm 包零违规
- git 真实性：3 commit 完整存在于 log 且已推送；diff 仅 14 文件，未触碰 README/pyproject/docs/migrations/probe()/live_probe()
- 行为矩阵实测：
  - **未配置**（默认）：`product.derive_*` → EXTERNAL_DEPENDENCY、idea.decompose 未注册、execute 抛 external_blocked 并写任务包——**与基线完全一致，诚实降级不破**
  - **已配置**（AIPD_MODEL_API_KEY + AIPD_MODEL_BASE_URL）：7 个 product.* 能力全部 AVAILABLE、idea.decompose 注册且可用
  - 边界 6 用例全过（未配置→LlmNotConfiguredError、HTTP500→RuntimeError、坏 JSON→RuntimeError/ProductProviderError/IdeaDecompositionUnavailable、```json 围栏剥离）
  - 无真实网络泄漏进测试（全部 monkeypatch/脚本化）

## 4. 遗留观察（非阻塞）

- **UP045 ×1**：`logging_utils.py:47` `_attach_handlers` 的 `Optional[Path]` 注解为本次新增的 1 条风格提示（QA 基线对比：logging_utils 3→4）。与同文件既有签名同风格、遵循 py39 既有约定，QA 判定无需返工。已记录，若后续启动「存量 lint 清债」批次一并处理。
- **存量 lint 债**（历史遗留，非本次引入）：约 2299 条 ruff UP/F + 33 条 mypy 于 research/cad/state/supply_chain 等文件，建议单独立项。

## 5. 效果

N-1 落地后，「全程 AI 推进」的承诺变为：配置两个环境变量即可点亮 decompose 与 derive_* 全链（契约、路由、服务、测试在 v5.9.1 早已就绪）。未配置用户行为不变，诚实原则不破。

## 6. 下一步建议

1. 存量 lint 清债独立批次（2299 条，分批小批量）
2. CLI 命令面统一（Q-4'）与 README/QUICKSTART 文档对齐（P2 UX 项）
3. v5.10 NPI（BOM/Cost/ValidationTest/Issue/MMDProjection）按「契约先行 → 确定性实现 → 测试锁定」节奏立项
