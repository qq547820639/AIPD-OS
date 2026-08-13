# AIPD-OS 重构后版本印象报告（2026-08-14）

> 评审对象：HEAD `e245555`（v5.9.2 + NEXT_ITERATION 批次 + REFACTOR R-1~R-8，共 98 commits）
> 评审方式：全仓目录层级走读（根 → src 26 子包 → tests/scripts/state_service/migrations/CI/发布证据）+ 两路深潜代理 + 本人核心链路逐行验证 + 实测（pytest 全量、ruff、mypy、doctor、release-ready 门禁）
> 前序报告：`IMPRESSION_V5_9_2_2026-08-13.md`（本报告为其继任，重点回答"两批迭代之后现在是什么状态"）

---

## TL;DR

- **印象**：这是我在该仓见过的最接近"生产发布级纪律"的工程骨架；08-13 报告列出的 Q-1/Q-2/N-1/N-2/N-3/N-4/Q-4'/N-5/N-6 共 9 项债务**已全部清除**，且不是打补丁式的——层次泄漏是依赖方向真反转、测试假断言是替换并证明灵敏度、大文件是拆到 <700 行且导出集逐项兼容。
- **代码层面是否全部实现**：**确定性骨架 100% 实装且被 1016 个测试锁定；AI 智能接线已从 0% 补到"代码就绪"**（N-1 配置驱动 LLM Provider 装配已落地，缺的只是用户配 key）。**未动工的只剩 v5.10 NPI（BOM/Cost/ValidationTest/Issue 等制造就绪域），这是路线图内的下一版本工作，不是欠账。**
- **还有没有深化/UX 空间**：**有，且本轮实测出 4 个 release-ready 门禁失败（P0 级）+ 4 个 P1 级代码缺陷 + 一批 P2 UX 项**。代码不是写完了，而是"骨架完美、发布收口没做完、细节还能磨"。

---

## 一、整体印象（主观评价先行）

1. **工程纪律是罕见的真纪律，不是表演。** 1016 passed / 3 skipped（我亲跑 3 分钟）；ruff 全仓 0；mypy 0 错误；V1 schema 冻结 + SHA-256 漂移校验；事务模型修掉了 SQLite 写锁自死锁；发布证据四件套 + Ed25519 签名 + 49 个门禁/审计脚本。上一轮报告的每一个 P0/P1 都真的改了，commit 历史能对上。
2. **"诚实优先"贯穿到每个缝隙。** ExecutionRouter 拒绝 simulated 占位；adapter 不可用统一 external_blocked 并写出外部任务包；doctor 明确区分「未实现」与「外部依赖」；CAD faceted 永不越 C1。README 对用户的承诺在代码里逐条兑现——除了一处（见 P1-1，视觉审核裂缝）。
3. **重构质量超出预期。** R-3 用 AST 实测 85 条 import 边证明 idea 域零 execution 依赖；R-1 用"删映射即测试失败"证明断言灵敏度；R-6 生成脚本重跑 byte-identical。这是"可证明的重构"，不是"看起来改干净了"。
4. **但发布收口掉链子了。** 最新一个 commit 刷新了清单，却没重跑发布证据管线——**现在这个仓库过不了自己的 release-ready 门禁**（4 项失败，详见 §三 P0）。对一个以"发布证据"为核心卖点的项目，这是最讽刺的一处。
5. **版本双轨制仍在。** pyproject/README/`__init__` 全是 5.6.0，功能实际到 v5.9.2+。08-14 记忆里记着这是"留待正式 release 的决策"——但现在 8 份审计报告都没进 git（workspace_clean 失败），说明连审计文档本身都还没收口。

---

## 二、达成度三层判定（回答"代码层面的工作全部实现了吗"）

