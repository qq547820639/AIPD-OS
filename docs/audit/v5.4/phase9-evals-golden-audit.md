# 阶段9 审计：Agent 行为 Evals + 三个黄金项目

- 审计目标：AIPD-OS（源码版本 5.3.0/5.4 阶段）——验证 (1) Completion 接口是否真实可插拔并能调用真实模型；(2) 15 个 Agent 行为评估是否真正驱动模型/Completion 接口；(3) 三个黄金项目是否可重复运行并保存完整元数据。
- 审计范围：`src/aipd_os/evals_runner/`（completion.py / runner.py / registry.py / scoring.py / golden_projects.py / versioning.py / cli.py）、`src/aipd_os/experience/instructions.py`、`evals/golden_projects/*`、`evals/evals.json`、5 个测试文件。
- 运行环境：`.venv/bin/python`（Python 3.9.6），cwd=`AIPD-OS`
- 判定等级：`fully_implemented` / `partially_implemented` / `external_dependency` / `not_implemented` / `not_verifiable`
- 核心规则：**canned/脚本化文本 + 关键词打分 ≠ 真实模型评估；只有真正发出 HTTP 调用到已配置端点的路径才算"触达模型"。**

---

## 测试结果

| 测试集合 | 命令 | 结果 |
|---|---|---|
| 评估运行器 | `pytest tests/test_evals_runner.py -q` | **8 passed** |
| 黄金项目 | `pytest tests/test_golden_projects.py -q` | **5 passed** |
| Completion 端点 | `pytest tests/test_completion_endpoint.py -q` | **7 passed** |
| CI 评估 | `pytest tests/test_evals_ci.py -q` | **3 passed** |
| 行为契约 | `pytest tests/test_behavior_contracts.py -q` | **7 passed** |
| **合计** | 以上 5 个文件 | **30 passed, 1 warning (13.37s)** |

测试全部通过。注意：**本命令未配置 `AIPD_EVAL_MODEL_ENDPOINT`/`AIPD_EVAL_MODEL_KEY`，因此没有任何测试真正向模型端点发起网络调用**（`test_real_call_parses_response` 用 `mock.patch("requests.post")` 模拟了请求）。

---

## 验证点 1 — Completion 接口是否真实/可插拔

**结论：`fully_implemented`。接口是真实、可插拔的；配置了真实端点时会发出真实 HTTP 调用，未配置时诚实标记为外部依赖（绝不伪造）。**

证据（`src/aipd_os/evals_runner/completion.py`）：
- `EnvCompletionProvider.complete()` L89-128 是**真实 HTTP 调用**，不是返回 canned 数据：
  - L90-94：`if not self._endpoint or not self._key: raise ModelNotConfiguredError(...)` —— 未配置端点/密钥时抛错，绝不伪造输出。
  - L102-110：构造 payload（`model` / `messages` / `temperature`）与 `Authorization: Bearer <key>` 头。
  - **L112-117：`resp = requests.post(self._endpoint, json=payload, headers=headers, timeout=self.timeout)`** —— 对 OpenAI 兼容 `/chat/completions` 端点做真实 HTTP POST。
  - L120-123：非 200 抛 `RuntimeError`（含状态码与响应文本）。
  - L124-128：解析 `data["choices"][0]["message"]["content"]`。
- 未配置时的诚实标记链路：`runner.py:run_case` L153-163 捕获 `ModelNotConfiguredError`，返回 `EvalResult(failure_type=["external"], passed=False, output=str(exc))`；`versioning.py:build_report` L29-31 的 summary 单独统计 `external` 数。→ 未配置时 case 被诚实标为 `external`，不虚报通过。

测试：
- `tests/test_completion_endpoint.py::test_model_not_configured_when_missing_env`（L34-38）：清空环境变量 → 抛 `ModelNotConfiguredError`。
- `tests/test_completion_endpoint.py::test_real_call_parses_response`（L53-73）：配置端点后 `mock.patch("requests.post")`，验证请求体 `model`/`messages`/Authorization 头正确、响应被解析。
- `tests/test_completion_endpoint.py::test_runner_marks_external_when_unconfigured`（L108-118）：未配置时 `EvalRunner` 把 case 标为 `external`。
- `tests/test_evals_runner.py::test_env_provider_raises_when_unconfigured`（L76-81）。

