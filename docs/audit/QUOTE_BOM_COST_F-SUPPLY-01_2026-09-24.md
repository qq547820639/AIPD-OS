# F-SUPPLY-01 / F-BOM-01 / F-COST-01：询价 → 报价 → BOM → 成本这条商业主链的闭合

日期：2026-09-24　范围：`AIPD-OS`　停止条件：本文所有读数均为本机实测，未实测处显式标注。

## 1. 结论

商业主链「想法 → 产品定义 → 手册/图纸治理 → **BOM → 成本核算** → 发布门禁」中的
报价→BOM→成本一段，接线前**在软件意义上从未成立过**：不是"实现得不够好"，而是
三个必要写入口在产品路径上一个都不存在。本轮闭合该段，并把「开模可用物料清单」
这个门禁从"数学上不可能满足"变成"能过、且过不了的时候会点名"。

## 2. 接线前的实测事实（`git grep HEAD`，非推测）

| # | 事实 | 读数 |
|---|---|---|
| 1 | 会写库的 `SupplyChainStore.persist_quote` 没有产品调用点 | 定义 1 处（`supply_chain/persistence.py:70`）+ 唯一调用者 `tests/test_supply_chain.py:455` ⇒ 产品侧 **0** |
| 2 | `set_bom_status` 没有产品调用点 ⇒ `bom_released` 在产品路径上永假 | 定义 `bom/store.py:166` + 仅 `tests/test_bom.py:141,156` ⇒ 产品侧 **0** |
| 3 | `bom show` 算发布清单时不带成本口径 ⇒ `cost_calculated` 永假 | HEAD `cli/commands_manufacturing.py:60`：`release_checklist(store, DEFAULT_TENANT, pid)`，`projection.py` 里 `cost_inputs is None ⇒ cost=None ⇒ cost_calculated=False` |
| 4 | 报价的单价从来没有成为过 BOM 的成本 | HEAD 全仓写 `unit_cost=` 的三处：`bom/cost.py:99`（成本结果字段，非 BOM 行）、`bom/store.py:244`（行→模型读取）、`cli/commands_manufacturing.py:101`（CLI 手填 `--unit-cost`）⇒ 唯一的 BOM 行单价来源是人手工敲 |
| 5 | `aipd industrialize --quote` 解析结果进临时注册表后丢弃 | `cli/commands_cad.py:63-72`：`registry = QuoteRegistry()`（第 65 行）为函数局部对象，返回值只带一份打印用的 `official_quotes` 列表 |
| 6 | `compute_bom_cost` 把不同币种直接相加、且把 `obsolete` 行算进材料小计 | HEAD `bom/cost.py`：`material_subtotal += line.quantity * line.unit_cost` 无币种判据、无状态判据 |
| 7 | 报价文件规范表头没有币种列 | `supply_chain/quotes.py` 的 `CANONICAL_CSV_HEADER` = supplier,part,moq,tooling_fee,unit_price,lead_time_days ⇒ 单价的单位只能由调用方声明 |
| 9 | 接线后自己量出：同文件二次 `quote apply` 直接崩在 UNIQUE 上 | `错误：UNIQUE constraint failed: facts.project_id, facts.tenant_id, facts.key, facts.version`（exit 1）——版本号取自进程内 `QuoteRegistry`（每次从 v1 起），事实却按项目持久 |
| 8 | `bom` / `cost` 能力从未进过能力登记表 | `git grep -n 'compute_bom_cost\|release_checklist\|BomStore' src/aipd_os/registry_data.py scripts/product_capabilities_extra.py` ⇒ **0 命中** |

第 1–4 条合起来是同一个结构缺陷的四个断面：**清单要求的事实（已报价、已核算、已发布）
没有任何一条写入路径**。第 8 条说明它为什么能长期不被发现——这条链既没有常驻用例走
真实入口，也没有进能力登记表，所以既没有测试面也没有声明面。

## 3. 技术选型：本轮为什么跳过外部生态检索

本轮改动是**在既有模块之间接线**（`supply_chain/quotes.py`、`supply_chain/persistence.py`、
`bom/store.py`、`bom/cost.py`、`cli/`），未引入任何新外部依赖、未新增第三方包、未改
`pyproject.toml` 的依赖面，符合目标里"影响范围明确的小修复或局部改动可跳过调研"的例外；
候选清单来自本会话前几轮对 `src/` 接线缺口的普查（排序第 1 项即本条链），不是外部检索结果。
本文不声称查阅过任何本轮未实际打开的项目或文档。

