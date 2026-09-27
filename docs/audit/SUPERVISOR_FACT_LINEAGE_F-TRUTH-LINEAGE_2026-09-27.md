# 执行证据接进失效传播（F-TRUTH-LINEAGE，第 70 片，2026-09-27）

产物：`src/aipd_os/supervisor/fact_lineage.py`（新模块）、`supervisor.py` 的
`_link_fact_lineage` 挂钩、`tests/test_supervisor_fact_lineage.py`（6 条）、
`docs/audit/s70/battery70.py`（5 臂）、登记表/架构文档/账本/矩阵的同批改口、
`tests/test_drawing_spec_lineage.py` 的 `REGISTERED_PRODUCERS` +1。

## 一、这条缺口挂了多久

第 42 片写下"标签要对应一次真写回"，同时留了这句限制；第 66 片普查说"没有键"；
第 67 片把它记成待做；第 69 片接上 `--commit`，上游记录这才存在；本片连边。
一句话：**四片才把一条 `current_limitation` 关掉**，中间每一片都有实测理由，不是拖着。

## 二、映射与判决

| 来源 | 解析 | 失败时的形状 |
| --- | --- | --- |
| `inputs["truth_refs"]`/`["truth_ids"]` | 逐个 `store.get` 回查 | 查不到的进 `unknown_refs` 原样报出，0 条边但不静默 |
| `inputs["idea_id"]` | `list_snapshots` 挑本 idea 的快照 → `get_commit` 读 `committed_truth_refs_json` | 快照没 commit ⇒ reason 指去 `aipd product gate --commit` |
| 都没有 | — | 0 条边 + "既没有 truth_refs 也没有 idea_id" |

边：`add_edge(upstream=那条 truth 记录, downstream=本次证据, relation="validated_by")`，
只经 `LineageGraph`（`truth_lineage` 的唯一 SQL 入口，环检测在里面）；
自环与环检测拒绝进 `skipped` 并报原因；**连边失败不改判证据步**
（证据已写成，边是另一件事，合并标签会掩盖真问题，标签逻辑仍由
`test_supervisor_fact_writeback.py` 钉着）。

## 三、两条被自己的用例抓出来的实现错

1. `get_commit` 返回的是**表行**（列名 `committed_truth_refs_json`），我按 receipt 形状读 `committed`
   ⇒ idea 路径永远解析成 0，而"解析成 0"和"真的没有上游"在读数上同形——这类 bug 不报错，
   只有把两种情况分开钉的用例会红。
2. `edges` 数的是调用次数，而 `add_edge` 是 `INSERT OR IGNORE` ⇒ 重放谎报"又连上了"。
   改成数前后行数之差，并额外报 `total_for_this_evidence`。

## 四、判据抓到自己人

新模块写边 ⇒ AST 现读的血缘生产者 8 → 9，第 66 片那两条 `producer_count` 登记**当场翻红**
（登记表一条、架构文档一条）。两句就地改 9，并写明第 9 处是谁。
这条值得记：判据的价值不在平时绿，而在你改实现的那一轮自动拦住"数没跟上"。

## 五、终局读数（由 `docs/audit/s70/terminal70.py` 从原件现跑生成，不手抄）