局限：
- 测试中**没有针对"已配置真实端点"发起真实网络请求的用例**：`test_real_call_parses_response` 全程 mock 了 `requests.post`，只验证了请求构造与响应解析的代码路径，未证明对真实/在线端点可达。代码层面看是真实 HTTP 调用，但"对真实端点连通"未做端到端验证。
- `EnvCompletionProvider` 用 `requests`（延迟导入 L96），依赖 `requests` 已安装。

---

## 验证点 2 — 15 个 Agent 行为评估是否触达模型

**结论：`partially_implemented`。评估体系在架构上是真实可插拔的（`--provider model` 会真实调用模型端点），但默认/CI 运行路径用脚本化 canned 文本 + 关键词打分，**不触达任何模型**；`test_behavior_contracts.py` 只驱动纯 Python 实际代码，不驱动 Completion 接口/模型。**

需要先说清"两条评估路径"：

### 路径 A — 默认 `--provider fake`（CI/测试实际走的路径）
- `runner.py:_DEFAULT_SCRIPT` L30-83 为每个 case_id 预置了**逐字包含 must 关键词的回显文本**（如 `autonomous-intake` → "已读取附件并建立或恢复项目状态，开始整理和研究材料，不先发长问卷。"）。
- `EvalRunner.__init__` L129-L134 默认构造 `RecordedCompletionProvider` 并注入该脚本。
- `run_case` L140-152 把 case 组装成 messages 调 `self.provider.complete(messages)`，`RecordedCompletionProvider.complete`（completion.py L47-57）仅从 system 消息提取 `[eval case: <id>]`，返回脚本预设文本并记录 history —— **不调用任何模型**。
- 打分 `score_response`（scoring.py L15-35）是**关键词子串匹配**：`m in text`（must 命中 +1、must_not 命中 -1）。即使换成真实模型，也依赖模型输出包含这些字面关键词。

### 路径 B — `--provider model`（CLI 可选，真实模型）
- `cli.py:_make_provider` L29-34：`provider="model"` → `EnvCompletionProvider()`；`cli.py:L74` choices 含 `fake`/`model`。
- 此时 `run_case` 会真实调用 `EnvCompletionProvider.complete`（见验证点 1），向已配置端点发真实 HTTP，返回真实模型文本，再走同样的关键词打分。

### 15 个行为评估 ↔ evals.json case 映射
`evals/evals.json` 共 17 个 case，覆盖任务列出的 15 项行为：

| 任务行为 | evals.json case | 契约 |
|---|---|---|
| 1 不发长问卷 | `autonomous-intake` | no_long_questionnaire |
| 2 只在必要决策暂停 | `route-decision` / `irreversible-tooling` / `conflicting-goals` | only_ask_when_necessary |
| 3 不重复询问已解决项 | `resume-state` | no_cross_session_repeat |
| 4 信息不足时检索/显式假设 | `missing-info-retrieve-or-assumption` | retrieve_or_mark_assumption |
| 5 不臆造产品参数 | `cad-after-manual` | no_fabricated_params |
| 6 连续附件真实继承 | `low-risk-layout` | attachment_continuity |
| 7 视觉失败只返工责任页 | `visual-failure-auto-rework` | visual_failure_auto_rework |
| 8 Faceted CAD 不越级 | `faceted-cad-no-overclaim` | faceted_cad_no_overclaim |
| 9 无真实报价不伪造 | `no-fake-supplier-quote` | no_fake_supplier_quote |
| 10 无测试不称通过 | `unsupported-claim` / `external-test` / `no-claim-without-test` | no_claim_without_test |
| 11 参数变更正确传播 | `key-dimension-propagation` | key_dimension_propagation |
| 12 CAD 变更回写手册 | `cad-change-writeback-manual` | cad_change_writes_back_manual |
| 13 新会话正确恢复 | `resume-state` | no_cross_session_repeat |
| 14 自然语言审批正确解析 | `natural-language-review-parsed` | natural_language_review_parsed |
| 15 物理工作未完成保持 HOLD | 无独立 case；由 `external-test`/`no-claim-without-test` 的 `blocked_external` 状态体现 | no_claim_without_test |

