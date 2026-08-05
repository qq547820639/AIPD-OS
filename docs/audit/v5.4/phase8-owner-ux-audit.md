# 阶段8 审计：产品所有者用户体验层

- 审计目标：AIPD-OS 所有者体验层（阶段8）
- 审计范围：`src/aipd_os/experience/`（views / project_summary / decision_card / resume_summary / artifact_preview / risk_health / external_wait / instructions）+ `src/aipd_os/cli/commands.py`（status / decide / resume / intake 等）
- 运行环境：`.venv/bin/python`，cwd=`AIPD-OS`
- 判定等级：`fully_implemented` / `partially_implemented` / `not_implemented` / `not_verifiable`
- 核心规则：**默认视图必须完全隐藏内部术语，仅展示项目摘要 + 单一决策卡；自然语言批准必须自动传播到全部下游工件。**

---

## 测试结果

| 测试集合 | 命令 | 结果 |
|---|---|---|
| 体验层 + 风险健康 + 外部等待 | `pytest tests/test_experience.py tests/test_risk_health.py tests/test_external_wait.py -q` | **23 passed**（0.27s） |

补充的针对性质证（非断言式，见下）：
- `parse_instruction` 对 `选A / 选择B / 保留模块化 / 暂不进入实体制造` 均返回 `kind=unknown`（实测确认）。
- `apply_instruction(parse_instruction("批准"))` 只 resolve 决策，`stale_deliverables=[]`、未新增任何 fact（实测确认）。
- `OwnerView(..).to_markdown(..)` 渲染出的默认正文（`<details>` 之外）实测含 `D-001`、`manual`、`cad`、`medium/high/none` 等内部代号。

---

## 验证点1：默认视图隐藏内部术语 + 单一决策卡

判定：**partially_implemented** — 单一决策卡真实实现，但默认 Markdown 存在多处内部代号漏出，未满足"完全隐藏"。

表格中"证据"均为实测渲染出的默认正文（`<details>` 之外）内容。

| # | 子能力 | 状态 | 证据（文件:函数/行） | 测试 | 局限 |
|---|---|---|---|---|---|
| 1.1 | 项目摘要字段全部为中文自然语言 | **partially_implemented** | `project_summary.py:build_project_summary` L98-135；字段 current_work/completed/gaps/top_risk/next_milestone | `test_experience.py::test_project_summary_is_natural_language` L74-85 | **internal 代号漏出**：deliverable type 原样拼进正文——`_current_work` L43 `"正在推进：{names}"`、`_completed` L53 `"已完成交付：cad"`、`_gaps` L70 `"有 N 项产物已过期需重做：manual"`。`manual/cad/bom` 这类类型代号未转中文 |
| 1.2 | gate 代号（G0–G9）隐藏 | **fully_implemented** | `_milestone` L32-33 用 `GATE_NAMES`（L15-26）把 gate 转成"项目启动与概念验证"等中文；gate 原始值只在 `details` 内 | 实测渲染正文无 G0-G9 | 仅项目摘要处转换；`resume_summary.current_phase` 仍是原始 gate 代号 G0，但未渲染进 Markdown 正文（只进 JSON details） |
| 1.3 | 单一决策卡（AI 建议/理由/2-4 选项/成本/性能/时间/安全/批准后自动执行） | **fully_implemented** | `decision_card.py:build_decision_card` L71-116 每次只取最高优先级（最早提出的 open_decision）；`render_markdown` L92-104 渲染单卡；`_per_option_impacts` L54-60 给每选项成本/性能/时间/安全 | `test_experience.py::test_decision_card_single_highest_priority` L88-99 | 无待审决策时返回 None（L76-77），正文显示"当前没有待您决策的事项" |
| 1.4 | 决策卡不暴露 decision_id | **not_implemented** | `views.py:render_markdown` L96 `f"**{card['topic']}**（{card['decision_id']}）"`；`cli/commands.py:cmd_project_summary` L214、`cmd_status` L651 同样拼出 `（{card['decision_id']}）` | 实测正文含 `D-001` | **decision_id（如 D-001）直接漏进默认正文**，属内部代号 |
| 1.5 | 影响档位本地化为中文 | **not_implemented** | `views.py:render_markdown` L102-103 直接把 `imp.get('cost')` 等原样拼出 | 实测正文含 `成本:medium / 性能:high / 时间:medium / 安全:none` | **英文档位 medium/high/low/none 未中文化**，直接漏进默认正文 |
| 1.6 | 恢复摘要"上次进行到哪"为人类可读 | **not_implemented** | `resume_summary.py` L43 `str(rs["last_off"])`；checkpoint `last_off` 是 dict（`checkpoint.py` L40），str() 得到 Python 字典 repr | 实测正文：`{'at': '2026-08-05T...', 'note': 'no summary recorded'}` | **Python dict repr 直接漏出**，且含英文 "no summary recorded" |
| 1.7 | "下一步"为中文自然语言 | **not_implemented** | `views.py:render_markdown` L115 渲染 `rs["next_action"]`；`checkpoint.py:resume_summary` L73-76 生成 `"resolve proposed decisions: ..."` / `"continue phase {gate}"` | 实测正文：`resolve proposed decisions: 外壳材质, 量产合作` | **英文 next_action + 多决策并列**漏进正文 |
| 1.8 | 风险健康 + 外部等待展示 | **fully_implemented** | `views.py:_health_section` L37-42、`_wait_section` L45-57；`risk_health.py`、`external_wait.py` | `test_risk_health.py` 全 8 例、`test_external_wait.py` 全 6 例、`test_experience.py::test_owner_view_composition` | 外部等待分桶为供应商/实验室/其他，不暴露 source/target 代号（`external_wait.py` L24 断言无 `:`） |

