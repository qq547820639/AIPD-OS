# Checklist

> 验收证据：每个 checkpoint 需有可重复运行的测试或审计输出。CI 通过为硬性要求。

- [x] Task 1 版本真实性审计再生成
  - [x] `docs/audit/audit.json` 与 version-truth 文档记录的 HEAD=`67fb368`（及后续发布提交）、版本与真实仓库一致
  - [x] `RELEASE_MANIFEST.json` 中 3 个审计文档哈希匹配（不一致为 0）
  - [x] `tests/test_audit_repo.py` 通过

- [x] Task 2 能力矩阵审计产物
  - [x] `docs/audit/repository_snapshot.json`、`docs/audit/capability_matrix.json`、`docs/audit/capability_matrix.md` 存在且 HEAD/版本与仓库一致
  - [x] 六大域全部能力逐项分类到 7 类，且每项含声明文件/实现文件/入口/运行命令/输入输出/测试/端到端证据/当前限制
  - [x] `tests/test_capability_matrix.py` 通过，能力矩阵生成与校验纳入 CI

- [x] Task 3 真实/可插拔 Completion 端点
  - [x] `EnvCompletionProvider.complete()` 在配置端点时真实调用 OpenAI 兼容 HTTP 端点并返回文本
  - [x] 未配置端点时抛 `ModelNotConfiguredError` 并诚实标记 `external_dependency`，不返回伪造输出
  - [x] 离线脚本化回退保留，`aipd eval` 15 项离线全绿
  - [x] `tests/test_completion_endpoint.py` 通过

- [x] Task 4 干净环境安装与 CI
  - [x] Python 3.9 下 `pip install -e ".[full,dev]"` 成功（不受 `mcp` Requires-Python 影响）
  - [x] CI unit/integration 安装完整依赖，全部测试可收集并通过
  - [x] 打包/CI 测试通过

- [x] Task 5 最终验收与发布
  - [x] 全量测试、能力矩阵校验、审计再生成、15 项评测全部通过
  - [x] 版本 `5.2.0`，发布包 + SHA-256 清单 + 签名生成
  - [x] 已提交并推送至 `origin/main`