### `test_behavior_contracts.py` 是否驱动模型/Completion 接口？
**不驱动。** 该文件 7 个测试全部是纯 Python 实际代码 / 逻辑契约，没有一条调用 `CompletionProvider`/`EnvCompletionProvider`/`EvalRunner`：
- L39-48：注册/语义检查器存在性（registry 检查）。
- L51-53 `test_no_long_questionnaire_semantic`：对固定字符串跑 `semantic_check`（正则）。
- L56-65 `test_faceted_cad_no_overclaim_caps_at_c1`：驱动真实 `FacetedAdapter`（`maturity_ceiling=="C1"`）。
- L68-86 `test_no_fake_supplier_quote_writes_external_package`：驱动真实 `ExecutionRouter`，imggen 不可用 → `blocked_external` + 外部任务包。
- L89-100 `test_no_claim_without_test_external_blocked`：真实 `ExecutionRouter`，CAD 不可用 → `blocked_external`。
- L103-132 `test_visual_failure_auto_rework_returns_rebuild_plan`：真实 `VisualAuditor.audit_batch`，仅失败页进 rebuild_plan。
- L135-146 `test_no_cross_session_repeat_does_not_relist_resolved`：真实 `CheckpointManager`+`AIPDStateDB`。
- L149-161 `test_key_dimension_propagation_marks_deliverable_stale`：真实 DB+`CheckpointManager`。
- L164-169 `test_only_ask_when_necessary_decision_policy`：真实 `decision_policy.should_ask_decision`。

这些是"逻辑契约"（`registry.LOGIC_CONTRACTS` L34-44），验证**底层代码确实强制了行为**（Faceted CAD 封顶 C1、外部能力诚实写任务包、视觉审计只返工失败页、决策不重复、关键尺寸传播、决策策略），但**它们不经过模型、不经过 Completion 接口**。

测试证据：
- `tests/test_evals_runner.py::test_fake_provider_case_passes`（L52-62）、`test_run_over_evals_json_produces_report`（L65-72）、`test_evals_ci.py::test_deterministic_subset_runs_green`（L19-25）与 `test_cli_run_fake_produces_report`（L28-45）都走**假实现**（RecordedCompletionProvider + 脚本），证明"管道+打分"在 CI 下全绿，但**不触达模型**。
- `test_completion_endpoint.py::test_model_gated_requires_endpoint`（test_evals_ci L48-54）只验证"未配置端点 → 抛错"，未验证"已配置 → 真实调用"。

局限：
- **默认/CI 评估不触达任何模型**：`evals.json` 的 17 个 case 在默认 fake 路径下用 canned 文本 + 关键词子串打分，只能证明管道与打分逻辑可回归，不能证明真实模型在这些行为上合格。
- 真实模型路径（`--provider model`）架构造通，但**没有已配置端点的端到端测试**，也没有把真实模型输出喂给行为契约的自动化门禁。
- 打分依赖关键词字面子串匹配，真实模型输出若措辞不同会被判 miss（脆弱）。

---

## 验证点 3 — 三个黄金项目是否可重复运行并保存完整元数据

**结论：`partially_implemented`。三个黄金项目是真实端到端运行（非静态 JSON 夹具），可重复；但"保存完整元数据"只部分满足——多数元数据字段（cost/tokens/耗时/hash/决策日志/证据/错误修复）未记录。**

证据（`src/aipd_os/evals_runner/golden_projects.py`）：
- **真实端到端运行**（`run_golden_project` L176-254）：
  - L187-189：建临时 SQLite DB、建 tenant/project；
  - L192-198：`build_manual_pages` 生成 ≥minimum_pages 页定义，用真实排版器 `render_page` 光栅化为 PNG；
  - L200-203：`_split_batches` 分批 + `VisualAuditor().audit_batch` 语义审计（批次连续性）；
  - L205-222：`FakeImageAdapter`（L39-68，`available=False` 诚实走 `blocked_external`）经**真实** `ExecutionRouter` 驱动，产出外部任务包；
  - L224-226：`compose_pdf` + `build_zip` 合成 PDF/ZIP；
  - L228-254：4 项断言（manual_pages_produced / batch_continuity_holds / no_fabricated_external_evidence / pdf_zip_produced）并返回报告。
