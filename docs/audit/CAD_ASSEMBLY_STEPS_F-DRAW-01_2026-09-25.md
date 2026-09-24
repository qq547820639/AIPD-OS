# F-DRAW-01 第 18 片：装配步骤文档的生产者（2026-09-25）

对应 C6 生产图纸包 15 项交付物里的 **`装配/维护`**（分母逐字取自
`references/production-cad-deliverables.md:3`）。本片把这一项从 `absent` 升到
`producer`，**只升装配那一半**：维护指引仍无生产者，要属主给内容。

排序来路：`docs/audit/C6_COVERAGE_CENSUS_F-C6-01_2026-09-25.md` §九 第 2 项
（「按零实现 + 可数字化 + 不需属主拍板」排；维护那一半需要属主，故拆两半先做装配）。

---

## 一、要拍板的事与结论

C6 要一份「装配/维护」交付物。本仓此前**完全没有落点**：`assembly_instructions`
这个键在三个地方被声明却没人生产它——

- `src/aipd_os/cad/maturity.py:29`（C6 需求项列表）
- `scripts/production_release_gate.py:39,53`（C6 项 + `FILE_KEYS`：值必须是真存在、
  哈希对得上的文件）
- `scripts/cad_maturity_gate.py:32`、`scripts/selftest_v3.py:31`（`assembly.md`）

结论：**生产者 = 从装配清单里作者声明的步骤序列渲染 Markdown + 证据侧车，并让
release manifest 写出 `assembly_instructions` 那一格**。不建 operations 表（那是
第 16 片已裁决不做的事），不做生成式装配说明，不做 PDF 版式。

## 二、技术选型（本机真实检索，六维对比）

检索动作与读到的东西都记在这里；**没读到的地方按没读到写**。

| 候选 | 功能匹配度 | License | 维护活跃度 | 安全风险 | 代码质量 | 适配成本 | 处置 |
|---|---|---|---|---|---|---|---|
| `Ayaan577/Assembly_Instruction_Generation-IITK`（T5 seq2seq，BoM→自然语言装配步骤） | 形态最接近（结构化 BoM 出步骤），但输出是模型生成的自然语言，**不引用图上件号**、不可追溯到受控图纸 | 仓库根目录清单里**没有 LICENSE 文件**（GitHub API 列全 7 项：两个数据集 zip、三个 notebook、README、83 字节的 `TRAINING MODEL`）→ 无授权不可复用 | 0 star，课程项目，2025-08 后未动 | 权重放在 Google Drive 外链文件里，无法哈希核验；要拖 PyTorch/transformers 整套推理链 | notebook 驱动、路径硬编码（README 让用户「Update the dataset paths」） | 高（新依赖 + 推理不可复现） | **不复用**；只借「步骤从物料结构长出来」这个形态，把结构换成作者声明 |
| Odoo `addons/mrp/models/mrp_routing.py`（`mrp.routing.workcenter`，本机按 commit f254c797 取到全文） | 工序是**独立记录**：必填 `workcenter_id`、`sequence`、工时算式（`time_cycle`/`time_total`）、`cost`、`blocked_by_operation_ids` 依赖 + `_check_no_cyclic_dependencies` 环检测——比「一份文档」大得多的一整套排产主数据 | LGPL-3（文件头 "Part of Odoo. See LICENSE file"） | 极活跃（主线仓库） | 依赖整个 Odoo 运行时与数据库 | 成熟 | 极高（要建 operations 表族，正是第 16 片裁决不做的） | **不复用**；借两点——顺序是声明字段、以及「内部排序键 vs 印出来的序号」的差别（见下） |
| InvenTree 生态（GitHub 检索 `inventree build order`，6 个命中） | 全是 0 star 微插件（quick-build / build-tree-generator / build-blockers / kicad-assembly / stock-reconciliation），没有一个产装配步骤文档 | GPL-3（核心） | 插件多为 2026 年新起、单个维护 | 装第三方插件即引第三方代码 | 参差 | 中 | **不采用**；其核心文档我这次取的 URL 404，**没读到就不引用** |
| S1000D 程序化结构（步骤 + 图上件号 callout） | 语义最贴（每步引用插图件号） | 那份中文导读（manualsware）称「它是免费的！可以通过S1000D官方网站免费下载：www.s1000d.org」——**我抓 s1000d.org 失败，这句未能验证** | — | — | — | 需按 CSDB/XML 全套实现 | **借结构不借标准**：编号步骤 + 每步显式列件号 + 边界自陈；导读里没有 FWA/CTA 细节，故不声称按其实现 |
| 交付介质：Markdown + `.evidence.json` / reportlab PDF / python-docx | Markdown 可逐字断言、可进门哈希；PDF 是车间展示件 | 全部仓内已有或标准库 | — | 无新增依赖 | 与本仓 `generate_*() -> 证据字典` 同形 | 最低 | **选 Markdown**。PDF 不是不能做：本机实测 reportlab 5.0.0 + `UnicodeCIDFont("STSong-Light")` 出中文成功（2374 字节 PDF），本轮不做的是**排版与分页判据**；docx 未安装，且本仓把 .docx 当外部输入拒绝（`supply_chain/lab.py:26,113`） |