**验证点1小结**：单一决策卡、风险健康、外部等待、gate 代号隐藏为真实实现；但**校验点要求的"完全隐藏"未达标**——D-001 决策号、manual/cad/bom 类型代号、英文 medium/high 档位、Python dict repr、英文 next_action 共 5 类内部表述泄漏进默认正文。另有 `_gaps` 的 `"有 N 项产物已过期需重做"`（`project_summary.py` L70）中 `N` 是**未替换的字面占位符**（应为 `len(stale)`），属明显 bug。

---

## 验证点2：自然语言审批解析与传播

判定：**partially_implemented** — 核心解析（批准/成本削减/风格约束）真实可用，但选项选择、多个自然语言指令未解析，且**批准不传播到任何下游工件，也未接入 CLI**。

### 2.1 解析（`experience/instructions.py`）

| 输入表述 | 结果 | 证据 | 测试 |
|---|---|---|---|
| 批准 / 同意 / approve / 确认执行 | `approve` ✅ | `_APPROVE_RE` L23、`parse_instruction` L57-65；目标=首个 open decision | `test_experience.py::test_parse_instruction_kinds` L134-135 |
| 成本/价钱/价格降低 X% | `cost_reduction`（percentage）✅ | `_COST_RE` L24、L68-77 | `test_experience.py` L136-138 |
| 外观更工业化 | `style_constraint`（style=industrial）✅ | `_INDUSTRIAL_RE` L25、L80-87 | `test_experience.py` L139-141 |
| 不要医疗风 / 医疗器械风 | `style_constraint`（avoid=medical）✅ | `_MEDICAL_RE` L26、L90-97（"不要医疗"命中"不要医疗器械风"） | `test_experience.py` L142-144 |
| **选A / 选择B** | **`unknown` ❌** | 无任何选项下标/"选X"正则；实测 `parse_instruction("选A")` → `unknown {'raw':'选A'}` | 无 |
| **保留模块化** | **`unknown` ❌** | 无对应规则；实测 unknown | 无 |
| **暂不进入实体制造** | **`unknown` ❌** | 无对应规则；实测 unknown | 无 |

### 2.2 传播（`apply_instruction`，目标：Product Truth=事实/手工/CAD/BOM/供应链/验证计划）

| 指令 | 传播结果 | 证据 | 局限 |
|---|---|---|---|
| approve（批准） | **仅 `db.resolve_decision`**，不写任何 fact、不标记任何 deliverable 过期、不创建供应链/验证任务 | `apply_instruction` L148-161；实测 approve 后 `stale_deliverables=[]`、`facts=[]` | **决策卡 after_approval 文案**（`decision_card.py` L68 "批准后…同步更新相关产物与检查点"）**承诺的自动传播并未在 approve 路径实现**。决策虽 resolve，但 Product Truth/manual/CAD/BOM/供应链/验证计划均未更新 |
| cost_reduction（成本降低20%） | 写 Product Truth fact `cost_target`（L165-169）+ `_mark_stale` 标记**所有**未发布 deliverable（manual/cad/bom）过期（L170-171） | `test_experience.py::test_apply_cost_reduction_marks_deliverables_stale` L147-158 | 只标记过期，**不创建供应商重新报价任务、不更新验证计划**；且无差别标记全部交付物 |
| style_constraint（风格） | 写 Product Truth fact `design_intent`（L180-184）+ 标记 manual/page 类过期（L185-189） | 无针对性单测 | 不传播到 CAD/BOM/供应链/验证计划 |

### 2.3 CLI 暴露

**`parse_instruction` / `apply_instruction` 未接入任何 CLI 命令**（`cli/` 全仓 grep 无引用）。所有者的自然语言审批只能通过 Python API 调用；CLI 仅提供 `decide`/`submit-decision`（需显式 `--decision-id --choice`，`commands.py` L222-234/L658-674），无法发送"成本降低20%"这类指令。**自然语言审批链路在产品所有者可见入口处断裂。**

**验证点2小结**：批准/成本削减/风格约束三类解析与部分传播真实存在；但"选A"、保留模块化、暂不进入实体制造未解析；批准不传播到 Product Truth/手工/CAD/BOM/供应链/验证计划；且整条自然语言审批未接入 CLI。

---

## 验证点3：UX 指标评估

