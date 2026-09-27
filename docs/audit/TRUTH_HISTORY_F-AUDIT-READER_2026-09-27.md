# `aipd truth history` 取证（F-AUDIT-READER 第 63 片，2026-09-27）

给 `audit_log` 补一张**带作用域的读表**。第 62 片刚把"链头有哪些有效要求"接上人读的口子，
这一片接的是"这些事实被谁改过"。

## 一、缺口在哪一侧（现读，不靠印象）

- 写侧不缺：`AIPDStateDB.add_audit`（`src/aipd_os/state/db.py:1073`）有这些调用点——
  `cli/commands_truth.py:448`（ctq.revise / ctq.deprecate）、`state/lineage.py:242,252`、
  `state/audit.py:37`、`state/recovery.py:235,277`、`experience/operations.py:202,271`、
  `mail/client.py:486`。
- 读侧只有 `list_audit(limit=100)`（`state/db.py:1082`）：`SELECT * FROM audit_log
  ORDER BY entry_id DESC LIMIT ?`——**没有 WHERE**，且截断不说。
  现役两个读者各自传 `limit=200`（`experience/owner_dashboard.py:62`、
  `experience/operations.py:224`），也没有总量。
- 结论：这不是"没数据"，是**读面缺作用域且会把截断读成全部**。

## 二、改了什么

| 位置 | 改动 |
| --- | --- |
| `src/aipd_os/state/db.py` | 新增 `audit_history(...)`：tenant/project/actor/actions/record_id/since/limit 全在 SQL 侧；`record_id` 用 `CASE WHEN json_valid(...) THEN json_extract(...,'$.record_id') END`；返回 `total`（与行集同一套 WHERE）、`returned`、`truncated`、`unparseable_rows`（按作用域谓词数，不含 payload 谓词）、`entries` |
| `src/aipd_os/cli/commands_truth.py` | 新增 `_audit_side`（None / dict / `_MISSING` 三态）、`_audit_diff`（渲染在读侧）、`cmd_truth_history`（读不出 2、成功 0、不写审计） |
| `src/aipd_os/cli/main.py` | `truth` 组下 `history` 子解析器（`--db --project --tenant --actor --action --record --since --limit --json`） |
| `src/aipd_os/cli/commands.py` | 派发表 `"truth history"` |
| `src/aipd_os/cli/command_contract.py` | 契约条目（PUBLIC / PRODUCT / 5.24） |
| `README.md` / `SKILL.md` / `src/aipd_os/registry_data.py` | 镜像：速查行 + 设计注释、分组条目与"主线共 64 个"、CTQ 那行的 run_command / unit_test / input_output / current_limitation |
| `tests/test_truth_history.py` | 新增 12 条（见 §四） |
| `tests/test_command_surface_census.py` | 分母 73 → 74（cli 档同为 74，满覆盖保持） |

## 三、现算读数（三条命令可复算；终读数见 §六）

- `aipd usage` 的 PUBLIC 数 63 → 64；argparse 声明树路径 89 → 90；注册命令 74、低于 cli 档 0。
- `ruff check src tests state_service` → `All checks passed!`；`mypy src` → `Success: no issues found in 245 source files`。
- `skill_quality_audit` / `doc_command_census` / `command_surface_census` 退出码均为 0，
  现状面缺陷 0 条。

## 四、常驻用例（12 条，每条对一个说谎方式）

`test_truth_history_is_registered_on_the_argparse_tree`、
`test_scoped_to_tenant_and_project_in_both_views`、
`test_record_filter_hits_the_before_side_and_names_both_ids`、
`test_limit_truncation_is_stated_not_hidden`、
`test_actor_filter_scopes_without_touching_other_peoples_rows`、
`test_unparseable_payload_is_counted_not_folded`、
`test_since_normalizes_timezones_and_filters`、
`test_changed_values_are_rendered_not_just_field_names`、
`test_listing_writes_no_audit_row`、
`test_failure_paths退2_and_emit_no_success_payload`、
`test_readme_quickref_lists_the_new_command`、
`test_action_filter_is_exact_not_a_prefix_glob`。

## 五、变异电池（八臂，改动点都写死在这里，可原地重放）

臂 1-5 在 `state/db.py`，6-8 在 `cli/commands_truth.py`：
`truncated` 恒 False；`unparseable_rows` 恒 0；撤掉 `json_valid` 兜底；
`total` 忽略 record 谓词（改成只按作用域数）；actor 谓词不进 SQL；
`--since` 不做 UTC 归一；`_audit_diff` 不产出任何值；读面往 `audit_log` 落一行。

首轮 **7/8**：`B3 撤掉 json_valid` SURVIVED——那支查询只在带 `--record` 时才走那段谓词，
而当时的用例只跑不带 record 的读法，**例外没有原告**。补上"脏行 + `--record` 同用"的断言后
终局 **8/8 KILLED / 0 SURVIVED / 0 INJECT-INVALID**，还原后 12 passed，
`db.py 11995290137e`、`commands_truth.py 1a37467a484c` 各自复原。

**本轮另两笔镜像账**（都当场改到绿，不留到下一片）：
- `SKILL.md` 的分组条目是给门**解析**的文本面，不是纯散文：我在里面用反引号包了
  `total`、`returned`、`truncated` 三个字段名，`skill_quality_audit` 与
  `test_command_coverage` 立刻报"声明但未注册的命令 ['returned','total','truncated']"。
  代码没错——是**字段名的写法与命令名同形**。修法：那张面上只给命令名加反引号。
- 夹具最初按「`ctq add` 会写审计行」写，五处同时红；重开写入点确认它今天**不写**，
  于是新增 `_one_change` 走 add+revise 造审计行，并把那格记进 §七的 F-AUDIT-WRITER。

## 六、终读数（干净工作树）

见收尾链路：取证工作树 @ 绑定前锚点提交，`collected/passed/skipped`、门禁 8/8、
`audit_repo --strict` 唯一 ✗（钉 v5.6.0 那条设计内的红）在绑定后由脚本从原件写在这里。

## 七、未证实与下一步

- **未证实**：存量开发者库上的真实审计行数与脏行比例（本仓规矩是不打开 `data/state.db`），
  所以"生产上到底有几行 payload 不是 JSON"只能等属主侧跑一次 `--json` 读数。
- **写入侧那一格（F-AUDIT-WRITER）**：`ctq add` 不写审计行 ⇒「谁第一次声明了这条要求」
  只能从记录自身的 `declared_by`/`created_at` 读，不在这张改动史上。补行会改写入语义，
  另立一片，不混进本轮。
- 两个现役 `list_audit(limit=200)` 读者（`experience/owner_dashboard.py:62`、
  `experience/operations.py:224`）还没换到新读面——它们同样在静默截断，属下一片范围。