- **签出那一跑**（`tmp/s70/final`，报告产出于提交 `5efd9f2`，主树当时 HEAD `7fe4407`）：`exitcode=0`、`collected=2577`、`passed=2574`、`skipped=3`、其余终态 `{'skipped': 3}`、用时 `483.7s`、`root=/Volumes/Extra/CodeProj/AI全链路自研/tmp/s70/final`、`source_commit=a66040520139`
- **本片主角（真仓库终态）**：`rc=0`；语料：84 个能力，带否定词的句子 36 句；账本登记 12 条，未挂锚点 29 句（宽档，只报不判）；能力缺失句（窄档＝判据面）：16 句 = 登记 6 + 豁免 10 + **未处置 0**；判红 0 条：登记的 12 句「仍缺着」现在都还缺着
- **`--self-test`**：`rc=0`，**23 条**合成读数全对上（含存在式登记、去处台账与 `table_ddl` 双向）
- **常驻用例**：`pytest tests/test_supervisor_fact_lineage.py tests/test_absence_claim_census.py -q` → `32 passed, 24 warnings in 14.91s`（rc=0）
- **变异电池（入库副本现跑）**：`docs/audit/s70/battery70.py` → `rc=0`，合计 KILLED 5 / 其余 0
- **两档分母现读**：宽档 36 句、窄档 16 句（差 20 句是谈判决/谈口径的假阳性）；登记表解析问题 `[]`；薄理由豁免 `[]`
- **第 64 片那台收尾验签在本片树上**：`rc=0`；收尾验签（报告 ↔ 证据 ↔ 工作树）；读数：报告 2577 条 / 210 个文件，树 210 个文件 / 2494 个 def，终态 {'passed': 2574, 'skipped': 3}
- **发布门禁**：`rc=0`、`"passed": true` 计 8 条、`release_ready` true
- **本片新档的读数**：`external_callers` 对 `commit_approved` / `commit_snapshot` 判 `HOLDS`（生产面外部调用点分别为 1 / 0 处，"外部"口径把同文件的兼容包装排除在外）；正向对照 `record_dxf_lineage` 判 `CONTRADICTED`（同一函数换个名字就翻红 ⇒ 探针会开火）。**更正记录**：这一行最初由 `terminal70.py` 生成时用了改口前的旧锚点，读出来是 `CLAIM_TEXT_ABSENT`（账文脱钩）而不是 `CONTRADICTED`（过期）——读数本身把脚本的错暴露了，脚本已改、这一行按实测重写。
- **`audit_repo --strict`**：`rc=1`，恰 **1** 条 ✗（`✗ Provenance source commit mismatch: manifest=a66040520139… vs HEAD=7f`）——设计内不修
- **锚点与哈希面**：`SOURCE_MANIFEST.source_commit` = `a66040520139` == tag；被哈希文件数 `672`（本片**文件数不变**，只改内容）
- **工作树**：`git status --porcelain` 输出 0 行

## 五之二、这一片的两次返工（都是我自己的错，被机器拦下）

1. **`git add` 漏了 `docs/architecture`。** 我在那篇里把生产者计数从 8 改到 9，却没提交：
   干净检出读到旧文本 ⇒ 第 66 片那两条 `producer_count` 判"账文脱钩"；
   而清单哈希是在**含着未提交改动的树**上重算的 ⇒ `test_*_manifest_hashes_match_disk` 两条一起红。
   一次全量暴露 5 条红。修：补提交 + 重算清单（`5efd9f2`）。
   固定处置已进记忆：提交前看 `git status --short`，提交后用 `git show --stat` 跟"我改过哪些文件"逐条比。
2. **新模块 docstring 写了不存在的命令** `aipd supervisor add-work`
   （真入口是 `python scripts/aipd_supervisor.py add-work`）。第 60 片那把 `doc_command_census`
   的判红面 ③ 当场点名 —— 这正是我上一片写进记忆的同一格（"新代码里不许写 `aipd <幻影>`"），
   还是犯了：说明那条纪律得靠闸拦而不是靠我记，而它确实拦住了。

终态：干净检出 `5efd9f2` 全量 **2574 passed / 3 skipped / 0 failed**，报告已绑定。

## 六、下一片入口

1. 证据这一类现在能被传播标 stale，但**返工执行器不认 `evidence`** ⇒ 任务停在"点名拒、不烧 attempts"。
   要么给它一个执行器（重跑那次 run），要么把这类任务显式标成"只能人处置"——今天两处文案都没说清。
2. 第 64 片留的 `doc_command_census` 只报面收窄；窄档两个手写词表的自证（第 67 片起挂着）。
