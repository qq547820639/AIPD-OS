# 计数叙述 × AST 现读对账（F-PRODUCER-COUNT，第 66 片，2026-09-27）

产物：`scripts/absence_claim_census.py` 加一档 `producer_count` ＋ `tests/test_absence_claim_census.py`
（15 → 19 条常驻用例）＋ `docs/audit/s66/battery66.py`（6 臂电池）。
本片**不加 `aipd` 命令、不加旗子、不加新脚本文件**，所以命令面三张分母与被哈希文件数
只多了 0 个新文件（改的是既有文件的内容 ⇒ 清单要重锚，文件数不变——这条可以拿来反查自己有没有误加文件）。

## 一、起因：同一件事，两个 live 面各说一套数

第 65 片收口时我在 §七 留了一格：「血缘边有几个生产者」这句话有三个互不相同的答案。
本片把它们对到代码上：

| 面 | 原话 | AST 现读 |
| --- | --- | --- |
| `src/aipd_os/registry_data.py`（`product_truth.impact_propagation` 的 `current_limitation`） | 「血缘边的生产者今天**有五个**」 | 8 |
| `docs/architecture/truth_architecture.md:185` | 「血缘边有**三个**生产者」 | 8 |

权威（我亲手用 AST 现读，不是引用）：文件里有 `add_edge` 属性调用 **且** 出现 `LineageGraph`
的共 8 个 —— `cad/spec_lineage.py`、`cad/spec_rework.py`、`cad/dxf_lineage.py`、
`cad/dxf_rework.py`、`bom/cost_lineage.py`、`bom/cost_rework.py`、
`supply_chain/quote_lineage.py`、`product_intelligence/gate.py`。
分档必须分：另有 3 处只写 canonical 的 `dependencies`（`idea/decomposer.py`、
`idea/evidence_relations.py`、`product_intelligence/service.py`），1 处是 `truth_lineage` 的
SQL 写入口自己（`product_truth/lineage.py`）。把 12 个 `add_edge` 位点混成一个数，
就是第 65 片 §七 说的那种"三处叙述各自成立又互相矛盾"。

**原话并不是胡说**：登记表那句下面按 1-5 展开的确实是"创建版本记录"的 5 处，
架构文档那句下面展开的确实是 3 处——**错在把部分展开说成全集**。所以修法不是删句子，
是把数改对并把"本节只展开哪几处"写明。

## 二、机器形状：数字从散文里读，权威从代码里读

账本条目新增一种 `file:` 形式（不再只吃登记表的 capability+field），
`check.kind = producer_count`，`scope ∈ {truth, canonical, sql_entry}`：

1. `locate_claim` 在声明的那个文件里逐字找到锚点，取**那一行**；
2. `slice_sentence` 从锚点起点切到本句末尾（`；。;\n`）——必须切句，否则同一行前一个小句的
   数字会被算在这句账上（B3 臂专打这个）；
3. `count_words` 先剥掉 markdown 的 `*` 再取「有/共/为 + 数字或中文数词 + 个」；
4. `edge_producers` 用 AST 现读权威集；
5. 判决：`写的数 ≠ 现读数` ⇒ `CONTRADICTED`；相等 ⇒ `HOLDS`；
   **权威面建不起来 / 那一档读到空集 / 有盲区 / 句里读不到数** ⇒ `PRECONDITION`（退 2）。

**计数档的优先级与存在档相反**，这是本片最重要的一条形状结论：
存在档里"已经找到那个文件/符号"可以无视别处盲区，因为证据已经到手；
计数档的数**就是从那批位点数出来的**，所以盲区或空集意味着这个数量不出来，
把它折成"句里写错了"就是拿判据造违规——与第 65 片"不把看不见折成合规"是同一条纪律的对偶面。
这条不是推出来的：`test_missing_authority_tree_is_precondition` 第一版就是红的，
红在旧实现把空权威读成了 `CONTRADICTED`。

## 三、被自己的用例教出来的第二处：`*` 不剥就等于在文档面上永不开火

架构文档的强调写法是 `有**三个**生产者`。第一版 `count_words` 不剥 `*` ⇒ 读不到数 ⇒
`PRECONDITION` ⇒ census `rc=2`。这个读数**看起来完全自洽**（"前提不成立"听着很安全），
但那意味着这一面在它唯一要管的文档面上永远不开火，只可能在登记表面上开火。
修法：先 `text.replace("*", "")`。这条教训的形状与第 60 片「`^` 锚点漏 MULTILINE」同族：
**探针恒零的读数不长成"红"，长成"不判"**。

## 四、常驻用例（19 条）与电池（6 臂，杀 6 / 活 0）

新增 4 条：真语料 mis-scope 必须翻红（同一句换 `canonical` 档 ⇒ 8≠3 ⇒ `CONTRADICTED`，
这一条同时是"数不是我在账本里抄的第二份"的机械证明）/ 文档面条目今天成立 /
读不到数退 2 / 权威树不存在退 2。

