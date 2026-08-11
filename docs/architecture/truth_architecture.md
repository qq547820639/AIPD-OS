# Truth Architecture：三种状态维度与 Truth 演进（P1-3）

> 目标：明确「一个事实/结论的认知状态」如何表达，避免把 *epistemic status*、
> *lifecycle status* 与 *confidence* 混为一谈；并说明 Idea Truth → Product Truth →
> Engineering Truth 的同构复用。

## 1. 三种维度，互不替代

| 维度 | 取值 | 定义位置 | 语义 |
|---|---|---|---|
| **epistemic_status** | `V` / `S` / `C` / `E` / `A` / `P` / `T` / `R` | `state/db.py` `FACT_STATUSES` | 事实的**认知分类**（verified / simulation / constraint / estimate / assumption / plan / target / requirement 等）。它不是「新旧」，而是「这是什么类型的主张」。 |
| **lifecycle_status** | `active` / `stale` / `expired` / `blocked` / `superseded` | `product_truth/models.py` `TRUTH_STATUS` | 记录的**生命周期**（当前是否仍被信任、是否需要返工/过期）。 |
| **confidence** | `[0, 1]` | `state/db.py` `add_fact(confidence=...)` | 连续**置信度**，用于排序/加权，不能单独决定可信级别。 |

关键区别：

- **UNKNOWN 不是 stale**。`stale` 表示「曾有效、现在因上游变化而过时，需返工」；
  「从未验证 / 无证据」应保持 `unverified` / `not_verified` 的 epistemic 状态，
  而不是标记为 stale。`product_truth/propagation.py` 的失效传播只把「受影响」
  的下游标 stale，绝不把「本来就没证据」的记录伪装成 stale 或 verified。
- **external evidence 必须经过适用性判断**。外部来源（论文/报告/供应商数据）
  到达后默认是 `unverified`/`low`；只有经过 `assess_trust` 的确定性规则
  （`product_truth/store.py`：evidence 类有内容即 verified；其余类型需有
  upstream evidence 链）才可升级为 `verified`。绝不因为「来源看起来权威」
  就自动 verified。

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

## 3. 作用域

所有 truth 记录与血缘/返工任务都带 `tenant_id` / `project_id`
（`product_truth/store.py`），查询一律按 scope 过滤；`find_id_by_type_and_content`
也按 scope 去重，防止跨项目误合并。这是「canonical truth 归属哪个项目」的存储基础。