真正需要裁决的是三个仓内设计选择，逐个对比后自行选定：

**决策 1：报价的价落在哪里。**
- 候选 A —— 只落 `quote.*` 事实，成本核算时 JOIN 报价：好处是 BOM 不被外部数据"污染"、
  报价改价不需回写；代价是 `compute_bom_cost` 必须做 IO（其函数文档明确写着"纯函数，
  无 IO"），且 `BomLine.quote_ref` / `status='quoted'` / `currency` 这些**模型里已经存在**
  的字段继续是死列。
- **选定 B** —— 报价落到对应 BOM 行（`unit_cost/supplier/quote_ref/status='quoted'`），
  成本核算保持纯函数。理由：模型早就为这一步留了字段（BomLine 已含 `quote_ref`、
  `status` 取值域含 `quoted`），`rollup`/`release_checklist` 已按"行上有价"判完整性，
  且不为 `compute_bom_cost` 的纯度契约开洞。适配成本最低，License/安全风险为零（无新依赖）。

**决策 2：`bom release` 是"置状态"还是"先过清单再置状态"。**
- 候选 A —— 只置状态，检查清单留给调用方自查：命令职责更窄；代价是 `release_ready`
  变成一句可以随意勾选的话（任何人先 release 再"顺便看一眼"清单）。
- **选定 B** —— `bom release` 内部先跑 `release_checklist`，除 `bom_released` 自身外
  任一未过即 `exit 4` 并列出 `blocking_checks`。理由：这张清单的定义就是"开模可用"的
  验收，验收必须长在写入口上而不是长在事后统计上。

**决策 3：多币种怎么办。**
- 候选 A —— 按默认汇率折算：仓内没有任何汇率源，等于**虚构**一个换算系数进成本，
  直接违反本仓"缺数据不按 0 元假装"的同一条诚实原则。
- **选定 B** —— 币种由 `--currency` 显式声明，逐行与 `BomLine.currency` 核对，不一致即
  拒绝该行（`rejected: currency-conflict`）；核算侧若发现多种币种共存则抛
  `CostCurrencyError`。钱没有单位就不算。

## 4. 落点与口径

| 位置（写后复读定位） | 内容 |
|---|---|
| `src/aipd_os/supply_chain/apply.py:36` `quote_fact_key` | 与 `persist_quote` 写入的 fact key 同形状（`quote.<supplier>.<part>.v<n>`），使 `BomLine.quote_ref` 可解析回一条真实事实 |
| `apply.py:62` `assign_quote_versions` | 版本号对齐到已落库事实：内容签名命中即**复用**那一版（不重复登记），否则取「库里最大版本 ∪ 本轮已分配」+1 ⇒ 同文件重放结果相同、改价只增不减、不撞号（F-SUPPLY-02） |
| `apply.py:107` `retire_stale_officials` | 本次涉及的 (供应商, 零件) 上，不是当前官方版且仍为 `V` 的事实改判 `R`——两版同时「作数」等于没有权威；本次没碰过的零件不动 |
| `apply.py:137` `ApplyReport` | `updated / unchanged / rejected / unmatched / clean` 四分账，`clean` = 无 unmatched 且无 rejected |
| `apply.py:167` `apply_quotes_to_bom` | 逐条报价：① 非 `official` ⇒ 命中活行即逐行 `rejected: not-official`（附 `would_have_set`）；② 零件对不上 ⇒ `unmatched: no-bom-line`（不静默跳过）；③ 行币种 ≠ 声明币种 ⇒ `currency-conflict`；④ 行 `status=obsolete` ⇒ `obsolete-line`；⑤ 价与引用已一致 ⇒ `unchanged`（不推高 `version_no`）；⑥ 其余经 `store.update_line(expected_version=…)` 乐观锁写入 |
| `src/aipd_os/cli/commands_supply.py:26/33` | `aipd quote apply`：解析 → 登记（版本递增/旧版 superseded）→ 按库对齐版本 → `persist_quote` 落 `quote.*` 事实 → `apply_quotes_to_bom` → `rollup` 的 `missing_cost_items` 作为 `bom_remaining_unpriced` 如实列出；报价侧不干净 ⇒ `exit 4` |
| `src/aipd_os/cli/commands_manufacturing.py:50` `_cost_inputs` | `bom show` / `bom release` 与 `cost calc` 共用同一套口径与默认值（五个 flag 已进 parser，故直接取属性而非 `getattr` 兜默认） |
| `commands_manufacturing.py:66` `_bom_release` | 清单未过 ⇒ `exit 4` + `blocking_checks`；过了才 `set_bom_status("released", expected_version=…)` |
| `commands_manufacturing.py:126` `_bom_show` | `release_checklist(..., cost_inputs=_cost_inputs(args))`，并把口径本身回显在 `cost_inputs` 字段（口径可见才谈可复算） |
| `src/aipd_os/bom/cost.py:16/19/64/96` | `OBSOLETE_STATUS`、`CostCurrencyError`、`obsolete_excluded`、核算时排除作废行并收集币种集合 |
| `src/aipd_os/bom/projection.py` `rollup` | 与核算共用 `OBSOLETE_STATUS`，新增 `obsolete_items`，作废行不进 `missing_cost_items` |
| `src/aipd_os/cli/commands_cad.py:63-78` | `industrialize --quote` 增加 `quotes_note`：自陈"仅解析、未写 Product Truth、未改 BOM 单价"，并指向 `aipd quote apply` |
| `cli/main.py` / `cli/commands.py` / `cli/command_contract.py` / `SKILL.md` | 新增 `quote apply`、`bom release` 两条 public 命令（parser → `COMMAND_FUNCS` → 契约 → SKILL 四处同源，public 计数 41 → 43） |
| `src/aipd_os/registry_data.py:66` | 新能力行 `industrialize.quote_to_bom_cost`（入口可被 `probe_entry_callable` 解析）；`industrialize.quote_parsing` 的 limitation 补一句"解析本身不动钱" |

