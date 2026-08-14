# AIPD-OS 版本印象 + P2 收口迭代实施报告（2026-08-14）

> 评审对象：HEAD `c2665b3`（P0 发布收口 + P1 四连修之后的最新版本）。
> 评审方式：根 → src（26 子包，183 文件）→ scripts（36）→ state_service /
> migrations / tests（135）→ CI / 发布证据 全目录层级走读；5 路深潜代理
> 并行审计（编排核心 / CLI·体验·Web / 状态·安全·发布 / 产品域链 / 供应链·卫生）
> + 本人核心链路逐行验证 + 实测（pytest 全量 / ruff / mypy / doctor /
> onboard / release-ready 门禁）。
> 本报告同时回答「代码是否全部实现」与「还有什么可深化/UX 优化」，并记录
> 本轮一次性迭代执行的全部落地项。

---

## 一、版本印象（一句话）

**确定性骨架与诚实性纪律已是本仓见过的最好状态，代码层面的工作基本全部实现；
但「发布证据自洽」「正确性细节」「用户体验打磨」三类缝隙仍然存在——本轮已
把能低成本修掉的缝隙全部修掉并补上回归测试，仓库重新回到「自己过得了自己
门禁」的状态。**

## 二、达成度三层判定（回答「代码层面的工作全部实现了吗」）

| 层 | 判定 | 依据 |
|---|---|---|
| 确定性/可追溯骨架：state（多租户/乐观锁/加密/事务/迁移）· supervisor · execution router · idea 证据图 · product_intelligence 转译链 · product_truth · security · web · cli · CAD 双后端 · 供应链 · 手册链 | **达成 100%** | 26 子包全部有真实实现 + 测试锁定；本轮全量回归 10xx passed |
| AI 智能接线（idea.decompose / product.derive_* / LLM Provider） | **代码就绪**（缺用户配 key） | N-1 配置驱动装配已落地；doctor 诚实提示配置项；未配置诚实 EXTERNAL_DEPENDENCY |
| 发布工程收口 | **此前 7/8（test_report STALE + PROVENANCE 锚点落后一个提交）；本轮修复并全绿** | 见 §四 |
| v5.10 NPI（BOM/Cost/ValidationTest/Issue 制造就绪） | **未动工（路线图内）** | 属下一版本工作，非欠账 |

**结论：代码层面的工作基本全部实现了。** 剩下的不是「没写完的代码」，而是
「细节正确性 + UX 打磨 + 发布签收」。本轮把前两类中的全部 S/M 项落地。

## 三、本轮实测发现并已修复的问题（按类别）

### A. 正确性 bug（会导致错误结果/错误数据）

