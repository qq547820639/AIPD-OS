# 阶段7 审计：供应链与物理验证链

- 审计目标：AIPD-OS 阶段7 供应链 / 物理验证链（quote、RFQ、supplier、lab/EVT-DVT-PVT、certification、纠偏、回归、事实回写）
- 审计范围：`src/aipd_os/supply_chain/`（analysis / certification / lab / quotes / suppliers）、`src/aipd_os/tool_adapters/`（mail_rfq_adapter / supplier_adapter / evt_dvt_pvt_adapter）、`src/aipd_os/experience/external_wait.py`、`src/aipd_os/execution/adapter.py`、`src/aipd_os/execution/decision_policy.py`、`src/aipd_os/cli/commands.py`（industrialize）
- 运行环境：`.venv/bin/python`，cwd=`AIPD-OS`
- 判定等级：`fully_implemented` / `partially_implemented` / `external_dependency` / `not_implemented` / `not_verifiable`
- 核心规则：**适配器返回占位/模拟数据 ≠ 真实实现**；物理证据（报价/制造/测试/认证/批准）缺失时状态必须保持 HOLD/未验证，绝不虚构。

---

## 测试结果

| 测试集合 | 命令 | 结果 |
|---|---|---|
| 供应链 + 认证 | `pytest tests/test_supply_chain.py tests/test_certification.py -q` | **20 passed** |
| 外部等待视图 | `tests/test_external_wait.py` | 6 passed（确定性分组/中文输出） |

---

## 能力逐项判定

| # | 能力 | 状态 | 证据（文件:函数/行） | 测试 | 局限 |
|---|---|---|---|---|---|
| S1 | Gmail / 邮件适配器（真实收发） | **not_implemented**（外部依赖占位） | `tool_adapters/mail_rfq_adapter.py:MailRfqAdapter.execute` L32-72：未配置 `AIPD_MAIL_PROVIDER` 时仅写出外部任务包并抛 `external_blocked`（L41-54）；配置后仍 `"sent": False`（L69），只生成确定性草稿 | `test_supply_chain.py::test_mail_rfq_no_provider_writes_task_package`、`test_mail_rfq_with_provider_makes_draft` | **无任何真实邮件发送/接收代码**；`sent` 恒为 False，绝不声称已发送 |
| S2 | RFQ 生成与发送 | **partially_implemented** | 草稿生成真实：`mail_rfq_adapter.py` L56-65 确定性拼装 subject/body；发送未实现：恒 `sent:False` 或 `external_blocked` 任务包 | 同上 | 只有"草稿合成"，无真实 SMTP/Gmail 发送；发送必须走外部人工/工具 |
| S3 | 供应商回复读取 | **not_implemented** | 无任何读取供应商邮件/回信的适配器；仅 `supplier_adapter.py:SupplierAdapter.execute` L37-79 登记用户手动提供的文件并解析其中的报价 CSV/JSON | 无 | 无"收件箱/回信"读取路径；回复需人工把文件交回系统 |
| S4 | 报价附件解析 | **fully_implemented**（CSV/JSON） | `supply_chain/quotes.py:parse_quote_file` L79-126；`normalize_quote` L47-66；`supplier_adapter.py` L54-70 接入 | `test_supply_chain.py::test_parse_normalize_canonical_csv_quote`、`test_parse_quote_unsupported_extension` | 仅支持 `.csv`/`.json`；PDF 报价不支持（抛 `ValueError`，诚实不伪造） |
| S5 | MOQ / 模具费 / 单价 / 交期 | **fully_implemented** | `quotes.py:normalize_quote` L47-66 规范化 `moq`/`tooling_fee`/`unit_price`/`lead_time_days`（非负钳制、非法转 0）；`CANONICAL_CSV_HEADER` L17-24 | `test_supply_chain.py::test_parse_normalize_canonical_csv_quote`、`test_normalize_quote_coercion` | 数值从真实文件解析，无模拟 |
| S6 | 报价修订（版本化） | **fully_implemented** | `quotes.py:QuoteRegistry.add_quote` L152-183：同 supplier+part 版本+1 并将旧版标 `superseded`；`get_official` L185-192 无 official 直接抛 `KeyError`（绝不虚构） | `test_supply_chain.py::test_quote_registry_versioning_supersedes`、`test_quote_registry_no_official_raises` | 版本仅在单进程/内存 registry 内，无持久化 |
| S7 | 供应商资质 | **fully_implemented** | `suppliers.py:SupplierRegistry.qualify` L32-43：仅当档案中真实含 `required_cert` 才判定合格，否则 False | `test_supply_chain.py::test_supplier_qualify_requires_cert` | 内存注册表；无外部资质库导入 |
| S8 | 物料证书 | **partially_implemented** | `certification.py:CertificationRegistry.transition` L51-89 与 `verified()` L29-31：无 `evidence_ref` 禁止进入 verified；到期自动 expired；`SupplierProfile.certificates`（suppliers.py L9-17） | `test_certification.py`（6 项，含 `test_verified_requires_evidence_ref_after_fact`） | 逻辑真实且诚实，但**无证书文件导入适配器、无持久化、未接入 CLI/执行链**；除非真实 evidence_ref，否则恒为 pending |
| S9 | EVT/DVT/PVT 文件导入 | **fully_implemented**（CSV/JSON/XLSX） | `evt_dvt_pvt_adapter.py:ValidationDataAdapter.execute` L43-79 委托 `supply_chain/lab.py:import_lab_csv/json/xlsx`；PDF/DOCX → `external_blocked`（lab.py L103-120） | `test_supply_chain.py::test_lab_import_analysis_and_tasks`、`test_lab_report_pdf_external_blocked` | XLSX 需 `openpyxl`，缺失时抛 `external_blocked`（诚实）；PDF/DOCX 报告无法本地解析 |
| S10 | CSV/XLSX/PDF 测试数据解析 | **CSV/JSON/XLSX fully、PDF partially(外部)** | `lab.py` import_lab_csv L52 / import_lab_json L61 / import_lab_xlsx L75（openpyxl 缺失→external_blocked L82-87）；PDF/DOCX → external_blocked L115-119 | `test_lab_import_analysis_and_tasks`、`test_lab_report_pdf_external_blocked` | XLSX 强依赖 openpyxl；PDF 无本地解析，须外部工具/人工 |
| S11 | 失败根因 | **partially_implemented** | `analysis.py:analyze_stage` L8-49 定位失败项；`mark_regression` L70-85 对比基线识别回归/改进 | `test_supply_chain.py::test_mark_regression` | 仅识别"失败项/回归"，**无更深层根因分析**（如根本原因分类/关联因素） |
| S12 | 纠偏工作包 | **fully_implemented** | `analysis.py:create_correction_tasks` L52-67 为每个失败项生成 `{work_id,type,stage,test_item,action,reason}`；`evt_dvt_pvt_adapter.py` L63 接入 | `test_supply_chain.py::test_lab_import_analysis_and_tasks` | 纠偏动作仅 `rerun`/`redesign` 二选一，较为简化 |
| S13 | 回归验证 | **fully_implemented** | `analysis.py:mark_regression` L70-85 | `test_mark_regression` | 纯函数，需外部传入 `prior_baseline`；系统内无持久化基线自动跟踪 |
| S14 | 物理结果回写 facts/CAD/BOM/manual | **partially_implemented** | `analysis.py:update_facts` L88-105 写回 facts 的 `verification.<stage>`（无失败才 `passed_flag`，`total>0` 才可通过）；`propagate_impact` L108-127 将受影响 BOM/CAD 行标 `stale`；均被 `evt_dvt_pvt_adapter.py` L62-67 与 CLI `cmd_industrialize`（commands.py L812-850）调用 | `test_supply_chain.py::test_update_facts_merges_verification`、`test_propagate_impact_marks_stale`、`test_no_official_quote_and_no_executed_lab_not_passed` | 回写覆盖 **facts（通过/失败计数）与 BOM/CAD（stale 标记）**；**未回写齐全的 CAD 图纸或产品手册**（manual 无回写路径）；`propagate_impact` 只标 stale，不写达标值 |