## 5. 测试与变异对照

`tests/test_quote_to_cost_chain.py`（16 条，`-p no:randomly` 全绿）：

- 完整性 4 条：混币种必须抛错且消息含两个币种、单币种如实汇总、作废行不虚增成本、
  **反向对照**——排除作废行不得顺手把"活行缺价"也放行；
- 报价落价 5 条：单价→材料小计精确对账（2 × 12.5 = 25.0）、对不上零件必须点名、
  草稿报价绝不覆盖已确认价、二次登记（同一注册表）⇒ v1 转 superseded 且在同一次应用里
  被 `not-official` 逐行拒绝、币种冲突逐行拒绝；
- 可重跑性 3 条：同文件重放 ⇒ 零新事实 + 全部 `unchanged` + 库里仍只有 v1；改价 ⇒ v2 为 `V`、v1 转 `R`、BOM 指回 v2；复用路径下 `quote_ref` 必须解析到**已落库**的那一条；
- 真实入口 4 条（`main(argv)`，参数由 `build_parser()` 产出，不手搓 Namespace）：
  清单端到端可满足（含 `bom release` 前后两次读数与 `cost_calculated` 必须为真）、
  `quote_ref` 能解析回真实 `quote.*` 事实、`industrialize --quote` 的自陈且**库里确实零条
  quote 事实**、分批报价时 `bom_remaining_unpriced` 如实列出而 `bom release` 仍被挡住。

> 为什么测试必须走真实入口：本轮之前的缺陷正是"没有一条命令把口径带进去"，而手搓的
> args 副本会替实现补上缺的字段，把缺口抹平成假绿。上一轮也真踩过这个（自造 Namespace
> 漏了 `--part`，测试却在测一个不存在的调用面）。

变异对照（本机改真码后复跑，之后从备份逐字节还原）：

| 变异 | 期望 | 实测 |
|---|---|---|
| `apply.py` 的 `if quote.status != "official":` → `if False:` | 至少 1 条红 | **2 红**：`test_draft_quote_never_overwrites_a_price`、`test_second_official_version_supersedes_the_first` |
| `_bom_show` 去掉 `cost_inputs=_cost_inputs(args)` | 至少 1 条红 | **1 红**：`test_release_checklist_is_satisfiable_end_to_end`（`cost_calculated` 翻回 False） |
| `assign_quote_versions` 的 `if reused is not None:` → `if False:` | 至少 1 条红 | **1 红**：`test_second_apply_of_the_same_file_is_a_no_op`（重放又登记了一条新事实） |
| `retire_stale_officials` 的改判分支永不进入 | 至少 1 条红 | **1 红**：`test_new_price_continues_the_version_and_retires_the_old_fact`（库里两版同时 `V`） |