| # | 问题 | 修复 |
|---|---|---|
| A1 | closure 写回把 `evidence_id` 同时当 `fact_id` 传给 `link_evidence`——证据链到它自己身上，`list_evidence_for_fact` 永远查不到事实的证据 | `execution/closure.py`：捕获 `add_fact` 返回的 fact_id 正确传参 + 回归测试 |
| A2 | 决策中心「影响」列把 `impacts` dict 当 list 迭代，显示的是选项文本而非成本/性能/时间/安全 | `web/templates.py`：按 option 取四维影响渲染 + 回归测试 |
| A3 | `parse_pdf` 对二进制 PDF 直接 decode，满屏乱码被当作「已获取全文」（诚实性红线） | `research/fetchers.py`：二进制 PDF 返回空文本 not obtainable + 测试 |
| A4 | `fetch_fulltext` 同样把二进制下载体当全文；`default_expires_at` 产出 `...+00:00Z` 双时区后缀，过期时间静默失效 | `research/fulltext.py`：二进制拒绝 + 去 "Z" 后缀 + 测试 |
| A5 | 视觉审核 `passed` 非布尔被 truthy 化（模型返回字符串 "false" → 假通过） | `visual_audit/providers.py` + `auditor.py`：严格 `is True` 判定 + 测试 |
| A6 | `RealImageGenProvider._decode_image` 把 JSON 错误体/非图像字节当真实图产出 | `imggen/providers.py`：error 体/无 data/非 PNG-JPEG 签名一律拒绝 + 测试 |
| A7 | `import_lab_report` 没有 `.xlsx` 分支（错误信息却谎称支持），`import_lab_xlsx` 从未被调用 | `supply_chain/lab.py`：补 dispatch + 测试 |
| A8 | Gmail OAuth：SMTP 把 access_token 当明文密码 login、IMAP 把 XOAUTH2 串当明文密码 login——真实凭据下必然认证失败 | `mail/client.py` + `gmail_oauth.py`：`auth_mechanism="XOAUTH2"` SASL 认证 + 测试 |
| A9 | `rollback_v5` 只按 tenant 过滤，多项目回滚把别的项目数据并入目标项目（数据污染） | `migrations/rollback_v5.py`：按 project_id 过滤 + fetchone None 守卫 |
| A10 | `is_expired` 混用 naive/aware 时间戳抛 TypeError；`backup.retention_prune` 同类崩溃 | `product_truth/models.py`、`state/backup.py`：UTC 归一化比较 + 测试 |
| A11 | Gate maturity 用字符串 `"I0" < "I2"` 依赖字典序 | `gate_criteria.py`：按枚举声明顺序比较 |
| A12 | `supervisor._mark_stale` 用 `LIKE %W-001%` 子串匹配，误伤前缀型 ID | 解析 `depends_on_json` 精确判等 + 测试 |
| A13 | `verify_file` 对已算出的 SHA 再算一遍（大产物双倍 IO）；`RunController.available_actions` 对 paused 状态仍提供 pause（无效动作） | 缓存 SHA；pause 集合修正 + 测试 |
| A14 | 三套 token 估算口径（len/3 vs len//4）并存；`token_meta` 把输入侧文本计入 tokens_out | 收敛为 `llm/tokens.py` 唯一实现，方向修正 + 测试 |

### B. 门禁假通过（fail-open → fail-closed）

| # | 问题 | 修复 |
|---|---|---|
| B1 | pip-audit 不可用/失败时 `no_unacknowledged_cve` 空真通过 | 无法执行即失败；已记录 CVE 走 `--ignore-vuln` 显式承认 |
| B2 | 5 项证据检查（revision/bom/gdt/ctq/expired）在数据缺失时空真通过 | 缺失即失败，测试夹具补全数据 |
| B3 | git 不可用/非仓库时 `workspace_clean` 判「干净」 | git 失败显式失败 + 测试 |
| B4 | `audit_dependency_ack` 未装 pip-audit 时 FileNotFoundError 崩溃；空承认集合直接拒绝（与 docstring「空则严格审计」矛盾） | 捕获 + 空集合严格审计 |

### C. UX / 一致性

| # | 问题 | 修复 |
|---|---|---|
| C1 | `aipd doctor` 因环境中存在与 AIPD 无关的敏感变量（CODEBUDDY_* 等）硬失败 | 只审查 `AIPD_*` 前缀；未登记降级 warn |
| C2 | CLI 状态输出用 🟢🟡🔴 emoji | 纯文本「良好/需关注/高风险」 |
| C3 | web/onboarding/doctor 三处 provider 配置提示与实际读取的环境变量不符（照着配会配错） | 全部对齐实现真实读取的 env |
| C4 | `--json` 模式下 stdout 被进度/报告文本污染（test/eval/package/operate） | 进度/日志统一走 stderr；`_emit` 加 `default=str` |
| C5 | `aipd eval` 缺 `--baseline`（deprecated 别名却有）；SystemExit 字符串 code 崩溃；`main.py` 帮助示例 `--stage dv` 笔误 | 补 parity + int() 守卫 + dv→dvt |
| C6 | `cmd_industrialize` 对 `--stage` 完全不做校验 | 校验 evt/dvt/pvt + 测试 |
| C7 | skip-link 不可聚焦（CSS 缺 :focus 回显）；按钮冗余 tabindex | 补 `.skip:focus` 规则；清冗余属性 |
| C8 | `aipd operate` CLI 丢弃进度事件（长任务无任何阶段反馈） | 打印 step→message |
| C9 | Web POST application/json 体被静默忽略 | 按 Content-Type 解析 JSON 体 |
| C10 | MCP 工具异常以裸 traceback 冒泡 | 统一结构化 `{ok,error}` 包装 |

