# 三档"挡掉"各配具名样本（F-AXIS-SAMPLES，第 74 片，2026-09-27）

产物：`scripts/absence_claim_census.py` 的 `AXIS_SAMPLES` / `check_axis_samples` /
`_sample_problems_for`；`tests/test_absence_claim_census.py` +2 条（`def test_` 计数 27 → 29）；
`docs/audit/s74/battery74.py`（5 臂）。不改登记表与矩阵。

## 一、为什么"每档 > 0"不够

第 73 片的三档下界只保证"没有哪档被改废"。但一次分布漂移可以完美绕过它：

| 改动 | 窄档 | 无谓词 | 无名词 | 谈判决 | 下界检查 |
| --- | --- | --- | --- | --- | --- |
| 把两句窄档挪去无名词、又把两句无名词挪去谈判决 | 17→15 | 11 | 5→7 | 3→5 | 全过 |

钉分布的办法只有一个：**说得出名字**。每档配 1–2 条逐字取自登记表的样本串，
样本对应的句子今天落在哪一档，是判据的一个可复核结论。

## 二、三种失败面（都是前提不成立，不是判红）

- `sample_missing`：样本串在本仓语料里找不到 ⇒ 登记表文案漂了，样本要跟着改而不是删掉。
- `sample_axis_mismatch`：样本在，但分类器把它判到别的档 ⇒ 词表被改坏。
- `axis_without_sample`：某档样本被清空 ⇒ 通常是"为了让判据看起来更严"顺手删了对照。

都是"刻度不准"，此时任何 HOLDS/CONTRADICTED 都不可信，所以退 2 而不是退 4。

## 三、两处自己被抓的写法

1. **接线没有反证**：真语料那条只断言 `problems == []`——把校验函数改成永远返回空表它也绿。
   补了 `test_sample_validation_is_actually_wired_into_the_audit`（喂坏样本要求真的报）。
2. **电池锚点截半句**：Q4 只替换了跨两行的 `problems.append(...)` 首行，替换后剩下悬空续行
   ⇒ BAD-MUTATION。锚点必须括住完整语句（同"单行锚点若是前缀会把原行另一半留在原地"那条）。

## 四、终局读数（由 `docs/audit/s74/terminal74.py` 从原件现跑生成，不手抄）

- **签出那一跑**（`tmp/s74/final`，报告产出于提交 `feaf9e5`，主树当时 HEAD `362deb1`）：`exitcode=0`、`collected=2592`、`passed=2589`、`skipped=3`、其余终态 `{'skipped': 3}`、用时 `344.8s`、`root=/Volumes/Extra/CodeProj/AI全链路自研/tmp/s74/final`、`source_commit=a66040520139`
- **本片主角（真仓库终态）**：`rc=0`；语料：84 个能力，带否定词的句子 36 句；账本登记 13 条，未挂锚点 29 句（宽档，只报不判）；能力缺失句（窄档＝判据面）：17 句 = 登记 7 + 豁免 10 + **未处置 0**；判红 0 条：登记的 13 句「仍缺着」现在都还缺着
- **`--self-test`**：`rc=0`，**25 条**合成读数全对上（条数由本次运行现数，不引用上一片的说法）
- **常驻用例（量具 + 执行守卫合跑）**：`pytest tests/test_absence_claim_census.py tests/test_supervisor_execution.py -q` → `35 passed, 24 warnings in 25.39s`（rc=0）
- **变异电池（入库副本现跑）**：`docs/audit/s74/battery74.py` → `rc=0`，合计 KILLED 5 / 其余 0
- **两档分母现读**：宽档 36 句、窄档 17 句（差的 19 句按轴分：无缺失谓词 11、无能力名词 5、谈判决/谈口径 3）；登记表解析问题 `[]`；薄理由豁免 `[]`
- **第 64 片那台收尾验签在本片树上**：`rc=0`；收尾验签（报告 ↔ 证据 ↔ 工作树）；读数：报告 2592 条 / 211 个文件，树 211 个文件 / 2506 个 def，终态 {'passed': 2589, 'skipped': 3}
- **发布门禁**：`rc=0`、`"passed": true` 计 8 条、`release_ready` true
- **具名样本核对**：四档共 8 条，样本问题 0 条；分档 {'no-noun': 5, 'non-claim': 3, 'narrow': 17, 'no-predicate': 11}
- **沿第 71 片那条轴的例行复算**：`external_callers` 对 `commit_approved` / `commit_snapshot` 判 HOLDS，正向对照 `record_dxf_lineage` 判 CONTRADICTED（同一函数换个名字就翻红 ⇒ 探针会开火；第一版这里用的是改口前的旧锚点，读出来是「账文脱钩」而不是「过期」，已更正）
- **`audit_repo --strict`**：`rc=1`，恰 **1** 条 ✗（`✗ Provenance source commit mismatch: manifest=a66040520139… vs HEAD=36`）——设计内不修
- **锚点与哈希面**：`SOURCE_MANIFEST.source_commit` = `a66040520139` == tag；被哈希文件数 `674`；**相对 tag v5.6.0** 的清单：新增 163 个、消失 9 个（这是 25 片的累计漂移，不是本片增量——本片增量看 `chore(sN): 清单再锚` 那两条提交里的文件数）
- **相对 tag 新增的被哈希文件（前 5 个）**：`assets/templates/fact.json`、`docs/architecture/project_boundary.md`、`docs/architecture/state_infrastructure.md`、`docs/architecture/state_inventory.md`、`scripts/absence_claim_census.py`
- **工作树**：`git status --porcelain` 输出 0 行

**这一节的生成过程本身又是一次"复制脚本文案"的复发**：脚本带着上一片的两处自我描述
（"本片未加合成读数"、"本片改的是粒度"），两句对本片都不成立；已在 `terminal74.py` 里
改成现数，并新增一行"具名样本核对"。这正是本片要钉的那类毛病的现场版——
**分布没人看，措辞就会自己漂**，所以我把它也写进控制：读数里凡是"本片如何如何"的句子，
必须由脚本现算，不接受从上一份脚本继承。

## 五、下一片入口

1. 第 64 片留的 `doc_command_census` 只报面收窄（`tests/` 不进语料 + 单开"记录性引述"一桶）。
2. `AXIS_SAMPLES` 目前是"每档 1–2 条"，可以进一步要求**每条样本都同时被登记/豁免账管着**
   （narrow 档的样本恰好都已有去处），否则样本进窄档后没人处置也无人红。
