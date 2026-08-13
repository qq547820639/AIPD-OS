# AIPD-OS 发布收口与缺陷修复实施计划（2026-08-14）

> 依据：`IMPRESSION_POST_REFACTOR_2026-08-14.md` 评审结论
> 执行模式：团队编排（架构师/后端/QA/运维 四角色），项目总监汇编 + 门禁
> 授权：PAN 全权自主裁决，一次性迭代执行完

---

## 一、目标

把上一轮评审锁定的 **P0×4（发布收口）+ P1×4（代码缺陷）** 全部修复，使 `production_release_gate.py --release-ready` 四项门禁全绿，仓库进入可正式发布状态。P2 项记录在案，本轮不排入（防范围蔓延）。

## 二、范围（锁定）

| 优先级 | 项 | 说明 |
|---|---|---|
| P0 | 发布证据锚点、test_report、签名、工作区 clean | 收口，必须全绿 |
| P1-1 | 视觉审核假通过 | `auditor.py:104-114` |
| P1-2 | 认证到期时区崩溃 | `certification.py:86-95` |
| P1-3 | 邮件附件跨会话丢失 | `mail/client.py:644-666` |
| P1-4 | 状态实现双重维护 | `scripts/aipd_store.py` 旧 store |

## 三、执行顺序（依赖 DAG）

```
阶段1（并行）
  ├─ T1 架构师：P1-4 裁决（删旧 store 或改造）
  └─ T2 后端：P1-1 / P1-2 / P1-3（三项独立）
阶段2  T3 后端：P1-4 按架构师裁决实施
阶段3  T4 QA：独立验证 + 补测试 + 全量回归 + ruff/mypy
阶段4  T5 运维：P0 发布收口（提交→打包→证据→签名→门禁）
阶段5  T6 总监：汇编 + 终验 + 交付 + 记忆落盘
```

## 四、详细任务分解

### T1（架构师）P1-4 状态双重维护裁决
- **输入**：`scripts/aipd_store.py`（旧单项目 store）、`scripts/quality_gate.py:5`、`scripts/selftest_state.py:5`、`scripts/selftest_v4.py`、`src/aipd_os/state/db.py`（新多租户库）
- **裁决**：① 删除旧 store，引用方改走 `src/aipd_os/state`；或 ② 保留但隔离+deprecated。倾向 ①（消除漂移源）
- **验收**：全仓无双重维护；引用方迁移完毕；selftest/gate 功能不退化

### T2（后端）P1-1/2/3 修复
- **P1-1** `auditor.py`：`_vision()` 现返回 `bool(vision_backend)` 导致配置即 `passed=True`。改诚实降级——`VisionAuditProvider.audit()` 未接线前，character/cmf 一律 `passed=False` + `requiring_vision=True`，标注「视觉审核尚未接入，NOT_VERIFIED」。不得假通过。
- **P1-2** `certification.py`：统一用 `_now_aware()`；`expires_at` 无 tz 时假设 UTC 再比较。消除 aware vs naive TypeError。
- **P1-3** `mail/client.py`：持久化 meta 保留附件字节（或独立存储），`download_attachment` 从持久化态取回。跨会话可下载。
- **验收**：三项各配针对性测试；全量回归通过；ruff/mypy 0

### T3（后端）P1-4 实施
- 按 T1 裁决落地，独立 commit

### T4（QA）独立验证
- 补/改测试覆盖 P1-1/2/3/4；独立全量 pytest（目标 ≥1016 passed）；ruff/mypy 0；对修复做「反向验证」（删修复则测试失败）

### T5（运维）P0 发布收口
- 顺序（严格）：
  1. `git add docs/audit/*.md` + 代码修复 → commit
  2. 全量测试并输出 `--json-report` 生成 test_report
  3. 打包 `aipd package` 生成 `releases/aipd-os-5.6.0.zip`
  4. `release_evidence.py --repo . --test-report <report> --source-commit HEAD` → 刷新 SOURCE/PROVENANCE
  5. `regenerate_release_manifest.py --version 5.6.0` → 刷新 RELEASE_MANIFEST
  6. `sign_release.py --sign releases/aipd-os-5.6.0.zip` → 重签
  7. `production_release_gate.py --release-ready --repo .` → 四项门禁全绿
- **验收**：`workspace_clean` / `commit_matches_head` / `test_numbers_from_report` / `signature_verifiable` 全部 passed

### T6（总监）汇编
- 终验门禁 → 更新根 `overview.md` → 落盘审计报告 → 记忆追加

## 五、门禁与验证（总）

| 门禁 | 标准 |
|---|---|
| 全量测试 | ≥1016 passed / 0 failed |
| lint/type | ruff 0 / mypy 0 |
| 发布门禁 | 4 项全 passed |
| 诚实性 | P1-1 修复后不得出现「配置即通过」 |

## 六、风险与回滚

- 签名私钥在本地 `.release_keys/ed25519_private.pem`，可重签
- 每项修复独立 commit，可逐条回滚
- P1-4 删旧 store 前需 grep 全仓确认无遗漏引用
