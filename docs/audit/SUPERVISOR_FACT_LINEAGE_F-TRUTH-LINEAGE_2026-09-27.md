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

## 五、终局读数（占位）

## 六、下一片入口

1. 证据这一类现在能被传播标 stale，但**返工执行器不认 `evidence`** ⇒ 任务停在"点名拒、不烧 attempts"。
   要么给它一个执行器（重跑那次 run），要么把这类任务显式标成"只能人处置"——今天两处文案都没说清。
2. 第 64 片留的 `doc_command_census` 只报面收窄；窄档两个手写词表的自证（第 67 片起挂着）。
