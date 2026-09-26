# F-DRIFT-2 第 52 片：报价批次的漂移键改由「库里的事实」投影，出图漂移补真库端到端断言

日期：2026-09-26 ｜ 分支树：本轮工作树（HEAD 起点 `c37a501`，第 51 片收尾）
本轮**不做新的外部检索**（诚信要求下的跳过）：判据形状沿用第 46 片（按输入签名认身份）、
第 48 片（记录要存口径值才重建得出来）、第 50 片（连不上下游也要点名）这三条已定规矩，
本轮唯一的裁决是「这把键该从哪个对象重算」，而它由本轮读到的代码事实决定，不由候选清单决定。
读过的出处（本轮逐行打开过）：`supply_chain/persistence.py:14-22,69-95`、
`supply_chain/apply.py:100-133`、`cli/commands_supply.py:52-110`、
`cad/dxf_lineage.py:70-80`。

## 一、第 51 片留下的两格，本轮各自读到什么

第 51 片 §六 自记两格缺口：

1. **`drawing_dxf` 那支 resolver 没有真库端到端断言**——四类 resolver 里只有它此前
   全靠合成记录（`metadata` 手搓）验。本轮补上：CTQ → `drawing spec` → `drawing generate`
   → 扫一条**真记录**判「一致」→ 改声明文件里的公差 → 同一支 resolver 判「漂移」。
   这条同时是第 46 片「签名要吃全出图输入」的**独立回归**：第 46 片那批用例盯的是
   「另起新版」，这里盯的是「能不能被发现」，签名漏吃一项时那批全绿而这条会红
   （电池 R6 实测：注入「签名不吃声明哈希」正是这两条一起红）。
2. **`quote_batch` 没有 resolver**——登记时留的话是「这一类制品还没接漂移探测器」，
   属于诚实的不可判，但那格到底能不能接，第 51 片没读到证据就挂着。

## 二、第二格的裁决：这把键**不能**从报价文件重算，只能从库里的事实投影

先把「照 `drawing_spec` 那支的样子，记路径、回来重算」这条最自然的做法读到不成立：

- `quote apply` 喂进签名的行不是文件行。`cli/commands_supply.py:64-74` 先把每条报价
  交给 `assign_quote_versions(...)`，**`quote_id` 与 `version` 是那时按库内当前官方版现铸的**
  （`quote_id = f"{supplier}-{part}-v{version}"`）；文件里根本没有这两样。
  ⇒ 重解析文件得不到同一把键，只能得到"另一批东西"。
- 反向映射（事实态 → 文件态）有损。`persistence.py:20` 是
  `_QUOTE_FACT_STATUS = {"official": "V", "superseded": "R", "draft": "P"}` 再配
  `.get(status, "P")`——任何没列进去的文件态都塌成 `P`。
  ⇒ 拿反查做键，会把「映射不一致」冒充成「漂了」，而假红在漂移工具里比不可判更贵。

真正该问的是：**哪一项是会变的？** 答案反过来决定了键必须建在哪：
文件里的 `official` 是解析观测，**它永远不会自己变**；
会变的只有库里的事实态——`apply.py:107-133` 的 `retire_stale_officials` 把
不再是当前官方版的 `V` 改成 `R`。
⇒ **按文件态算键的那把尺子是恒真的**：第 50 片想抓的那件事（「价换过了，
  当初据以定价的那版 BOM 还挂着 active」）在这把键下永远读不出来。

裁决（三选一，择一写明）：
① 不接（保持诚实不可判）——被否，上面那格本来就该有闸；
② 按文件/路径重算——被否，两条代码事实直接反驳；
③ **键的行只由「库里当前的报价事实」投影出来，生产侧与扫描侧共用同一份投影**——选定。
代价：登记侧的签名基准换了（`official` → `V`），记录 content 跟着变；
旧基准那批记录不许换基准重算 ⇒ 用 `metadata.rows_from = "fact_status"` 标出来，
没有这一格的记录判**不可判 + 点名原因**（与第 48 片「口径五项没记」同一处理方式）。

## 三、实现

- `supply_chain/quote_lineage.py` 新增 `quote_applied_rows(facts, *, currency, quote_ids)`
  与 `missing_quote_facts(...)`：唯一的投影，产 7 个字段
  （quote_id / supplier / part / version / status=**事实态字母** / unit_price / currency）。
  `record_quote_lineage` 多写一格 `rows_from`。
- `cli/commands_supply.py`：登记侧改为**在落库与 retire 之后**读回事实做投影，
  并加一条前提：读回的行数必须等于本批 quote_id 数，少一行就判未收口
  （`lineage_error` + `ok=False` + 退 4），不许写一条「少算几笔报价」的记录。
- `cli/commands_drift.py` 新增第五支 `_quote_resolver(db, project, tenant)`：
  老基准 / 没 quote_ids / 没币种 / 事实读不回 ⇒ 四种「不可判」各自点名；
  其余一律 `quote_input_signature(当前投影)` 与记录里存的那份比。
  顺带把 `build_resolvers` 的 tenant 打通（原来 BOM 那两支硬写 `DEFAULT_TENANT`，
  而 `--tenant` 能传进扫描 ⇒ 传非默认租户时 BOM 侧会读错归属，本轮一并修）。

