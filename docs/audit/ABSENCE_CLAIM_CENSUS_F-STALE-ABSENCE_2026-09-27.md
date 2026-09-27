# 登记表否定句 × 反证锚点对账（F-STALE-ABSENCE，第 65 片，2026-09-27）

产物：`scripts/absence_claim_census.py`（42 号常驻件）＋ `tests/test_absence_claim_census.py`。
本片**不加 `aipd` 命令、不加旗子**，所以 74 条注册命令 / 64 条 PUBLIC 契约 / 90 条 argparse 路径
三张分母都不动；动的是登记表本身（7 行过期话）与"谁来发现过期话"这件事。

## 一、起因：一句漂了 12 片的假话

`industrialize.quote_to_bom_cost` 的 `current_limitation` 今天还写着：

> 成本结论已有返工执行器（第 49 片…），**BOM 版本记录仍没有**：那一条要收口还是得手工再跑一次 cost calc --truth-lineage

而第 53 片已经把 BOM 版本记录的返工执行器接上了：`src/aipd_os/bom/bom_rework.py:32`
定义 `SUPPORTED_ARTIFACT = ARTIFACT_BOM`，`src/aipd_os/cli/commands_truth.py:188-195`
的 `run_executor` 里有 `if kind == BOM_ARTIFACT: return rework_bom_artifact(...)`。
**同一张登记表的另一行（`product_truth.impact_propagation`）早就把这一格写成"四类制品"**——
也就是说这一份自相矛盾同时存在于文件内与文件外，读者按哪一行决定下一片做什么，结论相反。

第 53 片的项目记忆里就记着这条纪律：「凡是"某类没有 X"的否定句，接上 X 的那一轮必须 grep 到它
并原地改」。那一轮改了 README 与 registry 的一部分，漏了这一句；第 54 片靠 grep 抓到过一次同族。
**两次都靠人**，所以这一片交给机器。

## 二、判据形状：一条登记 = 原话 + 反证锚点，四档判决

| 档 | 什么时候出 | 后果 |
| --- | --- | --- |
| `HOLDS` | 原话在声明它的那个 (能力 id, 字段) 里逐字找得到，且反证锚点**不在** | 绿 |
| `CONTRADICTED` | 原话在，反证锚点**在**（带出 `文件:行`） | 判红（退 4） |
| `CLAIM_TEXT_ABSENT` | 账本里有这条，登记表里已经没有这句原话 | 判红（退 4）——"删句不删账" |
| `PRECONDITION` | 反证锚点**解析不出来**（一跳 import 的常量指不到模块） | 退 2，绝不折算成 `HOLDS` |

三种锚点种类，每种都在真仓库里有活的双向对照：

- `artifact_executor`：扫 `src/**` 的模块级 `SUPPORTED_ARTIFACT = …`（字面量或一跳常量）。
  现读全表：`bom → src/aipd_os/bom/bom_rework.py:32`、`bom_cost → src/aipd_os/bom/cost_rework.py:37`、
  `drawing_dxf → src/aipd_os/cad/dxf_rework.py:45`、`drawing_spec → src/aipd_os/cad/spec_lineage.py:32`，
  盲区 0 处。`quote_batch` 不在表里 ⇒ 「quote_batch 仍没有执行器」这句今天成立。
- `identifier`：AST 面上的标识符引用（`Name`/`Attribute`/`def`/`class`/import 名），
  **不走文本**。这条是硬要求：这些否定句自己就要在注释里写「不做 X」，
  文本扫描会把"写清楚了没做"读成"做了"（第 45 片 `run_rework` 那条判据同一条理由）。
  实测面差异见 §四 第 3 条。
- 锚点绑 **(capability, field)** 不绑全文：登记表里有五条 `product.*` 行的 provider 描述**逐字相同**，
  只按子串找会一条改完、五条读成都改完（`test_anchor_bound_to_the_wrong_capability_does_not_pass` 钉这条）。

**散文面只报不红**，并报出「登记了几条 / 还有几条没登记」。实测把 15 个否定词打进登记表
命中 48 句（现算值，本文不抄成契约），其中大量是合法写法：
「不静默退回『没有基线』」「所以『没有执行器』不会被伪装成返工失败三次」「一张单都没有时整格
`undetermined`」——判红面一宽就会惩罚"把缺口写下来"这件事，与第 60 片只报面同一条理由。

