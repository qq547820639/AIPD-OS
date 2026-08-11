# Truth Architecture：三种状态维度与 Truth 演进（P1-3）

> 目标：明确「一个事实/结论的认知状态」如何表达，避免把 *epistemic status*、
> *lifecycle status* 与 *confidence* 混为一谈；并说明 Idea Truth → Product Truth →
> Engineering Truth 的同构复用。

## 1. 三种维度，互不替代

| 维度 | 取值 | 定义位置 | 语义 |
|---|---|---|---|
| **epistemic_status** | `V` / `S` / `C` / `E` / `A` / `P` / `T` / `R` / `U` | `state/db.py` `FACT_STATUSES` | 事实的**认知分类**（verified / simulation / constraint / estimate / assumption / plan / target / requirement / unknown 等）。它不是「新旧」，而是「这是什么类型的主张」。`U`=Unknown / 未验证（无证据或未确认）。 |
| **lifecycle_status** | `active` / `stale` / `expired` / `blocked` / `superseded` | `product_truth/models.py` `TRUTH_STATUS` | 记录的**生命周期**（当前是否仍被信任、是否需要返工/过期）。 |
| **confidence** | `[0, 1]` | `state/db.py` `add_fact(confidence=...)` | 连续**置信度**，用于排序/加权，不能单独决定可信级别。 |

> 注意：`FACT_STATUSES` 的 `S` 本义是 Simulation（模拟/仿真值）；`research/expiry.py`
> 历史复用 `S` 标记 stale（过期）。二者语义不同，已在该模块注释中警示，未来应引入
> 独立状态位区分。

关键区别：

- **UNKNOWN 不是 stale**。`stale` 表示「曾有效、现在因上游变化而过时，需返工」；
  「从未验证 / 无证据」应保持 `unverified` / `not_verified` / `U` 的 epistemic 状态，
  而不是标记为 stale。`product_truth/propagation.py` 的失效传播只把「受影响」
  的下游标 stale，绝不把「本来就没证据」的记录伪装成 stale 或 verified。
- **external evidence 必须经过适用性判断**。外部来源（论文/报告/供应商数据）
  到达后默认是 `unverified`/`low`；research 回写层写事实时默认 `E`（可靠外部
  证据），**绝不自动 `V`**（retrieval verified ≠ 命题 verified）。`assess_trust`
  的确定性规则（`product_truth/store.py`）只判断 provenance / lifecycle / 来源
  可用性：evidence 记录 → `high`（来源可信度，非 verified）、有上游链 → `medium`、
  无上游 → `low`；仅当显式 Owner/工程确认标记（metadata `confirm_by_owner=True`）
  才返回 `verified`。

## 2. Idea Truth → Product Truth → Engineering Truth 同构复用

三个阶段共享同一记录模型（`TruthRecord`：record_type / content / source /
trust_level / effective_at / expires_at / version / status / metadata），
区别仅在 `record_type` 与来源约束：

| 阶段 | record_type 示例 | 来源约束 |
|---|---|---|
| Idea Truth | assumption / ctq | 需求/构想陈述，低可信起步 |
| Product Truth | fact / requirement / evidence / risk / decision | 须有 evidence 或上游依赖才可 verified |
| Engineering Truth | artifact_version / verification 结果 | 绑定 CAD/BOM/验证产物（artifact_version + evidence） |

同构复用意味着：一套 `ProductTruthStore` + `LineageGraph` + `PropagationEngine`
即可服务三个阶段；跨阶段传播（Idea 变更 → Product 受影响 → Engineering 返工）
沿同一条血缘图计算。诚实性约束：没有执行器时不返回假成功
（`run_rework(rework_fn=None)` → `blocked`，绝不 bump 版本）。

## 2.1 Idea Truth 是 projection，不是第二 Store（v5.8 Commit 14）

`src/aipd_os/idea/projections.py` 的 `IdeaTruthProjection` 是**查询组合**，
不创建新 DB/表：

- 输入：idea + claims + evidence relations（`claim_evidence_relations` 复用
  canonical evidence 表）+ lineage 概念；
- 输出 auditable projection：known（有 supports 证据）/ assumption（A）/
  evidence（有 relation）/ contradicted（contradicts）/ unknown（U）/
  gaps（无 relation 的 claim）/ maturity（I0/I1/I2）；
- `IdeaTruthSnapshot`：可选不可变快照（JSON 可序列化，仅快照语义；生成后
  修改源数据不影响 snapshot）。

Maturity 确定性判定（`idea/maturity.py`）：I0=raw 无 claims；I1=claims 已创建
（schema valid）；I2=有关联真实 evidence（relation 的 evidence_id 必须真实
存在于 canonical evidence 表，无 fake evidence）；I3 只定义 contract。

## 3. 作用域

所有 truth 记录与血缘/返工任务都带 `tenant_id` / `project_id`
（`product_truth/store.py`），查询一律按 scope 过滤；`find_id_by_type_and_content`
也按 scope 去重，防止跨项目误合并。这是「canonical truth 归属哪个项目」的存储基础。
