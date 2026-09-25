# F-CLI-COV 第 40 片：把在册 17 条命令补成走过 CLI 入口的真调用

日期：2026-09-26 归属：命令面一致性（`aipd` CLI）
状态：已闭（`cli` 档 66/66，`BASELINE` 清空，闭合账 `CLOSED` 顶上）
上一片：`docs/audit/COMMAND_SURFACE_CENSUS_F-CLI-COV_2026-09-26.md`（量具本身）

## 一、这片要关的账

第 39 片把「命令被测过」从子串匹配换成 AST 读 argv 位之后，量出的 17 条低于 `cli` 档：

| 档 | 条数 | 命令 |
| --- | --- | --- |
| `none` | 10 | `cad preflight` `dashboard` `onboard` `operate` `product show` `product gate` `recover` `reset` `ui` `version` |
| `alias` | 4 | `cad build` `package` `resume` `test`（只有 deprecated 别名被 `main([...])` 走过） |
| `handler` | 1 | `doctor`（只有 `cmd_doctor(...)` 直调） |
| `handler_ambiguous` | 2 | `outbox drain` `outbox review`（都调 `cmd_outbox`，分不清 verb） |

## 二、补法：走解析器，别走捷径

`tests/test_cli_public_surface.py`（14 条）全部用 `main([...])` 形态：走 argparse、走分发。
理由写在 F-CLI-01：真正的产品面是解析器，直接调 `cmd_*` 看不见"注册了但没接线"这类缺陷。
断言一律落在**读数**上（JSON 字段 / 退出码 / 落盘产物），不写「rc 不为 0 就算跑过」——
第 33 片量过那种写法分不清"门在拦"与"门永远红"。三处判定值得单记：

1. **两问分开**：同一份 `faceted_brep`（封顶 C1）manifest，
   `cad preflight --target C1` ⇒ `passed: true`、rc=0（只问上限允不允许）；
   `cad build --target C1` ⇒ `ok: false`、`target_passed: false`、`reached_level: null`、rc=4
   （问证据够不够）。若两问混成一谈，`preflight` 那条就会把门禁的拒绝当成自己的失败。
2. **共用处理函数只能靠 verb 各走一次来消歧**：`outbox drain` 与 `outbox review`
   各调一次，并断言**两份读数不同**（`review != drain`）；只断"都 rc=0"关不掉这一档。
3. **`ui` 只 mock 最外那层**：`aipd_os.web.serve` 换成记录参数的桩，断言
   db/host/port 三个值原样交到位。起真服务会挂住套件；直接调 `cmd_ui` 又看不见接线。
   这类"命令本身就是起进程"的命令，证据边界是**参数交接**，不是端口能连上。

其余落点：`onboard` 断言首份结果四类齐全（fact/risk/deliverable/decision）；
`dashboard` 在空台账上断言措辞是「暂无风险条目」（不是"0 条风险都有真人认领"这种对空集的断言）；
`operate` 断言进度步序列固定六步且 `impact.reversible` 为真；
`reset → recover --backup` 配成一对手感（备份目录真在盘上、真能吃回去）；
`recover` 不带 `--backup` 时断言**没有** `restored` 字段（两条分支不许混）；
`product gate` 在无快照时断言 `NO_SNAPSHOT` + `eligibility.eligible is False` +
`authorization.state == "PENDING"`（AI 不能替属主先把门禁置成已批）；
`test` / `package` 只换掉下面的重活（`commands_release._run_pytest` /
`_build_release_impl`）——注意补丁要打**被调模块自己的名字**，打 `_helpers` 上那份不生效
（第一次探针就是因为这个在 `aipd test` 上跑了整套真套件）。

## 三、棘轮随即判红，账按规则清空

补完后 `tests/test_command_surface_census.py` 红了三条，报的是
`已补真调用却没删格：[17 条]` —— 这正是第 39 片设计的双向面在做事。按规则只删格：

- `BASELINE` 清空，并把它自己的条数断言改成「重新往基线里加格子 = 放行新缺口」即红；
- 非空转前提 `cli` 档 49 ⇒ 66；
- **空基线会留下空循环**：`test_each_recorded_tier_is_the_measured_one` 在 `BASELINE={}` 上
  永远绿。所以新增 `CLOSED`（17 条 × 证据文件名 needle）接住这一面：
  某条命令的 cli 证据不再来自 `test_cli_public_surface`，或 `CLOSED` 自己漂了条数 ⇒ 红；
- 顺带修掉一处上一轮我自己写的**把现状当应然**的断言：
  `test_command_coverage.py` 的报告用例原本硬要求「必有未测缺口」，
  补满 66 条后它自己成了假红。缺口存在性归棘轮与闭合账，报告只报。

## 四、撤改电池（`/tmp/s40/battery.py`，5 条：杀 5 / 存活 0 / 注入无效 0 / 崩溃式红 0）

对照臂（未注入）rc=0 先立。

| 注入 | 半径 |
| --- | --- |
| E1 `doctor` 退回直调 `cmd_doctor` | `test_below_cli_set_matches_the_record_exactly`、`test_closed_register_still_points_at_real_argv_evidence`、`test_reading_is_not_vacuous` |
| E2 注册新命令不补 argv 用例 | `test_below_cli_set_matches_the_record_exactly`、`test_tiers_partition_the_denominator` |
| E3 闭合账少记一条 | `test_closed_register_still_points_at_real_argv_evidence` |
| E4 证据指向写成不存在的文件名 | `test_closed_register_still_points_at_real_argv_evidence` |
| E5 往清空的基线里重新塞格子 | `test_below_cli_set_matches_the_record_exactly`、`test_each_recorded_tier_is_the_measured_one` |

两条电池纪律是这片现学的：**撤改核验要逐文件比 sha**（拿全仓快照比会让一臂的泄漏把
后续四臂全报成"还原失败"）；**注入需要的 import 必须由注入文本自己带上**
（第一版 E1 先往被测文件里加 `SimpleNamespace` 再"还原"，等于留下一处看着像用户改动的泄漏）。

## 五、复算入口

```
.venv/bin/python scripts/command_surface_census.py            # 读数：cli 66 / 其余 0
.venv/bin/python -m pytest tests/test_cli_public_surface.py tests/test_command_surface_census.py \
    tests/test_command_coverage.py -q
```

全量与两道发布门禁的终读数由 `production_release_gate` / `audit_repo --strict` 跑完后补在下节。

## 六、终读数（工作树干净后跑）

- 全量（干净 HEAD 签出、`AIPD_SOURCE_COMMIT=v5.6.0 tag 提交`）：
- `production_release_gate --release-ready --tag v5.6.0`：
- `audit_repo --strict`：
