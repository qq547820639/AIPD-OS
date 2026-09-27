# 产品定义门禁的 commit 没有生产入口（F-GATE-COMMIT-ENTRY，第 68 片，2026-09-27）

产物：`scripts/absence_claim_census.py` 加一档 `external_callers`（+ (root,symbol) 记忆化）、
`scripts/product_capabilities_extra.py` 与生成物 `src/aipd_os/registry_data.py` 各补一条限制、
账本两条新登记、`tests/test_absence_claim_census.py` 22 → 26 条、`docs/audit/s68/battery68.py` 4 臂。
本片不加 `aipd` 命令、不加旗子、不加脚本文件（被哈希面 669 → 669，只改内容）。

## 一、这一片修的是"低报"，与前两片方向相反

第 65/66 片修的都是**写着没有、其实已经有了**（过期缺口句）。这一片是反方向：
**写着的链路里，有一步其实没有生产入口**。普查用 AST 而不是子串 grep：

| 符号 | 生产面（`src/`+`scripts/`+`state_service/`）外部调用点 | 唯一命中在哪 |
| --- | --- | --- |
| `commit_approved` | **0** | —（定义了没人调） |
| `commit_snapshot` | **0** | `gate.py:562` 在**同文件**里被 `commit_approved` 调 ⇒ 按"外部"口径不算 |
| `record_dxf_lineage`（正向对照） | **1** | `src/aipd_os/cli/commands_drawing.py:240` |

`aipd product gate` 只走到 evaluate / authorization / eligibility（`cli/product_commands.py`），
所以结论是：**Product Definition Gate 的 commit 这一步今天没有生产入口**，
`requirement` 与 `feature` 两类 `product_truth` 记录只由测试驱动
（`tests/` 里 6 个文件调 commit；产品入口 0 个）。
登记表原话把这条链写成"Snapshot → GateEvaluation（READY/CONDITIONAL/BLOCKED +
authorization + eligibility）"——**没撒谎，但少写了一格**：读者会以为再往前一步就落到 truth 记录。

这也正面解释了第 66/67 片为什么不能直接做 `supervisor.fact_writeback → truth_lineage`：
要连的那批上游 `requirement`/`feature` 记录，在生产流程里根本还没人被写出来。
所以本片先修"看得见的事实"，把那一条留到有生产入口之后。

## 二、机器形状

新档 `external_callers`：`{kind: external_callers, symbol: X}` ⇒
反证 = X 在生产面的**外部**调用点（不在定义 X 的那个文件里）。
"外部"这一刀是关键：`commit_snapshot` 的调用点确实存在，但就在那条兼容包装自己身上，
把它算成"已接线"就是这次要防的错。加了 `(root, symbol)` 记忆化，整轮 census 实测 4.6s。

登记两条（不是一个符号一条就够）：`GATE-COMMIT-NO-PRODUCER-APPROVED` 与
`GATE-COMMIT-NO-PRODUCER-SNAPSHOT`，各盯一个名字——**接 CLI 时只接其中一个也会翻红**，
"接了另一个"不许被读成"还是没接"。

薄语料不判：除登记表自身外没有别的生产代码文件时记 `authority_thin` 并退 2。

## 三、两条被自己的控制教出来的形状（都不是推出来的）

1. **我写的守卫永不开火。** 第一版是 `scanned == 0 ⇒ 前提不成立`，
   但任何能被 `registry_strings` 解析出内容的语料里 `scanned` 至少为 1——登记表自己就在被扫的树上。
   这条守卫在真仓库与合成树上都不可能触发，属于"看起来保守、实际是死码"的前提档。
   改成"除登记表外没有别的 .py"之后，`test_external_callers_without_production_tree_is_precondition`
   才第一次让它变红（也正是电池 D3 臂的靶）。
2. **报错形状会冒充判据缺陷。** 那条控制测试我第一版直接 `write_text` 到没建的目录，
   拿到的是 `FileNotFoundError`，一眼像"external_callers 判不出来"；读栈才发现是夹具没建目录。
   夹具错与判据错的读数形状不同，别跳过读栈直接怀疑判据。

另记一条我自己的重复自伤（本会话第 5 次）：在双引号字符串里嵌半角双引号写中文引述 ⇒ `SyntaxError`。
入库副本里两处超长锚点因此改用 `# ruff: noqa: E501` 而不是手工拆字面量——
**锚点的值必须逐字不变**，拆行比重写更安全的情况是相邻字面量拼接，但我在同一个脚本里
连着把拼接写坏两次，所以选择不动值。这条已进记忆。

## 四、与"去处台账"的闭环

