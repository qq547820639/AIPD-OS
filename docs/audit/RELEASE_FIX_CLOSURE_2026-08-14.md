# AIPD-OS 发布收口与缺陷修复闭环报告（2026-08-14）

> 依据：`RELEASE_FIX_PLAN_2026-08-14.md`
> 执行结果：P0×4 发布收口 + P1×4 缺陷修复全部完成，release-ready 门禁全绿

---

## TL;DR

- **门禁**：`production_release_gate.py --release-ready` 8 项检查 **全部 PASS**，`release_ready: true`。
- **测试**：全量 **1022 passed / 0 failed / 3 skipped**；ruff/mypy 全仓 0。
- **提交**：6 个 commit 已推送 origin/main（`e245555..d15f29b`），v5.6.0 tag 更新到代码提交 `e896f67`。
- **额外修复**：发现并修复了 test report 证据链的**两处长期断裂**（见 §三），这是 release 门禁长期无法通过的真正根因。

## 一、P1 四连修（代码缺陷）

| ID | 修复 | 文件 | 测试 |
|---|---|---|---|
| P1-1 | 视觉审核假通过：`_vision()` 不再返回 `bool(vision_backend)`；真实接入 `VisionAuditProvider`（注入且 available 才真实调用 `audit()`），否则 character/cmf 诚实 HOLD | `visual_audit/auditor.py` + `scripts/manual_chain_gate.py` | 修正 `test_visual_honesty_guardrail`、`test_manual_chain_gate_visual` 中固化假通过的断言 |
| P1-2 | 认证到期时区崩溃：统一 `_now_aware()`/`_parse_expiry()`，消除 aware vs naive TypeError | `supply_chain/certification.py` | 补 aware 到期/未到期 2 测试 |
| P1-3 | 邮件附件跨会话丢失：`fetch_emails` 会话内保留 `_attachments` 字节，跨会话诚实提示重新 fetch | `mail/client.py` | 新增 `test_mail_attachment.py`（3 测试） |
| P1-4 | 状态双重维护：`aipd_store.AIPDStore` 标 DEPRECATED（SCHEMA 保留作 v4→v5 迁移锚点），明确 `src/state/db.py` 为唯一权威 | `scripts/aipd_store.py`、`aipd_state.py` | 迁移/supervisor 测试回归 |

## 二、P0 发布收口（门禁）

| 门禁项 | 结果 |
|---|---|
| workspace_clean | ✅ clean（审计文档已入库） |
| commit_matches_head | ✅ source_commit == tag(v5.6.0) |
| source_manifest_zero_diff | ✅ 507 文件零差异 |
| bundle_manifest_zero_diff | ✅ bundle 哈希匹配 |
| test_numbers_from_report | ✅ passed=1022 failed=0 total=1025 |
| signature_verifiable | ✅ Ed25519 验签通过 |
| no_secrets / no_unacknowledged_cve | ✅ |

## 三、额外修复：test report 证据链的两处长期断裂

排查 P0 时发现 `test_numbers_from_report` 门禁**从未真正通过**的根因——两处断裂：

1. **freshness 字段缺失**：`pytest-json-report` 默认不生成 `source_commit`/`package_version` 字段，导致 `test_report.source_commit` 恒缺、门禁判 STALE。修复：`tests/conftest.py` 新增 `pytest_json_modifyreport` hook 自动注入。
2. **hook 加载时机陷阱**：`pytest-json-report` 仅在传 `--json-report` 时才注册该 hookspec，直接定义会报 `unknown hook` 使常规 pytest 崩溃。修复：`optionalhook=True` + `AIPD_SOURCE_COMMIT` 环境变量锚定代码提交（代码提交与证据提交分离时）。

## 四、提交清单（6 commit）

| SHA | 内容 |
|---|---|
| 0005c1b | P1 四连修 + 审计文档收口 |
| 5b671ae | pytest-json-report 注入 freshness 字段 |
| 22c8447 | conftest hook optionalhook=True 修复 |
| b919732 | 首次刷新发布证据 |
| e896f67 | conftest 支持 AIPD_SOURCE_COMMIT（tag 锚点） |
| d15f29b | 最终刷新证据（test_report 1022 passed） |

## 五、遗留（记录在案，不阻塞）

- 版本号双轨制：pyproject 仍 5.6.0，功能版本已到 v5.9.2+ 重构后——正式发布时统一收口。
- P2 清单（doctor 敏感 env 硬失败、三套 LLM 客户端、CHANGELOG 漂移等）留待下轮。
- v5.10 NPI（BOM/Cost/ValidationTest/Issue）路线图未动。
