# F-LINEAGE-COST 第 48 片：给「BOM 版本 → 成本结论」补血缘生产者

日期：2026-09-26　　轮次：第 48 片　　依据登记：`industrialize.quote_to_bom_cost`、`product_truth.impact_propagation`

## 一、改前事实（这一段为什么断着）

- 成本结论今天只写进 `facts` 表的 `cost.total`，`conditions` 是一句
  `bom=BOM-001 qty=1000 tooling=50000.0 nre=1000.0 margin=20.0%` 的**拼串**
  （`src/aipd_os/cli/commands_manufacturing.py`，`cost calc` 的写回块）。
  拼串不是键：改一行 BOM 之后，旧的那句 `conditions` 与新 BOM 之间在库里连不上。
- AST 普查 `add_edge` 调用点：本片之前 `bom/` 与 `supply_chain/` 两个目录里**一处都没有**
  （收口时同一条普查读到 11 处，全部已登记，见 §六）。
  ⇒ 「改了 BOM，那笔成本还是不是它算出来的」在库里问不出来，`aipd truth propagate` 也打不到成本结论。
- 对照：同一条链的前三跳（CTQ → 图纸声明 → DXF 制品）已在第 43/45/46/47 片接上。
  这一支是当时点名的缺口，登记里原话是「BOM/成本那一支仍没有血缘生产者」。

## 二、技术选型：为什么这一片没有外部检索

按例外条款明写跳过理由：**这不是一个新的技术决策**。制品按什么认身份，本仓已经有两轮实读文档的取证：

- 第 45 片 `docs/audit/TRUTH_REWORK_F-REWORK_2026-09-26.md` 读了 **dbt `state:modified`**
  （node-selection 文档：拿当前节点签名与 `--state` 指的上一份 manifest 比才判「变了」，
  纯 cosmetic 字段刻意不算变更）与 **BitBake / Yocto concepts**（输入校验和汇成签名，
  `STAMPS_DIR` 里有签名匹配的戳文件才跳过执行）；
- 第 46 片 `docs/audit/DRAWING_DXF_LINEAGE_F-LINEAGE-DXF_2026-09-26.md` 在
  「按输出字节哈希 / Bazel action key / Reproducible Builds 抹时间戳后比字节 / Nix fixed-output」
  四个候选里选了 **Bazel 式动作键**（Nix 那条当时未读到，登记为不引用），
  并用实测否掉了按字节（同输入两份 `.dxf` 13170 行只差 2 行时间戳）。

⇒ 结论「**按输入签名认身份、不按产物字节**」在两轮之前已经定了，本片只是把这条已定判据
套到第二种制品上。唯一的新问题是「BOM 与成本的输入集合各包含什么」——
答案在本仓代码里（`CostInputs` 的五个字段、`BOMLine` 的行事实），不在外部生态里。
所以本片**没有做新的外部检索**，也没有查阅任何未实际访问的项目或文档。

（自查记录：本节初稿把 dbt 与 BitBake 记成了「第 46 片对照过的三项」——那是错的归因，
这两个来源属第 45 片，第 46 片的表里根本没有它们。落盘后跨文件复grep 才发现，就地改成本节这样。）

签名集合（照第 46 片的教训：先写全再撞键复现，见 §五）：

- `bom` 那条：`bom_id` / `revision` / `version_no` + 每条参与行的事实
  （件号、数量、单位、材料、供应商、单价、币种、状态）。
- `bom_cost` 那条：**上面整个 BOM 签名** + 口径五项
  `tooling_fee` / `target_quantity` / `amortize_over` / `nre` / `margin_pct`。

## 三、做法

新增 `src/aipd_os/bom/cost_lineage.py`：`record_cost_lineage(store, header=…, lines=…, inputs=…, cost=…, …)`

1. 按 BOM 签名找 `artifact=bom` 的有效记录：命中则复用（`created=False`），否则新写一条
   `artifact_version` 并把同作用域上一条标 `superseded`；
