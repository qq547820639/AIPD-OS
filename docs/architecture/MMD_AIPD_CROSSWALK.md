# MMD → AIPD Canonical Object 映射（v5.10 更新）

> **MMD 是 Projection/Interchange，不是第二 Truth Store（§64）。**
> 本表逐项说明：MMD object 在 AIPD 中的 canonical 落点、现状、
> owner / source of truth / lineage。

---

## 1. 映射表

| MMD object | AIPD canonical | existing implementation | owner | source of truth | lineage |
|---|---|---|---|---|---|
| `evidence` | State Evidence（`evidence` 表） | ✅ `db.add_evidence` / canonical dedupe | Research/State | `evidence` 表 | EvidenceRelation → Claim |
| `requirements` | Requirement（`product_intelligence.Requirement`） | ✅ migration v10，NPI-ready 字段 | Product/State | `product_intelligence` 表 | Claim → Evidence |
| `bom_items` | BOM（`bom.BomStore`） | ✅ `src/aipd_os/bom/`：models, store, cost, projection | Engineering | `bom` store | Deliverable → Project |
| `suppliers` | Supply Chain | ⚠️ `supplier_adapter` / MailRfqAdapter 存在 | Procurement | supplier 适配器输出 | 暂无 |
| `validation_tests` | Validation（`validation.*`） | ✅ migration v13：validation_plans/tests/runs/results | Quality | `validation_*` 表 | Requirement → Test → Result |
| `risks` | Risk（`risks` 表） | ✅ `db.add_risk` / list_risks | Risk owner | `risks` 表 | Risk → Project |
| `open_issues` | Issue（`validation.issues`） | ✅ migration v13：issues + corrective_actions | Program | `issues` 表 | Result → Issue → Action |
| `decisions` | Decision（`decisions` 表） | ✅ `db.propose_decision` / resolve | Owner | `decisions` 表 | Decision → Project |
| `changes` | Change（`changes` 表） | ✅ `db.add_change` | Engineering | `changes` 表 | Change → Object |
| `gate_reviews` | Gate Review（`gates` 表） | ✅ `db.add_gate` | Quality | `gates` 表 | Gate → Project |

---

## 2. 原则

1. **MMD 导入是 Projection/Interchange**：MMD 文件读入 AIPD canonical 表，
   生成 lineage 边（来源=MMD 文件 + object id），不建立第二套 graph persistence。
2. **source of truth 始终是 AIPD canonical 表**；MMD 导出只是投影。
3. **状态字段遵循 STATUS_SEMANTICS.md**：NPI definition_status 不得折叠进
   epistemic_status/lifecycle_status。
4. **重复项**：`evidence`/`risks`/`decisions`/`changes`/`gates` 已有一致 canonical
   实现 → MMD 导入走现有 service（写入即映射）。
5. **requirements**：`product_intelligence.Requirement`（migration v10）——
   NPI-ready 字段可直接承接 MMD requirement 投影。
6. **BOM**：`bom.BomStore`（v5.10）—— BOM models/store/cost/projection 已落地。
7. **Validation**：`validation.*`（migration v13）—— ValidationPlan/Test/Run/Result
   + Issue + CorrectiveAction 已落地。
8. **Issues**：`validation.issues`（migration v13）—— Issue + CorrectiveAction
   已落地，支持 idempotent creation、close semantics、audit trail。

---

## 3. MMD Projection 实现

### AIPD → MMD

```
canonical services → projection → versioned MMD artifact
```

输出必须包含：
- `schema_version`：MMD schema 版本
- `producer`：生成者标识
- `source_revision`：源 revision
- `generated_at`：生成时间
- `object_ids`：对象 ID 列表
- `content_hashes`：内容哈希
- `validation_errors`：验证错误

### MMD → AIPD

```
parse → validate → domain service commands → canonical state
```

禁止 MMD 自己维护第二套产品 truth DB。禁止双主写。

---

## 4. 待完成

- `suppliers`：canonical supplier 表（contact/qualification）
- MMD parser/projector/exporter 层的完整实现
- MMD ↔ AIPD 双向集成测试
