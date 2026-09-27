# 执行套件只许有一处构造（F-ONE-EXECUTION-SUITE，第 72 片，2026-09-27）

产物：`Supervisor._execution_suite` / `_run_capability`（唯一构造点与唯一 `router.run`）、
`rerun_for_rework` 作用域改为从工作项行读、`tests/test_supervisor_execution.py` 两条守卫、
`docs/audit/s72/battery72.py`（4 臂）。不改命令、旗子、登记文案与矩阵。

## 一、上一轮留下的债长什么样

第 71 片的 `rerun_for_rework` 复制了这五步。复制不会变红，只会**慢慢不一样**：

| 维度 | `run_supervisor` 里 | `rerun_for_rework` 里（第 71 片） | 后果 |
| --- | --- | --- | --- |
| 日志器 | `get_logger("aipd.router")` | 模块级 `logger`（`aipd.supervisor`） | router 的日志少一路，出事时看不出是谁 |
| 项目作用域 | `_resolve_project_id(project_id)` | `self.project_id()`（构造参数） | 跨项目重跑把 run/证据记到错项目 |
| context | 一份（work/project/tenant） | 又一份 | 两处字段可以各自演化 |

第 71 片的取证文档 §六.3 当时把这条记成"待抽共用函数"；本轮收掉，并加守卫防止再长第二处。

## 二、守卫的形状（两极都要能红）

- AST 计数：`ExecutionRouter(` / `build_registry(` / `router.run(` 在 `supervisor.py` 内**各恰好 1 处**。
  "恰好"而不是"至多"：拆掉共用口子也要红，否则守卫会跟着被删的实现一起自绿。
- 功能断言：Supervisor 构造指向 `P-ZZZ`、工作项在 `P1` ⇒ 重跑出的 run 记在 `P1`。
  这一条是那个真 bug 的反证；上一轮的用例都同项目，所以看不见它。

## 三、电池（4 臂，杀 4 活 0）

K1 在 rerun 里再抄一遍套件 → 结构守卫红；K2 把共用口子里的 `ExecutionRouter` 换成别的工厂名
（等于拆掉构造点）→ 守卫同样红（证明它不是单向）；K3 作用域退回构造参数 → 功能断言红；
K4 再加一处直接 `router.run` → `router.run` 计数守卫红。

## 四、下一片入口

1. 窄档两个手写词表的自证（第 67 片起挂着）：拿被挡掉的 20 句做常驻阴性夹具。
2. 第 64 片留的 `doc_command_census` 只报面收窄。
3. 本轮新记：`evidence_rework` 依赖 `Supervisor.rerun_for_rework`，而 CLI 每次都新建一个
   `Supervisor(...)`（构造里有建表/迁移）。要不要复用同一个实例，等真有性能或并发证据再动。

## 五、终局读数（由 `docs/audit/s72/terminal72.py` 从原件现跑生成，不手抄）

- **签出那一跑**（`tmp/s72/final`，报告产出于提交 `981c71c`，主树当时 HEAD `26a851c`）：`exitcode=0`、`collected=2589`、`passed=2586`、`skipped=3`、其余终态 `{'skipped': 3}`、用时 `238.9s`、`root=/Volumes/Extra/CodeProj/AI全链路自研/tmp/s72/final`、`source_commit=a66040520139`
- **本片主角（真仓库终态）**：`rc=0`；语料：84 个能力，带否定词的句子 36 句；账本登记 13 条，未挂锚点 29 句（宽档，只报不判）；能力缺失句（窄档＝判据面）：16 句 = 登记 6 + 豁免 10 + **未处置 0**；判红 0 条：登记的 13 句「仍缺着」现在都还缺着
- **`--self-test`**：`rc=0`，**23 条**合成读数全对上（含存在式登记、去处台账与 `table_ddl` 双向）
- **常驻用例**：`pytest tests/test_supervisor_execution.py tests/test_absence_claim_census.py -q` → `32 passed, 24 warnings in 22.85s`（rc=0）
- **变异电池（入库副本现跑）**：`docs/audit/s72/battery72.py` → `rc=0`，合计 KILLED 4 / 其余 0
- **两档分母现读**：宽档 36 句、窄档 16 句（差 20 句是谈判决/谈口径的假阳性）；登记表解析问题 `[]`；薄理由豁免 `[]`
- **第 64 片那台收尾验签在本片树上**：`rc=0`；收尾验签（报告 ↔ 证据 ↔ 工作树）；读数：报告 2589 条 / 211 个文件，树 211 个文件 / 2503 个 def，终态 {'passed': 2586, 'skipped': 3}
- **发布门禁**：`rc=0`、`"passed": true` 计 8 条、`release_ready` true
- **沿第 71 片那条轴的读数（本片未加新档）**：`external_callers` 对 `commit_approved` / `commit_snapshot` 判 HOLDS，正向对照 `record_dxf_lineage` 判 CONTRADICTED（同一函数换个名字就翻红 ⇒ 探针会开火；第一版这里用的是改口前的旧锚点，读出来是「账文脱钩」而不是「过期」，已更正）
- **`audit_repo --strict`**：`rc=1`，恰 **1** 条 ✗（`✗ Provenance source commit mismatch: manifest=a66040520139… vs HEAD=26`）——设计内不修
- **锚点与哈希面**：`SOURCE_MANIFEST.source_commit` = `a66040520139` == tag；被哈希文件数 `674`；**相对 tag v5.6.0** 的清单：新增 163 个、消失 9 个（这是 25 片的累计漂移，不是本片增量——本片增量看 `chore(sN): 清单再锚` 那两条提交里的文件数）
- **相对 tag 新增的被哈希文件（前 5 个）**：`assets/templates/fact.json`、`docs/architecture/project_boundary.md`、`docs/architecture/state_infrastructure.md`、`docs/architecture/state_inventory.md`、`scripts/absence_claim_census.py`
- **工作树**：`git status --porcelain` 输出 0 行

**这一节的来源**：`terminal72.py` 是从第 71 片脚本复制来的，两处措辞（"本片新档"、
"含四档去处判决"）是上一片的结论而非本片事实——正是我这一片刚写进记忆的那类
"复制脚本文案"错，被自己在生成物里又犯了一次；已在脚本与本文同时改成"沿用上片档位"。
本片真正新增的是两条守卫（AST 单点 + 跨项目作用域），它们在 §三 的电池里各自有开火证明。