**关键取舍**（这一步真的改变了实现）：

1. 序号连续性。Odoo 的 `sequence` 默认 100、**故意留空档**好插队，因为它是内部排序键；
   而印在受控文件里的「步骤 N」是正文本身，断档等于当着一线操作者的面少一页。
   所以本片的 `no` 要求 1..N 连续，断档当场 `ValueError` 并点名缺哪个号（M2 已验证开火）。
2. 作者写的字段一个都不丢。清单里出现 `torque` 之类不承载的字段是 **rc=2 拒绝**，
   不是静默丢弃——丢掉就得到一份「少了一格还自称完整」的文档。
3. 顺序不推断。与爆炸位移同一条纪律：不从爆炸向量、不从装配约束、不从遍历顺序反推。

## 三、实现落位

- `src/aipd_os/cad/assembly_steps.py`（新增）：`parse_assembly_steps`（校验声明）、
  `build_step_plan`（球标↔步骤双向闭合）、`_markdown`、`generate_assembly_steps`
  （写 `.md` + `.evidence.json`，返回证据字典）。不 import CadQuery/ezdxf——文档不需要投影，
  但 STEP 存在性照样过 `parse_assembly_manifest`。
  侧车**不复用** `drawings2d._finish_evidence`：那条收尾会盖 `hidden_line_method`，
  隐藏线求法是图纸的事实，写进步骤文档的证据里就是给读者一个不相干的字段。
- `src/aipd_os/cli/commands_drawing.py`：`cmd_drawing_assembly_steps`；顺手把装配图与
  步骤文档共用的 `--db/--bom` 读法抽成 `_bom_lines_or_none`（原文案逐字保留），
  否则两条命令对「只给一半参数」「库不存在」「BOM 编号写错」会各自漂。
- `src/aipd_os/cli/main.py` + `command_contract.py` + `commands.py`：
  `aipd drawing assembly-steps` 子命令、契约条目（`requires_args` = manifest/out/part）、
  注册表接线；`release manifest` 多一个 `--steps-doc`。
- `src/aipd_os/release_manifest.py`：`_collect_steps()`——没交文档就**不写这一格**，
  交了则 `assembly_instructions = {path, sha256}` + `assembly_steps` 汇总
  （`step_count` / `declared_balloons` / `unreferenced` / `not_covered` / 侧车哈希），
  三类阻断判据 `steps_missing` / `steps_evidence_missing` / `steps_evidence_incomplete`
  / `steps_balloons_uncovered` / `steps_not_closed`。
