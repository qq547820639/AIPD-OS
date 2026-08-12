# Score Contract（v5.8.2 Commit 8）

> 原则（提示词 §19-20）：「不把不知道的东西装成知道」同样适用于数字。

## 1. 未评分 = NULL，不是 0.5

- `Claim.confidence` / `EvidenceRelation.strength`：模型层 `Optional[float]`，
  未显式评分 → `None`。
- **DB 层（migration v9 起）**：`confidence` / `strength` 列 NULLABLE；
  新记录未评分写 `NULL`（不再落 `0.5` 哨兵）。
- **旧数据（v9 之前）**：`0.5` 是 `NOT NULL DEFAULT 0.5` 产生的
  legacy_unscored 哨兵。读取时模型层按
  `LEGACY_UNSCORED_SENTINEL == 0.5` 映射为 `None`
  （`claims.LEGACY_UNSCORED_SENTINEL` / `evidence_relations.LEGACY_UNSCORED_SENTINEL`）。
  migration v9 **保守保留** 0.5 值不迁移（无法可靠区分「真实显式 0.5」与
  「默认哨兵」，宁可保守，不破坏历史数据）。
- 禁止：把 0.5 当作「默认置信度」展示或计算。

## 2. 有评分的数字必须可溯源

任何未来 numeric score（v5.9+ 新对象）必须同时记录：

| 字段 | 含义 |
| --- | --- |
| `score` | 数值本身 |
| `score_model` | 评分模型/规则标识（如 `claim_assessment_v1`、`source_credibility_v2`） |
| `score_model_version` | 模型版本 |
| `inputs` | 评分的输入摘要（hash 或引用） |
| `generated_at` | 评分生成时间 |

没有版本化 scoring model 的数字不得展示为伪精确（`82%` / `0.64`）。
当前系统唯一允许的「无模型版本」数字是 legacy `facts.confidence`
（v1 历史字段，不进入新 Domain）。

## 3. 校验

- `0.0 <= score <= 1.0`（None 表示未评分）；
- 新 Domain 写入遵循本 contract（`tests/test_score_contract.py` 锁定
  nullable 写入 + legacy 读取映射）。