退码 0 / 4 / 2 沿用本仓形状；空账本、登记表读不出、锚点解析不出都是前提塌。

## 三、选型四段（原件本轮重开，读数由我亲手取）

| 候选 | 功能匹配度 | License | 维护活跃 | 安全 | 代码质量 | 适配成本 |
| --- | --- | --- | --- | --- | --- | --- |
| `doorstop@3.2`（github.com/doorstop-dev/doorstop） | 判定单元是「一条需求＝一个 YAML item + `links:`」，`doorstop link/validate` 查**断链**；对"中文否定句 + AST 反证"匹配度＝只借判决形状 | PyPI `license` 字段实测 **LGPLv3** | 最新发版 **2026-07-10**（PyPI `releases` 现读） | GHSA `affects=doorstop` → **0 条**；同端点 `affects=pygments` 实测回 5 条且包名字段正确 ⇒ 这条 0 是判据在管，不是过滤器失效（`affected_package=` 那个写法会被静默忽略并返回未过滤清单，本轮第一次就踩了） | README 顶部挂 Linux/macOS/Windows 三平台 CI + codecov + CII Best Practices 徽章（本轮重开所见） | 要把 84 行能力登记改写成 item 目录，且它没有否定语义 |
| `pytest-doctestplus@1.7.1` / 标准库 `doctest` | **0**：要求正文里是可执行 Python，中文否定句不可执行 | BSD / 标准库 | 1.7.1 发版 2026-01-26 | 未单独检索（记未检索） | 活跃插件、随 pytest | 需给登记表加可执行示例面 |
| `verdoc@1.0.2` | 0（把代码片段插进文档） | LGPLv2+ | 停在 **2021-06-14** ⇒ 不活跃 | 未检索 | — | — |
| 扩写第 60 片 `doc_command_census.py` | 它判"点名的命令注册着"，我判"承诺的缺口还缺着"，语料同为登记表 | 本仓 MIT | — | — | 复用已实测的三档面/0-4-2/自测形状 | 一张判据两种语义，退码与只报面都会互相遮蔽 |
| `scriv@1.8.0`（Apache-2.0） | **不相关**（changelog 工具）——列出以免只挑好讲的 | | | | | |

**择一：借语义、不引依赖。** 借 doorstop 的「引用必须落得住，悬空即判错」，
借 doctest 的「断言要住在正文旁边」；不引依赖的理由是两条硬约束——
运行时零网络依赖，以及登记面是 Python 常量而不是 item 文件树。
**明确否掉**"塞进 `doc_command_census.py`"：那会把两个不同问题压进同一张退码表。
未检索到"文档里的缺席承诺 vs 代码现状"这一轴上的现成工具（搜 traceability / stale docs /
assertion-in-prose 命中的是需求管理族与 doctest 族），如实记为未找到第二候选同类。

## 四、三处形状是被跑教出来的，不是推的

1. **盲区会越权推翻判决**。第一版把「有前提问题」排在「反证锚点已在」之前，于是
   `scripts` 里一个无关模块的一跳解析失败，把**所有** `artifact_executor` 判决压成
   `PRECONDITION`——self-test 合规臂第一轮就不绿（`FIRED` 读成 `PRECONDITION`）。
   改后规则：拿到证据的判决优先；盲区只在"本应读成 HOLDS"时才有资格改判，
   并在 `CONTRADICTED` 行里报出盲区处数（不改判决也要让读者看见）。
2. **Python 3.9 的 `ast.alias` 没有 `lineno`**，import 引用被读成 `runtime.py:0`——
   一个看起来自洽的假位点。改成在 `Import`/`ImportFrom` 语句层面收号。
3. **`--self-test` 的 stdout 里没有四档判决的档名**，只有 `✓立住` 叙述。
   常驻用例如果按 `[PRECONDITION]` 断言就会红而看不出为什么——补一行 `render(rep)`，
   让"四种判决真各走过一次"这件事在输出上可断言，而不是靠我口头保证。

## 五、抓到的过期话（开尺当天读数，判红面在真登记表上第一次开火）

