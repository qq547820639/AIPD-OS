# 阶段5 —— CAD 与生产图纸链审计 + 成熟度一致性门

- 审计日期：2026-08-06
- 审计性质：只读深度审计（允许新增/加强 CI 扫描测试）
- 结论：仓库在**成熟度一致性**上已一致（faceted 工具链上限为 C1），未发现需要修复的越级成熟度声明类真实冲突。发布门为**真实证据门**（非仅“字段非空”）。
- 但 C2 及以上能力大多未真正实现，多为门证据键 / 策略 / 占位工作包路由器。

---

## 1. CAD 能力实现状态

| 能力 | 状态 | 证据（文件/函数/行） | 测试 | 局限 |
|---|---|---|---|---|
| CAD 运行时发现（runtime discovery） | ✅ 已实现 | `src/aipd_os/execution/registry.py:discover_all()`; `execution_router.py:88,209,249`; `tool_adapters/builtin.py:build_registry()`; 各 adapter 的 `discover()` | `tests/test_adapters.py` | 只做能力发现/路由，不驱动真实建模 |
| text-to-cad 适配器 | ⚠️ 桩/模拟 | `tool_adapters/cad_adapter.py:execute()`（L39-56）仅返回 `cad_contract` 且 `status="simulated"`；未配置 `AIPD_CAD_PROVIDER` 时抛 `external_blocked`（L40-47） | `tests/test_adapters.py` | 未真实调用 CAD 引擎，仅生成契约/工作包，诚实标注 simulated |
| 本地原生 B-Rep 适配器 | ⚠️ 桩/工作包 | `tool_adapters/local_brep_adapter.py:execute()`（L37-48）仅返回 `brep_work_package`，不生成几何；maturity_ceiling=C2（L17） | `tests/test_adapters.py`（断言 ceiling=C2） | 未实现真实原生参数化建模 |
| Faceted 显式回退 | ✅ 已实现 | `tool_adapters/faceted_adapter.py:execute()/_write_step()`（L48-108）真实写出 `FACETED_BREP` STEP 文件；`scripts/faceted_step.py:FacetedStepWriter/parse_step` | `tests/test_adapters.py:test_faceted_writes_real_step_artifact`（断言 `FACETED_BREP(` 出现与结构解析） | 仅小平面数字样机；maturity_ceiling=C1；不可用于正式图纸/量产 |
| 参数化零件（parametric parts） | ❌ 未实现 | 仅门证据键 `native_parametric_brep/editable_feature_tree`；`local_brep_adapter` 为占位工作包 | 无 | 无真实特征树/参数化建模 |
| 装配约束（assembly constraints） | ❌ 未实现 | 仅 `cad_maturity_gate.py:REQUIREMENTS['C3']['assembly_constraints']` 等证据键 | 无 | 无约束求解/装配定义 |
| 标准件（standard parts） | ❌ 未实现 | 无代码；仅见于 `local-cad-fallback.md` 与 `cad-engineering-readiness.md` 策略 | 无 | 无标准件库/紧固件/轴承 |
| 连续运动验证（continuous kinematics） | ❌ 未实现 | 仅证据键 `continuous_rom_clearance`；`cad-production-pipeline.md` 策略 | 无 | 无运动学/ROM/干涉求解 |
| 人体分位族数据（anthropometric family） | ✅ 已实现（数据表） | `src/aipd_os/cad/anthropometry.py:ANTHROPOMETRY_TABLE`、`get_dimension/validate_dimension`（L13-87） | `tests/test_anthropometry.py`（7 用例） | 静态数据表，未接入 CAD 生成/工效检查管线 |
| CAE | ❌ 未实现 | 仅证据键 `cae_reports/load_cases`；`capability-floor-policy.md` 规定无求解器时生成任务包 | 无 | 无真实求解器/仿真 |
| 疲劳（fatigue） | ❌ 未实现 | 仅证据键 `fatigue_plan_or_evidence` | 无 | 无疲劳分析 |
| 失效分析（failure analysis） | ❌ 未实现 | 仅见于 `cad-engineering-readiness.md`/`cad-production-pipeline.md` 策略 | 无 | 无 FMEA/失效模式计算 |
| 公差链（tolerance stackup） | ❌ 未实现 | 策略提及；无代码 | 无 | 无公差堆栈计算 |
| DFM/DFA | ❌ 未实现 | 仅门证据键 `dfm_dfa`；`cad-production-pipeline.md` 策略 | 无 | 无工艺可行性分析 |
| GD&T | ❌ 未实现（仅门校验） | `production_release_gate.py:gdt_covers_ctq`（L227-237）校验 CTQ 覆盖 | `tests/test_production_release_gate.py:test_gdt_not_covering_ctq_fails` | 仅一致性校验，无 GD&T 生成/标注 |
| 2D 工程图纸 | ❌ 未实现 | 仅门证据键 `drawings`；无绘图生成器 | 无 | 无 DXF/图纸生成 |
| BOM/模型/图纸一致性 | ⚠️ 门校验已实现 | `production_release_gate.py:bom_matches_model`（L199-205）、版本一致性（L302-305）、数量一致性（L308-311） | `tests/test_production_release_gate.py:test_drawing_model_version_mismatch_fails` | 仅校验，无 BOM/图纸生成 |
| 检验计划（inspection plan） | ⚠️ 门校验已实现 | `production_release_gate.py:ctq_has_inspection`（L240-251） | `test_ctq_missing_inspection_fails` | 仅校验 CTQ 检验方法，无检验计划生成器 |
| 图纸修订（drawing revision） | ⚠️ 门校验已实现 | `production_release_gate.py:drawing_cad_same_revision`（L188-196） | `test_drawing_model_version_mismatch_fails` | 仅校验 `drawings_version == model_version` |
| CAD 变更回写手册 | ❌ 未实现 | 仅 `evals_runner/scoring.py:_cad_change_writes_back_manual`（L119-121）为 eval 文本匹配启发式 | 无 | 非真实回写链路，仅行为评测关键词 |

