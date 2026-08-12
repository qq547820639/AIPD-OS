# MMD → AIPD Canonical Object 映射（v5.8.1 Commit 15）

> **MMD 是 Projection/Interchange，不是第二 Truth Store（§64）。**
> 本表逐项说明：MMD object 在 AIPD 中的 canonical 落点、现状、缺失字段、
> owner / source of truth / lineage / migration need。

---

## 1. 映射表

| MMD object | AIPD canonical | existing implementation | missing fields | owner | source of truth | lineage | migration need |
|---|---|---|---|---|---|---|---|
| `evidence` | State Evidence（`evidence` 表） | ✅ `db.add_evidence` / canonical dedupe（Commit 6） | provenance/doi/arxiv_id 已并入 metadata；无独立 MMD `evidence_id` 字段 | Research/State | `evidence` 表 | EvidenceRelation → Claim | 无需（MMD evidence → AIPD evidence 1:1 写入） |
| `requirements` | Requirement / Product Truth | ⚠️ 无独立 Requirement 表；claims 承载需求文本 | `definition_status` 列缺失（见 STATUS_SEMANTICS.md）；owner/acceptance_criteria | Product/State | claims + future Requirement 表 | Claim → Evidence | **需要 schema extension**（v5.9：requirement 表 + definition_status） |
| `bom_items` | Deliverable / 未来 BOM | ⚠️ `deliverables` 表存在（type/path/status） | 无 BOM 专用表；无 quantity/uom/material 字段 | Engineering | deliverables + future bom_items 表 | Deliverable → Project | 需要 schema extension（v5.9：bom_items） |
| `suppliers` | Supply Chain | ⚠️ `supplier_adapter` / MailRfqAdapter 存在 | 无 canonical supplier 表；无 contact/qualification | Procurement | supplier 适配器输出 | 暂无 | 需要 schema extension（v5.9：suppliers） |
| `validation_tests` | Validation | ⚠️ `ValidationDataAdapter`（EVT/DVT/PVT）存在 | 无 canonical validation 表；无 test_case/pass_criteria | Quality | validation 适配器输出 | 暂无 | 需要 schema extension（v5.9：validation_tests） |
| `risks` | Risk（`risks` 表） | ✅ `db.add_risk` / list_risks | 无 MMD risk_id 映射字段 | Risk owner | `risks` 表 | Risk → Project | 无需（1:1 写入） |
| `open_issues` | Open Issue | ⚠️ 无独立 issue 表；work items 可承载 | 无 issue 表；无 severity/assignee | Program | supervisor_work_items + future issues 表 | WorkItem → Project | 需要 schema extension（v5.9：issues） |
| `decisions` | canonical Decision（`decisions` 表） | ✅ `db.propose_decision` / resolve（canonical 决策） | 无 MMD decision_id 映射 | Owner | `decisions` 表 | Decision → Project | 无需（1:1 写入） |
| `changes` | Change（`changes` 表） | ✅ `db.add_change`（object_type/object_id/action） | 无 MMD change_id 映射 | Engineering | `changes` 表 | Change → Object | 无需（1:1 写入） |
| `gate_reviews` | Gate Review（`gates` 表） | ✅ `db.add_gate`（gate/result/checks） | 无 MMD gate_review_id 映射 | Quality | `gates` 表 | Gate → Project | 无需（1:1 写入） |

---

## 2. 原则

1. **MMD 导入是 Projection/Interchange**：MMD 文件读入 AIPD canonical 表，
   生成 lineage 边（来源=MMD 文件 + object id），不建立第二套 graph persistence。
2. **source of truth 始终是 AIPD canonical 表**；MMD 导出只是投影。
3. **状态字段遵循 STATUS_SEMANTICS.md**：NPI definition_status 不得折叠进
   epistemic_status/lifecycle_status。
4. **重复项**：`evidence`/`risks`/`decisions`/`changes`/`gates` 已有一致 canonical
   实现 → MMD 导入走现有 service（写入即映射）。
5. **requirements（v5.9 已落地）**：`product_intelligence.Requirement`（migration v10）
   —— NPI-ready 字段（nominal_value/unit/lower_limit/upper_limit/tolerance/
   test_condition/verification_method/derivation_method/affected_item_refs/
   required_by_gate/owner）可直接承接 MMD requirement 投影；definition_status
   与 epistemic_status 正交（§40）。未来 MMD=Canonical State 的 Manufacturing
   Projection，不做第二套制造 Requirement（§62）。
6. **仍待 schema extension**：bom_items/suppliers/validation_tests/open_issues
   → 后续版本（见 V5_9_IMPLEMENTATION_PLAN.md）。

---

## 3. 未来实现建议

- 新建 `mmd` package：`mmd.parse` / `mmd.project_to_canonical` /
  `mmd.export_from_canonical`，全部走现有 Domain Service（不直接写表绕过 audit/version）。
- 每个 MMD object 导入后写 `lineage.add_edge(project → object, "derived_from",
  provenance={"source": "mmd", "mmd_id": ...})`（复用 Commit 9 generic lineage）。