### D. 卫生 / 文档

| # | 问题 | 修复 |
|---|---|---|
| D1 | CHANGELOG 停在 5.6.0（v5.7~v5.9.2 与两轮重构零记录） | 补 `[Unreleased]` 全 workstream 条目 |
| D2 | SKILL.md 标题/命令清单过期（缺 ui/product/operate/dashboard/onboard/reset/recover 7 项） | 刷新为 27 个主线命令 + 分组 |
| D3 | state_service README 声称「每项目独立 SQLite」且「生产化必须补充加密/审计/备份」——均已实现 | 更正为单库多租户 + 已实现清单；requirements 补 cryptography/jsonschema |
| D4 | 一次性补丁脚本 `_v592_p004/_p009_check.py` 混在正式 scripts/ | 归档至 `docs/audit/legacy-patch-scripts/` |
| D5 | 发布自检（selftest_state/selftest_v4/quality_gate）与 runtime_preflight 仍锚定废弃 aipd_store | 全部切换到 `AIPDStateDB` 并实跑通过 |
| D6 | CI 缺 lint job（ruff/mypy 硬基线不设防） | 新增 `lint` job 并挂入 release-ready needs |
| D7 | `registry_data` import 失败被静默吞掉（能力矩阵悄悄变空） | 记录 warning |
| D8 | 死代码/重复：`_AttachFieldsFilter` 空操作、`db._next_id` scan-max 无调用、LLM 两套 JSON 解析助手、quotes 两套 `_records_*`、`_SYSTEM_BASE` 漂移、`"gpt-4o-mini"` 双处硬编码、`utcnow()`（Py3.12 废弃） | 删除/收敛/统一 + 测试 |

## 四、发布收口（P0）

基线状态：`production_release_gate.py --release-ready` **7/8**——最新审计报告提交
（c2665b3）后 PROVENANCE/test_report 锚点落后一个提交，`commit_matches_head` 与
`test_numbers_from_report` 失败。本轮收口流程（§五第 8 步）：
提交代码 → 全量测试带 `AIPD_SOURCE_COMMIT` 锚定 → 刷新 SOURCE/BUNDLE/
PROVENANCE/RELEASE_MANIFEST → 重打 bundle → Ed25519/MAC 重签 → 门禁 8/8 全绿。

**最终门禁结果（8/8 PASS，`--tag v5.6.0`）**：
`workspace_clean` ✅ · `commit_matches_head` ✅ · `source_manifest_zero_diff` ✅ ·
`bundle_manifest_zero_diff` ✅ · `test_numbers_from_report` ✅（passed=1051 failed=0
total=1054，source_commit=24227f6）· `signature_verifiable` ✅（Ed25519）·
`no_secrets` ✅ · `no_unacknowledged_cve` ✅（pip-audit 实跑 + 18 条已记录 CVE
显式承认）。

**提交与推送**：`24227f6`（代码+测试批次）→ tag v5.6.0 更新指向 →
`5bc6454`（发布证据刷新）→ `origin/main` 与 `v5.6.0`（forced update）已推送。

## 五、本轮实施计划与执行结果

1. ✅ 全仓系统性走读（5 路并行深潜 + 本人核心链路逐行验证）；
2. ✅ 正确性 bug 批次（A1-A14）修复 + 回归测试；
3. ✅ 门禁 fail-closed（B1-B4）修复 + 测试；
4. ✅ UX/一致性批次（C1-C10）；
5. ✅ 文档/卫生批次（D1-D8）+ CI lint job；
6. ✅ ruff / mypy 全仓 0 保持；
7. ✅ 全量回归 **1051 passed / 0 failed / 3 skipped**（含本轮全部新增回归测试）；
8. ✅ 发布收口（提交 `24227f6` + `5bc6454` / tag v5.6.0 更新 / 证据刷新 / Ed25519+MAC 重签 / 门禁 8/8 全绿 / 推送 origin）。

## 六、遗留（记录在案，不阻塞）

