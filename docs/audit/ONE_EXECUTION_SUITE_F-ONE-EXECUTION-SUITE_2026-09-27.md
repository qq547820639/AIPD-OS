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

## 五、终局读数（占位）
