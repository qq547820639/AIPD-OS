# F-LINEAGE-PROD 第 43 片：CTQ → 图纸声明的血缘生产者

日期：2026-09-26 归属：Product Truth 血缘 / 失效传播覆盖面
状态：已闭（第二跳传播得到，常驻 10 条 + 电池 6 条 + 生产者两向棘轮）
落点：`src/aipd_os/cad/spec_lineage.py`、`src/aipd_os/cli/commands_drawing.py`
用例：`tests/test_drawing_spec_lineage.py`

## 一、先把一句旧断言核实，而不是直接动手

登记与 `docs/architecture/truth_architecture.md` 都写着「血缘边只有
`product_intelligence/gate.commit_snapshot` 会写，CTQ/图纸/BOM 之间没有生产者」。
按"名字 grep 数调用点"会得出**不一样的**结论：`grep add_edge(` 在 `src/` 里有 7 处。
分两层判才算对：

| 判据 | 读数 | 结论 |
| --- | --- | --- |
| SQL 写入口 `INTO truth_lineage` | 只有 `product_truth/lineage.py` 一处 | 所有 truth 边都必须走 `LineageGraph.add_edge`，没有绕过环检测的第二条路 |
| `add_edge` 调用点（AST） | 7 处 / 5 个文件 | 其中 `idea/decomposer.py`、`idea/evidence_relations.py`、`product_intelligence/service.py` 三处调的是 **canonical lineage 那张表**（节点是 `LineageNodeRef`），不是 truth_lineage |

所以旧断言对 `truth_lineage` 成立；把它写成"全仓只有一处在写血缘"就是错的——
两张同名表是这个仓库里最容易混的一层（`truth_lineage` 与 canonical `lineage`），
本轮把它写进棘轮而不是只写进散文。

## 二、加了什么

`aipd drawing spec` 成功落盘 ⇒ `record_spec_lineage()` 写

- 一条 `record_type="artifact_version"` 记录，content =
  `drawing spec <文件名> sha256=<正文哈希前 16> ← CTQ <引用列表>`，
  `source.file` 指声明文件本身，metadata 带 `path/spec_sha256/ctq_refs`；
- 每条**声明正文实际引用到**的 `ctq_ref` 一条 `ctq → 该记录` 的 `affects` 边。

三条取舍与理由：

1. **选择性**：只连正文里剩下的 `ctq_ref`。`spec_from_ctq` 会把有歧义/未收口的条目的
   `ctq_ref` 摘掉，所以"正文里有的"才是真参与者。给没参与的 CTQ 连边＝以后它一改，
   这份与它无关的声明就被打 stale。
   这一条只能在**函数级**测：CLI 面上"未引用的 active CTQ"根本走不到——它会先制造
   gap 让整条命令 HOLD。选择性用例因此手写一份 spec 直接喂生产者。
2. **HOLD 不写血缘**：与"半成品声明不落盘"同一条理由，一份不存在的声明没有版本可言。
3. **信任上限 high**：正文哈希是自证的，"生成过程对不对"没有独立复核。
   与第 42 片 `_write_back_facts` 同一取舍（那轮的 C5/B2 型注入这轮也配了一条）。

幂等键是 (类型, content, tenant, project)：内容没变重跑命中同一行；
CTQ 改了 ⇒ 正文变 ⇒ 自然另起一版（用例里真的改一次 CTQ 再跑，读数是 1 行→2 行）。

## 三、失败面：机器面与终端面差点各说一套

`test_lineage_failure_is_not_reported_as_success` 第一轮红的时候暴露的不是注入问题，
是我自己的实现：血缘写失败时退码给 4，但 `result["ok"]` 早在 gap 判定时就按
`not held` 定成了 `true`，于是 `--json` 输出 `"ok": true` + 进程退出 4。
修法是失败分支同时改判 `ok`，并把这条断言写进用例（`payload["ok"] is False`）。
另记一处小坑：`sqlite3.OperationalError.__name__` 是 `OperationalError`（不带模块前缀），
按 `"sqlite3.OperationalError"` 去匹配错误文案是打不中的——断言文案要按实际产出写。

## 四、撤改电池（`/tmp/s43/battery.py`，6 条：杀 6 / 存活 0 / 注入无效 0）

| 注入 | 半径 |
| --- | --- |
| C1 CLI 不再调生产者（文件照写、退码照 0） | 5（含接线棘轮） |
| C2 血缘写不进去时不改 `ok` | 1 |
| C3 连边改成"给全部 active CTQ 连" | 1（选择性那条） |
| C4 去掉幂等预检 | 1 |
| C5 信任写成常量 `verified` | 1 |
| C6 删掉 `add_edge` 循环（记录写了、边没连） | 5（含生产者棘轮：文件从登记集合里掉出去） |

对照臂（未注入）rc=0 先立；每条注入后按**被改的那个文件**比 sha 还原；
`rc==1 且半径为 0` 记「注入无效」而不是「杀掉」。

## 五、仍然没有的那一半

- **图纸 DXF / BOM / 成本**：没有血缘生产者。今天通的只有 CTQ → 声明这一跳；
  声明 → DXF、BOM 行 → 成本结论这些边还不存在，所以它们仍不会被传播打到。
- **返工的执行**：`run_rework` 在产品侧仍是 0 调用点，
  由 `tests/test_truth_propagate_cli.py::TestUnwiredHalfStaysVisible` 钉着；
  接执行器那一轮必须连同那条断言的极性一起改判。
- 下一片入口二选一：(a) 给「声明 → DXF/BOM/成本」补同类生产者
  （`drawing generate` 与 `bom`/`cost` 已经知道自己在处理哪份声明/哪张 BOM，
  边是有据可查的）；(b) 接真实返工执行器，把 stale 之后"谁来重跑"补上。

## 六、复算入口

```
.venv/bin/python -m pytest tests/test_drawing_spec_lineage.py -q          # 10 条
.venv/bin/python /tmp/s43/battery.py                                      # 6 条撤改
.venv/bin/python -m pytest tests -k "drawing or truth or propagat"        # 连带面
```

## 七、终读数

- 全量：待收尾（预期 2302 passed / 3 skipped，collected 2305）
- `production_release_gate --release-ready --tag v5.6.0`：待填
- `audit_repo --strict`：待填
