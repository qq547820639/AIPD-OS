# F-REWORK-BOM 第 53 片：给 `artifact=bom` 接上返工执行器（发现之后收得了口）

日期：2026-09-26 ｜ HEAD 起点 `3814527`（第 52 片收尾）
本轮**不做新的外部检索**（诚信条款下的跳过，理由写明）：执行器形状在第 45/47/49 片已经定了
四条判据（就地演进不另起版、重算由调用面注入、缺输入点名拒、签名一致而结论变了判拒），
本片只是把同一形状落到第四类制品，没有新的选型面；读过的出处（本轮逐行打开）：
`bom/cost_lineage.py:70-135`、`bom/cost_rework.py:1-165`、
`cli/commands_manufacturing.py:187-242`、`cli/commands_truth.py:148-253`。

## 一、要闭的那一格（第 51/52 片各留一次）

第 51 片让库**发现**「BOM 版本记录该 stale 却还 active」，第 52 片把报价那一格的键
接到库里的事实上；两片的 §六 都写着同一句：**`truth rework` 只认三类制品，
`artifact=bom` 在烧 attempts 之前被点名拒**。也就是说扫描能点名、却没人收口。

`truth rework` 的分派面读到的事实（不是推测）：`cli/commands_truth.py:175` 的
`supported` 是 `[drawing_spec, drawing_dxf, bom_cost]`，
`run_executor` 按 kind 三分支，其余落 `rework_artifact`（图纸声明那一支）。
⇒ 第四类要接的是**分派表 + 一支执行器 + 一份当前 BOM 的读法**。

## 二、实现（三处，都按"只有一份映射"来摆）

- `src/aipd_os/bom/bom_rework.py`（新，第四支执行器）：
  `SUPPORTED_ARTIFACT = "bom"`；`REQUIRED_INPUTS = (bom_id, revision, input_signature)`，
  `version_no` 只查键在不在（合法值可以是 0）；结果分档
  `unchanged / recomputed` + `missing_record / unsupported_artifact / missing_inputs /
  recalc_failed / recalc_incomplete_result / bom_moved / empty_bom / recalc_disagrees`。
  执行器**不新增边、不重指边**（BOM 是链的中间格，上游 `quote_batch` 指向的记录号不变）。
- `src/aipd_os/bom/cost_lineage.py:76-91`：抽出 `bom_version_fields(header, lines, signature=…)`
  ——正文 detail 与 metadata 的**唯一投影**，生产者（`cost calc --truth-lineage`）
  与返工执行器都走它。动机不是整洁：两边各写一遍时，「签名相同、正文不同」这种读数谁都不会红
  （第 52 片 R2 抓的是同一族病灶）。
- `src/aipd_os/cli/commands_manufacturing.py:187-259`：
  新增 `read_current_bom()`（怎么取行的唯一读法，`calc_current_cost` 改为调它）
  与 `bom_from_record()`（返工侧的重算器，**只读**，不走 `--truth-lineage` 那条会另起新版的分支）；
  `commands_truth.py` 把它接进分派表。

与成本那一支的一个真实差别，写进判据而不是注释：**当前 BOM 没有行 ⇒ 不算收口**。
版本记录描述的是「那张 BOM 的那些行」，空表重建不出它，拿 0 行演进等于把「行被删光了」
写成一次正常返工。

## 三、常驻用例 15 条（`tests/test_bom_rework.py`）

两个分支各钉「仍是同一条记录、引擎 bump 这一条（`version+1`、`stale→active`）、
执行器不动正文」；一条**绝对断言**：演进后的键 == 由 BOM 表当前行现算的
`bom_input_signature`（不是"和重算器自己说一致"）；一条投影形状断言
（`content == version_content(..., fields["detail"])` 且 metadata 去掉 `last_rework`
后**逐字段等于**生产面投影）；八种拒绝各一种子，每种子都跑
「快照逐字段不变」；一条把第 52 片的发现与本片收口接起来：返工跑完 `truth drift`
必须读成 `in_sync`；一条接线证明（AST 读 `commands_truth.py` 真调了
`rework_bom_artifact` 与 `bom_from_record`）+ README 镜像断言。

