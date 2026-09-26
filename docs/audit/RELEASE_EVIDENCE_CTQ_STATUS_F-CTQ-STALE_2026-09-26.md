# F-CTQ-STALE 第 44 片：要求被标陈旧，不等于要求消失了

日期：2026-09-26 归属：发布就绪证据 / CTQ 覆盖分母
状态：已闭（缩水可见 + 常驻 6 条 + 电池 4 条）
落点：`src/aipd_os/release_manifest.py::_collect_ctq`
用例：`tests/test_release_evidence_ctq_status.py`

## 一、复现（先测出来再改）

`_collect_ctq` 用 `truth.query(record_type="ctq", status="active")` 取分母。
最简夹具实测（两条 CTQ，第二条 `set_status(..., "stale")`，其余条件不变）：

```
ctq ids in doc: ['T-001']
issues kinds:   ['no_drawings', 'bom_db_missing']
```

**T-002 从证据里彻底消失，issues 一个字都没提它。** 而门禁的
`gdt_covers_ctq` / `ctq_has_inspection` 是拿 `doc["ctq"]` 当要求面的：
两条变一条，覆盖义务就少一条。只有全部掉光时才由 `no_ctq` 兜住——
所以这是一条**部分缩水即放行**的 fail-open 通路，不是"少报一条"的表述问题。

反讽之处要说清：这个函数自己的 docstring 就写着"缺 feature 的逐条点名（不静默少一条）"。
它对"字段缺"守了纪律，对"状态不在 active"没守——**同一函数内的两种"少一条"，
只有一种被认为需要交代**。这类"纪律只覆盖想到的那一半"是本仓反复出现的形状。

## 二、改判与边界

| 状态 | 进覆盖分母？ | 出点名？ | 阻断？ | 理由 |
| --- | --- | --- | --- | --- |
| `active` | 是 | 缺 feature / 缺检验方法才点 | 是（原有判据不变） | — |
| `stale` / `expired` / `blocked` | **否** | 逐条，带 record_id 与状态名 | **是** | 这是"还没收口的要求"，不是"少一条要求" |
| `superseded` | 否 | 逐条 | 否 | 被新版本取代是合法处置；但分母为什么小了必须让读者看见 |
| 枚举外的状态 | 否 | 逐条 | 是 | **兜底 hardening**：`store.update` 把状态核在 `TRUTH_STATUS` 内，今天没有生产者能写进去（按本仓纪律，没有生产者的守卫要标成加固而不是当成现状） |

分母语义**没有**放宽：陈旧要求不会被拿去和图纸硬核对（那是另一种错——
把没收口的东西当已核对）。变的只有一条：**缩水必须可见**。

## 三、常驻用例（6 条）与两条方向对照

除金路径与序列化外，特意配了两条"另一头"的对照：

- `test_clean_database_does_not_fire_the_new_criterion`：全 active 时新判据必须闭嘴
  （否则它只是一个永远抱怨的判据，下一轮就会被当成噪声关掉）；
- `test_denominator_shrink_is_now_visible`：同一条 CTQ 标 stale 前后，
  分母从 2 变 1（语义不变）**且**点名必须出现——两头各钉一格。
  电池里的 D4（非 active 也收进分母）就是这条对照的注入形态，半径 5 条。

## 四、撤改电池（`/tmp/s44/battery.py`，4 条：杀 4 / 存活 0 / 注入无效 0）

| 注入 | 半径 |
| --- | --- |
| D1 未收口的 CTQ 降级成非阻断 | 2 |
| D2 把 `superseded` 也当成未收口 | 1 |
| D3 点名只写条数不写 record_id | 3 |
| D4 非 active 也收进覆盖分母（反向） | 5 |

对照臂先立（未注入 rc=0）；每条只动它自己那一处，还原按被改文件 sha 比。

## 五、与第 43 片的关系

上一轮之前，"CTQ 被标 stale"几乎只会发生在测试里；`drawing spec` 写出血缘边之后，
`aipd truth propagate --upstream <CTQ>` 会让**图纸声明**被打 stale，而 `truth propagate`
本身也会把上游 CTQ 之外的下游纳入 stale 集合——也就是说"库里存在非 active 的 CTQ"
从理论状态变成日常状态。**这两片是同一件事的两半**：先有了会动的血缘，
再让"动过的要求"必须被看见。若只做 43 不做 44，传播越准，放行反而越松。

## 六、复算入口

```
.venv/bin/python -m pytest tests/test_release_evidence_ctq_status.py -q      # 6 条
.venv/bin/python /tmp/s44/battery.py                                          # 4 条撤改
.venv/bin/python -m pytest tests -k "release_manifest or production_release_gate or golden"
```

## 七、终读数

- 全量：待本轮收尾（预期 2308 passed / 3 skipped，collected 2311）
- `production_release_gate --release-ready --tag v5.6.0`：待填
- `audit_repo --strict`：待填
