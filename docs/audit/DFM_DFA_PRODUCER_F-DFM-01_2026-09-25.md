# F-DFM-01 第 19 片：DFM/DFA 分析的生产者（2026-09-25）

对应 C6 的 **`DFM/DFA`** 一项（分母逐字取自 `references/production-cad-deliverables.md:3`），
同时给 C5 的需求项 `dfm_dfa`（`scripts/production_release_gate.py:38`）一个真落点。
本片把普查档位从 `checker_only` 升到 **`producer`**：15 项 = 13 producer / 1 checker_only / 1 absent。

排序来路：`docs/audit/C6_COVERAGE_CENSUS_F-C6-01_2026-09-25.md` §九 第 4 项
（「`DFM/DFA` 从 `checker_only` 升 `producer` 需要一个真分析生产者，暂缓」）。
第 1-3 项里 1、2 已在前两片落地，3（ICD / ECR-ECO）需要属主给事实来源，仍不能自行造。

---

## 一、要拍板的事与结论

此前状态：能力行 `cad.dfm_dfa` 的 `implementation_file` 只写着
`templates/cad_engineering_manifest.json; scripts/production_release_gate.py`——
门会判「声明了什么」，产品侧没有任何东西**量**过零件。普查把这判成 `checker_only` 是对的。

结论：**自己做一层「内核实测事实 → 带来源的阈值判定 → 报告 + 证据」**。
不引入第三方 DFM 库（理由见 §二），不发明阈值（每条规则必须有 `source`），
量不出来的记 `blind`（不折算成 pass，也不折算成 0）。

## 二、技术选型（本机真实检索，六维对比）

| 候选 | 功能匹配度 | License | 维护活跃度 | 安全风险 | 代码质量 | 适配成本 | 处置 |
|---|---|---|---|---|---|---|---|
| `ncc-uk/SmartDFM`（复材件设计检查器，Python） | 最贴：`step_features.py`/`step_utils.py` 从 .step 抽特征事实，`fact_base.py` + `rule_base.py`(37KB) 把事实与规则分层 | GitHub API 列出的 26 个根条目里**没有 LICENSE 文件** → 不可引入 | 1 star / 1 fork / 5 open issue，2025-08 后未动 | 依赖 CATIA 与 GNN 训练链路（README 自陈） | 研究代码：`temp_file.txt`、`unused_or_outdated/` | 高 | **不引入，借分层结构** |
| `ishaannsaini-sudo/DFMedusa`（"A DFM checker For CAD CAM Models"） | 描述最贴，但实现读不到 | 不可判 | 0 star，2026-03 新建 | 不可判 | 不可判 | 不可判 | **不采用**：README 取不到（API 报 path 不存在），读不到就不评价、不复用 |
| PCB 类（`easyeda/eext-jlc-order-dfm-checker`、`shishir-dey/OpenDFM`、`theking801/dfm-checker`） | 领域不符：查 Gerber/制板工艺，本仓零件是机械 B-rep | 混杂 | — | — | — | — | 排除 |
| 通用几何库（pythonocc-demos、trimesh 壁厚分析） | 只给原语，不给 DFM 判据；本仓已有 OCP 在位 | LGPL/MIT | 活跃 | 低 | 好 | 中 | **不需要新增依赖**：射线用 `IntCurvesFace_ShapeIntersector`（本仓 `drawings2d.py:240` 已在用） |

阈值来处（这部分决定实现长什么样，不是装饰）：

- `https://hlhrapid.com/knowledge/design-guide-cnc-machining/`（访问 2026-09-25）：
  金属最小壁厚 **0.8mm**、塑料 **1.5mm**、钻孔深径比 **≤4×**、内角半径 ≥ 腔深 1/3、
  腔深 ≤ 宽 4×、螺纹啮合 3× 公称、雕刻 0.8×0.5mm/字高 5mm。**页面无 License 声明。**
- `https://xometry.hk/en/industry-standards-in-cnc-machining/`（同日）：金属最小壁厚
  **0.794mm**（= 1/32 英寸）、塑料 **1.5mm**、通用公差 **0.125mm**、可达 **±0.025mm**、
  钻孔深度一般 **4×直径**、最大 **10×**。它引的是 ISO 230/229/369，**没有** ISO 2768 表。
- `https://www.3erp.com/blog/iso-2768-standard/`（同日）：给全 ISO 2768-1 线性 f/m/c/v 表
  （0.5–3mm 段 ±0.05/±0.1/±0.2/–；100–200 段 ±0.5/±0.5…）与角度表；页面是**转述**不是逐字，
  且它自述「1989 年引入、2003 大改」与 ISO 2768-1:1989 的编号口径不一致 —— 来源里注明转述。