**结论**：真正实现的 CAD 能力为「运行时发现」「Faceted 显式回退（真实 STEP 生成）」「人体分位数据表」以及两套证据门（`cad_maturity_gate.py`、`production_release_gate.py`）。**C2 及以上能力（原生 B-Rep、装配、运动学、标准件、CAE、疲劳、失效、公差链、DFM/DFA、GD&T、图纸、检验、CAD回写手册）均未真正生成实现**，多为门证据键 / 策略文档 / 占位工作包路由器。

---

## 2. 成熟度一致性冲突扫描结果

全仓扫描（.py/.json/.md/.yaml/.yml/.txt/.html），排除 `.git/.venv/.pytest_cache/__pycache__/.trae/tests`：

- **未发现真实冲突**。产品代码中所有 faceted / 遗留 CAD-L 记号表述均已封顶 C1 或为否定/拦截语境：
  - `scripts/cad_maturity_gate.py:98` `faceted_brep_capped`；`RUNTIME_MAX['faceted_brep']='C1'`（L39）
  - `src/aipd_os/tool_adapters/faceted_adapter.py:31` `maturity_ceiling="C1"`
  - `references/cad-engineering-readiness.md:9` “Faceted BREP最多只能达到本级”
  - `references/cad-production-pipeline.md:10` “faceted_brep：最高C1”
  - `references/capability-floor-policy.md:7`、`references/local-cad-fallback.md:14`（“never above C1”）
  - `references/cad-plugin-matrix.json:37` `local-faceted-fallback` maturity_ceiling=“C1”
  - `docs/audit/capability_matrix.md:77` “成熟度最高 C1”
  - `evals/exo001_v13_cad_maturity_report.json`（runtime=faceted_brep，reached=C1，target_passed=false）
- **`.trae/specs/` 中的越级成熟度示例与遗留 CAD-L 层级记号均为对本次迁移/策略的描述**（如 `v5.4-.../spec.md:41` “任何 faceted 越级类冲突 SHALL 在 CI 中被扫描并失败”），非实时冲突声明，且被 CI 一致性测试排除（SKIP_DIRS 含 `.trae`）。

**修复动作**：无真实冲突需修复文档/代码。仅加强 CI 扫描测试（见 §4）。

---

## 3. 发布门是否为真实证据门

读取 `scripts/production_release_gate.py`，确认为**真实证据门**，远超“字段非空”：

