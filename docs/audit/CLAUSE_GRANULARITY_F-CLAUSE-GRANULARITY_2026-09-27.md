# 能力缺失判据落到子句粒度（F-CLAUSE-GRANULARITY，第 73 片，2026-09-27）

产物：`scripts/absence_claim_census.py` 的 `classify_absence` + 三档丢弃计数 + 未知轴前提；
`tests/test_absence_claim_census.py` 新增 3 条控制（含 5 例参数化）；`docs/audit/s73/battery73.py`（4 臂）。
不改登记表文案，因此 `capability_matrix` 与 README 本轮不动。

## 一、两个假阴性（都是"整句判"的代价）

| 语料句 | 里面真有什么 | 整句判的后果 |
| --- | --- | --- |
| 「…所以「没有执行器」不会被伪装成「返工失败三次」。四类之外到今天仍没有执行器的是 quote_batch」 | 真缺失断言 + 一句谈口径 | 整句被 NON_CLAIM 挡掉 ⇒ `REWORK-EXECUTOR-QUOTE-BATCH` 那条登记的"改了要撤"从没被机器管过 |
| 「C6 的「装配/维护」里维护指引没有生产者（内容要属主给），…读者不会把骨架当…」 | 真缺失断言 + 一句谈读者理解 | 我为它写的豁免理由成了**空装饰**（那句不在分母里） |

第二条尤其说明问题：豁免看起来在管一句话，实际上那句话根本没进判据面。

## 二、判据形状

- 子句 = `re.split(r"[。；;，、]")`；任一子句满足「缺失谓词 × 能力名词 × 不含谈判决」⇒ 整句进窄档。
- 不进窄档的句子必须归入三档之一，计数**印出来**（挡掉多少、为什么挡，与登记了多少同样要可见）。
- 未登记的轴 ⇒ `classifier_unknown_axis` ⇒ 退 2：词表被改坏时不许静默"这句不算"。

## 三、控制的强度是电池逼出来的（两轮）

第一版电池 M1（去掉逗号/顿号）与 M2（清空 NON_CLAIM 首项）**存活**：
- M1：我所有参数化用例的例句只用句号分隔 ⇒ 逗号那一档没有任何断言依赖，改与不改同读数；
- M2：只替换元组首项，其余模式照样挡句子 ⇒ `dropped_non_claim` 没变 0，轴下界不红。
补法：① 用**语料里那句真实文本**钉粒度（并从语料现读，不抄文本）；② 锚点改成清空整个元组。
之后 4 臂全杀。这正好复用了记忆里那条："一条臂存活先怀疑夹具/锚点不分辨，而不是先怀疑判据"。

## 四、终局读数（由 `docs/audit/s73/terminal73.py` 从原件现跑生成，不手抄）

- **签出那一跑**（`tmp/s73/final`，报告产出于提交 `9dddab2`，主树当时 HEAD `718a333`）：`exitcode=0`、`collected=2590`、`passed=2587`、`skipped=3`、其余终态 `{'skipped': 3}`、用时 `248.3s`、`root=/Volumes/Extra/CodeProj/AI全链路自研/tmp/s73/final`、`source_commit=a66040520139`
- **本片主角（真仓库终态）**：`rc=0`；语料：84 个能力，带否定词的句子 36 句；账本登记 13 条，未挂锚点 29 句（宽档，只报不判）；能力缺失句（窄档＝判据面）：17 句 = 登记 7 + 豁免 10 + **未处置 0**；判红 0 条：登记的 13 句「仍缺着」现在都还缺着
- **`--self-test`**：`rc=0`，**24 条**合成读数全对上（本片未加合成读数；档位沿用第 71/72 片）
- **常驻用例（量具 + 执行守卫合跑）**：`pytest tests/test_absence_claim_census.py tests/test_supervisor_execution.py -q` → `33 passed, 24 warnings in 20.71s`（rc=0）
- **变异电池（入库副本现跑）**：`docs/audit/s73/battery73.py` → `rc=0`，合计 KILLED 4 / 其余 0
- **两档分母现读**：宽档 36 句、窄档 17 句（差的 19 句按轴分：无缺失谓词 11、无能力名词 5、谈判决/谈口径 3）；登记表解析问题 `[]`；薄理由豁免 `[]`
- **第 64 片那台收尾验签在本片树上**：`rc=0`；收尾验签（报告 ↔ 证据 ↔ 工作树）；读数：报告 2590 条 / 211 个文件，树 211 个文件 / 2504 个 def，终态 {'passed': 2587, 'skipped': 3}
- **发布门禁**：`rc=0`、`"passed": true` 计 8 条、`release_ready` true
- **沿第 71 片那条轴的读数（本片改的是粒度，未加新档）**：`external_callers` 对 `commit_approved` / `commit_snapshot` 判 HOLDS，正向对照 `record_dxf_lineage` 判 CONTRADICTED（同一函数换个名字就翻红 ⇒ 探针会开火；第一版这里用的是改口前的旧锚点，读出来是「账文脱钩」而不是「过期」，已更正）
- **`audit_repo --strict`**：`rc=1`，恰 **1** 条 ✗（`✗ Provenance source commit mismatch: manifest=a66040520139… vs HEAD=71`）——设计内不修
- **锚点与哈希面**：`SOURCE_MANIFEST.source_commit` = `a66040520139` == tag；被哈希文件数 `674`；**相对 tag v5.6.0** 的清单：新增 163 个、消失 9 个（这是 25 片的累计漂移，不是本片增量——本片增量看 `chore(sN): 清单再锚` 那两条提交里的文件数）
- **相对 tag 新增的被哈希文件（前 5 个）**：`assets/templates/fact.json`、`docs/architecture/project_boundary.md`、`docs/architecture/state_infrastructure.md`、`docs/architecture/state_inventory.md`、`scripts/absence_claim_census.py`
- **工作树**：`git status --porcelain` 输出 0 行

**本节生成时连修三次，都是同一类病**（值得记，因为它发生在"读数是脚本生成、所以不会错"的假设上）：
① 小节编号抄上一片（本篇是 §四，脚本找 §五 ⇒ 拒写）；
② 两档差值的说明写死成"谈判决/谈口径的假阳性"，而本片刚刚把它分成三轴；
③ 常驻用例那行把同一个文件传了两遍 —— 于是"54 passed"其实是 27 条跑两次，
   看着像覆盖变大了，实际什么都没多测。三次都在脚本里改（不是在文档里手补数字），
   改完重新生成，所以这一节的每个数都能由 `docs/audit/s73/terminal73.py` 复算。

## 五、下一片入口

1. 第 64 片留的 `doc_command_census` 只报面收窄（`tests/` 不进语料 + 单开"记录性引述"一桶）。
2. `evidence_rework` 与 CLI 每次新建 `Supervisor`（构造里含建表/迁移），等有性能或并发证据再动。
3. 本轮新记：三档丢弃计数目前是"每档 > 0"的下界；更细的做法是给每档配一个**具名样本句**
   （从语料现读 + 断言它落在该档），这样词表被改成"整体偏移"时也能被点名，而不是只看总数。