- `https://www.fictiv.com/articles/dfm-design-for-manufacturing-guide`：抓到了正文，
  **一个数字都没有**（只有「壁厚保持一致」「用圆角」这类定性话，量化都指向付费电子书）。
  这就是为什么不能拿它当阈值来处。
- InvenTree 核心文档这次取的 URL 404（第 18 片记过），本轮**没有再读**，不引用。

两家厂商**各自独立**给出 0.8 / 0.794mm 与 1.5mm 与 4×，量级一致才敢用作分界；
`hold` 只给「超出厂商标称能力上限」的两条（深孔 >10×、公差严于 ±0.025），
其余给 `advisory`；`内圆角` 与 `同轴孔数` **不设阈值**（前者厂商给的是比值、
本仓没有可比的「腔深」定义；后者本来就不是合格与否的事），`limit = None` 只报事实。

## 三、实现落位

- `src/aipd_os/cad/dfm.py`（新增）：`geometry_facts`（圆柱面半径/深度/**角向张角**、
  包络、体积、同轴分组）、`measure_min_wall_thickness`（三轴网格射线 + 进→出配对，
  带 `spacing_mm`/`rays_with_hits`/`odd_hit_rays`/`caveat`）、`material_is_plastic`
  （三态：塑料/金属/**认不出来**）、`RULES`（每条带 `source`）、`analyze`
  （findings / blind / counts / not_covered）、`generate_dfm_report`（Markdown + 侧车）。
  整孔判据用**拓扑**：圆柱面 u 参数张角 ÷ 2π ≥ 0.999 才算孔。本机实测 Ø6×10 通孔
  张角 1.0000、R2 圆角 0.2500 —— 拿名字或「半径小」判孔会把圆角当成孔。
  同轴分组用**轴线位置**（`cyl.Axis().Location()`）而不是曲面上的点：一开始拿错点，
  Ø6 与 Ø3 的两个同轴孔被判成两根轴（用例 `test_coaxial_holes_group_by_axis_not_by_name`
  当场抓到）。轴向 ±Z 由建模顺序决定，所以按无向直线归一（`_oriented`）。
- `src/aipd_os/cli/commands_drawing.py`：`cmd_drawing_dfm`（hold ⇒ 退出码 4；
  读不出实体就 rc=2 不交空分析）。`commands.py`/`main.py`/`command_contract.py`/`SKILL.md`
  同步接线（public 命令 49→50，`--step/--out/--part` 为必填）。
- `src/aipd_os/release_manifest.py`：`_collect_dfm()` —— 没交就**不写 `dfm_dfa` 那一格**；
  交了则 `dfm_dfa = {path, sha256}` + `dfm_summary`（hold/advisory/blind/measured、
  材料分类、not_covered、侧车哈希）；三类阻断 `dfm_missing`/`dfm_evidence_missing`，
  `dfm_hold_findings` 阻断，`dfm_advisory_findings` 与 `dfm_unmeasured` **只提示**
  （告警≠阻断，与第 17 片那条纪律一致）。
- 能力行 `cad.dfm_dfa` 从「模板 + 门禁脚本」改写成真生产者行（行数仍 82，未新增行）。
- `scripts/c6_coverage.py` 的 `DFM/DFA` 条目升 producer；`tests/test_c6_coverage.py`
  棘轮同步成 13/1/1。

## 四、常驻用例

`tests/test_cad_dfm.py` 35 条，六组（每组条数由 `pytest --collect-only` 现算）：几何事实（9）、
规则来源（6）、判定与盲区（9）、材料分类（2）、CLI 面（3）、release manifest 看得见（6，含全盲区那一条）。

其中三条是为「判据有牙」专门补的：
- `test_a_shell_without_thickness_blinds_the_wall_rule_instead_of_reporting_zero`：
  只有一个面的壳量不出壁厚 ⇒ `min_mm is None` 且壁厚规则记 `no_probeable_planar_face`；
- `test_a_rule_whose_basis_disagrees_with_its_source_is_refused`：
  挂厂商的数却自称标准（或反过来）当场拒 —— 这条不写，D9 的注入会全绿存活；
- `test_an_all_blind_analysis_is_visible_not_a_green_pass`：一条都没判成时
  `measured_rule_count = 0` 且给出非阻断提示，不把空分析读成「没有 DFM 问题」。

## 五、变异电池（`/tmp/slice19-mutations.py`，18 条全开火）

| # | 注入的坏判据 | 开火的用例 |
|---|---|---|
| D1 | 取消「满一周才算孔」的拓扑判据 | fillet_is_not_counted_as_a_hole 等 2 条 |
| D2 | 把满周阈值放宽到 0.2（走常量） | fillet_is_not_counted_as_a_hole |
| D3 | 分轴改用曲面上的点（而非轴线位置） | coaxial_holes_group_by_axis |
| D4 | 材料认不出来就按金属兜底 | unknown_material_blinds 等 2 条 |
| D5 | 壁厚量不出时折成 0.0 | shell_without_thickness_blinds |
| D6 | 只沿一个轴打射线 | drilled_block 孔壁 7mm 那条 |
| D7 | 盲区记录被丢掉（等于默认合格） | no_holes_blinds 等 2 条 |
| D8 | 规则可以不填来源 | rule_can_not_be_added_without_a_source |
| D9 | basis 与 source.kind 不一致也不拦 | basis_disagrees_with_source |
| D10 | 金属壁厚阈值被改成 1.5 | thresholds_are_the_pages_own_numbers 等 |
| D11 | 判定方向写反（< 阈值算违规） | metal_thin_wall_fires_advisory |
| D12 | hold 降级成告警 | cli_exit4 等 2 条 |
| D13 | 报告不再声明自己没看什么 | exposes_what_it_did_not_look_at |
| D14 | 没交分析也写 `dfm_dfa` 那一格 | no_analysis_writes_no_key |
| D15 | 侧车不在也照样读 | missing_sidecar_is_blocking |
| D16 | 告警升成阻断 | advisory_findings_do_not_block |
| D17 | 全盲区不提示 | all_blind_is_visible |
| D18 | hold 结论不再阻断就绪 | hold_findings_block_readiness |

最终 `18 条：杀掉 18 / 存活 0 / 注入无效 0`。过程中两次「注入本身无效」值得记：
D16/D18 的锚点最初是**凭记忆写的字符串**（漏了行首的 `+ `），脚本按「命中必须恰好 1 次」
判为注入无效而不是误报通过——这条守卫比锚点写对更重要。

## 六、端到端实测（`/tmp/slice19-e2e.sh`，全程 mktemp，不碰开发者的库）

真 CadQuery 模型 5 个 → 真 STEP → 真 `aipd` 可执行文件：

| 件 | 读数 |
|---|---|
| 20×20×10 + Ø6 通孔（6061-T6） | 最小壁厚 **7.0mm**（= 20/2−3，孔壁到外侧面，不是板厚 10）；深径比 1.67 pass；rc=0 |
| 12×12×0.5 薄板 | 壁厚 0.5 vs 0.8 ⇒ `[flag]`，advisory 不阻断，rc=0 |
| 20×20×25 + Ø2×24 盲孔 | 比值 12 ⇒ `[flag]`(>4) + `[hold]`(>10)，**rc=4**；壁厚量出 1.0mm = 25−24（孔底留肉），物理对 |
| 12×12×1 塑料件（ABS） | 走 1.5 那条线 ⇒ `[flag]`；金属那条进盲区 `material_is_the_other_class` |
| 同件标「碳纤维预浸料」 | **判了 0 条、盲区 7 条**，两条壁厚都是 `material_class_unknown`，不猜 |
| Ø6 孔 + `--spec` 公差 ±0.01 | `[hold] 声明公差超出常规可达 0.01 vs 0.025`，rc=4 |
| 同件公差 ±0.1 | `[pass]`，rc=0 |
| 同轴 Ø6(深5) + Ø3(深8) | 同轴组报 2 孔（Ø6、Ø3），`[info]` 不设阈值；壁厚 7.0mm |
| `release manifest --dfm-doc` | `dfm_dfa.sha256` 与文档实测哈希逐位相同；正常件 `hold_count 0 / measured 4 / blind 3`；深孔件 `dfm_hold_findings` blocking=True + `dfm_advisory_findings` blocking=False |
| 反证：删掉侧车 | `dfm_evidence_missing`（阻断）；没交分析 ⇒ **没有** `dfm_dfa` 这一格 |

## 七、这一片没做的事

- DFA 只到「同轴孔系数」这一件事实：装配力与紧固顺序、插入方向数（需要每件声明的
  explode 位移，装配清单里可选）仍不判；
- 模具侧抽芯与脱模方向、铸造圆角与收缩率（本仓没有注塑/铸造的工艺输入）；
- 热变形/振动的 CAE（那是 `cad.cae_*` 那几行，仍不可核验）；
- 工序工时与加工成本（不建 operations 表，第 16 片裁决）；
- 斜置薄壁的壁厚：网格射线沿三轴测，斜筋会测厚不测薄 —— 这条写在报告的 `caveat` 里
  而不是悄悄不提；要收紧得改成沿面法向射线（尚未做）。
- 阈值来处是两家厂商工艺能力页 + 一份转述的 ISO 表，**都不是标准正文**；
  要按标准判定得先拿到 ISO 2768-1 与厂商能力合同的正式文本（属主/采购侧的事）。

## 八、收尾读数

见提交后的 `docs/audit/pytest-report-v5.6.0.json`、`SOURCE_MANIFEST.json`、
`PROVENANCE.json`、`capability_matrix.json` 与 §九 的复算表（本片落款时填）。
