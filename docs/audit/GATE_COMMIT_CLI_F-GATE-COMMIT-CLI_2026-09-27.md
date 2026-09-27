# 把产品定义门禁的 commit 接上 CLI（F-GATE-COMMIT-CLI，第 69 片，2026-09-27）

产物：`src/aipd_os/cli/main.py`（旗子）、`src/aipd_os/cli/product_commands.py`（支路）、
`scripts/absence_claim_census.py`（`expect: "present"`）、`tests/test_product_gate_commit_cli.py`（4 条）、
`docs/audit/s69/battery69.py`（5 臂）、登记表/README/账本的同批改口。命令数与三张分母不变；
被哈希文件数 669 → 670（新增一个常驻测试文件，差集见 §五）。

## 一、这一步为什么值得单独一片

第 68 片把"没有生产入口"变成了一条可判红的登记；本片把它闭合，
顺带把判据的形状补全：账本从"只有缺席式"变成"缺席式 + 存在式"。
存在式是必要的——**只有缺席式的账本，会在被修好的那一刻自动变瞎**：
`GATE-COMMIT-NO-PRODUCER-*` 一旦撤掉，那句话就没有任何机器再盯着了。

## 二、改口清单（一轮里必须同批动的位置）

| 面 | 改了什么 |
| --- | --- |
| `cli/main.py` | `--commit` 旗子 + parser help |
| `cli/product_commands.py` | 支路：`commit_approved(actor="owner-cli")`，不吞错 |
| `scripts/product_capabilities_extra.py` | `product.definition_gate` 的限制句改口（权威在此） |
| `src/aipd_os/registry_data.py` | 由 `migrate_capability_registry.py` 生成（不手改） |
| `docs/audit/capability_matrix.{md,json}` | 按 tag 重生成 |
| 量具账本 | 撤 2 条缺席式、加 1 条存在式（`expect: present`） |
| 常驻控制用例 | 第 68 片盯 0 调用点的两条改方向（否则绿着守旧说法） |
| `README.md` | 速查加 `--commit`；第 68 片那段"外部调用点为 0"就地更正 |

## 三、两条被实测纠正的预期

1. 我以为第二次 `--commit` 会走 `idempotent_replay` 幂等成功；实测被"非 frozen"拒
   （`commit_approved` 取最新 snapshot，它已 committed）。**代码赢，读数改判**，
   而且这个结果比静默重放更符合"旗子不许把拒绝洗成成功"。
2. 我第一版常驻用例用 `capsys.readouterr().stdout`（该对象只有 `.out/.err`），
   以及把私有方法 `_lineage_edges_for_test` 当断言路径——两处都在跑的第一秒暴露，
   都改成 SQL 直读 `truth_lineage`：判据要盯权威事实，不盯实现里恰好存在的方法名。

## 四、电池（5 臂，杀 5 / 活 0）

E1 摘掉 `expect=present` 那一支；E2 让缺席式永不判红（"永不判红"而不是"取反"——
第一版我写的是取反，被电池自己的 `new 已在树上` 守卫挡下，因为取反后的文本恰是存在式那一支）；
E3 摘掉 CLI 支路；E4 把前置校验的抛错洗成 ok；E5 旗子不进 argparse。
每臂先断言 `old` 恰好 1 处、`new` 不在树上、`compile()` 过，落地后校验 sha 已变，
`finally` 还原并再校验 sha 与基线同值。

## 五、终局读数（由 `docs/audit/s69/terminal69.py` 从原件现跑生成，不手抄）

