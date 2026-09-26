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

**可达性现状（2026-09-25，F-TRUTH-PROP-01）**：传播这一半已从产品面走得到——
`aipd truth propagate --db <state.db> --project <p> --upstream <id>` 调
`on_upstream_changed`（标 stale + 生成 `rework_tasks` 有界任务 + 产出 owner 可读四段
变更说明），`aipd truth tasks` 只读列待办。**返工的执行也已接上（2026-09-26，F-REWORK 第 45 片）**：
`aipd truth rework --task RW-xxx | --all-pending` 调 `run_rework` 并交真实执行器
（`src/aipd_os/cad/spec_rework.py`）——按当前 active CTQ 重算图纸声明：哈希一致**且**磁盘产物
仍匹配就一个字节都不动产物（`unchanged`，但库里的版本与 stale 真的收口）；内容变了、或文件被删/
被手改，就重写并补血缘边（`rewrote` / `file_restored`）；重算出 gap 一律判失败，交给引擎的
有界退避与 `max_attempts`。执行器认 `metadata.artifact` 为 `drawing_spec`（重算声明）与 `drawing_dxf`（第 47 片：按记录的输入集合重跑出图，先出到暂存目录，只有 `drawing generate` 退码 0 才替换正式图纸——判未收口的重跑既不覆盖现状也不记成功）；不认识的制品在
**烧 attempts 之前**逐条点名拒掉——「这格没有执行器」不许被伪装成「返工失败了三次」。
接线前那句「产品侧无人调用」现在反过来钉（`tests/test_truth_propagate_cli.py::`
`TestReworkHalfIsWiredAndItsBoundaryStaysVisible` 要求产品侧真有调用点），
边界本身由 `tests/test_truth_rework_cli.py` 逐条钉住。
另一处现状（2026-09-26 更新，F-LINEAGE-DXF 第 46 片）：血缘边有**三个**生产者——
`product_intelligence/gate.commit_snapshot`（PI 需求 / Feature → truth 记录）、
`aipd drawing spec`（`src/aipd_os/cad/spec_lineage.py`：按声明正文**实际引用到**的
`ctq_ref` 写一条 `artifact_version` 记录，并给每条参与 CTQ 连一条 `affects` 边；
有 gap 时文件与血缘都不写），以及 `aipd drawing generate --db`
（`src/aipd_os/cad/dxf_lineage.py`：按**输入签名**——模型摘要 + 声明内容哈希 + 全部出图参数（part/revision/views/scale/sheet/material/剖切/放大）——写图纸的 `artifact_version`，并连「声明记录 → 图纸记录」的边）。
于是链条的**第二跳 CTQ → 图纸声明**与**第三跳 图纸声明 → DXF 制品**今天都传播得到：
改一条 CTQ 再跑 `aipd truth propagate`，那份声明**和按它画出来的那张图**一起被标 stale
并各自生成返工任务。身份取输入签名而不取 DXF 字节是实测决定的：同输入连跑两次，两份 `.dxf` 的 13170 行里
只有 2 行不同，差的是 `$TDCREATE` / `$TDUPDATE` 那一对儒略日时间戳——按字节哈希会把
时间戳读成一次工程变更；DXF 自己的 sha256 仍作为**观测**留在 metadata 里。同一产物路径
只留一版有效，新版落下时把旧版标 `superseded`，否则一张图改十次就有十条永久的下游。
BOM / 成本那一支的血缘生产者已在第 48 片接上（`aipd cost calc --truth-lineage` → `src/aipd_os/bom/cost_lineage.py`：按「BOM 身份 + 参与行集合」写 `artifact=bom` 版本记录，按「BOM 签名 + 口径五项（tooling_fee/target_quantity/amortize_over/nre/margin_pct）」写 `artifact=bom_cost` 成本结论记录，连 `bom → cost` 的 `affects` 边；同作用域只留一版有效、旧版标 `superseded`；BOM 为空什么都不写），于是改一行 BOM 再跑 `aipd truth propagate` 就能把那笔成本结论标 stale；**这两条新记录仍没有返工执行器**（它们的任务仍走「不认识的制品在烧 attempts 之前逐条点名拒掉」那条路）。图纸这一跳在第 47 片两头都接上了：`aipd truth rework` 会按记录里的输入集合重跑出图，并且**不新增版本记录**——引擎 bump 的是这一条；「换输入另起一版 + 旧版标 superseded」只是生产面（`aipd drawing generate`）的规则。
生产者集合由
`tests/test_drawing_spec_lineage.py::TestProducerRatchet` 按 AST 两向钉住——
多一个未登记的 `add_edge` 调用点要红，把本轮这个删掉也要红。

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

Maturity 确定性判定（`idea/maturity.py`，v5.8.2 Commit 6）：I0=raw 无 claims；
I1=claims 已创建但未满足 I2；I2=**required key claim types 全覆盖**
（`IdeaMaturityPolicy`：problem/user/mechanism/technology 全部存在且
已检索/评审，ClaimAssessment 非 NOT_SEARCHED，无 fake evidence）；
I3 只定义 contract。只有部分 key claims 被调查 → I1 + Evidence Gap。

## 2.2 CAD artifact identity contract（v5.8.2 Commit 9）

两个 hash 语义严格区分，**禁止混用**：

| hash | 用途 | 性质 |
|---|---|---|
| `artifact_byte_hash`（sha256） | 文件完整性 / tamper detection | 同一磁盘工件 → 字节稳定；任何字节改动 → 变化 |
| `semantic_geometry_hash` | 几何身份 | 同参数 → 稳定；改参数 → 变化；**与序列化字节无关** |

- 测试契约（`tests/test_cad_contract_unify.py`）：同参数两次导出 →
  semantic hash 相同；改参数 → semantic hash 变化；保存后
  `artifact_byte_hash` verify 通过；篡改 → FAIL；契约后端（无真实几何测量）
  不伪造 semantic hash。
- **byte_reproducibility_profile**：除非固定 CadQuery / OpenCASCADE / Python
  writer 环境（版本 + 平台 + 依赖集），**不承诺**两次独立 STEP 序列化字节
  一致（STEP 序/元数据可能因环境不同而变化）。需要字节级复现时，必须显式
  声明环境 profile（cadquery 版本、OCP 构建、Python 版本、平台），
  `artifact_byte_hash` 只保证「同一工件」的完整性，不保证「跨环境重生成」。

## 3. 作用域

所有 truth 记录与血缘/返工任务都带 `tenant_id` / `project_id`
（`product_truth/store.py`），查询一律按 scope 过滤；`find_id_by_type_and_content`
也按 scope 去重，防止跨项目误合并。这是「canonical truth 归属哪个项目」的存储基础。