- 版本号双轨制（pyproject 5.6.0 vs 功能 v5.9.2+）：正式发布时统一收口（发布工程决策）；
- v5.10 NPI（BOM/Cost/ValidationTest/Issue/MMDProjection）：路线图下一版本；
- 结构性大项（需专门立项，非本轮 S/M 范畴）：
  - closure/limits/telemetry 三套「已实现未接线」层：决定去留（接入 run_supervisor 或标记实验层并删除）；
  - 三套 OpenAI 兼容 HTTP 客户端收敛为 `LlmClient` 唯一实现（vision/eval 薄适配）；
  - Supervisor 类型标注补全、`next_id` 扫描改 SQL MAX/序列表、状态查询单连接聚合；
  - 备份改用 `sqlite3.backup()` 活库安全快照；`add_change` 泛化敏感字段脱敏；
  - Gate/Snapshot 在多 Idea 项目下绑定 `snap.idea_id`（当前用 `ideas[-1]`）；
  - 加密 KDF 加盐（PBKDF2/scrypt）、`_check_secrets` ACK 逐条化 + 非 .py 后缀扫描；
  - schema_check 名不副实（未做真实 jsonschema.validate）扩展；
  - web POST 无 CSRF（localhost-only 场景下的纵深防御）。

---

## 附：第二轮（CLI/体验审计报告消化，2026-08-14）

依据 CLI/体验模块簇审计报告（subagent 15601d1b）核对后，上一轮已覆盖
impacts 渲染、provider env 对齐、--json 纯净、eval --baseline、_emit
default=str、SystemExit 保护、onboarding 去重/缓存。本轮补齐剩余项：

| 项 | 落地 |
|---|---|
| _options_of / _bump_version / _metadata 三组双实现 | 收敛为 `experience/common.py` 唯一实现（instructions/intent_engine/operations/artifact_preview/web 全部 import 复用）|
| CAD gate 累计成熟度内联复制（_helpers vs legacy） | `cmd_run_cad_chain` 复用 `_cad_gate_summary` |
| 多条件意图只落实第一条 | `auto_rework` 逐条展开主条件 + constraints 写事实（`recorded_fact_ids`）；`analyze_impact` 受影响制品取各条件并集 |
| revert_operation 回滚过宽 | 审计记录写入 `affected_ids`；回滚只作用于最近一次可撤销操作记录的制品；历史无清单记录如实报告不猜测 |
| `failure_type == ["external"]` 列表全等 | `"external" in (...)` 成员判断 |
| `_run_script_main` 只捕获 stdout | 同时捕获 stderr 并转发（信息不丢、stdout 不被污染）|
| `_silent` 吞掉 manual_chain 全部输出 | 捕获后转发 stderr |
| product_commands `_emit` indent 漂移 | 与 `_helpers._emit` 同契约（单行 + default=str）|

新增回归测试 6 个（多条件事实/影响并集、精确回滚、历史记录诚实降级、
共享助手同源、_silent 转发）。

**第二轮最终结果**：全量回归 **1057 passed / 0 failed / 3 skipped**；ruff/mypy 0；
提交 `496f011`（代码）+ tag v5.6.0 更新指向 + 发布证据刷新（test_report 锚定
496f011，bundle 重建 + Ed25519/MAC 重签）+ 证据提交；`release-ready --tag v5.6.0`
**8/8 PASS**；已推送 origin。

---

## 附：第三轮（供应链/卫生审计报告消化，2026-08-14）

依据供应链/适配器+仓库卫生审计报告（subagent 205deb78）核对后，前两轮已覆盖
gmail XOAUTH2、lab .xlsx 断链、quotes 重复+表头校验、token 口径、discover()
maturity_ceiling、SKILL/QUICKSTART/--stage、CHANGELOG。本轮补齐剩余项：