- **签出那一跑**（`tmp/s69/final`，报告产出于提交 `f8daa16`，主树当时 HEAD `2009ecb`）：`exitcode=0`、`collected=2571`、`passed=2568`、`skipped=3`、其余终态 `{'skipped': 3}`、用时 `282.2s`、`root=/Volumes/Extra/CodeProj/AI全链路自研/tmp/s69/final`、`source_commit=a66040520139`
- **本片主角（真仓库终态）**：`rc=0`；语料：84 个能力，带否定词的句子 37 句；账本登记 12 条，未挂锚点 29 句（宽档，只报不判）；能力缺失句（窄档＝判据面）：17 句 = 登记 7 + 豁免 10 + **未处置 0**；判红 0 条：登记的 12 句「仍缺着」现在都还缺着
- **`--self-test`**：`rc=0`，**23 条**合成读数全对上（含四档去处判决、`table_ddl` 双向与存在式登记双向）
- **常驻用例**：`pytest tests/test_product_gate_commit_cli.py tests/test_absence_claim_census.py -q` → `30 passed, 24 warnings in 29.64s`（rc=0）
- **变异电池（入库副本现跑）**：`docs/audit/s69/battery69.py` → `rc=0`，合计 KILLED 5 / 其余 0
- **两档分母现读**：宽档 37 句、窄档 17 句（差 20 句是谈判决/谈口径的假阳性）；登记表解析问题 `[]`；薄理由豁免 `[]`
- **第 64 片那台收尾验签在本片树上**：`rc=0`；收尾验签（报告 ↔ 证据 ↔ 工作树）；读数：报告 2571 条 / 209 个文件，树 209 个文件 / 2488 个 def，终态 {'passed': 2568, 'skipped': 3}
- **发布门禁**：`rc=0`、`"passed": true` 计 8 条、`release_ready` true
- **本片新档的读数**：`external_callers` 对 `commit_approved` / `commit_snapshot` 判 HOLDS，正向对照 `record_dxf_lineage` 判 CLAIM_TEXT_ABSENT（探针会开火）
- **`audit_repo --strict`**：`rc=1`，恰 **1** 条 ✗（`✗ Provenance source commit mismatch: manifest=a66040520139… vs HEAD=20`）——设计内不修
- **锚点与哈希面**：`SOURCE_MANIFEST.source_commit` = `a66040520139` == tag；被哈希文件数 `670`（本片**文件数不变**，只改内容）
- **工作树**：`git status --porcelain` 输出 0 行

## 五之二、这一片的收口为什么跑了三遍全量（三条真缺陷，全部已修）

第 69 片的产品改动只花了一半时间，另一半花在**自己的收口机器上**：

1. **在途红被我自己放大。** 第一遍全量里 `test_roster_gap_...` 红（名单缺 2 个文件、
   "报告以来改过的测试文件"只有 1 个）。我以为"再绑一遍就好"，于是把**含红的报告**绑进
   `PROVENANCE` 并提交 —— 结果第二遍全量从 1 条红变成 **4 条**：`terminal_clean` 那一格
   现在读着这份红报告，把 `test_closeout_verifier` 的四条真实语料用例一起拖红。
   已 `git revert` 掉那次绑定。**教训：报告含红就不许进证据链**，宁可多跑一遍。
2. **roster-gap 的基准选错。** 它用"最后一次碰报告文件的提交"当"报告那次提交"。
   revert 会把报告的 touch 点推到代码改动**之后** ⇒ "报告以来改过的文件"算成空集，
   缺口却还在。改成"按报告字节的 sha256 去 `PROVENANCE.json` 历史里找绑定那一次提交"。
3. **把"文件被 touch 过"当成名单缺口。** 名单能观测的只有"树上几条 `def test_`、报告里出现几条"；
   本片把第 68 片两条常驻控制 1:1 换向（条数不变），旧判据照样要求它出现在缺口里 ⇒ 假红。
   改成按 def 条数是否变化，并给这个谓词配了它自己的四条控制
   （`test_helper_only_fires_when_def_counts_move`）；等量改名这种它仍看不见的形状，写进注释不当已证。

终态：干净检出 `f8daa16` 全量 **2568 passed / 3 skipped / 0 failed**，报告已绑定，
两把闸（`closeout_verifier`、`production_release_gate`）在工作树干净时各自 `rc=0`。

## 六、下一片入口

1. `supervisor.fact_writeback → truth_lineage` 的前提**已解除**：现在生产面能写出
   `requirement`/`feature` 记录（本片 CLI）；仍缺的是"把工作项与那条记录对应起来"的键——
   入口在第 69 片之后可以走 `--commit` 之后的 receipt（`committed_truth_refs_json` 已落表）。
2. 第 64 片留的 `doc_command_census` 只报面收窄仍未做；窄档两个手写词表仍无自证。
