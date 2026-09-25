# F-FACT-WB 第 42 片：主管自述"事实写回"，但库里没有那一行

日期：2026-09-26 归属：主管执行 ↔ Product Truth 一致性
状态：已闭（写回真落库，常驻 7 条 + 电池 6 条）
落点：`src/aipd_os/supervisor/supervisor.py` 用例：`tests/test_supervisor_fact_writeback.py`

## 一、这根轴为什么存在

`run_supervisor` 的成功分支里有这么一句：

```
steps_log += ["register_artifact", "update_facts_evidence",
              "run_independent_quality_gate", ...]
```

它**只是把名字追加进一个字符串列表**。同一分支真正执行的只有
`complete → _register_outputs → _quality_gate → _mark_stale`：注册工件、跑独立质量门、
标 stale——没有一句把事实或证据写回任何结构化表。于是三处下游把这串自述当事实读：

1. `results[i]["steps"]` 的读者（CLI、e2e 断言、人）看到 `update_facts_evidence`；
2. 能力登记 `supervisor.fact_writeback` 的 `e2e_evidence` 写着"执行日志/血缘写回，
   但未写入独立 facts 事实表"——它描述的是**另一件不存在的事**（"独立 facts 表"），
   因为 `product_truth` 表自 v5.9 起就在 store 的建表脚本里；
3. `current_limitation` 那句「全库无独立 product_truth/facts 表」因此一路错了几轮，
   没有人拿结构事实去对它。

第 41 片装的文档引用普查抓不到这类病——它核"引用指得回文件吗"，
这里文件、表、方法名全都指得回，**错的是"说做过"与"做过"之间的差距**。

## 二、改了什么

`Supervisor._write_back_facts(wid, capability_floor, out, gate)`：向 `product_truth`
写一条 `record_type="evidence"` 的记录，成功分支里在质量门之后调用它。四条设计取舍：

| 取舍 | 定法 | 为什么 |
| --- | --- | --- |
| 幂等键 | `(record_type, content, tenant, project)`，content = 能力 + run 标识 + 输出哈希 | 同一 run 重放不重复建行；换 run 就是新证据，**该**另起一行 |
| 作用域 | 从 `supervisor_work_items` 行取，取不到才回落实例 scope | 写死 `default` 会让多项目库里第二条永远被"跨项目去重"吞掉（注入 B4 半径 4 条） |
| 信任分级 | 门 `pass` → `high`，否则 `low`；**上限 high，永不 verified** | `_quality_gate` 只核"证据引用与输出哈希在不在"，不是对内容的外部核验；写 `verified` 与第 32/34 片那族"机器默认值被读成权威"同形 |
| 失败面 | 异常不中断执行，但 `record_id` 置 None 且步骤标签改判 `fact_writeback_failed` | 静默保留 `update_facts_evidence` 等于把本轮的原始缺陷原地复现一遍 |

`source.file` 取执行留下的**首条**证据引用（不是新造的字符串），多产物时只记第一条——
这条限制写在登记的 `current_limitation` 里，不藏在代码里。

## 三、撤改电池（`/tmp/s42/battery.py`，6 条：杀 6 / 存活 0 / 注入无效 0）

对照臂（未注入）rc=0 先立；注入按"看起来合理的错误实现"写，不写会崩的假注入；
还原按被改文件自身的 sha 比对。

| 注入 | 半径 |
| --- | --- |
| B1 撤掉调用、改成伪造一份「看起来成功」的摘要 | 5 条（含幂等与作用域） |
| B2 信任分级写成常量 `verified` | 2 条（门推导 + 上限） |
| B3 去掉幂等预检 | 1 条 |
| B4 store 作用域写死 `default` | 4 条 |
| B5 写回失败静默（给个假 record_id、标签不改判） | 1 条 |
| B6 把「全库无独立 product_truth 表」这句旧错话抄回登记 | 1 条 |

B6 是给"登记措辞"这一条自己的对照：那条用例只写"不许出现某句话"的话，
删掉断言就能永久绿灯，所以它必须能被"把错话抄回来"打红。

## 四、没做的部分与下一片入口

- **不写 `truth_lineage` 边**：工作项（`W-xxx`）与上游 truth 记录之间今天没有映射关系，
  硬造一条边等于把"PI 需求 → truth"这条唯一真实在写的血缘之外再铺一条假边。
  后果要说清：这条 evidence 今天**不会**被 `aipd truth propagate` 传播到，
  所以能力分类留在 `partially_implemented`，没有因为本轮而升档。
- 下一片入口：给"图纸/BOM/成本 制品 ↔ 上游 truth"补血缘边的**生产者**
  （第 39/40/41 片之后 `product_truth.impact_propagation` 那行的限制里还写着
  "CTQ/图纸/BOM 之间没有生产者"）。
- 另一条已经量出来但没动的：`PropagationEngine.run_rework` 在 `src/` 里仍是 0 调用点，
  且这一半已被 `tests/test_truth_propagate_cli.py::TestUnwiredHalfStaysVisible` 钉成断言——
  接执行器那一轮必须连它一起改判，本轮不动它。

## 五、复算入口

```
.venv/bin/python -m pytest tests/test_supervisor_fact_writeback.py -q      # 7 条
.venv/bin/python /tmp/s42/battery.py                                      # 6 条撤改
.venv/bin/python -m pytest tests -k "supervisor or capabilit or registry" # 连带面
```

## 六、终读数

- 全量：待本轮收尾（预期 2292 passed / 3 skipped，collected 2295）
- `production_release_gate --release-ready --tag v5.6.0`：待填
- `audit_repo --strict`：待填