2. 按成本签名对 `artifact=bom_cost` 做同样的事；
3. 连 `bom → cost` 的 `affects` 边；
4. `header is None` 或 `lines` 为空 ⇒ **什么都不写**（空 BOM 不该留下一对「有效但无来源」的记录）；
5. 返回 `{written, reason, records, edges, bom, cost, bom_signature, cost_signature}`。

接线 `src/aipd_os/cli/commands_manufacturing.py`：`aipd cost calc` 新增旗子 `--truth-lineage`（`cli/main.py`）。

- 不给旗子：`lineage_skipped` 明写「未给 --truth-lineage ⇒ 不登记「BOM → 成本」血缘」，成本照算、退码 0；
- 给了但抛异常：`lineage_error` 非空 ⇒ `result["ok"] = False` 且退码 4（不静默跳过）。

命令面**没有**新增命令，只在既有命令上加了一个 flag ⇒ 按登记镜像清单，
`command_contract.py`、census 分母、`SKILL.md` 的「主线共 N 个」计数都不动。

## 四、实测读数（真实 CLI，不是测试内调用）

作用域 `/tmp/s48cli/state.db`，项目 `DEMO`；命令行一律走 `.venv/bin/aipd`
（`aipd_os.__file__` 指向 `src/`，可编辑安装，所以控制台脚本跑的就是本树代码）。

| 步 | 命令 | 读数 |
|---|---|---|
| 1 | `bom add … bracket 12.5` | rc=0 |
| 2 | `cost calc --tooling 50000 --quantity 1000 --nre 1000 --margin 20 --truth-lineage --json` | rc=0；`ok=true`；`written=true`；`edges=1`；bom=`T-001` created=true；cost=`T-002` created=true；`bom_signature=53935c6d…`；`cost_signature=22967705…` |
| 3 | 同输入重跑第 2 步 | rc=0；bom 仍 `T-001` created=**false**；cost 仍 `T-002` created=**false**（同输入命中同一条，没另起版） |
| 4 | `bom add … cover 3.2` 后重跑 | rc=0；bom=`T-003` created=true；cost=`T-004` created=true（换 BOM 才另起新版） |
| 5 | `truth propagate --upstream T-001 --json` | **rc=4**；`ok=false`；`affected=[T-002]`；`marked_stale=[T-002]`；生成任务 `RW-001`（truth_id=T-002，pending）；`pending_rework=true` |
| 6 | `truth rework --task RW-001 --json` | **rc=4**；`ok=false`；`refused=[{task_id:RW-001, truth_id:T-002, artifact_kind:"bom_cost", reason:"本执行器只认 drawing_spec / drawing_dxf；不烧 attempts，这条任务仍是 pending 并如实点名"}]`；`supported_artifacts=[drawing_spec, drawing_dxf]` |
| 7 | 复读库里状态 | `T-001` superseded / `T-002` **stale** / `T-003` active / `T-004` active；`RW-001` `attempts=0, status=pending`（拒跑不烧 attempts）；边 2 条：`T-001→T-002`、`T-003→T-004` |

⇒ 标题那句「第一次能被传播打到」是第 5 步的读数，不是叙述。
第 6/7 步是给登记里那句「仍没有执行器、正确处置是保持 pending 或被拒」取的证。

一次注入前的自查：第 6 步最初带 `| tail -3` 读成 rc=0，那是 `tail` 的退码不是 CLI 的；
去掉管道重测得 rc=4。上表记的是后者。

## 五、判据自证与撞键复现