---

## 诚实性 / 反虚构规则核查

| 规则 | 是否成立 | 代码证据 |
|---|---|---|
| 未收到真实报价不得声明 formal quote | **成立** | `quotes.py:QuoteRegistry.get_official` L185-192 无 official 直接抛 `KeyError`；CLI `cmd_industrialize` L829-830 无报价文件时输出"未登记任何官方报价（不发散、不虚构）" |
| 未制造不得声明样机完成 | **成立** | 供应链模块**无任何制造/样机"完成"声明代码**；无制造能力即无声明 |
| 未测试不得声明通过 | **成立** | `analysis.py:update_facts` L98-102：`total>0 且 failed==0` 才 `passed_flag=True`；`analyze_stage` L23-24 从真实记录计数；CLI L840-841 `total>0 and failed==0`。测试 `test_no_official_quote_and_no_executed_lab_not_passed` 验证空记录 `passed_flag=False` |
| 未认证不得声明 certified | **成立** | `certification.py:transition` L68-74 无 `evidence_ref` 返回错误且状态保持 pending；`verified()` L29-31 需 status+evidence_ref 双条件。测试 `test_cannot_verify_without_evidence_ref`、`test_verified_requires_evidence_ref_after_fact` |
| 未经用户批准不得发送订单/正式生产图纸 | **成立** | ① 无任何 PO/下单/正式图纸发送代码；② `mail_rfq_adapter` `sent` 恒 False（L69）；③ `decision_policy.py:ASK_CATEGORIES` L20-33 含 `tooling_or_purchase`/`formal_drawing_release`/`production_release`/`irreversible_investment`，`should_ask_decision` L45-80 对这类不可逆投入返回 True（须先征询决策） |

**结论**：5 条诚实性规则**全部成立**。当真实报价/制造/测试/认证/批准证据缺失时，系统通过 `external_blocked` 任务包、`get_official` 抛错、`passed_flag=False`、`transition` 拒绝 + 决策门禁，将状态保持为未验证/HOLD，**未发现任何虚构报价、制造、测试、认证或批准的逻辑**。

---

## 小结

- **真实实现（deterministic + 测试）**：报价解析（CSV/JSON）、MOQ/模具费/单价/交期规范化、报价版本化修订、供应商资质、实验室 CSV/JSON/XLSX 导入、阶段分析/通过判定、纠偏工作包、回归对比、事实回写（verification）、BOM/CAD stale 传播、认证状态机（含反虚构护栏）、外部等待汇总。
- **占位/外部依赖适配器（返回模拟或仅外部任务包）**：`mail_rfq_adapter`（永不真实发送，`sent:False` 或 `external_blocked` 任务包）、`supplier_adapter`（仅登记人工提供的文件，非真实回复读取）。
- **未实现**：真实邮件收发（Gmail/SMTP）、供应商回复自动读取、PDF/DOCX 报告本地解析、深层失败根因、完整 cad/manual 回写。
- **关键发现**：`update_facts` 与 `propagate_impact` 将验证结果写回 facts 与 BOM/CAD（stale），但**未写回产品手册**；证书与报价登记均为内存态，无持久化/导入适配器。
- **反虚构规则**：5 条全部成立，系统在证据缺失时保持 HOLD/未验证，不虚构。