| 项 | 落地 |
|---|---|
| 事实状态码 "S" 三重语义重载 | 统一正式 epistemic 语义：superseded 报价 → R（Retired）、失败阶段实验 → E（可靠外部证据）、expiry stale → R（Retired）；fact.schema.json 描述对齐（S=纯 Simulation、R=Retired）；STATUS_SEMANTICS.md 复用清单标记「已清理」 |
| certification `ok` 恒 True | `ok`=字段完整可验证，新增 `registered`（登记 ≠ 已验证）；PDF 测试改断言 ok=False |
| expiring_certs 查询副作用 | `dataclasses.replace` 拷贝，不再突变注册表原对象 + 回归测试 |
| writeback `passed is False` 死分支 | 恒 "high" 显式化 |
| builtin.py docstring 注册范围 | 更正为「10 个内置核心适配器；product.*/idea.* 由 runtime 动态装配」 |
| mail_rfq 配 AIPD_MAIL_PROVIDER 仍不发送 | 改读实现真实读取的 AIPD_SMTP_HOST/MAILPIT；配 SMTP 后经 mail.client.send_email 真实发送（sent 仅成功为 True），失败诚实 external_blocked + 2 个回归测试 |
| schema_check 名不副实 | schema Draft-7 元校验 + 同名模板数据真实 jsonschema.validate + 3 个测试 |
| 测试盲区 | 新增 test_mail_parse.py（8 个 MIME 解析/附件/主题/线程测试，含 RFC2047 解码改进）+ test_idea_product_adapters.py（4 个适配器直接测试）+ lab.import_lab_xlsx 直接测试 |

**第三轮最终结果**：全量回归 **1075 passed / 0 failed / 3 skipped**；ruff/mypy 0；
提交 `9d05733`（代码）+ tag v5.6.0 更新指向 + 发布证据刷新（test_report 锚定
9d05733，bundle 重建 + Ed25519/MAC 重签）+ 证据提交；`release-ready --tag v5.6.0`
**8/8 PASS**；已推送 origin。

---

## 附：第四轮（状态/安全/发布基础设施审计消化，2026-08-14）

依据状态/安全/发布审计报告（subagent 768650fb）核对后，前三轮已覆盖 rollback
project 过滤、add_fact changes 脱敏、CVE/证据/git fail-closed、doctor 敏感 env、
aipd_store 自检切换、db._next_id 死代码、state_service README/requirements。
本轮补齐剩余项：

| 项 | 落地 |
|---|---|
| 备份用 shutil.copy2 复制活库 | BackupManager.create_backup 与 RecoveryService.backup 均改 sqlite3.backup() 活库快照 + integrity_check 测试 |
| 迁移非原子 / 无并发锁 | migrate() 包 BEGIN IMMEDIATE（并发迁移串行化）；executescript 隐式 COMMIT 消除（_split_statements 引号/注释感知拆分 + _exec_script 事务内逐条执行）；schema_migrations 记录与 DDL 同事务提交 |
| _authorize actor=None 静默跳过 | StateService.trusted_local_api 传输边界标记：进程内可信 API 允许；run_http（HTTP 网络边界）翻转 False，actor=None 抛 UnauthorizedError（fail-closed） |
| AIPD_ACK_SECRET 整文件豁免 | ACK 必须带理由（伪造/fake/mock/fixture/样例）才豁免；扫描后缀扩展到 .json/.yaml/.yml/.toml/.md/.env |
| mask_secret 长度≤2 与 docstring 不符 | 长度≤2 全部打 *（docstring 契约）+ 测试更新 |
| require_mask 恒真死分支 | 合并为 `scope in SENSITIVE_SCOPES` 单一语义 |
| objects._safe 不中和 . / .. | 去首尾 "."（".."→"_"），路径穿越封堵 + 测试 |
| GET /health 触发 migrate 副作用 | health_check 改只读 current_version（不建表不迁移）；current_version 本身改为纯只读探测 |
| current_version 建表副作用 | 同上（sqlite_master 探测，无 schema_migrations 时返回 0） |

新增回归测试 8 个（备份 integrity、迁移幂等/语句拆分、传输边界拒绝、ACK 理由、
对象路径、健康只读、密钥扫描扩展）。

**第四轮最终结果**：全量回归 **1082 passed / 0 failed / 3 skipped**；ruff/mypy 0；
提交 `1a57427`（代码）+ tag v5.6.0 更新指向 + 发布证据刷新（test_report 锚定
1a57427，bundle 重建 + Ed25519/MAC 重签）+ 证据提交；`release-ready --tag v5.6.0`
**8/8 PASS**；已推送 origin。