- `src/aipd_os/registry_data.py`：新增能力行 `cad.assembly_instructions`（总数 81→82）。
- `scripts/c6_coverage.py`：`装配/维护` 条目 `absent → producer`，note 里写明只覆盖一半。

## 四、常驻用例

`tests/test_cad_assembly_steps.py` 29 条，分六组：序号是声明的（8）、步骤只认已声明球标（5）、
文档正文（6，含「材料缺了不许拿工艺顶」）、证据侧车（3）、CLI 面（3）、release manifest
看得见这份文档（4，含没交文档不写键）。

## 五、变异电池（`/tmp/slice18-mutations.py`，14 条全开火）

| # | 注入的坏判据 | 开火的用例 |
|---|---|---|
| M1 | 缺步骤号改为按遍历顺序代发 | 1（traversal_order） |
| M2 | 取消断档检查 | 1（gap） |
| M3 | 未知字段静默丢而不拒 | 1（unknown_field） |
| M4 | 允许引用没声明的球标 | 1（cite_a_declared_balloon） |
| M5 | 同步内重复球标静默去重 | 1（twice_in_one_step） |
| M6 | 没人装配的球标当作已覆盖 | 3（issue / 侧车 / manifest 阻断） |
| M7 | 数量绑不上时折成 0 | 1（unbound cells） |
| M8 | 材料缺了拿工艺顶 | **首轮全绿→存活**：补一条「材料空、工艺有值」的样本后开火 |
| M9 | 没交文档也写 `assembly_instructions` | 1（writes_no_key） |
| M10 | 步骤闭合问题降为不阻断 | 1（blocks_readiness） |
| M11 | 证据不再声明自己不承载什么 | 2（not_covered / manifest 传播） |
| M12 | 侧车不存在时直接去读 | 1（missing_sidecar_is_blocking） |
| M13 | 按文件顺序而非声明序号渲染 | 1（file_order） |
| M14 | 文档哈希抄成清单哈希 | 1（sidecar hash） |

最终 `14 条：杀掉 14 / 存活 0 / 注入本身无效 0`。
**M8 是这片唯一的新增知识点**：判据「两格不许互相顶」写在实现里（`row.get("material") or ""`），
但样本库里两格要么都有要么都没有，注入成 `material or process` 后测试全绿——
判据存在不等于判据被验过，缺的是那个「只缺一格」的样本。

## 六、端到端实测（`/tmp/slice18-e2e.sh`，全程 mktemp，不碰开发者的库）

真 CadQuery 模型两个（40×8×20 带 Ø6 孔 / 30×6×14 带 Ø5 孔）导出 STEP → 真 `bom.db`
两行（压板**故意只填材料不填工艺**）→ 真状态库里一条真 CTQ：

1. `aipd drawing assembly --explode`：明细表六列，`材料已填 2/2 行` / `工艺已填 1/2 行，缺的球标 [2]`。
2. `aipd drawing assembly-steps`：出 2 步、`球标覆盖 2/2`，压板那行 PROCESS 格**留空**
   （没拿材料顶，也没写占位符）；侧车 `manifest_sha256`/`document_sha256` 各自独立。
3. `aipd release manifest --steps-doc`：`assembly_instructions.sha256` 与文档实测哈希逐位相同，
   `assembly_steps = {step_count: 2, declared_balloons: 2, unreferenced: [], not_covered: [...]}`；
   就绪判定 rc=4 的原因是 `process_missing`（工艺那一格缺），不是步骤这一半。
4. 反证 A：把第 2 步删掉 ⇒ CLI rc=4 且明说「球标 2（压板）没有任何步骤装配它」，
   manifest 里 `steps_balloons_uncovered` blocking=True、`ok=False`、
   `unreferenced: [2]`、`step_count: 1`。文档**照样出**，但把缺的东西说清。
5. 反证 B：五种坏声明全 rc=2，且各归各的文案——引用不存在的号（`球标 7…没声明过`）、
   写了 `torque`（点名不承载字段与可声明清单）、断档（`缺 2、3`）、重号（`步骤号重复：1`）、
   整段没写（`没有 "assembly_steps" 那一段`）。