| 层 | 判定 | 依据（本轮实测） |
|---|---|---|
| 确定性/可追溯骨架：state（多租户+乐观锁+加密+事务）/ supervisor / execution router / product_intelligence 确定性域 / product_truth / security / web / cli / CAD 双后端 / 供应链 / 手册链 | **达成 100%** | 26 子包全部有真实实现+测试锁定；1016 passed；核心链路（CLI→Supervisor→Router→Adapter→State→PI）逐层验证无空壳 |
| AI 智能接线：idea.decompose、product.derive_*、evidence 评估、LLM Provider | **代码就绪（08-13 时为 0%，现为 100% 代码 / 0% 运行时，缺 key）** | N-1 已落地（4f33f91+f536dac）：配置驱动装配 + 测试；doctor 诚实提示「配置 AIPD_MODEL_API_KEY+BASE_URL 可启用」；llm/client.py 真实客户端就绪 |
| v5.10 NPI 制造就绪：BOM/Cost/ValidationTest/Issue/MMDProjection/Manufacturing Readiness | **未动工（路线图内）** | 无表无服务；§14 接口清单已列；这是下一版本工作，非缺陷 |
| 发布工程收口 | **未完成（P0）** | release-ready 门禁 4 项失败；8 份审计文档未提交；PROVENANCE 锚点落后一个 commit |

**结论：代码层面的工作基本全部实现了。** 相比 08-13"承诺兑现了一半"，现在确定性骨架 100% + AI 接线代码 100%（差配置）。剩下的是：① 发布收口（一次管线重跑的工程量）；② 4 个 P1 缺陷；③ v5.10 的下一版本工作。**没有"没写完的代码"，但有"没签收的发布"。**

---

## 三、本轮实测发现的问题清单

### P0（当前仓库过不了自己的发布门禁——发布前必须清）