## 四、效力证明（电池 `/tmp/s52/battery.py`，7/7 杀掉，一臂一原告）

对照臂（未注入）rc=0 先行。还原一律写回注入前读到的原文。

| 臂 | 注入 | 原告 |
|---|---|---|
| R1 | 投影把 status 冻成 `"V"` | `test_a_later_quote_retiring_the_batch_is_discovered_by_the_scan` |
| R2 | 扫描侧投影少传币种（两侧各写一遍映射的病灶） | `test_quote_key_is_recomputable_from_the_library_alone` |
| R3 | 去掉 `rows_from` 老基准判据 | `test_quote_record_on_the_old_file_status_basis_is_undecidable` |
| R4 | 去掉「事实读不回」判据 | `test_quote_record_naming_vanished_facts_is_undecidable` |
| R5 | 去掉登记侧行数前提 | `test_a_quote_fact_that_will_not_read_back_holds_the_command` |
| R6 | 出图签名不吃声明哈希 | `test_generated_drawing_drift_is_discovered_on_a_real_record` + `test_signature_covers_every_declared_input` |
| R7 | 只读扫描照旧构造 `BomStore`（没库就顺手建一个） | `test_scan_does_not_create_a_bom_store_when_the_sidecar_is_gone` |

R1/R2 是这片真正的两条新闸：**冻动态**（①的失效形状）与**两侧各写一遍**（②的失效形状）。
R6 半径 2 属正确——同一条判据（签名吃不吃声明）由第 46 片的单位级用例与第 52 片的
端到端用例共同拥有，两个原告都合法。

## 五、本轮自记（两处本轮改掉的东西，都不是"顺手"）

- **R7 那格是真库副本撞出来的**：第一次在 `/tmp/s50/state.db` 的副本上跑，
  `bom`/`bom_cost` 从第 51 片记录的「漂移 2」变成了「不可判 · 项目当前没有 BOM 头」。
  先怀疑自己的代码，读 `bom/store.py:83-89` 才看清两件事叠在一起：
  ① 我复制时只带了 `state.db`，同目录的 `bom.db` 没带（**读数的一部分是我的夹具**，
  不能算进代码的账）；② 但 `BomStore.__init__` 会建库建表，
  于是那次只读扫描**在只该读的地方造出了一个文件**——模块 docstring 自己写着
  「只读消费方在构造之前还得先确认该文件存在」，第 51 片的 resolver 没遵守。
  修法与断言一起落（见 R7）：判据改成先 `is_file()`，缺库点名「同目录没有 BOM 库文件」，
  用例同时断言扫完之后那个文件**仍然不存在**。
- §一 初稿把缺口写成「四类 resolver 都缺真库端到端断言」，范围过大：
  实际只有 `drawing_dxf` 一支缺，另外三支第 51 片就有真记录用例。已按读到的用例正文收窄。
- `quote_applied_rows` 与旧的內联推导**没有**抽成"两边各自复刻"：投影只有一份，
  这本身就是 R2 那条注入能被抓住的前提。若将来有人为了「让某条对照单独开火」而复刻它，
  要连带把 R2 换成不对称的两份投影才行——先问谁拥有这条对照。

## 六、真库读数（第 50 片留下的 `/tmp/s50/state.db` 副本，项目 `D50`）

带齐 `state.db` + `bom.db` 之后，按本片代码依次跑两次 `quote apply --truth-lineage`
（p1 单价 13.9，p2 单价 21.5）再扫：

```
扫描 5 条：一致 1、漂移 3、不可判 1、没有可比对的键 0   （rc=4）
should_be_stale：T-004（quote_batch，仍 active）
  0eb6eaee62ee879f → 4ec59c5593f0ba23
不可判：T-003（quote_batch）「当初按报价文件里的态算键（第 50 片）……不许换基准重算」
```

三格各说一句：`T-004` 是 p1 那批——p2 落库后 `retire_stale_officials` 把它那笔事实
从 `V` 改成 `R`（两次 apply 的 `retired_facts` 字段各自可查），**这就是第 50 片想要、
而按文件态永远看不见的这一格**；`T-005`（p2 自己）读成一致，证明登记与扫描同源；
`T-003` 是旧基准那条，落「不可判 + 点名」而不是被换成新基准重算。
`T-001`/`T-002`（bom/bom_cost）在这份副本上已挂着 stale，所以进 `drifted` 而不进
`should_be_stale`（那一栏只收 active，第 51 片定的一条）。

## 七、遗留（本轮不做，接第 51 片 §六）

- `artifact=bom` 仍无返工执行器：漂移能发现，`truth rework` 到得了的那类仍只有三种制品。
- 扫描 ≠ 触发：发现漂移之后要不要 `truth propagate` 仍靠人；把「漂移清单 → 建返工任务」
  接起来是下一格。
- 存量开发库的真实漂移半径仍未测（`data/state.db` 本轮同样未打开）。
- **本轮改了 `quote_batch` 的签名基准**：任何第 50~51 片期间写下的报价批次记录，
  在新代码下都会落「不可判（第 50 片按文件态算的键）」而不是被重算——这是刻意的，
  但它意味着旧库里的报价边不会自动获得漂移覆盖，要重新 `quote apply --truth-lineage` 一次。

## 终读数

@@FINAL@@


