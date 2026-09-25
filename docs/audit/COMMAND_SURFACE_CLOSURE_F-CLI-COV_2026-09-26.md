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

## 六、终读数（工作树干净后跑，两跑全在 `git worktree` 的 HEAD 签出里）

| 跑 | 树 | collected | passed | failed | 说明 |
| --- | --- | --- | --- | --- | --- |
| A | `d4b8c64`（代码与镜像，清单未刷） | 2281 | 2276 | 2 | 只红在 `test_release_manifest_hashes_match_disk` / `test_source_manifest_hashes_match_disk`（新用例文件未入册），预期 |
| B | `fa9611f`（清单已重锚） | 2281 | **2278** | **0** | 报告 `source_commit = a660405…`（v5.6.0 tag 提交）、sha256 前缀 `ba8a5a6be008`；同一份既作本轮记录也作锚定用（`HEAD=310774a` 时 PROVENANCE 绑的就是它） |

- 上一片 2263 → 本片 **2278** 通过（+15；收集 2266 → 2281），跳过仍为 3。
- 这一片**没再踩**第 39 片那两条 5× 比值性能门的并发假红（load 已降到 ~12）。
  读数与「上一片也红过所以大概是噪声」无关：B 跑本身就是 0 failed。
- `scripts/command_surface_census.py`：`cli 66 / alias 0 / handler 0 / handler_ambiguous 0 / none 0`。
- `skill_quality_audit.py`：0 警告 / 0 失败，rc=0，「测试文件覆盖」49 → **66**。
- `production_release_gate --release-ready --tag v5.6.0`（带 `.venv/bin` 进 PATH）：
  **8/8 全绿、`release_ready: true`、rc=0**；跑完 `git status` 仍为空。
- `audit_repo --strict`：**rc=1，唯一一条红**仍是既有的
  `Provenance source commit mismatch: manifest=a66040520139… vs HEAD=310774aea0de…`
  ——锚点按设计停在 tag 提交（见项目记忆「release 锚点」条），两份清单 `hash_mismatch_count` 为 0。

## 七、下一步

命令面这条轴到这里没有已知残留：66 条注册命令都有 argv 位证据，且证据来自哪条用例可逐条指认。
再往前要换轴，不再在同一个问题上加深（例如「走过 CLI 入口」不等于「断言了产物内容」——
`test` / `package` 两格今天靠桩把重活换掉，那是**接线证据**不是**行为证据**，
要不要把这两格升成行为级，属于下一个待裁项而不是本片欠账）。

### 收尾留痕（两条，都是过程事实）

1. **本片自查抓到一处我自己写下的误引**：第 39/40 片把 `ts_interface_shape.py` 说成同仓先例，
   该文件不在本仓（`import ast` 的真实同仓持有者是 `src/aipd_os/interface_contract.py` 与
   `src/aipd_os/schema_binding.py`，全仓未使用 tree-sitter）。两处已在提交 `c32ecb1` 更正，
   并由第 41 片的文档引用普查作为该类缺陷的第一批真读数。
2. **`commit -m` 里的反引号会被 shell 执行**：那次提交的正文里 `` `import ast` `` 被命令替换吃掉，
   留下「（ 在同仓的真实持有者是」这样的空位——提交内容与仓库文件都不受影响，
   但记号丢了。后续一律改用 `-F <文件>` 写提交说明。
3. **重锚漏暂存 RELEASE_MANIFEST.json，被 `workspace_clean` 当场拦住**：更正误引那一轮我
   重刷了两份清单，但 `git add` 的 pathspec 只列了 `CHANGELOG.md docs/audit PROVENANCE.json
   SOURCE_MANIFEST.json` ⇒ 磁盘已新、HEAD 仍旧，工作树一路带着 ` M RELEASE_MANIFEST.json`。
   `production_release_gate` 报 **7/8，红项 workspace_clean**、`release_ready: false`；
   补提交 `38ff731` 后回到 **8/8、rc=0、`release_ready: true`**。
   要记的是判据的**层级差**：`test_packaging` 那两条比的是"磁盘 ↔ 磁盘"，
   所以它对这种漂移全绿（17 passed），只有按 HEAD 记账的门禁看得见"未提交"这一半——
   一份一致性测试绿，不等于那份一致性已经进历史。
   终读数因此以 `38ff731` 为准：`audit_repo --strict` rc=1，唯一红项仍是
   `Provenance source commit mismatch: manifest=a66040520139… vs HEAD=38ff73172bf5…`。