| ID | 问题 | 证据 |
|---|---|---|
| R-1 | **PROVENANCE.source_commit = 82d8fd4 ≠ HEAD e245555**，`commit_matches_head` 门禁失败 | `PROVENANCE.json:4`；门禁输出「82d8fd4… != e245555…」 |
| R-2 | **PROVENANCE.test_report = {"present": false}**，`test_numbers_from_report` 失败——1016 个真实测试数字没进证据 | `PROVENANCE.json:23-25` |
| R-3 | **Ed25519 签名失效**（清单刷新后未重签），`signature_verifiable` 失败 | 门禁输出「Ed25519 signature FAILED」 |
| R-4 | **工作区不干净**：8 份审计/走读报告未提交 git，`workspace_clean` 失败 | `git status`：docs/audit/*.md 全部 `??` |

> 修法是一条命令级：提交审计文档 → 重跑 release_evidence.py（含 test_report）→ 重签 → 重跑门禁。工程量 <1 小时，但**不修的话"发布证据体系"这个卖点就自相矛盾**。

### P1（真实代码缺陷，本版本内值得修）

| ID | 问题 | 证据 | 影响 |
|---|---|---|---|
| P1-1 | **视觉审核假通过裂缝**：`_vision()` 只返回 `bool(vision_backend)`——只要配置了视觉后端，character/cmf 一致性直接 `passed=True` 并标注「checked by vision backend」，但 `VisionAuditProvider.audit()` 从未被调用 | `visual_audit/auditor.py:72,104-114`；全仓 grep `.audit(` 仅 providers/__init__ 与测试 | 违背本项目第一原则「绝不假装成功」 |
| P1-2 | **认证到期比较时区炸弹**：`expires < datetime.now()`，aware 到期日 vs naive now → TypeError 崩溃；`_now_aware()` 定义了却没人用 | `supply_chain/certification.py:86-95` | 运行时崩溃 |
| P1-3 | **邮件附件跨会话丢失**：持久化 meta 由 `to_dict()` 生成不含附件字节，重启后 `download_attachment` 在持久化 meta 里找不到 `_attachments` | `mail/client.py:644-666` | 附件下载功能实际不可靠 |
| P1-4 | **状态实现双重维护**：scripts/aipd_store.py（旧单项目库）仍被 quality_gate/selftest_state/selftest_v4 import，与 src/state/db.py（新多租户库）并存 | `scripts/quality_gate.py:5` 等 | 两套状态语义漂移源 |

### P2（深化/UX 空间，按价值排序）

**UX 类：**
1. **doctor 对无关环境变量报硬失败**——本机 3 个未注册的 `CODEBUDDY_*` 环境变量让体检结论变「存在 1 项硬失败」。用户装个别的软件 doctor 就红了，应降为 warning。
2. **三套 OpenAI 兼容客户端并存**（llm/client.py urllib、evals_runner/completion.py、evals/runner.py requests）+ `len/3` vs `len//4` token 口径不一致——同一模型调用三种行为。
3. **README/CHANGELOG 版本文档漂移**：CHANGELOG 停在 5.6.0，v5.7~v5.9.2 和两轮重构没有任何条目；README 页脚 v5.6.0。新用户翻 CHANGELOG 会以为这个项目三个月没动。
4. web/views.py `available_actions` 把 `paused` 列入 pause 但 `pause()` 不处理该状态；UI 引导写 `AIPD_IMAGE_PROVIDER` 而实现用 `AIPD_IMAGE_PROVIDER_URL/KEY`——照着 UI 提示配会配错。
5. CLI 状态输出用 🟢🟡🔴 装饰字符（experience/owner_dashboard.py:36）——按本团队 P0 规则，应换纯文字/ASCII 状态符。

**工程类：**
6. integration marker 空转：pyproject 注册了但全仓仅 2 个文件使用，CI 的 `-m integration` 近乎白跑。
7. CI 的 license-scan 只打印不判失败（装饰性门禁）；ruff/mypy 在本地是硬基线但 CI 没有对应 job——**基线不设防**。
8. evals_out/ 被 .gitignore 忽略且只存了 5.0.0/5.4.0 报告——评测结果不可复现。
9. 死代码漂移源：KEY_CLAIM_TYPES 导出零消费、from_lifecycle 全仓零调用、`_records_from_rows/_records_result` 近重复。
10. 一次性补丁脚本 `_v592_p004_check.py/_v592_p009_check.py` 混在正式 scripts/ 里。

---

## 四、与"预期"的对齐结论

| 设计意图 | 现状 |
|---|---|
| 确定性骨架 | ✅ 100%，测试锁定 |
| AI 智能推理 | ✅ 代码就绪（N-1 完成），运行时差 key |
| 诚实优先 | ⚠️ 99%——P1-1 视觉审核裂缝是唯一违反处 |
| 分层纯净 | ✅ R-3 反转后 AST 可证 |
| 发布证据自洽 | ❌ 当前不自洽（P0×4），一次管线重跑可清 |
| 文档与代码同版本 | ❌ CHANGELOG/版本号双轨待收口 |
| v5.10 NPI | ⏳ 未动工，路线图内 |

---

## 五、下一步建议（按性价比排序）

1. **发布收口（P0×4，半天内）**：提交 8 份审计文档 → 重跑 release_evidence + 重签 + 重跑 release-ready 门禁至全绿。**这是"把已完成的代码变成可交付版本"的最后一步，不做等于白干。**
2. **P1 四连修（1-2 天）**：视觉审核真接线（或诚实降级为 NOT_VERIFIED 直到接好）＞认证时区统一 aware ＞邮件附件持久化字节 ＞统一状态实现。
3. **版本收口决策**：正式发布时把 pyproject/README/CHANGELOG 对齐到真实功能版本，补 v5.7~5.9.2 的 CHANGELOG 条目。
4. **UX 批次**：doctor 敏感 env 降级、三套 LLM 客户端收敛、web 配置提示对齐实现、RYG 状态符去 emoji。
5. **v5.10 NPI 立项**：按 v5.9 的「契约先行 → 确定性实现 → 测试锁定」节奏推进 BOM/Cost/ValidationTest/Issue/MMDProjection。

**一句话给用户**：这个版本把"确定性、可追溯、诚实"做到了接近生产发布级的高水准，且上一轮评审提出的所有债务都已真实清除；但**仓库当前过不了自己的发布门禁，代码写完了、发布没签收**。剩下的是半天收口 + 四个 P1 打磨 + 一条明确的 v5.10 路线——不是没写完，是差最后一程。
