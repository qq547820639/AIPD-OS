# 能力缺失句逐条有去处（F-ABSENCE-LEDGER，第 67 片，2026-09-27）

产物：`scripts/absence_claim_census.py` 加"去处台账"一面（`is_capability_absence` /
`EXEMPTIONS` / `UNACCOUNTED` / `table_ddl` 档）＋ `tests/test_absence_claim_census.py`
（19 → 22 条）＋ `docs/audit/s67/battery67.py`（7 臂）。
本片**不加 `aipd` 命令、不加旗子、不改登记表文案**（改文案会牵动 `capability_matrix` 与
`--pin-commit`，这里没有那件事）；被哈希文件数不变，只改内容。

## 一、起因：第 65 片留下的那个数，本身没人守

第 65 片在输出里写"未挂锚点 N 句（只报，不判红）"，并把它当成诚实的暴露。
问题是：**暴露不等于处置**。那句 N 从 34 涨到 40 也不会有任何一格变红，
于是"覆盖率是一个会变的数"实际上仍然是口头承诺。这一片给它加牙。

## 二、先收窄，再逼处置（顺序反了就会造出一堆空豁免）

直接拿"带否定词的句子"当分母去要求"每条都要登记"，实测是错的：37 句里有 17 句
根本不是缺失断言，而是谈判决/谈口径的写法——

- 「圆内没有图线**即判未收口**，且不编号不画圈」
- 「当前 BOM 没有行、这张 BOM 已不是记录那张…**三种都不算收口**」
- 「公差只能来自 --spec 声明，**未声明则不写任何公差**」
- 「生产者把「一张单都没有」记成盲区不阻断，门把它读成不通过」
- 「所以「没有执行器」**不会被伪装成**返工失败三次」

判据面因此改成**能力缺失句**：缺失谓词（仍没有/还没有/尚未/未实现/未接入/未做/未建/不建模/…）
× 能力名词（执行器/生产者/入口/求解/表/工艺路线/剖/图框/投影/语义/工时/成本/自动/…）同句，
再排掉六个"这句话在谈判决本身"的写法。实测：**宽档 37 句、窄档 17 句**。
这条顺序值得记下来：先收窄，"每条都要有去处"才是可执行的；反过来先逼处置，
得到的是一一长串空理由的豁免，而空理由的豁免就是没有豁免。

## 三、去处两档 + 三档判决

| 档 | 触发 | 后果 |
| --- | --- | --- |
| 登记 | 句子在 `CLAIMS` 里有锚点（两侧都剥 `*` 后逐字相等） | 由反证锚点判 HOLDS/CONTRADICTED |
| 豁免 | 句子在 `EXEMPTIONS` 里，且理由 ≥8 字 | 只报不判，但**理由与句子一起记账** |
| 未处置 `UNACCOUNTED` | 两处都没有 | **判红**（退 4） |
| 豁免理由太薄 `exemption_reason_thin` | 理由为空/过短 | 前提不成立（退 2） |
| 豁免悬空 `CLAIM_TEXT_ABSENT` | 台账里的句子在语料里消失了 | 判红（退 4） |

豁免陈旧性按**宽档**判而不是窄档：豁免记的是"这句我看过、决定不登记"，
而窄档会因为同句里另一处谈判决的写法把整句挡在判据面之外——
那时豁免仍然是有效记录（第 67 片实测：两句这样的豁免被自己的窄档判成"该删"过一次）。

## 四、新增登记的四条（每条锚点都我自己数过 0 命中）