```
$ .venv/bin/python scripts/absence_claim_census.py --claims /Volumes/Extra/CodeProj/AI全链路自研/tmp/s65/before_claims.json
语料：84 个能力，带否定词的句子 48 句；账本登记 3 条，未挂锚点 38 句（只报，不判红）
  ✗ REWORK-EXECUTOR-BOM [CONTRADICTED] 锚点 current_limitation:71 | 反证位点 src/aipd_os/bom/bom_rework.py:32
  ✗ REWORK-EXECUTOR-SCOPE [CONTRADICTED] 锚点 current_limitation:77 | 反证位点 src/aipd_os/cad/dxf_rework.py:45
  ✗ PRODUCT-PROVIDER-UNWIRED [CONTRADICTED] 锚点 current_limitation:90 | 反证位点 src/aipd_os/llm/product_intelligence_provider.py:68、src/aipd_os/runtime.py:0、src/aipd_os/runtime.py:343
rc=4
```

第三行的位点里有 `runtime.py:0`——那是 §四 第 2 条那个 `lineno` 缺陷的现场，
修好后同一位点是 import 语句行与装配行两处。**读数本身在修前修后同向**（这句话确实被证伪）。

三条锚点覆盖 **7 行**登记表：`industrialize.quote_to_bom_cost`、`industrialize.physical_writeback`、
以及 `product.derive_insights` / `product.identify_opportunity` / `product.derive_principles` /
`product.derive_requirements` / `product.derive_features`（同一句「生产 Provider 未接入」逐字出现 5 次）。
第 5 条的真相由 `src/aipd_os/runtime.py:343-344` 与
`src/aipd_os/tool_adapters/product_adapters.py:396-400` 共同给出：配了
`AIPD_MODEL_API_KEY` + `AIPD_MODEL_BASE_URL` 时 `LlmProductIntelligenceProvider` 被装配并注入这五个
adapter——所以「未接入」是低报，准确说法是"只有 LLM 这一家，不配模型就没有"。

`research.fulltext_fetch` 那句按**窄法**改写而不是删掉：库里 `src/aipd_os/research/fulltext.py`
确实有 `fetch_fulltext`/`classify_text`（本轮重开），但 `scripts/research/` 里 0 处引用——
「各连接器当前仅取摘要」是真的，「未实现全文获取」是低报。账本里那条锚点因此取前者，
反证位点取**连接器目录**（取在库里会把自己判红）。

## 六、常驻牙与电池

**散文面分母的现算值**：开尺当天（三句过期话还在登记表上）`corpus.absence_sentences` = **48**，
本轮修完是 **37**，未挂锚点 **34**。两个数都由 `--json` 现算，本文只记当轮读数，
不把它当契约抄（`--self-test` 与常驻用例钉的是下界，不是等号）。

### 常驻牙（`tests/test_absence_claim_census.py`，15 条）

`--self-test` 被真 spawn 且 stdout 里四档档名齐备 / 真仓库上内置账本全 `HOLDS` 且分母非空
（84 能力、否定句 ≥30、未挂锚点 ≥20——覆盖率读数本身要可见）/ 每条登记的锚点都落在
**声明它的那个文件与字段**上（`文件:字段:行` 三段可拆）/ 两份登记表对同一 id 各说各话 ⇒
自己退 4（合规侧同批存在：`product.*` 七行今天两处逐字相同）/ 真语料上的永久判红对照
（`--claims` 换账本，锚点用今天仍成立的「跨币种折算未实现」，反证位点故意取 `cad` 里真在的
`LineageGraph`）/ 真语料上的永久判红对照之二（第 65 片真删掉的三句原话 ⇒ `CLAIM_TEXT_ABSENT`）/
锚点绑错能力行 ⇒ 不许借全文子串蒙过（反证：同一锚点绑回它真正所在行就翻成 `CONTRADICTED`）/
五条 `product.*` 行逐字同句 ⇒ 数到 5 / 只走 AST 不走文本（注释里写「不做 LineageGraph」不算引用）/
一跳解析不到 ⇒ 前提不成立且退 2 / 量具与它的用例不进任何分母 / README 行首镜像。

### 变异电池（11 臂，杀 11 / 活 0 / 锚点或落地问题 0）

跑法：`/Volumes/Extra/CodeProj/AI全链路自研/tmp/s65/battery65.py`（每臂先断言 `old` 命中恰好 1 次、
`new` 原本 0 次，落地后校验 sha 已变，跑靶，`finally` 还原并再校验 sha==基线 `32e8378ee394`）。