电池（`docs/audit/s66/battery66.py`，每臂先断言 `old` 恰好命中 1 次、`new` 原本 0 次、
`compile()` 过才落盘，落地后校验 sha 已变，跑靶，`finally` 还原并校验 sha==基线）：

| 臂 | 撤掉什么 | 结果 |
| --- | --- | --- |
| B1 | 空权威/盲区不判那一支 | **KILLED**（self-test + `pytest:missing_authority`） |
| B2 | 不剥 markdown 的 `*` | **KILLED**（self-test + `pytest:document_face`） |
| B3 | 不切句，拿整行取第一个数量词 | **KILLED**（第一版**存活**，见下） |
| B4 | `file:` 锚点那一支 | **KILLED**（self-test + `pytest:document_face`） |
| B5 | 不分 truth / canonical 档 | **KILLED**（self-test + `pytest:count_face`） |
| B6 | 数词表清空（只吃阿拉伯数字） | **KILLED**（self-test） |

**B3 第一版活着的原因是我的夹具不分辨**：`docs/x.md` 每行只装一句话，
切句与不切句读出同一个数 ⇒ 变异确实落地了，但这个位点在两种实现下没有区别
（与记忆 `mutation-landing-proof`／第 58 片 B3 型同族）。
补一行「另有五个说法。血缘边有两个生产者——p1、p2」之后：切句读 2 ⇒ `HOLDS`（真实现），
不切句读 5 ⇒ `CONTRADICTED`（变异体）⇒ 臂立刻死。
这条按纪律记进取证文档：**写反例之前先问"两种实现在这条反例上会不会给出同一个答案"**。

## 五、真语料双向读数（改口前后）

```
$ python scripts/absence_claim_census.py            # 改口前
  ✗ PRODUCER-COUNT-REGISTRY [CONTRADICTED] 锚点 src/aipd_os/registry_data.py:current_limitation:23 | 反证位点 现读 truth 生产者 = 8 个，句里写 5 个、...
  ✗ PRODUCER-COUNT-ARCH     [CONTRADICTED] 锚点 docs/architecture/truth_architecture.md:text:185 | 反证位点 现读 truth 生产者 = 8 个，句里写 3 个、...
rc=4

$ python scripts/absence_claim_census.py            # 改口后（终态）
  ✓ PRODUCER-COUNT-REGISTRY [HOLDS] ... 现读 truth 生产者 = 8 个，句里写 8 个
  ✓ PRODUCER-COUNT-ARCH     [HOLDS] ... 现读 truth 生产者 = 8 个，句里写 8 个
rc=0
```

`--self-test` 17 条合成读数全对上；`pytest tests/test_absence_claim_census.py -q` 19 passed。

## 六、终局读数（占位）

## 七、下一片入口

1. 第 65 片 §七 那格已闭合（原行内已改，不在这里重复）。
2. 账本里还有 **34 句带否定词的句子没挂锚点**（`--json` 的 `sample_unanchored` 与 `corpus` 现读），
   其中"生产 Provider / 依赖外部数据源"这类条件句需要一个新的判据种类（条件式声明），
   不是加锚点就能吃下的——留给有一片专门处理"条件式现状句"的轮次。
3. `supervisor.fact_writeback → truth_lineage` 那格**本片刻意不做**，原因写清楚。
   「没有生产者」这类断言按**生产侧与测试侧各数一遍**才成立：
   生产侧 `src/`+`scripts/` 的全部 `add_work` 调用点（`supervisor.py:743` 的 CLI `add-work`
   与 `supervisor/idea_capabilities.py` 那十处）里，`inputs=` 只带
   `idea_id` / `claim_id` / `tenant_id` / `project_id` / `actor` / `query` / `capability` /
   `gap_reason`，或整份由 `--inputs-json` 手给；测试侧 `tests/` 的 **31 处** `add_work(`
   调用点也是 0 处把 `T-NNN` 放进 inputs（`grep truth_id` 命中的全是
   `rework_tasks` 的字段，不是工作项输入）；
   而 `ExecutionRecord.artifacts` / `evidence_references` 装的是适配器产出的文件路径
   （`document_adapter.py:60`、`local_brep_adapter.py:99`、`supplier_adapter.py:88` 等），
   与 `artifact_version` 记录的 `metadata["path"]`（`cad/dxf_lineage.py:99-108` 的
   `find_artifact_record` 按 (artifact, path) 匹配）**今天不是同一批路径**——
   血缘记录全部由 CLI 命令写（`commands_drawing.py:157,240`、`commands_manufacturing.py:307`、
   `commands_supply.py:117`），没有一个适配器走那条路。
   所以"接一条边"在今天要么靠一个没人写的输入键（造出配置项有、读者为零的假承诺），
   要么靠一个 0 命中的路径 join。真正的入口是先让**某个 producer** 把上游 truth 身份带进工作项，
   这一片没做那个动作，故登记为待做而不是硬做。
4. 第 64 片留的 `doc_command_census` 只报面收窄仍未做。