- `project.json`（`evals/golden_projects/{exoskeleton,consumer_electronics,simple_mechanical_tool}/project.json`）只是**输入夹具**（facts/params、minimum_pages、expected），不是输出。

**但报告元数据不完整**（返回 dict L239-254 仅含）：
- 有：`project_id`/`project_name`、`model_version`（硬编码 `"golden-deterministic"` L242，**非真实模型/工具版本**）、`generated_at`、`manual_pages`、`batches`、`batch_continuity_ok`、`failing_pages`、`external_status`、`external_task_packages`（外部任务包路径）、`pdf`/`zip`（产物路径）、`checks`、`passed`。
- **缺**：原始输入 raw input、产物 hash、决策日志 decision log、证据 evidence、错误与修复 errors & fixes、成本 cost、token 数、耗时（仅 `generated_at` 时间戳，无 elapsed）、工具轨迹（tool trajectory 仅外部任务包一条，无完整轨迹）。

测试：
- `tests/test_golden_projects.py`：`test_exoskeleton_ten_page_manual`（L23-32）、`test_consumer_electronics`（L35-39）、`test_simple_mechanical_tool`（L42-45）、`test_all_golden_projects_run`（L48-52）——对每个夹具 `run_golden_dir(...)` 并断言 `report["passed"] is True`、`batch_continuity_ok is True`、`external_status == "blocked_external"`、PDF/ZIP 存在。本次实测**5 passed**，确认三个项目真实端到端跑通（非静态夹具）。

局限：
- **元数据不完整**：未记录 cost/tokens/elapsed/hash/决策日志/证据/错误修复，`model_version` 是写死的 `"golden-deterministic"`，不满足任务要求的"保存模型与工具版本/成本/代币/耗时"等完整元数据。
- FakeImageAdapter 为确定性假实现（诚实外部依赖），黄金项目不真正调用文生图/模型，验证的是"端到端流程/诚实外部依赖"而非真实模型能力。
- 测试只断言 `passed` 布尔与少数字段，未校验元数据完整性（如 hash/cost 存在性）。

---

## 总体判定

1. **Completion 接口**：真实、可插拔。配置 `AIPD_EVAL_MODEL_ENDPOINT`+`AIPD_EVAL_MODEL_KEY` 时会向 OpenAI 兼容端点发出**真实 HTTP 调用**（completion.py L112-117）；未配置时抛 `ModelNotConfiguredError` 并被 runner 诚实标记为 `external`（runner.py L153-163）。**非 canned 数据**。但测试从未对真实在线端点做端到端连通验证（真实调用测试 mock 了 `requests.post`）。

2. **15 个 Agent 行为评估**：评估体系"能触达模型"，但**默认/CI 路径不触达**——用脚本化 canned 文本 + 关键词子串打分（`_DEFAULT_SCRIPT` + `RecordedCompletionProvider` + `score_response`）。`test_behavior_contracts.py` 只驱动纯 Python 实际代码（FacetedAdapter/ExecutionRouter/VisualAuditor/CheckpointManager/decision_policy），**不经过 Completion 接口/模型**。真实模型路径（`--provider model`）架构造通但无端到端测试。因此：**"评估真正触达模型"在默认交付物中不成立，仅在显式配置真实端点 + `--provider model` 时成立。**

3. **三个黄金项目**：**真实端到端运行**（生成手册页→渲染 PNG→批次审计→真实 ExecutionRouter 驱动→合成 PDF/ZIP），重复运行每次重新生成，**非静态 JSON 夹具**。但**元数据保存不完整**：缺 cost/tokens/耗时/hash/决策日志/证据/错误修复，`model_version` 硬编码为 `golden-deterministic`。

## 关键局限汇总（修复优先级参考）

- **P1**：默认/CI 的 15 个行为评估不触达模型（canned 脚本 + 关键词打分）；需"已配置真实端点"的端到端模型评估才能在 CI 中真正验证模型行为。
- **P1**：`test_behavior_contracts.py` 只测纯代码逻辑，不测 Completion/模型路径；需补充"真实 provider 输出 → 行为契约"的接线测试。
- **P1**：黄金项目报告元数据不完整（缺 cost/tokens/elapsed/hash/决策日志/证据/错误修复），`model_version` 硬编码。
- **P2**：打分依赖关键词子串匹配，真实模型不同措辞会被误判 miss。