| 指标 | 状态 | 证据 | 说明 |
|---|---|---|---|
| 一句话开始 | **fully_implemented** | `cli/commands.py:cmd_intake` L556-579：单句 `--prompt` 即可建项 | 确定性建项，无需多步表单 |
| 一句话恢复 | **partially_implemented** | `cmd_resume` L583-620：`where_left_off` 单行，但输出多行摘要 | 无真正"一句话"恢复；`where_left_off` 含 dict repr（见 1.6） |
| 首次成果时间（time-to-first-outcome） | **not_implemented** | 无计时/耗时指标；`cmd_run` L444-502 运行到首个决策即停 | 无可量化指标 |
| 配置步骤数 | 低（**满足**） | `cmd_intake` 仅需 `--prompt` | 无表单化配置 |
| 不必要提问数 | **部分满足** | 决策卡单张（1.3）；`resume_summary` 过滤已解决决策（`resume_summary.py` L19-26） | 但"下一步"会并列列出多个待决策（checkpoint L73-74），未去重聚焦 |
| 决策数（number of decisions） | **fully_implemented** | `db.list_resolved_decisions/list_open_decisions`（`db.py` L546-556）；summary.details.counts（`project_summary.py` L127-133） | 有计数，无跨会话趋势 |
| 手工返工率（manual rework rate） | **not_implemented** | 无指标；仅 `cmd_run` 统计本轮 `internal_rework` 次数（`commands.py` L475/L499） | 无累计率/历史 |
| CAD 迭代次数 | **not_implemented** | 无计数指标；`artifact_preview` 只列 versions 列表 | 无迭代次数统计 |
| 错误恢复率（error recovery rate） | **not_implemented** | 仅 `risk_health` 有 blocker 状态（`risk_health.py` L14/L30-42），无恢复率指标 | 无量化 |
| 移动端可读性 | **not_implemented** | 输出为 Markdown/CLI 纯文本，无响应式/移动端渲染层 | `layout/` 面向产品手册排版，不服务所有者视图 |
| 页面 & CAD 版本差异预览 | **not_implemented（数据已算、未展示）** | `artifact_preview.py:artifact_preview` L44-100 计算 manual_pages/cad_versions/bom_diffs/parameter_diffs，进入 `OwnerView.owner_update`（`views.py` L145），但 **`render_markdown` 从不渲染 artifact_preview** | **算而未展示**：版本差异数据在 JSON details 里，产品所有者默认视图看不到页面/CAD 版本 diff |
| 外部等待展示 | **fully_implemented** | `external_wait.py`、`views.py:_wait_section` L45-57、风险健康黄灯（`risk_health.py` L38-40） | 分桶+计数+中文摘要 |

---

## 真实用户体验缺口（按严重度排序）

1. **批准后不传播到下游工件**（验证点2）：决策卡声明"批准后系统将自动…同步更新相关产物与检查点"，但 `apply_instruction` 的 approve 分支只 `resolve_decision`，Product Truth(事实)/手工/CAD/BOM/供应链任务/验证计划**均不变**。承诺与实现不符（`decision_card.py` L68 vs `instructions.py` L148-161）。
2. **自然语言审批未接入 CLI**（验证点2）：解析器仅 Python API，`decide`/`submit-decision` 需传 `--decision-id --choice`，产品所有者无法用自然语言审批。
3. **默认视图泄漏 5 类内部代号**（验证点1）：D-001 决策号、manual/cad/bom 类型代号、英文 medium/high 档位、Python dict repr、英文 `resolve proposed decisions`。
4. **页面 & CAD 版本差异预览算而未展示**（验证点3）：`artifact_preview` 数据在 owner_update 里，但 Markdown 正文从不渲染，版本 diff 对所有者不可见。
5. **`_gaps` 字面占位符 "N"**（验证点1.1）：`project_summary.py` L70 `"有 N 项产物已过期需重做"` 未替换为实际数量。
6. **"选A/保留模块化/暂不进入实体制造"未解析**（验证点2）：选项选择与更多自然语言指令回落到 `unknown`。
7. **影响档位未本地化**（验证点1.5）：成本/性能/时间/安全档位 medium/high/low/none 原样拼进正文。

---

## 结论

- **真实实现（genuine）**：单一决策卡（最高优先级、2-4 选项、四维影响、批准后文案）；风险健康红黄绿灯；外部等待分桶展示；gate 代号 G0-G9 中文映射；批准/成本削减/风格约束三类解析；成本削减传播到 Product Truth + 标记交付物过期；一句话建项（intake）；决策计数；恢复摘要过滤已解决决策。
- **缺失（missing）**：批准→下游工件传播；自然语言审批 CLI 入口；页面 & CAD 版本差异预览渲染；移动端可读层；manual rework / CAD 迭代 / 错误恢复率指标。
- **部分（partial）**：默认视图隐藏术语（5 类代号泄漏）；"选A/保留模块化/暂不进入实体制造"解析；一句话恢复（含 dict repr）；"下一步"英文化。
- **测试结果**：`23 passed`（test_experience / test_risk_health / test_external_wait）。现有测试只验证"字段存在/中文非空/决策单张"，**未覆盖代号泄漏、审批传播、CLI 暴露**，故测试绿不代表上述缺口闭合。