| id | 句子 | 反证锚点 | 今天 |
| --- | --- | --- | --- |
| `BOM-COST-TO-CTQ-REVERSE-PATH` | 「BOM/成本变动要反向影响 CTQ 结论（上游方向）也还没有路」 | `src/aipd_os/bom` 里引用 `ctq`/`CTQ` | 0 命中 ⇒ 成立 |
| `DRAWING-SECTION-TYPES` | 「未做阶梯剖/旋转剖」 | `src/aipd_os/cad` 里 `stepped_section`/`aligned_section`/`rotated_section` | 0 命中 ⇒ 成立 |
| `ASSEMBLY-OPERATIONS-TABLE` | 「多工序工艺路线仍未建 operations 表」 | DDL 里出现 `CREATE TABLE operations(` | 0 处 ⇒ 成立 |
| `ASSEMBLY-STEPS-PDF-LAYOUT` | 「版式只有 Markdown，PDF/图框未做」 | `src/aipd_os/cad` 里 `compose_pdf`/`pdfgen`/`to_pdf` | 0 命中 ⇒ 成立 |

两条**故意做窄**的理由值得单独记：

1. `ASSEMBLY-STEPS-PDF-LAYOUT` 若把锚点取在库里（`src/aipd_os`），会立刻假红——
   `src/aipd_os/layout/composer.py:13-14` 真的 import reportlab 并 `compose_pdf` 出手册 PDF。
   那句话的主语是**装配步骤文档**，锚点就得取在它那一侧。
2. `ASSEMBLY-OPERATIONS-TABLE` 不能用"文件里有没有 `operations` 这个词"——
   实测 `src/aipd_os` 下 17 个文件提到 `operations`（`external_operations` 等），
   那会把真话判成过期。所以新开 `table_ddl` 档，正则要求表名后紧跟左括号，
   前缀碰撞因此不吃（与第 41 片扩展名右边界同一条纪律）。

10 条豁免的完整理由写在 `scripts/absence_claim_census.py` 的 `EXEMPTIONS` 里，
每条都指到一个具体去处（同因的哪条登记吃住它、或这是线下/产品裁决）。

## 五、电池：7 臂，第一版 4 条存活

`docs/audit/s67/battery67.py`（每臂先断言 `old` 恰好命中 1 次、`new` 原本 0 次、
`compile()` 过才落盘，落地后校验 sha 已变，跑靶，`finally` 还原并校验 sha==基线）：

| 臂 | 撤掉什么 | 第一版 | 终局 | 为什么第一版活着 |
| --- | --- | --- | --- | --- |
| C1 | 比较锚点时不剥 `*` | SURVIVED | **KILLED** | 合成语料里当时没有"带 `*` 且已登记"的能力缺失句 ⇒ 补 `**quote_batch**` 那句 |
| C2 | 不做收窄（宽档当判据面） | SURVIVED | **KILLED** | 夹具里当时没有"宽档命中但窄档该挡住"的句子 ⇒ 补 cap.d 两句 |
| C3 | 清空"谈判决"排除表 | SURVIVED | **KILLED** | 我给这条臂**忘了挂 `--self-test` 靶**——臂不炸先怀疑电池，不是先怀疑判据 |
| C4 | 未处置不产出行 | KILLED | KILLED | — |
| C5 | 豁免悬空不判 | KILLED | KILLED | — |
| C6 | 空理由豁免照收 | KILLED | KILLED | — |
| C7 | 去掉 `table_ddl` 那一支 | SURVIVED | **KILLED** | 合成语料里当时没有任何走 `table_ddl` 的登记 ⇒ 补 migrations 夹具（建过 operations ⇒ 判红；没建 routing_rules ⇒ 成立，双向都有） |

四条存活里有三条是同一个病：**夹具不分辨**（两种实现读出同一个数），
一条是电池自己的靶表不全。这与第 58 片 B3 型、第 66 片 B3 臂同族，
本轮把"写控制前先问一句：把被测那支整支反过来，这条夹具的输出会不会变一格"
当成硬规矩用——三条都是问了之后才发现自己没造出差异。

## 六、终局读数（由 `docs/audit/s67/terminal67.py` 从原件现跑生成，不手抄）