## 七、这一片没做的事

- **维护指引**：C6 该项的另一半，内容要属主给；文档与侧车的 `not_covered` 都列了它。
- 工时 / 工序成本 / 扭矩值：不建模，清单里写就拒绝（与第 16 片同一裁决）。
- 逐步骤的点检项接线：检验事实仍走 CTQ/图纸那条线，步骤里没有检查点。
- PDF/图框版式：reportlab 中文本机可用，缺的是排版与分页判据。
- 步骤顺序的自动求解：与爆炸位移同理，前提（装配约束、无碰撞路径）本仓没有。

## 八、收尾读数（落盘后复算，不是计划）

提交：`ee89476`（代码 + 文档）→ `7fae8d2`（发布工件重锚）。顺序按第 17 片同一口径：
`regenerate_release_manifest.py` → `release_evidence.py --source-commit a66040520139…`
→ 带 `AIPD_SOURCE_COMMIT` 的全量 pytest 出 JSON → 再跑 `release_evidence.py --test-report`。

| 量具 | 读数 |
|---|---|
| 全量 pytest（报告 `docs/audit/pytest-report-v5.6.0.json`） | **1801 passed / 0 failed / 3 skipped**（共 1804；上一片收尾 1772/0/3） |
| `PROVENANCE.json` | `test_report.{passed:1801, failed:0, total:1804, source_commit:a66040520139…}`，与 v5.6.0 标签指向一致 |
| `SOURCE_MANIFEST.json` | 被哈希面 **597 → 599**（新增的两个正是 `assembly_steps.py` 与 `test_cad_assembly_steps.py`；由脚本读两份 manifest 求差算出，**不是**记忆里的 596——工件提交信息里那句 596 是错数，以本行为准） |
| `production_release_gate --release-ready --tag v5.6.0` | rc=0，`release_ready: true`，8 项检查全过、未通过列表为空 |
| `skill_quality_audit.py` | rc=0，0 警告 0 失败（新增的 public 命令已逐条进 `SKILL.md`，总数 48→49 同步） |
| `state_perf_gate.py` | PASS |
| `audit_repo.py --strict` | rc=1，唯一 ✗ 是 `Provenance source commit mismatch: manifest=a66040520139… vs HEAD=7fae8d22e5b8…`——**按设计为红**：真发版前 HEAD 必然走在标签之后 |
| `scripts/c6_coverage.py` | rc=0、`problems: []`、`--self-test` 7/7 开火；档位 **12 producer / 2 checker_only / 1 absent**（缺席只剩 ICD），`装配/维护` 已升到 producer |
| 变异电池 `/tmp/slice18-mutations.py` | 14 条：杀掉 14 / 存活 0 / 注入本身无效 0（M8 首轮存活→补样本后开火，见 §五） |
| 端到端 `/tmp/slice18-e2e.sh` | 脚本 rc=0（其中「故意坏声明」那五条各自 rc=2、未收口那次 rc=4，都在预期内）；产物落在 `mktemp -d` 目录，收尾后已删。两份一次性脚本里只有 `/tmp/slice18-mutations.py`（变异电池）还在本机 `/tmp`；端到端脚本 `/tmp/slice18-e2e.sh` 被清理通配符一并删掉了——§六 已把五条命令逐条写明，按那里重建即可（两份都不入库，随系统清理自然消失） |

本片**没有**动的东西（都是刻意的，不是漏的）：`assembly/assembly.py` 的投影路径、
共享门禁的判据与白名单、tag/bundle/签名、任何开发者数据库。`_bom_lines_or_none` 的抽取
把装配图那条 BOM 读法逐字搬过去（文案不变），由既有用例 `tests/test_cli.py`、
`tests/test_cad_assembly_bom_link.py` 与新增 `TestCliSurface` 共同守住。
