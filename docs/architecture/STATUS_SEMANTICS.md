# 状态语义：NPI definition_status vs AIPD epistemic_status vs lifecycle_status（v5.8.1 Commit 15）

> **核心结论：三个维度正交，禁止简单替换（例如 ``RECOMMENDED = A`` 是错的）。**
> 任何把 NPI 状态映射为 AIPD 状态的代码/文档，必须同时声明三个维度，
> 不能把「需求被推荐」与「认知状态为假设」混为一谈。

---

## 1. 三个维度

### 1.1 NPI definition_status（产品定义成熟度）

| 值 | 含义 |
|---|---|
| CONFIRMED | 已被权威来源确认（实测/规范/已验证） |
| DERIVED | 从确认项推导而来（不是直接观测） |
| RECOMMENDED | 被建议/推荐，尚未确认 |
| ESTIMATED | 估算值（数量/范围） |
| TBD | 待定（尚未赋值） |
| CONFLICT | 来源冲突 |
| OBSOLETE | 已废弃/被取代 |

### 1.2 AIPD epistemic_status（认知/证据状态，claim 级别）

| 值 | 含义 |
|---|---|
| V | Verified（已核实） |
| S | Supported（有支持证据） |
| C | Contradicted（有反驳证据） |
| E | Evaluated（已评估但结论未定） |
| A | Assumption（假设，未验证） |
| P | Pending（待验证） |
| T | Testable（可验证） |
| U | Unknown（未知） |
| R | Rejected（已拒绝） |

### 1.3 AIPD lifecycle_status（对象生命周期，idea/claim/relation 级别）

| 值 | 含义 |
|---|---|
| raw | 原始输入（未结构化） |
| active | 活跃（在系统中推进） |
| archived | 归档（保留但不推进） |
| superseded | 被新版本取代 |

---

## 2. 正交性规则

1. **definition_status 描述「产品定义/需求的确定性」**，不描述「证据真值」：
   - ``Requirement definition_status=RECOMMENDED`` 只说「这条需求是推荐项」，没说它有没有证据。
2. **epistemic_status 描述「对 claim 的认知真值」**，由 ClaimAssessment 从 relation 证据计算。
3. **lifecycle_status 描述「对象是否还在被系统推进」**，与真值/确定性无关。

**禁止映射表（反例）**：
- ~~RECOMMENDED = A~~（推荐 ≠ 假设；推荐可以是 V/S 支撑的）
- ~~CONFIRMED = V~~（需求被确认 ≠ claim 被验证；确认是产品定义层，验证是认知层）
- ~~TBD = U~~（待定是「还没定」，未知是「评估过但不知道」，不同义）

---

## 3. 正确示例

一条需求同时携带三个维度：

```json
{
  "requirement_id": "REQ-001",
  "text": "居家康复系统必须支持单目摄像头姿态估计",
  "definition_status": "RECOMMENDED",
  "epistemic_status": "C",
  "lifecycle_status": "active"
}
```

含义：该需求是**推荐项**（产品定义层）；其背后的 claim **有反驳证据**（认知层，来自
golden-paper-2 的 contradicts relation）；对象**正在被系统推进**（生命周期层）。

另一个示例——已废弃的需求：

```json
{
  "requirement_id": "REQ-002",
  "text": "必须支持深度相机",
  "definition_status": "OBSOLETE",
  "epistemic_status": "U",
  "lifecycle_status": "superseded"
}
```

---

## 4. 工程含义

- 任何 NPI 导入/导出代码必须保留三维度字段，不得折叠成单字段。
- MMD 映射（见 `docs/architecture/MMD_AIPD_CROSSWALK.md`）中，
  NPI ``definition_status`` 映射到未来 ``Requirement.definition_status`` 列
  （**需要 schema extension**），而不是覆写 AIPD ``epistemic_status``。
- 提示词/报告/UI 展示时必须区分：「这是推荐项」「这条有证据」「这个对象在推进中」。