按 [[feedback-instrument-validation] 的规矩，凡是「按输入判身份」的键，落盘后先拿真输入做
**不同输入撞同键**的复现（第 46 片就是这么抓到签名漏吃模型的）：

- 撞键用例：`test_signature_covers_every_declared_input` 逐个把声明的输入项改成不同值，
  断言签名两两不同。E3/E4 两支电池（成本签名不吃口径、BOM 签名不吃行集合）注入后这条**必红**，
  说明它真的在盯签名内容而不是只盯长度。
- 记录状态可见性：`supersede` 只写 `status="superseded"`，**不写后继指针**
  （第 4 步的 `$.superseded_by` 读出 None，代码里也没有这个键）。本轮没有声称有指针。
- 一个会让人误查的账面现象：连跑 4 次 `cost calc --truth-lineage` 后
  `truth_lineage` 只有 2 行，而 `sqlite_sequence.seq = 4`、`max(edge_id) = 3`。
  成因是 `LineageGraph.add_edge` 用 `INSERT OR IGNORE` + AUTOINCREMENT：**被忽略的插入照样消耗序列号**。
  每次 calc 都调一次 `add_edge`，所以序列号 1:1 跟着 calc 次数走，行数只跟着「真正新的边」走。
  已用第 3 步之后「行数不变、seq 递增」的观察对上，不是丢边。

## 六、常驻用例与电池

- `tests/test_cost_lineage.py` 共 **10 条**（`test_cost_conclusion_is_reachable_from_the_bom`、
  `test_same_inputs_hit_one_cost_version`、`test_only_the_caliber_changed_supersedes_the_cost_not_the_bom`、
  `test_new_line_starts_a_new_bom_version_and_repoints_the_edge`、`test_no_flag_is_a_stated_skip_not_a_silent_one`、
  `test_empty_bom_writes_no_lineage`、`test_lineage_failure_holds_the_command_and_agrees_with_ok`、
  `test_signature_covers_every_declared_input`、`test_producer_is_registered_and_wired`、
  `test_producer_refuses_to_write_when_upstream_id_missing`）。
- 撤改电池 `/tmp/s48/battery.py`：**对照臂（未注入）rc=0 先立**，8 支注入 **8 杀 0 活 0 无效**，
  每支还原后按 sha256 断言字节回到原样。
  E1 命令面不调生产者 → 6 红；E2 不标 superseded → 1 红；E3 成本签名不吃口径 → 2 红；
  E4 BOM 签名不吃行集合 → 2 红；E5 空 BOM 也写 → 2 红；E6 写失败不改 ok → 1 红；
  E7 没给旗子时静默 → 1 红；E8 两条记录之间不连边 → 2 红。
- 生产者棘轮：`tests/test_drawing_spec_lineage.py::TestProducerRatchet` 的 `REGISTERED_PRODUCERS`
  补入 `src/aipd_os/bom/cost_lineage.py`；同一次 AST 普查读到 **11 处 `add_edge` 调用点，全部在登记里**
  （其中 3 处写 canonical 而非 `truth_lineage`，登记里按注释区分）。
- 镜像同步：`src/aipd_os/registry_data.py`（生产者计数三→四、能力行、unit_test 列表、
  `industrialize.quote_to_bom_cost` 的 limitation 行）、`docs/architecture/truth_architecture.md`、
  `README.md` 速查。命令数与 census 分母未动。
  镜像后复跑受影响常驻用例 **53 passed**（cost lineage / spec lineage 棘轮 / census /
  capability entry surface / capability matrix / doc reference census / registry export / skill 命令面）。
- 登记里那句第 47 片漏改的「BOM/成本那一支仍没有血缘生产者」本轮在原行内清掉
  （读者不会往下翻三层找更正）。

## 七、仍然没接上的（是读数，不是完成度）

- **`bom` / `bom_cost` 两类制品没有返工执行器**：第 6 步实测拒跑，任务停在 pending。（**本条已被第 49 片推翻一半**：`bom_cost` 今天有执行器了，见`docs/audit/COST_REWORK_F-REWORK-COST_2026-09-26.md`；仍没有的是 `artifact=bom` 那一条。本节下方「缺口径五项的值」那条读数是第 49 片的第一步前提，仍然成立。）
  收口那条 stale 今天只能靠再跑一次 `cost calc --truth-lineage`。
  而且这不是「只差接线」：`bom_cost` 记录的 metadata 今天只存了
  `input_signature`（哈希）、`total_cost`、`currency`、`line_ids`、`bom_record_id`，
  **没有存口径五项的值**（`cost_lineage.py:145-151`）⇒ 拿这条记录重建不出同一次核算，
  执行器只能拿默认值猜。第 47 片对「缺字段的旧 DXF 记录」的纪律是**点名拒而不是猜**，
  所以接执行器之前必须先让生产者把口径五项写进 metadata（记为第 49 片第一步）。
- **上游方向仍断**：没有任何生产者往 `artifact=bom` 那条记录**连入边**
  （`quote apply` 写的是 `quote.*` fact，不是 truth 版本记录）。
  所以「改一条 CTQ 会打到成本」仍不成立——第 5 步是从 BOM 版本记录起算的。
- **触发靠人给 id**（**本条已被第 51 片补掉一半**：`aipd truth drift` 已经能只读地扫出「登记时的键 ≠ 当前输入的键」这类记录并点名为 `should_be_stale`，所以「发现」不再依赖人记得去 propagate；但**收口**仍要人跑 propagate + rework，drift 只报不写。原文照抄如下）：`aipd truth propagate --upstream` 取的是 `cost calc` 打印出来的
  `lineage.bom.record_id`；没有任何东西在 BOM 变化时自动去调它。
- `superseded` 只有状态、没有后继指针；「磁盘上的 BOM 与记录不符」不做常驻判定。
- 边表序列号与被忽略的插入一起增长（§五），本轮不修，只登记。

## 八、终读数

绑定前先过一道自建的报告前置校验（`/tmp/s48/verify_report.py`，11 条前提全成立才允许 mint）：
报告不早于被 attested 的检出、`root=/private/tmp/s48b`（证明跑的是干净检出而不是主树）、
`exitcode=0`、逐条 outcome 里无 `failed/error/x*/rerun`、`summary.collected == len(tests) == 2353`、
`passed+skipped == collected`、`collected == 2353`、报告内 `source_commit == tag SHA`、
`tests/test_cost_lineage.py` 恰 10 条且全 passed、attested HEAD == 主仓 HEAD。

| 项 | 读数 |
|---|---|
| 全量（干净 worktree `git worktree add --detach /tmp/s48b HEAD` @4723e00） | **2350 passed / 3 skipped / 0 failed**，1012.89s，rc=0 |
| 报告 | `docs/audit/pytest-report-v5.6.0.json`，sha256 `1d055c4bd493683e…`，`source_commit` = tag SHA |
| 清单 | `RELEASE_MANIFEST` / `SOURCE_MANIFEST` 均 **646** 文件（644 → 646，+`bom/cost_lineage.py`、+`tests/test_cost_lineage.py`） |
| 锚定 | 两份清单的 `source_commit` 都保持在 tag SHA `a66040520139405095648461f7144d4f00629924`，未跟 HEAD |
| `production_release_gate --release-ready --tag v5.6.0` | **8/8 passed，rc=0，`release_ready: true`** |
| `audit_repo --strict` | rc=1，**恰好 1 条 ✗**：`Provenance source commit mismatch: manifest=a66040520139… vs HEAD=…`（按设计：清单钉在 tag，树在其后） |
| 撤改电池 | **8 杀 / 0 活 / 0 注入无效**（对照臂未注入 rc=0 先立，见 §六） |
| 镜像后受影响常驻用例 | 53 passed（§六末） |
| lint（CI 口径 `ruff check src tests`） | All checks passed |
| `doc_reference_census` | 7 passed —— 但**它按设计不管 `docs/audit/**`**（该文件头第 12 行写明这里记的是当时的事实），所以本文件里 `cost_lineage.py:145-151` 这类行号引用不受该门禁保护，是本轮逐条读码核对过的，不是门禁背书的 |

两条本轮自抓、都记了出处的问题：
① 收尾提交漏了 `SOURCE_MANIFEST.json`，`workspace_clean` 那道检查把它判红（gate rc=2、
`release_ready: false`）——是门禁救了这一手，补交后 8/8；
② §二 初稿把 dbt 与 BitBake 归给了第 46 片，跨文件复grep 才暴露（第 46 片那张表里根本没有它们）。