| 要求 | 实现 | 位置 |
|---|---|---|
| 文件存在/可读 | `check_requirement` + `file_openable` evidence check | L109-121, L156-172 |
| SHA-256 匹配 | `file_hash` 与清单 `sha256` 比对 | L79-84, L115-118 |
| 图号/修订一致 | `drawing_cad_same_revision`（drawings_version==model_version） | L188-196 |
| BOM 与模型一致 | `bom_matches_model`（bom_line_count==model_part_count）+ 版本/数量一致性 | L199-205, L302-311 |
| 单位/基准完整 | `units_datum_tolerance_complete` | L207-224 |
| GD&T 覆盖 CTQ | `gdt_covers_ctq` | L227-237 |
| CTQ 有检验方法 | `ctq_has_inspection` | L240-251 |
| 审批真实 | `owner_approval_real`（approval_status in approved/released） | L259-263 |
| 证据属当前版本 | 版本一致性 + `evidence_not_expired`（时间戳时效） | L302-318, L266-272 |
| 工具支持声明成熟度 | `tool_capability_supports_level`（ceiling>=target）+ 运行时封顶 | L253-256, L296-299 |

测试覆盖：`tests/test_production_release_gate.py`（完整清单通过、文件缺失失败、证据过期失败、GD&T 不覆盖 CTQ 失败、CTQ 缺检验失败、版本不一致失败、C0 缺失 achieved=None）。

**局限**：
- `schema_valid` 检查（L174-185）仅对含 `schema` 字符串字段的 dict 做 `json.loads`，**未真正用 `assets/schemas/cad_contract.schema.json` 做 JSON-Schema 校验**。
- “证据属当前版本”仅靠版本一致性 + 时间戳时效，未对每条证据打版本标签逐一核对。
- 上述均为门校验增强点，不影响“真实证据门”结论。

---

## 4. CI 成熟度一致性扫描（加强）

`tests/maturity_consistency_test.py` 已扫描全仓并拒绝：
- 任何遗留 CAD-L 层级记号（正则 `CAD-L` 后接数字）。
- 该小平面（faceted）回退工具链的越级成熟度声明（过度声称）；
  检测目标层级为 C2 及以上，或与遗留 CAD-L 高层级记号关联。

CI 已含 `maturity-consistency` job（`.github/workflows/ci.yml:58-71`）运行 `pytest tests/maturity_consistency_test.py`。

**本次加强**（新增 2 个自验证用例 + 修正否定词表）：
1. `test_scan_flags_faceted_over_c1_conflicts`：断言扫描能识别 faceted 越级（如关联到高层级）类肯定性冲突句，防止正则失效而静默放过。
2. `test_scan_allows_faceted_at_or_below_c1`：断言不误伤 “Faceted BREP 最高只能达到 C1” 等 ≤C1 与否定/拦截语境。
3. `NEGATION_HINTS` 补增 `'不可'`、`'不可用于'`、`'不得用于'`：修复“Faceted BREP 不可用于 C2 及以上的正式图纸”这类合法否定句被误判为冲突的**假阳性**（由新自验证用例暴露）。`tests/maturity_consistency_test.py:33-37`。

---

## 5. 测试结果

```text
.venv/bin/python -m pytest tests/test_cad_maturity_gate.py tests/maturity_consistency_test.py tests/test_anthropometry.py -q
..............  14 passed in 0.50s
```

- `tests/test_cad_maturity_gate.py`：4 通过（native_brep 最高可到 C7；faceted 封顶 C1；非法 CAD-L 目标被拒）
- `tests/maturity_consistency_test.py`：4 通过（含本次新增 2 个自验证用例）
- `tests/test_anthropometry.py`：7 通过

**CI 一致性扫描现已能捕获冲突**：`maturity-consistency` job 的 `test_no_legacy_cad_l_vocabulary` + `test_no_faceted_overclaim` 扫描全仓，新增自验证用例保证一旦有人写入 faceted 越级（即把该工具链与高层级关联）类冲突，扫描正则必然命中并失败。

---

## 6. 关键缺口清单（供阶段10 只修复真实缺口）

| 优先级 | 缺口 | 证据 |
|---|---|---|
| P1 | 原生参数化 B-Rep（C2）未实现，`local_brep_adapter` 仅返回工作包 | `local_brep_adapter.py:execute` |
| P1 | text-to-cad 仅为 simulated/blocked 桩 | `cad_adapter.py:execute`（L53 `status="simulated"`） |
| P1 | 装配约束/运动学/标准件（C3）、CAE/疲劳/失效（C4）、DFM/GDT/公差链（C5）、图纸/检验（C6）、CAD回写手册 均无生成实现 | 门证据键 vs 无生产代码 |
| P2 | 发布门 `schema_valid` 未真正用 JSON-Schema 校验、证据未按版本逐一核对 | `production_release_gate.py:L174-185` |