# Tasks

> 执行原则：所有交付物必须有可重复运行的测试与审计证据。先核对已有实现避免重复开发，再补齐真实缺口。在不重写已实现且有证据能力的前提下增量实现。

- [x] Task 1: 在当前真实 HEAD 再生成版本真实性审计并修复 manifest 哈希
  - [x] 1.1 在 HEAD `67fb368` 重新运行/扩展 `scripts/audit_repo.py`，使 `docs/audit/audit.json` 与 `docs/audit/v5.1-version-truth-audit.{json,md}` 记录的 HEAD/时间/版本与真实仓库一致。
  - [x] 1.2 修复 `RELEASE_MANIFEST.json` 中 3 个审计文档（`docs/audit/audit.json`、`docs/audit/v5.1-version-truth-audit.json`、`docs/audit/v5.1-version-truth-audit.md`）的哈希，使 manifest 与真实文件一致。
  - [x] 1.3 运行 `tests/test_audit_repo.py` 确认审计再生成与一致性校验通过。

- [x] Task 2: 能力矩阵审计产物（repository_snapshot / capability_matrix）
  - [x] 2.1 新增 `scripts/capability_matrix.py`（或扩展 `audit_repo.py`），产出 `docs/audit/repository_snapshot.json`（默认分支/HEAD SHA/时间/版本/文件树/tag/release/CI/manifest 哈希/未跟踪/冲突/依赖锁/SBOM/签名）。
  - [x] 2.2 对六大域（主管执行/理论研究/产品手册/CAD 与生产图纸/工业化与验证/跨会话与用户体验）全部能力逐项分类到 7 类（fully_implemented / partially_implemented / protocol_only / template_only / external_dependency / not_implemented / not_verifiable）。
  - [x] 2.3 每项能力给出证据字段：声明文件、实现文件、类或函数入口、运行命令、输入输出、单元测试、集成测试、端到端证据、当前限制。
  - [x] 2.4 输出 `docs/audit/capability_matrix.json` 与 `docs/audit/capability_matrix.md`。
  - [x] 2.5 新增 `tests/test_capability_matrix.py`：校验三份产物存在、HEAD/版本一致、能力分类覆盖齐全、7 类枚举合法。
  - [x] 2.6 将能力矩阵生成与校验纳入 CI（audit job），并核对 RELEASE_MANIFEST 哈希与真实文件一致。

- [x] Task 3: Agent 评测真实/可插拔 Completion 端点
  - [x] 3.1 重写 `src/aipd_os/evals_runner/completion.py` 的 `EnvCompletionProvider.complete()`：接入 OpenAI 兼容 HTTP 端点（`AIPD_EVAL_MODEL_ENDPOINT/KEY/VERSION`），用 `requests` 真实调用并返回文本。
  - [x] 3.2 未配置端点/密钥时抛 `ModelNotConfiguredError`，评测器将该 case 诚实标记为 `external_dependency`，绝不返回伪造输出。
  - [x] 3.3 保留 `RecordedCompletionProvider` 作为离线脚本化回退（不伪造）。
  - [x] 3.4 新增 `tests/test_completion_endpoint.py`（mock 端点验证真实调用、请求体、响应解析、未配置时 external_dependency 分类）。
  - [x] 3.5 运行 `aipd eval` 确认 15 项评测在离线脚本化路径下仍全绿。

- [x] Task 4: 修复打包/CI 干净环境安装缺陷
  - [x] 4.1 修正 `pyproject.toml`：将 `mcp` 移出 `[full]`（或声明独立的 `Requires-Python >=3.10` extra），保证 Python 3.9 下 `pip install -e ".[full,dev]"` 可成功。
  - [x] 4.2 确保 `[full]` 含 `pillow`/`reportlab` 等让 layout/visual/manual_chain 测试可收集的依赖。
  - [x] 4.3 更新 CI `.github/workflows/ci.yml`：unit/integration job 安装 `.[full,dev]`（或等价），使全部测试可收集并通过。
  - [x] 4.4 新增/更新打包测试覆盖 extras 解析与干净安装不因 Requires-Python 失败。

- [x] Task 5: 最终验收与发布
  - [x] 5.1 全量测试（`pytest`）、能力矩阵校验、审计再生成、15 项评测全部跑通。
  - [x] 5.2 版本提升至 `5.2.0`，更新 CHANGELOG/README/QUICKSTART，重新生成 `RELEASE_MANIFEST.json`、构建发布包与 SHA-256 清单并签名。
  - [x] 5.3 提交并推送至 `origin/main`。

# Task Dependencies

- Task 1 无依赖（在真实 HEAD 做基线）。
- Task 2 依赖 Task 1（审计基线复用）。
- Task 3 依赖 Task 1（评测基线）。
- Task 4 依赖 Task 1；4.3 依赖 Task 2/3 引入的测试文件。
- Task 5 依赖 Task 1—4。

可并行：Task 1、Task 3、Task 4 可并行；Task 2 依赖 Task 1；Task 5 最后。