| 臂 | 撤掉什么 | 结果 | 开火的靶 |
| --- | --- | --- | --- |
| A1 | `locate` 放宽成全文子串找 | **KILLED** | `pytest:wrong_capability`（前提断言先红，见下） |
| A2 | 把 present 那一支挪到盲区之后（第 65 片真犯的耦合） | **KILLED** | self-test（`FIRED` 读成 `PRECONDITION`） |
| A3 | 盲区折成 `HOLDS` | **KILLED** | self-test + `pytest:precondition` |
| A4 | AST 面退化成逐行文本 | **KILLED** | `pytest:comment_only`（`m.py:2` 假命中） |
| A5 | 找不到锚点就跳过 | **KILLED** | self-test + `pytest:dangling` |
| A6 | 空账本不判前提 | **KILLED** | self-test（"空账本不许读成零违规"） |
| A7 | 不做一跳常量解析 | **KILLED** | self-test（真语料那条 `--claims` 探针 **rc=0**，见"未证实"） |
| A8 | `judged` 里去掉 `CLAIM_TEXT_ABSENT` | **KILLED** | self-test + `pytest:dangling` |
| A9 | 扫描面不再排除量具自身 | **KILLED** | `pytest:instrument_and_its` |
| A10 | 去掉 `duplicate_divergence` 那一面 | **KILLED** | self-test + `pytest:divergent` |
| A11 | 读数不带文件名 | **KILLED** | `pytest:every_claim`（三段拆不开） |

**A1 第一轮活过**：我的对抗夹具写的是加了前缀的「这句话只属于别的行：生产 Provider…」，
于是"放宽成全文子串找"与"不放宽"读出同一个 `CLAIM_TEXT_ABSENT`——**夹具太独特，判据放宽也抓不到**。
换成逐字取自另一行的原话（「跨币种折算未实现」绑到 `supervisor.fact_writeback`）之后才杀掉，
并补了一条反证（同一锚点绑回它真正所在行 ⇒ `CONTRADICTED`）。这是"空改写永远绿"的又一实例
（见记忆 `mutation-landing-proof`：对照前先数 `old==1` 且 `new==0`，并怀疑自己的反例不够像）。

**未证实（两条，都属机制而非本轮没做完）**：
① A7 臂在真语料上的 `--claims` 探针没有开火（`rc=0`）——那条探针用 `identifier` 锚点，
不经过一跳解析那一支；一跳解析这一支的牙今天只由合成臂与 `bom`/`bom_cost` 的现读全表撑着。
② "登记表里每句否定句都该被登记"无法机器判定：反证锚点是人给的语义映射，
覆盖率只能报数不能判红——所以 34 句未挂锚点是**明写的待挑清单**（`--json` 的 `sample_unanchored`），
不是绿。

## 七、下一片的入口（本片不留待裁项）

1. `supervisor.fact_writeback` 那条 `SUPERVISOR-TRUTH-MAPPING` 登记今天仍成立；接上它的那一轮
   要把这条账本条目一起删（不删就 `CLAIM_TEXT_ABSENT` 响，这是刻意的）。
2. **血缘边的"有几个生产者"三个面各说各话**（本轮我亲手数过，不是引用）：
   `docs/architecture/truth_architecture.md:185` 写「血缘边有**三个**生产者」；
   `registry_data.py` 的 `product_truth.impact_propagation` 那行写「血缘边的生产者今天有**五个**」；
   我自己按 AST 数 `x.add_edge(` 在 `src/` 下命中 **12 个文件**（含 `product_truth/lineage.py` 自身
   与三处写 canonical 的 `idea/decomposer.py`、`idea/evidence_relations.py`、
   `product_intelligence/service.py`）。权威应是 `tests/test_drawing_spec_lineage.py:200`
   的 `REGISTERED_PRODUCERS`（AST 双向棘轮），下一片按它现读统一这三处叙述。
   这正是本片那把尺子的形状能管到、但**账本还没登记**的一类（"三个生产者"里没有否定词，
   所以不进 37 句的分母）——记在这里，不假装机器已经覆盖。
3. 第 64 片留的 `doc_command_census` 只报面收窄（把 `tests/` 挡在语料外 + 单开"记录性引述"一桶）仍未做。


## 八、终局读数（占位）

（本节由 `tmp/s65/terminal65.py` 从原件现跑替换，写之前先过"取不到读数就整轮拒写"那道闸。）