新增的这条限制句本身就是能力缺失句（「今天没有生产入口」：缺失谓词 × 名词"入口"），
所以它自动进窄档分母并必须挂锚点——实测：窄档从 17 涨到 19，登记 9 条、豁免 10 条、未处置 0。
**登记文本变长没有让机器管不住的比例变大**，这正是第 67 片那面账要的效果。

## 五、下一片入口

1. 把门禁 commit 接进 CLI（`aipd product gate --commit` 之类，走"加旗子"那一档镜像清单），
   接上时账本那两条会翻红 ⇒ 同批改口。这一步做完，`supervisor` 那条边的上游记录才存在。
2. 第 64 片留的 `doc_command_census` 只报面收窄仍未做。
3. 窄档两个手写词表仍无自证（第 67 片 §七.3）。

## 六、终局读数（由 `docs/audit/s68/terminal68.py` 从原件现跑生成，不手抄）

- **签出那一跑**（`tmp/s68/checkout`，报告产出于提交 `06f9133`，主树当时 HEAD `03859f7`）：`exitcode=0`、`collected=2566`、`passed=2563`、`skipped=3`、其余终态 `{'skipped': 3}`、用时 `296.8s`、`root=/Volumes/Extra/CodeProj/AI全链路自研/tmp/s68/checkout`、`source_commit=a66040520139`
- **本片主角（真仓库终态）**：`rc=0`；语料：84 个能力，带否定词的句子 39 句；账本登记 13 条，未挂锚点 29 句（宽档，只报不判）；能力缺失句（窄档＝判据面）：19 句 = 登记 9 + 豁免 10 + **未处置 0**；判红 0 条：登记的 13 句「仍缺着」现在都还缺着
- **`--self-test`**：`rc=0`，**22 条**合成读数全对上（含四档去处判决与 `table_ddl` 双向）
- **常驻用例**：`pytest tests/test_absence_claim_census.py -q` → `26 passed in 11.77s`（rc=0）
- **变异电池（入库副本现跑）**：`docs/audit/s68/battery68.py` → `rc=0`，合计 KILLED 4 / 其余 0
- **两档分母现读**：宽档 39 句、窄档 19 句（差 20 句是谈判决/谈口径的假阳性）；登记表解析问题 `[]`；薄理由豁免 `[]`
- **第 64 片那台收尾验签在本片树上**：`rc=0`；收尾验签（报告 ↔ 证据 ↔ 工作树）；读数：报告 2566 条 / 208 个文件，树 208 个文件 / 2483 个 def，终态 {'passed': 2563, 'skipped': 3}
- **发布门禁**：`rc=0`、`"passed": true` 计 8 条、`release_ready` true
- **本片新档的读数**：`external_callers` 对 `commit_approved` / `commit_snapshot` 各判 `HOLDS`（生产面外部调用点均为 0），正向对照 `record_dxf_lineage` 判 `CONTRADICTED`（同一函数在 `commands_drawing.py:240` 有 1 处外部调用点 ⇒ 探针会开火）
- **`audit_repo --strict`**：`rc=1`，恰 **1** 条 ✗（`✗ Provenance source commit mismatch: manifest=a66040520139… vs HEAD=03`）——设计内不修
- **锚点与哈希面**：`SOURCE_MANIFEST.source_commit` = `a66040520139` == tag；被哈希文件数 `669`（本片**文件数不变**，只改内容）
- **工作树**：`git status --porcelain` 输出 0 行

**这一节的读数被闸拒了三次才写成，三次都是闸对、脚本错**（记下来，因为它同时证了三件事）：
① 第一次 `closeout_verifier rc=4 / gate rc=2`：那时我还有未提交的改动 —— 验签打印的是
`worktree_clean：工作树有 1 处未提交改动：['M docs/audit/s68/terminal68.py']`，
门禁同一口径，两把都没被我"顺手放宽"；
② `battery rc=2` 的真相是脚本里路径写成 `docs/audit/s67/battery68.py`（我生成 terminal68 时
只替了 `battery67.py` 文件名、没替目录）——**第一版的失败消息不带输出尾，只能猜**，
补上 `输出尾：…can't open file…` 才一次定位；
③ 修完路径重跑，工作树干净 → 全绿（上面那串读数）。

**这两行为什么是手改的**：第一版 `terminal68.py` 的行里写着 `tmp/s67/checkout`（我从第 67 片
脚本复制时只替了报告文件名，没替句子里的路径字面量），而"本片新档的读数"那一行把
**语料级**的 `UNACCOUNTED` 行一起数进了"判决集合"（喂半份账本必然产生那些行，第 67 片的
常驻用例里就记过这个坑）。两处都在脚本里改掉了：路径改对、判决集合按 claim id 过滤。
文档里这一行是照脚本新形状更正事实，不是补一个更好看的说法——`external_callers` 的两条
登记今天确实各判 `HOLDS`，正向对照确实判 `CONTRADICTED`。
