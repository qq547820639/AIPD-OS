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

## 六、终局读数（占位）