三条常驻用例被**同批改判**（它们是「钉住缺省保证」那一类，见记忆里
`resident test may pin the ABSENCE` 那条）：
`tests/test_truth_rework_cli.py` 两条把「没有执行器的制品」当拒绝样本的用例、
`tests/test_dxf_rework.py::test_rework_cli_supports_four_artifacts_and_still_refuses_quote_batch`
——宿主从 `artifact=bom` 换成 `quote_batch`。不改这三条，它们会在本片当场红；
改了而不换宿主，拒绝路径就再没有主人。镜像面另两处：`README.md:458` 与
`registry_data.py` 的 `product_truth.impact_propagation`（`current_limitation` 五处措辞
+ `unit_test` 名单）。

## 四、效力证明（电池 `/tmp/s53/battery.py`，7 臂）

对照臂（未注入）rc=0 先行；还原一律写回注入前读到的原文；收尾打印本轮留下的差异。

| 臂 | 注入 | 读数 | 原告 |
|---|---|---|---|
| BR1 | 执行器自己拼正文（绕开生产面投影） | KILLED 1 红 | `test_reworked_record_takes_the_producer_content_shape` |
| BR2 | 空 BOM 也算收口 | **注入无效**（电池内 rc=2，收集期 1 error） | 单独复现：`test_refuses_current_empty_bom` 红，rc=1 |
| BR3 | 记录挂的 BOM 已不是当前那张也照演进 | **注入无效**（同上） | 单独复现：`test_refuses_when_the_bom_moved` 红，rc=1 |
| BR4 | 签名没变而 revision/version_no 变了照样 bump | KILLED 1 红 | `test_refuses_same_signature_but_identity_moved` |
| BR5 | 没交出 BOM 表本体仍然投影 | KILLED 1 红 | `test_refuses_when_projection_inputs_absent` |
| BR6 | 缺身份输入的旧记录也去重算 | KILLED 1 红 | `test_refuses_record_without_identity_inputs` |
| BR7 | 不认识的制品也送去烧 attempts | KILLED 3 红 | `test_unknown_artifact_is_refused_before_consuming_attempts`、`test_refusals_are_visible_in_the_json_payload`、`test_rework_cli_supports_four_artifacts_and_still_refuses_quote_batch` |

**BR2/BR3 的读数不干净，这里按事实记，不折成「杀掉」也不折成「判据没主」**：
在电池那一跑里这两臂都是 `rc=2 / Interrupted: 1 error during collection`，
而把同一条注入单独拿去跑（同一份 target 顺序、同样 `PYTHONDONTWRITEBYTECODE=1`）
得到的是 `rc=1`、只有被告那一条红；两条日志留在
`/tmp/s53/battery4.log` 与 `/tmp/s53/br2iso.log`。
按 [[feedback-mutation-battery-controls]] 的口径：这两臂记「注入无效（量具相关，归因未定）」，
判据的主人是靠**单独复现**那两次读数确认的；下一片若再遇到同形状，先查电池多臂共用
一份工作副本时的收集期状态，别先动判据。

## 五、真库读数（第 50/52 片那份副本，项目 `D50`，带齐 `state.db`+`bom.db`）

第 50 片那次 `truth propagate --upstream T-003` 给 `T-001`(bom) 与 `T-002`(bom_cost)
各留了一条 pending 任务。本片之前 `truth rework --all-pending` 只能收掉 `T-002`，
`T-001` 落在拒绝清单里。现在的读数（`/tmp/s53/rework.json`，退码 0、`ok=true`）：

```
RW-001 / T-001：executor.outcome = recomputed
  recorded_signature 4f9f3f81cf3806f7e481b9081deab6… → ac62f93e5664c2029e47ba61d5ebfb…
  engine.status = succeeded, attempts 0 → 1, new_version = 2
selected = [RW-001, RW-002]，refused = []（本副本里没有 quote_batch 任务）
```

也就是说：**同一条 BOM 版本记录被就地演进到当前行集合的键，由引擎 bump 到 version 2，
没有新增版本记录**——这正是 §二 第一条判据在真库上的形状，而不只是用例里的断言。

## 六、终读数

@@FINAL@@

## 七、遗留

- `quote_batch` 仍没有执行器（刻意：它的"返工"是重新 apply 一次报价，属生产面动作）。
- 扫描 ≠ 触发：发现漂移之后要不要 `truth propagate` 仍靠人；「漂移清单 → 建返工任务」
  这一格是本片之后最直接的下一步。
- BOM/成本变动反向影响 CTQ（上游方向）仍没有路。
- 本地开发库 `data/state.db` 刻意未打开，存量记录在新老基准下的分布仍未量。

