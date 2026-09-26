# F-GATE-MULTIPLICITY 第 58 片：`gdt_covers_ctq` 按记录号核对覆盖（2026-09-26）

## 一、要拍的问题

第 57 片 §九 留了一句「覆盖率归发布门禁 `gdt_covers_ctq` 管」，并记下一个疑点：那条门两侧的
特征名可能不同源。任务 #65 要把它测清楚，不许停在叙述上。

## 二、先把读到的前提钉住（原假设是被源码否证的）

- 门的判据（改前，`scripts/production_release_gate.py:271-284`）：
  `{c.feature for c in doc["ctq"]} - {g.feature for g in doc["gdt"]}` 的**集合差**；
- `doc["gdt"][].feature` **不是**图纸上的名字：`src/aipd_os/release_manifest.py:256`（尺寸凭据）
  与 `:292`（形位框凭据）写的都是 `"feature": ctq["feature"]`，图纸名另存在 `drawing_feature`。
  ⇒ 「两侧前缀不同会假红」这个原假设不成立，未进修法；
- 但同一段暴露出另一件事：既然是**按名字**求差，名字撞车就丢记录条数。
  `aipd ctq add` 只拦「同一图纸尺寸上已有 active CTQ」（`product_truth/ctq.py:declare_ctq`
  在落库前按 `drawing_feature` 点名拒），不拦两条不同图纸特征共用同一个 `feature` 标签 ⇒ 掩盖是**可达**的。

## 三、第一轮实测：顺序不对，什么都没测到（夹具错，不是判据没问题）

`/tmp/s58/gate_multiplicity.py`：两臂都先 `ctq add` 两条再一次出声明出图。
读数：`drawing generate` 退 4 —— 「spec 声明的这些特征在图上找不到 ⇒ 少标了公差：
['TOP.hole_9']」，另有「TOP.hole_1 实测 8 不在 CTQ 的 5.95–6.05 内」。
⇒ 没有交付物进清单，两臂都读不到目标形状。两处都是**我的夹具**的问题：
限值是抄测试常量（Ø6）而黄金件模型实测 Ø8；未覆盖那条又被出图那一步先拦掉了。

## 四、第二轮实测：生产可达的顺序，两臂只差一个标签

`/tmp/s58/order_arms.py`：`ctq add A` → `drawing spec` → `drawing generate`（退 0）→
**之后**再 `ctq add B`（B 挂 `TOP.slot_1`，声明里没有它）→ `build_release_manifest` → 门禁子进程。
限值按模型实测取（标称 8.0 / ±0.05）。

| 臂 | 两条 CTQ 的 `feature` | `doc[ctq]` | `doc[gdt]` 挂到的记录 | 按记录号应得 | 门禁（改前判据） |
| --- | --- | --- | --- | --- | --- |
| 丙 | `hole_Ø8`、`hole_Ø8`（撞车） | 2 条，名字集合 `{hole_Ø8}` | `T-001` | `T-004` 未覆盖 | **passed=True**，`all ctq features covered by gdt` |
| 丁 | `hole_Ø8`、`hole_Ø9` | 2 条，两个名字 | `T-001` | `T-004` 未覆盖 | passed=False，`['hole_Ø9']` |

两臂命令、限值、模型、顺序全同，唯一差别是标签是否撞车 ⇒ **假绿成立**：
一条 active 要求没有任何覆盖凭据，门禁却宣布全覆盖。
读数原文 `/tmp/s58/run1.log`、`/tmp/s58/run2.log`、`/tmp/s58/run3.log`（第三份是改后复跑：
两臂都红且点名 `T-004（…）`）。

## 五、修法与为什么不改生产者

`scripts/production_release_gate.py`：按 `ctq[].record_id` ↔ `gdt[].ctq_record_id` 求差；
`ctq` 条目缺 `record_id` 时判**不可核**（fail-closed），不退回按名字猜——按名字正是刚被推翻的
那个错做法；未覆盖的理由点名记录号并带上它的特征名，绿的时候报记录条数（`all 2 ctq records covered`）。
生产者两列本来就写（`release_manifest.py:86`/`:257`/`:293`），门只是没读它 ⇒ 写侧无事可做。

## 六、连带发现：同一个"生产者不会产出的形状"被抄了三份

改完门禁后有 3 条常驻用例红，全都是**手写夹具**：
`tests/test_production_release_gate.py`（默认清单）、`tests/test_cli.py`（两处最小清单）、
`tests/test_production_release_gate_file_lists.py`（`_pack`）——它们的 `ctq`/`gdt` 只写 `feature`
不写记录号，而各自都断言门**通过**。这不是判据太严：那三处断言的是"证据齐了就绿"，
而"齐"的形状按生产者算就是带记录号的。三处一并补齐，并在每处注明两列的出处。

## 七、常驻用例（4 条新的，两侧都有对照）

- `test_two_ctq_records_sharing_a_feature_label_are_not_masked` —— 甲形必红，理由含 `T-002`；
- `test_every_record_covered_is_green_even_with_shared_labels` —— **不开火对照**：
  两条同名记录各自都有凭据 ⇒ 绿，且理由报 `all 2 ctq records covered`；
- `test_ctq_entry_without_record_id_fails_closed` —— 缺记录号判不可核，不许退回按名字；
- `TestCliProducerAndGate::test_a_requirement_arriving_after_the_declaration_is_not_masked`
  —— **链上真数据**：`ctq add` → `drawing spec` → `drawing generate` 退 0 → 再加一条同名要求 →
  `build_release_manifest` → 子进程跑门，断言红且点名那条未覆盖记录的 id；
  它上面那条 `test_the_whole_chain_needs_no_hand_written_spec_to_pass_the_gate`（单条 CTQ 全绿）
  就是这条的对照，两条一起才说明"红是因为少了一条覆盖，不是因为链跑不通"。

@@TESTS@@

## 八、变异电池（`/tmp/s58/battery.py`，worktree `/tmp/s58w`）

五条臂：B1 退回按名字集合求差、B2 缺记录号不 fail-closed、B3 覆盖集合改回读特征名、
B4 理由不点名记录号、B5 生产者不再写 `ctq_record_id`（写侧撤镜像）。

@@BATTERY@@

@@FINAL@@

## 九、遗留

- `doc["ctq"]` 为**空**（一条要求都没声明）时走 `else` 分支判"不可核"，本轮没有为这条路径
  新增正面用例——它现在只被"数据缺失即失败"这一族间接覆盖。**未实测的就是未证实的**。
- `gdt` 两条凭据同源同一条记录（尺寸 + 形位框都挂它）由 `release_manifest.py:289` 的
  `covered` 集合去重，本轮未改也未测。
- 真实存量库 `data/state.db` 仍未打开（属主数据，刻意不动），所以"存量清单里有多少条 `ctq`
  条目没有 `record_id`"未测；按 §六 的三份手写夹具外推，生产清单一定有，但未亲验。
- 相邻判据 `ctq_has_inspection` 也是逐条读 `doc["ctq"]`（不按集合），本轮顺手核对过它
  没有同类"丢条数"的形状，但没有为它补多重记录的正反对照。