- **签出那一跑**（`tmp/s67/checkout`，报告产出于提交 `fd04fcb`，主树当时 HEAD `b49d077`）：`exitcode=0`、`collected=2562`、`passed=2559`、`skipped=3`、其余终态 `{'skipped': 3}`、用时 `328.4s`、`root=/Volumes/Extra/CodeProj/AI全链路自研/tmp/s67/checkout`、`source_commit=a66040520139`
- **本片主角（真仓库终态）**：`rc=0`；语料：84 个能力，带否定词的句子 37 句；账本登记 11 条，未挂锚点 29 句（宽档，只报不判）；能力缺失句（窄档＝判据面）：17 句 = 登记 7 + 豁免 10 + **未处置 0**；判红 0 条：登记的 11 句「仍缺着」现在都还缺着
- **`--self-test`**：`rc=0`，**21 条**合成读数全对上（含四档去处判决与 `table_ddl` 双向）
- **常驻用例**：`pytest tests/test_absence_claim_census.py -q` → `22 passed in 28.51s`（rc=0）
- **变异电池（入库副本现跑）**：`docs/audit/s67/battery67.py` → `rc=0`，合计 KILLED 7 / SURVIVED 0 / 电池自身问题 0
- **两档分母现读**：宽档 37 句、窄档 17 句（差 20 句是谈判决/谈口径的假阳性）；登记表解析问题 `[]`；薄理由豁免 `[]`
- **第 64 片那台收尾验签在本片树上**：`rc=0`；收尾验签（报告 ↔ 证据 ↔ 工作树）；读数：报告 2562 条 / 208 个文件，树 208 个文件 / 2479 个 def，终态 {'passed': 2559, 'skipped': 3}
- **发布门禁**：`rc=0`、`"passed": true` 计 8 条、`release_ready` true
- **`audit_repo --strict`**：`rc=1`，恰 **1** 条 ✗（`✗ Provenance source commit mismatch: manifest=a66040520139… vs HEAD=b4`）——设计内不修
- **锚点与哈希面**：`SOURCE_MANIFEST.source_commit` = `a66040520139` == tag；被哈希文件数 `669`（本片**文件数不变**，只改内容）
- **工作树**：`git status --porcelain` 输出 0 行

**补记一条环境读数事故（不修代码，改脚本的闸）**：上面那串"门禁 8/8"之后，我在**最终 HEAD**
（本节落盘的那一提）上又跑了一次门禁，读出 `rc=2`、只有 7 条 `"passed": true`，
失败项是 `no_unacknowledged_cve`，detail 写的是「pip-audit not available…（fail-closed）」。
这是项目记忆里记过两次的同一格：**门禁用 `shutil.which('pip-audit')` 找可执行，
PATH 里没带 `.venv/bin` 就 fail-closed 假红**。同一条命令树、同一份清单，
补上 PATH 后复跑 → `rc=0`、8 条 true、`release_ready: true`（已实测）。
处置不是把这一格当回归去改代码，而是给 `terminal67.py` 加了一道**跑前先查 pip-audit 在不在 PATH**
的守卫：不在就整轮拒写读数并打印该 export 什么——环境缺位不该冒充判决，也不该由读者去猜。

## 七、下一片入口
1. `supervisor.fact_writeback → truth_lineage`：第 66 片 §七.3 的普查结论仍然成立
   （没有任何生产者把工作项的上游 truth 身份带进 `inputs`），
   先做"带进来"那一步（契约 + 至少一个真调用点），再谈边。
2. 第 64 片留的 `doc_command_census` 只报面收窄（`tests/` 不进语料 + 单开"记录性引述"一桶）仍未做。
3. 窄档的两个词表（缺失谓词 / 能力名词）今天是**手写的**，它们自己也需要反证：
   下一片可加一档"词表覆盖自证"——从窄档里被挡掉的 17 句里抽若干做常驻阴性夹具，
   防止将来加名词时把真缺失挡掉（这是本轮唯一没被机器管住的判断点）。