还原后 16 条重新全绿。首次注入尝试还顺带量出一个工具性事实：`python` 不在裸 PATH 上时，
heredoc 里的改码头脚本会静默不执行，"变异后仍全绿"是假读数——因此改用 venv 绝对路径并在
跑测试前 `grep -c` 确认变异已落盘（`grep` 计数为 1 才继续）。

## 6. 已知边界与本轮未做

- **不做汇率折算**：多币种只在"逐行拒绝 + 核算抛错"这一侧收口，跨币种折算未实现；
- **MOQ / 模具费 / 交期未参与决策**：`tooling_fee` 仍由 `cost calc --tooling` 手填，报价里的
  `moq/tooling_fee/lead_time_days` 只作为事实留存，没有做"按 MOQ 取整"或"模具费自动进摊销"；
- **跨库仍无原子性**：`quote.*` 事实在 `state.db`、定价后的行在 `bom.db`，两步之间崩溃会留下「有事实、未定价」。收口手段是**重放即修复**（F-SUPPLY-02 正是为这条窗口服务的： 修法前重放会二次崩，等于窗口永远合不上）。本机实测：重放读数「新登记事实 0 条，复用已有事实 1 条 / 已是该价」，改价读数「新登记事实 1 条 … 旧版报价事实转 R」；
- **`quote apply` 不因 BOM 缺价而失败**（决策：分批报价是正常工作流，缺价由 `bom release` 挡），
  这一点已写进 `commands_supply.py` 模块文档与用例名，避免下一个人当成 bug 改回去；
- **能力登记面仍不完整**：`bom show/add`、`cost calc` 自身在 HEAD 就没有能力行（第 8 条事实），
  本轮只补了"报价→BOM→成本"这一条闭环行，没有把制造就绪域的历史缺口全数补齐；
- **发布门禁未纳入成本**：`production_release_gate` 是否要求"成本已核算"属共享门禁语义变更，
  仍留待属主裁决（前几轮普查的第 4 候选，维持不动）；
- 本轮未触碰：外部邮件真实投递、WAL 启用、版本双轨、tag/签名重锚、`releases/golden-projects/**`。

## 7. 复算入口

```bash
export PATH="$PWD/.venv/bin:$PATH"
python -m pytest tests/test_quote_to_cost_chain.py tests/test_bom.py \
                 tests/test_supply_chain.py tests/test_cli.py -q -p no:randomly
python -m pytest tests/test_skill_command_surface.py tests/test_command_coverage.py -q
python scripts/capability_matrix.py --repo . --out docs/audit   # 矩阵含新能力行
# 手工看一条链（临时库，不碰开发者数据）：
D=$(mktemp -d); python -m aipd_os.cli.main init --db "$D/state.db" \
  --project P-1 --name 支架 --goal 量产 >/dev/null
printf 'supplier,part,moq,tooling_fee,unit_price,lead_time_days\n亚明五金,支架,100,5000,12.5,15\n' \
  > "$D/q.csv"
python -m aipd_os.cli.main bom add --db "$D/state.db" --project P-1 --part 支架 --quantity 2
python -m aipd_os.cli.main quote apply --db "$D/state.db" --project P-1 --file "$D/q.csv"
python -m aipd_os.cli.main bom show --db "$D/state.db" --project P-1 --tooling 5000 --quantity 1000
python -m aipd_os.cli.main bom release --db "$D/state.db" --project P-1 --tooling 5000 --quantity 1000
```

上述五步本轮已在本机临时目录实际跑过，输出原文（`mktemp -d` 的一次性库，未触碰开发者数据）：

```text
已添加 BOM 行：支架（LINE-001，数量 2.0pcs，供应商 未填，单位成本 未填）
报价解析 1 条（/var/folders/.../q.csv），落库事实 1 条，币种 CNY
  已定价：支架 → 12.5 （亚明五金，quote.亚明五金.支架.v1）      # quote apply rc=0
BOM：P-1 主物料清单（BOM-001，rev 0.1，状态 draft）
  行数：1；根件：支架
  供应商分布：亚明五金×1
  发布检查：✓bom_exists ✗bom_released ✓lines_present ✓cost_complete ✓no_orphan_parents ✓cost_calculated
  开模可用物料清单就绪：否
BOM BOM-001 已置为 released（version 2）                        # bom release rc=0
```

对照第 2 节事实 2/3：接线前同一序列里 `cost_calculated` 只会是 ✗、`bom_released` 无任何写入
路径，`release_ready` 恒为「否」。
